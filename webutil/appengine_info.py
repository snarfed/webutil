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

PROJECT = (os.getenv('GOOGLE_CLOUD_PROJECT')
           or os.getenv('GAE_APPLICATION')
           or os.getenv('K_SERVICE')
           or '')
APP_ID = PROJECT.split('~')[-1]

creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
gae_env = os.environ.get('GAE_ENV')          # App Engine Standard
gae_instance = 'GAE_INSTANCE' in os.environ  # App Engine Flex
cloud_run_service = os.getenv('K_SERVICE')   # Cloud Run

GAE = bool(gae_env == 'standard' or gae_instance)
CLOUD_RUN = bool(cloud_run_service)
PROD = GAE or CLOUD_RUN

READ_ONLY = bool(os.environ.get('READ_ONLY'))

args = ' '.join(sys.argv)
TESTING = 'unittest' in args or 'pytest' in args

LOCAL_SERVER = not PROD and not TESTING

if creds and not creds.endswith('fake_user_account.json'):
  DEBUG = False
else:
  DEBUG = gae_env in (None, 'localdev') and not PROD
