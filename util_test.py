#!/usr/bin/python
"""Unit tests for util.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import unittest
from webob import exc

import testutil
import util
from util import KeyNameModel, SingleEGModel
import webapp2

from google.appengine.ext import db


class UtilTest(testutil.HandlerTest):

  def test_no_values(self):
    self.assertEqual('', util.to_xml({}))

  def test_flat(self):
    self.assertEqual("""
<a>3.14</a>\n<b>xyz</b>
""", util.to_xml({'a': 3.14, 'b': 'xyz'}))

  def test_none(self):
    self.assertEqual("""
<a></a>
""", util.to_xml({'a': None}))

  def test_empty_string(self):
    self.assertEqual("""
<a></a>
"""
, util.to_xml({'a': ''}))

  def test_empty_dict(self):
    self.assertEqual("""
<a></a>
"""
, util.to_xml({'a': {}}))

  def test_zero(self):
    self.assertEqual("""
<a>0</a>
"""
, util.to_xml({'a': 0}))

  def test_list(self):
    self.assertEqual("""
<a>1</a>
<a>2</a>
""", util.to_xml({'a': [1, 2]}))

  def test_nested(self):
    self.assertEqual("""
<a>
<b>
<c>x</c>
<d>y</d>
</b>
<e>2</e>
<e>3</e>
</a>
""", util.to_xml({'a': {'b': {'c': 'x', 'd': 'y'},
                        'e': (2, 3),
                        }}))

  def test_none(self):
    self.assertEqual(None, util.trim_nulls(None))

  def test_string(self):
    self.assertEqual('foo', util.trim_nulls('foo'))

  def test_empty_list(self):
    self.assertEqual([], util.trim_nulls([]))

  def test_empty_dict(self):
    self.assertEqual({}, util.trim_nulls({}))

  def test_simple_dict_with_nulls(self):
    self.assertEqual({}, util.trim_nulls({1: None, 2: [], 3: {}}))

  def test_simple_dict(self):
    self.assertEqual({1: 2, 3: 4}, util.trim_nulls({1: 2, 3: 4}))

  def test_simple_dict_with_nones(self):
    self.assertEqual({3: 4, 2: 9}, util.trim_nulls({1: None, 3: 4, 5: [], 2: 9}))

  def test_nested_dict_with_nones(self):
    self.assertEqual({1: {3: 4}}, util.trim_nulls({1: {2: [], 3: 4}, 5: {6: None}}))

  def test_urlfetch(self):
    self.expect_urlfetch('http://my/url', 'hello', method='foo')
    self.mox.ReplayAll()
    self.assertEquals('hello', util.urlfetch('http://my/url', method='foo'))

  def test_urlfetch_error_passes_through(self):
    self.expect_urlfetch('http://my/url', 'my error', status=408)
    self.mox.ReplayAll()

    try:
      util.urlfetch('http://my/url')
    except exc.HTTPException, e:
      self.assertEquals(408, e.status_int)
      self.assertEquals('my error', e.body_template_obj.template)

  def test_favicon_for_url(self):
    for url in ('http://a.org/b/c?d=e&f=g', 'https://a.org/b/c', 'http://a.org/'):
      self.assertEqual('http://a.org/favicon.ico', util.favicon_for_url(url))

  def test_domain_from_link(self):
    for good_link in 'asdf.com', 'https://asdf.com/', 'asdf.com/foo?bar#baz':
      self.assertEqual('asdf.com', util.domain_from_link(good_link), good_link)

    for bad_link in '', '  ', 'com', 'com.', 'a/b/c':
      self.assertRaises(exc.HTTPBadRequest, util.domain_from_link, bad_link)

  def test_parse_acct_uri(self):
    self.assertEquals(('me', 'x.com'), util.parse_acct_uri('acct:me@x.com'))

  def test_parse_acct_uri_allowed_domain(self):
    self.assertEquals(('me', 'x.com'),
                      util.parse_acct_uri('acct:me@x.com', ['x.com', 'y.com']))

  def test_parse_acct_uri_scheme_not_acct_error(self):
    self.assertRaises(ValueError, util.parse_acct_uri, 'mailto:me@x.com')

  def test_parse_acct_uri_bad_format_error(self):
    self.assertRaises(ValueError, util.parse_acct_uri, 'acct:foo')

  def test_parse_acct_uri_wrong_domain_error(self):
    self.assertRaises(ValueError,
                      util.parse_acct_uri, 'acct:me@a.com', ['x.com'])


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

