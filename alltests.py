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

APP_ENGINE_SDK_PATH = os.path.expanduser('/usr/local/google_appengine')
sys.path += [os.path.join(APP_ENGINE_SDK_PATH, 'lib', lib)
             for lib in ('django-1.3', 'mox', 'yaml/lib')]


def main():
  if '--debug' in sys.argv:
    sys.argv.remove('--debug')
    logging.getLogger().setLevel(logging.DEBUG)
  else:
    logging.disable(logging.CRITICAL + 1)

  # add working directory since this is often symlinked in a different dir by
  # clients, in which case we want it to load and run test in that dir.
  sys.path = ([os.getcwd(), APP_ENGINE_SDK_PATH] +
              [os.path.join(APP_ENGINE_SDK_PATH, 'lib', lib) for lib in
               'mox', 'webapp2-2.5.2', 'webob-1.2.3', 'yaml-3.10', 'django-1.4'] +
              sys.path)

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
