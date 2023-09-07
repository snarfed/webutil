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

project = os.getenv('GOOGLE_CLOUD_PROJECT') or os.getenv('GAE_APPLICATION') or ''
APP_ID = project.split('~')[-1]

creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
if creds and not creds.endswith('fake_user_account.json'):
  DEBUG = False
  LOCAL_SERVER = True
else:
  DEBUG = os.environ.get('GAE_ENV') in (None, 'localdev')  # 'standard' in production
  LOCAL_SERVER = (os.environ.get('GAE_ENV') != 'standard'  # App Engine Standard
                  and not os.environ.get('GAE_INSTANCE'))  # App Engine Flex
