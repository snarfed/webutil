"""Unit tests for flask_util.py."""
import datetime
import os
import unittest

from flask_caching import Cache
from flask import Flask, flash, get_flashed_messages, make_response, request
from werkzeug.exceptions import BadRequest

from .. import flask_util
from ..flask_util import get_required_param


class FlaskUtilTest(unittest.TestCase):
  def setUp(self):
    self.app = Flask('test_flask_util')
    self.app.url_map.converters['regex'] = flask_util.RegexConverter
    self.app.config.from_mapping({
      'TESTING': True,
      'SECRET_KEY': 'sooper seekret',
      'CACHE_TYPE': 'SimpleCache',
    })
    self.client = self.app.test_client()

  def test_regex_converter(self):
    @self.app.route('/<regex("abc|def"):letters>')
    def fn(letters):
      return ''

    with self.app.test_client() as client:
      resp = client.get('/def')
      self.assertEqual(200, resp.status_code)
      self.assertEqual('def', request.view_args['letters'])

      resp = client.get('/xyz')
      self.assertEqual(404, resp.status_code)

  def test_get_required_param(self):
    for ctx in (
        self.app.test_request_context('/?x=y&z='),
        self.app.test_request_context(method='POST', data={'x': 'y', 'z': ''}),
    ):
      with ctx:
        self.assertEqual('y', get_required_param('x'))
        with self.assertRaises(BadRequest):
            get_required_param('z')
        with self.assertRaises(BadRequest):
            get_required_param('a')

  def test_cached(self):
    cache = Cache(self.app)
    calls = 0

    def view():
      nonlocal calls
      calls += 1

      if 'flash' in request.args:
        flash('foo')

      resp = make_response(str(calls))

      if 'set-cookie' in request.args:
        resp.set_cookie('kooky')

      if '500' in request.args:
        resp.status_code = 500

      return resp

    @self.app.route('/foo')
    @flask_util.cached(cache, datetime.timedelta(days=1))
    def foo():
      return view()

    client = self.app.test_client(use_cookies=False)
    client.get('/foo?500')
    self.assertEqual(1, calls)

    client.get('/foo?500')
    self.assertEqual(2, calls)

    client.get('/foo?flash')
    self.assertEqual(3, calls)

    client.get('/foo?cache=false')
    self.assertEqual(4, calls)

    client.get('/foo?xyz')
    self.assertEqual(5, calls)

    client.get('/foo?abc')
    self.assertEqual(6, calls)

    resp = client.get('/foo?abc')
    self.assertEqual(6, calls)
    self.assertEqual('6', resp.get_data(as_text=True))

    client.get('/foo')
    self.assertEqual(7, calls)

    client.get('/foo', headers={'Cookie': 'bar'})
    self.assertEqual(8, calls)

    client.get('/foo?set-cookie')
    self.assertEqual(9, calls)

    resp = client.get('/foo')
    self.assertEqual(9, calls)
    self.assertEqual('7', resp.get_data(as_text=True))

    resp = client.head('/foo?head')
    self.assertEqual(10, calls)

    resp = client.get('/foo?head')
    self.assertEqual(11, calls)
    self.assertEqual('11', resp.get_data(as_text=True))

  def test_cached_http_5xx(self):
    cache = Cache(self.app)
    calls = 0

    @self.app.route('/error')
    @flask_util.cached(cache, datetime.timedelta(days=1), http_5xx=True)
    def error():
      nonlocal calls
      calls += 1
      return '', 500

    resp = self.client.get('/error')
    self.assertEqual(500, resp.status_code)
    self.assertEqual(1, calls)

    resp = self.client.get('/error')
    self.assertEqual(500, resp.status_code)
    self.assertEqual(1, calls)

  def test_cached_flask_util_error(self):
    cache = Cache(self.app)
    calls = 0

    @self.app.route('/error')
    @flask_util.cached(cache, datetime.timedelta(days=1))
    def error():
      nonlocal calls
      calls += 1
      flask_util.error('asdf', status=400)

    resp = self.client.get('/error')
    self.assertEqual(400, resp.status_code)
    self.assertEqual(1, calls)

    resp = self.client.get('/error')
    self.assertEqual(400, resp.status_code)
    self.assertEqual(1, calls)

  def test_cached_headers(self):
    cache = Cache(self.app)
    calls = 0

    @self.app.route('/foo')
    @flask_util.cached(cache, datetime.timedelta(days=1),
                       headers=('Accept', 'Vary'))
    def foo():
      nonlocal calls
      calls += 1
      return ''

    client = self.app.test_client()
    client.get('/foo', headers={'Accept': 'bar'})
    self.assertEqual(1, calls)

    client.get('/foo', headers={'Accept': 'bar'})
    self.assertEqual(1, calls)

    client.get('/foo', headers={'Accept': 'baz'})
    self.assertEqual(2, calls)

    client.get('/foo', headers={'Accept': 'baz', 'Vary': 'biff'})
    self.assertEqual(3, calls)

    client.get('/foo', headers={'Accept': 'bar'})
    self.assertEqual(3, calls)

    client.get('/foo', headers={'Accept': 'baz', 'Vary': 'biff'})
    self.assertEqual(3, calls)

  def test_canonicalize_domain_get(self):
    @self.app.route('/', defaults={'_': ''})
    @self.app.route('/<path:_>')
    def view(_):
      return '', 204

    self.app.before_request(flask_util.canonicalize_domain('from.com', 'to.org'))

    # should redirect
    for url in '/', '/a/b/c', '/d?x=y':
      for scheme in 'http', 'https':
        resp = self.client.get(url, base_url=f'{scheme}://from.com')
        self.assertEqual(301, resp.status_code)
        self.assertEqual(f'{scheme}://to.org{url}', resp.headers['Location'])

    # shouldn't redirect
    for base_url in 'http://abc.net', 'https://to.org':
      resp = self.client.get('/', base_url=base_url)
      self.assertEqual(204, resp.status_code)
      self.assertNotIn('Location', resp.headers)

  def test_canonicalize_domain_post(self):
    @self.app.route('/<path:_>', methods=['POST'])
    def view(_):
      return '', 204

    self.app.before_request(
      flask_util.canonicalize_domain(('from.com', 'from.net'), 'to.org'))

    # should redirect and include *args
    for base_url in 'http://from.com', 'http://from.net':
      resp = self.client.post('/x/y', base_url=base_url)
      self.assertEqual(301, resp.status_code)
      self.assertEqual('http://to.org/x/y', resp.headers['Location'])

    # shouldn't redirect, should include *args
    for base_url in 'http://abc.net', 'https://to.org':
      resp = self.client.post('/x/y', base_url=base_url)
      self.assertEqual(204, resp.status_code)
      self.assertNotIn('Location', resp.headers)

  def test_flash(self):
    with self.app.test_request_context('/'):
      flask_util.flash('foo')
      flask_util.flash('bar')
      self.assertEqual(['foo', 'bar'], get_flashed_messages())


class XrdOrJrdTest(unittest.TestCase):
  def setUp(self):
    super().setUp()

    class View(flask_util.XrdOrJrd):
      def template_prefix(self):
        return 'test_handler_template'

      def template_vars(self, **kwargs):
        return {'foo': 'bar'}

    self.View = View

    self.app = Flask('XrdOrJrdTest')
    self.app.config['TESTING'] = True
    self.app.template_folder = os.path.dirname(__file__)

    view_func = View.as_view('XrdOrJrdTest')
    self.app.add_url_rule('/', view_func=view_func)
    self.app.add_url_rule('/<path>', view_func=view_func)

    self.client = self.app.test_client()

  def assert_jrd(self, resp, expected={'foo': 'bar'}):
    self.assertEqual(200, resp.status_code)
    self.assertEqual('application/jrd+json', resp.headers['Content-Type'])
    self.assertEqual(expected, resp.json)

  def assert_xrd(self, resp, expected='<XRD><Foo>bar</Foo></XRD>'):
    self.assertEqual(200, resp.status_code)
    self.assertEqual('application/xrd+xml; charset=utf-8',
                     resp.headers['Content-Type'])
    self.assertEqual(expected, resp.get_data(as_text=True))

  def test_xrd_or_jrd_handler_default_jrd(self):
    self.assert_jrd(self.client.get('/'))
    for resp in (self.client.get('/x.xrd'),
                 self.client.get('/x.xml'),
                 self.client.get('/?format=xrd'),
                 self.client.get('/?format=xml'),
                 self.client.get('/', headers={'Accept': 'application/xrd+xml'}),
                 self.client.get('/', headers={'Accept': 'application/xml'}),
                 ):
      self.assert_xrd(resp)

  def test_xrd_or_jrd_handler_default_xrd(self):
    self.View.DEFAULT_TYPE = flask_util.XrdOrJrd.XRD

    self.assert_xrd(self.client.get('/'))
    for resp in (self.client.get('/x.jrd'),
                 self.client.get('/x.json'),
                 self.client.get('/?format=jrd'),
                 self.client.get('/?format=json'),
                 self.client.get('/', headers={'Accept': 'application/jrd+json'}),
                 self.client.get('/', headers={'Accept': 'application/json'}),
                 ):
      self.assert_jrd(resp)

  def test_xrd_or_jrd_handler_accept_header_order(self):
    self.assert_jrd(self.client.get('/', headers={
      'Accept': 'application/jrd+json,application/xrd+xml',
    }))
    self.assert_xrd(self.client.get('/', headers={
      'Accept': 'application/xrd+xml,application/jrd+json',
    }))
