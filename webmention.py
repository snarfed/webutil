"""Webmention endpoint discovery and sending.

Spec: https://webmention.net/draft/
"""
from collections import namedtuple
import logging
import re
from urllib.parse import urljoin

from . import util

LINK_HEADER_RE = re.compile(
  r'''<([^>]+)>; rel=["']?(https?://)?webmention(\.org/?)?["']?''')

# Returned by discover(). Attributes:
#   endpoint: str
#   response: requests.Response
Endpoint = namedtuple('Endpoint', ('endpoint', 'response'))


def discover(url, **requests_kwargs):
  """Discovers a URL's webmention endpoint.

  Args:
    url: str
    requests_kwargs: passed to :meth:`requests.post`

  Returns: :class:`Endpoint`. If no endpoint is discovered, the endpoint
  attribute will be None.

  Raises: :class:`ValueError` on bad URL, :class:`requests.HTTPError` on failure
  """
  resp = util.requests_get(url, **requests_kwargs)
  resp.raise_for_status()

  # look in headers
  # TODO: it looks like requests doesn't handle multiple headers with the
  # same name, e.g. 'Link'. from skimming the code, it looks like the last
  # one wins. ugh. :/
  for link in resp.headers.get('Link', '').split(','):
    match = LINK_HEADER_RE.search(link)
    if match:
      endpoint = urljoin(url, match.group(1))
      logging.debug(f'Discovered webmention endpoint for {url} in Link header: {endpoint}')
      return Endpoint(endpoint, resp)

  # if no header, require HTML content
  content_type = resp.headers.get('content-type')
  if content_type and not content_type.split(';')[0] =='text/html':
    logging.debug(f'No webmention endpoint for {url} in headers and content type {content_type} is not HTML')
    return Endpoint(None, resp)

  # look in the content
  soup = util.parse_html(resp.text)
  for tag in soup.find_all(
      ('link', 'a'), attrs={'rel': ('webmention', 'http://webmention.org/')}):
    if tag and tag.get('href'):
      endpoint = urljoin(url, tag['href'])
      logging.debug(f'Discovered webmention endpoint for {url} in tag: {endpoint}')
      return Endpoint(endpoint, resp)

  logging.debug(f'No webmention endpoint found for {url} in headers or HTML')
  return Endpoint(None, resp)


def send(endpoint, source, target, **requests_kwargs):
  """Sends a webmention

  Args:
    endpoint: str, webmention endpoint URL
    source: str, source URL
    target: str, target URL
    requests_kwargs: passed to :meth:`requests.post`

  Returns: :class:`requests.Response` on success.

  Raises: :class:`ValueError` on bad URL, :class:`requests.HTTPError` on failure
  """
  requests_kwargs.setdefault('headers', {})['Accept'] = '*/*'
  # following 3xx redirects translates POST to GET, which we don't want,
  # so disable that. we may support 307/308 later.
  # https://github.com/snarfed/bridgy/issues/753
  resp = util.requests_post(endpoint, data={'source': source, 'target': target},
                            allow_redirects=False, **requests_kwargs)
  resp.raise_for_status()
  return resp
