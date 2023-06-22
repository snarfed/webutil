"""Utilities for Flask. View classes, decorators, URL route converters, etc."""
import functools
import logging
import os
import re
import urllib.parse

import flask
from flask import abort, get_flashed_messages, make_response, redirect, render_template, request
from flask.views import View
from google.cloud import ndb
import werkzeug.exceptions
from werkzeug.exceptions import BadRequestKeyError, HTTPException
from werkzeug.routing import BaseConverter

from . import util

logger = logging.getLogger(__name__)

# Modern HTTP headers for CORS, CSP, other security, etc.
MODERN_HEADERS = {
  'Access-Control-Allow-Headers': '*',
  'Access-Control-Allow-Methods': '*',
  'Access-Control-Allow-Origin': '*',
  # see https://content-security-policy.com/
  'Content-Security-Policy':
    "script-src https: localhost:8080 my.dev.com:8080 'unsafe-inline'; "
    "frame-ancestors 'self'; ",
  # 16070400 seconds is 6 months
  'Strict-Transport-Security': 'max-age=16070400; preload',
  'X-Content-Type-Options': 'nosniff',
  # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
  'X-Frame-Options': 'SAMEORIGIN',
  'X-XSS-Protection': '1; mode=block',
}


# A few extra non-error HTTPExceptions
class Created(HTTPException):
    code = 201
    description = 'Created'

class Accepted(HTTPException):
    code = 202
    description = 'Accepted'

class NoContent(HTTPException):
    code = 204
    description = 'No Content'

class Redirect(HTTPException):
    def __init__(self, *args, location=None, **kwargs):
      assert location
      self.location = location
      super().__init__(**kwargs)

    def get_headers(self, *args, **kwargs):
      return {'Location': self.location}

class MovedPermanently(Redirect):
    code = 301
    description = 'Moved Permanently'

class Found(Redirect):
    code = 302
    description = 'Found'

class NotModified(HTTPException):
    code = 304
    description = 'Not Modified'

class PaymentRequired(HTTPException):
    code = 402
    description = 'Payment Required'

class ProxyAuthenticationRequired(HTTPException):
    code = 407
    description = 'Proxy Authentication Required'

class MisdirectedRequest(HTTPException):
    code = 421
    description = 'Misdirected Request'

class UpgradeRequired(HTTPException):
    code = 426
    description = 'Upgrade Required'

class PreconditionRequired(HTTPException):
    code = 428
    description = 'Precondition Required'

class ClientClosedRequest(HTTPException):
    code = 499
    description = 'Client Closed Request'

class VariantAlsoNegotiates(HTTPException):
    code = 506
    description = 'Variant Also Negotiates'

class InsufficientStorage(HTTPException):
    code = 507
    description = 'Insufficient Storage'

class LoopDetected(HTTPException):
    code = 508
    description = 'Loop Detected'

class NotExtended(HTTPException):
    code = 510
    description = 'Not Extended'

class NetworkAuthenticationRequired(HTTPException):
    code = 511
    description = 'Network Authentication Required'

class NetworkConnectTimeoutError(HTTPException):
    code = 599
    description = 'Network Connect Timeout Error'


for cls in (
    Created,
    Accepted,
    NoContent,
    MovedPermanently,
    Found,
    NotModified,
    PaymentRequired,
    ProxyAuthenticationRequired,
    MisdirectedRequest,
    UpgradeRequired,
    PreconditionRequired,
    ClientClosedRequest,
    VariantAlsoNegotiates,
    InsufficientStorage,
    LoopDetected,
    NotExtended,
    NetworkAuthenticationRequired,
    NetworkConnectTimeoutError,
):
  # https://github.com/pallets/flask/issues/1837#issuecomment-304996942
  werkzeug.exceptions.default_exceptions.setdefault(cls.code, cls)
  werkzeug.exceptions._aborter.mapping.setdefault(cls.code, cls)


class RegexConverter(BaseConverter):
  """Regexp URL route for Werkzeug/Flask.

  Based on https://github.com/rhyselsmore/flask-reggie.

  Usage:

    @app.route('/<regex("abc|def"):letters>')

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


def ndb_context_middleware(app, client=None, **kwargs):
  """WSGI middleware to add an NDB context per request.

  Follows the WSGI standard. Details: http://www.python.org/dev/peps/pep-0333/

  Install with e.g.:

    ndb_client = ndb.Client()
    app = Flask('my-app')
    app.wsgi_app = flask_util.ndb_context_middleware(app.wsgi_app, ndb_client)

  Background: https://cloud.google.com/appengine/docs/standard/python3/migrating-to-cloud-ndb#using_a_runtime_context_with_wsgi_frameworks

  Args:
    client: :class:`google.cloud.ndb.Client`
    kwargs: passed through to :meth:`google.cloud.ndb.Client.context`
  """
  def wrapper(environ, start_response):
    if ndb.context.get_context(raise_context_error=False):
      # someone else (eg a unit test harness) has already created a context
      return app(environ, start_response)

    with client.context(**kwargs):
      return app(environ, start_response)

  return wrapper


def handle_exception(e):
  """Flask error handler that propagates HTTP exceptions into the response.

  Install with:
    app.register_error_handler(Exception, handle_exception)
  """
  if isinstance(e, BadRequestKeyError):
      if e.args:
          e._description = f'Missing required parameter: {e.args[0]}'
      else:
          e.show_exception = True

  logger.error(f'{e.__class__}: {e}')

  if isinstance(e, HTTPException):
    # raised by this app itself, pass it through. use body and headers from
    # response if available (but not status code).
    resp = e.get_response()
    if resp:
      resp.status_code = e.code
      return resp
    else:
      return str(e), e.code

  code, body = util.interpret_http_exception(e)
  if code:
    return ((f'Upstream server request failed: {e}' if code in ('502', '504')
             else f'HTTP Error {code}: {body}'),
            int(code),
            {'Content-Type': 'text/plain; charset=utf-8'})

  raise e


def error(msg, status=400, exc_info=False, **kwargs):
  """Logs and returns an HTTP error via :class:`werkzeug.exceptions.HTTPException`.

  Args:
    msg: str
    status: int
    exc_info: Python exception info three-tuple, eg from sys.exc_info()
    kwargs: passed through to :func:`flask.abort`
  """
  logger.info(f'Returning {status}: {msg} {kwargs}', exc_info=exc_info)
  abort(int(status), msg, **kwargs)


def flash(msg, **kwargs):
  """Wrapper for :func:`flask.flash` that also logs the message."""
  flask.flash(msg, **kwargs)
  logger.info(f'Flashed message: {msg}')


def default_modern_headers(resp):
  """Include modern HTTP headers by default, but let the response override them.

  Install with:
    app.after_request(default_modern_headers)
  """
  for name, value in MODERN_HEADERS.items():
    resp.headers.setdefault(name, value)

  return resp


def cached(cache, timeout, headers=(), http_5xx=False):
  """Thin flask-cache wrapper that supports timedelta and cache query param.

  If the `cache` URL query parameter is `false`, skips the cache. Also, does not
  store the response in the cache if it's an HTTP 5xx or if there are any
  flashed messages.

  Args:
    cache: :class:`flask_caching.Cache`
    timeout: :class:`datetime.timedelta`
    headers: sequence of str, optional headers to include in the cache key
    http_5xx: bool, optional, whether to cache HTTP 5xx (server error) responses
  """
  def response_filter(resp):
    """Return False if the response shouldn't be cached."""
    resp = make_response(resp)
    return (not get_flashed_messages() and 'Set-Cookie' not in resp.headers and
            (http_5xx or resp.status_code // 100 != 5))

  def unless():
    return bool(request.args.get('cache', '').lower() == 'false' or
                request.cookies)

  def decorator(f):
    # catch werkzeug HTTPExceptions, eg raised by abort(), and return them
    # instead of letting them propagate, so that flask-cache can cache them
    @functools.wraps(f)
    def httpexception_to_return(*args, **kwargs):
      try:
        return f(*args, **kwargs)
      except HTTPException as e:
        return e

    decorated = cache.cached(timeout.total_seconds(), query_string=True,
                             response_filter=response_filter, unless=unless
                             )(httpexception_to_return)

    # include specified headers in cache key:
    # https://flask-caching.readthedocs.io/en/latest/api.html#flask_caching.Cache.cached
    orig_cache_key = decorated.make_cache_key
    def make_cache_key(*args, **kwargs):
      header_vals = '  '.join(request.headers.get(h, '') for h in sorted(headers))
      k = f'{orig_cache_key(*args, **kwargs)}  {header_vals}'
      if request.method != 'GET':
        k = f'{request.method} {k}'
      return k

    decorated.make_cache_key = make_cache_key

    return decorated

  return decorator


def canonicalize_domain(from_domains, to_domain):
  """Returns a callable that redirects one or more domains to a canonical domain.

  Preserves scheme, path, and query.

  Install with eg:

    app = flask.Flask(...)
    app.before_request(canonicalize_domain(('old1.com', 'old2.org'), 'new.com'))

  Args:
    from_domains: str or sequence of str
    to_domain: str
  """
  if isinstance(from_domains, str):
    from_domains = [from_domains]

  def fn():
    parts = list(urllib.parse.urlparse(request.url))
    # not using request.host because it includes port
    if parts[1] in from_domains:  # netloc
      parts[1] = to_domain
      return redirect(urllib.parse.urlunparse(parts), code=301)

  return fn


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
    assert isinstance(data, dict)

    # Content-Types are from https://tools.ietf.org/html/rfc7033#section-10.2
    if self._type() == self.JRD:
        return data, {'Content-Type': 'application/jrd+json'}

    template = f'{self.template_prefix()}.{self._type()}'
    return (render_template(template, **data),
            {'Content-Type': 'application/xrd+xml; charset=utf-8'})
