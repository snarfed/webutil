"""App Engine settings.

Reads Facebook and Twitter app keys and secrets into constants from these files:

facebook_app_id
facebook_app_secret
facebook_app_id_local
facebook_app_secret_local
twitter_app_key
twitter_app_secret
"""

from __future__ import with_statement
import logging
import os

from google.appengine.api import app_identity

try:
  APP_ID = app_identity.get_application_id()
except AttributeError:
  # this is probably a unit test
  APP_ID = None

# app_identity.get_default_version_hostname() would be better here, but
# it doesn't work in dev_appserver since that doesn't set
# os.environ['DEFAULT_VERSION_HOSTNAME'].
HOST = os.getenv('HTTP_HOST')
SCHEME = 'https' if (os.getenv('HTTPS') == 'on') else 'http'


def read(filename):
  """Returns the contents of filename, or None if it doesn't exist."""
  if os.path.exists(filename):
    with open(filename) as f:
      return f.read().strip()
  else:
    logging.warning('%s file not found, cannot authenticate!', filename)

MOCKFACEBOOK = False
DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Development')

if DEBUG:
  FACEBOOK_APP_ID = read('facebook_app_id_local')
  FACEBOOK_APP_SECRET = read('facebook_app_secret_local')
else:
  FACEBOOK_APP_ID = read('facebook_app_id')
  FACEBOOK_APP_SECRET = read('facebook_app_secret')

GOOGLEPLUS_CLIENT_ID = read('googleplus_client_id')
GOOGLEPLUS_CLIENT_SECRET = read('googleplus_client_secret')
TWITTER_APP_KEY = read('twitter_app_key')
TWITTER_APP_SECRET = read('twitter_app_secret')
