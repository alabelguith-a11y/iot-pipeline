import os
import unittest
from unittest import mock

from iotpipe.config import load


class ConfigTests(unittest.TestCase):
    def test_test_profile_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            s = load(profile="test")
        self.assertEqual((s.transport, s.queue), ("zmq", "direct"))
        self.assertTrue(s.db_url.startswith("sqlite"))

    def test_dev_profile_and_env_override(self):
        with mock.patch.dict(os.environ, {"TRANSPORT": "zmq"}, clear=True):
            s = load(profile="dev")
        self.assertEqual((s.transport, s.queue), ("zmq", "kafka"))  # env wins over profile
        self.assertTrue(s.db_url.startswith("postgresql"))

    def test_unknown_profile(self):
        with self.assertRaises(ValueError):
            load(profile="nope")
