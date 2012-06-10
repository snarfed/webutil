#!/usr/bin/python
"""Misc utilities.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import datetime
import logging
import urlparse
import webapp2

from google.appengine.api import urlfetch as gae_urlfetch
from google.appengine.ext import db


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


def tag_uri(domain, name):
  """Returns a tag URI string for the given domain and name.

  Example return value: 'tag:twitter.com,2012:snarfed_org/172417043893731329'

  Background on tag URIs: http://taguri.org/
  """
  return 'tag:%s,%d:%s' % (domain, datetime.datetime.now().year, name)


def favicon_for_url(url):
  return 'http://%s/favicon.ico' % urlparse.urlparse(url).netloc


class KeyNameModel(db.Model):
  """A model class that requires a key name."""

  def __init__(self, *args, **kwargs):
    """Raises AssertionError if key name is not provided."""
    super(KeyNameModel, self).__init__(*args, **kwargs)
    try:
      assert self.key().name()
    except db.NotSavedError:
      assert False, 'key name required but not provided'


class SingleEGModel(db.Model):
  """A model class that stores all entities in a single entity group.

  All entities use the same parent key (below), and all() automatically adds it
  as an ancestor. That allows, among other things, fetching all entities of
  this kind with strong consistency.
  """

  def __init__(self, *args, **kwargs):
    """Raises AssertionError if key name is not provided."""
    self.enforce_parent(kwargs)
    super(SingleEGModel, self).__init__(*args, **kwargs)

  @classmethod
  def shared_parent_key(cls):
    """Returns the shared parent key for this class.

    It's not actually an entity, just a placeholder key.
    """
    return db.Key.from_path('Parent', cls.kind())

  @classmethod
  def get_by_id(cls, id):
    return db.get(db.Key.from_path(cls.kind(), id, parent=cls.shared_parent_key()))

  get_by_key_name = get_by_id

  @classmethod
  def all(cls):
    return db.Query(cls).ancestor(cls.shared_parent_key())

  @classmethod
  def enforce_parent(cls, kwargs):
    """Sets the parent keyword arg. If it's already set, checks that it's correct."""
    if '_from_entity' in kwargs:
      return

    parent = cls.shared_parent_key()
    if 'parent' in kwargs:
      assert kwargs['parent'] == parent, "Can't override parent in SingleEGModel"
    kwargs['parent'] = parent
