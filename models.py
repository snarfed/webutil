"""App Engine datastore model base classes, properties, and utilites."""
import base64
from datetime import timezone
import enum
import os
from google.cloud import ndb

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from oauth_dropins.webutil import util
from oauth_dropins.webutil.util import json_dumps, json_loads

# 1MB limit: https://cloud.google.com/datastore/docs/concepts/limits
# use this to check an entity's size:
#   len(entity._to_pb().Encode())
MAX_ENTITY_SIZE = 1 * 1000 * 1000

ENCRYPTED_PROPERTY_KEY = None
if key_base64 := util.read('encrypted_property_key'):  # base-64 encoded key bytes
  key_bytes = base64.b64decode(key_base64)
  assert len(key_bytes) == 32
  ENCRYPTED_PROPERTY_KEY = AESGCM(key_bytes)


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

    Stores the enum's integer value in the datastore.
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


class EncryptedProperty(ndb.BlobProperty):
    """Property that stores encrypted bytes.

    Encrypts bytes values using AES-256-GCM before storing in the datastore,
    and decrypts them when reading back.

    The AES-256-GCM key should be in the ``encrypted_property_key`` file, base64
    encoded. Here's example code to generate an AES-256-GCM key and base64 encode it:

      import base64
      from cryptography.hazmat.primitives.ciphers.aead import AESGCM

      key_bytes = AESGCM.generate_key(bit_length=256)
      print(base64.b64encode(key_bytes))
    """
    def _validate(self, value):
        if value is not None and not isinstance(value, bytes):
            raise TypeError('EncryptedProperty value must be bytes')

    def _to_base_type(self, value):
        if value is None:
            return None

        if not ENCRYPTED_PROPERTY_KEY:
            raise RuntimeError('No encryption key found in encrypted_property_key.pem')

        nonce = os.urandom(12)  # 96-bit nonce for GCM
        ciphertext = ENCRYPTED_PROPERTY_KEY.encrypt(nonce, value, None)

        # concatenate nonce and ciphertext for storage
        return nonce + ciphertext

    def _from_base_type(self, value):
        if value is None:
            return None

        if not ENCRYPTED_PROPERTY_KEY:
            raise RuntimeError('No encryption key found in encrypted_property_key.pem')

        nonce = value[:12]
        ciphertext = value[12:]
        return ENCRYPTED_PROPERTY_KEY.decrypt(nonce, ciphertext, None)


class Cache(ndb.Model):
    """Simple, dumb, datastore-backed key/value cache."""
    value = ndb.BlobProperty()
    expire = ndb.DateTimeProperty(tzinfo=timezone.utc)

    @classmethod
    def get(cls, key):
        """
        Args:
          key (str)

        Returns:
          str or None: value
        """
        if got := cls.get_by_id(key):
            if not got.expire or datetime.now(timezone.utc) < got.expire:
                return got.value.decode()

    @classmethod
    def put(cls, key, value, expire=None):
        """
        Args:
          key (str)
          value (str)
          expire (datetime.timedelta)
        """
        cached = cls(id=key, value=value.encode(),
                     expire=datetime.now(timezone.utc) + expire)
        super(cls, cached).put()
