# -*- coding: utf-8 -*-
"""Property-based tests for util.py, using hypothesis.

https://hypothesis.readthedocs.io/
"""
from datetime import datetime, timedelta, timezone
import re
from string import ascii_letters, ascii_lowercase, digits
import urllib.parse

from hypothesis import assume, given, strategies as st
from hypothesis.provisional import urls

from ... import testutil, util

# values that trim_nulls strips out
NULLS = (None, {}, [], (), '', set(), frozenset())

SCALARS = st.booleans() | st.integers() | st.text() | st.none()

# nested dicts and lists of scalars, ie roughly a JSON document
NESTED = st.recursive(
  SCALARS,
  lambda children: st.lists(children) | st.dictionaries(st.text(), children),
  max_leaves=10)

# no ':' or ',', which are tag URI delimiters
TAG_PART = st.text(alphabet=ascii_letters + digits + '.-_/@', min_size=1)

# no '@', which separates username from host, and nothing urlparse treats as a
# scheme, path, query, or fragment delimiter
ACCT_PART = st.text(alphabet=ascii_letters + digits + '.-_', min_size=1)

# non-empty ranges. overlaps() only handles step 1.
RANGES = st.builds(lambda start, length: range(start, start + length),
                   st.integers(min_value=-100, max_value=100),
                   st.integers(min_value=1, max_value=20))

# fixed offsets, ie what parse_iso8601 returns. as_utc only handles these; it
# raises TypeError on zoneinfo timezones.
FIXED_OFFSETS = st.builds(lambda minutes: timezone(timedelta(minutes=minutes)),
                          st.integers(min_value=-23 * 60 - 59,
                                      max_value=23 * 60 + 59))
TIMEZONES = st.timezones() | FIXED_OFFSETS
DATETIMES = st.datetimes(timezones=TIMEZONES | st.none())

# range that POSIX timestamps round trip cleanly through float, and that
# humanize.naturaltime can handle without overflowing
MODERN_DATETIMES = st.datetimes(min_value=datetime(1970, 1, 1),
                                max_value=datetime(2100, 1, 1),
                                timezones=TIMEZONES | st.none())
TIMESTAMPS = (st.integers(min_value=0, max_value=2 ** 31)
              | st.floats(min_value=0, max_value=2 ** 31, allow_nan=False,
                          allow_infinity=False))

# no 'utm_' or 'source' name, so clean_url keeps all of these, and no blank
# values, which its parse_qsl call drops. otherwise arbitrary, to exercise the
# parse_qsl/urlencode round trip.
QUERY_PARAMS = st.lists(st.tuples(
  st.text(min_size=1).filter(
    lambda name: not name.startswith('utm_') and name != 'source'),
  st.text(min_size=1)))

# plain words, with no dots, so they never look like bare domains
WORDS = st.text(ascii_lowercase, min_size=1, max_size=8)

# characters provisional urls() generates that PATH_QUERY_RE stops at
UNMATCHED_URL_CHARS = set('!*\',')
# HOST_RE only matches a port of 2-6 digits
TINY_PORT_RE = re.compile(r'https?://[^/]*:\d/')


class UtilHypothesisTest(testutil.TestCase):

  @given(st.lists(SCALARS))
  def test_uniquify(self, input):
    got = util.uniquify(input)

    expected = []
    for elem in input:
      if elem not in expected:
        expected.append(elem)

    self.assertEqual(expected, got)

  @given(NESTED)
  def test_trim_nulls(self, input):
    trimmed = util.trim_nulls(input)
    self.assert_no_nulls(trimmed)
    self.assertEqual(trimmed, util.trim_nulls(trimmed))

  def assert_no_nulls(self, val):
    if isinstance(val, dict):
      values = val.values()
    if isinstance(val, list):
      values = val
    else:
      return

    for v in values:
      self.assertNotIn(v, NULLS, f'{v!r} in {val!r}')
      self.assert_no_nulls(v)

  @given(st.lists(st.integers(), unique=True), st.integers())
  def test_add_then_remove_restores_seq(self, seq, val):
    orig = list(seq)
    added = util.add(seq, val)
    self.assertIn(val, seq)
    self.assertEqual(val in orig, not added)

    util.remove(seq, val)
    self.assertNotIn(val, seq)
    if added:
      self.assertEqual(orig, seq)

  @given(RANGES, st.lists(RANGES))
  def test_overlaps(self, val, ranges):
    expected = any(set(val) & set(r) for r in ranges)
    self.assertEqual(expected, util.overlaps(val, ranges))

  @given(TAG_PART, TAG_PART, st.integers(min_value=1, max_value=9999) | st.none())
  def test_tag_uri_round_trips(self, domain, name, year):
    self.assertEqual((domain, name),
                     util.parse_tag_uri(util.tag_uri(domain, name, year=year)))

  @given(st.integers())
  def test_is_int_is_float_integers(self, val):
    self.assertTrue(util.is_int(val))
    # not is_float(val): for numbers the conversion also has to be lossless, so
    # eg is_float(2 ** 53 + 1) is False
    self.assertTrue(util.is_int(str(val)))
    self.assertTrue(util.is_float(str(val)))

  @given(st.floats(allow_nan=False, allow_infinity=False))
  def test_is_int_is_float_floats(self, val):
    self.assertTrue(util.is_float(val))
    self.assertEqual(val.is_integer(), util.is_int(val))

  @given(st.text())
  def test_is_int_is_float_strings(self, val):
    if util.is_int(val):
      self.assertTrue(util.is_float(val))

  @given(st.lists(st.integers()) | st.dictionaries(st.text(), st.text()) | st.none())
  def test_is_int_is_float_non_numbers(self, val):
    self.assertFalse(util.is_int(val))
    self.assertFalse(util.is_float(val))

  @given(st.text(), st.integers(min_value=1, max_value=20),
         st.integers(min_value=4, max_value=200))
  def test_ellipsize(self, text, words, chars):
    got = util.ellipsize(text, words=words, chars=chars)

    if len(text.split()) <= words and len(text) <= chars:
      self.assertEqual(text, got)
    else:
      self.assertLessEqual(len(got), chars)
      self.assertLessEqual(len(got.split()), words)
      self.assertTrue(got.endswith('...'), got)

  @given(urls(), st.text(min_size=1), st.text())
  def test_add_then_remove_query_param_round_trips(self, url, param, val):
    added = util.add_query_params(url, {param: val})
    removed, got = util.remove_query_param(added, param)
    self.assertEqual(val, got)
    self.assertEqual(url, removed)

  @given(st.dictionaries(st.text(), NESTED))
  def test_encode_then_decode_oauth_state_round_trips(self, obj):
    self.assert_equals(util.trim_nulls(obj),
                       util.decode_oauth_state(util.encode_oauth_state(obj)))

  @given(st.lists(urls() | st.just('') | st.none()))
  def test_dedupe_urls(self, urls):
    got = util.dedupe_urls(urls)

    self.assertLessEqual(len(got), len(urls))
    self.assertEqual(len(got), len(set(got)))
    for url in got:
      self.assertEqual(url, util.normalize_url(url))

    self.assertEqual(got, util.dedupe_urls(got))

  @given(st.text(), st.integers(min_value=0, max_value=50),
         st.integers(min_value=0, max_value=50))
  def test_wide_unicode(self, str, start, end):
    wide = util.WideUnicode(str)

    self.assertEqual(len(str), len(wide))
    self.assertEqual(str, ''.join(wide[i] for i in range(len(wide))))
    self.assertEqual(str[start:end], wide[start:end])
    self.assertEqual(str[start:], wide[start:])

  @given(DATETIMES)
  def test_parse_iso8601_round_trips(self, dt):
    iso = dt.isoformat()
    self.assertEqual(dt, util.parse_iso8601(iso))
    self.assertEqual(dt, util.parse_iso8601(f'  {iso} \n'))
    # offset without a colon, and Z instead of +00:00
    self.assertEqual(dt, util.parse_iso8601(
      util.TIMEZONE_OFFSET_RE.sub(lambda m: m.group().replace(':', ''), iso)))
    if dt.utcoffset() == timedelta(0):
      self.assertEqual(dt, util.parse_iso8601(iso.replace('+00:00', 'Z')))

  @given(st.timedeltas(min_value=timedelta(0)))
  def test_iso8601_duration_round_trips(self, delta):
    # to_iso8601_duration silently drops fractional seconds
    expected = timedelta(days=delta.days, seconds=delta.seconds)
    self.assertEqual(
      expected, util.parse_iso8601_duration(util.to_iso8601_duration(delta)))

  @given(MODERN_DATETIMES)
  def test_to_utc_timestamp(self, dt):
    # naive datetimes are assumed to already be UTC
    expected = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    self.assertAlmostEqual(expected.timestamp(), util.to_utc_timestamp(dt),
                           places=4)
    self.assertIsNone(util.to_utc_timestamp(None))

  @given(st.datetimes(timezones=FIXED_OFFSETS | st.none()))
  def test_as_utc(self, dt):
    got = util.as_utc(dt)
    self.assertIsNone(got.tzinfo)
    if dt.tzinfo:
      dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

    self.assertEqual(dt, got)

  @given(TIMESTAMPS)
  def test_maybe_timestamp_to_rfc3339_and_iso8601(self, timestamp):
    rfc3339 = util.maybe_timestamp_to_rfc3339(timestamp)
    self.assertAlmostEqual(float(timestamp),
                          util.parse_iso8601(rfc3339).timestamp(), places=2)
    self.assertEqual(rfc3339.replace('+00:00', 'Z'),
                     util.maybe_timestamp_to_iso8601(timestamp))

  @given(st.lists(st.text()) | st.dictionaries(st.text(), st.text())
         | st.text(ascii_letters, min_size=1) | st.none())
  def test_maybe_timestamp_passes_through_non_timestamps(self, input):
    self.assertEqual(input, util.maybe_timestamp_to_rfc3339(input))
    self.assertEqual(input, util.maybe_timestamp_to_iso8601(input))

  @given(DATETIMES)
  def test_maybe_iso8601_to_rfc3339(self, dt):
    got = util.maybe_iso8601_to_rfc3339(dt.isoformat())
    self.assertEqual(dt, util.parse_iso8601(got))
    self.assertEqual(got, util.maybe_iso8601_to_rfc3339(got))

  @given(st.integers() | st.text(ascii_letters) | st.lists(st.text())
         | st.dictionaries(st.text(), st.text()) | st.none())
  def test_maybe_iso8601_to_rfc3339_passes_through_non_dates(self, input):
    self.assertEqual(input, util.maybe_iso8601_to_rfc3339(input))

  @given(MODERN_DATETIMES, MODERN_DATETIMES)
  def test_naturaltime_ignores_timezones(self, val, when):
    self.assertEqual(util.naturaltime(val.replace(tzinfo=None),
                                      when=when.replace(tzinfo=None)),
                     util.naturaltime(val, when=when))

  @given(urls())
  def test_domain_from_link(self, url):
    hostname = urllib.parse.urlparse(url).hostname
    self.assertEqual(hostname, util.domain_from_link(url, minimize=False))

    # no scheme
    self.assertEqual(hostname, util.domain_from_link(
      urllib.parse.urlparse(url).netloc, minimize=False))

    for empty in None, '':
      self.assertIsNone(util.domain_from_link(empty))

  @given(urls(), st.text(ascii_lowercase, min_size=1, max_size=8))
  def test_domain_or_parent_in(self, url, subdomain):
    domain = util.domain_from_link(url)

    self.assertTrue(util.domain_or_parent_in(url, [domain]))
    self.assertTrue(util.domain_or_parent_in(domain, [domain]))
    self.assertTrue(util.domain_or_parent_in(f'{subdomain}.{domain}', [domain]))
    self.assertTrue(util.domain_or_parent_in(f'{subdomain}.{domain}',
                                             [f'.{domain}']))

    self.assertFalse(util.domain_or_parent_in(domain, []))
    self.assertFalse(util.domain_or_parent_in('', [domain]))
    self.assertFalse(util.domain_or_parent_in(domain, [f'{subdomain}.{domain}']))

    with self.assertRaises(ValueError):
      util.domain_or_parent_in(domain, domain)

  @given(QUERY_PARAMS)
  def test_clean_url_removes_tracking_params(self, params):
    tracking = [('utm_campaign', 'a'), ('utm_content', 'b'), ('utm_medium', 'c'),
                ('utm_source', 'd'), ('utm_term', 'e'), ('source', 'rss-1')]
    base = 'http://example.com/post'
    with_tracking = f'{base}?{urllib.parse.urlencode(params + tracking)}'
    without = f'{base}?{urllib.parse.urlencode(params)}'

    got = util.clean_url(with_tracking)
    self.assertEqual(util.clean_url(without), got)
    self.assertEqual(got, util.clean_url(got))
    # everything else survives, unchanged and in order
    self.assertEqual(params, urllib.parse.parse_qsl(
      urllib.parse.urlparse(got).query, keep_blank_values=True))

    for empty in None, '':
      self.assertEqual(empty, util.clean_url(empty))

  @given(st.lists(urls()), WORDS)
  def test_extract_links(self, input, separator):
    for url in input:
      assume(not UNMATCHED_URL_CHARS & set(url))
      assume(not TINY_PORT_RE.match(url))
      # tokenize_links trims trailing punctuation
      assume(url[-1] not in '.!?,;:)')

    self.assertEqual(util.uniquify(input),
                     util.extract_links(f' {separator} '.join(input)))

  @given(st.lists(urls()), WORDS)
  def test_extract_links_returns_unique_substrings(self, input, separator):
    text = f' {separator} '.join(input)
    links = util.extract_links(text)
    self.assertEqual(links, util.uniquify(links))
    for link in links:
      self.assertIn(link, text)

  @given(st.lists(urls()), WORDS, st.text('.!?,;:)', max_size=4))
  def test_tokenize_links_reconstructs_text(self, input, separator, punctuation):
    text = ''.join(f'{url}{punctuation} {separator} ' for url in input)
    links, splits = util.tokenize_links(text)
    self.assertEqual(len(links) + 1, len(splits))

    reconstructed = splits[0]
    for link, split in zip(links, splits[1:]):
      reconstructed += link + split

    self.assertEqual(text, reconstructed)

  @given(ACCT_PART, ACCT_PART)
  def test_parse_acct_uri(self, username, host):
    for uri in f'acct:{username}@{host}', f'{username}@{host}':
      self.assertEqual((username, host), util.parse_acct_uri(uri))
      self.assertEqual((username, host), util.parse_acct_uri(uri, [host]))
      self.assertEqual((username, host),
                       util.parse_acct_uri(uri, ['other.com', host]))

      with self.assertRaises(ValueError):
        util.parse_acct_uri(uri, [f'not-{host}'])

  @given(st.sets(WORDS))
  def test_load_file_lines(self, lines):
    self.assertEqual(lines, util.load_file_lines(list(lines)))
    # blank lines and comments are ignored
    self.assertEqual(lines, util.load_file_lines(
      list(lines) + ['', '   ', '# comment', '#']))
    self.assertEqual(set(), util.load_file_lines('/nonexistent/file'))

  @given(urls())
  def test_url_canonicalizer(self, url):
    canonicalize = util.UrlCanonicalizer(redirects=False)
    got = canonicalize(url)
    self.assertTrue(got.startswith('https://'), got)
    self.assertEqual(got, canonicalize(got))

    self.assertEqual(url, util.UrlCanonicalizer(redirects=False, approve='.*')(url))
    self.assertIsNone(util.UrlCanonicalizer(redirects=False, reject='.*')(url))
    self.assertIsNone(
      util.UrlCanonicalizer(redirects=False, domain='nope.invalid')(url))
