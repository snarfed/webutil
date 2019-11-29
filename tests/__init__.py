import logging, sys

# Piggyback on unittest's -v and -q flags to show/hide logging.
if 'discover' in sys.argv or '-q' in sys.argv or '--quiet' in sys.argv:
  logging.disable(logging.CRITICAL + 1)
elif '-v' in sys.argv:
  logging.getLogger().setLevel(logging.DEBUG)

# Suppress warnings. (Not currently working.)
# ../local3/lib/python3.6/site-packages/mox3/mox.py:909: DeprecationWarning: inspect.getargspec() is deprecated, use inspect.signature() or inspect.getfullargspec()
import warnings
warnings.filterwarnings('ignore', message=r'inspect.getargspec() is deprecated')
