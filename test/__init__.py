# dumb hack to add the webutil dir to sys.path so the tests can be run from
# oauth-dropins even though they import webutil modules as top level
# (ie not from oauth_dropins.webutil import ...)
import os, sys
pkg = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
if pkg not in sys.path:
  sys.path.append(pkg)
