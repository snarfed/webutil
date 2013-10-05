#!/usr/bin/python
"""Unit tests for util.py.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import datetime
from webob import exc

import testutil
import util


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

  def test_list(self):
    self.assertEqual([{'xyz': 3}], util.trim_nulls([{'abc': None, 'xyz': 3}]))

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

  def test_zero(self):
    self.assertEqual({1: 0}, util.trim_nulls({1: 0}))

  def test_favicon_for_url(self):
    for url in ('http://a.org/b/c?d=e&f=g', 'https://a.org/b/c', 'http://a.org/'):
      self.assertEqual('http://a.org/favicon.ico', util.favicon_for_url(url))

  def test_domain_from_link(self):
    self.assertEqual('localhost', util.domain_from_link('http://localhost/foo'))
    for good_link in 'asdf.com', 'https://asdf.com/', 'asdf.com/foo?bar#baz':
      self.assertEqual('asdf.com', util.domain_from_link(good_link), good_link)

    for bad_link in '', '  ', 'a&b.com', 'http://', 'file:///':
      self.assertEquals(None, util.domain_from_link(bad_link))

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

  def test_linkify_empty(self):
    self.assertEqual('', util.linkify(''))

  def test_linkify_no_links(self):
    self.assertEqual('asdf qwert', util.linkify('asdf qwert'))

  def test_linkify_links(self):
    self.assertEqual(
      'asdf <a href="http://foo.com">http://foo.com</a> qwert '
      '<a class="x" href="http://foo.com" >xyz</a> <a href="http://www.bar.com">www.bar.com</a>',
      util.linkify('asdf http://foo.com qwert <a class="x" href="http://foo.com" >xyz</a> www.bar.com'))

  def test_linkify_tco(self):
    self.assertEqual(
      'asdf <a href="http://t.co/asdf">http://t.co/asdf</a> qwert',
      util.linkify('asdf http://t.co/asdf qwert'))

  def test_linkify_ignores_anchor_tags(self):
    for text in ('X <a class="x" href="http://foo.com" >xyz</a> Y',
                 '<a href="http://foo.com"  class="x">xyz</a> Y',
                 "X <a href='http//foo.com' />"):
      self.assertEqual(text, util.linkify(text))

  def test_linkify_links_and_anchor_tags(self):
    self.assertEqual(
      'asdf <a href="http://foo.com">foo</a> qwert '
      '<a href="http://www.bar.com">www.bar.com</a>',
      util.linkify('asdf <a href="http://foo.com">foo</a> qwert www.bar.com'))

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
