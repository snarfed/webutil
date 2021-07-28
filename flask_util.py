"""Utilities for Flask. View classes, decorators, URL route converters, etc."""
import logging
import os
import re

from flask import render_template, request
from flask.views import View
from google.cloud import ndb
from werkzeug.exceptions import abort, HTTPException
from werkzeug.routing import BaseConverter

from . import util

# Modern HTTP headers for CORS, CSP, other security, etc.
MODERN_HEADERS = {
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
}


class RegexConverter(BaseConverter):
  """Regexp URL route for Werkzeug/Flask.

  Based on https://github.com/rhyselsmore/flask-reggie.

  Usage:

    @app.route('/<regex("(abc|def)"):letters>')

  Install with:

    app = Flask(...)
    app.url_map.converters['regex'] = RegexConverter
  """
  def __init__(self, url_map, *items):
    super(RegexConverter, self).__init__(url_map)
    self.regex = items[0]


def get_required_param(name):
  """Returns the given request parameter.

  If it's not in a query parameter or POST field, the current HTTP request
  aborts with status 400.
  """
  try:
    val = request.values.get(name)
  except (UnicodeDecodeError, UnicodeEncodeError) as e:
    abort(400, f"Couldn't decode parameters as UTF-8: {e}")

  if not val:
    abort(400, f'Missing required parameter: {name}')

  return val


def ndb_context_middleware(app, client=None):
  """WSGI middleware to add an NDB context per request.

  Follows the WSGI standard. Details: http://www.python.org/dev/peps/pep-0333/

  Install with e.g.:

    application = handlers.ndb_context_middleware(webapp2.WSGIApplication(...)

  Background: https://cloud.google.com/appengine/docs/standard/python3/migrating-to-cloud-ndb#using_a_runtime_context_with_wsgi_frameworks

  Args:
    client: :class:`google.cloud.ndb.Client`
  """
  def wrapper(environ, start_response):
    if ndb.context.get_context(raise_context_error=False):
      # someone else (eg a unit test harness) has already created a context
      return app(environ, start_response)

    with client.context():
      return app(environ, start_response)

  return wrapper


def not_5xx(resp):
  """Returns False if resp is an HTTP 5xx, True otherwise.

  Useful to pass to flask-caching's `@cache.cached`'s `response_filter` kwarg to
  avoid caching 5xxes.

  Args:
    resp: :class:`flask.Response`

  Returns: boolean
  """
  return not (isinstance(resp, tuple) and len(resp) > 1 and
              util.is_int(resp[1]) and int(resp[1]) // 100 == 5)


def handle_exception(e):
  """Flask error handler that propagates HTTP exceptions into the response.

  Install with:
    app.register_error_handler(Exception, handle_exception)
  """
  code, body = util.interpret_http_exception(e)
  if code:
    return ((f'Upstream server request failed: {e}' if code in ('502', '504')
             else f'HTTP Error {code}: {body}'),
            int(code))

  logging.error(f'{e.__class__}: {e}')
  if isinstance(e, HTTPException):
    return e
  else:
    raise e


def default_modern_headers(resp):
  """Include modern HTTP headers by default, but let the response override them.

  Install with:
    app.after_request(default_modern_headers)
  """
  for name, value in MODERN_HEADERS.items():
    resp.headers.setdefault(name, value)

  return resp


class XrdOrJrd(View):
  """Renders and serves an XRD or JRD file.

  JRD is served if the request path ends in .jrd or .json, or the format query
  parameter is 'jrd' or 'json', or the request's Accept header includes 'jrd' or
  'json'.

  XRD is served if the request path ends in .xrd or .xml, or the format query
  parameter is 'xml' or 'xrd', or the request's Accept header includes 'xml' or
  'xrd'.

  Otherwise, defaults to DEFAULT_TYPE.

  Subclasses must override :meth:`template_prefix()` and
  :meth:`template_vars()`. URL route variables are passed through to
  :meth:`template_vars()` as keyword args.

  Class members:
    DEFAULT_TYPE: either JRD or XRD, which type to return by default if the
    request doesn't ask for one explicitly with the Accept header.
  """
  JRD = 'jrd'
  XRD = 'xrd'
  DEFAULT_TYPE = JRD  # either JRD or XRD

  def template_prefix(self):
    """Returns template filename, without extension."""
    raise NotImplementedError()

  def template_vars(self, **kwargs):
    """Returns a dict with template variables.

    URL route variables are passed through as kwargs.
    """
    raise NotImplementedError()

  def _type(self):
    """Returns XRD or JRD."""
    format = request.args.get('format', '').lower()
    ext = os.path.splitext(request.path)[1]

    if ext in ('.jrd', '.json') or format in ('jrd', 'json'):
      return self.JRD
    elif ext in ('.xrd', '.xml') or format in ('xrd', 'xml'):
      return self.XRD

    # We don't do full content negotiation (Accept Header parsing); we just
    # check whether jrd/json and xrd/xml are in the header, and if they both
    # are, which one comes first. :/
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Content_negotiation
    accept = request.headers.get('Accept', '').lower()
    jrd = re.search(r'jrd|json', accept)
    xrd = re.search(r'xrd|xml', accept)
    if jrd and (not xrd or jrd.start() < xrd.start()):
      return self.JRD
    elif xrd and (not jrd or xrd.start() < jrd.start()):
      return self.XRD

    assert self.DEFAULT_TYPE in (self.JRD, self.XRD)
    return self.DEFAULT_TYPE

  def dispatch_request(self, **kwargs):
    data = self.template_vars(**kwargs)
    if not isinstance(data, dict):
      return data

    # Content-Types are from https://tools.ietf.org/html/rfc7033#section-10.2
    if self._type() == self.JRD:
      return data, {'Content-Type': 'application/jrd+json'}
    else:
      template = f'{self.template_prefix()}.{self._type()}'
      return (render_template(template, **data),
              {'Content-Type': 'application/xrd+xml; charset=utf-8'})

