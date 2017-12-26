"""Unit tests for logs.py. Woefully incomplete."""
import datetime

from google.appengine.ext import ndb
import mox

import logs


class LogsTest(mox.MoxTestBase):

  def test_url(self):
    self.assertEqual('log?start_time=172800&key=agZhcHBfaWRyCQsSA0Zvbxh7DA',
                     logs.url(datetime.datetime(1970, 1, 3), ndb.Key('Foo', 123)))

  def test_maybe_link(self):
    when = datetime.datetime(1970, 1, 3)
    key = ndb.Key('Foo', 123)

    expected = r'<time class="foo" datetime="1970-01-03T00:00:00" title="Sat Jan  3 00:00:00 1970">\d+ years ago</time>'
    actual = logs.maybe_link(when, key, time_class='foo')
    self.assertRegexpMatches(actual, expected)

    self.mox.StubOutWithMock(logs, 'MAX_LOG_AGE')
    logs.MAX_LOG_AGE = datetime.timedelta(days=99999)

    self.assertEqual(
      '<a class="bar" href="/log?start_time=172800&key=agZhcHBfaWRyCQsSA0Zvbxh7DA">%s</a>' % actual,
      logs.maybe_link(when, key, time_class='foo', link_class='bar'))

  def test_maybe_link_future(self):
    when = datetime.datetime.now() + datetime.timedelta(minutes=1)
    got = logs.maybe_link(when, ndb.Key('Foo', 123))
    self.assertFalse(got.startswith('<a'), got)
