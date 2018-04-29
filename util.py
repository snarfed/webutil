"""Misc utilities.

Supports Python 3. Should not depend on App Engine API or SDK packages.
"""
from __future__ import absolute_import, division, unicode_literals
# Future's default urllib backport based on the http library doesn't work in App
# Engine's dev_appserver, probably because it doesn't support SSL. Use this
# urllib2-based one instead. http://python-future.org/imports.html#aliased-imports
from future.moves.urllib.request import urlopen as urllib_urlopen
from future.moves.urllib import error as urllib_error
from future import standard_library
standard_library.install_aliases()
from future.utils import bytes_to_native_str, PY2, text_type
from builtins import object, range, str
import past.builtins
from past.builtins import basestring

import calendar
import collections
import contextlib
import base64
import datetime
import http.client
import inspect
import json
import logging
import mimetypes
import numbers
import os
import re
import socket
import urllib.parse, urllib.request

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
  from webob import exc
except ImportError:
  exc = None

try:
  from appengine_config import HTTP_TIMEOUT
  from google.appengine.api import urlfetch_errors
  from google.appengine.runtime import apiproxy_errors
except (ImportError, ValueError):
  HTTP_TIMEOUT = 15
  urlfetch_errors = None
  apiproxy_errors = None

EPOCH = datetime.datetime.utcfromtimestamp(0)
EPOCH_ISO = EPOCH.isoformat()
T = bytes_to_native_str(b'T')  # for isoformat()


class Struct(object):
  """A generic class that initializes its attributes from constructor kwargs."""
  def __init__(self, **kwargs):
    vars(self).update(**kwargs)


class CacheDict(dict):
  """A dict that also implements memcache's get_multi() and set_multi() methods.

  Useful as a simple in memory replacement for App Engine's memcache API for
  e.g. get_activities_response() in snarfed/activitystreams-unofficial.
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
      elems.extend('<%s>%s</%s>' % (key, to_xml(val), key) for val in vals)
    return '\n' + '\n'.join(elems) + '\n'
  else:
    if value is None:
      value = ''
    return str(value)


def trim_nulls(value, ignore=()):
  """Recursively removes dict and list elements with None or empty values.

  Args:
    value: dict or list
    ignore: optional sequence of keys to allow to have None/empty values
  """
  NULLS = (None, {}, [], (), '', set(), frozenset())

  if isinstance(value, dict):
    trimmed = {k: trim_nulls(v, ignore=ignore) for k, v in value.items()}
    return {k: v for k, v in trimmed.items() if k in ignore or v not in NULLS}
  elif (isinstance(value, (tuple, list, set, frozenset, collections.Iterator)) or
        inspect.isgenerator(value)):
    trimmed = [trim_nulls(v, ignore=ignore) for v in value]
    ret = (v for v in trimmed if v if v not in NULLS)
    if isinstance(value, collections.Iterator) or inspect.isgenerator(value):
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
  return val.get('url') if isinstance(val, dict) else val


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
  if year is not None:
    year = ',%s' % year
  else:
    year = ''
  return 'tag:%s%s:%s' % (domain, year, name)


_TAG_URI_RE = re.compile('tag:([^,]+)(?:,\d+)?:(.+)$')

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
  parsed = urllib.parse.urlparse(uri)
  if parsed.scheme and parsed.scheme != 'acct':
    raise ValueError('Acct URI %s has unsupported scheme: %s' %
                     (uri, parsed.scheme))

  try:
    username, host = parsed.path.split('@')
    assert host
  except (ValueError, AssertionError):
    raise ValueError('Bad acct URI: %s' % uri)

  if hosts is not None and host not in hosts:
    raise ValueError('Acct URI %s has unsupported host %s; expected %r.' %
                     (uri, host, hosts))

  return username, host


def favicon_for_url(url):
  return 'http://%s/favicon.ico' % urllib.parse.urlparse(url).netloc


# http://stackoverflow.com/questions/2532053/validate-hostname-string-in-python
HOSTNAME_RE_STR = r'%s(\.%s)*\.?' % ((r'(?!-)[A-Za-z\d-]{1,63}(?<!-)',) * 2)
HOSTNAME_RE = re.compile(HOSTNAME_RE_STR + '$')

def domain_from_link(url):
  """Extracts and returns the meaningful domain from a URL.

  Strips www., mobile., and m. from the beginning of the domain.

  Args:
    url: string

  Returns:
    string
  """
  parsed = urllib.parse.urlparse(url)
  if not parsed.hostname and '//' not in url:
    parsed = urllib.parse.urlparse('http://' + url)

  domain = parsed.hostname
  if domain:
    for subdomain in ('www.', 'mobile.', 'm.'):
      if domain.startswith(subdomain):
        domain = domain[len(subdomain):]
    if domain and HOSTNAME_RE.match(domain):
      return domain

  return None


def domain_or_parent_in(input, domains):
  """Returns True if an input domain or its parent is in a set of domains.

  Examples:

  * foo, [] => False
  * foo, [foo] => True
  * foo.bar.com, [bar.com] => True
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

def update_scheme(url, handler):
  """Returns a modified URL with the current request's scheme.

  Useful for converting URLs to https if and only if the current request itself
  is being served over https.

  Args:
    url: string
    handler: :class:`webapp2.RequestHandler`

  Returns: string, url
  """
  # Instagram can't serve images over SSL, so switch to their S3 or Akamai URLs,
  # which can.
  # https://groups.google.com/d/msg/instagram-api-developers/fB4mwYXZF1c/q9n9gPO11JQJ
  # http://stackoverflow.com/questions/23755897#comment36547383_23755897
  url = re.sub(r'^http://images\.(ak\.)instagram\.com',
               'http://distillery.s3.amazonaws.com', url)
  url = re.sub(r'^http://photos-\w\.(ak\.)instagram\.com',
               'http://igcdn-photos-e-a.akamaihd.net', url)
  return urllib.parse.urlunparse((handler.request.scheme,) +
                                 urllib.parse.urlparse(url)[1:])


def schemeless(url, slashes=True):
  """Strips the scheme (e.g. 'https:') from a URL.

  Args:
    url: string
    leading_slashes: if False, also strips leading slashes and trailing slash,
      e.g. 'http://example.com/' becomes 'example.com'

  Returns:
    string URL
  """
  url = urllib.parse.urlunparse(('',) + urllib.parse.urlparse(url)[1:])
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
  return urllib.parse.urlunparse(urllib.parse.urlparse(url)[:5] + ('',))


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
    parts = list(urllib.parse.urlparse(url))
  except (AttributeError, TypeError, ValueError):
    return None

  query = urllib.parse.unquote_plus(parts[4])
  params = [(name, value) for name, value in urllib.parse.parse_qsl(query)
            if name not in utm_params
            and not (name == 'source' and value.startswith('rss-'))]
  parts[4] = urllib.parse.urlencode(params)
  return urllib.parse.urlunparse(parts)


def base_url(url):
  """Returns the base of a given URL.

  For example, returns 'http://site/posts/' for 'http://site/posts/123'.

  Args:
    url: string
  """
  return urllib.parse.urljoin(url, ' ')[:-1] if url else None


# Based on kylewm's from redwind:
# https://github.com/snarfed/bridgy/issues/209#issuecomment-47583528
# https://github.com/kylewm/redwind/blob/863989d48b97a85a1c1a92c6d79753d2fbb70775/redwind/util.py#L39
#
# I used to use a more complicated regexp based on
# https://github.com/silas/huck/blob/master/huck/utils.py#L59 , but i kept
# finding new input strings that would make it hang the regexp engine.
#
# more complicated alternative:
# http://stackoverflow.com/questions/720113#comment23297770_2102648
_SCHEME_RE = r'\b(?:[a-z]{3,9}:/{1,3})'
_HOST_RE = r'(?:[a-z0-9\-.])+(?::\d{2,6})?'
_DOMAIN_RE = r'(?:[a-z0-9\-]+\.)+[a-z]{2,4}(?::\d{2,6})?'
_PATH_QUERY_RE = r'(?:(?:/[\w/.\-_~.;:%?@$#&()=+]*)|\b)'
_LINK_RE = re.compile(
  _SCHEME_RE + _HOST_RE + _PATH_QUERY_RE,  # scheme required
  re.UNICODE | re.IGNORECASE)
_LINKIFY_RE = re.compile(
  _SCHEME_RE + '?' + _DOMAIN_RE + _PATH_QUERY_RE,  # scheme optional
  re.UNICODE | re.IGNORECASE)


def extract_links(text):
  """Returns a list of unique string URLs in the given text.

  URLs in the returned list are in the order they first appear in the text.
  """
  if not text:
    return []

  links = uniquify(match.group() for match in _LINK_RE.finditer(text))
  # strip "outside" parens
  links = [l[:-1] if l[-1] == ')' and '(' not in l else l
           for l in links]
  return links


def tokenize_links(text, skip_bare_cc_tlds=False):
  """Splits text into link and non-link text.

  Args:
    text: string to linkify
    skip_bare_cc_tlds: boolean, whether to skip links of the form
      [domain].[2-letter TLD] with no schema and no path

  Returns:
    a tuple containing two lists of strings, a list of links and list of
    non-link text. Roughly equivalent to the output of re.findall and re.split,
    with some post-processing.
  """
  links = _LINKIFY_RE.findall(text)
  splits = _LINKIFY_RE.split(text)

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
    if (splits[ii].strip().endswith('="')
        or splits[ii].strip().endswith("='")
        or splits[ii + 1].strip().startswith('</a')
        # skip domains with 2-letter TLDs and no schema or path
        or (skip_bare_cc_tlds and re.match('[a-z0-9\-]+\.[a-z]{2}$', link))):
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
      result.append('<a href="%s">%s</a>' % (href, url))
  result.append(splits[-1])
  return ''.join(result)


def pretty_link(url, text=None, keep_host=True, glyphicon=None, attrs=None,
                new_tab=False, max_length=None):
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
    parsed = urllib.parse.urlparse(url)
    text = url[len(parsed.scheme) + 3:]  # strip scheme and ://
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

  if max_length and len(text) > max_length:
    text = text[:max_length] + '...'

  if glyphicon is not None:
    text += ' <span class="glyphicon glyphicon-%s"></span>' % glyphicon
  attr_str = (''.join('%s="%s" ' % (attr, val) for attr, val in list(attrs.items()))
              if attrs else '')
  target = 'target="_blank" ' if new_tab else ''
  return ('<a %s%shref="%s">%s</a>' % (attr_str, target, url, text))


class SimpleTzinfo(datetime.tzinfo):
  """A simple, DST-unaware tzinfo subclass.
  """

  offset = datetime.timedelta(0)

  def utcoffset(self, dt):
    return self.offset

  def dst(self, dt):
    return datetime.timedelta(0)

UTC = SimpleTzinfo()


TIMEZONE_OFFSET_RE = re.compile(r'[+-]\d{2}:?\d{2}$')

def parse_iso8601(val):
  """Parses an ISO 8601 or RFC 3339 date/time string and returns a datetime.

  Time zone designator is optional. If present, the returned datetime will be
  time zone aware.

  Args:
    str: string ISO 8601 or RFC 3339, e.g. '2012-07-23T05:54:49+00:00'

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
    offset = zone.group()
    val = val[:-len(offset)]
    tz = SimpleTzinfo()
    tz.offset = (datetime.datetime.strptime(offset[1:].replace(':', ''), '%H%M') -
                 datetime.datetime.strptime('', ''))
    if offset[0] == '-':
      tz.offset = -tz.offset
  elif val[-1] == 'Z':
    val = val[:-1]
    tz = UTC

  # fractional seconds are optional. add them if they're not already there to
  # make strptime parsing below easier.
  if '.' not in val:
    val += '.0'

  return datetime.datetime.strptime(val, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=tz)


def maybe_iso8601_to_rfc3339(input):
  """Tries to convert an ISO 8601 date/time string to RFC 3339.

  The formats are similar, but not identical, eg. RFC 3339 includes a colon in
  the timezone offset at the end (+0000 instead of +00:00), but ISO 8601
  doesn't.

  If the input can't be parsed as ISO 8601, it's silently returned, unchanged!

  http://www.rfc-editor.org/rfc/rfc3339.txt
  """
  try:
    return parse_iso8601(input).isoformat(T)
  except (AssertionError, ValueError, TypeError):
    return input


def maybe_timestamp_to_rfc3339(input):
  """Tries to convert a string or int UNIX timestamp to RFC 3339.

  Assumes UNIX timestamps are always UTC. (They're generally supposed to be.)
  """
  try:
    return datetime.datetime.utcfromtimestamp(int(input)).replace(tzinfo=UTC).isoformat(T)
  except (ValueError, TypeError):
    return input


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
  if input.tzinfo:
    utc = input - input.tzinfo.utcoffset(False)
    return utc.replace(tzinfo=None)
  else:
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
    url: string URL or :class:`urllib2.Request`. May already have query parameters.
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
  parsed = list(urllib.parse.urlparse(url))
  # query params are in index 4
  params = [(k, str(v).encode('utf-8')) for k, v in params]
  parsed[4] += ('&' if parsed[4] else '') + urllib.parse.urlencode(params)
  updated = urllib.parse.urlunparse(parsed)

  if is_request:
    return urllib.request.Request(updated, data=req.data, headers=req.headers)
  else:
    return updated


def get_required_param(handler, name):
  try:
    val = handler.request.get(name)
  except (UnicodeDecodeError, UnicodeEncodeError) as e:
    handler.abort(400, "Couldn't decode query parameters as UTF-8: %s" % e)

  if not val:
    handler.abort(400, 'Missing required parameter: %s' % name)

  return val


def dedupe_urls(urls):
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

  TODO: port to https://pypi.python.org/pypi/urlnorm

  Args:
    urls: sequence of string URLs

  Returns:
    sequence of string URLs
  """
  result = []

  for url in urls:
    if not url:
      continue

    p = urllib.parse.urlsplit(url)
    # normalize domain (hostname attr is lower case) and path
    norm = [p.scheme, p.hostname, p.path or '/', p.query, p.fragment]

    if p.scheme == 'http' and urllib.parse.urlunsplit(['https'] + norm[1:]) in result:
      continue
    elif p.scheme == 'https':
      try:
        result.remove(urllib.parse.urlunsplit(['http'] + norm[1:]))
      except ValueError:
        pass

    url = urllib.parse.urlunsplit(norm)
    if url not in result:
      result.append(url)

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
    raise TypeError('Expected dict, got %s' % obj.__class__)

  logging.debug('encoding state "%s"' % obj)
  # pass in custom separators to cut down on whitespace, and sort keys for
  # unit test consistency
  return urllib.parse.quote_plus(json.dumps(trim_nulls(obj), separators=(',', ':'),
                                            sort_keys=True))


def decode_oauth_state(state):
  """Decodes a state parameter encoded by :meth:`encode_state_parameter`.

  Args:
    state: a string (JSON-serialized dict), or None

  Returns: dict
  """
  if not isinstance(state, basestring) and state is not None:
    raise TypeError('Expected basestring, got %s' % state.__class__)

  logging.debug('decoding state "%s"' % state)
  try:
    obj = json.loads(urllib.parse.unquote_plus(state)) if state else {}
  except ValueError:
    logging.exception('Invalid value for state parameter: %s' % state)
    raise exc.HTTPBadRequest('Invalid value for state parameter: %s' % state)

  if not isinstance(obj, dict):
    logging.error('got a non-dict state parameter %s', state)
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
    return json.loads(value)
  elif '=' in value:
    return {k: v[0] if len(v) == 1 else v
            for k, v in urllib.parse.parse_qs(value).items()}
  else:
    return json.loads(value)


def interpret_http_exception(exception):
  """Extracts the status code and response from different HTTP exception types.

  Args:
    exception: an HTTP request exception. Supported types:

      * :class:`apiclient.errors.HttpError`
      * :class:`webob.exc.WSGIHTTPException`
      * :class:`gdata.client.RequestError`
      * :class:`oauth2client.client.AccessTokenRefreshError`
      * :class:`requests.HTTPError`
      * :class:`urllib2.HTTPError`
      * :class:`urllib2.URLError`

  Returns:
    (string status code or None, string response body or None)
  """
  e = exception
  code = body = None

  if exc and isinstance(e, exc.WSGIHTTPException):
    code = e.code
    body = e.plain_body({})

  elif isinstance(e, urllib_error.HTTPError):
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

  elif isinstance(e, urllib_error.URLError):
    body = str(e.reason)

  elif requests and isinstance(e, requests.HTTPError):
    code = e.response.status_code
    body = e.response.text

  elif apiclient and isinstance(e, apiclient.errors.HttpError):
    code = e.resp.status
    body = e.content.decode('utf-8')

  elif AccessTokenRefreshError and isinstance(e, AccessTokenRefreshError):
    body = str(e)
    if body.startswith('invalid_grant'):
      code = '401'
    elif body.startswith('internal_failure'):
      code = '502'

  # hack to interpret gdata.client.RequestError since gdata isn't a dependency
  elif e.__class__.__name__ == 'RequestError':
    code = getattr(e, 'status')
    body = getattr(e, 'body')

  if code:
    code = str(code)
  orig_code = code
  if code or body:
    logging.warning('Error %s, response body: %s', code, repr(body))

  # silo-specific error_types that should disable the source.
  #
  # instagram
  if body and ('OAuthAccessTokenException' in body or      # revoked access
               'APIRequiresAuthenticationError' in body):  # account deleted
    code = '401'

  # facebook
  # https://developers.facebook.com/docs/graph-api/using-graph-api/#errors
  body_json = None
  error = {}
  if body:
    try:
      body_json = json.loads(body)
      error = body_json.get('error', {})
      if not isinstance(error, dict):
        error = {'message': repr(error)}
    except BaseException:
      pass

  # twitter
  # https://dev.twitter.com/overview/api/response-codes
  if body_json and not error:
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
    logging.info('Converting code %s to %s', orig_code, code)

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
      http.client.ImproperConnectionState,
      http.client.NotConnected,
      socket.timeout,
  ]
  # socket.error is its own thing in python 2, but python 3.3 changed it to be
  # an alias of OSError.
  if PY2:
    types.append(socket.error)
  if apiproxy_errors:
    types += [
      apiproxy_errors.CancelledError,
      apiproxy_errors.DeadlineExceededError,
    ]
  if urlfetch_errors:
    types += [
      urlfetch_errors.DownloadError,  # base class, e.g. for DeadlineExceededError
      urlfetch_errors.InternalTransientError,
    ]
  if requests:
    types += [
      requests.ConnectionError,
      requests.Timeout,
    ]

  if urllib3:
    types += [urllib3.exceptions.HTTPError]

  msg = str(exception)
  if (isinstance(exception, tuple(types)) or
      (isinstance(exception, urllib_error.URLError) and
       isinstance(exception.reason, socket.error)) or
      (isinstance(exception, http.client.HTTPException) and
       'Deadline exceeded' in msg) or
      'Connection closed unexpectedly' in msg  # tweepy.TweepError
     ):
    # TODO: exc_info might not be for exception, e.g. if the json.loads() in
    # interpret_http_exception() fails. need to pass through the whole
    # sys.exc_info() tuple here, not just the exception object.
    logging.info('Connection failure: %s' % exception, exc_info=True)
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
    assert isinstance(line, str), "Use future's builtins.open, not Python 2's!"
    val = line.strip()
    if val and not val.startswith('#'):
      items.add(val)

  return items


def urlopen(url_or_req, *args, **kwargs):
  """Wraps urllib2.urlopen and logs the HTTP method and URL."""
  data = kwargs.get('data')

  if url_or_req.__class__.__name__ == 'Request':
    if data is None:
      data = url_or_req.data
    url = url_or_req.get_full_url()
  else:
    url = url_or_req

  if url_or_req.__class__.__module__ == 'urllib2':
    # convert python 2 urllib2.Request to python 3 urllib.request.Request
    url_or_req = urllib.request.Request(url, data=data, headers=url_or_req.headers)

  logging.info('urlopen %s %s %s', 'GET' if data is None else 'POST', url,
               _prune(kwargs))
  kwargs.setdefault('timeout', HTTP_TIMEOUT)
  return urllib_urlopen(url_or_req, *args, **kwargs)


def requests_fn(fn):
  """Wraps requests.* and logs the HTTP method and URL."""
  def call(url, *args, **kwargs):
    logging.info('requests.%s %s %s', fn, url, _prune(kwargs))
    kwargs.setdefault('timeout', HTTP_TIMEOUT)
    # use getattr so that stubbing out with mox still works
    return getattr(requests, fn)(url, *args, **kwargs)

  return call

requests_get = requests_fn('get')
requests_head = requests_fn('head')
requests_post = requests_fn('post')


def _prune(kwargs):
  pruned = dict(kwargs)

  headers = pruned.get('headers')
  if headers:
    pruned['headers'] = {k: '...' for k in headers}

  return {k: v for k, v in list(pruned.items())
          if k not in ('allow_redirects', 'stream', 'timeout')}


def follow_redirects(url, cache=None, fail_cache_time_secs = 60 * 60 * 24,  # a day
                     **kwargs):
  """Fetches a URL with HEAD, repeating if necessary to follow redirects.

  *Does not* raise an exception if any of the HTTP requests fail, just returns
  the failed response. If you care, be sure to check the returned response's
  status code!

  Args:
    url: string
    cache: optional, a cache object to read and write resolved URLs to. Must
      have get(key) and set(key, value, time=...) methods. Stores
      'R [original URL]' in key, final URL in value.
    kwargs: passed to requests.head()

  Returns:
    the `requests.Response` for the final request. The `url` attribute has the
      final URL.
  """
  if cache is not None:
    cache_key = 'R ' + url
    resolved = cache.get(text_type(cache_key))
    if resolved is not None:
      return resolved

  # can't use urllib2 since it uses GET on redirect requests, even if i specify
  # HEAD for the initial request.
  # http://stackoverflow.com/questions/9967632
  try:
    # default scheme to http
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
      url = 'http://' + url
    resolved = requests_head(url, allow_redirects=True, **kwargs)
    resolved.raise_for_status()
    if resolved.url != url:
      logging.debug('Resolved %s to %s', url, resolved.url)
    cache_time = 0  # forever
  except AssertionError:
    raise
  except BaseException as e:
    logging.warning("Couldn't resolve URL %s : %s", url, e)
    resolved = requests.Response()
    resolved.url = url
    resolved.status_code = 499  # not standard. i made this up.
    cache_time = fail_cache_time_secs

  content_type = resolved.headers.get('content-type')
  if not content_type and resolved.url:
    type, _ = mimetypes.guess_type(resolved.url)
    resolved.headers['content-type'] = type or 'text/html'

  refresh = resolved.headers.get('refresh')
  if refresh:
    for part in refresh.split(';'):
      if part.strip().startswith('url='):
        return follow_redirects(part.strip()[4:], cache=cache, **kwargs)

  resolved.url = clean_url(resolved.url)
  if cache is not None:
    cache.set_multi({cache_key: resolved, 'R ' + resolved.url: resolved},
                    time=cache_time)
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
    return val.decode('utf-8') if isinstance(val, (bytes, past.builtins.str)) else val

  def __call__(self, url, redirects=None):
    """Canonicalizes a string URL.

    Returns the canonical form of a string URL, or None if it can't be
    canonicalized, ie it's in the blacklist or its domain doesn't match.
    """
    url = self.to_unicode(url)
    if self.approve and self.approve.match(url):
      return url
    elif self.reject and self.reject.match(url):
      return None

    parsed = urllib.parse.urlparse(url)
    domain = parsed.hostname
    if not domain:
      return None
    elif self.domain and not (domain == self.domain or
                              domain.endswith('.' + self.domain)):
      return None
    if domain.startswith('www.'):
      domain = domain[4:]
    if self.subdomain and domain.count('.') == 1:
      domain = '%s.%s' % (self.subdomain, domain)

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
