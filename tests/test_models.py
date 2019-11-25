"""Unit tests for models.py.
"""
from __future__ import unicode_literals

from google.cloud import ndb

from ..models import StringIdModel
from .. import testutil


class StringIdModelTest(testutil.TestCase):

  def test_put(self):
    with ndb.Client().context():
      self.assertEqual(ndb.Key(StringIdModel, 'x'),
                       StringIdModel(id='x').put())
      self.assertRaises(AssertionError, StringIdModel().put)
      self.assertRaises(AssertionError, StringIdModel(id=1).put)
