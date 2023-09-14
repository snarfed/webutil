"""Unit test utilities."""
from datetime import datetime, timezone
import difflib
import email
import io
import os
import pprint
import re
import traceback
import urllib.error, urllib.parse, urllib.request
import warnings

from bs4 import (
    GuessedAtParserWarning,
    MarkupResemblesLocatorWarning,
    XMLParsedAsHTMLWarning,
)
from mox3 import mox
import requests

from . import appengine_info
from . import util
from .util import json_dumps, json_loads, HTTP_TIMEOUT

RE_TYPE = (re.Pattern if hasattr(re, 'Pattern')  # python >=3.7
           else re._pattern_type)                # python <3.7

NOW = datetime(2022, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

# don't truncate assertion error diffs
import unittest.util
unittest.util._MAX_LENGTH = 999999


def requests_response(body='', url=None, status=200, content_type=None,
                      redirected_url=None, headers=None, allow_redirects=None,
                      encoding=None):
    """
    Args:
      redirected_url: string URL or sequence of string URLs for multiple redirects
    """
    resp = requests.Response()

    if isinstance(body, (dict, list)):
      body = json_dumps(body, indent=2)
      if content_type is None:
        content_type = 'application/json'

    resp._text = body
    resp._content = body.encode('utf-8') if isinstance(body, str) else body
    resp.raw = io.BytesIO(resp._content)  # needed for close()
    resp.encoding = encoding if encoding is not None else 'utf-8'

    resp.url = url
    if redirected_url is not None:
      if allow_redirects is False:
        resp.headers['location'] = redirected_url
      else:
        if isinstance(redirected_url, str):
          redirected_url = [redirected_url]
        assert isinstance(redirected_url, (list, tuple))
        resp.url = redirected_url[-1]
        for u in [url] + redirected_url[:-1]:
          resp.history.append(requests.Response())
          resp.history[-1].url = u

    resp.status_code = status
    if content_type is None:
      content_type = 'text/html'
    elif content_type == 'None':
      content_type = None
    resp.headers['content-type'] = content_type
    if headers is not None:
      resp.headers.update(headers)

    return resp


def enable_flask_caching(app, cache):
  """Test case decorator that enables a flask_caching cache.

  Usage:

    from app import app, cache

    class FooTest(TestCase):
      @enable_flask_caching(app, cache)
      def test_foo(self):
        ..

  Args:
    app: :class:`flask.Flask` app
    cache: :class:`flask_caching.Cache`
  """
  def decorator(method):
    def wrapper(self, *args, **kwargs):
      orig_cache_type = app.config.get('CACHE_TYPE')
      try:
        app.config['CACHE_TYPE'] = 'SimpleCache'
        cache.init_app(app)
        method(self, *args, **kwargs)
      finally:
        app.config['CACHE_TYPE'] = orig_cache_type
        cache.init_app(app)

    return wrapper

  return decorator


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
        '\n'.join(f'{key}: {val}' for key, val in self.headers.items()))


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
                     f'Different lengths:\n expected {a}\n actual {b}')

    for x, y in zip(a, b):
      x_key = None
      try:
        x_key = x.key.flat()
        self.assertEqual(x_key, y.key.flat())
      except Exception as err:
        if err.__class__.__name__ in ('BadKeyError', 'NotSavedError',
                                      'AttributeError'):
          if keys_only:
            raise
        else:
          raise

      def props(e):
        all = e.to_dict()
        return {k: v for k, v in list(all.items()) if k not in ignore}

      if not keys_only:
        self.assert_equals(props(x), props(y), x_key)

  def entity_keys(self, entities):
    """Returns a list of keys for a list of entities.
    """
    return [e.key() for e in entities]

  def assert_equals(self, expected, actual, msg=None, in_order=False, ignore=()):
    """Pinpoints individual element differences in lists and dicts.

    If in_order is False, ignores order in lists and tuples.
    """
    try:
      self._assert_equals(expected, actual, in_order=in_order, ignore=ignore)
    except AssertionError as e:
      if not isinstance(expected, str):
        expected = pprint.pformat(expected)
      if not isinstance(actual, str):
        actual = pprint.pformat(actual)
      raise AssertionError(f"""{msg}: {''.join(e.args)}
Expected value:
{expected}
Actual value:
{actual}""") from None

  def _assert_equals(self, expected, actual, in_order=False, ignore=()):
    """Recursive helper for assert_equals().
    """
    key = None

    try:
      if isinstance(expected, RE_TYPE):
        if not re.match(expected, actual):
          self.fail(f"{expected!r} doesn't match {actual}")
      elif isinstance(expected, dict) and isinstance(actual, dict):
        for key in set(expected.keys()) | set(actual.keys()):
          if key not in ignore:
            self._assert_equals(expected.get(key), actual.get(key),
                                in_order=in_order, ignore=ignore)
      elif (isinstance(expected, (list, tuple, set)) and
            isinstance(actual, (list, tuple, set))):
        if not in_order:
          # use custom key because Python 3 dicts are not comparable :/
          def hash_or_json(x):
            try:
              return str(hash(x))
            except TypeError:
              return json_dumps(x, sort_keys=True)
          expected = sorted(expected, key=hash_or_json)
          actual = sorted(actual, key=hash_or_json)

        self.assertEqual(len(expected), len(actual),
                         f'Different lengths:\n expected {len(expected)}\n actual {len(actual)}')
        for key, (e, a) in enumerate(zip(expected, actual)):
          self._assert_equals(e, a, in_order=in_order, ignore=ignore)
      elif (isinstance(expected, str) and isinstance(actual, str) and
            '\n' in expected):
        self.assert_multiline_equals(expected, actual)
      else:
        self.assertEqual(expected, actual)

    except AssertionError as e:
      # fill in where this failure came from. this recursively builds,
      # backwards, all the way up to the root.
      args = (f'[{key}] ' if key is not None else '') + ''.join(e.args)
      raise AssertionError(args) from None

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
    self.assertIn(exp, act, f"""{exp}

not found in:

{act}""")

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
    # suppress a few warnings
    # local/lib/python3.8/site-packages/mf2util.py:556: DeprecationWarning: The 'warn' function is deprecated, use 'warning' instead
    # logging.warn(f'Failed to parse datetime {date_str}')
    warnings.filterwarnings('ignore', module='mf2util',
                            message="The 'warn' function is deprecated")
    # local/lib/python3.6/site-packages/mox3/mox.py:909: DeprecationWarning: inspect.getargspec() is deprecated, use inspect.signature() or inspect.getfullargspec()
    warnings.filterwarnings('ignore', module='mox', message=r'inspect\.getargspec')
    # local/lib/python3.8/site-packages/webmentiontools/send.py:65: GuessedAtParserWarning: No parser was explicitly specified, so I'm using the best available HTML parser for this system ("lxml"). This usually isn't a problem, but if you run this code on another system, or in a different virtual environment, it may use a different parser and behave differently.
    warnings.filterwarnings('ignore', category=GuessedAtParserWarning)
    # local/lib/python3.9/site-packages/bs4/__init__.py:435: MarkupResemblesLocatorWarning: The input looks more like a filename than markup. You may want to open this file and pass the filehandle into Beautiful Soup.
    warnings.filterwarnings('ignore', category=MarkupResemblesLocatorWarning)
    # local/lib/python3.9/site-packages/bs4/builder/__init__.py:545: XMLParsedAsHTMLWarning: It looks like you're parsing an XML document using an HTML parser. If this really is an HTML document (maybe it's XHTML?)...
    warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

    super(TestCase, self).setUp()

    appengine_info.APP_ID = 'my-app'
    appengine_info.LOCAL_SERVER = False

    for method in 'get', 'post', 'delete':
      self.mox.StubOutWithMock(requests, method, use_mock_anything=True)
    self.stub_requests_head()

    self.mox.StubOutWithMock(util.urllib.request, 'urlopen')

    # set time zone to UTC so that tests don't depend on local time zone
    os.environ['TZ'] = 'UTC'

    util.follow_redirects_cache.clear()

    util.now = lambda **kwargs: NOW

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

  def expect_requests_delete(self, *args, **kwargs):
    return self._expect_requests_call(*args, method=requests.delete, **kwargs)

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
      allow_redirects=kwargs.get('allow_redirects'),
      encoding=kwargs.pop('encoding', None))

    if 'timeout' not in kwargs:
      kwargs['timeout'] = HTTP_TIMEOUT
    elif kwargs['timeout'] is None:
      del kwargs['timeout']

    if 'stream' not in kwargs:
      kwargs['stream'] = True
    elif kwargs['stream'] is None:
      del kwargs['stream']

    if method is requests.head:
      kwargs['allow_redirects'] = True

    headers = kwargs.get('headers')
    if not headers:
      headers = kwargs['headers'] = {}

    if not isinstance(headers, mox.Comparator):
      headers.setdefault('User-Agent', util.user_agent)

      def check_headers(actual):
        missing = set(headers.items()) - set(actual.items())
        assert not missing, f'Missing request headers: {missing}\n(Got {set(actual.items())}, expected {set(headers.items())})'
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
      assert isinstance(req, urllib.request.Request), repr(req)
      try:
        if isinstance(url, RE_TYPE):
          self.assertRegexpMatches(req.get_full_url(), url)
        else:
          self.assertEqual(url, req.get_full_url())

        self.assertEqual(
            data.decode() if isinstance(data, bytes) else data,
            req.data.decode() if isinstance(req.data, bytes) else req.data)

        nonlocal headers
        if isinstance(headers, mox.Comparator):
          self.assertTrue(headers.equals(req.header_items()))
        else:
          if not headers:
            headers = {}
          missing = set(headers.items()) - set(req.header_items())
          assert not missing, f'Missing request headers: {missing}; got {req.header_items()}'

      except AssertionError:
        traceback.print_exc()
        return False

      return True

    if 'timeout' not in kwargs:
      kwargs['timeout'] = HTTP_TIMEOUT

    call = util.urllib.request.urlopen(mox.Func(check_request), **kwargs)
    if status // 100 != 2:
      if response:
        response = urllib.request.addinfourl(io.StringIO(str(response)),
                                             response_headers, url, status)
      call.AndRaise(urllib.error.HTTPError('url', status, 'message',
                                           response_headers, response))
    elif response is not None:
      call.AndReturn(UrlopenResult(status, response, url=url,
                                   headers=response_headers))

    return call
