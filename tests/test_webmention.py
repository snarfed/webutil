# -*- coding: utf-8 -*-
"""Unit tests for webmention.py."""
from urllib.error import HTTPError, URLError
import urllib.parse, urllib.request

import requests
import urllib3

from .. import testutil, util
from ..webmention import discover, send

class WebmentionTest(testutil.TestCase):

  def _test_discover(self, expected, html, **kwargs):
    call = self.expect_requests_get('http://foo', f'<html>{html}</html>', **kwargs)
    self.mox.ReplayAll()

    got = discover('http://foo')
    self.assertEqual(expected, got.endpoint)
    self.assertEqual(call._return_value, got.response)

  def test_discover_no_endpoint(self):
      self._test_discover(None, '')

  def test_discover_html_link(self):
      self._test_discover(
        'http://endpoint', '<link rel="webmention" href="http://endpoint">')

  def test_discover_html_a(self):
      self._test_discover(
        'http://endpoint', '<a rel="webmention" href="http://endpoint">')

  def test_discover_html_relative(self):
      self._test_discover('http://foo/bar', '<link rel="webmention" href="/bar">')

  def test_discover_html_rel_url(self):
      self._test_discover(
        'http://foo/bar', '<link rel="http://webmention.org/" href="/bar">')

  def test_discover_html_link_and_a(self):
      self._test_discover(
        'http://endpoint1', """\
<a rel="webmention" href="http://endpoint1">
<link rel="webmention" href="http://endpoint2">
""")

  def test_discover_html_other_links(self):
      self._test_discover(
        'http://endpoint', """\
<link rel="foo" href="http://bar">
<link rel="webmention" href="http://endpoint">
""")

  def test_discover_html_empty(self):
      self._test_discover(None, '<link rel="webmention/" href="">')

  def test_discover_header(self):
      self._test_discover('http://endpoint', '', response_headers={
        'Link': '<http://endpoint>; rel=webmention',
      })

  def test_discover_header_relative(self):
      self._test_discover('http://foo/bar', '', response_headers={
        'Link': '</bar>; rel="webmention"',
      })

  def test_discover_header_quoted(self):
      self._test_discover('http://endpoint', '', response_headers={
        'Link': '<http://endpoint>; rel="webmention"',
      })

  def test_discover_header_rel_url(self):
      self._test_discover('http://endpoint', '', response_headers={
        'Link': '<http://endpoint>; rel="https://webmention.org/"',
      })

  def test_discover_other_headers(self):
      self._test_discover('http://endpoint', '', response_headers={
        'Link': '<http://foo>; rel="bar", <http://endpoint>; rel="webmention"',
      })

  def test_discover_multiple_link_headers(self):
      self._test_discover('http://1', '', response_headers={
        'Link': '<http://1>; rel="webmention", <http://2>; rel="webmention"',
      })

  def test_discover_header_empty(self):
      self._test_discover(None, '', response_headers={
        'Link': '<http://endpoint>; rel=""',
      })

  # def test_link_header_rel_webmention_unquoted(self):
  #   """We should support rel=webmention (no quotes) in the Link header."""
  #   self.mox.UnsetStubs()  # drop WebmentionSend mock; let it run
  #   super(PropagateTest, self).setUp()

  #   self.responses[0].unsent = ['http://my/post']
  #   self.responses[0].put()
  #   self.expect_requests_head('http://my/post')
  #   self.expect_webmention_requests_get(
  #     'http://my/post', timeout=999,
  #     response_headers={'Link': '<http://my/endpoint>; rel=webmention'})

  #   source_url = ('http://localhost/comment/fake/%s/a/1_2_a' %
  #                 self.sources[0].key.string_id())
  #   self.expect_requests_post(
  #     'http://my/endpoint', timeout=999,
  #     data={'source': source_url, 'target': 'http://my/post'},
  #     stream=None, allow_redirects=False, headers={'Accept': '*/*'})

  #   self.mox.ReplayAll()
  #   self.post_task()
  #   self.assert_response_is('complete', sent=['http://my/post'])

  # def test_discover_error(self):
  #   self.expect_webmention(error={'code': 'NO_ENDPOINT'}).AndReturn(False)
  #   # second time shouldn't try to send a webmention

  #   self.mox.ReplayAll()
  #   self.post_task()
  #   self.assert_response_is('complete', skipped=['http://target1/post/url'])

  #   self.responses[0].status = 'new'
  #   self.responses[0].put()
  #   self.post_task()
  #   self.assert_response_is('complete', skipped=['http://target1/post/url'])

  # def test_non_html_file(self):
  #   """If our HEAD fails, we should still require content-type text/html."""
  #   self.mox.UnsetStubs()  # drop WebmentionSend mock; let it run
  #   super(PropagateTest, self).setUp()

  #   self.responses[0].unsent = ['http://not/html']
  #   self.responses[0].put()
  #   self.expect_requests_head('http://not/html', status_code=405)
  #   self.expect_webmention_requests_get(
  #     'http://not/html', content_type='image/gif', timeout=999)

  #   self.mox.ReplayAll()
  #   self.post_task()
  #   self.assert_response_is('complete', skipped=['http://not/html'])

  # def test_non_html_file_extension(self):
  #   """If our HEAD fails, we should infer type from file extension."""
  #   self.responses[0].unsent = ['http://this/is/a.pdf']
  #   self.responses[0].put()

  #   self.expect_requests_head('http://this/is/a.pdf', status_code=405,
  #                             # we should ignore an error response's content type
  #                             content_type='text/html')

  #   self.mox.ReplayAll()
  #   self.post_task()
  #   self.assert_response_is('complete')

  # def test_content_type_html_with_charset(self):
  #   """We should handle Content-Type: text/html; charset=... ok."""
  #   self.mox.UnsetStubs()  # drop WebmentionSend mock; let it run
  #   super(PropagateTest, self).setUp()

  #   self.responses[0].unsent = ['http://html/charset']
  #   self.responses[0].put()
  #   self.expect_requests_head('http://html/charset', status_code=405)
  #   self.expect_webmention_requests_get(
  #     'http://html/charset',
  #     content_type='text/html; charset=utf-8',
  #     response_headers={'Link': '<http://my/endpoint>; rel="webmention"'},
  #     timeout=999)

  #   source_url = ('http://localhost/comment/fake/%s/a/1_2_a' %
  #                 self.sources[0].key.string_id())
  #   self.expect_requests_post(
  #     'http://my/endpoint',
  #     data={'source': source_url, 'target': 'http://html/charset'},
  #     stream=None, timeout=999, allow_redirects=False, headers={'Accept': '*/*'})

  #   self.mox.ReplayAll()
  #   self.post_task()
  #   self.assert_response_is('complete', sent=['http://html/charset'])

  # def test_no_content_type_header(self):
  #   """If the Content-Type header is missing, we should assume text/html."""
  #   self.mox.UnsetStubs()  # drop WebmentionSend mock; let it run
  #   super(PropagateTest, self).setUp()

  #   self.responses[0].unsent = ['http://unknown/type']
  #   self.responses[0].put()
  #   self.expect_requests_head('http://unknown/type', status_code=405)
  #   self.expect_webmention_requests_get('http://unknown/type', content_type=None,
  #                                       timeout=999)

  #   self.mox.ReplayAll()
  #   self.post_task()
  #   self.assert_response_is('complete', skipped=['http://unknown/type'])

  # def test_webmention_post_omits_accept_header(self):
  #   """The webmention POST request should never send the Accept header."""
  #   self.mox.UnsetStubs()  # drop WebmentionSend mock; let it run
  #   super(PropagateTest, self).setUp()

  #   self.responses[0].source = Twitter(id='rhiaro').put()
  #   self.responses[0].put()
  #   # self.expect_requests_head('http://my/post')
  #   self.expect_webmention_requests_get(
  #     'http://target1/post/url', timeout=999,
  #     headers=util.REQUEST_HEADERS_CONNEG,
  #     response_headers={'Link': '<http://my/endpoint>; rel=webmention'})

  #   self.expect_requests_post(
  #     'http://my/endpoint', timeout=999,
  #     data={'source': 'http://localhost/comment/twitter/rhiaro/a/1_2_a',
  #           'target': 'http://target1/post/url'},
  #     stream=None, allow_redirects=False, headers={'Accept': '*/*'})

  #   self.mox.ReplayAll()
  #   self.post_task()
  #   self.assert_response_is('complete', sent=['http://target1/post/url'])

  # def test_unicode_in_target_url(self):
  #   """Target URLs with escaped unicode chars should work ok."""
  #   url = 'https://maps/?q=' + urllib.parse.quote_plus('3 Cours de la République'.encode())
  #   self.responses[0].unsent = [url]
  #   self.responses[0].put()

  #   self.expect_webmention(target=url).AndReturn(True)
  #   self.mox.ReplayAll()

  #   self.post_task()
  #   self.assert_response_is('complete', sent=[url])

  # def test_dns_failure(self):
  #   """If DNS lookup fails for a URL, we should give up."""
  #   self.responses[0].put()
  #   self.expect_webmention().AndRaise(requests.exceptions.ConnectionError(
  #       'Max retries exceeded: DNS lookup failed for URL: foo'))
  #   self.mox.ReplayAll()

  #   self.post_task()
  #   self.assert_response_is('complete', failed=['http://target1/post/url'])

  def test_send_preserve_endpoint_query_params(self):
    pass
