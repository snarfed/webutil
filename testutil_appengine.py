"""Unit test utilities that depend on the App Engine SDK."""
import os

from google.appengine.datastore import datastore_stub_util
from google.appengine.ext import testbed
import webapp2

import testutil


class HandlerTest(testutil.TestCase):
  """Base test class for webapp2 request handlers.

  Uses App Engine's testbed to set up API stubs:
  http://code.google.com/appengine/docs/python/tools/localunittesting.html

  Attributes:
    application: :class:`webapp2.WSGIApplication`
    handler: :class:`webapp2.RequestHandler`
  """
  def setUp(self):
    super(HandlerTest, self).setUp()

    os.environ['APPLICATION_ID'] = 'app_id'
    self.current_user_id = '123'
    self.current_user_email = 'foo@bar.com'

    self.testbed = testbed.Testbed()
    self.testbed.setup_env(user_id=self.current_user_id,
                           user_email=self.current_user_email)
    self.testbed.activate()

    hrd_policy = datastore_stub_util.PseudoRandomHRConsistencyPolicy(probability=.5)
    self.testbed.init_datastore_v3_stub(consistency_policy=hrd_policy)
    self.testbed.init_taskqueue_stub(root_path='.')
    self.testbed.init_user_stub()
    self.testbed.init_mail_stub()
    self.testbed.init_memcache_stub()
    self.testbed.init_logservice_stub()

    # unofficial API, whee! this is so we can call
    # TaskQueueServiceStub.GetTasks() in tests. see
    # google/appengine/api/taskqueue/taskqueue_stub.py
    self.taskqueue_stub = self.testbed.get_stub('taskqueue')

    self.request = webapp2.Request.blank('/')
    self.response = webapp2.Response()
    self.handler = webapp2.RequestHandler(self.request, self.response)

  def tearDown(self):
    self.testbed.deactivate()
    super(HandlerTest, self).tearDown()
