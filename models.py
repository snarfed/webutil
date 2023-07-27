"""App Engine datastore model base classes, properties, and utilites.
"""
from google.cloud import ndb

from oauth_dropins.webutil.util import json_dumps, json_loads


class StringIdModel(ndb.Model):
  """An ndb model class that requires a string id."""
  def put(self, *args, **kwargs):
    """Raises AssertionError if string id is not provided."""
    assert self.key and self.key.string_id(), 'string id required but not provided'
    return super(StringIdModel, self).put(*args, **kwargs)


class JsonProperty(ndb.TextProperty):
    """Fork of ndb's that subclasses TextProperty instead of BlobProperty.

    This makes values show up as normal, human-readable, serialized JSON in the
    web console.
    https://github.com/googleapis/python-ndb/issues/874#issuecomment-1442753255

    Duplicated in arroba:
    https://github.com/snarfed/arroba/blob/main/arroba/ndb_storage.py
    """
    def _validate(self, value):
        if not isinstance(value, dict):
            raise TypeError('JSON property must be a dict')

    def _to_base_type(self, value):
        as_str = json_dumps(value, separators=(',', ':'), ensure_ascii=True)
        return as_str.encode('ascii')

    def _from_base_type(self, value):
        if not isinstance(value, str):
            value = value.decode('ascii')
        return json_loads(value)


class ComputedJsonProperty(JsonProperty, ndb.ComputedProperty):
    """Custom ComputedProperty for JSON values that stores them as strings.

    ...instead of like StructuredProperty, with "entity" type, which bloats them
    unnecessarily in the datastore.
    """
    def __init__(self, *args, **kwargs):
        kwargs['indexed'] = False
        super().__init__(*args, **kwargs)
