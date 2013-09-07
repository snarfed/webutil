#!/usr/bin/python
"""Unit tests for handlers.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import mox
import testutil
import unittest
import webapp2

import handlers

# TODO: switch to django.template since this is deprecated
from google.appengine.ext.webapp import template


class FakeTemplateHandler(handlers.TemplateHandler):
  def template_file(self):
    return 'my_template_file'

  def template_vars(self):
    return {'foo': 'bar'}

  def content_type(self):
    return 'text/baz'


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
