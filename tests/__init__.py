import logging, sys

logging.getLogger('chardet').setLevel(logging.INFO)
logging.getLogger('google.cloud').setLevel(logging.INFO)
logging.getLogger('urllib3').setLevel(logging.INFO)

# Piggyback on unittest's -v and -q flags to show/hide logging.
if 'discover' in sys.argv or '-q' in sys.argv or '--quiet' in sys.argv:
  logging.disable(logging.CRITICAL + 1)
elif '-v' in sys.argv:
  logging.getLogger().setLevel(logging.DEBUG)
