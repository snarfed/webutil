#!/usr/bin/python
"""Unit tests for handlers.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import mox
import testutil
import unittest
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


class BaseHandlerTest(testutil.HandlerTest):

  def test_get(self):
    class FakeHandler(handlers.BaseHandler):
      def get(self):
        raise urllib2.HTTPError('/', 408, 'foo bar', None, None)

    resp = webapp2.WSGIApplication([('/', FakeHandler)]).get_response('/')
    self.assertEquals(408, resp.status_int)
    self.assertEquals('HTTP Error 408: foo bar', resp.body)


class TemplateHandlerTest(testutil.HandlerTest):

  def test_get(self):
    self.mox.StubOutWithMock(template, 'render')
    template.render('my_template_file', {'host': None, 'foo': 'bar'})\
        .AndReturn('')
    self.mox.ReplayAll()

    webapp2.WSGIApplication([('/', FakeTemplateHandler)]).get_response('/')

  def test_force_to_sequence(self):
    class ForceFoo(FakeTemplateHandler):
      def force_to_sequence(self):
        return ['foo']

    self.mox.StubOutWithMock(template, 'render')
    template.render('my_template_file', {'host': None, 'foo': ('bar',)})\
        .AndReturn('')
    self.mox.ReplayAll()

    webapp2.WSGIApplication([('/', ForceFoo)]).get_response('/')
