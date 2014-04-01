# -*- coding: utf-8 -*-
"""Unit tests for util.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import datetime
import urlparse
from webob import exc

import testutil
import util
import webapp2


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

  def test_list_container(self):
    self.assertEqual([{'xyz': 3}], util.trim_nulls([{'abc': None, 'xyz': 3}]))

  def test_list_values(self):
    self.assertEqual({'a': ['b'], 'd': ['e']}, util.trim_nulls(
        {'a': ['b'], 'c': [None], 'd': [None, 'e', None], 'f': [[{}], {'a': []}]}))

  def test_empty_dict(self):
    self.assertEqual({}, util.trim_nulls({}))

  def test_simple_dict_with_nulls(self):
    self.assertEqual({}, util.trim_nulls({1: None, 2: [], 3: {}, 4: set(),
                                          5: frozenset()}))

  def test_simple_dict(self):
    self.assertEqual({1: 2, 3: 4}, util.trim_nulls({1: 2, 3: 4}))

  def test_simple_dict_with_nones(self):
    self.assertEqual({3: 4, 2: 9}, util.trim_nulls({1: None, 3: 4, 5: [], 2: 9}))

  def test_nested_dict_with_nones(self):
    self.assertEqual({1: {3: 4}}, util.trim_nulls({1: {2: [], 3: 4}, 5: {6: None}}))

  def test_zero(self):
    self.assertEqual({1: 0}, util.trim_nulls({1: 0}))

  def test_favicon_for_url(self):
    for url in ('http://a.org/b/c?d=e&f=g', 'https://a.org/b/c', 'http://a.org/'):
      self.assertEqual('http://a.org/favicon.ico', util.favicon_for_url(url))

  def test_domain_from_link(self):
    self.assertEqual('localhost', util.domain_from_link('http://localhost/foo'))
    self.assertEqual('a.b.c.d', util.domain_from_link('http://a.b.c.d/foo'))
    for good_link in ('asdf.com', 'www.asdf.com', 'https://asdf.com/',
                      'asdf.com/foo?bar#baz'):
      actual = util.domain_from_link(good_link)
      self.assertEqual('asdf.com', actual, '%s returned %s' % (good_link, actual))

    self.assertEqual('asdf.com.', util.domain_from_link('http://asdf.com./x'))

    for bad_link in '', '  ', 'a&b.com', 'http://', 'file:///':
      self.assertEquals(None, util.domain_from_link(bad_link))

  def test_update_scheme(self):
    for orig in 'http', 'https':
      for new in 'http', 'https':
        self.handler.request.scheme = new
        updated = util.update_scheme(orig + '://foo', self.handler)
        self.assertEqual(new + '://foo', updated)

    self.handler.request.scheme = 'https'
    self.assertEqual(
      'https://distillery.s3.amazonaws.com/profiles/xyz.jpg',
      util.update_scheme('http://images.ak.instagram.com/profiles/xyz.jpg',
                         self.handler))

  def test_tag_uri(self):
    self.assertEquals('tag:x.com:foo', util.tag_uri('x.com', 'foo'))
    self.assertEquals('tag:x.com,2013:foo',
                      util.tag_uri('x.com', 'foo', year=2013))

  def test_parse_tag_uri(self):
    self.assertEquals(('x.com', 'foo'), util.parse_tag_uri('tag:x.com,2013:foo'))
    self.assertEquals(('x.com', 'foo'), util.parse_tag_uri('tag:x.com:foo'))
    self.assertEquals(None, util.parse_tag_uri('asdf'))

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

  def test_extract_links(self):
    self.assertEquals(set(), util.extract_links(''))
    self.assertEquals(set(), util.extract_links('asdf qwert'))

    for text in ('http://foo.com',
                 '  http://foo.com  ',
                 '  http://foo.com \n http://foo.com  ',
                 'x http://foo.com\ny',
                 'x\thttp://foo.com.',
                 'x\rhttp://foo.com! ',
                 'x http://foo.com? ',
                 '<a href="http://foo.com">',
                 "<a href='http://foo.com'>",
                 '<a href="xyz">http://foo.com</a>',
                 ):
      self.assertEquals(set(['http://foo.com']), util.extract_links(text),
                        'Failed on %r' % text)

    self.assertEquals(
      set(['http://foo.com', 'https://www.bar.com']),
      util.extract_links('x http://foo.com y https://www.bar.com z'))
    self.assertEquals(
      set(['http://foo.com', 'http://bar.com']),
      util.extract_links('asdf http://foo.com qwert <a class="x" href="http://bar.com" >xyz</a> www.baz.com'))

  def test_linkify(self):
    self.assertEqual('', util.linkify(''))
    self.assertEqual('asdf qwert', util.linkify('asdf qwert'))
    self.assertEqual(
      'asdf <a href="http://foo.com">http://foo.com</a> qwert '
      '<a class="x" href="http://foo.com" >xyz</a> <a href="http://www.bar.com">www.bar.com</a>',
      util.linkify('asdf http://foo.com qwert <a class="x" href="http://foo.com" >xyz</a> www.bar.com'))
    self.assertEqual(
      'asdf <a href="http://t.co/asdf">http://t.co/asdf</a> qwert',
      util.linkify('asdf http://t.co/asdf qwert'))

    for text in ('X <a class="x" href="http://foo.com" >xyz</a> Y',
                 '<a href="http://foo.com"  class="x">xyz</a> Y',
                 "X <a href='http//foo.com' />"):
      self.assertEqual(text, util.linkify(text))

    self.assertEqual(
      'asdf <a href="http://foo.com">foo</a> qwert '
      '<a href="http://www.bar.com">www.bar.com</a>',
      util.linkify('asdf <a href="http://foo.com">foo</a> qwert www.bar.com'))

  def test_pretty_link(self):
    pl = util.pretty_link
    self.assertEquals('<a href="http://foo">foo</a>', pl('http://foo'))
    self.assertEquals('<a class="my cls" href="http://foo">foo</a>',
                      pl('http://foo', a_class='my cls'))
    self.assertEquals('<a target="_blank" href="http://foo">foo</a>',
                      pl('http://foo', new_tab=True))
    self.assertEquals('<a href="http://www.foo">foo</a>', pl('http://www.foo'))
    self.assertEquals('<a href="http://www.foo/bar">foo/ba...</a>',
                      pl('http://www.foo/bar', max_length=6))
    self.assertEquals('<a href="http://foo/bar/baz">foo/ba...</a>',
                      pl('http://foo/bar/baz', max_length=6))

    # default length is full domain plus 14 ch
    self.assertEquals(
      '<a href="http://foo/bar/baz/baj/XY">foo/bar/baz/baj/XY</a>',
      pl('http://foo/bar/baz/baj/XY'))
    self.assertEquals(
      '<a href="http://foo/bar/baz/baj/asdf_qwert">foo/bar/baz/baj/as...</a>',
      pl('http://foo/bar/baz/baj/asdf_qwert'))


  # TODO: make this work
  # def test_linkify_broken(self):
  #   self.assertEqual('', util.linkify(
  #       '<a href="http://www.example.com/?feature_embedded">'))

  def test_linkify_pretty(self):
    lp = lambda url: util.linkify(url, pretty=True, max_length=6)
    self.assertEqual('', lp(''))
    self.assertEqual('asdf qwert', lp('asdf qwert'))
    self.assertEquals('x <a href="http://foo">foo</a> y', lp('x http://foo y'))
    self.assertEquals('x <a href="http://www.foo/baz/baj">foo/ba...</a> y',
                      lp('x http://www.foo/baz/baj y'))

  def test_parse_iso8601(self):
    for str, offset in (
      ('2012-07-23T05:54:49', None),
      ('2012-07-23T05:54:49+0000', 0),
      ('2012-07-23T05:54:49-0000', 0),
      ('2012-07-23T05:54:49+0130', 90),
      ('2012-07-23T05:54:49-1300', -780),
      ('2012-07-23T05:54:49-13:00', -780),
      ):
      dt = util.parse_iso8601(str)
      self.assertEqual(datetime.datetime(2012, 07, 23, 5, 54, 49),
                       dt.replace(tzinfo=None))
      if offset is not None:
        offset = datetime.timedelta(minutes=offset)
      self.assertEqual(offset, dt.utcoffset())

  def test_maybe_iso8601_to_rfc3339(self):
    for input, expected in (
      (None, None),
      ('', ''),
      ('not iso8601!', 'not iso8601!'),
      ('2012-07-23T05:54:49+0000', '2012-07-23T05:54:49+00:00'),
      ):
      self.assertEqual(expected, util.maybe_iso8601_to_rfc3339(input))

  def test_maybe_timestamp_to_rfc3339(self):
    for input, expected in (
      (None, None),
      ('', ''),
      ('not a timestamp!', 'not a timestamp!'),
      (1349588757, '2012-10-06T22:45:57'),
      ('1349588757', '2012-10-06T22:45:57'),
      ):
      self.assertEqual(expected, util.maybe_timestamp_to_rfc3339(input))

  def test_ellipsize(self):
    self.assertEqual('', util.ellipsize(''))
    self.assertEqual('asdf', util.ellipsize('asdf'))
    self.assertEqual('asdf qwert', util.ellipsize('asdf qwert'))
    self.assertEqual('asdf...', util.ellipsize('asdf qwert', words=1))
    self.assertEqual('asdf q...', util.ellipsize('asdf qwert', chars=9))
    self.assertEqual('asdf...', util.ellipsize('asdf qwert', words=1, chars=9))
    self.assertEqual('asdf q...', util.ellipsize('asdf qwert', words=2, chars=9))

  def test_add_query_param(self):
    for expected, url, params in (
      ('http://a.com?x=', 'http://a.com', [('x', '')]),
      ('http://a.com?x=y', 'http://a.com', [('x', 'y')]),
      ('http://a.com?x=y&u=v', 'http://a.com', [('x', 'y'), ('u', 'v')]),
      ('http://a.com?x=y&u=v', 'http://a.com?x=y', [('u', 'v')]),
      ('http://a.com?x=y&u=v', 'http://a.com?x=y', [('u', 'v')]),
      ('http://a.com?x=y&x=z', 'http://a.com', [('x', 'y'), ('x', 'z')]),
      ('http://a.com?x=y&x=z&x=w', 'http://a.com?x=y&x=z', [('x', 'w')]),
      ('http://a.com?x=y', 'http://a.com', {'x': 'y'}),
      # note encoding declaration at top of file
      ('http://a.com?x=R+%C3%87', 'http://a.com', {'x': u'R Ç'}),
      ('http://a.com?x=R+%C3%87&x=R+%C3%87', 'http://a.com?x=R+%C3%87', {'x': u'R Ç'}),
      ):
      self.assertEqual(expected, util.add_query_params(url, params))

    query_string = ''
    for i in range(2):
      query_string = util.add_query_params(query_string, {'x': u'Ryan Çelik'})
      for key, val in urlparse.parse_qsl(query_string[1:]):
        self.assertEquals('x', key)
        self.assertEquals(u'Ryan Çelik', val.decode('utf-8'))

  def test_get_required_param(self):
    handler = webapp2.RequestHandler(webapp2.Request.blank('/?a=b'), None)
    self.assertEqual('b', util.get_required_param(handler, 'a'))
    try:
      util.get_required_param(handler, 'c')
      self.fail('Expected HTTPException')
    except exc.HTTPException, e:
      self.assertEqual(400, e.status_int)

  def test_if_changed(self):
    cache = testutil.FakeCache()
    updates = {}

    for val in (0, '', []):  # should all be normalized to None
      self.assertIsNone(None, util.if_changed(cache, updates, 'x', val))
      cache['x'] = 0
      self.assertIsNone(None, util.if_changed(cache, updates, 'x', val))
      del cache['x']

    self.assertEquals(1, util.if_changed(cache, updates, 'x', 1))
    self.assertEquals(1, updates['x'])
    cache['x'] = 1
    self.assertIsNone(util.if_changed(cache, updates, 'x', 1))
    self.assertEquals(2, util.if_changed(cache, updates, 'x', 2))
    self.assertEquals(2, updates['x'])

    self.assertIsNone(util.if_changed(cache, updates, 'x', None))
    self.assertEquals(None, updates['x'])
