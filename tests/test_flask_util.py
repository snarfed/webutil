"""Unit tests for flask_util.py."""
import os
import unittest

from flask import Flask, request
from flask.views import View
from werkzeug.exceptions import BadRequest

from .. import flask_util
from ..flask_util import get_required_param, not_5xx


class FlaskUtilTest(unittest.TestCase):
  def setUp(self):
    self.app = Flask('test_regex_converter')
    self.app.url_map.converters['regex'] = flask_util.RegexConverter
    self.app.config['TESTING'] = True

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
    for ctx in (self.app.test_request_context('/?x=y&z='),
                self.app.test_request_context(data={'x': 'y', 'z': ''})):
      with ctx:
        self.assertEqual('y', get_required_param('x'))
        with self.assertRaises(BadRequest):
            get_required_param('z')
        with self.assertRaises(BadRequest):
            get_required_param('a')

  def test_not_5xx(self):
    for bad in (None, 'body', ('body',), ('body', 200), ('', 400)):
      self.assertTrue(not_5xx(bad))

    self.assertFalse(not_5xx(('body', 500)))


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
