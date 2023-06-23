"""Unit tests for logs.py. Woefully incomplete."""
from datetime import datetime, timedelta, timezone
import time

from flask import Flask
from google.cloud import ndb
from mox3 import mox

from .. import appengine_config, logs
from ..testutil import NOW

with appengine_config.ndb_client.context():
  KEY = ndb.Key('Foo', 123)
  KEY_STR = KEY.urlsafe().decode()


class LogsTest(mox.MoxTestBase):
  def setUp(self):
    super().setUp()
    self.app = Flask('test_logs')
    self.app.add_url_rule('/log', view_func=logs.log)
    self.app.config['TESTING'] = True
    self.client = self.app.test_client()

  def test_url(self):
    self.assertEqual(f'log?start_time=172800&key={KEY_STR}',
                     logs.url(datetime(1970, 1, 3), KEY))

  def test_maybe_link(self):
    when = datetime(1970, 1, 3)
    expected = r'<time class="foo" datetime="1970-01-03T00:00:00\+00:00" title="Sat Jan  3 00:00:00 1970 UTC">\d+ years ago</time>'
    actual = logs.maybe_link(when, KEY, time_class='foo')
    self.assertRegex(actual, expected)

    self.mox.StubOutWithMock(logs, 'MAX_LOG_AGE')
    logs.MAX_LOG_AGE = timedelta(days=99999)

    self.assertEqual(
      f'<a class="bar" href="/log?start_time=172800&key={KEY_STR}">{actual}</a>',
      logs.maybe_link(when, KEY, time_class='foo', link_class='bar'))

  def test_maybe_link_path(self):
    self.mox.StubOutWithMock(logs, 'MAX_LOG_AGE')
    logs.MAX_LOG_AGE = timedelta(days=99999)
    self.assertIn('path=foo%2Cbar%2Fbaz',
                  logs.maybe_link(NOW, KEY, path=['foo', 'bar/baz']))

  def test_maybe_link_future(self):
    got = logs.maybe_link(NOW + timedelta(minutes=1), KEY)
    self.assertFalse(got.startswith('<a'), repr(got))

  def test_start_time_too_old(self):
    resp = self.client.get(f'/log?key=abc&start_time=644858558')
    self.assertEqual(400, resp.status_code)
    self.assertIn('start_time must be &gt;= ', resp.get_data(as_text=True))

  def test_start_time_too_far_future(self):
    resp = self.client.get(f'/log?key=abc&start_time=16448494169326941')
    self.assertEqual(400, resp.status_code)
    self.assertIn('start_time must be &lt;= ', resp.get_data(as_text=True))
