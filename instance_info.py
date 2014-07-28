"""Renders vital stats about a single App Engine instance.

Intended for developers, not users. Uses the Runtime API:
https://developers.google.com/appengine/docs/python/backends/runtimeapi

Note that the Runtime API isn't implemented in dev_appserver, so all stats will
be reported as 0.

(The docs say it's deprecated because it's part of Backends, which is replaced
by Modules, but I haven't found a corresponding part of the Modules API.)

To turn on concurrent request recording, add this to your appengine_config.py:

def webapp_add_wsgi_middleware(app):
  from webutil import instance_info
  app = instance_info.concurrent_requests_wsgi_middleware(app)
"""

import datetime
import os

import appengine_config
import collections
from google.appengine.api import runtime
import handlers
import threading
import webapp2

Concurrent = collections.namedtuple('Concurrent', ('when', 'count'))

# globals
current_requests = set()  # stores string request IDs
current_requests_lock = threading.Lock()
concurrents = collections.deque(maxlen=20)  # stores Concurrents; thread safe


class InfoHandler(handlers.TemplateHandler):
  def template_file(self):
    return os.path.join(os.path.dirname(__file__),
                        'templates/instance_info.html')

  def template_vars(self):
    return {'concurrents': concurrents,
            'current_requests': current_requests,
            'os': os,
            'runtime': runtime,
            }


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
        concurrents.append(Concurrent(when=datetime.datetime.now(),
                                      count=len(current_requests)))

    ret = app(environ, start_response)

    with current_requests_lock:
      current_requests.remove(req_id)
    return ret

  return wrapper


application = webapp2.WSGIApplication([
    ('/_info', InfoHandler),
    ], debug=appengine_config.DEBUG)


if __name__ == '__main__':
  main()
