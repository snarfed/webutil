"""A handler that exposes App Engine app logs to users.
"""
from future import standard_library
standard_library.install_aliases()

import calendar
import cgi
import datetime
import logging
import re
import time
import urllib.request, urllib.parse, urllib.error

import appengine_config
from google.appengine.api import logservice
from google.appengine.ext import ndb
import humanize
import webapp2

import util


LEVELS = {
  logservice.LOG_LEVEL_DEBUG:    'D',
  logservice.LOG_LEVEL_INFO:     'I',
  logservice.LOG_LEVEL_WARNING:  'W',
  logservice.LOG_LEVEL_ERROR:    'E',
  logservice.LOG_LEVEL_CRITICAL: 'F',
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
    calendar.timegm(when.utctimetuple()), key.urlsafe())


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
      key_str = '|'.join('%d/%s|%d/%s' % (len(kind), kind, len(id), id)
                         for kind, id in tokens)
      return "'<a title='%s' href='https://console.developers.google.com/datastore/editentity?project=%s&kind=%s&queryType=GQLQuery&queryText&key=0/|%s'>%s...</a>'" % (
        match.group(1), appengine_config.APP_ID, key.kind(), key_str, match.group(2))
    except BaseException:
      logging.debug("Couldn't linkify candidate datastore key.", exc_info=True)
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

    key = urllib.parse.unquote_plus(util.get_required_param(self, 'key'))
    # the propagate task logs the poll task's URL, which includes the source
    # entity key as a query param. exclude that with this heuristic.
    key_re = re.compile('[^=]' + key)

    self.response.headers['Content-Type'] = 'text/html; charset=utf-8'

    offset = None
    kwargs = {
      'start_time': start_time - 60,
      'end_time': start_time + 120,
      'offset': offset,
      'include_app_logs': True,
    }
    if self.MODULE_VERSIONS:
      kwargs['module_versions'] = self.MODULE_VERSIONS
    if self.VERSION_IDS:
      kwargs['version_ids'] = self.VERSION_IDS

    logging.info('Fetching logs with %s', kwargs)
    for log in logservice.fetch(**kwargs):
      first_lines = '\n'.join([line.message.decode('utf-8') for line in
                               log.app_logs[:min(10, len(log.app_logs))]])
      if log.app_logs and key_re.search(first_lines):
        # found it! render and return
        self.response.out.write("""\
<html>
<body style="font-family: monospace; white-space: pre">
""")
        self.response.out.write(sanitize(log.combined))
        self.response.out.write('<br /><br />')
        for a in log.app_logs:
          msg = a.message.decode('utf-8')
          # don't sanitize poll task URLs since they have a key= query param
          msg = linkify_datastore_keys(util.linkify(cgi.escape(
              msg if msg.startswith('Created by this poll:') else sanitize(msg))))
          self.response.out.write('%s %s %s<br />' %
              (datetime.datetime.utcfromtimestamp(a.time), LEVELS[a.level],
               msg.replace('\n', '<br />')))
        self.response.out.write('</body>\n</html>')
        return

      offset = log.offset

    self.response.out.write('No log found!')


application = webapp2.WSGIApplication([
    ('/log', LogHandler),
    ], debug=appengine_config.DEBUG)
