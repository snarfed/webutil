"""Unit tests for models.py.
"""
import warnings

from google.cloud import ndb
from google.cloud.ndb.exceptions import BadValueError

from ..models import AssignableSet, StringIdModel, StringSetProperty, UniqueList
from .. import appengine_config, testutil


class ModelTest(testutil.TestCase):

  def setUp(self):
    super().setUp()

    warnings.filterwarnings('ignore', module='google.auth',
      message='Your application has authenticated using end user credentials')

    self.ndb_context = appengine_config.ndb_client.context()
    self.ndb_context.__enter__()

  def tearDown(self):
    self.ndb_context.__exit__(None, None, None)
    super().tearDown()

  def test_StringIdModel_put(self):
    self.assertEqual(ndb.Key(StringIdModel, 'x'),
                     StringIdModel(id='x').put())
    self.assertRaises(AssertionError, StringIdModel().put)
    self.assertRaises(AssertionError, StringIdModel(id=1).put)

  def test_UniqueList(self):
    l = UniqueList(['x', 'y', 'x'])
    self.assertCountEqual(['x', 'y'], l)

    l[:] = ['a', 'b', 'a']
    self.assertIsInstance(l, UniqueList)
    self.assertCountEqual(['a', 'b'], l)

    l.append('a')
    l.append('c')
    l += ['c', 'c', 'd', 'a']
    l.remove('a')
    l.extend(['e', 'b'])
    self.assertIsInstance(l, UniqueList)
    self.assertCountEqual(['b', 'c', 'd', 'e'], l, l)

  def test_AssignableSet(self):
    s = AssignableSet(['x', 'y'])

    s[:] = ['a', 'b']
    self.assertIsInstance(s, AssignableSet)
    self.assertEqual({'a', 'b'}, s)

    s.add('c')
    s.remove('a')
    s |= {'d', 'b'}
    self.assertIsInstance(s, AssignableSet)
    self.assertEqual({'b', 'c', 'd'}, s)

  def test_StringSetProperty(self):
    class Foo(ndb.Model):
      x = StringSetProperty()

    f = Foo(x=['a', 'b', 'a'])
    self.assertEqual(['a', 'b'], f.x)

    f = f.put().get()
    self.assertEqual(['a', 'b'], f.x)

    f.x.add('a')
    f.x.add('c')
    f.x.remove('a')
    f.x.update({'d', 'b'})
    self.assertEqual(['b', 'c', 'd'], f.x)

    f = f.put().get()
    self.assertEqual(['b', 'c', 'd'], f.x)

    g = Foo(x=f.x)
    g = g.put().get()
    self.assertEqual(f.x, g.x)
