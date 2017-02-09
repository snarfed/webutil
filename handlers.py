"""Request handler utility classes.

Includes classes for serving templates with common variables and XRD[S] and JRD
files like host-meta and friends.
"""

import logging
import os
import urllib2
import urlparse

import appengine_config
from google.appengine.ext.webapp import template
from google.appengine.api import memcache
import jinja2
import webapp2

import util


def handle_exception(self, e, debug):
  """A webapp2 exception handler that propagates HTTP exceptions into the response.

  Use this as a :meth:`webapp2.RequestHandler.handle_exception()` method by
  adding this line to your handler class definition::

    handle_exception = handlers.handle_exception

  I originally tried to put this in a :class:`webapp2.RequestHandler` subclass,
  but it gave me this exception::

    File ".../webapp2-2.5.1/webapp2_extras/local.py", line 136, in _get_current_object
      raise RuntimeError('no object bound to %s' % self.__name__) RuntimeError: no object bound to app

  These are probably related:

  * http://eemyop.blogspot.com/2013/05/digging-around-in-webapp2-finding-out.html
  * http://code.google.com/p/webapp-improved/source/detail?r=d962ac4625ce3c43a3e59fd7fc07daf8d7b7c46a

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
  if isinstance(from_domain, basestring):
    from_domain = [from_domain]

  def decorator(method):
    def wrapper(self, *args, **kwargs):
      parts = list(urlparse.urlparse(self.request.url))
      # not using self.request.host because it includes port
      if parts[1] in from_domain:  # netloc
        parts[1] = to_domain
        return self.redirect(urlparse.urlunparse(parts), permanent=True)
      else:
        return method(self, *args)

    return wrapper

  return decorator


def memcache_response(expiration):
  """:class:`webapp2.RequestHandler` decorator that memcaches the response.

  Args:
    expiration: :class:`datetime.timedelta`
  """
  def decorator(method):
    def wrapper(self, *args, **kwargs):
      cache_key = 'memcache_response %s' % self.request.url
      cached = memcache.get(cache_key)
      if cached:
        logging.info('Serving cached response %r', cache_key)
        return cached

      resp = method(self, *args, **kwargs)

      logging.info('Caching response in %r', cache_key)
      memcache.set(cache_key, resp or self.response, expiration.total_seconds())

    return wrapper

  return decorator


class ModernHandler(webapp2.RequestHandler):
  """Base handler that adds modern open/secure headers like CORS, HSTS, etc."""
  def __init__(self, *args, **kwargs):
    super(ModernHandler, self).__init__(*args, **kwargs)
    self.response.headers.update({
      'Access-Control-Allow-Origin': '*',
      # see https://content-security-policy.com/
      'Content-Security-Policy':
        "script-src https: localhost:8080 'unsafe-inline'; "
        "frame-ancestors 'self'; "
        "report-uri /csp-report; ",
      # 16070400 seconds is 6 months
      'Strict-Transport-Security': 'max-age=16070400; includeSubDomains; preload',
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
  # set to True to use google.appengine.ext.webapp.template instead of jinja2
  USE_APPENGINE_WEBAPP = False

  def template_file(self):
    """Returns the string template file path."""
    raise NotImplementedError()

  def template_vars(self):
    """Returns a dict of template variable string keys and values."""
    return {}

  def content_type(self):
    """Returns the string content type."""
    return 'text/html; charset=utf-8'

  def headers(self):
    """Returns dict of HTTP response headers. Subclasses may override.

    To advertise XRDS, use::

      headers['X-XRDS-Location'] = 'https://%s/.well-known/host-meta.xrds' % appengine_config.HOST
    """
    return {
      'Cache-Control': 'max-age=300',
      'Access-Control-Allow-Origin': '*',
      }

  def get(self):
    self.response.headers['Content-Type'] = self.content_type()
    # can't update() because wsgiref.headers.Headers doesn't have it.
    for key, val in self.headers().items():
      self.response.headers[key] = val

    vars = {'host': appengine_config.HOST}

    # add query params. use a list for params with multiple values.
    for key in self.request.params:
      values = self.request.params.getall(key)
      if len(values) == 1:
        values = values[0]
      vars[key] = values

    vars.update(self.template_vars())

    if self.USE_APPENGINE_WEBAPP:
      self.response.out.write(template.render(self.template_file(), vars))
    else:
      env = jinja2.Environment(loader=jinja2.FileSystemLoader(('.', '/')),
                               autoescape=True)
      self.response.out.write(env.get_template(self.template_file()).render(**vars))


class XrdOrJrdHandler(TemplateHandler):
  """Renders and serves an XRD or JRD file.

  JRD is served if the request path ends in .json, or the query parameters
  include 'format=json', or the request headers include
  'Accept: application/json'.

  Subclasses must override :meth:`template_prefix()`.
  """
  def content_type(self):
    return 'application/json' if self.is_jrd() else 'application/xrd+xml'

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
