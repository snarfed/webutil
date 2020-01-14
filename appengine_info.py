"""HTTP request and server information derived from the environment.

App Engine: https://cloud.google.com/appengine/docs/standard/python3/runtime#environment_variables
WSGI: https://www.python.org/dev/peps/pep-3333/
"""
import os

APP_ID = os.getenv('GAE_APPLICATION', '').split('~')[-1]
DEBUG = os.environ.get('GAE_ENV') in (None, 'localdev')  # 'standard' in production
LOCAL = os.environ.get('GAE_ENV') == 'localdev'
