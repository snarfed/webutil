"""Unit test utilities.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import base64
import datetime
import difflib
import logging
import mox
import pprint
import re
import os
import rfc822
import StringIO
import traceback
import urllib2
import urlparse

import appengine_config
import requests
import webapp2

from google.appengine.datastore import datastore_stub_util
from google.appengine.ext import db
from google.appengine.ext import ndb
from google.appengine.ext import testbed


def get_task_params(task):
  """Parses a task's POST body and returns the query params in a dict.
  """
  params = urlparse.parse_qs(base64.b64decode(task['body']))
  params = dict((key, val[0]) for key, val in params.items())
  return params


def get_task_eta(task):
  """Returns a task's ETA as a datetime."""
  return datetime.datetime.fromtimestamp(
    float(dict(task['headers'])['X-AppEngine-TaskETA']))


class UrlopenResult(object):
  """A fake urllib2.urlopen() result object. Also works for urlfetch.fetch().
  """
  def __init__(self, status_code, content, url=None, headers={}):
    self.status_code = status_code
    self.content = StringIO.StringIO(content)
    self.url = url
    self.headers = headers

  def read(self, length=-1):
    return self.content.read(length)

  def getcode(self):
    return self.status_code

  def geturl(self):
    return self.url

  def info(self):
    return rfc822.Message(StringIO.StringIO(
        '\n'.join('%s: %s' % item for item in self.headers.items())))


class TestCase(mox.MoxTestBase):
  """Test case class with lots of extra helpers."""

  def setUp(self):
    super(TestCase, self).setUp()
    for method in 'get', 'post':
      self.mox.StubOutWithMock(requests, method, use_mock_anything=True)
    self.stub_requests_head()

    self.mox.StubOutWithMock(urllib2, 'urlopen')

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
    resp = requests.Response()

    resp._text = response
    resp._content = (response.encode('utf-8') if isinstance(response, unicode)
                     else response)
    resp.encoding = 'utf-8'

    resp.url = url
    if redirected_url is not None:
      if kwargs.get('allow_redirects') == False:
        resp.headers['location'] = redirected_url
      else:
        if isinstance(redirected_url, basestring):
          redirected_url = [redirected_url]
        assert isinstance(redirected_url, (list, tuple))
        resp.url = redirected_url[-1]
        for u in [url] + redirected_url[:-1]:
          resp.history.append(requests.Response())
          resp.history[-1].url = u

    resp.status_code = status_code
    resp.headers['content-type'] = content_type
    if response_headers is not None:
      resp.headers.update(response_headers)

    kwargs.setdefault('timeout', appengine_config.HTTP_TIMEOUT)
    if method is requests.head:
      kwargs['allow_redirects'] = True

    files = kwargs.get('files')
    if files:
      def check_files(actual):
        self.assertEqual(actual.keys(), files.keys())
        for name, expected in files.items():
          self.assertEqual(expected, actual[name].read())
        return True
      kwargs['files'] = mox.Func(check_files)

    call = method(url, **kwargs)
    call.AndReturn(resp)
    return call

  def expect_urlopen(self, url, response=None, status=200, data=None,
                     headers=None, response_headers={}, **kwargs):
    """Stubs out urllib2.urlopen() and sets up an expected call.

    If status isn't 2xx, makes the expected call raise a urllib2.HTTPError
    instead of returning the response.

    If data is set, url *must* be a urllib2.Request.

    If response is unset, returns the expected call.

    Args:
      url: string, re.RegexObject or urllib2.Request or webob.Request
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
          self.assertEqual(data, req.get_data())
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
      kwargs['timeout'] = appengine_config.HTTP_TIMEOUT

    call = urllib2.urlopen(mox.Func(check_request), **kwargs)
    if status / 100 != 2:
      if response:
        response = urllib2.addinfourl(StringIO.StringIO(response),
                                      response_headers, url, status)
      call.AndRaise(urllib2.HTTPError('url', status, 'message',
                                      response_headers, response))
    elif response is not None:
      call.AndReturn(UrlopenResult(status, response, url=url,
                                   headers=response_headers))

    return call

  def assert_entities_equal(self, a, b, ignore=frozenset(), keys_only=False,
                            in_order=False):
    """Asserts that a and b are equivalent entities or lists of entities.

    ...specifically, that they have the same property values, and if they both
    have populated keys, that their keys are equal too.

    Args:
      a, b: db.Model or ndb.Model instances or lists of instances
      ignore: sequence of strings, property names not to compare
      keys_only: boolean, if True only compare keys
      in_order: boolean. If False, all entities must have keys.
    """
    if not isinstance(a, (list, tuple, db.Query, ndb.Query)):
      a = [a]
    if not isinstance(b, (list, tuple, db.Query, ndb.Query)):
      b = [b]

    key_fn = lambda e: e.key if isinstance(e, ndb.Model) else e.key()
    if not in_order:
      a = list(sorted(a, key=key_fn))
      b = list(sorted(b, key=key_fn))

    self.assertEqual(len(a), len(b),
                     'Different lengths:\n expected %s\n actual %s' % (a, b))

    flat_key = lambda e: e.key.flat() if isinstance(e, ndb.Model) else e.key().to_path()
    for x, y in zip(a, b):
      try:
        self.assertEqual(flat_key(x), flat_key(y))
      except (db.BadKeyError, db.NotSavedError):
        if keys_only:
          raise

      def props(e):
        all = e.to_dict() if isinstance(e, ndb.Model) else e.properties()
        return {k: v for k, v in all.items() if k not in ignore}

      if not keys_only:
        self.assert_equals(props(x), props(y), flat_key(x))

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
    except AssertionError, e:
      if not isinstance(expected, basestring):
        expected = pprint.pformat(expected)
      if not isinstance(actual, basestring):
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
      elif isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
        if not in_order:
          expected = sorted(list(expected))
          actual = sorted(list(actual))
        self.assertEqual(len(expected), len(actual),
                         'Different lengths:\n expected %s\n actual %s' %
                         (len(expected), len(actual)))
        for key, (e, a) in enumerate(zip(expected, actual)):
          self._assert_equals(e, a, in_order=in_order)
      elif (isinstance(expected, basestring) and isinstance(actual, basestring) and
            '\n' in expected):
        self.assert_multiline_equals(expected, actual)
      else:
        self.assertEquals(expected, actual)

    except AssertionError, e:
      # fill in where this failure came from. this recursively builds,
      # backwards, all the way up to the root.
      args = ('[%s] ' % key if key is not None else '') + ''.join(e.args)
      raise AssertionError(args)

  def assert_multiline_equals(self, expected, actual):
    """Compares two multi-line strings and reports a diff style output.

    Ignores leading and trailing whitespace on each line, and squeezes repeated
    blank lines down to just one.
    """
    exp_lines = self._normalize_lines(expected)
    act_lines = self._normalize_lines(actual)
    if exp_lines != act_lines:
      self.fail(''.join(difflib.Differ().compare(exp_lines, act_lines)))

  def assert_multiline_in(self, expected, actual):
    """Checks that a multi-line string is in another and reports a diff output.

    Ignores leading and trailing whitespace on each line, and squeezes repeated
    blank lines down to just one.
    """
    exp = ''.join(self._normalize_lines(expected)).strip()
    act = ''.join(self._normalize_lines(actual))
    self.assertIn(exp, act, """\
%s

not found in:

%s""" % (exp, act))

  @staticmethod
  def _normalize_lines(val):
      lines = [l.strip() + '\n' for l in val.splitlines(True)]
      return [l for i, l in enumerate(lines)
              if i <= 1 or not (lines[i - 1] == l == '\n')]


class HandlerTest(TestCase):
  """Base test class for webapp2 request handlers.

  Uses App Engine's testbed to set up API stubs:
  http://code.google.com/appengine/docs/python/tools/localunittesting.html

  Attributes:
    application: WSGIApplication
    handler: webapp2.RequestHandler
  """
  def setUp(self):
    super(HandlerTest, self).setUp()

    os.environ['APPLICATION_ID'] = 'app_id'
    self.current_user_id = '123'
    self.current_user_email = 'foo@bar.com'

    self.testbed = testbed.Testbed()
    self.testbed.setup_env(user_id=self.current_user_id,
                           user_email=self.current_user_email)
    self.testbed.activate()

    hrd_policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=.5)
    self.testbed.init_datastore_v3_stub(consistency_policy=hrd_policy)
    self.testbed.init_taskqueue_stub(root_path='.')
    self.testbed.init_user_stub()
    self.testbed.init_mail_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_logservice_stub()

    # unofficial API, whee! this is so we can call
    # TaskQueueServiceStub.GetTasks() in tests. see
    # google/appengine/api/taskqueue/taskqueue_stub.py
    self.taskqueue_stub = self.testbed.get_stub('taskqueue')

    self.request = webapp2.Request.blank('/')
    self.response = webapp2.Response()
    self.handler = webapp2.RequestHandler(self.request, self.response)

  def tearDown(self):
    self.testbed.deactivate()
    super(HandlerTest, self).tearDown()
