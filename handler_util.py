#!/usr/bin/python
"""Web handler utility functions.

The main value of these methods is that they catch exceptions and convert them
to the corresponding webob.exc exception with the appropriate HTTP status code.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import logging
import urllib2
from webob import exc

import util


def urlread(url, **kwargs):
  """Wraps urllib2.urlopen, returns body or raises exception.

  Args:
    url: str
    kwargs: passed through to urllib2.Request()

  Returns: the HTTP response body

  Raises: urllib2.HTTPError
  """
  logging.debug('Fetching %s', url)
  try:
    return urllib2.urlopen(urllib2.Request(url, **kwargs), timeout=999).read()
  except urllib2.HTTPError, e:
    raise exc.status_map[e.code](body_template=str(e))


def domain_from_link(url):
  try:
    return util.domain_from_link(url)
  except ValueError, e:
    raise exc.HTTPBadRequest(str(e))
