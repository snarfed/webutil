"""App Engine settings.
"""
import os

HTTP_TIMEOUT = 15  # seconds
SCHEME = 'https' if (os.getenv('HTTPS') == 'on') else 'http'
# https://cloud.google.com/appengine/docs/standard/python3/runtime#environment_variables
APP_ID = os.getenv('GAE_APPLICATION', '').split('~')[-1]
HOST = os.getenv('HTTP_HOST', 'localhost')
HOST_URL = '%s://%s' % (SCHEME, HOST)
DEBUG = os.environ.get('GAE_ENV') in (None, 'localdev')  # 'standard' in production
LOCAL = os.environ.get('GAE_ENV') == 'localdev'
