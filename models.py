"""App Engine datastore model base classes and utilites.
"""
import functools

from google.cloud import ndb


class StringIdModel(ndb.Model):
  """An ndb model class that requires a string id."""
  def put(self, *args, **kwargs):
    """Raises AssertionError if string id is not provided."""
    assert self.key and self.key.string_id(), 'string id required but not provided'
    return super(StringIdModel, self).put(*args, **kwargs)
