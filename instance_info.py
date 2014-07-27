"""Renders vital stats about a single App Engine instance.

Intended for developers, not users. Uses the Runtime API:
https://developers.google.com/appengine/docs/python/backends/runtimeapi

Note that the Runtime API isn't implemented in dev_appserver, so all stats will
be reported as 0.

(The docs say it's deprecated because it's part of Backends, which is replaced
by Modules, but I haven't found a corresponding part of the Modules API.)
"""

import os

import appengine_config
from google.appengine.api import runtime
import handlers
import webapp2

class InfoHandler(handlers.TemplateHandler):
  def template_file(self):
    return os.path.join(os.path.dirname(__file__),
                        'templates/instance_info.html')

  def template_vars(self):
    return {'os': os, 'runtime': runtime}


application = webapp2.WSGIApplication([
    ('/_info', InfoHandler),
    ], debug=appengine_config.DEBUG)


if __name__ == '__main__':
  main()
