"""HTTP request and server information derived from the environment.

App Engine: https://cloud.google.com/appengine/docs/standard/python3/runtime#environment_variables
WSGI: https://www.python.org/dev/peps/pep-0333/
"""
import os

APP_ID = os.getenv('GAE_APPLICATION', '').split('~')[-1]
SCHEME = 'https' if (os.getenv('HTTPS') == 'on') else 'http'
HOST = os.getenv('HTTP_HOST', 'localhost')
HOST_URL = '%s://%s' % (SCHEME, HOST)
DEBUG = os.environ.get('GAE_ENV') in (None, 'localdev')  # 'standard' in production
LOCAL = os.environ.get('GAE_ENV') == 'localdev'
