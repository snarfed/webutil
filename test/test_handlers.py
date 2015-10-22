"""Unit tests for handlers.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import urllib2

from google.appengine.ext.webapp import template
import webapp2

import handlers
import testutil


class FakeTemplateHandler(handlers.TemplateHandler):
  def template_file(self):
    return 'my_template_file'

  def template_vars(self):
    return {'foo': 'bar'}

  def content_type(self):
    return 'text/baz'


class HandlersTest(testutil.HandlerTest):

  def test_handle_exception(self):
    # HTTP exception
    class HttpException(webapp2.RequestHandler):
      handle_exception = handlers.handle_exception
      def get(self):
        raise urllib2.HTTPError('/', 408, 'foo bar', None, None)

    resp = webapp2.WSGIApplication([('/', HttpException)]).get_response('/')
    self.assertEquals(408, resp.status_int)
    self.assertEquals('HTTP Error 408: foo bar', resp.body)

    # other exception
    class Assertion(webapp2.RequestHandler):
      handle_exception = handlers.handle_exception
      def get(self):
        assert False

    resp = webapp2.WSGIApplication([('/', Assertion)]).get_response('/')
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
    self.mox.StubOutWithMock(template, 'render')
    template.render('my_template_file', {'host': 'localhost', 'foo': 'bar'})\
        .AndReturn('')
    self.mox.ReplayAll()

    webapp2.WSGIApplication([('/', FakeTemplateHandler)]).get_response('/')

  def test_template_handler_force_to_sequence(self):
    class ForceFoo(FakeTemplateHandler):
      def force_to_sequence(self):
        return ['foo']

    self.mox.StubOutWithMock(template, 'render')
    template.render('my_template_file', {'host': 'localhost', 'foo': ('bar',)})\
        .AndReturn('')
    self.mox.ReplayAll()

    webapp2.WSGIApplication([('/', ForceFoo)]).get_response('/')
