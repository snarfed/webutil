"""Unit test utilities.

Supports Python 3. Should not depend on App Engine API or SDK packages.
"""
from __future__ import absolute_import, division, unicode_literals
from future import standard_library
from future.moves.urllib import error as urllib_error
from future.utils import native_str
standard_library.install_aliases()
from builtins import object, str, zip
from past.builtins import basestring

import base64
import datetime
import difflib
import json
from mox3 import mox
import pprint
import re
import os
import email
import io
import traceback
import urllib.parse, urllib.request

try:
  from appengine_config import HTTP_TIMEOUT
except (ImportError, ValueError):
  HTTP_TIMEOUT = 15

from oauth_dropins.webutil import util
import requests


def get_task_params(task):
  """Parses a task's POST body and returns the query params in a dict.
  """
  params = urllib.parse.parse_qs(base64.b64decode(task['body']))
  params = dict((key, val[0]) for key, val in list(params.items()))
  return params


def get_task_eta(task):
  """Returns a task's ETA as a datetime."""
  return datetime.datetime.fromtimestamp(
    float(dict(task['headers'])['X-AppEngine-TaskETA']))


def requests_response(body='', url=None, status=200, content_type=None,
                      redirected_url=None, headers=None, allow_redirects=None):
    """
    Args:
      redirected_url: string URL or sequence of string URLs for multiple redirects
    """
    resp = requests.Response()

    if isinstance(body, (dict, list)):
      body = json.dumps(body, indent=2)
      if content_type is None:
        content_type = 'application/json'

    resp._text = body
    resp._content = body.encode('utf-8') if isinstance(body, str) else body
    resp.encoding = 'utf-8'

    resp.url = url
    if redirected_url is not None:
      if allow_redirects is False:
        resp.headers['location'] = redirected_url
      else:
        if isinstance(redirected_url, basestring):
          redirected_url = [redirected_url]
        assert isinstance(redirected_url, (list, tuple))
        resp.url = redirected_url[-1]
        for u in [url] + redirected_url[:-1]:
          resp.history.append(requests.Response())
          resp.history[-1].url = u

    resp.status_code = status
    if content_type is None:
      content_type = 'text/html'
    resp.headers['content-type'] = content_type
    if headers is not None:
      resp.headers.update(headers)

    return resp


class UrlopenResult(object):
  """A fake :func:`urllib.request.urlopen()` or :func:`urlfetch.fetch()` result object.
  """
  def __init__(self, status_code, content, url=None, headers={}):
    self.status_code = status_code
    self.content = io.StringIO(str(content))
    self.url = url
    self.headers = headers

  def read(self, length=-1):
    return self.content.read(length)

  def getcode(self):
    return self.status_code

  def geturl(self):
    return self.url

  def info(self):
    return email.message_from_string(
        '\n'.join('%s: %s' % item for item in self.headers.items()))


class Asserts(object):
  """Test case mixin class with extra assert helpers."""

  def assert_entities_equal(self, a, b, ignore=frozenset(), keys_only=False,
                            in_order=False):
    """Asserts that a and b are equivalent entities or lists of entities.

    ...specifically, that they have the same property values, and if they both
    have populated keys, that their keys are equal too.

    Args:
      a: :class:`ndb.Model` instances or lists of instances
      b: same
      ignore: sequence of strings, property names not to compare
      keys_only: boolean, if True only compare keys
      in_order: boolean. If False, all entities must have keys.
    """
    # all the __class__.__name__ hacks below are so we avoid importing ndb
    # from the app engine SDK, since this file needs to support Python 3.
    if not (isinstance(a, (list, tuple) or a.__class__.__name__ == 'Query')):
      a = [a]
    if not (isinstance(b, (list, tuple) or b.__class__.__name__ == 'Query')):
      b = [b]

    if not in_order:
      a = list(sorted(a, key=lambda e: e.key))
      b = list(sorted(b, key=lambda e: e.key))

    self.assertEqual(len(a), len(b),
                     'Different lengths:\n expected %s\n actual %s' % (a, b))

    for x, y in zip(a, b):
      try:
        self.assertEqual(x.key.flat(), y.key.flat())
      except Exception as err:
        if err.__class__.__name__ in ('BadKeyError', 'NotSavedError'):
          if keys_only:
            raise
        else:
          raise

      def props(e):
        all = e.to_dict()
        return {k: v for k, v in list(all.items()) if k not in ignore}

      if not keys_only:
        self.assert_equals(props(x), props(y), x.key.flat())

  def entity_keys(self, entities):
    """Returns a list of keys for a list of entities.
    """
    return [e.key() for e in entities]

  def assert_equals(self, expected, actual, msg=None, in_order=False):
    """Pinpoints individual element differences in lists and dicts.

    If in_order is False, ignores order in lists and tuples.
    """
    try:
      self._assert_equals(expected, actual, in_order=in_order)
    except AssertionError as e:
      if not isinstance(expected, str):
        expected = pprint.pformat(expected)
      if not isinstance(actual, str):
        actual = pprint.pformat(actual)
      raise AssertionError("""\
%s: %s
Expected value:
%s
Actual value:
%s""" % (msg, ''.join(e.args), expected, actual))

  def _assert_equals(self, expected, actual, in_order=False):
    """Recursive helper for assert_equals().
    """
    key = None

    try:
      if isinstance(expected, re._pattern_type):
        if not re.match(expected, actual):
          self.fail("%r doesn't match %s" % (expected, actual))
      elif isinstance(expected, dict) and isinstance(actual, dict):
        for key in set(expected.keys()) | set(actual.keys()):
          self._assert_equals(expected.get(key), actual.get(key), in_order=in_order)
      elif (isinstance(expected, (list, tuple, set)) and
            isinstance(actual, (list, tuple, set))):
        if not in_order:
          # use custom key because Python 3 dicts are not comparable :/
          def hash_or_json(x):
            try:
              return native_str(hash(x))
            except TypeError:
              return json.dumps(x, sort_keys=True)
          expected = sorted(expected, key=hash_or_json)
          actual = sorted(actual, key=hash_or_json)

        self.assertEqual(len(expected), len(actual),
                         'Different lengths:\n expected %s\n actual %s' %
                         (len(expected), len(actual)))
        for key, (e, a) in enumerate(zip(expected, actual)):
          self._assert_equals(e, a, in_order=in_order)
      elif (isinstance(expected, str) and isinstance(actual, str) and
            '\n' in expected):
        self.assert_multiline_equals(expected, actual)
      else:
        self.assertEqual(expected, actual)

    except AssertionError as e:
      # fill in where this failure came from. this recursively builds,
      # backwards, all the way up to the root.
      args = ('[%s] ' % key if key is not None else '') + ''.join(e.args)
      raise AssertionError(args)

  def assert_multiline_equals(self, expected, actual, ignore_blanks=False):
    """Compares two multi-line strings and reports a diff style output.

    Ignores leading and trailing whitespace on each line, and squeezes repeated
    blank lines down to just one.

    Args:
      ignore_blanks: boolean, whether to ignore blank lines altogether
    """
    exp = self._normalize_lines(expected, ignore_blanks=ignore_blanks)
    act = self._normalize_lines(actual, ignore_blanks=ignore_blanks)
    if exp != act:
      self.fail(''.join(difflib.Differ().compare(exp, act)))

  def assert_multiline_in(self, expected, actual, ignore_blanks=False):
    """Checks that a multi-line string is in another and reports a diff output.

    Ignores leading and trailing whitespace on each line, and squeezes repeated
    blank lines down to just one.

    Args:
      ignore_blanks: boolean, whether to ignore blank lines altogether
    """
    exp = ''.join(self._normalize_lines(expected, ignore_blanks=ignore_blanks)).strip()
    act = ''.join(self._normalize_lines(actual, ignore_blanks=ignore_blanks))
    self.assertIn(exp, act, """\
%s

not found in:

%s""" % (exp, act))

  @staticmethod
  def _normalize_lines(val, ignore_blanks=False):
      lines = [l.strip() + '\n' for l in val.splitlines(True)]
      return [l for i, l in enumerate(lines)
              if not (ignore_blanks and l == '\n') and
                 (i <= 1 or not (lines[i - 1] == l == '\n'))]


class TestCase(mox.MoxTestBase, Asserts):
  """Test case class with lots of extra helpers."""
  maxDiff = None

  def setUp(self):
    super(TestCase, self).setUp()
    for method in 'get', 'post':
      self.mox.StubOutWithMock(requests, method, use_mock_anything=True)
    self.stub_requests_head()

    self.mox.StubOutWithMock(util, 'urllib_urlopen')

    # set time zone to UTC so that tests don't depend on local time zone
    os.environ['TZ'] = 'UTC'

  def stub_requests_head(self):
    """Automatically return 200 to outgoing HEAD requests."""
    def fake_head(url, **kwargs):
      resp = requests.Response()
      resp.url = url
      if '.' in url or url.startswith('http'):
        resp.headers['content-type'] = 'text/html; charset=UTF-8'
        resp.status_code = 200
      else:
        resp.status_code = 404
      return resp
    self.mox.stubs.Set(requests, 'head', fake_head)

    self._is_head_mocked = False  # expect_requests_head() sets this to True

  def unstub_requests_head(self):
    """Mock outgoing HEAD requests so they must be expected individually."""
    if not self._is_head_mocked:
      self.mox.StubOutWithMock(requests, 'head', use_mock_anything=True)
      self._is_head_mocked = True

  def expect_requests_head(self, *args, **kwargs):
    self.unstub_requests_head()
    return self._expect_requests_call(*args, method=requests.head, **kwargs)

  def expect_requests_get(self, *args, **kwargs):
    return self._expect_requests_call(*args, method=requests.get, **kwargs)

  def expect_requests_post(self, *args, **kwargs):
    return self._expect_requests_call(*args, method=requests.post, **kwargs)

  def _expect_requests_call(self, url, response='', status_code=200,
                            content_type='text/html', method=requests.get,
                            redirected_url=None, response_headers=None,
                            **kwargs):
    """
    Args:
      redirected_url: string URL or sequence of string URLs for multiple redirects
    """
    resp = requests_response(
      response, url=url, status=status_code, content_type=content_type,
      redirected_url=redirected_url, headers=response_headers,
      allow_redirects=kwargs.get('allow_redirects'))

    if 'timeout' not in kwargs:
      kwargs['timeout'] = HTTP_TIMEOUT
    elif kwargs['timeout'] is None:
      del kwargs['timeout']

    if method is requests.head:
      kwargs['allow_redirects'] = True

    headers = kwargs.get('headers')
    if headers and not isinstance(headers, mox.Comparator):
      def check_headers(actual):
        missing = set(headers.items()) - set(actual.items())
        assert not missing, 'Missing request headers: %s\n(Got %s, %s)' % (
          missing, set(actual.items()), set(headers.items()))
        return True
      kwargs['headers'] = mox.Func(check_headers)


    files = kwargs.get('files')
    if files:
      def check_files(actual):
        self.assertEqual(list(actual.keys()), list(files.keys()))
        for name, expected in files.items():
          self.assertEqual(expected, actual[name].read())
        return True
      kwargs['files'] = mox.Func(check_files)

    call = method(url, **kwargs)
    call.AndReturn(resp)
    return call

  def expect_urlopen(self, url, response=None, status=200, data=None,
                     headers=None, response_headers={}, **kwargs):
    """Stubs out :func:`urllib.request.urlopen()` and sets up an expected call.

    If status isn't 2xx, makes the expected call raise a
    :class:`urllib.error.HTTPError` instead of returning the response.

    If data is set, url *must* be a :class:`urllib.request.Request`.

    If response is unset, returns the expected call.

    Args:
      url: string, :class:`re.RegexObject` or :class:`urllib.request.Request` or
        :class:`webob.request.Request`
      response: string
      status: int, HTTP response code
      data: optional string POST body
      headers: optional expected request header dict
      response_headers: optional response header dict
      kwargs: other keyword args, e.g. timeout
    """
    def check_request(req):
      try:
        req_url = req if isinstance(req, basestring) else req.get_full_url()
        if isinstance(url, re._pattern_type):
          self.assertRegexpMatches(req_url, url)
        else:
          self.assertEqual(url, req_url)

        if isinstance(req, basestring):
          assert not data, data
          assert not headers, headers
        else:
          self.assertEqual(data, req.data)
          if isinstance(headers, mox.Comparator):
            self.assertTrue(headers.equals(req.header_items()))
          elif headers is not None:
            missing = set(headers.items()) - set(req.header_items())
            assert not missing, 'Missing request headers: %s' % missing

      except AssertionError:
        traceback.print_exc()
        return False

      return True

    if 'timeout' not in kwargs:
      kwargs['timeout'] = HTTP_TIMEOUT

    call = util.urllib_urlopen(mox.Func(check_request), **kwargs)
    if status // 100 != 2:
      if response:
        response = urllib.request.addinfourl(io.StringIO(str(response)),
                                             response_headers, url, status)
      call.AndRaise(urllib_error.HTTPError('url', status, 'message',
                                           response_headers, response))
    elif response is not None:
      call.AndReturn(UrlopenResult(status, response, url=url,
                                   headers=response_headers))

    return call
