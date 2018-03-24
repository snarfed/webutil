"""Monkey patch in a few python-future bug fixes.

(I tried telling setup.py to use my fork on github instead, with
dependency_links=, but that requires users to install with pip install
--process-dependency_links, which I don't want to depend on.)
"""
from future.utils import PY2

if PY2:
  # A few httplib constants that aren't available on App Engine.
  # https://github.com/PythonCharmers/python-future/pull/321
  import httplib
  if not hasattr(httplib, '_CS_IDLE'):
    httplib._CS_IDLE = 'Idle'
  if not hasattr(httplib, '_CS_REQ_STARTED'):
    httplib._CS_REQ_STARTED = 'Request-started'
  if not hasattr(httplib, '_CS_REQ_SENT'):
    httplib._CS_REQ_SENT = 'Request-sent'

  # https://github.com/PythonCharmers/python-future/pull/331
  def _coerce(obj):
    return (unicode(obj) if isinstance(obj, basestring)
            else [_coerce(elem) for elem in obj] if isinstance(obj, (list, tuple, set))
            else {k: _coerce(v) for k, v in obj.items()} if isinstance(obj, dict)
            else obj)

  orig = {}
  def wrapper(name):
    def wrapped(*args, **kwargs):
      return orig[name](*_coerce(args), **_coerce(kwargs))
    return wrapped

  from future.backports.urllib import parse
  for name in ('urlparse', 'urlunparse', 'urlsplit', 'urlunsplit', 'urljoin',
               'urldefrag', 'parse_qsl'):
    orig[name] = getattr(parse, name)
    setattr(parse, name, wrapper(name))
