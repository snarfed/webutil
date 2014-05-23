"""Misc utilities.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import base64
import datetime
import logging
import os
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
  NULLS = (None, {}, [], (), '', set(), frozenset())

  if isinstance(value, dict):
    trimmed = {k: trim_nulls(v) for k, v in value.items()}
    return {k: v for k, v in trimmed.items() if v not in NULLS}
  elif isinstance(value, (tuple, list, set, frozenset)):
    trimmed = [trim_nulls(v) for v in value]
    return type(value)([v for v in trimmed if v if v not in NULLS])
  else:
    return value


def tag_uri(domain, name, year=None):
  """Returns a tag URI string for the given domain and name.

  Example return value: 'tag:twitter.com,2012:snarfed_org/172417043893731329'

  Background on tag URIs: http://taguri.org/
  """
  if year is not None:
    year = ',%s' % year
  else:
    year = ''
  return 'tag:%s%s:%s' % (domain, year, name)


_TAG_URI_RE = re.compile('tag:([^,]+)(?:,\d+)?:(.+)$')

def parse_tag_uri(uri):
  """Returns the domain and name in a tag URI string.

  Inverse of tag_uri().

  Returns: (string domain, string name) tuple, or None if the tag URI couldn't
    be parsed
  """
  match = _TAG_URI_RE.match(uri)
  return match.groups() if match else None


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


# http://stackoverflow.com/questions/2532053/validate-hostname-string-in-python
HOSTNAME_RE_STR = r'%s(\.%s)*\.?' % ((r'(?!-)[A-Za-z\d-]{1,63}(?<!-)',) * 2)
HOSTNAME_RE = re.compile(HOSTNAME_RE_STR + '$')

def domain_from_link(url):
  parsed = urlparse.urlparse(url)
  if not parsed.netloc:
    parsed = urlparse.urlparse('http://' + url)

  domain = parsed.netloc
  if domain.startswith('www.'):
    domain = domain[4:]
  if domain and HOSTNAME_RE.match(domain):
    return domain

  logging.error('domain_from_link: Invalid domain in %r', url)
  return None


def update_scheme(url, handler):
  """Returns a modified string url with the current request's scheme.

  Useful for converting URLs to https if and only if the current request itself
  is being served over https.
  """
  # Instagram can't serve images over SSL, so switch to their S3 URL, which can.
  # https://groups.google.com/d/msg/instagram-api-developers/fB4mwYXZF1c/q9n9gPO11JQJ
  url = re.sub('^http://images\.(ak\.)instagram\.com',
               'http://distillery.s3.amazonaws.com', url)
  return urlparse.urlunparse([handler.request.scheme] +
                             list(urlparse.urlparse(url)[1:]))


_LINK_RE = re.compile(ur'\bhttps?://[^\s<>]+\b')
# more complicated alternative:
# http://stackoverflow.com/questions/720113#comment23297770_2102648

def extract_links(text):
  """Returns a set of string URLs in the given text.
  """
  return set(match.group() for match in _LINK_RE.finditer(text))


_LINKIFY_RE = re.compile(ur"""
(?<! href=["'])  # negative lookahead for beginning of HTML anchor tag
\b((?:([\w-]+):(/{1,3})|www[.])(?:(?:(?:[^\s&()]|&amp;|&quo
t;)*(?:[^!"#$%&'()*+,.:;<=>?@\[\]^`{|}~\s]))|(?:\((?:[^\s&()]|&amp;|&quot;)*\)))+)
(?![^<>]*>)  # negative lookahead for end of HTML anchor tag
""", re.VERBOSE)

def linkify(text, pretty=False, **kwargs):
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
  def make_link(m):
    url = m.group(1)
    proto = m.group(2)
    href = m.group(1)
    if not proto:
      href = 'http://' + href
    if pretty:
      return pretty_link(href, **kwargs)
    else:
      return u'<a href="%s">%s</a>' % (href, url)

  return _LINKIFY_RE.sub(make_link, text)


def pretty_link(url, text=None, keep_host=True, glyphicon=None, a_class=None,
                new_tab=False, max_length=None):
  """Renders a pretty, short HTML link to a URL.

  In the the link text, Removes the leading http(s)://[www.] and ellipsizes at
  the end if necessary.

  The default maximum length follow's Twitter's rules: full domain plus 15
  characters of path (including leading slash).
  https://dev.twitter.com/docs/tco-link-wrapper/faq
  https://dev.twitter.com/docs/counting-characters

  Args:
    url: string
    text: string, optional
    keep_host: if False, remove the host from the link text
    glyphicon: string glyphicon to render after the link text, if provided.
      Details: http://glyphicons.com/
    new_tab: boolean, include target="_blank" if True
    class: string, included in a tag if provided
    max_length: int, max link text length in characters. ellipsized beyond this.
  """
  if text:
    if max_length is None:
      max_length = 30
  else:
    # use shortened version of URL as link text
    parsed = urlparse.urlparse(url)
    text = url[len(parsed.scheme) + 3:]  # strip scheme and ://
    host_len = len(parsed.netloc)
    if not keep_host:
      text = text[host_len + 1:]
      host_len = 0
    if text.startswith('www.'):
      text = text[4:]
      host_len -= 4
    if max_length is None:
      max_length = host_len + 15

  if max_length and len(text) > max_length:
    text = text[:max_length] + '...'

  if glyphicon is not None:
    text += ' <span class="glyphicon glyphicon-%s"></span>' % glyphicon
  cls = 'class="%s" ' % a_class if a_class else ''
  target = 'target="_blank" ' if new_tab else ''
  return ('<a %s%shref="%s">%s</a>' % (cls, target, url, text))


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
    str: string ISO 8601 or RFC 3339, e.g. '2012-07-23T05:54:49+00:00'

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


def ellipsize(str, words=14, chars=140):
  """Truncates and ellipsizes str if it's longer than words or chars.

  Words are simply tokenized on whitespace, nothing smart.
  """
  split = str.split()
  if len(split) <= words and len(str) <= chars:
    return str
  return ' '.join(split[:words])[:chars-3] + '...'


def add_query_params(url, params):
  """Adds new query parameters to a URL. Encodes as UTF-8 and URL-safe.

  Args:
    url: string URL. May already have query parameters.
    params: dict or list of (string key, string value) tuples. Keys may repeat.

  Returns: string URL
  """
  if isinstance(params, dict):
    params = params.items()

  # convert to list so we can modify later
  parsed = list(urlparse.urlparse(url))
  # query params are in index 4
  params = set((k, unicode(v).encode('utf-8')) for k, v in params)
  parsed[4] += ('&' if parsed[4] else '') + urllib.urlencode(list(params))
  return urlparse.urlunparse(parsed)


def get_required_param(handler, name):
  val = handler.request.get(name)
  if not val:
    handler.abort(400, 'Missing required parameter: %s' % name)
  return val


def if_changed(cache, updates, key, value):
  """Returns a value if it's different from the cached value, otherwise None.

  Values that evaluate to False are considered equivalent to None, in order to
  save cache space.

  If the values differ, updates[key] is set to value. You can use this to
  collect changes that should be made to the cache in batch. None values in
  updates mean that the corresponding key should be deleted.

  Args:
    cache: any object with a get(key) method
    updates: mapping (e.g. dict)
    key: anything supported by cache
    value: anything supported by cache

  Returns: value or None
  """
  if cache is None:
    return value
  cached = cache.get(key)

  # normalize to None
  if not value:
    value = None
  if not cached:
    cached = None

  if value == cached:
    return None

  updates[key] = value
  return value


def generate_secret():
  """Generates a URL-safe random secret string.

  Uses App Engine's os.urandom(), which is designed to be cryptographically
  secure: http://code.google.com/p/googleappengine/issues/detail?id=1055

  Args:
    bytes: integer, length of string to generate

  Returns: random string
  """
  return base64.urlsafe_b64encode(os.urandom(16))
