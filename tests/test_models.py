"""Unit tests for models.py.
"""
from future.types.newstr import newstr

from google.appengine.ext import db
from google.appengine.ext import ndb

from models import FutureModel, KeyNameModel, SingleEGModel, StringIdModel
from testutil_appengine import HandlerTest


class FutureModelTest(HandlerTest):

  def test_put(self):
    """
    newstr property values only seem to fail put() in dev_appserver, not in the
    local testbed, so this test isn't actually useful right now. ah well. :/
    """
    class MyModel(FutureModel):
      a_str = ndb.StringProperty()
      a_uni = ndb.StringProperty()
      a_newstr = ndb.StringProperty()
      a_null = ndb.StringProperty()
      a_float = ndb.FloatProperty()

    obj = MyModel(a_str=str('x'), a_uni=unicode('x'), a_newstr=newstr('x'),
                  a_float=1.23)
    key = obj.put()
    got = key.get()
    self.assertEqual('x', got.a_str)
    self.assertEqual('x', got.a_uni)
    self.assertEqual('x', got.a_newstr)
    self.assertEqual(unicode, got.a_newstr.__class__)
    self.assertEqual(1.23, got.a_float)
    self.assertIsNone(got.a_null)


class StringIdModelTest(HandlerTest):

  def test_put(self):
    self.assertEqual(ndb.Key('StringIdModel', 'x'),
                      StringIdModel(id='x').put())

    self.assertRaises(AssertionError, StringIdModel().put)
    self.assertRaises(AssertionError, StringIdModel(id=1).put)


class KeyNameModelTest(HandlerTest):

  def test_constructor(self):
    # with key name is ok
    entity = KeyNameModel(key_name='x')
    entity.save()
    db.get(entity.key())

    # without key name is not ok
    self.assertRaises(AssertionError, KeyNameModel)


class SingleEGModelTest(HandlerTest):

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
    self.assert_equals(key, self.Foo.get_by_id(key.id()).key())

    got = self.Foo.get_by_id(key.id(), parent=self.Foo.shared_parent_key())
    self.assert_equals(foo.key(), got.key())

    self.assertRaises(AssertionError, self.Foo.get_by_id, key.id(), parent=foo)

  def test_get_by_key_name(self):
    foo = self.Foo(key_name='foo')
    foo.save()
    self.assert_equals(foo.key(), self.Foo.get_by_key_name('foo').key())

    got = self.Foo.get_by_key_name('foo', parent=self.Foo.shared_parent_key())
    self.assert_equals(foo.key(), got.key())

    self.assertRaises(AssertionError, self.Foo.get_by_key_name, 'foo', parent=foo)

  def test_get_or_insert(self):
    # doesn't exist
    foo = self.Foo.get_or_insert(key_name='my name')

    # exists
    got = self.Foo.get_or_insert(key_name='my name')
    self.assert_equals(foo.key(), got.key())

    got = self.Foo.get_or_insert(key_name='my name',
                                 parent=self.Foo.shared_parent_key())
    self.assert_equals(foo.key(), got.key())

    self.assertRaises(AssertionError, self.Foo.get_or_insert,
                      key_name='my name', parent=foo)

  def test_all(self):
    """Unfortunately Query.list_index() only supports composite indices in the
    local file stub, so this test can only run in prod. Oh well.
    """
    query = self.Foo.all()
    query.fetch(1)
