"""Request handler utility classes.

Includes classes for serving templates with common variables and XRD[S] and JRD
files like host-meta and friends.
"""
import calendar
import datetime
import functools
import logging
import os
import re
import threading
import urllib.parse

import cachetools
from google.cloud import ndb
import jinja2
import webapp2
from webob import exc

from . import util
from .util import json_dumps, json_loads

JINJA_ENV = jinja2.Environment(
  loader=jinja2.FileSystemLoader(('.', 'templates')),
  autoescape=True,
)
JINJA_ENV.globals.update({
  'EPOCH': util.EPOCH,
  'timestamp': lambda dt: calendar.timegm(dt.utctimetuple()),
})


def handle_exception(self, e, debug):
  """A webapp2 exception handler that propagates HTTP exceptions into the response.

  Use this as a :meth:`webapp2.RequestHandler.handle_exception()` method by
  adding this line to your handler class definition::

    handle_exception = handlers.handle_exception
  """
  code, body = util.interpret_http_exception(e)
  if code:
    self.response.set_status(int(code))
    self.response.write('Upstream server request failed: %s' % e
                        if code in ('502', '504')
                        else 'HTTP Error %s: %s' % (code, body))
  else:
    raise


def redirect(from_domain, to_domain):
  """:class:`webapp2.RequestHandler` decorator that 301 redirects to a new domain.

  Preserves scheme, path, and query.

  Args:
    from_domain: string or sequence of strings
    to_domain: strings
  """
  if isinstance(from_domain, str):
    from_domain = [from_domain]

  def decorator(method):
    def wrapper(self, *args, **kwargs):
      parts = list(urllib.parse.urlparse(self.request.url))
      # not using self.request.host because it includes port
      if parts[1] in from_domain:  # netloc
        parts[1] = to_domain
        return self.redirect(urllib.parse.urlunparse(parts), permanent=True)
      else:
        return method(self, *args, **kwargs)

    return wrapper

  return decorator


def cache_response(expiration,
                   size=20 * 1000 * 1000,  # 20 MB
                   headers=None):
  """:class:`webapp2.RequestHandler` method decorator that caches the response in memory.

  Includes a `cache_clear()` function that clears all cached responses.

  Ideally this would be just a thin wrapper around the
  :func:`cachetools.cachedmethod` decorator, but that doesn't pass `self` to the
  `key` function, which we need to get the request URL. Long discussion:
  https://github.com/tkem/cachetools/issues/107

  Args:
    expiration: :class:`datetime.timedelta`
    size: integer, bytes. defaults to 20 MB.
    headers: sequencey of string HTTP headers to include in the cache key
  """
  lock = threading.RLock()
  ttlcache = cachetools.TTLCache(
    size, expiration.total_seconds(),
    getsizeof=lambda response: len(response.body))

  def decorator(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
      key = self.request.url
      if headers:
        key += ' ' + repr(sorted(
          (h, v) for h, v in self.request.headers.items() if h in headers))

      cache = self.request.get('cache', '').lower() != 'false'
      if cache:
        resp = ttlcache.get(key)
        if resp:
          logging.info('Serving cached response')
          return resp

      resp = method(self, *args, **kwargs)
      if not resp:
        resp = self.response

      if cache and ttlcache.getsizeof(resp) <= size:
        with lock:
          ttlcache[key] = resp

      return resp

    wrapper.cache_clear = ttlcache.clear
    return wrapper

  return decorator


def throttle(one_request_each, cache_size=5000):
  """:class:`webapp2.RequestHandler` method decorator that rate limits requests.

  Accepts at most one request with a given URL (including query parameters)
  within each `one_request_each` time period. After that, serves a HTTP 429
  response to each subsequent request for the same URL until the time period
  finished.

  Args:
    one_request_each: :class:`datetime.timedelta`
    cache_size: integer, number of URLs to cache. defaults to 5000.
  """
  lock = threading.RLock()
  ttlcache = cachetools.TTLCache(cache_size, one_request_each.total_seconds())

  def decorator(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
      if self.request.url in ttlcache:
        logging.info('Throttling repeated request for this URL; returning HTTP 429')
        raise exc.HTTPTooManyRequests("Too many requests for this URL. Please reduce your polling rate.")

      resp = method(self, *args, **kwargs)
      if not resp:
        resp = self.response

      with lock:
        ttlcache[self.request.url] = True

      return resp

    wrapper.cache_clear = ttlcache.clear
    return wrapper

  return decorator


def ndb_context_middleware(app, client=None):
  """WSGI middleware for per request instance info instrumentation.

  Follows the WSGI standard. Details: http://www.python.org/dev/peps/pep-0333/

  Install with e.g.:

    application = handlers.ndb_context_middleware(webapp2.WSGIApplication(...)

  Args:
    client: :class:`google.cloud.ndb.Client`
  """
  def wrapper(environ, start_response):
    with client.context():
      return app(environ, start_response)

  wrapper.get_response = app.get_response
  return wrapper


class ModernHandler(webapp2.RequestHandler):
  """Base handler that adds modern open/secure headers like CORS, HSTS, etc."""
  handle_exception = handle_exception

  def __init__(self, *args, **kwargs):
    super(ModernHandler, self).__init__(*args, **kwargs)
    self.response.headers.update({
      'Access-Control-Allow-Headers': '*',
      'Access-Control-Allow-Methods': '*',
      'Access-Control-Allow-Origin': '*',
      # see https://content-security-policy.com/
      'Content-Security-Policy':
        "script-src https: localhost:8080 my.dev.com:8080 'unsafe-inline'; "
        "frame-ancestors 'self'; "
        "report-uri /csp-report; ",
      # 16070400 seconds is 6 months
      'Strict-Transport-Security': 'max-age=16070400; preload',
      'X-Content-Type-Options': 'nosniff',
      # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
      'X-Frame-Options': 'SAMEORIGIN',
      'X-XSS-Protection': '1; mode=block',
    })

  def options(self, *args, **kwargs):
    """Respond to CORS pre-flight OPTIONS requests."""
    pass


class TemplateHandler(ModernHandler):
  """Renders and serves a template based on class attributes.

  Subclasses must override :meth:`template_file()` and may also override
  :meth:`template_vars()` and :meth:`content_type()`.
  """
  def template_file(self):
    """Returns the string template file path."""
    raise NotImplementedError()

  def template_vars(self, *args, **kwargs):
    """Returns a dict of template variable string keys and values.

    Args:
      args, kwargs: passed through from get()
    """
    return {}

  def content_type(self):
    """Returns the string content type."""
    return 'text/html; charset=utf-8'

  def headers(self):
    """Returns dict of HTTP response headers. Subclasses may override.

    To advertise XRDS, use::

      headers['X-XRDS-Location'] = 'https://%s/.well-known/host-meta.xrds' % self.request.host
    """
    return {
      'Cache-Control': 'max-age=300',
      'Access-Control-Allow-Origin': '*',
      }

  def get(self, *args, **kwargs):
    self.response.headers['Content-Type'] = self.content_type()
    # can't update() because wsgiref.headers.Headers doesn't have it.
    for key, val in list(self.headers().items()):
      self.response.headers[key] = val

    vars = {
      'host': self.request.host,
      'host_uri': self.request.host_url,
    }

    # add query params. use a list for params with multiple values.
    try:
      for key in self.request.params:
        values = self.request.params.getall(key)
        if len(values) == 1:
          values = values[0]
        vars[key] = values
    except UnicodeDecodeError as e:
      logging.warning('Bad query param', exc_info=True)
      self.response.status = 400
      self.response.write("Couldn't decode query parameters as UTF-8")
      return

    vars.update(self.template_vars(*args, **kwargs))
    self.response.out.write(
      JINJA_ENV.get_template(self.template_file()).render(**vars))


class XrdOrJrdHandler(TemplateHandler):
  """Renders and serves an XRD or JRD file.

  JRD is served if the request path ends in .jrd or .json, or the format query
  parameter is 'jrd' or 'json', or the request's Accept header includes 'jrd' or
  'json'.

  XRD is served if the request path ends in .xrd or .xml, or the format query
  parameter is 'xml' or 'xrd', or the request's Accept header includes 'xml' or
  'xrd'.

  Otherwise, defaults to DEFAULT_TYPE.

  Subclasses must override :meth:`template_prefix()`.

  Class members:
    DEFAULT_TYPE: either JRD or XRD, which type to return by default if the
      request doesn't ask for one explicitly with the Accept header.
    JRD_TEMPLATE: boolean, renders JRD with a template if True,
      otherwise renders it as JSON directly.
  """
  JRD = 'jrd'
  XRD = 'xrd'
  DEFAULT_TYPE = JRD  # either JRD or XRD
  JRD_TEMPLATE = True

  def _type(self):
    """Returns XRD or JRD."""
    format = self.request.get('format', '').lower()
    ext = os.path.splitext(self.request.path)[1]

    if ext in ('.jrd', '.json') or format in ('jrd', 'json'):
      return self.JRD
    elif ext in ('.xrd', '.xml') or format in ('xrd', 'xml'):
      return self.XRD

    # We don't do full content negotiation (Accept Header parsing); we just
    # check whether jrd/json and xrd/xml are in the header, and if they both
    # are, which one comes first. :/
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Content_negotiation
    accept = self.request.headers.get('Accept', '').lower()
    jrd = re.search(r'jrd|json', accept)
    xrd = re.search(r'xrd|xml', accept)
    if jrd and (not xrd or jrd.start() < xrd.start()):
      return self.JRD
    elif xrd and (not jrd or xrd.start() < jrd.start()):
      return self.XRD

    assert self.DEFAULT_TYPE in (self.JRD, self.XRD)
    return self.DEFAULT_TYPE

  def get(self, *args, **kwargs):
    if self.JRD_TEMPLATE or self._type() == self.XRD:
      return super(XrdOrJrdHandler, self).get(*args, **kwargs)

    self.response.headers['Content-Type'] = self.content_type()
    # can't update() because wsgiref.headers.Headers doesn't have it.
    for key, val in self.headers().items():
      self.response.headers[key] = val

    self.response.write(json_dumps(self.template_vars(*args, **kwargs), indent=2))

  def content_type(self):
    # https://tools.ietf.org/html/rfc7033#section-10.2
    return ('application/jrd+json' if self._type() == self.JRD
            else 'application/xrd+xml; charset=utf-8')

  def template_prefix(self):
    """Returns template filename, without extension."""
    raise NotImplementedError()

  def template_file(self):
    return f'{self.template_prefix()}.{self._type()}'


class HostMetaHandler(XrdOrJrdHandler):
  """Renders and serves the /.well-known/host-meta file.

  Supports both JRD and XRD; defaults to XRD.
  https://tools.ietf.org/html/rfc6415#section-3
  """
  DEFAULT_TYPE = XrdOrJrdHandler.XRD

  def template_prefix(self):
    return 'templates/host-meta'


class HostMetaXrdsHandler(TemplateHandler):
  """Renders and serves the /.well-known/host-meta.xrds XRDS-Simple file.
  """
  def content_type(self):
    return 'application/xrds+xml'

  def template_file(self):
    return 'templates/host-meta.xrds'


HOST_META_ROUTES = [
  ('/\.well-known/host-meta(?:\.json)?', HostMetaHandler),
  ('/\.well-known/host-meta.xrds', HostMetaXrdsHandler),
  ]
