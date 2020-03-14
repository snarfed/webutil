"""Request handler utility classes.

Includes classes for serving templates with common variables and XRD[S] and JRD
files like host-meta and friends.
"""
import calendar
import functools
import logging
import os
import threading
import urllib.parse

import cachetools
from google.cloud import ndb
import jinja2
import webapp2

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


def cache_response(expiration, size=20 * 1000 * 1000):  # 20 MB
  """:class:`webapp2.RequestHandler` method decorator that caches the response in memory.

  Includes a `cache_clear()` function that clears all cached responses.

  Ideally this would be just a thin wrapper around the
  :func:`cachetools.cachedmethod` decorator, but that doesn't pass `self` to the
  `key` function, which we need to get the request URL. Long discussion:
  https://github.com/tkem/cachetools/issues/107

  Args:
    expiration: :class:`datetime.timedelta`
    size: integer, bytes. defaults to 20 MB.
  """
  lock = threading.RLock()
  ttlcache = cachetools.TTLCache(
    size, expiration.total_seconds(),
    getsizeof=lambda response: len(response.body))

  def decorator(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
      cache = self.request.get('cache', '').lower() != 'false'
      if cache:
        resp = ttlcache.get(self.request.url)
        if resp:
          logging.info('Serving cached response')
          return resp

      resp = method(self, *args, **kwargs)
      if not resp:
        resp = self.response

      if cache:
        with lock:
          ttlcache[self.request.url] = resp

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
    for key in self.request.params:
      values = self.request.params.getall(key)
      if len(values) == 1:
        values = values[0]
      vars[key] = values

    vars.update(self.template_vars(*args, **kwargs))
    self.response.out.write(
      JINJA_ENV.get_template(self.template_file()).render(**vars))


class XrdOrJrdHandler(TemplateHandler):
  """Renders and serves an XRD or JRD file.

  JRD is served if the request path ends in .json, or the query parameters
  include 'format=json', or the request headers include
  'Accept: application/json'.

  Subclasses must override :meth:`template_prefix()`.

  Class members:
    JRD_TEMPLATE: boolean, renders JRD with a template if True,
    otherwise renders it as JSON directly.
  """
  JRD_TEMPLATE = True

  def get(self, *args, **kwargs):
    if self.JRD_TEMPLATE:
      return super(XrdOrJrdHandler, self).get(*args, **kwargs)

    self.response.headers['Content-Type'] = self.content_type()
    # can't update() because wsgiref.headers.Headers doesn't have it.
    for key, val in self.headers().items():
      self.response.headers[key] = val

    self.response.write(json_dumps(self.template_vars(*args, **kwargs), indent=2))

  def content_type(self):
    return ('application/json; charset=utf-8' if self.is_jrd()
            else 'application/xrd+xml; charset=utf-8')

  def template_prefix(self):
    """Returns template filename, without extension."""
    raise NotImplementedError()

  def template_file(self):
    return self.template_prefix() + ('.jrd' if self.is_jrd() else '.xrd')

  def is_jrd(self):
    """Returns True if JRD should be served, False if XRD."""
    return (os.path.splitext(self.request.path)[1] == '.json' or
            self.request.get('format') == 'json' or
            self.request.headers.get('Accept') == 'application/json')


class HostMetaHandler(XrdOrJrdHandler):
  """Renders and serves the /.well-known/host-meta file.
  """
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
