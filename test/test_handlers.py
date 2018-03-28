"""Unit tests for handlers.py.
"""
from future import standard_library
standard_library.install_aliases()
from future.moves.urllib import error as urllib_error

import datetime
import os
import socket
import traceback

from google.appengine.api import memcache
from google.appengine.ext.webapp import template
import webapp2

import handlers
from testutil_appengine import HandlerTest

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
    Handler.err = urllib_error.HTTPError('/', 408, 'foo bar', None, None)
    resp = app.get_response('/')
    self.assertEquals(408, resp.status_int)
    self.assertEquals('HTTP Error 408: foo bar', resp.body)

    # network failure
    Handler.err = socket.timeout('foo bar')
    resp = app.get_response('/')
    self.assertEquals(504, resp.status_int)
    self.assertEquals('Upstream server request failed: foo bar', resp.body)

    # other exception
    Handler.err = AssertionError('foo')
    resp = app.get_response('/')
    self.assertEquals(500, resp.status_int)

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
        self.assertEqual('%s://to.org%s' % (scheme, url), resp.headers['Location'])

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

  def test_template_handler_get_jinja(self):
    resp = webapp2.WSGIApplication([('/', FakeTemplateHandler)]).get_response('/')
    self.assertEquals("""\
my host: localhost
my foo: bar""", resp.body)

  def test_template_handler_get_appengine_webapp(self):
    class WebappTemplateHandler(FakeTemplateHandler):
      USE_APPENGINE_WEBAPP = True

    self.mox.StubOutWithMock(template, 'render')
    filename = WebappTemplateHandler(self.request, self.response).template_file()
    template.render(filename, {
      'host': 'localhost',
      'host_uri': 'http://localhost',
      'foo': 'bar',
    }).AndReturn('')
    self.mox.ReplayAll()
    webapp2.WSGIApplication([('/', WebappTemplateHandler)]).get_response('/')

  def test_memcache_response(self):
    class Handler(webapp2.RequestHandler):
      calls = 0

      @handlers.memcache_response(datetime.timedelta(days=1))
      def get(self):
        Handler.calls += 1
        self.response.set_status(204)
        self.response.out.write('got %s' % self.request.url)

    app = webapp2.WSGIApplication([('.*', Handler)])

    # first fetch populates the cache
    resp = app.get_response('/?x')
    self.assertEquals(1, Handler.calls)
    self.assertEquals(204, resp.status_int)
    self.assertEquals('got http://localhost/?x', resp.body)

    # second fetch should use the cache instead of fetching from the silo
    resp = app.get_response('/?x')
    self.assertEquals(1, Handler.calls)
    self.assertEquals(204, resp.status_int)
    self.assertEquals('got http://localhost/?x', resp.body)

    # fetches with ?cache=false shouldn't use the cache
    resp = app.get_response('/?x&cache=false')
    resp = app.get_response('/?x&cache=false')
    self.assertEquals(3, Handler.calls)
    self.assertEquals(204, resp.status_int)
    self.assertEquals('got http://localhost/?x&cache=false', resp.body)

    # a different URL shouldn't be cached
    resp = app.get_response('/?y')
    self.assertEquals(4, Handler.calls)
    self.assertEquals(204, resp.status_int)
    self.assertEquals('got http://localhost/?y', resp.body)

  def test_memcache_response_too_big(self):
    self.mox.stubs.Set(memcache, 'MAX_VALUE_SIZE', 100)

    class Handler(webapp2.RequestHandler):
      @handlers.memcache_response(datetime.timedelta(days=1))
      def get(self):
        self.response.out.write('x' * 101)

    app = webapp2.WSGIApplication([('.*', Handler)])
    resp = app.get_response('/?x')
    self.assertEquals(200, resp.status_int)
    self.assertIsNone(memcache.get('memcache_response http://localhost/?x'))
