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
  # this is a unit test or the Python 3 runtime
  # https://cloud.google.com/appengine/docs/standard/python3/runtime#environment_variables
  APP_ID = os.getenv('GAE_APPLICATION', '').split('~')[-1]
  HOST = os.getenv('HTTP_HOST', 'localhost')

HOST_URL = '%s://%s' % (SCHEME, HOST)

DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Development')
