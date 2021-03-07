"""A handler that exposes App Engine app logs to users.

StackDriver Logging API:
https://cloud.google.com/logging/docs/apis
"""
import calendar
import datetime
import html
import logging
import re
import time
import urllib.request, urllib.parse, urllib.error

from google.cloud import ndb
from google.cloud.logging import Client
import humanize
import webapp2

from .appengine_info import APP_ID
from . import handlers, util

LEVELS = {
  logging.DEBUG:    'D',
  logging.INFO:     'I',
  logging.WARNING:  'W',
  logging.ERROR:    'E',
  logging.CRITICAL: 'F',
}

CACHE_TIME = datetime.timedelta(days=1)
CACHE_SIZE = 2 * 1000 * 1000  # 2 MB

MAX_LOG_AGE = datetime.timedelta(days=30)
# App Engine's launch, roughly
MIN_START_TIME = time.mktime(datetime.datetime(2008, 4, 1).timetuple())

SANITIZE_RE = re.compile(r"""
  ((?:access|api|oauth)?[ _]?
   (?:code|consumer_key|consumer_secret|nonce|secret|signature|token|verifier)
     (?:u?['"])?
   (?:=|:|\ |,\ |%3D)\ *
     (?:u?['"])?
  )
  [^ &='"]+
""", flags=re.VERBOSE | re.IGNORECASE)

def sanitize(msg):
  """Sanitizes access tokens and Authorization headers."""
  return SANITIZE_RE.sub(r'\1...', msg)


def url(when, key):
  """Returns the relative URL (no scheme or host) to a log page.

  Args:
    when: datetime
    key: ndb.Key
  """
  return 'log?start_time=%s&key=%s' % (
    calendar.timegm(when.utctimetuple()), key.urlsafe().decode())


def maybe_link(when, key, time_class='dt-updated', link_class=''):
  """Returns an HTML snippet with a timestamp and maybe a log page link.

  Example:

  <a href="/log?start_time=1513904267&key=aglz..." class="u-bridgy-log">
    <time class="dt-updated" datetime="2017-12-22T00:57:47.222060"
            title="Fri Dec 22 00:57:47 2017">
      3 days ago
    </time>
  </a>

  The <a> tag is only included if the timestamp is 30 days old or less, since
  Stackdriver's basic tier doesn't store logs older than that:
    https://cloud.google.com/monitoring/accounts/tiers#logs_ingestion
    https://github.com/snarfed/bridgy/issues/767

  Args:
    when: datetime
    key: ndb.Key
    time_class: string, optional class value for the <time> tag
    link_class: string, optional class value for the <a> tag (if generated)

  Returns: string HTML
  """
  # always show time zone. assume naive timestamps are UTC.
  if when.tzinfo is None:
    when = when.replace(tzinfo=datetime.timezone.utc)

  # humanize.naturaltime breaks on timezone-aware datetimes :(
  # https://github.com/jmoiron/humanize/issues/9#issuecomment-322917865
  now = datetime.datetime.now(tz=when.tzinfo)

  time = '<time class="%s" datetime="%s" title="%s %s">%s</time>' % (
    time_class, when.isoformat(), when.ctime(), when.tzname(),
    humanize.naturaltime(when, when=now))

  if now > when > now - MAX_LOG_AGE:
    return '<a class="%s" href="/%s">%s</a>' % (link_class, url(when, key), time)

  return time


# datastore string keys are url-safe-base64 of, say, at least 32(ish) chars.
# https://cloud.google.com/appengine/docs/python/ndb/keyclass#Key_urlsafe
# http://tools.ietf.org/html/rfc3548.html#section-4
BASE64 = 'A-Za-z0-9-_='
DATASTORE_KEY_RE = re.compile("([^%s])(([%s]{8})[%s]{24,})([^%s])" % ((BASE64,) * 4))

def linkify_datastore_keys(msg):
  """Converts string datastore keys to links to the admin console viewer."""
  def linkify_key(match):
    try:
      logging.debug('Linkifying datastore key: %s', match.group(2))
      key = ndb.Key(urlsafe=match.group(2))
      tokens = [(kind, '%s:%s' % ('id' if isinstance(id, int) else 'name', id))
                for kind, id in key.pairs()]
      key_str = '0/|' + '|'.join('%d/%s|%d/%s' % (len(kind), kind, len(id), id)
                                 for kind, id in tokens)
      key_quoted = urllib.parse.quote(urllib.parse.quote(key_str, safe=''), safe='')
      html = "%s<a title='%s' href='https://console.cloud.google.com/datastore/entities;kind=%s;ns=__$DEFAULT$__/edit;key=%s?project=%s'>%s...</a>%s" % (
        match.group(1), match.group(2), key.kind(), key_quoted, APP_ID,
        match.group(3), match.group(4))
      logging.debug('Returning %s', html)
      return html
    except BaseException as e:
      # logging.debug("Couldn't linkify candidate datastore key.")   # too noisy
      return match.group(0)

  return DATASTORE_KEY_RE.sub(linkify_key, msg)


class LogHandler(webapp2.RequestHandler):
  """Searches for and renders the app logs for a single task queue request."""
  @handlers.cache_response(CACHE_TIME, size=CACHE_SIZE)
  def get(self):
    """URL parameters:
      start_time: float, seconds since the epoch
      key: string that should appear in the first app log
    """
    start_time = util.get_required_param(self, 'start_time')
    if not util.is_float(start_time):
      self.abort(400, "Couldn't convert start_time to float: %r" % start_time)

    start_time = float(start_time)
    if start_time < MIN_START_TIME:
      self.abort(400, "start_time must be >= %s" % MIN_START_TIME)

    client = Client()
    project = 'projects/%s' % APP_ID
    key = urllib.parse.unquote_plus(util.get_required_param(self, 'key'))

    # first, find the individual stdout log message to get the trace id
    timestamp_filter = 'timestamp>="%s" timestamp<="%s"' % (
      self.utcfromtimestamp(start_time - 60).isoformat() + 'Z',
      self.utcfromtimestamp(start_time + 120).isoformat() + 'Z')
    query = 'logName="%s/logs/stdout" jsonPayload.message:"%s" %s' % (
      project, key, timestamp_filter)
    logging.info('Searching logs with: %s', query)
    try:
      # https://googleapis.dev/python/logging/latest/client.html#google.cloud.logging_v2.client.Client.list_entries
      log = next(iter(client.list_entries(filter_=query, page_size=1)))
    except StopIteration:
      logging.info('No log found!')
      self.response.out.write('No log found!')
      return

    logging.info('Got insert id %s trace %s', log.insert_id, log.trace)

    # now, print all logs with that trace
    self.response.headers['Content-Type'] = 'text/html; charset=utf-8'
    self.response.out.write("""\
<html>
<body style="font-family: monospace; white-space: pre">
""")

    query = 'logName="%s/logs/stdout" trace="%s" resource.type="gae_app" %s' % (
      project, log.trace, timestamp_filter)
    logging.info('Searching logs with: %s', query)

    # sanitize and render each line
    for log in client.list_entries(filter_=query, page_size=1000):
      msg = log.payload.get('message')
      if msg:
        msg = linkify_datastore_keys(util.linkify(html.escape(
          msg if msg.startswith('Created by this poll:') else sanitize(msg),
          quote=False)))
        self.response.out.write('%s %s %s<br />' % (
          log.severity[0], log.timestamp, msg.replace('\n', '<br />')))

    self.response.out.write('</body>\n</html>')

  def utcfromtimestamp(self, val):
    """Wrapper for datetime.utcfromtimestamp that returns HTTP 400 on overflow.

    ...specifically, if datetime.utcfromtimestamp raises OverflowError because
    the timestamp is greater than the platform's time_t can hold.
    https://docs.python.org/3.9/library/datetime.html#datetime.datetime.utcfromtimestamp
    """
    try:
      return datetime.datetime.utcfromtimestamp(val)
    except OverflowError:
      self.abort(400, f'start_time too big: {val}')
