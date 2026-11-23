"""Run the real bridge loop + DirectSink against SQLite with a fake transport (no ZeroMQ/MQTT needed)."""
import os
import tempfile
import threading
import unittest
from unittest import mock

from iotpipe import bridge
from iotpipe.config import load
from iotpipe.db import connect
from iotpipe.simulator import generate


class BridgeRunTests(unittest.TestCase):
    def test_run_writes_raw_and_dead_letter(self):
        msgs = generate(seed=11)
        stop = threading.Event()

        def fake_messages(_s, _stop):
            for dev, payload, _ in msgs:
                yield (f"sensors/{dev}/reading", payload)
            yield None
            stop.set()

        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=True):
            s = load(profile="test", db_url=f"sqlite:///{d}/t.db")
            with mock.patch.object(bridge.transport, "messages", fake_messages):
                bridge.run(s, stop)
            db = connect(s.db_url)
            raw = db.query("SELECT COUNT(*) n FROM raw_readings")[0]["n"]
            dl = db.query("SELECT COUNT(*) n FROM dead_letter")[0]["n"]
            self.assertGreater(raw, 400)
            self.assertEqual(dl, sum(1 for *_, lab in msgs if lab in ("missing_field", "garbage")))
            db.close()
