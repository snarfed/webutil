#!/usr/bin/python
"""Misc utilities.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import logging
import urlparse
import webapp2

from google.appengine.api import urlfetch as gae_urlfetch


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
  """Recursively removes dict elements with None or empty values."""
  if isinstance(value, dict):
    return dict((k, trim_nulls(v)) for k, v in value.items() if trim_nulls(v))
  else:
    return value


def urlfetch(url, **kwargs):
  """Wraps urlfetch. Passes error responses through to the client.

  ...by raising HTTPException.

  Args:
    url: str
    kwargs: passed through to urlfetch.fetch()

  Returns:
    the HTTP response body
  """
  logging.debug('Fetching %s with kwargs %s', url, kwargs)
  resp = gae_urlfetch.fetch(url, deadline=999, **kwargs)

  if resp.status_code == 200:
    return resp.content
  else:
    logging.warning('GET %s returned %d:\n%s',
                    url, resp.status_code, resp.content)
    webapp2.abort(resp.status_code, body_template=resp.content,
                  headers=resp.headers)

def favicon_for_url(url):
  return 'http://%s/favicon.ico' % urlparse.urlparse(url).netloc
