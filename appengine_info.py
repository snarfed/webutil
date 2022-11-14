"""HTTP request and server information derived from the environment.

App Engine: https://cloud.google.com/appengine/docs/standard/python3/runtime#environment_variables
WSGI: https://www.python.org/dev/peps/pep-3333/

To run against the prod datastore, make a service account, download its JSON
credentials file, then run eg:

env GOOGLE_APPLICATION_CREDENTIALS=service_account_creds.json FLASK_ENV=development flask run -p 8080
"""
import os, sys

creds = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
if creds and not creds.endswith('fake_user_account.json'):
  APP_ID = 'bridgy-federated'
  DEBUG = False
  LOCAL = True
else:
  APP_ID = os.getenv('GAE_APPLICATION', '').split('~')[-1]
  DEBUG = os.environ.get('GAE_ENV') in (None, 'localdev')  # 'standard' in production
  LOCAL = os.environ.get('GAE_ENV') == 'localdev'
