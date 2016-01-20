"""App Engine settings.
"""

import os

HTTP_TIMEOUT = 15  # seconds

try:
  from google.appengine.api import app_identity
  APP_ID = app_identity.get_application_id()
except (ImportError, AttributeError):
  # this is probably a unit test
  APP_ID = None

# app_identity.get_default_version_hostname() would be better here, but
# it doesn't work in dev_appserver since that doesn't set
# os.environ['DEFAULT_VERSION_HOSTNAME'].
HOST = os.getenv('HTTP_HOST', 'localhost')
SCHEME = 'https' if (os.getenv('HTTPS') == 'on') else 'http'
DEBUG = os.environ.get('SERVER_SOFTWARE', '').startswith('Development')

# ereporter records exceptions and emails them to me.
# https://developers.google.com/appengine/articles/python/recording_exceptions_with_ereporter
# to test, open this path:
# http://localhost:8080/_ereporter?sender=ryan@brid.gy&to=ryan@brid.gy&debug=true&delete=false&date=2014-07-09
# where the date is today or tomorrow (because of UTC)
import logging
import traceback
from google.appengine.ext import ereporter

# monkey patch ereporter to combine exceptions from different versions and dates
ereporter.ExceptionRecord.get_key_name = \
    classmethod(lambda cls, signature, version, date=None: signature)

# monkey patch ereporter to blacklist some exceptions
class BlacklistingHandler(ereporter.ExceptionRecordingHandler):
  """An ereporter handler that ignores exceptions in a blacklist."""
  # Exception message prefixes to ignore
  BLACKLIST = (
    'AccessTokenRefreshError: internal_failure',
    'AccessTokenRefreshError: Invalid response 502.',
    'BadRequestError: The referenced transaction has expired',
    'ConnectionError: HTTPConnectionPool',
    'ConnectionError: HTTPSConnectionPool',
    'DeadlineExceededError',
    'error: An error occured while connecting to the server:',
    'Error: Logs data is not available.',
    'HTTPClientError: ',
    'HTTPError: HTTP Error 400: Bad Request',
    'HTTPError: HTTP Error 400: message=Sorry, the Flickr API service is not currently available',
    'HTTPError: HTTP Error 404: Not Found',
    'HTTPError: HTTP Error 500: Internal Server Error',
    'HTTPError: HTTP Error 502: Bad Gateway',
    'HTTPError: HTTP Error 503: Service Unavailable',
    'HTTPError: 400 Client Error: Bad Request',
    'HTTPError: 404 Client Error: Not Found',
    'HTTPError: 500 Server Error: Internal Server Error',
    'HTTPError: 502 Server Error: Bad Gateway',
    'HTTPError: 503 Server Error: Service Unavailable',
    'HttpError: <HttpError 400 when requesting',
    'HttpError: <HttpError 404 when requesting',
    'HttpError: <HttpError 500 when requesting',
    'HttpError: <HttpError 502 when requesting',
    'HttpError: <HttpError 503 when requesting',
    'HTTPException: Deadline exceeded while waiting for HTTP response from URL:',
    'HTTPNotFound: ',
    'InstagramClientError: Unable to parse response, not valid JSON:',
    'InternalError: server is not responding',  # usually datastore
    'InternalError: Server is not responding',
    'InternalTransientError',
    'JointException: taskqueue.DatastoreError',
    'RequestError: Server responded with: 503',  # gdata.client.RequestError
    'Timeout',
    'TransactionFailedError',
    'TransientError',
    'TweepError: HTTPSConnectionPool',
    "TweepError: Token request failed with code 401, response was 'This feature is temporarily unavailable'.",
    'TweepError: Token request failed with code 5',
    )

  def emit(self, record):
    # don't report warning or lower levels
    if record and record.exc_info and record.levelno >= logging.ERROR:
      type_and_msg = traceback.format_exception_only(*record.exc_info[:2])[-1]
      for prefix in self.BLACKLIST:
        if type_and_msg.startswith(prefix):
          return
      return super(BlacklistingHandler, self).emit(record)


ereporter_logging_handler = BlacklistingHandler()
logging.getLogger().addHandler(ereporter_logging_handler)
