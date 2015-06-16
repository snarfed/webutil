"""Unit tests for models.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

from google.appengine.ext import db
from google.appengine.ext import ndb

from models import StringIdModel, KeyNameModel, SingleEGModel
import testutil


class StringIdModelTest(testutil.HandlerTest):

  def test_put(self):
    self.assertEquals(ndb.Key('StringIdModel', 'x'),
                      StringIdModel(id='x').put())

    self.assertRaises(AssertionError, StringIdModel().put)
    self.assertRaises(AssertionError, StringIdModel(id=1).put)


class KeyNameModelTest(testutil.HandlerTest):

  def test_constructor(self):
    # with key name is ok
    entity = KeyNameModel(key_name='x')
    entity.save()
    db.get(entity.key())

    # without key name is not ok
    self.assertRaises(AssertionError, KeyNameModel)


class SingleEGModelTest(testutil.HandlerTest):

  class Foo(SingleEGModel):
    pass

  def test_shared_parent_key(self):
    self.assertEqual(db.Key.from_path('Parent', 'Foo'),
                     self.Foo.shared_parent_key())

  def test_constructor(self):
    parent = self.Foo.shared_parent_key()
    self.assertEqual(parent, self.Foo().parent_key())
    self.assertEqual(parent, self.Foo(parent=parent).parent_key())

    other_parent = db.Key.from_path('Parent', 'foo')
    self.assertRaises(AssertionError, self.Foo, parent=other_parent)

  def test_get_by_id(self):
    foo = self.Foo()
    key = foo.save()
    self.assert_entities_equal(foo, self.Foo.get_by_id(key.id()))

    got = self.Foo.get_by_id(key.id(), parent=self.Foo.shared_parent_key())
    self.assert_entities_equal(foo, got)

    self.assertRaises(AssertionError, self.Foo.get_by_id, key.id(), parent=foo)

  def test_get_by_key_name(self):
    foo = self.Foo(key_name='foo')
    foo.save()
    self.assert_entities_equal(foo, self.Foo.get_by_key_name('foo'))

    got = self.Foo.get_by_key_name('foo', parent=self.Foo.shared_parent_key())
    self.assert_entities_equal(foo, got)

    self.assertRaises(AssertionError, self.Foo.get_by_key_name, 'foo', parent=foo)

  def test_get_or_insert(self):
    # doesn't exist
    foo = self.Foo.get_or_insert(key_name='my name')

    # exists
    got = self.Foo.get_or_insert(key_name='my name')
    self.assert_entities_equal(foo, got)

    got = self.Foo.get_or_insert(key_name='my name',
                                 parent=self.Foo.shared_parent_key())
    self.assert_entities_equal(foo, got)

    self.assertRaises(AssertionError, self.Foo.get_or_insert,
                      key_name='my name', parent=foo)

  def test_all(self):
    """Unfortunately Query.list_index() only supports composite indices in the
    local file stub, so this test can only run in prod. Oh well.
    """
    query = self.Foo.all()
    query.fetch(1)
