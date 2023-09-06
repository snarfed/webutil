"""Misc utilities.

Should not depend on App Engine API or SDK packages.
"""
import base64
import calendar
import collections
from collections.abc import Iterator
import contextlib
from datetime import datetime, timedelta, timezone
import http.client
import humanize
import inspect
import logging
import mimetypes
import numbers
import os
import re
import socket
import ssl
import string
import sys
import threading
import traceback
import urllib.error, urllib.parse, urllib.request
from urllib.parse import urlparse
from xml.sax import saxutils

from cachetools import cached, TTLCache
from domain2idna import domain2idna
from flask import abort

try:
  import ujson
  json = ujson
except ImportError:
  ujson = None
  import json

# These are used in interpret_http_exception() and is_connection_failure(). They
# use dependencies that we may or may not have, so degrade gracefully if they're
# not available.
try:
  import apiclient
  import apiclient.errors
except ImportError:
  apiclient = None

try:
  from oauth2client.client import AccessTokenRefreshError
except ImportError:
  AccessTokenRefreshError = None

try:
  import requests
except ImportError:
  requests = None

try:
  import urllib3
except ImportError:
  if requests:
    try:
      from requests.packages import urllib3
    except ImportError:
      urllib3 = None

try:
  import webob
  from webob import exc
  # webob doesn't know about HTTP 429 for rate limiting. Tell it.
  try:
    webob.util.status_reasons[429] = 'Rate limited'  # webob <= 0.9
  except AttributeError:
    webob.status_reasons[429] = 'Rate limited'  # webob >= 1.1.1
except ImportError:
  exc = None

try:
  import werkzeug
  import werkzeug.exceptions
except ImportError:
  werkzeug = None

# Used in parse_html() and friends.
try:
  import bs4
except ImportError:
  bs4 = None

try:
  import mf2py
except ImportError:
  mf2py = None

try:
  import prawcore
except ImportError:
  prawcore = None

try:
  import tumblpy
except ImportError:
  tumblpy = None

try:
  import tweepy
except ImportError:
  tweepy = None

logger = logging.getLogger(__name__)

user_agent = 'webutil (https://github.com/snarfed/webutil)'
"""Set with :func:`set_user_agent`."""

EPOCH = datetime.fromtimestamp(0, timezone.utc)
EPOCH_ISO = EPOCH.isoformat()
# from https://stackoverflow.com/a/53140944/186123
ISO8601_DURATION_RE = re.compile(
  r'^ *P(?!$)(\d+Y)?(\d+M)?(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)? *$')

HTTP_TIMEOUT = 15  # seconds
"""Default HTTP request timeout, used in :func:`requests_get` etc."""
socket.setdefaulttimeout(HTTP_TIMEOUT)
# monkey-patch socket.getdefaulttimeout() because it often gets reset, e.g. by
# socket.setblocking() and maybe other operations.
# http://stackoverflow.com/a/8465202/186123
socket.getdefaulttimeout = lambda: HTTP_TIMEOUT

MAX_HTTP_RESPONSE_SIZE = 2000000  # 2MB
"""Average HTML size as of 2015-10-15 is 56K, so this is generous and conservative.
Raised from 1MB to 2MB on 2023-07-07.
http://www.sitepoint.com/average-page-weight-increases-15-2014/
http://httparchive.org/interesting.php#bytesperpage
"""
HTTP_RESPONSE_TOO_BIG_STATUS_CODE = 422  # Unprocessable Entity

FOLLOW_REDIRECTS_CACHE_TIME = 60 * 60 * 24  # 1d expiration
follow_redirects_cache = TTLCache(1000, FOLLOW_REDIRECTS_CACHE_TIME)
follow_redirects_cache_lock = threading.RLock()

# https://en.wikipedia.org/wiki/Top-level_domain#Reserved_domains
# Currently used in granary.source.Source.original_post_discovery, not here.
RESERVED_TLDS = {
  'corp',
  'example',
  'internal',
  'invalid',
  'onion',
  'test',
}
LOCAL_TLDS = {
  'local',
  'localhost',
}

now = lambda tz=timezone.utc, **kwargs: datetime.now(tz=tz, **kwargs)
"""Alias, allows unit tests to mock the function."""

beautifulsoup_parser = None
"""Global config, string parser for BeautifulSoup to use, e.g. 'lxml'.
May be set at runtime.
https://www.crummy.com/software/BeautifulSoup/bs4/doc/#installing-a-parser
"""

# Regexps for domains, hostnames, and URLs.
#
# Based on kylewm's from redwind:
# https://github.com/snarfed/bridgy/issues/209#issuecomment-47583528
# https://github.com/kylewm/redwind/blob/863989d48b97a85a1c1a92c6d79753d2fbb70775/redwind/util.py#L39
#
# I used to use a more complicated regexp based on
# https://github.com/silas/huck/blob/master/huck/utils.py#L59 , but i kept
# finding new input strings that would make it hang the regexp engine.
#
# more complicated alternatives:
# http://stackoverflow.com/questions/720113#comment23297770_2102648
# https://daringfireball.net/2010/07/improved_regex_for_matching_urls
#
# list of TLDs:
# https://en.wikipedia.org/wiki/List_of_Internet_top-level_domains#ICANN-era_generic_top-level_domains
#
# Allows emoji and other unicode chars in all domain labels *except* TLDs.
# TODO: support IDN TLDs:
# https://en.wikipedia.org/wiki/Top-level_domain#Internationalized_country_code_TLDs
# https://www.iana.org/domains/root/db
#
# TODO: fix bug in LINK_RE that makes it miss emoji domain links without scheme,
# eg '☕⊙.ws'. bug is that the \b at the beginning of SCHEME_RE doesn't apply to
# emoji, since they're not word-constituent characters, and that the '?' added
# in LINK_RE only applies to the parenthesized group in SCHEME_RE, not the \b.
# I tried changing \b to '(?:^|[\s%s])' % PUNCT, but that broke other things.
PUNCT = string.punctuation.replace('-', '').replace('.', '')
SCHEME_RE = r'\b(?:[a-z]{3,9}:/{1,3})'
HOST_RE = r'(?:[^\s%s])+(?::\d{2,6})?' % PUNCT
DOMAIN_RE = r'(?:[^\s.%s]+\.)+[a-z]{2,}(?::\d{2,6})?' % PUNCT
PATH_QUERY_RE = r'(?:(?:/[\w/.\-_~.;:%?@$#&()=+]*)|\b)'
URL_RE = re.compile(SCHEME_RE + HOST_RE + PATH_QUERY_RE,  # scheme required
                    re.UNICODE | re.IGNORECASE)
LINK_RE = re.compile(SCHEME_RE + '?' + DOMAIN_RE + PATH_QUERY_RE,  # scheme optional
                     re.UNICODE | re.IGNORECASE)


class Struct(object):
  """A generic class that initializes its attributes from constructor kwargs."""
  def __init__(self, **kwargs):
    vars(self).update(**kwargs)


class CacheDict(dict):
  """A dict that also implements memcache's get_multi() and set_multi() methods.

  Useful as a simple in memory replacement for App Engine's memcache API for
  e.g. get_activities_response() in granary.
  """
  def get_multi(self, keys):
    keys = set(keys)
    return {k: v for k, v in list(self.items()) if k in keys}

  def set(self, key, val, **kwargs):
    self[key] = val

  def set_multi(self, updates, **kwargs):
    super(CacheDict, self).update(updates)


def to_xml(value):
  """Renders a dict (usually from JSON) as an XML snippet."""
  if isinstance(value, dict):
    if not value:
      return ''
    elems = []
    for key, vals in sorted(value.items()):
      if not isinstance(vals, (list, tuple)):
        vals = [vals]
      elems.extend(f'<{key}>{to_xml(val)}</{key}>' for val in vals)
    return '\n' + '\n'.join(elems) + '\n'
  else:
    if value is None:
      value = ''
    return str(value)


def trim_nulls(value, ignore=()):
  """Recursively removes dict and list elements with None or empty values.

  Args:
    value: dict or list
    ignore: optional sequence of keys to allow to have None/empty values.
      Transitive: ignored keys' *entire contents* are ignored and allowed to
      have nulls, all the way down!
  """
  NULLS = (None, {}, [], (), '', set(), frozenset())

  if isinstance(value, dict):
    trimmed = {k: (v if k in ignore else trim_nulls(v, ignore=ignore))
               for k, v in value.items()}
    return {k: v for k, v in trimmed.items() if k in ignore or v not in NULLS}
  elif (isinstance(value, (tuple, list, set, frozenset, Iterator)) or
        inspect.isgenerator(value)):
    trimmed = [trim_nulls(v, ignore=ignore) for v in value]
    ret = (v for v in trimmed if v not in NULLS)
    if isinstance(value, Iterator) or inspect.isgenerator(value):
      return ret
    else:
      return type(value)(list(ret))
  else:
    return value


def uniquify(input):
  """Returns a list with duplicate items removed.

  Like list(set(...)), but preserves order.
  """
  if not input:
    return []
  return list(collections.OrderedDict([x, 0] for x in input).keys())


def get_list(obj, key):
  """Returns a value from a dict as a list.

  If the value is a list or tuple, it's converted to a list. If it's something
  else, it's returned as a single-element list. If the key doesn't exist,
  returns [].
  """
  val = obj.get(key, [])
  return (list(val) if isinstance(val, (list, tuple, set))
          else [val] if val
          else [])


def pop_list(obj, key):
  """Like get_list(), but also removes the item."""
  val = get_list(obj, key)
  obj.pop(key, None)
  return val


def encode(obj, encoding='utf-8'):
  """Character encodes all unicode strings in a collection, recursively.

  Args:
    obj: list, tuple, dict, set, or primitive
    encoding: string character encoding

  Returns:
    sequence or dict version of obj with all unicode strings encoded
  """
  if isinstance(obj, str):
    return obj.encode(encoding)
  elif isinstance(obj, tuple):
    return tuple(encode(v) for v in obj)
  elif isinstance(obj, list):
    return [encode(v) for v in obj]
  elif isinstance(obj, set):
    return {encode(v) for v in obj}
  elif isinstance(obj, dict):
    return {encode(k): encode(v) for k, v in obj.items()}
  else:
    return obj


def get_first(obj, key, default=None):
  """Returns the first element of a dict value.

  If the value is a list or tuple, returns the first value. If it's something
  else, returns the value itself. If the key doesn't exist, returns None.
  """
  val = obj.get(key)
  if not val:
    return default
  return val[0] if isinstance(val, (list, tuple)) else val


def get_url(val, key=None):
  """Returns val['url'] if val is a dict, otherwise val.

  If key is not None, looks in val[key] instead of val.
  """
  if key is not None:
    val = get_first(val, key)
  return get_first(val, 'url') if isinstance(val, dict) else val


def get_urls(obj, key, inner_key=None):
  """Returns elem['url'] if dict, otherwise elem, for each elem in obj[key].

  If inner_key is provided, the returned values are elem[inner_key]['url'].
  """
  return dedupe_urls(get_url(elem, key=inner_key) for elem in get_list(obj, key))


def tag_uri(domain, name, year=None):
  """Returns a tag URI string for the given domain and name.

  Example return value: 'tag:twitter.com,2012:snarfed_org/172417043893731329'

  Background on tag URIs: http://taguri.org/
  """
  year = f',{year}' if year else ''
  return f'tag:{domain}{year}:{name}'


_TAG_URI_RE = re.compile(r'tag:([^,]+)(?:,\d+)?:(.+)$')

def parse_tag_uri(uri):
  """Returns the domain and name in a tag URI string.

  Inverse of :func:`tag_uri()`.

  Returns:
    (string domain, string name) tuple, or None if the tag URI couldn't
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

  Returns:
    (username, host) tuple

  Raises: ValueError if the uri is invalid or the host isn't allowed.
  """
  parsed = urlparse(uri)
  if parsed.scheme and parsed.scheme != 'acct':
    raise ValueError(f'Acct URI {uri} has unsupported scheme: {parsed.scheme}')

  try:
    username, host = parsed.path.strip('@').split('@')
    assert host
  except (ValueError, AssertionError):
    raise ValueError(f'Bad acct URI: {uri}')

  if hosts is not None and host not in hosts:
    raise ValueError(f'Acct URI {uri} has unsupported host {host}; expected {hosts!r}.')

  return username, host


def favicon_for_url(url):
  return f'http://{urlparse(url).netloc}/favicon.ico'


FULL_HOST_RE = re.compile(HOST_RE + '$')

def domain_from_link(url, minimize=True):
  """Extracts and returns the meaningful domain from a URL.

  Args:
    url: string
    minimize: bool; if true, strips www., mobile., and m. subdomains from the
      beginning of the domain

  Returns:
    str, or None if url is None or blank
  """
  if not url:
    return None

  try:
    parsed = urlparse(url)
    if not parsed.hostname and '//' not in url:
      parsed = urlparse('http://' + url)
  except ValueError:
    return None

  domain = parsed.hostname
  if domain and minimize:
    for subdomain in ('www.', 'mobile.', 'm.'):
      if domain.startswith(subdomain):
        domain = domain[len(subdomain):]

  if domain and FULL_HOST_RE.match(domain):
    return domain

  return None


def domain_or_parent_in(input, domains):
  """Returns True if an input domain or its parent is in a set of domains.

  Examples:

  * foo, [] => False
  * foo, [foo] => True
  * foo.bar.com, [bar.com] => True
  * foobar.com, [bar.com] => False
  * foo.bar.com, [.bar.com] => True
  * foo.bar.com, [fux.bar.com] => False
  * bar.com, [fux.bar.com] => False

  Args:
    input: string domain
    domains: sequence of string domains

  Returns:
    boolean
  """
  if not input or not domains:
    return False
  elif input in domains:
    return True

  for domain in domains:
    if not domain.startswith('.'):
      domain = '.' + domain
    if input.endswith(domain):
      return True

  return False


def update_scheme(url, request):
  """Returns a modified URL with the scheme upgraded to https if the
  request uses https.

  Useful for converting URLs to https if and only if the current request itself
  is being served over https.

  Args:
    url: string
    request: :class:`flask.Request` or :class:`webob.Request`

  Returns: string, url
  """
  if request.scheme == 'https':
    return urllib.parse.urlunparse((request.scheme,) + urlparse(url)[1:])
  return url


def schemeless(url, slashes=True):
  """Strips the scheme (e.g. 'https:') from a URL.

  Args:
    url: string
    slashes: if False, also strips leading slashes and trailing slash,
      e.g. 'http://example.com/' becomes 'example.com'

  Returns:
    string URL
  """
  url = urllib.parse.urlunparse(('',) + urlparse(url)[1:])
  if not slashes:
    url = url.strip('/')
  return url


def fragmentless(url):
  """Strips the fragment (e.g. '#foo') from a URL.

  Args:
    url: string

  Returns:
    string URL
  """
  return urllib.parse.urlunparse(urlparse(url)[:5] + ('',))


def clean_url(url):
  """Removes transient query params (e.g. utm_*) from a URL.

  The utm_* (Urchin Tracking Metrics?) params come from Google Analytics.
  https://support.google.com/analytics/answer/1033867

  The source=rss-... params are on all links in Medium's RSS feeds.

  Args:
    url: string

  Returns:
    string, the cleaned url, or None if it can't be parsed
  """
  if not url:
    return url

  utm_params = set(('utm_campaign', 'utm_content', 'utm_medium', 'utm_source',
                    'utm_term'))
  try:
    parts = list(urlparse(url))
  except (AttributeError, TypeError, ValueError):
    return None

  query = urllib.parse.unquote_plus(parts[4])
  params = [(name, value) for name, value in urllib.parse.parse_qsl(query)
            if name not in utm_params
            and not (name == 'source' and value.startswith('rss-'))]
  parts[4] = urllib.parse.urlencode(params)
  return urllib.parse.urlunparse(parts)


def quote_path(url):
  """Quotes (URL-encodes) just the path part of a URL.

  Args:
    url: string

  Returns:
    string, the quoted url, or None if it can't be parsed
  """
  try:
    parts = list(urlparse(url))
  except (AttributeError, TypeError, ValueError):
    return None

  parts[2] = urllib.parse.quote(parts[2])
  return urllib.parse.urlunparse(parts)


def base_url(url):
  """Returns the base of a given URL.

  For example, returns 'http://site/posts/' for 'http://site/posts/123'.

  Args:
    url: string
  """
  return urllib.parse.urljoin(url, 'x')[:-1] if url else None


def is_web(url):
  """Returns True if the argument is an http or https URL, False otherwise."""
  return isinstance(url, str) and (url.startswith('http://') or
                                   url.startswith('https://'))


def extract_links(text):
  """Returns a list of unique string URLs in the given text.

  URLs in the returned list are in the order they first appear in the text.
  """
  if not text:
    return []

  return uniquify(tokenize_links(text, skip_html_links=False, require_scheme=True)[0])


def tokenize_links(text, skip_bare_cc_tlds=False, skip_html_links=True,
                   require_scheme=False):
  """Splits text into link and non-link text.

  Args:
    text: string to linkify
    skip_bare_cc_tlds: boolean, whether to skip links of the form
      [domain].[2-letter TLD] with no schema and no path
    skip_html_links: boolean, whether to skip links in HTML <a> tags (
      both href and text)
    require_scheme: boolean, whether to require scheme (eg http:// )

  Returns:
    a tuple containing two lists of strings, a list of links and list of
    non-link text. Roughly equivalent to the output of re.findall and re.split,
    with some post-processing.
  """
  regexp = URL_RE if require_scheme else LINK_RE
  links = regexp.findall(text)
  splits = regexp.split(text)

  for ii in range(len(links)):
    # trim trailing punctuation from links
    link = links[ii]
    jj = len(link) - 1
    while (jj >= 0 and link[jj] in '.!?,;:)'
           # allow 1 () pair
           and (link[jj] != ')' or '(' not in link)):
      jj -= 1
      links[ii] = link[:jj + 1]
      splits[ii + 1] = link[jj + 1:] + splits[ii + 1]

    link = links[ii]

    # avoid double linking by looking at preceeding 2 chars
    if ((skip_html_links and (splits[ii].strip().endswith('="')
                              or splits[ii].strip().endswith("='")
                              or splits[ii + 1].strip().startswith('</a')))
        # skip domains with 2-letter TLDs and no schema or path
        or (skip_bare_cc_tlds and re.match(r'[^\s%s]+\.[a-z]{2}$' % PUNCT, link))):
      # collapse link into before text
      splits[ii] = splits[ii] + links[ii]
      links[ii] = None
      continue

  # clean up the output by collapsing removed links
  ii = len(links) - 1
  while ii >= 0:
    if links[ii] is None:
      splits[ii] = splits[ii] + splits[ii + 1]
      del links[ii]
      del splits[ii + 1]
    ii -= 1

  return links, splits


def linkify(text, pretty=False, skip_bare_cc_tlds=False, **kwargs):
  """Adds HTML links to URLs in the given plain text.

  For example: ``linkify('Hello http://tornadoweb.org!')`` would return
  'Hello <a href="http://tornadoweb.org">http://tornadoweb.org</a>!'

  Ignores URLs that are inside HTML links, ie anchor tags that look like
  <a href="..."> .

  Args:
    text: string, input
    pretty: if True, uses :func:`pretty_link()` for link text
    skip_bare_cc_tlds: boolean, whether to skip links of the form
      [domain].[2-letter TLD] with no schema and no path

  Returns:
    string, linkified input
  """

  links, splits = tokenize_links(text, skip_bare_cc_tlds)
  result = []

  for ii in range(len(links)):
    result.append(splits[ii])

    url = href = links[ii]
    if not href.startswith('http://') and not href.startswith('https://'):
      href = 'http://' + href

    if pretty:
      result.append(pretty_link(href, **kwargs))
    else:
      result.append(f'<a href="{href}">{url}</a>')
  result.append(splits[-1])
  return ''.join(result)


def pretty_link(url, text=None, text_prefix=None, keep_host=True,
                glyphicon=None, attrs=None, new_tab=False, max_length=None):
  """Renders a pretty, short HTML link to a URL.

  If text is not provided, the link text is the URL without the leading
  http(s)://[www.], ellipsized at the end if necessary. URL escape characters
  and UTF-8 are decoded.

  The default maximum length follow's Twitter's rules: full domain plus 15
  characters of path (including leading slash).

  * https://dev.twitter.com/docs/tco-link-wrapper/faq
  * https://dev.twitter.com/docs/counting-characters

  Args:
    url: string
    text: string, optional
    text_prefix: string, optional, added to beginning of text
    keep_host: if False, remove the host from the link text
    glyphicon: string glyphicon to render after the link text, if provided.
      Details: http://glyphicons.com/
    attrs: dict of attributes => values to include in the a tag. optional
    new_tab: boolean, include target="_blank" if True
    max_length: int, max link text length in characters. ellipsized beyond this.

  Returns:
    unicode string HTML snippet with <a> tag
  """
  if text:
    if max_length is None:
      max_length = 30
  else:
    # use shortened version of URL as link text
    parsed = urlparse(url)
    text = url.removeprefix(parsed.scheme + '://')
    host_len = len(parsed.netloc)
    if (keep_host and not parsed.params and not parsed.query and not parsed.fragment):
      text = text.strip('/')  # drop trailing slash
    elif not keep_host:
      text = text[host_len + 1:]
      host_len = 0
    if text.startswith('www.'):
      text = text[4:]
      host_len -= 4
    if max_length is None:
      max_length = host_len + 15
    try:
      text = urllib.parse.unquote_plus(str(text))
    except ValueError:
      pass

  full_text = text
  if max_length and len(text) > max_length:
    text = text[:max_length] + '...'

  escaped_text = saxutils.escape(text)
  if text_prefix:
    escaped_text = f'{text_prefix} {escaped_text}'
  if glyphicon is not None:
    escaped_text += f' <span class="glyphicon glyphicon-{glyphicon}"></span>'

  attr_str = (''.join(f'{attr}="{val}" ' for attr, val in list(attrs.items()))
              if attrs else '')
  target = 'target="_blank" ' if new_tab else ''
  return ('<a %s%s%shref="%s">%s</a>' %
          (f'title="{full_text}" ' if text.endswith('...') else '',
           attr_str, target,
           # not using urllib.parse.quote because it quotes a ton of chars we
           # want to pass through, including most unicode chars
           url.replace('<', '%3C').replace('>', '%3E'),
           escaped_text))


TIMEZONE_OFFSET_RE = re.compile(r'[+-]\d{2}:?\d{2}$')

def parse_iso8601(val):
  """Parses an ISO 8601 or RFC 3339 date/time string and returns a datetime.

  Time zone designator is optional. If present, the returned datetime will be
  time zone aware.

  Args:
    val: string ISO 8601 or RFC 3339, e.g. '2012-07-23T05:54:49+00:00'

  Returns:
    datetime
  """
  # grr, this would be way easier if strptime supported %z, but evidently that
  # was only added in python 3.2.
  # http://stackoverflow.com/questions/9959778/is-there-a-wildcard-format-directive-for-strptime
  assert val

  val = val.replace('T', ' ')
  tz = None
  zone = TIMEZONE_OFFSET_RE.search(val)

  if zone:
    offset_str = zone.group()
    val = val[:-len(offset_str)]
    offset = (datetime.strptime(offset_str[1:].replace(':', ''), '%H%M') -
              datetime.strptime('', ''))
    if offset_str[0] == '-':
      offset = -offset
    tz = timezone(offset)
  elif val[-1] == 'Z':
    val = val[:-1]
    tz = timezone.utc

  # fractional seconds are optional. add them if they're not already there to
  # make strptime parsing below easier.
  if '.' not in val:
    val += '.0'

  return datetime.strptime(val, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=tz)


def parse_iso8601_duration(input):
  """Parses an ISO 8601 duration.

  Note: converts months to 30 days each. (ISO 8601 doesn't seem to define the
  number of days in a month. Background:
  https://stackoverflow.com/a/29458514/186123 )

  Args:
    input: string ISO 8601 duration, e.g. 'P3Y6M4DT12H30M5S'

  https://en.wikipedia.org/wiki/ISO_8601#Durations

  Returns:
    :class:`datetime.timedelta`, or None if input cannot be parsed as an ISO
      8601 duration
  """
  if not input:
    return None

  match = ISO8601_DURATION_RE.match(input)
  if not match:
    return None

  def g(i):
    val = match.group(i)
    return int(val[:-1]) if val else 0

  return timedelta(weeks=g(3),
                   days=365 * g(1) + 30 * g(2) + g(4),
                   hours=g(6), minutes=g(7), seconds=g(8))


def to_iso8601_duration(input):
  """Converts a timedelta to an ISO 8601 duration.

  Returns a fairly strict format: 'PnMTnS'. Fractional seconds are silently
  dropped.

  Args:
    input: :class:`datetime.timedelta`

  https://en.wikipedia.org/wiki/ISO_8601#Durations

  Returns:
    string ISO 8601 duration, e.g. 'P3DT4S'

  Raises: :class:`TypeError` if delta is not a :class:`datetime.timedelta`
  """
  if not isinstance(input, timedelta):
    raise TypeError(f'Expected timedelta, got {input.__class__}')

  return f'P{input.days}DT{input.seconds}S'


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
  except (AssertionError, ValueError, TypeError):
    return input


def maybe_timestamp_to_rfc3339(input):
  """Tries to convert a string or int UNIX timestamp to RFC 3339.

  Assumes UNIX timestamps are always UTC. (They're generally supposed to be.)
  """
  try:
    dt = datetime.utcfromtimestamp(float(input)).replace(tzinfo=timezone.utc)
    return dt.isoformat('T', 'milliseconds' if dt.microsecond else 'seconds')
  except (ValueError, TypeError):
    return input


def maybe_timestamp_to_iso8601(input):
  """Tries to convert a string or int UNIX timestamp to ISO 8601.

  Assumes UNIX timestamps are always UTC. (They're generally supposed to be.)
  """
  ret = maybe_timestamp_to_rfc3339(input)
  return ret if ret == input else ret.replace('+00:00', 'Z')


def to_utc_timestamp(input):
  """Converts a datetime to a float POSIX timestamp (seconds since epoch)."""
  if not input:
    return None

  timetuple = list(input.timetuple())
  # timetuple() usually strips microsecond
  timetuple[5] += input.microsecond / 1000000
  return calendar.timegm(timetuple)


def as_utc(input):
  """Converts a timezone-aware datetime to a naive UTC datetime.

  If input is timezone-naive, it's returned as is.

  Doesn't support DST!
  """
  if not input.tzinfo:
    return input

  utc = input - input.tzinfo.utcoffset(None)
  return utc.replace(tzinfo=None)


def naturaltime(val, when=None, **kwargs):
  """Wrapper for humanize.naturaltime that handles timezone-aware datetimes.

  ...since humanize currently doesn't. :(
  https://github.com/python-humanize/humanize/issues/17
  """
  val = val.replace(tzinfo=None)
  if when is not None:
    when = when.replace(tzinfo=None)
  return humanize.naturaltime(val, when=when, **kwargs)


def ellipsize(str, words=14, chars=140):
  """Truncates and ellipsizes str if it's longer than words or chars.

  Words are simply tokenized on whitespace, nothing smart.
  """
  split = str.split()
  if len(split) <= words and len(str) <= chars:
    return str
  return ' '.join(split[:words])[:chars - 3] + '...'


def add_query_params(url, params):
  """Adds new query parameters to a URL. Encodes as UTF-8 and URL-safe.

  Args:
    url: string URL or :class:`urllib.request.Request`. May already have query
      parameters.
    params: dict or list of (string key, string value) tuples. Keys may repeat.

  Returns:
    string URL
  """
  is_request = isinstance(url, urllib.request.Request)
  if is_request:
    req = url
    url = req.get_full_url()

  if isinstance(params, dict):
    params = list(params.items())

  # convert to list so we can modify later
  parsed = list(urlparse(url))
  # query params are in index 4
  params = [(k, str(v).encode('utf-8')) for k, v in params]
  parsed[4] += ('&' if parsed[4] else '') + urllib.parse.urlencode(params)
  updated = urllib.parse.urlunparse(parsed)

  if is_request:
    return urllib.request.Request(updated, data=req.data, headers=req.headers)
  else:
    return updated


def remove_query_param(url, param):
  """Removes query parameter(s) from a URL. Decodes URL escapes and UTF-8.

  If the query parameter is not present in the URL, the URL is returned
  unchanged, and the returned value is None.

  If the query parameter is present multiple times, *only the last value is
  returned*.

  Args:
    url: string URL
    param: string name of query parameter to remove

  Returns:
    (string URL without the given param, string param value)
  """
  # convert to list so we can modify later
  parsed = list(urlparse(url))

  # query params are in index 4
  removed = None
  rest = []
  for name, val in urllib.parse.parse_qsl(parsed[4], keep_blank_values=True):
    if name == param:
      removed = val
    else:
      rest.append((name, val))

  parsed[4] = urllib.parse.urlencode(rest)
  url = urllib.parse.urlunparse(parsed)
  return url, removed


def dedupe_urls(urls, key=None):
  """Normalizes and de-dupes http(s) URLs.

  Converts domain to lower case, adds trailing slash when path is empty, and
  ignores scheme (http vs https), preferring https. Preserves order. Removes
  Nones and blank strings.

  Domains are case insensitive, even modern domains with Unicode/punycode
  characters:

  http://unicode.org/faq/idn.html#6
  https://tools.ietf.org/html/rfc4343#section-5

  As examples, http://foo/ and https://FOO are considered duplicates, but
  http://foo/bar and http://foo/bar/ aren't.

  Background: https://en.wikipedia.org/wiki/URL_normalization

  Args:
    urls: sequence of string URLs or dict objects with 'url' keys
    key: if not None, an inner key to be dereferenced in a dict object before
      looking for the 'url' key

  Returns:
    sequence of string URLs
  """
  seen = set()
  result = []

  for obj in urls:
    url = get_url(obj, key=key)
    if not url:
      continue

    p = urllib.parse.urlsplit(url)
    # normalize domain and path
    # (the hostname param is automatically lower cased, but we can't use it
    # because it doesn't include port)
    norm = [p.scheme, p.netloc.lower(), p.path or '/', p.query, p.fragment]

    if p.scheme == 'http' and urllib.parse.urlunsplit(['https'] + norm[1:]) in result:
      continue
    elif p.scheme == 'https':
      try:
        result.remove(urllib.parse.urlunsplit(['http'] + norm[1:]))
      except ValueError:
        pass

    url = urllib.parse.urlunsplit(norm)
    if url not in seen:
      seen.add(url)
      if isinstance(obj, dict):
        val = obj if key is None else get_first(obj, key)
        val['url'] = url
      else:
        obj = url
      result.append(obj)

  return result


def encode_oauth_state(obj):
  """The state parameter is passed to various source authorization
  endpoints and returned in a callback. This encodes a JSON object
  so that it can be safely included as a query string parameter.

  Args:
    obj: a JSON-serializable dict

  Returns:
    a string
  """
  if not isinstance(obj, dict):
    raise TypeError(f'Expected dict, got {obj.__class__}')

  logger.debug(f'encoding state {obj!r}')
  return urllib.parse.quote_plus(json_dumps(trim_nulls(obj), sort_keys=True))


def decode_oauth_state(state):
  """Decodes a state parameter encoded by :meth:`encode_state_parameter`.

  Args:
    state: a string (JSON-serialized dict), or None

  Returns: dict
  """
  if not isinstance(state, str) and state is not None:
    raise TypeError(f'Expected str, got {state.__class__}')

  logger.debug(f'decoding state {state!r}', )
  try:
    obj = json_loads(urllib.parse.unquote_plus(state)) if state else {}
  except ValueError:
    logger.error(f'Invalid value for state parameter: {state}', stack_info=True)
    abort(400, f'Invalid value for state parameter: {state}')

  if not isinstance(obj, dict):
    logger.error(f'got a non-dict state parameter {state}')
    return {}

  return obj


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

  Returns:
    value or None
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

  Uses App Engine's `os.urandom()`, which is designed to be cryptographically
  secure: http://code.google.com/p/googleappengine/issues/detail?id=1055

  Args:
    bytes: integer, length of string to generate

  Returns:
    random string
  """
  return base64.urlsafe_b64encode(os.urandom(16))


def is_int(arg):
  """Returns True if arg can be converted to an integer, False otherwise."""
  try:
    as_int = int(arg)
    return as_int == arg if isinstance(arg, numbers.Number) else True
  except (ValueError, TypeError):
    return False


def is_float(arg):
  """Returns True if arg can be converted to a float, False otherwise."""
  try:
    as_float = float(arg)
    return as_float == arg if isinstance(arg, numbers.Number) else True
  except (ValueError, TypeError):
    return False


def is_base64(arg):
  """Returns True if arg is a base64 encoded string, False otherwise."""
  return isinstance(arg, str) and re.match('^[a-zA-Z0-9_=-]*$', arg)


def sniff_json_or_form_encoded(value):
  """Detects whether value is JSON or form-encoded, parses and returns it.

  Args:
    value: string

  Returns: dict if form-encoded; dict or list if JSON; otherwise string
  """
  if not value:
    return {}
  elif value[0] in ('{', '['):
    return json_loads(value)
  elif '=' in value:
    return {k: v[0] if len(v) == 1 else v
            for k, v in urllib.parse.parse_qs(value).items()}
  else:
    return json_loads(value)


def interpret_http_exception(exception):
  """Extracts the status code and response from different HTTP exception types.

  Args:
    exception: an HTTP request exception. Supported types:

      * :class:`apiclient.errors.HttpError`
      * :class:`webob.exc.WSGIHTTPException`
      * :class:`gdata.client.RequestError`
      * :class:`oauth2client.client.AccessTokenRefreshError`
      * :class:`requests.HTTPError`
      * :class:`urllib.error.HTTPError`
      * :class:`urllib.error.URLError`
      * :class:`werkzeug.exceptions.HTTPException`

  Returns:
    (string status code or None, string response body or None)
  """
  e = exception
  code = body = None

  if exc and isinstance(e, exc.WSGIHTTPException):
    code = e.code
    body = e.plain_body({})

  elif werkzeug and isinstance(e, werkzeug.exceptions.HTTPException):
    code = e.code
    body = e.get_description()

  elif isinstance(e, urllib.error.HTTPError):
    code = e.code
    try:
      body = e.read() or e.body
      if body:
        # store a copy inside the exception because e.fp.seek(0) to reset isn't
        # always available.
        e.body = body
        body = body.decode('utf-8')
    except (AttributeError, KeyError):
      if not body:
        body = str(e.reason)

    # yes, flickr returns 400s when they're down. kinda ridiculous. fix that.
    if (code == '418' or
        (code == '400' and
         'Sorry, the Flickr API service is not currently available' in body)):
      code = '504'

  elif isinstance(e, urllib.error.URLError):
    body = str(e.reason)

  elif ((requests and isinstance(e, requests.HTTPError)) or
        (prawcore and isinstance(e, prawcore.exceptions.ResponseException))):
    code = e.response.status_code
    # TODO: this (and same below) can raise if the body was already read:
    # 'RuntimeError: The content for this response was already consumed'
    # https://console.cloud.google.com/errors/detail/CKuWp8f18s3g0gE;time=P30D?project=brid-gy
    body = e.response.text

  elif tumblpy and isinstance(e, tumblpy.TumblpyError):
    code = e.error_code
    body = e.msg

  elif tweepy and isinstance(e, tweepy.HTTPException):
    code = '429' if isinstance(e, tweepy.TooManyRequests) else '400'
    body = e.response.text

  elif apiclient and isinstance(e, apiclient.errors.HttpError):
    code = e.resp.status
    body = e.response.text

  elif ((AccessTokenRefreshError and isinstance(e, AccessTokenRefreshError)) or
        (prawcore and isinstance(e, prawcore.exceptions.OAuthException))):
    body = str(e)
    if body.startswith('invalid_grant'):
      code = '401'
    elif body.startswith('internal_failure'):
      code = '502'

  # hack to interpret gdata.client.RequestError since gdata isn't a dependency
  elif e.__class__.__name__ == 'RequestError':
    code = getattr(e, 'status')
    body = getattr(e, 'body')
  elif e.__class__.__name__ == 'Unauthorized':
    code = '401'
    body = ''

  if code:
    code = str(code)
  orig_code = code
  if code or body:
    logger.warning(f'Error {code}, response body: {body!r}')

  if isinstance(body, bytes):
    # good faith effort to decode as UTF-8 or ASCII
    try:
      body = body.decode()
    except:
      pass

  # silo-specific error_types that should disable the source.
  #
  # instagram
  if body and ('OAuthAccessTokenException' in body or      # revoked access
               'APIRequiresAuthenticationError' in body):  # account deleted
    code = '401'

  # facebook and others
  # https://developers.facebook.com/docs/graph-api/using-graph-api/#errors
  body_json = None
  error = {}
  if body:
    try:
      body_json = json_loads(body)
      error = body_json if isinstance(body_json, str) else body_json.get('error', {})
      if not isinstance(error, dict):
        error = {'message': repr(error)}
    except BaseException:
      pass

  # twitter
  # https://dev.twitter.com/overview/api/response-codes
  if not error and body_json and isinstance(body_json, dict):
    errors = body_json.get('errors')
    if errors and isinstance(errors, list):
      error = errors[0]

  type = error.get('type')
  message = error.get('message')
  if not isinstance(message, str):
    message = repr(message)
  err_code = error.get('code')
  err_subcode = error.get('error_subcode')
  if ((type == 'OAuthException' and
       # have to use message, not error code, since some error codes are for
       # both auth and non-auth errors, e.g. we've gotten code 100 for both
       # "This authorization code has expired." and "Too many IDs. ..."
       ('token provided is invalid.' in message or
        'authorization code has expired.' in message or
        'the user is not a confirmed user.' in message or
        'user must be an administrator of the page' in message or
        'user is enrolled in a blocking, logged-in checkpoint' in message or
        'access token belongs to a Page that has been deleted.' in message or
        # this one below comes with HTTP 400, but actually seems to be transient.
        # 'Cannot call API on behalf of this user' in message or
        'Permissions error' == message
      )) or
      (type == 'FacebookApiException' and 'Permissions error' in message) or
      # https://developers.facebook.com/docs/graph-api/using-graph-api#errorcodes
      # https://developers.facebook.com/docs/graph-api/using-graph-api#errorsubcodes
      (err_code in (102, 190) and err_subcode in (458, 459, 460, 463, 467, 490)) or
      (err_code == 326 and 'this account is temporarily locked' in message)
    ):
    code = '401'

  if error.get('is_transient'):
    if code == '401':
      code = orig_code if orig_code != '401' else '402'
    else:
      code = '503'

  if (code == '400' and type == 'OAuthException' and
      ('Page request limit reached' in message or
       'Page request limited reached' in message)):
    code = '429'

  # upstream errors and connection failures become 502s and 504s, respectively
  if code == '500':
    code = '502'
  elif is_connection_failure(e):
    code = '504'
    if not body:
      body = str(e)

  if orig_code != code:
    logger.info(f'Converting code {orig_code} to {code}')

  return code, body


@contextlib.contextmanager
def ignore_http_4xx_error():
  try:
    yield
  except BaseException as e:
    code, _ = interpret_http_exception(e)
    if not (code and int(code) // 100 == 4):
      raise


def is_connection_failure(exception):
  """Returns True if the given exception is a network connection failure.

  ...False otherwise.
  """
  types = [
      ConnectionError,
      http.client.ImproperConnectionState,
      http.client.IncompleteRead,
      http.client.NotConnected,
      prawcore.exceptions.RequestException,
      socket.timeout,
      TimeoutError,
      ssl.SSLError,
  ]
  if requests:
    types += [
      requests.exceptions.ChunkedEncodingError,
      requests.exceptions.ContentDecodingError,
      requests.ConnectionError,
      requests.Timeout,
      requests.TooManyRedirects,
    ]

  if urllib3:
    types += [
      urllib3.exceptions.HTTPError,
      urllib3.exceptions.ReadTimeoutError,
    ]

  msg = str(exception)
  if (isinstance(exception, tuple(types)) or
      (isinstance(exception, urllib.error.URLError) and
       isinstance(exception.reason, socket.error)) or
      (isinstance(exception, http.client.HTTPException) and
       'Deadline exceeded' in msg) or
      # these are tweepy.TweepError wrapping NewConnectionError
      'Connection closed unexpectedly' in msg or
      'Max retries exceeded' in msg
     ):
    logger.info(f'Connection failure: {exception}', stack_info=False)
    return True

  return False


class FileLimiter(object):
  """A file object wrapper that reads up to a limit and then reports EOF.

  From http://stackoverflow.com/a/29838711/186123 . Thanks SO!
  """
  def __init__(self, file_obj, read_limit):
    self.read_limit = read_limit
    self.amount_seen = 0
    self.file_obj = file_obj
    self.ateof = False

    # So that requests doesn't try to chunk an upload but will instead stream it
    self.len = read_limit

  def read(self, amount=-1):
    if self.amount_seen >= self.read_limit:
      return b''

    remaining = self.read_limit - self.amount_seen
    to_read = remaining if amount < 0 else min(amount, remaining)
    data = self.file_obj.read(to_read)

    self.amount_seen += len(data)
    if (len(data) < to_read) or (to_read and not data):
      self.ateof = True
    return data


def read(filename):
  """Returns the contents of filename, or None if it doesn't exist."""
  if os.path.exists(filename):
    with open(filename, encoding='utf-8') as f:
      return f.read().strip()


def load_file_lines(file):
  """Reads lines from a file and returns them as a set.

  Leading and trailing whitespace is trimmed. Blank lines and lines beginning
  with # (ie comments) are ignored.

  Args:
    file: a file object or other iterable that returns lines

  Returns:
    set of strings
  """
  items = set()

  for line in file:
    val = line.strip()
    if val and not val.startswith('#'):
      items.add(val)

  return items


def json_loads(*args, **kwargs):
  """Wrapper around :func:`json.loads` that centralizes our JSON handling."""
  return json.loads(*args, **kwargs)


def json_dumps(*args, **kwargs):
  """Wrapper around :func:`json.dumps` that centralizes our JSON handling."""
  if ujson:
    kwargs.setdefault('escape_forward_slashes', False)

  return json.dumps(*args, **kwargs)


def set_user_agent(val):
  """Sets the user agent to be sent in :func:`urlopen` and :func:`requests_fn`.

  Args:
    val: str
  """
  global user_agent
  user_agent = val


def urlopen(url_or_req, *args, **kwargs):
  """Wraps :func:`urllib.request.urlopen` and logs the HTTP method and URL.

  Use :func:`set_user_agent` to change the User-Agent header to be sent.
  """
  data = kwargs.get('data')
  if isinstance(data, str):
    kwargs['data'] = data.encode()

  if url_or_req.__class__.__name__ == 'Request':
    req = url_or_req
    if data is None:
      data = req.data
      if isinstance(data, str):
        req.data = data.encode()
    url = req.get_full_url()
  else:
    url = url_or_req
    req = urllib.request.Request(url)

  if not req.has_header('User-Agent'):
    global user_agent
    req.add_header('User-Agent', user_agent)

  method = 'GET' if data is None else 'POST'
  logger.info(f'urlopen {method} {url} {_prune(kwargs)}')
  kwargs.setdefault('timeout', HTTP_TIMEOUT)
  return urllib.request.urlopen(req, *args, **kwargs)


def requests_fn(fn):
  """Wraps requests.* and logs the HTTP method and URL.

  Use :func:`set_user_agent` to change the User-Agent header to be sent.

  Args:
    method: 'get', 'head', or 'post'

  Returns:
    callable, (str url, gateway=None, **kwargs) => :class:`requests.Response`,
      drop-in replacement for :func:`requests.get` etc

      The gateway kwarg is a boolean for whether this is in a HTTP gateway
      request handler context. If True, errors will be raised as appropriate
      Flask HTTP exceptions. Malformed URLs result in
      :class:`werkzeug.exceptions.BadRequest` (HTTP 400), connection failures
      and HTTP 4xx and 5xx result in :class:`werkzeug.exceptions.BadGateway`
      (HTTP 502).
  """
  def call(url, session=None, *args, **kwargs):
    logger.info(f'{session or "requests"}.{fn} {url} {_prune(kwargs)}')

    gateway = kwargs.pop('gateway', None)
    kwargs.setdefault('timeout', HTTP_TIMEOUT)
    # stream to short circuit on too-long response bodies (below)
    kwargs.setdefault('stream', True)

    if kwargs.get('headers') is None:
      kwargs['headers'] =  {}
    kwargs['headers'].setdefault('User-Agent', user_agent)

    try:
      # use getattr so that stubbing out with mox still works
      resp = getattr((session or requests), fn)(url, *args, **kwargs)
      if gateway:
        logger.info(f'Received {resp.status_code}: {"" if resp.ok else resp.text[:500]}')
        resp.raise_for_status()
    except (ValueError, requests.URLRequired) as e:
      if isinstance(e, requests.exceptions.InvalidURL):
        punycode = domain2idna(url)  # surprisingly, this handles full URLs fine
        if punycode != url:
          # the domain is valid idn2003 but not idn2008. encode and try again.
          # https://unicode.org/faq/idn.html#6
          # https://github.com/psf/requests/issues/3687
          # https://github.com/kjd/idna/issues/18
          # https://github.com/kjd/idna/issues/40
          resp = call(punycode, *args, **kwargs)
          resp.url = resp.url.replace(urlparse(punycode).netloc,
                                      urlparse(url).netloc)
          return resp

      if gateway:
        msg = f'Bad URL {url} : {e}'
        logger.warning(msg)
        # this format_exc with tb None below, instead of passing exc_info=True
        # above, prevents the 'Traceback (most recent call last):' prefix that
        # triggers Stackdriver Error Reporting
        logger.warning('\n'.join(traceback.format_tb(sys.exc_info()[2])))
        abort(400, msg)
      raise

    except requests.RequestException as e:
      if gateway:
        msg = str(e)
        if e.response is not None:
          msg += f' ; {e.response.text}'
        logger.warning(msg)
        logger.warning('\n'.join(traceback.format_tb(sys.exc_info()[2])))
        abort(502, msg)
      raise

    if url != resp.url:
      logger.info(f'Redirected to {resp.url}')

    # check response size for text/ and application/ Content-Types
    type = resp.headers.get('Content-Type', '')
    if type and (type.startswith('text/') or type.startswith('application/')):
      length = resp.headers.get('Content-Length')
      if is_int(length):
        length = int(length)
      else:
        length = len(resp.text)
      if length > MAX_HTTP_RESPONSE_SIZE:
        resp.close()
        resp.status_code = HTTP_RESPONSE_TOO_BIG_STATUS_CODE
        resp._text = f'Content-Length {length} is larger than our limit {MAX_HTTP_RESPONSE_SIZE}.'
        resp._content = resp._text.encode('utf-8')
        if gateway:
          resp.raise_for_status()

    msg = f'Received {resp.status_code}'
    if resp.status_code // 100 == 3:
      msg += f' {resp.headers.get("Location") or "no Location header"}'
    logger.info(msg)

    return resp

  return call

requests_get = requests_fn('get')
requests_head = requests_fn('head')
requests_post = requests_fn('post')
requests_delete = requests_fn('delete')


def requests_post_with_redirects(url, *args, **kwargs):
  """Make an HTTP POST, and follow redirects with POST instead of GET.

  Violates the HTTP spec's rule to follow POST redirects with GET. Yolo!

  Args:
    url: string

  Returns: :class:`requests.Response`

  Raises: TooManyRedirects
  """
  for _ in range(requests.models.DEFAULT_REDIRECT_LIMIT):
    resp = requests_post(url, *args, allow_redirects=False, **kwargs)
    url = resp.headers.get('Location')
    if resp.is_redirect and url:
      continue
    resp.raise_for_status()
    return resp

  raise requests.TooManyRedirects(response=resp)


def _prune(kwargs):
  pruned = dict(kwargs)

  headers = pruned.get('headers')
  if headers:
    pruned['headers'] = {k: '...' for k in headers}

  return {k: v for k, v in list(pruned.items())
          if k not in ('allow_redirects', 'stream', 'timeout')}


@cached(follow_redirects_cache, lock=follow_redirects_cache_lock,
        key=lambda url, **kwargs: url)
def follow_redirects(url, **kwargs):
  """Fetches a URL with HEAD, repeating if necessary to follow redirects.

  Caches results for 1 day by default. To bypass the cache, use
  follow_redirects.__wrapped__(...).

  Does not raise an exception if any of the HTTP requests fail, just returns
  the failed response. If you care, be sure to check the returned response's
  status code!

  Args:
    url: string
    kwargs: passed to requests.head()

  Returns:
    the `requests.Response` for the final request. The `url` attribute has the
      final URL.
  """
  try:
    # default scheme to http
    parsed = urlparse(url)
    if not parsed.scheme:
      url = 'http://' + url
    resolved = requests_head(url, allow_redirects=True, **kwargs)
  except AssertionError:
    raise
  except BaseException as e:
    logger.warning(f"Couldn't resolve URL {url} : {e}")
    resolved = requests.Response()
    resolved.url = url
    resolved.status_code = 499  # not standard. i made this up.

  try:
    resolved.raise_for_status()
    if resolved.url != url:
      logger.debug(f'Resolved {url} to {resolved.url}')
  except BaseException as e:
    logger.warning(f"Couldn't resolve URL {url}: {resolved.url}")

  content_type = resolved.headers.get('content-type')
  if (not resolved.ok or
      not content_type):  # Content-Type of error response isn't useful
    if resolved.url:
      type, _ = mimetypes.guess_type(resolved.url)
      resolved.headers['content-type'] = type or 'text/html'

  refresh = resolved.headers.get('refresh')
  if refresh:
    for part in refresh.split(';'):
      if part.strip().startswith('url='):
        return follow_redirects(part.strip()[4:], **kwargs)

  resolved.url = clean_url(resolved.url)
  if url != resolved.url:
    with follow_redirects_cache_lock:
      follow_redirects_cache[resolved.url] = resolved

  return resolved


class UrlCanonicalizer(object):
  """Converts URLs to their canonical form.

  If an input URL matches approve or reject, it's automatically approved as is
  without following redirects.

  If we HEAD the URL to follow redirects and it returns 4xx or 5xx, we return
  None.
  """
  def __init__(self, scheme='https', domain=None, subdomain=None, approve=None,
               reject=None, query=False, fragment=False, trailing_slash=False,
               redirects=True, headers=None):
    """Constructor.

    Args:
      scheme: string canonical scheme for this source (default 'https')
      domain: string canonical domain for this source (default None). If set,
        links on other domains will be rejected without following redirects.
      subdomain: string canonical subdomain, e.g. 'www' (default none, ie root
        domain). only added if there's not already a subdomain.
      approve: string regexp matching URLs that are automatically considered
        canonical
      reject: string regexp matching URLs that are automatically considered
        canonical
      query: boolean, whether to keep query params, if any (default False)
      fragment: boolean, whether to keep fragment, if any (default False)
      trailing slash: boolean, whether the path should end in / (default False)
      redirects: boolean, whether to make HTTP HEAD requests to follow
        redirects (default True)
      headers: passed through to the requests.head call for following redirects
    """
    self.scheme = self.to_unicode(scheme)
    self.domain = self.to_unicode(domain)
    self.subdomain = self.to_unicode(subdomain)
    self.approve = re.compile(approve) if approve else None
    self.reject = re.compile(reject) if reject else None
    self.query = query
    self.fragment = fragment
    self.trailing_slash = trailing_slash
    self.redirects = redirects
    self.headers = headers

  @staticmethod
  def to_unicode(val):
    return val.decode() if isinstance(val, bytes) else val

  def __call__(self, url, redirects=None):
    """Canonicalizes a string URL.

    Returns the canonical form of a string URL, or None if it can't be
    canonicalized, eg its domain doesn't match.
    """
    url = self.to_unicode(url)
    if self.approve and self.approve.match(url):
      return url
    elif self.reject and self.reject.match(url):
      return None

    parsed = urlparse(url)
    domain = parsed.hostname
    if not domain:
      return None
    elif (self.domain and domain != self.domain
          and not domain.endswith('.' + self.domain)):
      return None
    if domain.startswith('www.'):
      domain = domain[4:]
    if self.subdomain and domain.count('.') == 1:
      domain = f'{self.subdomain}.{domain}'

    scheme = self.scheme or parsed.scheme
    query = parsed.query if self.query else ''
    fragment = parsed.fragment if self.fragment else ''

    path = parsed.path
    if self.trailing_slash and not path.endswith('/'):
      path += '/'
    elif not self.trailing_slash and path.endswith('/'):
      path = path[:-1]

    new_url = urllib.parse.urlunparse((scheme, domain, path, '', query, fragment))
    if new_url != url:
      return self(new_url, redirects=redirects)  # recheck approve/reject

    if redirects or (redirects is None and self.redirects):
      resp = follow_redirects(url, headers=self.headers)
      if resp.status_code // 100 in (4, 5):
        return None
      elif resp.url != url:
        return self(resp.url, redirects=False)

    return url


class WideUnicode(str):
  """String class with consistent indexing and len() on narrow *and* wide Python.

  PEP 261 describes that Python 2 builds come in "narrow" and "wide" flavors.
  Wide is configured with --enable-unicode=ucs4, which represents Unicode high
  code points above the 16-bit Basic Multilingual Plane in unicode strings as
  single characters. This means that len(), indexing, and slices of unicode
  strings use Unicode code points consistently.

  Narrow, on the other hand, represents high code points as "surrogate pairs" of
  16-bit characters. This means that len(), indexing, and slicing unicode
  strings does *not* always correspond to Unicode code points.

  Mac OS X, Windows, and older Linux distributions have narrow Python 2 builds,
  while many modern Linux distributions have wide builds, so this can cause
  platform-specific bugs, e.g. with many commonly used emoji.

  Docs:
  https://www.python.org/dev/peps/pep-0261/
  https://docs.python.org/2.7/library/codecs.html?highlight=ucs2#encodings-and-unicode
  http://www.unicode.org/glossary/#high_surrogate_code_point

  Inspired by: http://stackoverflow.com/a/9934913

  Related work:
  https://uniseg-python.readthedocs.io/
  https://pypi.python.org/pypi/pytextseg
  https://github.com/LuminosoInsight/python-ftfy/
  https://github.com/PythonCharmers/python-future/issues/116
  https://dev.twitter.com/basics/counting-characters

  On StackOverflow:
  http://stackoverflow.com/questions/1446347/how-to-find-out-if-python-is-compiled-with-ucs-2-or-ucs-4
  http://stackoverflow.com/questions/12907022/python-getting-correct-string-length-when-it-contains-surrogate-pairs
  http://stackoverflow.com/questions/35404144/correctly-extract-emojis-from-a-unicode-string
  """
  def __init__(self, *args, **kwargs):
    super(WideUnicode, self).__init__()
    # use UTF-32LE to avoid a byte order marker at the beginning of the string
    self.__utf32le = str(self).encode('utf-32le')

  def __len__(self):
    return len(self.__utf32le) // 4

  def __getitem__(self, key):
    length = len(self)

    if isinstance(key, int):
      if key >= length:
        raise IndexError()
      key = slice(key, key + 1)

    start = key.start or 0
    stop = length if key.stop is None else key.stop
    assert key.step is None

    return WideUnicode(self.__utf32le[start * 4:stop * 4].decode('utf-32le'))

  def __getslice__(self, i, j):
    return self.__getitem__(slice(i, j))


def parse_html(input, **kwargs):
  """Parses an HTML string with BeautifulSoup.

  Uses the HTML parser currently set in the beautifulsoup_parser global.
  http://www.crummy.com/software/BeautifulSoup/bs4/doc/#specifying-the-parser-to-use

  We generally try to use the same parser and version in prod and locally, since
  we've been bit by at least one meaningful difference between lxml and e.g.
  html5lib: lxml includes the contents of <noscript> tags, html5lib omits them.
  https://github.com/snarfed/bridgy/issues/798#issuecomment-370508015
  Also lxml is noticeably faster than the others.

  Specifically, projects like oauth-dropins, granary, and bridgy all use lxml
  explicitly.

  Args:
    input: unicode HTML string or :class:`requests.Response`
    kwargs: passed through to :class:`bs4.BeautifulSoup` constructor

  Returns: :class:`bs4.BeautifulSoup`
  """
  kwargs.setdefault('features', beautifulsoup_parser)

  if isinstance(input, requests.Response):
    # The original HTTP 1.1 spec (RFC 2616, 1999) said to default HTML charset
    # to ISO-8859-1 if it's not explicitly provided in Content-Type. RFC 7231
    # (2014) removed that default: https://tools.ietf.org/html/rfc7231#appendix-B
    #
    # requests is working on incorporating that change, but hasn't shippet it yet.
    # https://github.com/psf/requests/issues/2086
    #
    # so, if charset isn't explicitly provided, pass on the raw bytes and let
    # BS4/UnicodeDammit figure it out from <meta charset> tag or anything else.
    # https://github.com/snarfed/granary/issues/171
    content_type = input.headers.get('content-type') or ''
    input = input.text if 'charset' in content_type else input.content

  return bs4.BeautifulSoup(input, **kwargs)


def parse_mf2(input, url=None, id=None):
  """Parses microformats2 out of HTML.

  Currently uses mf2py.

  Args:
    input: unicode HTML string, :class:`bs4.BeautifulSoup`, or
      :class:`requests.Response`
    url: optional unicode string, URL of the input page, used as the base for
      relative URLs
    id: string, optional id of specific element to extract and parse. defaults
      to the whole page.

  Returns:
    dict, parsed mf2 data, or None if id is provided and not found in the input HTML
  """
  if isinstance(input, requests.Response) and not url:
    url = input.url

  if not isinstance(input, (bs4.BeautifulSoup, bs4.Tag)):
    input = parse_html(input)

  if id:
    logger.info(f'Extracting and parsing just DOM element {id}')
    input = input.find(id=id)
    if not input:
      return None

  return mf2py.parse(url=url, doc=input, img_with_alt=True)


def parse_http_equiv(content):
  """Parses the value in the http_equiv meta field and returns the url.

  Args:
    content: str, http_equiv content string https://www.w3.org/TR/WCAG20-TECHS/H76.html#procedure

  Returns: str, empty if content format is incorrect
  """
  split = content.rpartition('URL=')
  if not split[1]: # If URL= is not in the string return an empty string
    return ''

  return split[2].strip("'")


def fetch_http_equiv(input, **kwargs):
  """Fetches http_equiv meta tag, if available.

  Args:
    input: unicode HTML string, :class:`bs4.BeautifulSoup`, or
      :class:`requests.Response`

  Returns: str, empty if not available or a url if available
  """
  if not isinstance(input, (bs4.BeautifulSoup, bs4.Tag)):
    input = parse_html(input)

  element = input.find('meta', attrs={'http-equiv': 'refresh'})

  if not element:
    return ''

  refresh_content = element.get('content')

  if not refresh_content:
    return ''

  return parse_http_equiv(refresh_content)


def fetch_mf2(url, get_fn=requests_get, gateway=False, require_backlink=None,
              **kwargs):
  """Fetches an HTML page over HTTP, parses it, and returns its microformats2.

  If url includes a fragment, or redirects to a URL with a fragment, only that
  element of the HTML will be parsed and returned.

  Args:
    url: str
    get_fn: callable matching :func:`requests.get`'s signature, for the HTTP fetch
    gateway: boolean; see :func:`requests_fn`
    require_backlink: str or sequence of strs; raises ValueError if one of these
      strings is not present in the returned HTML, in any form. Generally used
      for webmention validation.
    **kwargs: passed through to :func:`requests.get`

  Returns: dict, parsed mf2 data. Includes the final URL of the parsed document
    (after redirects) in the top-level `url` field.

  Raises:
    ValueError: if a backlink in require_backlink is not found
  """
  resp = get_fn(fragmentless(url), gateway=gateway, **kwargs)
  resp.raise_for_status()

  if require_backlink:
    if not isinstance(require_backlink, (tuple, list)):
      require_backlink = [require_backlink]
    for link in require_backlink:
      if link in resp.text:
        break
    else:
      raise ValueError(f"Couldn't find {require_backlink} in {url}")

  fragment = urllib.parse.urlparse(url).fragment
  mf2 = parse_mf2(resp, id=fragment)
  if mf2 is None:
    return None

  assert 'url' not in mf2
  mf2['url'] = resp.url
  return mf2


def d(*objs):
  """Pretty-prints an object as JSON, for debugging."""
  dumped = []
  for o in objs:
    try:
      dumped.append(json_dumps(o, indent=2))
    except TypeError:
      dumped.append(str(o))

  print('@', '\n'.join(dumped))
