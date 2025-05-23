"""App Engine datastore model base classes, properties, and utilites.
"""
import enum
from google.cloud import ndb

from oauth_dropins.webutil.util import json_dumps, json_loads

# 1MB limit: https://cloud.google.com/datastore/docs/concepts/limits
# use this to check an entity's size:
#   len(entity._to_pb().Encode())
MAX_ENTITY_SIZE = 1 * 1000 * 1000


class StringIdModel(ndb.Model):
  """An :class:`ndb.Model` class that requires a string id."""
  def put(self, *args, **kwargs):
    """Raises AssertionError if string id is not provided."""
    assert self.key and self.key.string_id(), 'string id required but not provided'
    return super(StringIdModel, self).put(*args, **kwargs)


class JsonProperty(ndb.TextProperty):
    """Fork of ndb's that subclasses :class:`ndb.TextProperty` instead of :class:`ndb.BlobProperty`.

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
    """Custom :class:`ndb.ComputedProperty` for JSON values that stores them as
    strings.

    ...instead of like :class:`ndb.StructuredProperty`, with "entity" type,
    which bloats them unnecessarily in the datastore.
    """
    def __init__(self, *args, **kwargs):
        kwargs['indexed'] = False
        super().__init__(*args, **kwargs)


class EnumProperty(ndb.IntegerProperty):
    """Property for storing Python Enum values.

    Stores the enum's value in the datastore.
    """
    def __init__(self, enum_class, **kwargs):
        if not issubclass(enum_class, enum.Enum):
            raise TypeError('enum_class must be a subclass of enum.Enum')
        self._enum_class = enum_class
        super().__init__(**kwargs)

    def _validate(self, value):
        if value is not None and not isinstance(value, self._enum_class):
            raise TypeError(f'Expected {self._enum_class.__name__}, got {type(value).__name__}')

    def _to_base_type(self, value):
        if value is None:
            return None
        return value.value

    def _from_base_type(self, value):
        if value is None:
            return None
        return next((item for item in self._enum_class if item.value == value), None)
