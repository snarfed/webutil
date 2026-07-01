"""Unit test utilities."""
from datetime import datetime, timezone
import difflib
import email
import functools
import io
import os
import pprint
import re
import traceback
import unittest.mock
import urllib.error, urllib.parse, urllib.request
import warnings

from bs4 import (
    GuessedAtParserWarning,
    MarkupResemblesLocatorWarning,
    XMLParsedAsHTMLWarning,
)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import requests

from . import appengine_info, models, util
from .util import json_dumps, json_loads, HTTP_TIMEOUT

RE_TYPE = (re.Pattern if hasattr(re, 'Pattern')  # python >=3.7
           else re._pattern_type)                # python <3.7

NOW = datetime(2022, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
NOW_SECONDS = int((NOW - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())

# don't truncate assertion error diffs
import unittest.util
unittest.util._MAX_LENGTH = 999999

_TEST_KEY_BYTES = b'test_key_32_bytes_for_aes_256___'
models.ENCRYPTED_PROPERTY_KEYS_BYTES = (_TEST_KEY_BYTES,)
models.ENCRYPTED_PROPERTY_KEYS = (AESGCM(_TEST_KEY_BYTES),)


def requests_response(body='', url=None, status=200, content_type=None,
                      redirected_url=None, headers=None, allow_redirects=None,
                      encoding=None):
    """
    Args:
      redirected_url (str sequence of str): URL(s) for multiple redirects
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


def head_returns_200(fn):
  """Test method decorator that stubs :func:`util.requests_head` to a no-op 200.

  Returns each requested URL unchanged (no redirect), so code that follows
  redirects via ``HEAD`` doesn't make real requests. Unlike a bare
  ``@patch.object``, doesn't inject a mock argument into the decorated method.
  """
  @functools.wraps(fn)
  def wrapper(*args, **kwargs):
    with unittest.mock.patch.object(
        util, 'requests_head',
        side_effect=lambda url, **kw: requests_response('', url=url)):
      return fn(*args, **kwargs)

  return wrapper


def enable_flask_caching(app, cache):
  """Test case decorator that enables a flask_caching cache.

  Usage::

      from app import app, cache

      class FooTest(TestCase):
        @enable_flask_caching(app, cache)
        def test_foo(self):
          ..

  Args:
    app (flask.Flask)
    cache (flask_caching.Cache)
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
    self.content = io.StringIO(content if isinstance(content, str)
                               else json_dumps(content))
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
      a (:class:`ndb.Model`): instance or list of instances
      b (:class:`ndb.Model`): same
      ignore (sequence of str): property names not to compare
      keys_only (bool): if True only compare keys
      in_order (bool): if False, all entities must have keys
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

    If ``in_order`` is False, ignores order in lists and tuples.
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
            not isinstance(expected, unittest.mock._Call) and
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
                         f'Different lengths:\n expected {len(expected)}\n actual {len(actual)}\nexpected {expected}\nactual {actual}')
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
      ignore_blanks (boolean): whether to ignore blank lines altogether
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
      ignore_blanks (boolean): whether to ignore blank lines altogether
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


class TestCase(Asserts, unittest.TestCase):
  """Base test case with assert helpers, common setUp, and mock utilities."""
  maxDiff = None

  def setUp(self):
    suppress_warnings()
    super().setUp()

    appengine_info.APP_ID = 'my-app'
    appengine_info.LOCAL_SERVER = False

    # set time zone to UTC so that tests don't depend on local time zone
    os.environ['TZ'] = 'UTC'

    util.follow_redirects_cache.clear()

    orig_now = util.now
    util.now = lambda tz=timezone.utc: NOW.replace(tzinfo=tz)
    self.addCleanup(setattr, util, 'now', orig_now)

  def start_patch(self, obj, attr, **kwargs):
    # TODO: replace with self.enterContext(patch.object(...)) once we require
    # Python >= 3.11.
    patcher = unittest.mock.patch.object(obj, attr, **kwargs)
    mock = patcher.start()
    self.addCleanup(patcher.stop)
    return mock

  def assert_urlopen(self, url, data=None):
    """Asserts self.mock_urlopen was called with this exact URL."""
    for c in self.mock_urlopen.call_args_list:
      if c.args[0].full_url == url:
        if data:
          actual = c.args[0].data
          if isinstance(actual, bytes):
            actual = actual.decode()
          self.assertEqual(data, actual)
        return

    self.fail(f'No urlopen call to {url}; got {[c.args[0].full_url for c in self.mock_urlopen.call_args_list]}')

  def assert_requests_get(self, url, cookie=None):
    self._assert_request(self.mock_get, url, cookie=cookie)

  def assert_requests_post(self, url, **kwargs):
    self._assert_request(self.mock_post, url, **kwargs)

  def _assert_request(self, mock, url, cookie=None, **kwargs):
    """Asserts a mock was called with this URL and optional kwargs."""
    for c in mock.call_args_list:
      if c.args[0] == url:
        if cookie is not None:
          self.assertEqual(cookie, c.kwargs.get('headers', {}).get('Cookie'))
        for key, val in kwargs.items():
          self.assertEqual(val, c.kwargs[key])
        return

    self.fail(f'No session.get call to {url}; got {[c.args[0] for c in self.mock_get.call_args_list]}')



def suppress_warnings():
    # local/lib/python3.11/site-packages/bs4/builder/_lxml.py:124: DeprecationWarning: The 'strip_cdata' option of HTMLParser() has never done anything and will eventually be removed.
    warnings.filterwarnings('ignore', category=DeprecationWarning,
                            message="The 'strip_cdata' option of HTMLParser")
    # local/lib/python3.12/site-packages/google/cloud/ndb/model.py:3900: DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version. Use timezone-aware objects to represent datetimes in UTC: datetime.datetime.now(datetime.UTC).
    warnings.filterwarnings('ignore', category=DeprecationWarning,
                            message=r'datetime\.datetime\.utcnow\(\) is deprecated')
    # local/lib/python3.12/site-packages/google/cloud/ndb/tasklets.py:319: DeprecationWarning: the (type, exc, tb) signature of throw() is deprecated, use the single-arg signature instead.
    warnings.filterwarnings('ignore', category=DeprecationWarning,
                            message=r'the \(type, exc, tb\) signature of throw\(\) is deprecated')
    # local/lib/python3.8/site-packages/mf2util.py:556: DeprecationWarning: The 'warn' function is deprecated, use 'warning' instead
    # logging.warn(f'Failed to parse datetime {date_str}')
    warnings.filterwarnings('ignore', module='mf2util',
                            message="The 'warn' function is deprecated")
    # local/lib/python3.8/site-packages/webmentiontools/send.py:65: GuessedAtParserWarning: No parser was explicitly specified, so I'm using the best available HTML parser for this system ("lxml"). This usually isn't a problem, but if you run this code on another system, or in a different virtual environment, it may use a different parser and behave differently.
    warnings.filterwarnings('ignore', category=GuessedAtParserWarning)
    # local/lib/python3.9/site-packages/bs4/__init__.py:435: MarkupResemblesLocatorWarning: The input looks more like a filename than markup. You may want to open this file and pass the filehandle into Beautiful Soup.
    warnings.filterwarnings('ignore', category=MarkupResemblesLocatorWarning)
    # local/lib/python3.9/site-packages/bs4/builder/__init__.py:545: XMLParsedAsHTMLWarning: It looks like you're parsing an XML document using an HTML parser. If this really is an HTML document (maybe it's XHTML?)...
    warnings.filterwarnings('ignore', category=XMLParsedAsHTMLWarning)

    # https://stackoverflow.com/a/78803598/186123
    os.environ['GRPC_VERBOSITY'] = 'ERROR'
