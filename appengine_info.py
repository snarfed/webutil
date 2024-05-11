"""HTTP request and server information derived from the environment.

App Engine:
* https://cloud.google.com/appengine/docs/standard/python3/runtime#environment_variables
* https://cloud.google.com/appengine/docs/flexible/python/runtime#environment_variables

WSGI: https://www.python.org/dev/peps/pep-3333/

To run against the prod datastore, make a service account, download its JSON
credentials file, then run eg:

env GOOGLE_APPLICATION_CREDENTIALS=service_account_creds.json FLASK_ENV=development flask run -p 8080
"""
import os, sys

PROJECT = os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('GAE_APPLICATION') or ''
APP_ID = PROJECT.split('~')[-1]

creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
gae_env = os.environ.get('GAE_ENV')  # App Engine Standard
gae_instance = 'GAE_INSTANCE' in os.environ  # App Engine Flex
if creds and not creds.endswith('fake_user_account.json'):
  DEBUG = False
  LOCAL_SERVER = True
else:
  DEBUG = gae_env in (None, 'localdev') and not gae_instance
  LOCAL_SERVER = (gae_env != 'standard' and not gae_instance
                  and 'unittest' not in ' '.join(sys.argv))
