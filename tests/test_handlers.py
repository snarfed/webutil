"""Unit tests for handlers.py.
"""
from collections import defaultdict
from datetime import timedelta
import os
import socket
import traceback
import urllib.error

import webapp2

from .. import handlers
from ..testutil import HandlerTest

handlers.JINJA_ENV.loader.searchpath.append('/')


class FakeTemplateHandler(handlers.TemplateHandler):
  def template_file(self):
    return os.path.join(os.path.dirname(__file__), 'test_handler_get.tmpl')

  def template_vars(self):
    return {'foo': 'bar'}

  def content_type(self):
    return 'text/baz'

  def handle_exception(self, e, debug):
    traceback.print_exc()
    raise e


class HandlersTest(HandlerTest):

  def test_handle_exception(self):
    class Handler(webapp2.RequestHandler):
      handle_exception = handlers.handle_exception
      err = None

      def get(self):
        raise self.err

    app = webapp2.WSGIApplication([('/', Handler)])

    # HTTP exception
    Handler.err = urllib.error.HTTPError('/', 408, 'foo bar', None, None)
    resp = app.get_response('/')
    self.assertEqual(408, resp.status_int)
    self.assertEqual('HTTP Error 408: foo bar', resp.text)

    # network failure
    Handler.err = socket.timeout('foo bar')
    resp = app.get_response('/')
    self.assertEqual(504, resp.status_int)
    self.assertEqual('Upstream server request failed: foo bar', resp.text)

    # other exception
    Handler.err = AssertionError('foo')
    resp = app.get_response('/')
    self.assertEqual(500, resp.status_int)

  def test_redirect(self):
    class Handler(webapp2.RequestHandler):

      @handlers.redirect('from.com', 'to.org')
      def get(self):
        self.response.set_status(204)

      @handlers.redirect(('from.com', 'from.net'), 'to.org')
      def post(self, first, second):
        self.response.set_status(205)

    app = webapp2.WSGIApplication([('/(.*)/(.*)', Handler),
                                   ('.*', Handler)])

    # should redirect
    for url in '/', '/a/b/c', '/d?x=y':
      for scheme in 'http', 'https':
        resp = app.get_response(url, base_url=scheme + '://from.com')
        self.assertEqual(301, resp.status_int)
        self.assertEqual(f'{scheme}://to.org{url}', resp.headers['Location'])

    # should redirect and include *args
    for url in 'http://from.com', 'http://from.net':
      resp = app.get_response('/x/y', method='POST', base_url=url)
      self.assertEqual(301, resp.status_int)
      self.assertEqual('http://to.org/x/y', resp.headers['Location'])

    for base_url in 'http://abc.net', 'https://to.org':
      # shouldn't redirect
      resp = app.get_response('/', base_url=base_url)
      self.assertEqual(204, resp.status_int)
      self.assertNotIn('Location', resp.headers)

      # shouldn't redirect, should include *args
      resp = app.get_response('/x/y', method='POST', base_url='http://')
      self.assertEqual(205, resp.status_int)
      self.assertNotIn('Location', resp.headers)

  def test_template_handler_unicode_error(self):
    resp = webapp2.WSGIApplication([('/', FakeTemplateHandler)]
                                   ).get_response('/?x=%C0%AF')
    self.assertEqual(400, resp.status_int)
    self.assertIn("Couldn't decode query parameters as UTF-8", resp.text)

  def test_template_handler_get_jinja(self):
    resp = webapp2.WSGIApplication([('/', FakeTemplateHandler)]).get_response('/')
    self.assertEqual("""\
my host: localhost:80
my foo: bar""", resp.text)

  def test_cache_response(self):
    class Handler(webapp2.RequestHandler):
      calls = 0

      @handlers.cache_response(timedelta(days=1), size=1000)
      def get(self):
        Handler.calls += 1
        self.response.set_status(204)
        self.response.out.write(f'got {self.request.url}')

    app = webapp2.WSGIApplication([('.*', Handler)])

    # first fetch populates the cache
    resp = app.get_response('/?x')
    self.assertEqual(1, Handler.calls)
    self.assertEqual(204, resp.status_int)
    self.assertEqual('got http://localhost/?x', resp.text)

    # second fetch should use the cache instead of fetching from the silo
    resp = app.get_response('/?x')
    self.assertEqual(1, Handler.calls)
    self.assertEqual(204, resp.status_int)
    self.assertEqual('got http://localhost/?x', resp.text)

    # fetches with ?cache=false shouldn't use the cache
    resp = app.get_response('/?x&cache=false')
    resp = app.get_response('/?x&cache=false')
    self.assertEqual(3, Handler.calls)
    self.assertEqual(204, resp.status_int)
    self.assertEqual('got http://localhost/?x&cache=false', resp.text)

    # a different URL shouldn't be cached
    resp = app.get_response('/?y')
    self.assertEqual(4, Handler.calls)
    self.assertEqual(204, resp.status_int)
    self.assertEqual('got http://localhost/?y', resp.text)

    # too big response shouldn't be cached
    url = '/?z' + 'z' * 1001
    resp = app.get_response(url)
    resp = app.get_response(url)
    self.assertEqual(6, Handler.calls)

  def test_cache_response_headers(self):
    class Handler(webapp2.RequestHandler):
      # maps (Foo, Bar) header values tuple to # of calls
      calls = defaultdict(int)

      @handlers.cache_response(timedelta(days=1), headers=('Foo', 'Bar'))
      def get(self):
        Handler.calls[(self.request.headers.get('Foo'),
                       self.request.headers.get('Bar'))] += 1

    app = webapp2.WSGIApplication([('.*', Handler)])

    for i in range(2):
      app.get_response('/', headers={'Foo': 'x', 'Bar': 'y'})

    for i in range(2):
      app.get_response('/', headers={'Foo': 'z'})

    for i in range(2):
      app.get_response('/', headers={})

    app.get_response('/', headers={'Foo': 'z'})

    self.assertEqual({
      ('x', 'y'): 1,
      ('z', None): 1,
      (None, None): 1,
    }, Handler.calls)

  def test_throttle(self):
    class Handler(webapp2.RequestHandler):
      @handlers.throttle(one_request_each=timedelta(seconds=60))
      def get(self):
        self.response.set_status(204)

    app = webapp2.WSGIApplication([('.*', Handler)])

    # three different initial fetches, all should succeed
    urls = ('/a', '/a?x', '/a?y')
    for url in urls:
      self.assertEqual(204, app.get_response(url).status_int)

    # second time should fail
    for url in urls:
      self.assertEqual(429, app.get_response(url).status_int)

    # clear cache, should succeed again
    Handler.get.cache_clear()
    for url in urls:
      self.assertEqual(204, app.get_response(url).status_int)

  def test_modern_handler_options(self):
    app = webapp2.WSGIApplication([('.*', handlers.ModernHandler)])
    resp = app.get_response('/', method='OPTIONS')
    self.assertEqual(200, resp.status_int)
    self.assertEqual('*', resp.headers['Access-Control-Allow-Origin'])
    self.assertEqual('*', resp.headers['Access-Control-Allow-Methods'])
    self.assertEqual('*', resp.headers['Access-Control-Allow-Headers'])
