"""App Engine config. dev_appserver vs prod, logging, Google API clients, etc."""
import os

from .appengine_info import DEBUG

# Use lxml for BeautifulSoup explicitly.
from . import util
util.beautifulsoup_parser = 'lxml'

# # Suppress warnings
# import warnings
# warnings.filterwarnings('ignore', module='bs4',
#                         message='No parser was explicitly specified')
# if DEBUG:
#   warnings.filterwarnings('ignore', module='google.auth',
#     message='Your application has authenticated using end user credentials')

# make oauthlib let us use non-SSL http://localhost in dev_appserver etc
# https://oauthlib.readthedocs.io/en/latest/oauth2/security.html#envvar-OAUTHLIB_INSECURE_TRANSPORT
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = 'true'

#
# Google API clients
#
if DEBUG:
  os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(
    os.path.dirname(__file__), 'fake_user_account.json')
  os.environ.setdefault('CLOUDSDK_CORE_PROJECT', 'app')
  os.environ.setdefault('DATASTORE_DATASET', 'app')
  os.environ.setdefault('GOOGLE_CLOUD_PROJECT', 'app')


# NDB (Cloud Datastore)
try:
  # TODO: make thread local?
  # https://googleapis.dev/python/python-ndb/latest/migrating.html#setting-up-a-connection
  from google.cloud import ndb
  ndb_client = ndb.Client()
  if DEBUG:
    # work around that these APIs don't natively support dev_appserver.py
    # https://github.com/googleapis/python-ndb/issues/238
    ndb_client.host = 'localhost:8089'
    ndb_client.secure = False
except ImportError:
  pass

# Google Cloud Tasks
try:
  from google.cloud import tasks_v2
  tasks_client = tasks_v2.CloudTasksClient()
  if DEBUG:
    tasks_client.host = 'localhost:9999'
    tasks_client.secure = False
except ImportError:
  pass

# Stackdriver Error Reporting
try:
  from google.cloud import error_reporting
  error_reporting_client = error_reporting.Client()
  if DEBUG:
    error_reporting_client.host = 'localhost:9999'
    error_reporting_client.secure = False
except ImportError:
  pass

# Stackdriver Logging
import logging
# needed for visible logging in dev_appserver
logging.getLogger().setLevel(logging.DEBUG)

try:
  import google.cloud.logging
  logging_client = google.cloud.logging.Client()
  if not DEBUG:
    # https://stackoverflow.com/a/58296028/186123
    # https://googleapis.dev/python/logging/latest/usage.html#cloud-logging-handler
    from google.cloud.logging.handlers import AppEngineHandler, setup_logging
    setup_logging(AppEngineHandler(logging_client, name='stdout'),
                  log_level=logging.DEBUG)
    # this currently occasionally hits the 256KB stackdriver logging limit and
    # crashes in the background service. i've tried batch_size=1 and
    # SyncTransport, but no luck, same thing.
    # https://stackoverflow.com/questions/59398479
except ImportError:
  pass

for logger in ('google.cloud', 'oauthlib', 'requests', 'requests_oauthlib',
               'urllib3'):
  logging.getLogger(logger).setLevel(logging.INFO)
