import unittest
from collections import Counter

from iotpipe.bridge import process
from iotpipe.simulator import generate


class FakeSink:
    def __init__(self):
        self.accepted, self.rejected = [], []

    def accept(self, r):
        self.accepted.append(r)

    def reject(self, reason, raw):
        self.rejected.append(reason)


class SimulatorBridgeTests(unittest.TestCase):
    def test_deterministic(self):
        from datetime import datetime, timezone
        end = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.assertEqual(generate(seed=1, end=end), generate(seed=1, end=end))

    def test_clean_run_has_no_rejects(self):
        sink = FakeSink()
        for dev, payload, label in generate(defects={}):
            process(f"sensors/{dev}/reading", payload, sink)
        self.assertEqual(sink.rejected, [])
        self.assertEqual(len(sink.accepted), 4 * 120)

    def test_defects_are_rejected_with_reason(self):
        sink = FakeSink()
        msgs = generate(seed=3)
        for dev, payload, _ in msgs:
            process(f"sensors/{dev}/reading", payload, sink)
        expected = sum(1 for *_, label in msgs if label in ("missing_field", "garbage"))
        self.assertEqual(len(sink.rejected), expected)
        self.assertIn("invalid_json", Counter(sink.rejected))

    def test_topic_device_mismatch(self):
        sink = FakeSink()
        dev, payload, _ = generate(defects={})[0]
        self.assertFalse(process("sensors/someone-else/reading", payload, sink))
        self.assertEqual(sink.rejected, ["topic/device_id mismatch"])
