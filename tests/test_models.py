"""Unit tests for models.py.
"""
import enum
import warnings

from google.cloud import ndb

from ..models import EnumProperty, StringIdModel
from .. import appengine_config, testutil


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
  enum_field = EnumProperty(TestEnum)
  optional_enum = EnumProperty(TestEnum, required=False)


class EnumPropertyTest(testutil.TestCase):

  def setUp(self):
    warnings.filterwarnings('ignore', module='google.auth',
      message='Your application has authenticated using end user credentials')

  def test_init_non_enum(self):
    with self.assertRaises(TypeError):
      EnumProperty(str)

  def test_validate(self):
    with self.assertRaises(TypeError):
      EnumModel(enum_field='not_an_enum').put()

  def test_round_trip(self):
    with appengine_config.ndb_client.context():
      entity = EnumModel(enum_field=TestEnum.FOO)
      key = entity.put()

      retrieved = key.get()
      self.assertEqual(TestEnum.FOO, retrieved.enum_field)
      self.assertEqual(1, retrieved.enum_field.value)  # Check the stored value
      self.assertIsNone(retrieved.optional_enum)

      entity.enum_field = TestEnum.BAR
      entity.optional_enum = TestEnum.FOO
      entity.put()

      retrieved = key.get()
      self.assertEqual(TestEnum.BAR, retrieved.enum_field)
      self.assertEqual(2, retrieved.enum_field.value)  # Check the stored value
      self.assertEqual(TestEnum.FOO, retrieved.optional_enum)
      self.assertEqual(1, retrieved.optional_enum.value)  # Check the stored value
