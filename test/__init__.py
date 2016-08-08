import logging, os, sys

try:
  # Add the App Engine SDK's bundled libraries (django, webob, yaml, etc.) to
  # sys.path so we can use them instead of adding them all to tests_require in
  # setup.py.
  # https://cloud.google.com/appengine/docs/python/tools/localunittesting#Python_Setting_up_a_testing_framework
  import dev_appserver
  dev_appserver.fix_sys_path()

  # Put them at the end of sys.path so that we prefer versions in our
  # virtualenv. Necessary for e.g. google-api-python-client and oauth2client,
  # which we want newer versions of.
  sys.path.sort(key=lambda path: 1 if path.startswith(dev_appserver._DIR_PATH) else 0)

  # Also use the App Engine SDK's mox because it has bug fixes that aren't in pypi
  # 0.5.3. (Annoyingly, they both say they're version 0.5.3.)
  sys.path.append(os.path.join(dev_appserver._DIR_PATH, 'lib', 'mox'))

except ImportError:
  logging.warning("Couldn't load App Engine SDK!")

# Piggyback on unittest's -v and -q flags to show/hide logging.
if 'discover' in sys.argv or '-q' in sys.argv or '--quiet' in sys.argv:
  logging.disable(logging.CRITICAL + 1)
elif '-v' in sys.argv:
  logging.getLogger().setLevel(logging.DEBUG)

# dumb hack to add the webutil dir to sys.path so the tests can be run from
# oauth-dropins even though they import webutil modules as top level
# (ie not from oauth_dropins.webutil import ...)
pkg = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
if pkg not in sys.path:
  sys.path.append(pkg)
