"""A handler that exposes App Engine app logs to users.

StackDriver Logging API:
https://cloud.google.com/logging/docs/apis
"""
import calendar
import cgi
import datetime
import logging
import re
import time
import urllib.request, urllib.parse, urllib.error

from . import appengine_config

from google.cloud import ndb
from google.cloud.logging_v2 import LoggingServiceV2Client
import humanize
import webapp2

from . import request_log_pb2
from . import util
from .util import json_dumps

appengine_config.APP_ID = 'brid-gy'

LEVELS = {
  logging.DEBUG:    'D',
  logging.INFO:     'I',
  logging.WARNING:  'W',
  logging.ERROR:    'E',
  logging.CRITICAL: 'F',
}

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
  time = '<time class="%s" datetime="%s" title="%s">%s</time>' % (
    time_class, when.isoformat(), when.ctime(), humanize.naturaltime(when))

  now = datetime.datetime.now()
  if now > when > now - MAX_LOG_AGE:
    return '<a class="%s" href="/%s">%s</a>' % (link_class, url(when, key), time)

  return time


# datastore string keys are url-safe-base64 of, say, at least 32(ish) chars.
# https://cloud.google.com/appengine/docs/python/ndb/keyclass#Key_urlsafe
# http://tools.ietf.org/html/rfc3548.html#section-4
DATASTORE_KEY_RE = re.compile("'(([A-Za-z0-9-_=]{8})[A-Za-z0-9-_=]{24,})'")

def linkify_datastore_keys(msg):
  """Converts string datastore keys to links to the admin console viewer."""
  def linkify_key(match):
    try:
      key = ndb.Key(urlsafe=match.group(1))
      tokens = [(kind, '%s:%s' % ('id' if isinstance(id, int) else 'name', id))
                for kind, id in key.pairs()]
      key_str = '0/|' + '|'.join('%d/%s|%d/%s' % (len(kind), kind, len(id), id)
                                 for kind, id in tokens)
      key_quoted = urllib.parse.quote(urllib.parse.quote(key_str), safe=True)
      return "'<a title='%s' href='https://console.cloud.google.com/datastore/entities;kind=%s;ns=__$DEFAULT$__/edit;key=%s?project=%s'>%s...</a>'" % (
        match.group(1), key.kind(), key_quoted, appengine_config.APP_ID, match.group(2))
    except BaseException:
      logging.debug("Couldn't linkify candidate datastore key.", stack_info=True)
      return msg

  return DATASTORE_KEY_RE.sub(linkify_key, msg)


class LogHandler(webapp2.RequestHandler):
  """Searches for and renders the app logs for a single task queue request.

  Class attributes:
    MODULE_VERSIONS: optional list of (module, version) tuples to search.
      Overrides VERFSION_IDS.
    VERSION_IDS: optional list of current module versions to search. If unset,
      defaults to just the current version!
  """
  MODULE_VERSIONS = None
  VERSION_IDS = None

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

    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_file('/Users/ryan/brid-gy-f51a4db29784.json')

    client = LoggingServiceV2Client(credentials=creds)
    project = 'projects/%s' % appengine_config.APP_ID
    key = urllib.parse.unquote_plus(util.get_required_param(self, 'key'))

    # first, find the individual stdout log message to get the trace id
    query = '\
logName="%s/logs/stdout" AND \
timestamp>="%s" AND \
timestamp<="%s" AND \
jsonPayload.message:"%s"' % (
  project,
  datetime.datetime.utcfromtimestamp(start_time - 60).isoformat() + 'Z',
  datetime.datetime.utcfromtimestamp(start_time + 120).isoformat() + 'Z',
  key)
    logging.info('Searching logs with: %s', query)
    try:
      # https://googleapis.dev/python/logging/latest/gapic/v2/api.html#google.cloud.logginjg_v2.LoggingServiceV2Client.list_log_entries
      log = next(iter(client.list_log_entries((project,), filter_=query, page_size=1)))
    except StopIteration:
      self.response.out.write('No log found!')
      return

    logging.info('Got insert id %s trace %s', log.insert_id, log.trace)

    # now, find the request_log with that trace
    query = '\
logName="%s/logs/appengine.googleapis.com%%2Frequest_log" AND \
trace="%s"' % (project, log.trace)
    logging.info('Searching logs with: %s', query)
    try:
      req = next(iter(client.list_log_entries((project,), filter_=query, page_size=1)))
    except StopIteration:
      self.response.out.write('No log found!')
      return

    pb = request_log_pb2.RequestLog.FromString(req.proto_payload.value)
    logging.info('Got insert id %s request id %s', req.insert_id, pb.request_id)

    self.response.headers['Content-Type'] = 'text/html; charset=utf-8'
    self.response.out.write("""\
<html>
<body style="font-family: monospace; white-space: pre">
<p>%s %s %s %s</p>
""" % (pb.http_version, pb.method, pb.resource, pb.status))

    # sanitize and render each text line
    logging.info('@ %s', req)
    logging.info('@@ %s', pb)
    for line in pb.line:
      logging.info('@@@')
      msg = line.log_message
      # don't sanitize poll task URLs since they have a key= query param
      msg = linkify_datastore_keys(util.linkify(cgi.escape(
        msg if msg.startswith('Created by this poll:') else sanitize(msg))))
      timestamp = line.time.seconds + float(line.time.nanos) / 1000000000
      self.response.out.write('%s %s %s:%s %s<br />' % (
        LEVELS[line.severity],
        datetime.datetime.utcfromtimestamp(timestamp),
        line.source_location.file.split('/')[-1],
        line.source_location.line,
        msg.replace('\n', '<br />')))

    self.response.out.write('</body>\n</html>')
