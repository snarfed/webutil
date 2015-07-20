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
    class FakeHandler(webapp2.RequestHandler):
      handle_exception = handlers.handle_exception
      def get(self):
        raise urllib2.HTTPError('/', 408, 'foo bar', None, None)

    resp = webapp2.WSGIApplication([('/', FakeHandler)]).get_response('/')
    self.assertEquals(408, resp.status_int)
    self.assertEquals('HTTP Error 408: foo bar', resp.body)

  def test_redirect(self):
    class Handler(webapp2.RequestHandler):
      from_to = handlers.redirect('from.com', 'to.org')

      @from_to
      def get(self):
        self.response.set_status(204)

      @from_to
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
    resp = app.get_response('/x/y', method='POST', base_url='http://from.com')
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
