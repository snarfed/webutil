"""Misc utilities.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import datetime
import logging
import re
import urllib
import urlparse


class Struct(object):
  """A generic class that initializes its attributes from constructor kwargs."""
  def __init__(self, **kwargs):
    vars(self).update(**kwargs)


def to_xml(value):
  """Renders a dict (usually from JSON) as an XML snippet."""
  if isinstance(value, dict):
    if not value:
      return ''
    elems = []
    for key, vals in value.iteritems():
      if not isinstance(vals, (list, tuple)):
        vals = [vals]
      elems.extend(u'<%s>%s</%s>' % (key, to_xml(val), key) for val in vals)
    return '\n' + '\n'.join(elems) + '\n'
  else:
    if value is None:
      value = ''
    return unicode(value)


def trim_nulls(value):
  """Recursively removes dict and list elements with None or empty values."""
  NULLS = (None, {}, [], (), '')

  if isinstance(value, dict):
    trimmed = {k: trim_nulls(v) for k, v in value.items()}
    return {k: v for k, v in trimmed.items() if v not in NULLS}
  elif isinstance(value, list):
    trimmed = [trim_nulls(v) for v in value]
    return [v for v in trimmed if v if v not in NULLS]
  else:
    return value


def tag_uri(domain, name):
  """Returns a tag URI string for the given domain and name.

  Example return value: 'tag:twitter.com,2012:snarfed_org/172417043893731329'

  Background on tag URIs: http://taguri.org/
  """
  return 'tag:%s,%d:%s' % (domain, datetime.datetime.now().year, name)


def parse_acct_uri(uri, hosts=None):
  """Parses acct: URIs of the form acct:user@example.com .

  Background: http://hueniverse.com/2009/08/making-the-case-for-a-new-acct-uri-scheme/

  Args:
    uri: string
    hosts: sequence of allowed hosts (usually domains). None means allow all.

  Returns: (username, host) tuple

  Raises: ValueError if the uri is invalid or the host isn't allowed.
  """
  parsed = urlparse.urlparse(uri)
  if parsed.scheme and parsed.scheme != 'acct':
    raise ValueError('Acct URI %s has unsupported scheme: %s' %
                     (uri, parsed.scheme))

  try:
    username, host = parsed.path.split('@')
    assert username, host
  except ValueError, AssertionError:
    raise ValueError('Bad acct URI: %s' % uri)

  if hosts is not None and host not in hosts:
    raise ValueError('Acct URI %s has unsupported host %s; expected %r.' %
                     (uri, host, hosts))

  return username, host


def favicon_for_url(url):
  return 'http://%s/favicon.ico' % urlparse.urlparse(url).netloc


def domain_from_link(url):
  parsed = urlparse.urlparse(url)
  if not parsed.netloc:
    parsed = urlparse.urlparse('http://' + url)

  domain = parsed.netloc
  if not domain:
    logging.error('domain_from_link: No domain found in %r', url)
    return None

  # strip exactly one dot from the right, if present
  if domain[-1:] == ".":
    domain = domain[:-1]

  # http://stackoverflow.com/questions/2532053/validate-hostname-string-in-python
  allowed = re.compile('(?!-)[A-Z\d-]{1,63}(?<!-)$', re.IGNORECASE)
  split = domain.split('.')
  for part in split:
    if not allowed.match(part):
      logging.error('domain_from_link: Bad component in domain: %r', part)
      return None

  return domain


def linkify(text):
  """Adds HTML links to URLs in the given plain text.

  For example: linkify("Hello http://tornadoweb.org!") would return
  Hello <a href="http://tornadoweb.org">http://tornadoweb.org</a>!

  Ignores URLs that are inside HTML links, ie anchor tags that look like
  <a href="..."> .

  Based on https://github.com/silas/huck/blob/master/huck/utils.py#L59

  TODO: this blows up on some URLs with underscores in query params.
  """
  # Huck: "I originally used the regex from
  # http://daringfireball.net/2010/07/improved_regex_for_matching_urls
  # but it gets all exponential on certain patterns (such as too many trailing
  # dots), causing the regex matcher to never return. This regex should avoid
  # those problems."
  _URL_RE = re.compile(ur"""
(?<! href=["'])  # negative lookahead for beginning of HTML anchor tag
\b((?:([\w-]+):(/{1,3})|www[.])(?:(?:(?:[^\s&()]|&amp;|&quo
t;)*(?:[^!"#$%&'()*+,.:;<=>?@\[\]^`{|}~\s]))|(?:\((?:[^\s&()]|&amp;|&quot;)*\)))+)
(?![^<>]*>)  # negative lookahead for end of HTML anchor tag
""", re.VERBOSE)

  def make_link(m):
    url = m.group(1)
    proto = m.group(2)
    href = m.group(1)
    if not proto:
      href = 'http://' + href
    return u'<a href="%s">%s</a>' % (href, url)

  return _URL_RE.sub(make_link, text)


class SimpleTzinfo(datetime.tzinfo):
  """A simple, DST-unaware tzinfo subclass.
  """

  offset = datetime.timedelta(0)

  def utcoffset(self, dt):
    return self.offset

  def dst(self, dt):
    return datetime.timedelta(0)


def parse_iso8601(str):
  """Parses an ISO 8601 or RFC 3339 date/time string and returns a datetime.

  Time zone designator is optional. If present, the returned datetime will be
  time zone aware.

  Args:
    str: string ISO 8601 or RFC 3339, e.g. '2012-07-23T05:54:49+0000'

  Returns: datetime
  """
  # grr, this would be way easier if strptime supported %z, but evidently that
  # was only added in python 3.2.
  # http://stackoverflow.com/questions/9959778/is-there-a-wildcard-format-directive-for-strptime
  try:
    base, zone = re.match('(.{19})([+-]\d{2}:?\d{2})?', str).groups()
  except AttributeError, e:
    raise ValueError(e)

  tz = None
  if zone:
    zone = zone.replace(':', '')
    tz = SimpleTzinfo()
    tz.offset = (datetime.datetime.strptime(zone[1:], '%H%M') -
                 datetime.datetime.strptime('', ''))
    if zone[0] == '-':
      tz.offset = -tz.offset

  return datetime.datetime.strptime(base, '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz)


def maybe_iso8601_to_rfc3339(input):
  """Tries to convert an ISO 8601 date/time string to RFC 3339.

  The formats are similar, but not identical, eg. RFC 3339 includes a colon in
  the timezone offset at the end (+0000 instead of +00:00), but ISO 8601
  doesn't.

  If the input can't be parsed as ISO 8601, it's silently returned, unchanged!

  http://www.rfc-editor.org/rfc/rfc3339.txt
  """
  try:
    return parse_iso8601(input).isoformat('T')
  except (ValueError, TypeError):
    return input


def maybe_timestamp_to_rfc3339(input):
  """Tries to convert a string or int UNIX timestamp to RFC 3339."""
  try:
    return datetime.datetime.fromtimestamp(int(input)).isoformat('T')
  except (ValueError, TypeError):
    return input


def ellipsize(str, limit=20):
  """Truncates and ellipsizes str if it's longer than limit.
  """
  assert limit > 3
  return str if len(str) <= limit else str[:limit-3] + '...'


def add_query_params(url, params):
  """Adds new query parameters to a URL.

  Args:
    url: string URL. May already have query parameters.
    params: list of (string key, string value) tuples. Keys may repeat.

  Returns: string URL
  """
  # convert to list so we can modify later
  parsed = list(urlparse.urlparse(url))
  # query params are in index 4
  params = urlparse.parse_qsl(parsed[4]) + params
  parsed[4] = urllib.urlencode(params)
  return urlparse.urlunparse(parsed)
