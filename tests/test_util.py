# -*- coding: utf-8 -*-
"""Unit tests for util.py.

Supports Python 3. Should not depend on App Engine API or SDK packages.
"""
import datetime
import http.client
import socket
import ssl
import io
from urllib.error import HTTPError, URLError
import urllib.parse, urllib.request

from flask import Flask, request
import prawcore.exceptions
import requests
import tumblpy
import tweepy
import urllib3
from webob import exc
from werkzeug.exceptions import BadGateway, BadRequest

from .. import testutil, util
from ..util import json_dumps, json_loads

ORIG_USER_AGENT = util.user_agent

class UtilTest(testutil.TestCase):

  def setUp(self):
    super(UtilTest, self).setUp()
    util.follow_redirects_cache.clear()
    util.user_agent = ORIG_USER_AGENT

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

    # iterator and generator
    self.assertEqual(['a', 'b'], list(util.trim_nulls(iter(['a', None, 'b']))))
    self.assertEqual(['a', 'b'], list(util.trim_nulls(iter(['a', None, 'b']))))

    # ignore
    self.assertEqual({'a': None}, util.trim_nulls({'a': None}, ignore=('a',)))
    self.assertEqual({'a': [None]}, util.trim_nulls({'a': [None]}, ignore=('a',)))
    self.assertEqual(['a'], util.trim_nulls(['a', None], ignore=('a',)))
    self.assertEqual({'a': {'b': ''}}, util.trim_nulls({'a': {'b': ''}},
                                                       ignore=('a',)))
    self.assertEqual({'a': {'b': None}}, util.trim_nulls({'a': {'b': None}},
                                                         ignore=('a', 'b')))

  def test_uniquify(self):
    self.assertEqual([], util.uniquify(None))
    self.assertEqual([], util.uniquify([]))
    self.assertEqual([3], util.uniquify((3,)))
    self.assertEqual([3, 2, 4, 5, 9],
                     util.uniquify([3, 3, 2, 3, 4, 3, 5, 9, 9, 9, 3]))

  def test_get_list(self):
    for dict, expected in (
        ({}, []),
        ({9: 9}, []),
        ({0: []}, []),
        ({0: ()}, []),
        ({0: [3]}, [3]),
        ({0: (3, 4)}, [3, 4]),
        ({0: set((3, 4))}, [3, 4]),
        ({0: 2}, [2]),
        ({0: None}, []),
      ):
      self.assertEqual(expected, util.get_list(dict, 0))

  def test_pop_list(self):
    obj = {'a': 1}
    self.assertEqual([1], util.pop_list(obj, 'a'))
    self.assertEqual({}, obj)

    self.assertEqual([], util.pop_list(obj, 'a'))
    self.assertEqual({}, obj)

  def test_encode(self):
    coffee = u'☕'
    coffee_utf8 = coffee.encode('utf-8')

    for expected, input in (
        (None, None),
        (1.23, 1.23),
        (True, True),
        (b'xyz', 'xyz'),
        (b'xyz', u'xyz'),
        (coffee_utf8, coffee),
        ([], []),
        ((), ()),
        ({}, {}),
        (set(), set()),
        ([1, coffee_utf8], [1, coffee]),
        ({coffee_utf8: 1, 2: coffee_utf8, 3: [4, set((coffee_utf8,))]},
         {coffee: 1, 2: coffee, 3: [4, set((coffee,))]}),
        (set((coffee_utf8,)), set((coffee,))),
        ((b'xyz', [coffee_utf8], b'abc'), ('xyz', [coffee], 'abc')),
    ):
      self.assertEqual(expected, util.encode(input))

  def test_get_first(self):
    for dict, expected in (
        ({}, None),
        ({9: 9}, None),
        ({0: None}, None),
        ({0: []}, None),
        ({0: [3]}, 3),
        ({0: (3, 4, 5)}, 3),
      ):
      self.assertEqual(expected, util.get_first(dict, 0))

    self.assertEqual('default', util.get_first({}, 0, 'default'))

  def test_get_url(self):
    for val, expected in (
        (None, None),
        ({}, None),
        ([], []),
        ({'x': 'y'}, None),
        ({'url': 'foo'}, 'foo'),
        ({'url': ['foo', 'x']}, 'foo'),
      ):
      self.assertEqual(expected, util.get_url(val))

    for val, expected in (
        ({}, None),
        ({'a': 'b'}, None),
        ({'x': 'y'}, 'y'),
        ({'x': {'url': 'foo'}}, 'foo'),
        ({'x': {'url': ['foo', 'x']}}, 'foo'),
      ):
      self.assertEqual(expected, util.get_url(val, 'x'))

  def test_get_urls(self):
    for val, expected in (
        (None, []),
        ({}, []),
        ([], []),
        ([None, 'asdf', {'url': 'qwert'}, {'foo': 'bar'}, {}],
         ['asdf', 'qwert']),
    ):
      self.assertEqual(expected, util.get_urls({'key': val}, 'key'))

    self.assertEqual(['bar'], util.get_urls(
      {'outer': [{'url': 'foo'}, {'inner': {'url': 'bar'}}]}, 'outer', 'inner'))

  def test_favicon_for_url(self):
    for url in ('http://a.org/b/c?d=e&f=g', 'https://a.org/b/c', 'http://a.org/'):
      self.assertEqual('http://a.org/favicon.ico', util.favicon_for_url(url))

  def test_domain_from_link(self):
    dfl = util.domain_from_link

    for url in None, '':
      self.assertIsNone(dfl(url))

    self.assert_equals('localhost', dfl('http://localhost/foo'))
    self.assert_equals('a.b.c.d', dfl('http://a.b.c.d/foo'))

    for url in ('asdf.com', 'https://asdf.com/', 'asdf.com/foo?bar#baz',
                'asdf.com:1234', '//asdf.com/foo/bar'):
      self.assert_equals('asdf.com', dfl(url, minimize=True))
      self.assert_equals('asdf.com', dfl(url, minimize=False))

    for url in ('www.asdf.com', 'm.asdf.com', 'mobile.asdf.com/foo?bar#baz',
                'https://m.asdf.com/foo?bar#baz'):
      self.assert_equals('asdf.com', dfl(url, minimize=True))

    self.assert_equals('www.asdf.com', dfl('www.asdf.com', minimize=False))
    self.assert_equals('m.asdf.com', dfl('m.asdf.com', minimize=False))
    self.assert_equals('mobile.asdf.com', dfl('mobile.asdf.com/foo?bar#baz', minimize=False))
    self.assert_equals('m.asdf.com', dfl('https://m.asdf.com/foo?bar#baz', minimize=False))

    self.assert_equals('asdf.com.', dfl('http://asdf.com./x'))
    self.assert_equals('⊙.de', dfl('http://⊙.de/x'))
    self.assert_equals('abc⊙.de', dfl('http://abc⊙.de/x'))
    self.assert_equals('abc.⊙.de', dfl('http://abc.⊙.de/x'))

    for bad_link in ('', '  ', 'a&b.com', 'http://', 'file:///',
                     """12345'"\\'\\");|]*\x00{\r\n<\x00>�''💡"""):
      self.assert_equals(None, dfl(bad_link))

  def test_domain_or_parent_in(self):
    for expected, inputs in (
        (False, [
          ('', []), ('', ['']), ('x', []), ('x', ['']), ('x.y', []),
          ('x.y', ['']), ('', ['x', 'y']), ('', ['x.y']), ('x', ['y']),
          ('xy', ['y', 'x']), ('x', ['yx']), ('v.w.x', ['v.w', 'x.w']),
          ('x', ['', 'y', 'xy', 'yx', 'xx', 'xxx']),
        ]),
        (True, [
          ('x', ['x']), ('x', ['x', 'y']), ('x', ['y', 'x']),
          ('w.x', ['x']), ('u.v.w.x', ['y', 'v.w.x']),
        ])):
      for input, domains in inputs:
        self.assertEqual(expected, util.domain_or_parent_in(input, domains),
                          repr((input, domains, expected)))

  def test_update_scheme(self):
    # Should only upgrade http -> https, never downgrade
    with Flask(__name__).test_request_context('/'):
      request.scheme = 'http'
      for orig in 'http', 'https':
        self.assertEqual(orig + "://foo", util.update_scheme(orig + "://foo", request))
      request.scheme = 'https'
      for orig in 'http', 'https':
        self.assertEqual("https://foo", util.update_scheme(orig + "://foo", request))

  def test_schemeless(self):
    for expected, url in (
        ('', ''),
        ('/path', '/path'),
        ('//foo', '//foo'),
        ('//foo', 'http://foo'),
        ('//foo.bar/baz', 'http://foo.bar/baz'),
        ('//foo.bar/baz', 'https://foo.bar/baz'),
      ):
      self.assertEqual(expected, util.schemeless(url))

    self.assertEqual('foo', util.schemeless('http://foo/', slashes=False))
    self.assertEqual('foo/bar', util.schemeless('http://foo/bar/', slashes=False))

  def test_fragmentless(self):
    for expected, url in (
        ('', ''),
        ('/path', '/path'),
        ('http://foo', 'http://foo'),
        ('http://foo', 'http://foo#bar'),
        ('http://foo/bar?baz', 'http://foo/bar?baz#baj'),
      ):
      self.assertEqual(expected, util.fragmentless(url))

  def test_clean_url(self):
    for unchanged in '', 'http://foo', 'http://foo#bar', 'http://foo?x=y&z=w':
      self.assertEqual(unchanged, util.clean_url(unchanged))

    for bad in None, 'http://foo]', 3.14, ['http://foo']:
      self.assertIsNone(util.clean_url(bad))

    self.assertEqual('http://foo',
                     util.clean_url('http://foo?utm_source=x&utm_campaign=y'
                                     '&source=rss----12b80d28f892---4'))
    self.assertEqual('http://foo?a=b&c=d',
                     util.clean_url('http://foo?a=b&utm_source=x&c=d'
                                     '&source=rss----12b80d28f892---4'))
    self.assertEqual('http://foo?source=not-rss',
                     util.clean_url('http://foo?&source=not-rss'))

  def test_quote_path(self):
    for unchanged in '', 'foo', 'http://foo', 'http://foo#bar', 'http://foo?x=y&z=w':
      self.assertEqual(unchanged, util.quote_path(unchanged))

    for input, expected in (
        ('http://x/☕', 'http://x/%E2%98%95'),
        ('http://x/foo ☕ bar', 'http://x/foo%20%E2%98%95%20bar'),
        ('http://☕:☕@☕.com/☕?☕=☕&☕=☕#☕', 'http://☕:☕@☕.com/%E2%98%95?☕=☕&☕=☕#☕'),
    ):
      self.assertEqual(expected, util.quote_path(input))

  def test_dedupe_urls(self):
    self.assertEqual([], util.dedupe_urls([]))
    self.assertEqual([], util.dedupe_urls(['', None, '']))
    self.assertEqual(['http://foo/'], util.dedupe_urls(['http://foo']))
    self.assertEqual(['http://foo/'], util.dedupe_urls(['http://foo', 'http://foo']))
    self.assertEqual(['http://foo/'], util.dedupe_urls(['http://foo', 'http://foo/']))
    self.assertEqual(['https://foo/'], util.dedupe_urls([
      'https://foo', 'http://foo', 'https://foo/', 'http://foo/']))
    self.assertEqual(['https://foo/'],
                     util.dedupe_urls(['http://foo', '', 'https://foo/']))
    self.assertEqual(['http://foo/bar', 'http://foo/bar/'],
                     util.dedupe_urls(['http://foo/bar', 'http://foo/bar/', None, '']))
    self.assertEqual(['http://foo/'],
                     util.dedupe_urls(['http://foo', 'http://FOO/', 'http://FoO/']))
    self.assertEqual(['http://foo/', 'http://foo:80/', 'http://foo:3333/'],
                     util.dedupe_urls(['http://foo', 'http://foo:80/',
                                       'http://foo:3333/']))

    self.assertEqual([{'url': 'http://foo/'}, {'url': 'http://bar/'}],
                     util.dedupe_urls([{'url': 'http://foo'},
                                       {'url': 'http://FOO/'},
                                       {'url': 'http://bar'}]))
    self.assertEqual(
      [{'stream': {'url': 'http://foo/'}}, {'stream': {'url': 'http://bar/'}}],
       util.dedupe_urls([{'stream': {'url': 'http://foo'}},
                         {'stream': {'url': 'http://FOO/'}},
                         {'stream': {'url': 'http://bar'}}],
                        key='stream'))

  def test_tag_uri(self):
    self.assertEqual('tag:x.com:foo', util.tag_uri('x.com', 'foo'))
    self.assertEqual('tag:x.com,2013:foo',
                      util.tag_uri('x.com', 'foo', year=2013))

  def test_parse_tag_uri(self):
    self.assertEqual(('x.com', 'foo'), util.parse_tag_uri('tag:x.com,2013:foo'))
    self.assertEqual(('x.com', 'foo'), util.parse_tag_uri('tag:x.com:foo'))
    self.assertEqual(None, util.parse_tag_uri('asdf'))

  def test_parse_acct_uri(self):
    self.assertEqual(('me', 'x.com'), util.parse_acct_uri('acct:me@x.com'))
    self.assertEqual(('me', 'x.com'), util.parse_acct_uri('acct:@me@x.com'))
    self.assertEqual(('me', 'x.com'),
                      util.parse_acct_uri('acct:me@x.com', ['x.com', 'y.com']))
    self.assertRaises(ValueError, util.parse_acct_uri, 'mailto:me@x.com')
    self.assertRaises(ValueError, util.parse_acct_uri, 'acct:foo')
    self.assertRaises(ValueError, util.parse_acct_uri, 'acct:me@a.com', ['x.com'])

  def test_extract_links(self):
    self.assertEqual([], util.extract_links(None))
    self.assertEqual([], util.extract_links(''))
    self.assertEqual([], util.extract_links('asdf qwert'))

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
      self.assertEqual(['http://foo.com'], util.extract_links(text),
                        f'Failed on {text!r}')

    self.assertEqual(
      ['http://foo.com', 'https://www.bar.com'],
      util.extract_links('x http://foo.com y https://www.bar.com z'))
    self.assertEqual(
      ['http://foo.com', 'http://bar.com'],
      util.extract_links('asdf http://foo.com qwert <a class="x" href="http://bar.com" >xyz</a> www.baz.com'))

    # trailing slash
    self.assertEqual(['http://foo.com/'],
                      util.extract_links('x http://foo.com/'))

    # trailing dash
    self.assertEqual(['http://foo.com/z-'],
                      util.extract_links('x http://foo.com/z-'))

    # omit trailing close parentheses (eg in markdown links)
    self.assertEqual(['http://xy/z'], util.extract_links('[abc](http://xy/z)'))
    self.assertEqual(['http://xy/z'], util.extract_links('[abc](http://xy/z).'))
    self.assertEqual(['http://xy/z'], util.extract_links('([abc](http://xy/z))'))

    # query
    self.assertEqual(['http://foo.com/bar?baz=baj'],
                      util.extract_links('http://foo.com/bar?baz=baj y'))

    # trailing paren inside link vs outside
    self.assertEqual(['http://example/inside_(parens)'],
                      util.extract_links('http://example/inside_(parens)'))
    self.assertEqual(['http://example/outside_parens'],
                      util.extract_links('(http://example/outside_parens)'))

    # preserve order
    self.assertEqual([f'http://{c}' for c in ('a', 'b', 'c', 'd')],
                      util.extract_links('http://a http://b http://c http://d'))

    # emoji in domain
    self.assertEqual(['http://☕⊙.ws'],
                     util.extract_links('emoji http://☕⊙.ws domain'))

  def test_linkify(self):
    for unchanged in (
        '',
        'x.c',
        'asdf qwert',
        'X <a class="x" href="http://foo.com" >xyz</a> Y',
        '<a href="http://foo.com"  class="x">xyz</a> Y',
        "X <a href='http://foo.com' />",
        'asdf <a href="http://foo.com">foo</a> qwert ',
        'http://a<b>.com',
        '<a href="http://www.example.com/?feature_embedded">',
    ):
      self.assertEqual(unchanged, util.linkify(unchanged))

    for expected, input in (
        ('<a href="http://foo.com">http://foo.com</a>', 'http://foo.com'),
        ('<a href="http://foo.com/">http://foo.com/</a>', 'http://foo.com/'),
        ('<a href="http://foo.com/y">http://foo.com/y</a>', 'http://foo.com/y'),
        ('<a href="http://www.foo">www.foo</a>', 'www.foo'),
        ('<a href="http://x.computer">x.computer</a>', 'x.computer'),
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
        ('"<a href="http://foo.com">http://foo.com</a>",', '"http://foo.com",'),
        ('\'<a href="http://foo.com">http://foo.com</a>\',', "'http://foo.com',"),
        ('<a href="http://aÇb.com">http://aÇb.com</a>', 'http://aÇb.com'),
        ('<a href="http://a☕⊙b.com">http://a☕⊙b.com</a>', 'http://a☕⊙b.com'),
        ('<a href="http://a☕⊙b.com">a☕⊙b.com</a>', 'a☕⊙b.com'),
        ('<a href="http://☕⊙.ws">http://☕⊙.ws</a>', 'http://☕⊙.ws'),
        # TODO: implement
        # see comments in regexps at top of util.py for details
        # ('<a href="http://☕⊙.ws">☕⊙.ws</a>', '☕⊙.ws'),
    ):
        self.assertEqual(expected, util.linkify(input))

    # test skip_bare_cc_tlds
    for unchanged in ('x ab.ws y', 'x ☕⊙.ws y'):
      self.assertEqual(unchanged, util.linkify(unchanged, skip_bare_cc_tlds=True))

  def test_pretty_link(self):
    pl = util.pretty_link
    self.assertEqual('<a href="http://foo">foo</a>', pl('http://foo'))
    self.assertEqual('<a href="http://foo/">foo</a>', pl('http://foo/'))
    self.assertEqual('<a href="http://foo?bar=baz#biff">foo?bar=baz#biff</a>',
                     pl('http://foo?bar=baz#biff'))
    self.assertEqual('<a attr="val" href="http://foo">foo</a>',
                      pl('http://foo', attrs={'attr': 'val'}))
    self.assertEqual('<a target="_blank" href="http://foo">foo</a>',
                      pl('http://foo', new_tab=True))
    self.assertEqual('<a href="http://www.foo">foo</a>', pl('http://www.foo'))
    self.assertEqual('<a title="foo/bar" href="http://www.foo/bar">foo/ba...</a>',
                      pl('http://www.foo/bar', max_length=6))
    self.assertEqual('<a title="foo/bar/baz" href="http://foo/bar/baz">foo/ba...</a>',
                      pl('http://foo/bar/baz', max_length=6))
    self.assertEqual('<a title="foo/bar/baz" href="http://foo/bar/baz">foo/ba...</a>',
                      pl('http://foo/bar/baz', max_length=6))

    self.assertEqual('<a href="http://foo/bar/baz">bar/baz</a>',
                      pl('http://foo/bar/baz', keep_host=False))
    self.assertEqual('<a title="bar/baz" href="http://foo/bar/baz">bar/ba...</a>',
                      pl('http://foo/bar/baz', keep_host=False, max_length=6))

    self.assertEqual('<a href="http://foo">foo</a>', pl('http://foo', text=''))
    self.assertEqual('<a href="http://foo">biff</a>',
                      pl('http://foo', text='biff'))

    self.assertEqual('<a href="http://%3Ca%3Eb">&lt;a&gt;b</a>',
                     pl('http://<a>b'))
    self.assertEqual('<a href="http://%3Ca%3Eb">d&lt;e</a>',
                      pl('http://<a>b', text='d<e'))

    self.assertEqual('<a href="http://foo">foo <span class="glyphicon glyphicon-bar"></span></a>',
                     pl('http://foo', glyphicon='bar'))
    self.assertEqual('<a href="http://foo">🌐 foo</a>',
                     pl('http://foo', text_prefix='🌐'))
    self.assertEqual('<a href="http://%3Ca%3Eb">&lt;a&gt;b <span class="glyphicon glyphicon-bar"></span></a>',
                     pl('http://<a>b', glyphicon='bar'))

    # default text max length is full domain plus 14 chars
    self.assertEqual(
      '<a href="http://foo/bar/baz/baj/XY">foo/bar/baz/baj/XY</a>',
      pl('http://foo/bar/baz/baj/XY'))
    self.assertEqual(
      '<a title="foo/bar/baz/baj/asdf_qwert" href="http://foo/bar/baz/baj/asdf_qwert">foo/bar/baz/baj/as...</a>',
      pl('http://foo/bar/baz/baj/asdf_qwert'))

    # default link max length is 30 chars
    self.assertEqual('<a title="123456789012345678901234567890TOOMUCH" href="http://foo">123456789012345678901234567890...</a>',
                     pl('http://foo', text='123456789012345678901234567890TOOMUCH'))
    self.assertEqual('<a title="barbazbaj" href="http://foo">bar...</a>',
                     pl('http://foo', text='barbazbaj', max_length=3))

    # unquote URL escape chars and decode UTF-8 in link text
    expected = '<a href="http://x/ben-werdm%C3%BCller">x/ben-werdmüller</a>'
    url = 'http://x/ben-werdm%C3%BCller'
    self.assertEqual(expected, pl(str(url)))

    # pass through unicode chars gracefully(ish)
    self.assertEqual('<a href="http://x/ben-werdmüller">x/ben-werdmüller</a>',
                     pl('http://x/ben-werdmüller'))

    self.assertEqual('<a href="http://aÇb.com">aÇb.com</a>', pl('http://aÇb.com'))
    self.assertEqual('<a href="http://a☕⊙b.com">a☕⊙b.com</a>',
                     pl('http://a☕⊙b.com'))

    # no scheme, shouldn't try to strip it
    self.assertEqual('<a href="foo.com">foo.com</a>', pl('foo.com'))

  def test_linkify_pretty(self):
    def lp(url):
      return util.linkify(url, pretty=True, max_length=6)

    self.assertEqual('', lp(''))
    self.assertEqual('asdf qwert', lp('asdf qwert'))
    self.assertEqual('x <a href="http://foo.co">foo.co</a> y', lp('x http://foo.co y'))
    self.assertEqual(
      'x <a title="foo.ly/baz/baj" href="http://www.foo.ly/baz/baj">foo.ly...</a> y',
      lp('x http://www.foo.ly/baz/baj y'))
    self.assertEqual(
      'x <a title="foo.co/bar?baz=baj#biff" href="http://foo.co/bar?baz=baj#biff">foo.co...</a> y',
      lp('x http://foo.co/bar?baz=baj#biff y'))

  def test_parse_iso8601(self):
    for val, offset, usecs in (
      ('2012-07-23 05:54:49', None, 0),
      ('2012-07-23T05:54:49', None, 0),
      ('2012-07-23 05:54:49.123', None, 123000),
      ('2012-07-23T05:54:49.0', None, 0),
      ('2012-07-23 05:54:49Z', 0, 0),
      ('2012-07-23 05:54:49.000123Z', 0, 123),
      ('2012-07-23T05:54:49+0000', 0, 0),
      ('2012-07-23 05:54:49.00-0000', 0, 0),
      ('2012-07-23T05:54:49.010203+0130', 90, 10203),
      ('2012-07-23 05:54:49-1300', -780, 0),
      ('2012-07-23T05:54:49.123-13:00', -780, 123000),
    ):
      dt = util.parse_iso8601(val)
      self.assertEqual(datetime.datetime(2012, 7, 23, 5, 54, 49, usecs),
                       dt.replace(tzinfo=None))
      if offset is not None:
        offset = datetime.timedelta(minutes=offset)
      self.assertEqual(offset, dt.utcoffset())

  def test_parse_iso8601_duration(self):
    for bad in (None, '', 'bad'):
        self.assertIsNone(util.parse_iso8601_duration(bad))

    for input, expected in (
        ('P0D', (0, 0)),
        (' PT0M ', (0, 0)),
        ('PT2M3S', (0, 123)),
        ('P1Y2M3W4DT5H0M6S', (365 + 2 * 30 + 3 * 7 + 4, 5 * 60 * 60 + 6)),
    ):
        self.assertEqual(datetime.timedelta(*expected),
                         util.parse_iso8601_duration(input))

  def test_to_iso8601_duration(self):
    for bad in (None, 3, 4.5, '', 'bad'):
        self.assertRaises(TypeError, util.to_iso8601_duration, bad)

    for input, expected in (
        ((0, 0), 'P0DT0S'),
        ((1, 2), 'P1DT2S'),
        ((3, 4.5), 'P3DT4S'),
    ):
        self.assertEqual(expected, util.to_iso8601_duration(datetime.timedelta(*input)))

  def test_maybe_iso8601_to_rfc3339(self):
    for input, expected in (
      (None, None),
      ('', ''),
      ('not iso8601!', 'not iso8601!'),
      ('2012-07-23T05:54:49+0000', '2012-07-23T05:54:49+00:00'),
      ('2012-07-23 05:54:49+0200', '2012-07-23T05:54:49+02:00'),
      ('2012-07-23 05:54:49-0800', '2012-07-23T05:54:49-08:00'),
      ('2012-07-23 05:54:49Z', '2012-07-23T05:54:49+00:00'),
      ('2012-07-23T05:54:49', '2012-07-23T05:54:49'),
      ('2012-07-23 05:54:49.321', '2012-07-23T05:54:49.321000'),
    ):
      self.assertEqual(expected, util.maybe_iso8601_to_rfc3339(input))

  def test_maybe_timestamp_to_rfc3339(self):
    for input, expected in (
      (None, None),
      ('', ''),
      ('not a timestamp!', 'not a timestamp!'),
      (1349588757, '2012-10-07T05:45:57+00:00'),
      ('1349588757', '2012-10-07T05:45:57+00:00'),
      (1349588757.123, '2012-10-07T05:45:57.123+00:00'),
      (1349588757.123456, '2012-10-07T05:45:57.123+00:00'),
    ):
      self.assertEqual(expected, util.maybe_timestamp_to_rfc3339(input))

  def test_maybe_timestamp_to_iso8601(self):
    for input, expected in (
      (None, None),
      ('', ''),
      ('not a timestamp!', 'not a timestamp!'),
      (1349588757, '2012-10-07T05:45:57Z'),
      ('1349588757', '2012-10-07T05:45:57Z'),
      (1349588757.123, '2012-10-07T05:45:57.123Z'),
      (1349588757.123456, '2012-10-07T05:45:57.123Z'),
    ):
      self.assertEqual(expected, util.maybe_timestamp_to_iso8601(input))

  def test_to_utc_timestamp(self):
    self.assertIsNone(util.to_utc_timestamp(None))
    self.assertEqual(0, util.to_utc_timestamp(datetime.datetime(1970, 1, 1)))
    self.assertEqual(1446103883.456789, util.to_utc_timestamp(
      datetime.datetime(2015, 10, 29, 7, 31, 23, 456789)))

  def test_as_utc(self):
    dt = datetime.datetime(2000, 1, 1)  # naive
    self.assertEqual(dt, util.as_utc(dt))

    tz = datetime.timezone(datetime.timedelta(minutes=-390))
    dt = datetime.datetime(2000, 1, 1, tzinfo=tz)  # aware

    got = util.as_utc(dt)
    self.assertEqual(datetime.datetime(2000, 1, 1, 6, 30), got)
    self.assertEqual(got, got)

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
      ('http://a.com?x=R+%C3%87', 'http://a.com', {'x': 'R Ç'}),
      ('http://a.com?x=R+%C3%87&x=R+%C3%87', 'http://a.com?x=R+%C3%87', {'x': 'R Ç'}),
    ):
      self.assertEqual(expected, util.add_query_params(url, params))

    for expected, req, params in (
      (urllib.request.Request('http://a.com?x=y'), urllib.request.Request('http://a.com'),
       [('x', 'y')]),
      (urllib.request.Request('http://a.com?x=y&u=v'), urllib.request.Request('http://a.com?x=y'),
       [('u', 'v')]),
      (urllib.request.Request('http://a.com?x=y', data='my data', headers={'X': 'Y'}),
       urllib.request.Request('http://a.com', data='my data', headers={'X': 'Y'}),
       [('x', 'y')]),
    ):
      actual = util.add_query_params(req, params)
      self.assertIsInstance(actual, urllib.request.Request)
      self.assertEqual(expected.get_full_url(), actual.get_full_url())
      self.assertEqual(expected.data, actual.data)
      self.assertEqual(expected.headers, actual.headers)

    query_string = ''
    for _ in range(2):
      query_string = util.add_query_params(query_string, {'x': 'Ryan Çelik'})
      for key, val in urllib.parse.parse_qsl(query_string[1:]):
        self.assertEqual('x', key)
        self.assertEqual('Ryan Çelik', val)

  def test_remove_query_param(self):
    for input, expected, param, val in (
      ('http://a.com', 'http://a.com', 'x', None),
      ('http://a.com?x=', 'http://a.com', 'x', ''),
      ('http://a.com?x=', 'http://a.com?x=', 'u', None),
      ('http://a.com?x=y', 'http://a.com', 'x', 'y'),
      ('http://a.com?x=y&u=v', 'http://a.com?u=v', 'x', 'y'),
      ('http://a.com?x=y&u=v', 'http://a.com?x=y', 'u', 'v'),
      ('http://a.com?x=y&x=z', 'http://a.com', 'x', 'z'),
      ('http://a.com?x=y&x=z', 'http://a.com?x=y&x=z', 'u', None),
      ('http://a.com?x=R+%C3%87', 'http://a.com', 'x', 'R Ç'),
    ):
      self.assertEqual((expected, val), util.remove_query_param(input, param))

  def test_parse_http_equiv(self):
    for input, expected in (
      ('', ''),
      ('0;URL=', ''),
      ('http://a', ''),
      ('=http://a', ''),
      ('URL=http://a', 'http://a'),
      ('0;URL=http://a', 'http://a'),
      ('0;URL=\'http://a\'', 'http://a'),
      ('0;\'URL=http://a\'', 'http://a')
    ):
      self.assertEqual(expected, util.parse_http_equiv(input))

  def test_if_changed(self):
    cache = util.CacheDict()
    updates = {}

    for val in (0, '', []):  # should all be normalized to None
      self.assertIsNone(None, util.if_changed(cache, updates, 'x', val))
      cache['x'] = 0
      self.assertIsNone(None, util.if_changed(cache, updates, 'x', val))
      del cache['x']

    self.assertEqual(1, util.if_changed(cache, updates, 'x', 1))
    self.assertEqual(1, updates['x'])
    cache['x'] = 1
    self.assertIsNone(util.if_changed(cache, updates, 'x', 1))
    self.assertEqual(2, util.if_changed(cache, updates, 'x', 2))
    self.assertEqual(2, updates['x'])

    self.assertIsNone(util.if_changed(cache, updates, 'x', None))
    self.assertEqual(None, updates['x'])

  def test_generate_secret(self):
    self.assertEqual(24, len(util.generate_secret()))

  def test_cache_dict(self):
    data = {1: 2, 3: 4}
    cd = util.CacheDict(data)
    self.assert_equals(data, cd)
    self.assert_equals({}, cd.get_multi([]))
    self.assert_equals({}, cd.get_multi({9}))
    self.assert_equals({1: 2}, cd.get_multi({1, 9}))
    self.assert_equals(data, cd.get_multi({1, 3}))

    # get_multi should handle a generator args ok
    self.assert_equals(data, cd.get_multi(iter([1, 3])))
    self.assert_equals(data, cd.get_multi(list(range(4))))

  def test_is_int(self):
    for arg in 0, 1, -1, '0', '11', 1.0, 12345:
      self.assertTrue(util.is_int(arg), repr(arg))
    for arg in 0.1, 3.14, '3.0', '3xyz', None, self:
      self.assertFalse(util.is_int(arg), repr(arg))

  def test_is_float(self):
    for arg in 0, 1, -1, '0', '11', 1.0, 12345, 0.1, 3.14, '3.0':
      self.assertTrue(util.is_float(arg), repr(arg))
    for arg in '3xyz', None, self:
      self.assertFalse(util.is_float(arg), repr(arg))

  def test_is_base64(self):
    for arg in '', 'asdf', '1', '1===', '_-aglzfmJyaWQtZ3lyDgsSB1R3aXR0ZXIiAXQM':
      self.assertTrue(util.is_base64(arg), repr(arg))
    for arg in 0, 12.2, ')(,.",\'",[---', None, self:
      self.assertFalse(util.is_base64(arg), repr(arg))

  def test_interpret_http_exception(self):
    ihc = util.interpret_http_exception

    self.assertEqual(('402', '402 Payment Required\n\nmy body'), ihc(
        exc.HTTPPaymentRequired(body_template='my body')))

    self.assertEqual(('502', '<p>my body</p>'), ihc(BadGateway('my body')))

    # rate limiting
    ex = HTTPError('url', 429, 'msg', {}, io.StringIO('my body'))
    self.assertFalse(util.is_connection_failure(ex))
    self.assertEqual(('429', 'my body'), ihc(ex))
    # check that it works multiple times even though read() doesn't.
    self.assertEqual(('429', 'my body'), ihc(ex))

    self.assertEqual((None, 'foo bar'), ihc(URLError('foo bar')))

    self.assertEqual(('429', 'my body'), ihc(
        requests.HTTPError(response=util.Struct(status_code='429', text='my body'))))

    # facebook page rate limiting
    def json_str(obj):
      return io.StringIO(str(json_dumps(obj)))

    body = {'error': {
      'type': 'OAuthException',
      'code': 32,
      'message': '(#32) Page request limited reached',
    }}
    code, _ = ihc(HTTPError('url', 400, '', {}, json_str(body)))
    self.assertEqual('429', code)

    # fake gdata.client.RequestError since gdata isn't a dependency
    class RequestError(util.Struct):
      pass

    ex = RequestError(status=429, body='my body')
    self.assertEqual(('429', 'my body'), ihc(ex))

    ex = RequestError(status=429, body=b'my body')
    self.assertEqual(('429', 'my body'), ihc(ex))

    ex = tumblpy.TumblpyError('my body', error_code=429)
    self.assertEqual(('429', 'my body'), ihc(ex))

    ex = tweepy.HTTPException(testutil.requests_response('my body'))
    self.assertEqual(('400', 'my body'), ihc(ex))

    ex = tweepy.TooManyRequests(testutil.requests_response('my body'))
    self.assertEqual(('429', 'my body'), ihc(ex))

    ex = prawcore.exceptions.OAuthException(None, 'invalid_grant', None)
    self.assertEqual(('401', 'invalid_grant error processing request'), ihc(ex))

    ex = prawcore.exceptions.Forbidden(util.Struct(status_code='403', text='foo'))
    self.assertEqual(('403', 'foo'), ihc(ex))

    # Flickr
    #
    # generated by oauth_dropins.flickr_auth.raise_for_failure()
    msg = 'message=Sorry, the Flickr API service is not currently available., flickr code=0'
    self.assertEqual(('504', msg), ihc(HTTPError('url', '400', msg, {}, io.StringIO())))

    # https://console.cloud.google.com/errors/13299057966731352169?project=brid-gy
    self.assertEqual(('504', 'Unknown'),
                     ihc(HTTPError('url', '418', 'Unknown', {}, io.StringIO())))

    # auth failures as HTTPErrors that should become 401s
    for body in (
      # instagram, expired or revoked
      {'meta': {
        'error_type': 'OAuthAccessTokenException',
        'code': 400,
        'error_message': 'The access_token provided is invalid.'
      }},
      # facebook, https://github.com/snarfed/bridgy/issues/59#issuecomment-34549314
      {'error': {
        'type': 'OAuthException',
        'code': 100,
        'message': 'This authorization code has expired.'
      }},
      # facebook, https://github.com/snarfed/bridgy/issues/436
      {'error': {
        'message': 'Error validating access token: Sessions for the user X are not allowed because the user is not a confirmed user.',
        'type': 'OAuthException',
        'code': 190,
        'error_subcode': 464,
      }},
      # facebook, https://github.com/snarfed/bridgy/issues/437
      {'error': {
        'message': 'Permissions error',
        'type': 'FacebookApiException',
        'code': 200,
      }},
      # facebook, revoked
      {'error': {
        'code': 190,
        'error_subcode': 458,
      }},
      # facebook, expired
      {'error': {
        'code': 102,
        'error_subcode': 463,
      }},
      # facebook, changed password
      {'error': {
        'code': 102,
        'error_subcode': 460,
      }},
      # facebook, user removed from page admins
      # https://github.com/snarfed/bridgy/issues/596
      {'error': {
        'code': 190,
        'type': 'OAuthException',
        'message': 'The user must be an administrator of the page in order to impersonate it.',
      }},
      # facebook, deleted page
      {'error': {
        'message': 'This Page access token belongs to a Page that has been deleted.',
        'type': 'OAuthException',
        'code': 190,
      }},
      # facebook, account is flagged for possibly being hacked
      # http://stackoverflow.com/questions/36401621/facebook-oauthexception-code-190-subcode-490-user-is-enrolled-in-a-blocking-l
      {'error': {
        'code': 190,
        'error_subcode': 490,
        'type': 'OAuthException',
        'message': 'Error validating access token: The user is enrolled in a blocking, logged-in checkpoint',
      }},
      # facebook, account is soft-disabled and needs to log in to re-enable
      {'error': {
        'code': 190,
        'error_subcode': 459,
        'type': 'OAuthException',
        'message': 'Error validating access token: You cannot access the app till you log in to www.facebook.com and follow the instructions given.',
      }},
      # twitter
      # https://dev.twitter.com/overview/api/response-codes
      {'errors': [{
        'code': 326,
        'message': 'To protect our users from spam and other malicious activity, this account is temporarily locked. ...',
      }]},
      ):
      for code in 400, 500:
        got_code, got_body = ihc(HTTPError(
          'url', code, 'BAD REQUEST', {}, json_str(body)))
        self.assertEqual('401', got_code, (got_code, body))
        self.assert_equals(body, json_loads(got_body), body)

    # HTTPErrors that *shouldn't* become 401s
    for body in (
      # is_transient should override messages that imply auth failure
      {'error': {
        'message': 'The token provided is invalid.',
        'type': 'OAuthException',
        'is_transient': True,
      }},
      # facebook deprecated API, https://github.com/snarfed/bridgy/issues/480
      {'error': {
        'message': '(#12) notes API is deprecated for versions v2.0 and higher',
        'code': 12,
        'type': 'OAuthException',
      }},
      # facebook too many IDs
      {'error': {
        'message': '(#100) Too many IDs. Maximum: 50. Provided: 54.',
        'code': 100,
        'type': 'OAuthException',
      }},
    ):
      for code, expected in (400, 400), (500, 502):
        got_code, got_body = ihc(HTTPError(
          'url', code, 'BAD REQUEST', {}, json_str(body)))
        self.assertEqual(str(expected), got_code, (code, got_code, body))
        self.assert_equals(body, json_loads(got_body), body)

    # facebook temporarily unavailable with is_transient
    # https://github.com/snarfed/bridgy/issues/450
    fb_transient = {'error': {
      'message': '(#2) Service temporarily unavailable',
      # also seen:
      # 'message': 'An unexpected error has occurred. Please retry your request later.',
      'code': 2,
      'type': 'OAuthException',
      'is_transient': True,
    }}
    for code in (400, 500):
      body = json_str(fb_transient)
      self.assertEqual(
        ('503', body.getvalue()),
        ihc(HTTPError('url', code, 'BAD REQUEST', {}, body)))

    # pleroma JSON string error message
    # https://console.cloud.google.com/errors/CP3p1f2g_MeF5AE
    code, body = ihc(HTTPError('url', 500, '', {}, json_str('Something went wrong')))
    self.assertEqual('502', code)
    self.assertEqual('"Something went wrong"', body)

    # Unstodon (Mastodon fork, https://git.sleeping.town/sleeping-town/unstodon )
    # evidently includes just the HTTP status code in response bodies, eg '404'
    # make sure we don't assume it's a dict
    resp = testutil.requests_response('404', status=404)
    self.assertEqual(('404', '404'), ihc(requests.HTTPError(response=resp)))

    # make sure we handle non-facebook JSON bodies ok
    wordpress_rest_error = json_str({
      'error': 'unauthorized',
      'message': 'Comments on this post are closed',
    })
    self.assertEqual(
      ('402', wordpress_rest_error.getvalue()),
      ihc(HTTPError('url', 402, 'BAD REQUEST', {}, wordpress_rest_error)))

    # HTTPError.reason can be an exception as well as a string
    err = socket.error(-1, 'foo bar')
    self.assertEqual(
      ('504', '[Errno -1] foo bar'),
      ihc(HTTPError('url', None, err, {}, None)))

    # upstream connection failures are converted to 504
    self.assertEqual(('504', 'foo bar'), ihc(socket.timeout('foo bar')))

    self.assertEqual(('504', 'foo bar'),
                     ihc(prawcore.exceptions.ResponseException(
                       testutil.requests_response('foo bar', status=504))))

  def test_ignore_http_4xx_error(self):
    x = 0
    with util.ignore_http_4xx_error():
      x = 1
      raise exc.HTTPNotFound()
      x = 2

    self.assertEqual(1, x)

    for exc_cls in AssertionError, exc.HTTPInternalServerError:
      with self.assertRaises(exc_cls):
        with util.ignore_http_4xx_error():
          raise exc_cls()

  def test_is_connection_failure(self):
    for e in (
        socket.timeout(),
        requests.ConnectionError(),
        requests.TooManyRedirects(),
        http.client.NotConnected(),
        URLError(socket.gaierror('foo bar')),
        urllib3.exceptions.TimeoutError(),
        Exception('Connection closed unexpectedly by server at URL: ...'),
        ssl.SSLError(),
        prawcore.exceptions.RequestException(None, None, None),
    ):
      self.assertTrue(util.is_connection_failure(e), repr(e))

    for e in (None, 3, 'asdf', IOError(), http.client.HTTPException('unknown'),
              URLError('asdf'), HTTPError('url', 403, 'msg', {}, None),
              ):
      self.assertFalse(util.is_connection_failure(e), repr(e))

  def test_file_limiter(self):
    buf = io.StringIO('abcdefghijk')

    lim = util.FileLimiter(buf, 1)
    self.assertEqual('a', lim.read())
    self.assertEqual(b'', lim.read())
    self.assertFalse(lim.ateof)

    lim = util.FileLimiter(buf, 1)
    self.assertEqual('b', lim.read(2))
    self.assertEqual(b'', lim.read(2))

    lim = util.FileLimiter(buf, 1)
    self.assertEqual('c', lim.read(1))
    self.assertEqual(b'', lim.read(1))

    lim = util.FileLimiter(buf, 5)
    self.assertEqual('d', lim.read(1))
    self.assertEqual('efgh', lim.read(6))
    self.assertEqual(b'', lim.read(6))
    self.assertFalse(lim.ateof)

    lim = util.FileLimiter(buf, 5)
    self.assertEqual('ij', lim.read(2))
    self.assertEqual('k', lim.read())
    self.assertEqual('', lim.read())
    self.assertTrue(lim.ateof)

  def test_base_url(self):
    for expected, url in (
        ('http://site/', 'http://site/'),
        ('http://site/path/', 'http://site/path/'),
        ('http://site/path/', 'http://site/path/leaf'),
        ('http://site/path/', 'http://site/path/leaf?query#frag'),
      ):
      self.assertEqual(expected, util.base_url(url))

  def test_is_web(self):
    for good in 'http://foo', 'https://bar/baz?biff=boff':
      self.assertTrue(util.is_web(good), good)

    for bad in (None, 3, '', ['http://foo'], 'foo', 'foo.com/bar',
                'tag:foo.com:bar', 'acct:x@y.z', 'http:/x'):
      self.assertFalse(util.is_web(bad), bad)

  def test_follow_redirects(self):
    for _ in range(2):
      self.expect_requests_head('http://will/redirect',
                                redirected_url='http://final/url')
    self.mox.ReplayAll()

    self.assert_equals(
      'http://final/url',
      util.follow_redirects('http://will/redirect').url)

    # another call without cache should refetch
    self.assert_equals(
      'http://final/url',
      util.follow_redirects.__wrapped__('http://will/redirect').url)

    # another call with cache shouldn't refetch
    self.assert_equals(
      'http://final/url',
      util.follow_redirects('http://will/redirect').url)

  def test_follow_redirects_with_refresh_header(self):
    headers = {'x': 'y'}
    self.expect_requests_head('http://will/redirect', headers=headers,
                              response_headers={'refresh': '0; url=http://refresh'})
    self.expect_requests_head('http://refresh', headers=headers,
                              redirected_url='http://final')

    self.mox.ReplayAll()
    self.assert_equals('http://final',
                       util.follow_redirects('http://will/redirect',
                                             headers=headers).url)

  def test_follow_redirects_defaults_scheme_to_http(self):
    self.expect_requests_head('http://foo/bar', redirected_url='http://final')
    self.mox.ReplayAll()
    self.assert_equals('http://final', util.follow_redirects('foo/bar').url)

  def test_url_canonicalizer(self):
    def check(expected, input, **kwargs):
      self.assertEqual(expected, util.UrlCanonicalizer(**kwargs)(input))

    check('https://fa.ke/post', 'http://www.fa.ke/post')
    check('http://fa.ke/123', 'https://fa.ke/123', scheme='http')
    check('https://fa.ke/123', 'http://fa.ke/123', domain='fa.ke')
    check(None, 'http://fa.ke/123', domain='a.bc')

    check('https://www.fa.ke/123', 'https://fa.ke/123', subdomain='www')
    check('https://foo.fa.ke/123', 'https://www.fa.ke/123', subdomain='foo')
    check('https://foo.fa.ke/123', 'https://foo.fa.ke/123', subdomain='bar')

    check('https://fa.ke/123?x=y', 'http://fa.ke/123?x=y', query=True)
    check('https://fa.ke/123', 'http://fa.ke/123?x=y#abc', query=False)

    check('https://fa.ke/123#abc', 'http://fa.ke/123#abc', fragment=True)
    check('https://fa.ke/123', 'http://fa.ke/123#abc', fragment=False)

    check('https://fa.ke/123/', 'http://fa.ke/123', trailing_slash=True)
    check('https://fa.ke/123', 'http://fa.ke/123/', trailing_slash=False)

    check('https://fa.ke/123/?x=y#abc', 'http://fa.ke/123?x=y#abc',
          query=True, fragment=True, trailing_slash=True)
    check('https://fa.ke/123', 'http://fa.ke/123/?x=y#abc',
          query=False, fragment=False, trailing_slash=False)

    self.unstub_requests_head()
    self.expect_requests_head('https://a.b/post', redirected_url='https://x.yz/post')
    self.expect_requests_head('https://c.d/post', headers={'Foo': 'bar'},
                              redirected_url='https://x.yz/post')
    self.expect_requests_head('https://e.f/post', status_code=404)
    self.mox.ReplayAll()

    check('https://x.yz/post', 'http://a.b/post')
    check('https://x.yz/post', 'http://c.d/post', headers={'Foo': 'bar'})
    check(None, 'http://e.f/post')

    # do these after unstub_requests_head to check that they don't HEAD
    check('http://fa.ke/good', 'http://fa.ke/good', approve='.*/good')
    check(None, 'http://fa.ke/bad', reject='.*/bad')
    check(None, 'mailto:xyz@fa.ke')

  def test_load_file_lines(self):
    for expected, contents in (
      ((), ''),
      ((), '\n\n'),
      ((), '   \n# asdf\n	\n# qwert\n'),
      (('asdf', 'qwert'), '# header\nasdf\n\nqwert\n\nqwert\n  # comment\n  asdf  '),
      (('zzang.kr', '›.ws'), 'zzang.kr\n›.ws'),
    ):
      self.assert_equals(set(expected),
                         util.load_file_lines(io.StringIO(contents)))

  def test_wide_unicode(self):
    empty = util.WideUnicode('')
    self.assert_equals(0, len(empty))
    self.assert_equals('', empty[2:3])
    with self.assertRaises(IndexError):
      empty[0]

    ascii = util.WideUnicode('asdf')
    self.assert_equals(4, len(ascii))
    self.assert_equals('s', ascii[1])
    self.assert_equals('sd', ascii[1:-1])
    self.assert_equals('', ascii[0:0])
    self.assert_equals('', ascii[8:9])
    with self.assertRaises(IndexError):
      ascii[5]

    low = util.WideUnicode('xÇy')
    self.assert_equals(3, len(low))
    self.assert_equals('xÇ', low[:2])
    self.assert_equals('y', low[2])
    self.assert_equals('', low[8:])
    with self.assertRaises(IndexError):
      low[3]

    high = util.WideUnicode('💯💯💯')
    self.assert_equals(3, len(high))
    self.assert_equals('💯', high[2])
    self.assert_equals('💯', high[2:3])
    self.assert_equals('', high[8:])
    self.assert_equals(high, high[:9])
    with self.assertRaises(IndexError):
      high[3]

  def test_encode_decode_oauth_state(self):
    for bad in None, 1, [], (), 'x':
      with self.assertRaises(TypeError):
        util.encode_oauth_state(bad)

    for bad in 1, [], (), {}:
      with self.assertRaises(TypeError):
        util.decode_oauth_state(bad)

    self.assertEqual({}, util.decode_oauth_state(None))

    for obj, str in (
        ({}, '{}'),
        ({'foo': 'bar', 'baz': None}, '{"foo":"bar"}'),
        ({'b': 1, 'a': 2}, '{"a":2,"b":1}'),
    ):
      self.assert_equals(str, urllib.parse.unquote(util.encode_oauth_state(obj)))
      self.assert_equals(obj, util.decode_oauth_state(str))
      self.assert_equals(obj, util.decode_oauth_state(util.encode_oauth_state(obj)))
      self.assert_equals(str, urllib.parse.unquote(util.encode_oauth_state(util.decode_oauth_state(str))))

  def test_sniff_json_or_form_encoded(self):
    for expected, input in (
      ({'a': 1, 'b': 2}, '{"a":1,"b":2}'),
      ({'a': '1', 'b': '2'}, 'a=1&b=2'),
      ({'a': '1', 'b': '2'}, '&a=1&b=2&'),
      ({'a': 'x'}, 'a=x'),
      (['a', 'b'], '["a", "b"]'),
      (['a', {'b': 3}], '["a", {"b": 3}]'),
      ({}, '{}'),
      ({}, ''),
      (False, 'false'),
    ):
      self.assert_equals(expected, util.sniff_json_or_form_encoded(input), input)

  def test_requests_post_with_redirects_no_redirect(self):
    self.expect_requests_post('http://xyz', 'abc', allow_redirects=False)
    self.mox.ReplayAll()
    resp = util.requests_post_with_redirects('http://xyz')
    self.assert_equals('abc', resp.text)

  def test_requests_post_with_redirects_two_redirects(self):
    self.expect_requests_post(
      'http://first', allow_redirects=False, status_code=302,
      response_headers={'Location': 'https://second'})
    self.expect_requests_post(
      'https://second', allow_redirects=False, status_code=301,
      response_headers={'Location': 'https://third'})
    self.expect_requests_post('https://third', 'abc', allow_redirects=False)
    self.mox.ReplayAll()

    resp = util.requests_post_with_redirects('http://first')
    self.assert_equals('abc', resp.text)
    self.assert_equals('https://third', resp.url)

  def test_requests_post_with_redirects_error(self):
    self.expect_requests_post('http://first', 'abc', allow_redirects=False,
                              status_code=400)
    self.mox.ReplayAll()

    with self.assertRaises(requests.HTTPError) as e:
      util.requests_post_with_redirects('http://first')

    self.assert_equals('abc', e.exception.response.text)
    self.assert_equals(400, e.exception.response.status_code)

  def test_requests_post_with_redirects_redirect_then_error(self):
    self.expect_requests_post('http://ok', allow_redirects=False, status_code=302,
                              response_headers={'Location': 'https://bad'})
    self.expect_requests_post('https://bad', 'abc', allow_redirects=False,
                              status_code=400)
    self.mox.ReplayAll()

    with self.assertRaises(requests.HTTPError) as e:
      util.requests_post_with_redirects('http://ok')

    self.assert_equals('abc', e.exception.response.text)
    self.assert_equals(400, e.exception.response.status_code)

  def test_requests_post_with_redirects_too_many_redirects(self):
    for _ in range(requests.models.DEFAULT_REDIRECT_LIMIT):
      self.expect_requests_post(
        'http://xyz', 'abc', allow_redirects=False, status_code=302,
        response_headers={'Location': 'http://xyz'})
    self.mox.ReplayAll()

    with self.assertRaises(requests.TooManyRedirects) as e:
      util.requests_post_with_redirects('http://xyz')

    self.assert_equals('abc', e.exception.response.text)
    self.assert_equals(302, e.exception.response.status_code)
    self.assert_equals('http://xyz', e.exception.response.headers['Location'])

  def test_requests_get_too_big(self):
    for type in 'text/html', 'application/json', '', 'image/jpeg':
      self.expect_requests_get('http://xyz', 'abc', response_headers={
        'Content-Type': type,
        'Content-Length': util.MAX_HTTP_RESPONSE_SIZE + 1,
      })
    self.mox.ReplayAll()

    for i in range(2):
      self.assertEqual(422, util.requests_get('http://xyz').status_code, i)

    for _ in range(2):
      self.assertEqual(200, util.requests_get('http://xyz').status_code)

  def test_requests_get_unicode_url_ValueError(self):
    """https://console.cloud.google.com/errors/CPzNwYaL3tjb9gE"""
    url = 'http://acct:abc⊙de/'
    self.expect_requests_get(url).AndRaise(ValueError())
    self.mox.ReplayAll()
    self.assertRaises(BadRequest, util.requests_get, url, gateway=True)

  def test_requests_get_unicode_url_ConnectionError(self):
    """https://console.cloud.google.com/errors/CPzNwYaL3tjb9gE"""
    url = 'http://acct:abc⊙de/'
    self.expect_requests_get(url).AndRaise(requests.ConnectionError())
    self.mox.ReplayAll()
    self.assertRaises(BadGateway, util.requests_get, url, gateway=True)

  def test_requests_get_invalid_emoji_domain_fallback_to_domain2idnaError(self):
    url = 'http://abc⊙.de/'
    self.expect_requests_get(url).AndRaise(requests.exceptions.InvalidURL())
    self.expect_requests_get('http://xn--abc-yr2a.de/', 'ok')
    self.mox.ReplayAll()

    resp = util.requests_get(url)
    self.assertEqual(200, resp.status_code)
    self.assertEqual(url, resp.url)

  def test_set_user_agent_requests(self):
    self.expect_requests_get('http://xyz', 'abc', headers={'User-Agent': 'Fooey'})
    self.mox.ReplayAll()

    util.set_user_agent('Fooey')
    self.assertEqual(200, util.requests_get('http://xyz').status_code)

  def test_set_user_agent_urlopen(self):
    self.expect_urlopen('http://xyz', 'abc', headers={'User-agent': 'Fooey'})
    self.mox.ReplayAll()

    util.set_user_agent('Fooey')
    self.assertEqual(200, util.urlopen('http://xyz').status_code)

  def test_fetch_mf2(self):
    html = '<html><body class="h-entry"><p class="e-content">asdf</p></body></html>'
    self.expect_requests_get('http://xyz', html)
    self.mox.ReplayAll()

    self.assert_equals({
      'items': [{
        'type': ['h-entry'],
        'properties': {
          'content': [{'value': 'asdf', 'html': 'asdf'}],
        },
      }],
      'url': 'http://xyz',
    }, util.fetch_mf2('http://xyz'), ignore=['debug', 'rels', 'rel-urls'])

  def test_fetch_mf2_fragment(self):
    html = """\
<html>
<body>
<div id="a" class="h-entry"><p class="e-content">asdf</p></div>
<div id="b" class="h-entry"><p class="e-content">qwer</p></div>
</body>
</html>"""
    self.expect_requests_get('http://xyz', html)
    self.mox.ReplayAll()

    self.assert_equals({
      'items': [{
        'type': ['h-entry'],
        'id': 'b',
        'properties': {
          'content': [{'value': 'qwer', 'html': 'qwer'}],
        },
      }],
      'url': 'http://xyz',
    }, util.fetch_mf2('http://xyz#b'), ignore=['debug', 'rels', 'rel-urls'])

  def test_fetch_mf2_require_backlink_missing(self):
    html = '<html><body class="h-entry"><p class="e-content">asdf</p></body></html>'
    self.expect_requests_get('http://xyz', html).MultipleTimes()
    self.mox.ReplayAll()

    with self.assertRaises(ValueError):
      util.fetch_mf2('http://xyz', require_backlink='http://back')

    with self.assertRaises(ValueError):
      util.fetch_mf2('http://xyz', require_backlink=['http://back', 'http://link'])

  def test_fetch_mf2_require_backlink_found(self):
    html = '<html><body class="h-entry"><p class="e-content"><a href="http://back"></a></p></body></html>'
    self.expect_requests_get('http://xyz', html).MultipleTimes()
    self.mox.ReplayAll()

    self.assertIsNotNone(util.fetch_mf2('http://xyz', require_backlink='http://back'))
    self.assertIsNotNone(util.fetch_mf2(
      'http://xyz',require_backlink=['http://link', 'http://back']))
