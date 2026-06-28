# -*- coding: utf-8 -*-
"""Unit tests for webmention.py."""
from unittest.mock import patch

import requests

from .. import testutil, util
from ..testutil import requests_response
from ..webmention import discover, send


class DiscoverTest(testutil.BaseTestCase):

  def _test(self, expected, html, status_code=200, response_headers=None):
    resp = requests_response(
        f'<html>{html}</html>', url='http://foo', status=status_code,
        headers=response_headers)

    with patch.object(util.session, 'get', return_value=resp):
      got = discover('http://foo')

    self.assertEqual(expected, got.endpoint)
    self.assertEqual(resp, got.response)

  def test_bad_url(self):
    for bad in (None, 123, '', 'asdf'):
      with self.assertRaises(ValueError):
        discover(bad)

  def test_no_endpoint(self):
    self._test(None, '')

  def test_html_link(self):
    self._test('http://endpoint', '<link rel="webmention" href="http://endpoint">')

  def test_html_a(self):
    self._test('http://endpoint', '<a rel="webmention" href="http://endpoint">')

  def test_html_refresh(self):
    resp2 = requests_response(
      '<html><link rel="webmention" href="http://endpoint"></html>', url='http://foo')
    with patch.object(util.session, 'get', side_effect=[
      requests_response(
        """<html><meta http-equiv="refresh" content="0;URL='http://foo'"></html>""",
        url='http://will/redirect'),
      resp2,
    ]):
      got = discover('http://will/redirect', follow_meta_refresh=True)

    self.assertEqual('http://endpoint', got.endpoint)
    self.assertEqual(resp2, got.response)

  def test_html_relative(self):
    self._test('http://foo/bar', '<link rel="webmention" href="/bar">')

  def test_html_rel_url(self):
    self._test('http://foo/bar', '<link rel="http://webmention.org/" href="/bar">')

  def test_html_link_and_a(self):
    self._test('http://endpoint1', """\
<a rel="webmention" href="http://endpoint1">
<link rel="webmention" href="http://endpoint2">
""")

  def test_html_link_a_and_refresh(self):
    self._test('http://endpoint1', """\
<meta http-equiv="refresh" content="0;URL=\'http://refresh\'">
<a rel="webmention" href="http://endpoint1">
<link rel="webmention" href="http://endpoint2">
""")

  def test_html_other_links(self):
    self._test('http://endpoint', """\
<link rel="foo" href="http://bar">
<link rel="webmention" href="http://endpoint">
""")

  def test_html_empty(self):
    self._test(None, '<link rel="webmention/" href="">')

  def test_html_unicode(self):
    self._test('http://☕/☕?☕=☕', '<link rel="webmention" href="http://☕/☕?☕=☕">')

  def test_html_escaped(self):
    self._test('http://%E2%98%95/%E2%98%95?%E2%98%95=%E2%98%95',
      '<link rel="webmention" href="http://%E2%98%95/%E2%98%95?%E2%98%95=%E2%98%95">')

  def test_html_content_type_html(self):
    self._test('http://foo/bar', '<link rel="http://webmention.org/" href="/bar">',
               response_headers={'Content-Type': 'text/html'})

  def test_html_content_type_html_charset(self):
    self._test('http://foo/bar', '<link rel="http://webmention.org/" href="/bar">',
               response_headers={'Content-Type': 'text/html; charset=utf-8'})

  def test_html_content_type_other(self):
    self._test(None, '<link rel="http://webmention.org/" href="/bar">',
               response_headers={'Content-Type': 'text/json'})

  def test_header(self):
    self._test('http://endpoint', '', response_headers={
      'Link': '<http://endpoint>; rel=webmention',
    })

  def test_header_relative(self):
    self._test('http://foo/bar', '', response_headers={
      'Link': '</bar>; rel="webmention"',
    })

  def test_header_quoted(self):
    self._test('http://endpoint', '', response_headers={
      'Link': '<http://endpoint>; rel="webmention"',
    })

  def test_header_rel_url(self):
    self._test('http://endpoint', '', response_headers={
      'Link': '<http://endpoint>; rel="https://webmention.org/"',
    })

  def test_other_headers(self):
    self._test('http://endpoint', '', response_headers={
      'Link': '<http://foo>; rel="bar", <http://endpoint>; rel="webmention"',
    })

  def test_multiple_link_headers(self):
    self._test('http://1', '', response_headers={
      'Link': '<http://1>; rel="webmention", <http://2>; rel="webmention"',
    })

  def test_header_empty(self):
    self._test(None, '', response_headers={
      'Link': '<http://endpoint>; rel=""',
    })

  def test_header_query_params(self):
    self._test('http://endpoint?x=y&a=b', '', response_headers={
      'Link': '<http://endpoint?x=y&a=b>; rel="webmention"',
    })

  def test_header_fragment(self):
    self._test('http://endpoint', '', response_headers={
      'Link': '<http://endpoint#foo>; rel="webmention"',
    })

  def test_header_unicode(self):
    self._test('http://☕/☕?☕=☕', '', response_headers={
      'Link': '<http://☕/☕?☕=☕>; rel="webmention"',
    })

  def test_header_escaped(self):
    self._test('http://%E2%98%95/%E2%98%95?%E2%98%95=%E2%98%95', '',
               response_headers={
      'Link': '<http://%E2%98%95/%E2%98%95?%E2%98%95=%E2%98%95>; rel="webmention"',
    })

  def test_http_500(self):
    self._test('http://endpoint', '', status_code=500, response_headers={
      'Link': '<http://endpoint>; rel=webmention',
    })

  @patch.object(util.session, 'get', side_effect=requests.ConnectionError('foo'))
  def test_connection_error(self, _):
    with self.assertRaises(requests.ConnectionError):
      discover('http://foo')


class SendTest(testutil.BaseTestCase):

  def _test(self, endpoint='http://endpoint', source='http://source',
            target='http://target', status_code=200):
    resp = requests_response('', url=endpoint, status=status_code)
    with patch.object(util.session, 'post', return_value=resp):
      got = send(endpoint, source, target)
    self.assertEqual(resp, got)

  def test_bad_url(self):
    for bad in (None, 123, '', 'asdf'):
      with self.assertRaises(ValueError):
        send(bad, 'http://x', 'http://x')
      with self.assertRaises(ValueError):
        send('http://x', bad, 'http://x')
      with self.assertRaises(ValueError):
        send('http://x', 'http://x', bad)

  def test_success(self):
    self._test()

  def test_requests_exception(self):
    with self.assertRaises(requests.HTTPError):
      self._test(status_code=500)

  def test_preserve_endpoint_query_params(self):
    self._test('http://endpoint?x=y&a=b')

  def test_unicode_urls(self):
    self._test('http://☕/☕?☕=☕', 'http://❤/❤?❤=❤', 'http://⚠/⚠?⚠=⚠')

  def test_unicode_urls_escaped(self):
    self._test('http://%E2%98%95/%E2%98%95?%E2%98%95=%E2%98%95',
               'http://%E2%9A%A0/%E2%9A%A0?%E2%9A%A0=%E2%9A%A0',
               'http://%E2%9D%A4/%E2%9D%A4?%E2%9D%A4=%E2%9D%A4')
