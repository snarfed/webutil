import logging, os, sys

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

# Suppress warnings. (Not currently working.)
# ../local3/lib/python3.6/site-packages/mox3/mox.py:909: DeprecationWarning: inspect.getargspec() is deprecated, use inspect.signature() or inspect.getfullargspec()
import warnings
warnings.filterwarnings('ignore', message=r'inspect.getargspec() is deprecated')
