#!/usr/bin/python
"""Unit tests for handler_util.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import datetime
from webob import exc

import testutil
import handler_util


class HandlerUtilTest(testutil.HandlerTest):

  def test_urlread(self):
    self.expect_urlopen('http://my/url', 'hello')
    self.mox.ReplayAll()
    self.assertEquals('hello', handler_util.urlread('http://my/url'))

  def test_urlread_error_passes_through(self):
    self.expect_urlopen('http://my/url', 'my error', status=408)
    self.mox.ReplayAll()

    try:
      handler_util.urlread('http://my/url')
    except exc.HTTPException, e:
      self.assertEquals(408, e.status_int)
      self.assertEquals('my error', e.body_template_obj.template)

  def test_domain_from_link(self):
    self.assertEqual('asdf.com', handler_util.domain_from_link('https://asdf.com/'))
    for bad_link in '', '  ', 'a&b.com', 'http://', 'file:///':
      self.assertRaises(exc.HTTPBadRequest, handler_util.domain_from_link, bad_link)
