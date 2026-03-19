"""Unit tests for models.py.
"""
from datetime import datetime, timedelta, timezone
import enum
import warnings

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.cloud import ndb

import unittest.mock as mock

from ..models import EncryptedProperty, EnumProperty, Reloader, StringIdModel
from .. import appengine_config, models, testutil, util


class ReloaderTest(testutil.TestCase):

  def setUp(self):
    super().setUp()

    class Foo(StringIdModel):
      num = ndb.IntegerProperty()

    self.Foo = Foo
    with appengine_config.ndb_client.context():
      self.entity = Foo(id='x', num=4)
      self.entity.put()
    self.t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    self.reloader = Reloader(Foo, 'x', timedelta(minutes=5))

  def test_loads_on_first_access(self):
    with appengine_config.ndb_client.context():
      with mock.patch.object(util, 'now', return_value=self.t0):
        got = self.reloader.obj

    self.assertEqual(self.entity.key, got.key)
    self.assertEqual(self.t0, self.reloader.loaded_at)

  def test_returns_none_if_missing(self):
    reloader = Reloader(StringIdModel, 'missing', timedelta(minutes=5))
    with appengine_config.ndb_client.context():
      self.assertIsNone(reloader.obj)

  def test_caches_within_interval(self):
    with appengine_config.ndb_client.context():
      with mock.patch.object(util, 'now', return_value=self.t0):
        first = self.reloader.obj

      self.entity.key.delete()

      with mock.patch.object(util, 'now', return_value=self.t0 + timedelta(minutes=4)):
        second = self.reloader.obj

    self.assertIs(first, second)

  def test_reloads_after_interval(self):
    with appengine_config.ndb_client.context():
      with mock.patch.object(util, 'now', return_value=self.t0):
        self.reloader.obj

      self.entity.key.delete()

      t1 = self.t0 + timedelta(minutes=6)
      self.entity.num = 9
      self.entity.put()

      with mock.patch.object(util, 'now', return_value=t1):
        got = self.reloader.obj

    self.assertEqual(9, got.num)

  def test_reload(self):
    with appengine_config.ndb_client.context():
      with mock.patch.object(util, 'now', return_value=self.t0):
        self.reloader.obj

      self.entity.key.delete()
      self.entity.num = 9
      self.entity.put()

      t1 = self.t0 + timedelta(minutes=2)
      with mock.patch.object(util, 'now', return_value=t1):
        self.reloader.reload()

    self.assertEqual(9, self.reloader.obj.num)
    self.assertEqual(t1, self.reloader.loaded_at)


class StringIdModelTest(testutil.TestCase):

  def setUp(self):
    warnings.filterwarnings('ignore', module='google.auth',
      message='Your application has authenticated using end user credentials')

  def test_put(self):
    with appengine_config.ndb_client.context():
      self.assertEqual(ndb.Key(StringIdModel, 'x'),
                       StringIdModel(id='x').put())
      self.assertRaises(AssertionError, StringIdModel().put)
      self.assertRaises(AssertionError, StringIdModel(id=1).put)


class TestEnum(enum.Enum):
  FOO = 1
  BAR = 2


class EnumModel(ndb.Model):
  field = EnumProperty(TestEnum)


class EnumPropertyTest(testutil.TestCase):

  def test_init_non_enum(self):
    with self.assertRaises(TypeError):
      EnumProperty(str)

  def test_validate(self):
    with self.assertRaises(TypeError):
      EnumModel(field='not_an_enum').put()

  def test_round_trip(self):
    with appengine_config.ndb_client.context():
      entity = EnumModel()
      entity.put()
      self.assertIsNone(entity.key.get().field)

      entity.field = TestEnum.FOO
      entity.put()
      got = entity.key.get()
      self.assertEqual(TestEnum.FOO, got.field)
      self.assertEqual(1, got.field.value)

      entity.field = TestEnum.BAR
      entity.put()
      got = entity.key.get()
      self.assertEqual(TestEnum.BAR, got.field)
      self.assertEqual(2, got.field.value)


class EncryptedModel(ndb.Model):
  secret = EncryptedProperty()


class EncryptedPropertyTest(testutil.TestCase):
  def setUp(self):
    super().setUp()

    self.ndb_context = appengine_config.ndb_client.context()
    self.ndb_context.__enter__()

  def tearDown(self):
    self.ndb_context.__exit__(None, None, None)
    super().tearDown()

  def test_validate(self):
    with self.assertRaises(TypeError):
      EncryptedModel(secret=123).put()

    with self.assertRaises(TypeError):
      EncryptedModel(secret='string').put()

  def test_round_trip(self):
    entity = EncryptedModel(secret=b'seekret')
    entity.put()
    self.assertEqual(b'seekret', entity.key.get().secret)

    utf8 = 'émojis 🔐'.encode('utf-8')
    entity.secret = utf8
    entity.put()
    self.assertEqual(utf8, entity.key.get().secret)

  def test_encrypted_storage(self):
    test_secret = b'plaintext secret'
    entity = EncryptedModel(secret=test_secret)
    encrypted = EncryptedModel.secret._to_base_type(test_secret)

    self.assertIsInstance(encrypted, bytes)
    self.assertNotIn(test_secret, encrypted)
    self.assertEqual(12, len(encrypted[:12]))
    self.assertGreater(len(encrypted), 12 + len(test_secret))

    decrypted = EncryptedModel.secret._from_base_type(encrypted)
    self.assertEqual(test_secret, decrypted)

  def test_none_value(self):
    entity = EncryptedModel(secret=None)
    entity.put()
    self.assertIsNone(entity.key.get().secret)

  def test_no_key_error(self):
    self.mox.StubOutWithMock(models, 'ENCRYPTED_PROPERTY_KEY')
    models.ENCRYPTED_PROPERTY_KEY = None
    with self.assertRaises(RuntimeError) as cm:
      EncryptedModel(secret=b'test').put()
    self.assertIn('No encryption key found', str(cm.exception))

  def test_different_nonces(self):
    test_secret = b'same secret'
    prop = EncryptedModel.secret

    encrypted1 = prop._to_base_type(test_secret)
    encrypted2 = prop._to_base_type(test_secret)

    self.assertNotEqual(encrypted1, encrypted2)

    self.assertEqual(test_secret, prop._from_base_type(encrypted1))
    self.assertEqual(test_secret, prop._from_base_type(encrypted2))
