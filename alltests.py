#!/usr/bin/python
"""Runs all unit tests in *_test.py files in the current directory.
"""

__author__ = ['Ryan Barrett <webutil@ryanb.org>']

import glob
import imp
import logging
import os
import sys
import unittest

for app_engine_path in (os.getenv('GAE_SDK_ROOT', ''),
                        '/usr/local/google_appengine',
                        os.path.expanduser('~/google_appengine')):
  if os.path.exists(app_engine_path):
    break
else:
  print >> sys.stderr, """\
Couldn't find the Google App Engine SDK. Please set the GAE_SDK_ROOT environment
variable or install it in ~/google_appengine or /usr/local/google_appengine."""
  sys.exit(1)

# Monkey patch to fix template loader issue:
#
# File "/usr/local/google_appengine/lib/django-1.4/django/template/loader.py", line 101, in find_template_loader:
# ImproperlyConfigured: Error importing template source loader django.template.loaders.filesystem.load_template_source: "'module' object has no attribute 'load_template_source'"
sys.path.append(os.path.join(app_engine_path, 'lib', 'django-1.3'))
from django.template.loaders import filesystem
filesystem.load_template_source = filesystem._loader.load_template_source

# add working directory since this is often symlinked in a different dir by
# clients, in which case we want it to load and run test in that dir.
sys.path = ([os.getcwd(), app_engine_path] +
            [os.path.join(app_engine_path, 'lib', lib) for lib in
             'mox', 'webob-1.2.3', 'yaml-3.10', 'django-1.4',
             # webapp2 2.5.2 has a change that breaks get_response(). it
             # starts returning None for the response. not sure why. changes:
             # http://code.google.com/p/webapp-improved/source/list
             'webapp2-2.5.1'] +
            sys.path)


def main():
  if '--debug' in sys.argv:
    sys.argv.remove('--debug')
    logging.getLogger().setLevel(logging.DEBUG)
  else:
    logging.disable(logging.CRITICAL + 1)

  for filename in glob.glob('*_test.py'):
    name = os.path.splitext(filename)[0]
    if name in sys.modules:
      # this is important. imp.load_module() twice is effectively a reload,
      # which duplicates test case base classes (e.g. TestbedTest) and makes
      # super() think an instance of one isn't an instance of another.
      module = sys.modules[name]
    else:
      module = imp.load_module(name, *imp.find_module(name))

    # ugh. this is the simplest way to make all of the test classes defined in
    # the modules visible to unittest.main(), but it's really ugly.
    globals().update(vars(module))

  unittest.main()


if __name__ == '__main__':
  main()
