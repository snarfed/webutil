#!/usr/bin/python
"""Unit tests for handlers.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import mox
import testutil
import unittest

import handlers

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
    mox.StubOutWithMock(template, 'render')
    template.render('my_template_file', {'host': 'xyz', 'foo': 'bar'})\
        .AndReturn('')
    self.mox.ReplayAll()

    FakeTemplateHandler().get()
