#!/usr/bin/python
"""Unit tests for handlers.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import testutil
import urllib2
import webapp2

import handlers

from google.appengine.ext.webapp import template


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


  def test_template_handler_get(self):
    self.mox.StubOutWithMock(template, 'render')
    template.render('my_template_file', {'host': None, 'foo': 'bar'})\
        .AndReturn('')
    self.mox.ReplayAll()

    webapp2.WSGIApplication([('/', FakeTemplateHandler)]).get_response('/')

  def test_template_handler_force_to_sequence(self):
    class ForceFoo(FakeTemplateHandler):
      def force_to_sequence(self):
        return ['foo']

    self.mox.StubOutWithMock(template, 'render')
    template.render('my_template_file', {'host': None, 'foo': ('bar',)})\
        .AndReturn('')
    self.mox.ReplayAll()

    webapp2.WSGIApplication([('/', ForceFoo)]).get_response('/')
