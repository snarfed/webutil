"""App Engine config. local vs prod, logging, Google API clients, etc."""
import logging
import os

from .appengine_info import DEBUG

# Use lxml for BeautifulSoup explicitly.
from . import util
util.beautifulsoup_parser = 'lxml'

# make oauthlib let us use non-SSL http://localhost when running locally
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
  os.environ.setdefault('DATASTORE_EMULATOR_HOST', 'localhost:8089')

# NDB (Cloud Datastore)
try:
  # TODO: make thread local?
  # https://googleapis.dev/python/python-ndb/latest/migrating.html#setting-up-a-connection
  from google.cloud import ndb
  ndb_client = ndb.Client()
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

# needed to make logging visible locally under flask run, etc
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)

# Stackdriver Logging
try:
  import google.cloud.logging
  logging_client = google.cloud.logging.Client()

  if not DEBUG:
    logging_client.setup_logging(log_level=logging.DEBUG)
    # this currently occasionally hits the 256KB stackdriver logging limit and
    # crashes in the background service. i've tried batch_size=1 and
    # SyncTransport, but no luck, same thing.
    # https://stackoverflow.com/questions/59398479
except ImportError:
  pass

for logger in ('google.cloud', 'oauthlib', 'requests', 'requests_oauthlib',
               'urllib3'):
  logging.getLogger(logger).setLevel(logging.INFO)
