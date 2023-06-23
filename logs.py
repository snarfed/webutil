"""A handler that serves all app logs for an App Engine HTTP request.

StackDriver Logging API:
https://cloud.google.com/logging/docs/apis
"""
import calendar
from datetime import datetime, timedelta, timezone
import html
import logging
import re
import time
import urllib.request, urllib.parse, urllib.error

from flask import request
from google.cloud import ndb
from google.cloud.logging import Client
from oauth_dropins.webutil.util import json_dumps, json_loads

from .appengine_info import APP_ID
from . import flask_util, util
from .flask_util import error

logger = logging.getLogger(__name__)

LEVELS = {
  logging.DEBUG:    'D',
  logging.INFO:     'I',
  logging.WARNING:  'W',
  logging.ERROR:    'E',
  logging.CRITICAL: 'F',
}

CACHE_TIME = timedelta(days=1)
MAX_LOG_AGE = timedelta(days=30)
# App Engine's launch, roughly
MIN_START_TIME = time.mktime(datetime(2008, 4, 1, tzinfo=timezone.utc).timetuple())
MAX_START_TIME = time.mktime(datetime(2099, 1, 1, tzinfo=timezone.utc).timetuple())

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


def url(when, key, **params):
  """Returns the relative URL (no scheme or host) to a log page.

  Args:
    when: datetime
    key: ndb.Key or str
    params: included as query params, eg module, path
  """
  assert 'start_time' not in params and 'key' not in params, params

  if isinstance(params.get('path'), (list, tuple)):
    for path in params['path']:
      assert ',' not in path, path
    params['path'] = ','.join(params['path'])

  params.update({
    'start_time': calendar.timegm(when.utctimetuple()),
    'key': key.urlsafe().decode() if isinstance(key, ndb.Key) else key,
  })
  return 'log?' + urllib.parse.urlencode(params)


def maybe_link(when, key, time_class='dt-updated', link_class='', **params):
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
    key: ndb.Key or str
    time_class: string, optional class value for the <time> tag
    link_class: string, optional class value for the <a> tag (if generated)
    params: dict {string: string}, query params to include in the link URL,
      eg module, path

  Returns: string HTML
  """
  # always show time zone. assume naive timestamps are UTC.
  if when.tzinfo is None:
    when = when.replace(tzinfo=timezone.utc)

  now = util.now(tz=when.tzinfo)

  time = f'<time class="{time_class}" datetime="{when.isoformat()}" title="{when.ctime()} {when.tzname()}">{util.naturaltime(when, when=now)}</time>'

  if now > when > now - MAX_LOG_AGE:
    return f'<a class="{link_class}" href="/{url(when, key, **params)}">{time}</a>'

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
      # Useful for logging, but also causes false positives in the search, we
      # find and use log requests instead of real requests.
      # logger.debug(f'Linkifying datastore key: {'match.group(2)}')
      key = ndb.Key(urlsafe=match.group(2))
      tokens = [(kind, f"{'id' if isinstance(id, int) else 'name'}:{id}")
                for kind, id in key.pairs()]
      key_str = '0/|' + '|'.join(f'{len(kind)}/{kind}|{len(id)}/{id}'
                                 for kind, id in tokens)
      key_quoted = urllib.parse.quote(urllib.parse.quote(key_str, safe=''), safe='')
      html = f"{match.group(1)}<a title='{match.group(2)}' href='https://console.cloud.google.com/datastore/entities;kind={key.kind()};ns=__$DEFAULT$__/edit;key={key_quoted}?project={APP_ID}'>{match.group(3)}...</a>{match.group(4)}"
      logger.debug(f'Returning {html}')
      return html
    except BaseException:
      # logger.debug("Couldn't linkify candidate datastore key.")   # too noisy
      return match.group(0)

  return DATASTORE_KEY_RE.sub(linkify_key, msg)


def log(module=None, path=None):
    """Flask view that searches for and renders app logs for an HTTP request.

    URL parameters:
      start_time: float, seconds since the epoch
      key: string that should appear in the first app log

    Install with:
      app.add_url_rule('/log', view_func=logs.log)

    Or:
      @app.get('/log')
      @cache.cached(600)
      def log():
        return logs.log()

    Args:
      module: str, App Engine module to search. Defaults to all.
      path: string or sequence of strings, optional HTTP request path(s) to
        limit logs to.

    Returns:
      (string response body, dict headers) Flask response
    """
    if not module:
      module = request.values.get('module')
    if not path:
      path = request.values.get('path')

    start_time = flask_util.get_required_param('start_time')
    if not util.is_float(start_time):
      return error(f"Couldn't convert start_time to float: {start_time!r}")

    start_time = float(start_time)
    if start_time < MIN_START_TIME:
      return error(f'start_time must be >= {MIN_START_TIME}')
    elif start_time > MAX_START_TIME:
      return error(f'start_time must be <= {MAX_START_TIME}')

    client = Client()
    project = f'projects/{APP_ID}'
    key = urllib.parse.unquote_plus(flask_util.get_required_param('key'))

    # first, find the individual log message to get the trace id
    utcfromtimestamp = datetime.utcfromtimestamp
    timestamp_filter = (
      f"timestamp>=\"{utcfromtimestamp(start_time - 60).isoformat() + 'Z'}\" "
      f"timestamp<=\"{utcfromtimestamp(start_time + 120).isoformat() + 'Z'}\"")
    query = f'logName="{project}/logs/python" textPayload:"{key}" {timestamp_filter}'
    if module:
      query += f' resource.labels.module_id="{module}"'
    if path:
      or_paths = ' OR '.join(f'"{path}"' for path in path.split(','))
      query += f' httpRequest.requestUrl:({or_paths})'

    logger.info(f'Searching logs with: {query}')
    try:
      # https://googleapis.dev/python/logging/latest/client.html#google.cloud.logging_v2.client.Client.list_entries
      log = next(iter(client.list_entries(filter_=query, page_size=1)))
    except StopIteration:
      logger.info('No log found!')
      return 'No log found!', 404

    logger.info(f'Got insert id {log.insert_id} trace {log.trace}')

    # now, print all logs with that trace
    resp = """\
<html>
<body style="font-family: monospace; white-space: pre">
"""

    query = f'logName="{project}/logs/python" trace="{log.trace}" resource.type="gae_app" {timestamp_filter}'
    logger.info(f'Searching logs with: {query}')

    # sanitize and render each line
    for log in client.list_entries(filter_=query, page_size=1000):
      # payload is a union that can be string, JSON, or protobuf
      # https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry#FIELDS.oneof_payload
      msg = log.payload
      if not msg:
        continue
      elif isinstance(msg, (dict, list)):
        msg = json_dumps(msg, indent=2)
      else:
        msg = str(msg)

      msg = linkify_datastore_keys(util.linkify(html.escape(
        msg if msg.startswith('Created by this poll:') else sanitize(msg),
        quote=False)))
      resp += '%s %s %s<br />' % (
        log.severity[0], log.timestamp, msg.replace('\n', '<br />'))

    resp += '</body>\n</html>'
    return resp, {'Content-Type': 'text/html; charset=utf-8'}
