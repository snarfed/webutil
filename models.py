"""App Engine datastore model base classes, properties, and utilites.
"""
from collections import UserList

from google.cloud import ndb
from google.cloud.ndb.exceptions import BadValueError

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


class Unique:
  """ndb Property mixin class that acts like a set instead of a list.

  Specifically, de-duplicates elements with :class:`UniqueList` so that each
  distinct value appears at most once.
  """
  def __init__(self, *args, **kwargs):
    assert 'repeated' not in kwargs, f'{self.__class__} is always repeated'
    super().__init__(*args, repeated=True, **kwargs)

  def _store_value(self, entity, value):
    return super()._store_value(entity, UniqueList(value))


class StringSetProperty(Unique, ndb.StringProperty):
  """StringProperty that's repeated and de-duplicates elements."""


class KeySetProperty(Unique, ndb.KeyProperty):
  """KeyProperty that's repeated and de-duplicates elements."""


class UniqueList(UserList):
  """A list-compatible class that de-duplicates elements.

  Specifically, if an element is already in a UniqueList, inserting or appending
  it again has no effect.

  Not intended for large lists! Most operations are quadratic, ie O(n^2).

  Used in :class:`StringSetProperty`.
  """
  def __init__(self, val=None):
    super().__init__(val)
    self.dedupe()

  def append(self, val):
    super().append(val)
    self.dedupe()

  add = append

  def extend(self, val):
    super().extend(val)
    self.dedupe()

  update = extend

  def insert(self, i, val):
    super().insert(i, val)
    self.dedupe()

  def __setitem__(self, key, val):
    super().__setitem__(key, val)
    self.dedupe()

  def __add__(self, val):
    return UniqueList(super() + val)

  def __iadd__(self, val):
    super().__iadd__(val)
    self.dedupe()
    return self

  def dedupe(self):
    deduped = []

    # preserve order; don't use set or dict since ndb _BaseValue isn't hashable
    for elem in self.data:
      if elem not in deduped:
        deduped.append(elem)

    self.data = deduped


class AssignableSet(set):
  """A set-compatible class that allows assigning to a slice of the whole set.

  Eg this class allows x[:] = [...], which replaces the entire contents.
  """
  def __setitem__(self, key, val):
    if key == slice(None):
      val = set(val)
      self.clear()
      self.update(val)
      return

    return super().__setitem__(key, val)
