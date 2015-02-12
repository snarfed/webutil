# -*- coding: utf-8 -*-
"""Unit tests for util.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import datetime
import urlparse
from webob import exc

import testutil
import urllib2
import util
import webapp2


class UtilTest(testutil.HandlerTest):

  def test_to_xml(self):
    self.assert_equals('', util.to_xml({}))
    self.assert_equals('\n<a>3.14</a>\n<b>xyz</b>\n',
                       util.to_xml({'a': 3.14, 'b': 'xyz'}))
    self.assert_equals('\n<a></a>\n',
                       util.to_xml({'a': None}))
    self.assert_equals('\n<a></a>\n',
                       util.to_xml({'a': ''}))
    self.assert_equals('\n<a></a>\n',
                       util.to_xml({'a': {}}))
    self.assert_equals('\n<a>0</a>\n',
                       util.to_xml({'a': 0}))
    self.assert_equals('\n<a>1</a>\n<a>2</a>\n',
                       util.to_xml({'a': [1, 2]}))
    self.assert_equals("""
<a>
<b>
<c>x</c>
<d>y</d>
</b>
<e>2</e>
<e>3</e>
</a>
""", util.to_xml({'a': {'b': {'c': 'x', 'd': 'y'}, 'e': (2, 3), }}))

  def test_trim_nulls(self):
    # basic
    self.assertEqual(None, util.trim_nulls(None))
    self.assertEqual('foo', util.trim_nulls('foo'))
    self.assertEqual([], util.trim_nulls([]))
    self.assertEqual({}, util.trim_nulls({}))
    self.assertEqual(set(), util.trim_nulls(set()))
    self.assertEqual((), util.trim_nulls(()))
    self.assertEqual({1: 0}, util.trim_nulls({1: 0}))  # numeric zero

    # lists
    self.assertEqual([{'xyz': 3}], util.trim_nulls([{'abc': None, 'xyz': 3}]))
    self.assertEqual({'a': ['b'], 'd': ['e']}, util.trim_nulls(
        {'a': ['b'], 'c': [None], 'd': [None, 'e', None], 'f': [[{}], {'a': []}]}))
    self.assertEqual({}, util.trim_nulls({1: None, 2: [], 3: {}, 4: set(),
                                          5: frozenset()}))

    # sets
    self.assertEqual(set((1, 2)), util.trim_nulls(set((1, None, 2))))
    self.assertEqual({'a': set(['b']), 'd': set(['e'])}, util.trim_nulls(
        {'a': set(['b']), 'c': set([None]), 'd': set([None, 'e', None])}))
    self.assertEqual(set(), util.trim_nulls(set((None,))))

    # dicts
    self.assertEqual({1: 2, 3: 4}, util.trim_nulls({1: 2, 3: 4}))
    self.assertEqual({3: 4, 2: 9}, util.trim_nulls({1: None, 3: 4, 5: [], 2: 9}))
    self.assertEqual({1: {3: 4}}, util.trim_nulls({1: {2: [], 3: 4}, 5: {6: None}}))

  def test_uniquify(self):
    self.assertEqual([], util.uniquify(None))
    self.assertEqual([], util.uniquify([]))
    self.assertEqual([3], util.uniquify((3,)))
    self.assertEqual([3, 2, 4, 5, 9],
                     util.uniquify([3, 3, 2, 3, 4, 3, 5, 9, 9, 9, 3]))

  def test_favicon_for_url(self):
    for url in ('http://a.org/b/c?d=e&f=g', 'https://a.org/b/c', 'http://a.org/'):
      self.assertEqual('http://a.org/favicon.ico', util.favicon_for_url(url))

  def test_domain_from_link(self):
    self.assertEqual('localhost', util.domain_from_link('http://localhost/foo'))
    self.assertEqual('a.b.c.d', util.domain_from_link('http://a.b.c.d/foo'))
    for good_link in ('asdf.com', 'www.asdf.com', 'https://asdf.com/',
                      'asdf.com/foo?bar#baz', 'm.asdf.com',
                      'mobile.asdf.com/foo?bar#baz',
                      'https://m.asdf.com/foo?bar#baz'):
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
    self.assertEqual(
      'https://igcdn-photos-e-a.akamaihd.net/hphotos-ak-xpf1/123_a.jpg',
      util.update_scheme('http://photos-e.ak.instagram.com/hphotos-ak-xpf1/123_a.jpg',
                         self.handler))

  def test_schemeless(self):
    for expected, url in (
        ('', util.schemeless('')),
        ('/path', util.schemeless('/path')),
        ('//foo', util.schemeless('//foo')),
        ('//foo', util.schemeless('http://foo')),
        ('//foo.bar/baz', util.schemeless('http://foo.bar/baz')),
        ('//foo.bar/baz', util.schemeless('https://foo.bar/baz'))):
      self.assertEqual(expected, util.schemeless(url))

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
    self.assertEquals(('me', 'x.com'),
                      util.parse_acct_uri('acct:me@x.com', ['x.com', 'y.com']))
    self.assertRaises(ValueError, util.parse_acct_uri, 'mailto:me@x.com')
    self.assertRaises(ValueError, util.parse_acct_uri, 'acct:foo')
    self.assertRaises(ValueError,
                      util.parse_acct_uri, 'acct:me@a.com', ['x.com'])

  def test_extract_links(self):
    self.assertEquals([], util.extract_links(None))
    self.assertEquals([], util.extract_links(''))
    self.assertEquals([], util.extract_links('asdf qwert'))

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
      self.assertEquals(['http://foo.com'], util.extract_links(text),
                        'Failed on %r' % text)

    self.assertEquals(
      ['http://foo.com', 'https://www.bar.com'],
      util.extract_links('x http://foo.com y https://www.bar.com z'))
    self.assertEquals(
      ['http://foo.com', 'http://bar.com'],
      util.extract_links('asdf http://foo.com qwert <a class="x" href="http://bar.com" >xyz</a> www.baz.com'))

    # trailing slash
    # TODO: make this work
    # self.assertEquals(['http://foo.com/'],
    #                   util.extract_links('x http://foo.com/'))

    # query
    self.assertEquals(['http://foo.com/bar?baz=baj'],
                      util.extract_links('http://foo.com/bar?baz=baj y'))

    # preserve order
    self.assertEquals(['http://%s' % c for c in 'a', 'b', 'c', 'd'],
                      util.extract_links('http://a http://b http://c http://d'))

  def test_linkify(self):
    for unchanged in (
        '',
        'x.c',
        'x.computer',
        'asdf qwert',
        'X <a class="x" href="http://foo.com" >xyz</a> Y',
        '<a href="http://foo.com"  class="x">xyz</a> Y',
        "X <a href='http://foo.com' />",
        'asdf <a href="http://foo.com">foo</a> qwert ',
        # only a-z0-9 allowed in domain names
        u'http://aÇb.com'):
      self.assertEqual(unchanged, util.linkify(unchanged))

    for expected, input in (
        ('<a href="http://foo.com">http://foo.com</a>', 'http://foo.com'),
        ('<a href="http://foo.com/">http://foo.com/</a>', 'http://foo.com/'),
        ('<a href="http://foo.com/y">http://foo.com/y</a>', 'http://foo.com/y'),
        ('<a href="http://www.foo">www.foo</a>', 'www.foo'),
        ('<a href="http://www.foo:80">www.foo:80</a>', 'www.foo:80'),
        ('<a href="http://www.foo:80/x">www.foo:80/x</a>', 'www.foo:80/x'),
        ('asdf <a href="http://foo.com">http://foo.com</a> qwert <a class="x" href="http://foo.com" >xyz</a>',
         'asdf http://foo.com qwert <a class="x" href="http://foo.com" >xyz</a>'),
        ('asdf <a href="http://t.co/asdf">http://t.co/asdf</a> qwert',
         'asdf http://t.co/asdf qwert'),
        ('<a href="http://foo.co/?bar&baz">http://foo.co/?bar&baz</a>',
         'http://foo.co/?bar&baz'),
        ('<a href="http://www.foo.com">www.foo.com</a>', 'www.foo.com'),
        ('a <a href="http://www.foo.com">www.foo.com</a> b', 'a www.foo.com b'),
        ('asdf <a href="http://foo.com">foo</a> qwert '
         '<a href="http://www.bar.com">www.bar.com</a>',
         'asdf <a href="http://foo.com">foo</a> qwert www.bar.com'),
        # https://github.com/snarfed/bridgy/issues/325#issuecomment-67923098
        ('<a href="https://github.com/pfefferle/wordpress-indieweb-press-this">https://github.com/pfefferle/wordpress-indieweb-press-this</a> >',
         'https://github.com/pfefferle/wordpress-indieweb-press-this >'),
        ('interesting how twitter auto-links it <a href="http://example.com/a_link_(with_parens)">http://example.com/a_link_(with_parens)</a> vs. (<a href="http://example.com/a_link_without">http://example.com/a_link_without</a>)',
         'interesting how twitter auto-links it http://example.com/a_link_(with_parens) vs. (http://example.com/a_link_without)'),
        ('links separated by punctuation <a href="http://foo.com">http://foo.com</a>, <a href="http://bar.com/">http://bar.com/</a>; <a href="http://baz.com/?s=query">http://baz.com/?s=query</a>; did it work?',
         'links separated by punctuation http://foo.com, http://bar.com/; http://baz.com/?s=query; did it work?'),
    ):
        self.assertEqual(expected, util.linkify(input))

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
    self.assertEquals('<a href="http://foo/bar/baz">foo/ba...</a>',
                      pl('http://foo/bar/baz', max_length=6))

    self.assertEquals('<a href="http://foo/bar/baz">bar/baz</a>',
                      pl('http://foo/bar/baz', keep_host=False))
    self.assertEquals('<a href="http://foo/bar/baz">bar/ba...</a>',
                      pl('http://foo/bar/baz', keep_host=False, max_length=6))

    self.assertEquals('<a href="http://foo">foo</a>', pl('http://foo', text=''))
    self.assertEquals('<a href="http://foo">biff</a>',
                      pl('http://foo', text='biff'))

    # default text max length is full domain plus 14 chars
    self.assertEquals(
      '<a href="http://foo/bar/baz/baj/XY">foo/bar/baz/baj/XY</a>',
      pl('http://foo/bar/baz/baj/XY'))
    self.assertEquals(
      '<a href="http://foo/bar/baz/baj/asdf_qwert">foo/bar/baz/baj/as...</a>',
      pl('http://foo/bar/baz/baj/asdf_qwert'))

    # default link max length is 30 chars
    self.assertEquals('<a href="http://foo">123456789012345678901234567890...</a>',
                      pl('http://foo', text='123456789012345678901234567890TOOMUCH'))
    self.assertEquals('<a href="http://foo">bar...</a>',
                      pl('http://foo', text='barbazbaj', max_length=3))

  # TODO: make this work
  # def test_linkify_broken(self):
  #   self.assertEqual('', util.linkify(
  #       '<a href="http://www.example.com/?feature_embedded">'))

  def test_linkify_pretty(self):
    lp = lambda url: util.linkify(url, pretty=True, max_length=6)
    self.assertEqual('', lp(''))
    self.assertEqual('asdf qwert', lp('asdf qwert'))
    self.assertEquals('x <a href="http://foo.co">foo.co</a> y', lp('x http://foo.co y'))
    self.assertEquals('x <a href="http://www.foo.ly/baz/baj">foo.ly...</a> y',
                      lp('x http://www.foo.ly/baz/baj y'))

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
      (1349588757, '2012-10-07T05:45:57'),
      ('1349588757', '2012-10-07T05:45:57'),
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

    for expected, req, params in (
      (urllib2.Request('http://a.com?x=y'), urllib2.Request('http://a.com'),
       [('x', 'y')]),
      (urllib2.Request('http://a.com?x=y&u=v'), urllib2.Request('http://a.com?x=y'),
       [('u', 'v')]),
      (urllib2.Request('http://a.com?x=y', data='my data', headers={'X': 'Y'}),
       urllib2.Request('http://a.com', data='my data', headers={'X': 'Y'}),
       [('x', 'y')]),
      ):
      actual = util.add_query_params(req, params)
      self.assertIsInstance(actual, urllib2.Request)
      self.assertEqual(expected.get_full_url(), actual.get_full_url())
      self.assertEqual(expected.get_data(), actual.get_data())
      self.assertEqual(expected.headers, actual.headers)

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
    cache = util.CacheDict()
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

  def test_generate_secret(self):
    self.assertEquals(24, len(util.generate_secret()))

  def test_cache_dict(self):
    data = {1: 2, 3: 4}
    cd = util.CacheDict(data)
    self.assert_equals(data, cd)
    self.assert_equals({}, cd.get_multi([]))
    self.assert_equals({}, cd.get_multi({9}))
    self.assert_equals({1: 2}, cd.get_multi({1, 9}))
    self.assert_equals(data, cd.get_multi({1, 3}))

    # get_multi should handle a generator args ok
    self.assert_equals(data, cd.get_multi(k for k in [1, 3]))
    self.assert_equals(data, cd.get_multi(xrange(4)))

  def test_is_int(self):
    for arg in 0, 1, -1, '0', '11', 1.0, 12345:
      self.assertTrue(util.is_int(arg), `arg`)
    for arg in 0.1, 3.14, '3.0', '3xyz', None, self:
      self.assertFalse(util.is_int(arg), `arg`)
