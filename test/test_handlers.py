"""Unit tests for handlers.py.
"""

import os
import socket
import traceback
import urllib2

import jinja2
import webapp2

import handlers
import testutil


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


class HandlersTest(testutil.HandlerTest):

  def test_handle_exception(self):
    class Handler(webapp2.RequestHandler):
      handle_exception = handlers.handle_exception
      err = None
      def get(self):
        raise self.err

    app = webapp2.WSGIApplication([('/', Handler)])

    # HTTP exception
    Handler.err = urllib2.HTTPError('/', 408, 'foo bar', None, None)
    resp = app.get_response('/')
    self.assertEquals(408, resp.status_int)
    self.assertEquals('HTTP Error 408: foo bar', resp.body)

    # network failure
    Handler.err = socket.error('foo bar')
    resp = app.get_response('/')
    self.assertEquals(502, resp.status_int)
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
        self.assertEquals(301, resp.status_int)
        self.assertEquals('%s://to.org%s' % (scheme, url), resp.headers['Location'])

    # should redirect and include *args
    for url in 'http://from.com', 'http://from.net':
      resp = app.get_response('/x/y', method='POST', base_url=url)
      self.assertEquals(301, resp.status_int)
      self.assertEquals('http://to.org/x/y', resp.headers['Location'])

    for base_url in 'http://abc.net', 'https://to.org':
      # shouldn't redirect
      resp = app.get_response('/', base_url=base_url)
      self.assertEquals(204, resp.status_int)
      self.assertNotIn('Location', resp.headers)

      # shouldn't redirect, should include *args
      resp = app.get_response('/x/y', method='POST', base_url='http://')
      self.assertEquals(205, resp.status_int)
      self.assertNotIn('Location', resp.headers)

  def test_template_handler_get(self):
    resp = webapp2.WSGIApplication([('/', FakeTemplateHandler)]).get_response('/')
    self.assertEquals("""\
my host: localhost
my foo: bar""", resp.body)

