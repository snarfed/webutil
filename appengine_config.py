"""App Engine settings.
"""

import os

HTTP_TIMEOUT = 15  # seconds

SCHEME = 'https' if (os.getenv('HTTPS') == 'on') else 'http'

try:
  from google.appengine.api import app_identity
  APP_ID = app_identity.get_application_id()
  HOST = app_identity.get_default_version_hostname()
except (ImportError, AttributeError):
  # this is probably a unit test
  APP_ID = None
  HOST = os.getenv('HTTP_HOST', 'localhost')

HOST_URL = '%s://%s' % (SCHEME, HOST)

DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Development')
