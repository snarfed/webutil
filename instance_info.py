"""Renders vital stats about a single App Engine instance.

Intended for developers, not users. To turn on concurrent request recording, add the middleware and InfoHandler to your WSGI application, eg:

  from oauth_dropins.webutil.instance_info import concurrent_requests_wsgi_middleware, info

  application = concurrent_requests_wsgi_middleware(WSGIApplication([
      ...
      ('/_info', info),
  ])
"""
import collections
import heapq
import os
import threading

from flask import render_template

from . import util

CONCURRENTS_SIZE = 20

# A time when there was more than one request running at once. count is the
# first field so that instances compare by count, since they're stored in a
# heap, so that we keep the highest count instances.
Concurrent = collections.namedtuple('Concurrent', ('count', 'when'))

# globals
current_requests = set()  # stores string request IDs
current_requests_lock = threading.Lock()
concurrents = []  # a heapq. stores Concurrents


def info():
  """Flask handler that renders current instance info."""
  return render_template(
    os.path.join(os.path.dirname(__file__), 'templates/instance_info.html'),
    concurrents=concurrents,
    current_requests=current_requests,
    os=os,
    runtime=os.getenv('GAE_RUNTIME'),
  )


def concurrent_requests_wsgi_middleware(app):
  """WSGI middleware for per request instance info instrumentation.

  Follows the WSGI standard. Details: http://www.python.org/dev/peps/pep-0333/
  """
  def wrapper(environ, start_response):
    req_id = os.environ['REQUEST_LOG_ID']

    global current_requests, current_requests_lock, concurrents
    with current_requests_lock:
      current_requests.add(req_id)
      if len(current_requests) > 1:
        heapq.heappush(concurrents, Concurrent(count=len(current_requests),
                                               when=util.now()))
        if len(concurrents) > CONCURRENTS_SIZE:
          heapq.heappop(concurrents)

    ret = app(environ, start_response)

    with current_requests_lock:
      current_requests.remove(req_id)
    return ret

  return wrapper
