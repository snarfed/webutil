"""App Engine settings.
"""

import os

HTTP_TIMEOUT = 15  # seconds

try:
  from google.appengine.api import app_identity
  APP_ID = app_identity.get_application_id()
except (ImportError, AttributeError):
  # this is probably a unit test
  APP_ID = None

# app_identity.get_default_version_hostname() would be better here, but
# it doesn't work in dev_appserver since that doesn't set
# os.environ['DEFAULT_VERSION_HOSTNAME'].
HOST = os.getenv('HTTP_HOST', 'localhost')
SCHEME = 'https' if (os.getenv('HTTPS') == 'on') else 'http'
DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Development')
