import logging, os, sys

from ..appengine_info import DEBUG

assert DEBUG
creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
assert not creds or creds.endswith('fake_user_account.json')

logging.getLogger('chardet').setLevel(logging.INFO)
logging.getLogger('google.cloud').setLevel(logging.INFO)
logging.getLogger('lexrpc').setLevel(logging.INFO)
logging.getLogger('negotiator').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.INFO)

# Piggyback on unittest's -v and -q flags to show/hide logging.
logging.basicConfig()
if '-v' in sys.argv:
  logging.getLogger().setLevel(logging.DEBUG)
else:
  # used to be: elif 'discover' in sys.argv or '-q' in sys.argv or '--quiet' in sys.argv:
  # dropped that to suppress logging when running full single test files
  logging.disable(logging.CRITICAL + 1)
