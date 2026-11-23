"""End-to-end ELT on in-memory SQLite: simulator -> bridge validation -> raw -> staging -> analytics."""
import unittest
from collections import Counter
from datetime import datetime, timezone

from iotpipe import loader
from iotpipe.bridge import process
from iotpipe.db import connect
from iotpipe.etl import runner
from iotpipe.simulator import generate


class Sink:
    def __init__(self, db):
        self.db, self.ok = db, []

    def accept(self, r):
        self.ok.append(r)

    def reject(self, reason, raw):
        loader.insert_dead_letter(self.db, reason, raw)


def load_messages(db, msgs):
    sink = Sink(db)
    for dev, payload, _ in msgs:
        process(f"sensors/{dev}/reading", payload, sink)
    loader.insert_raw(db, sink.ok)
    return sink


class EtlTests(unittest.TestCase):
    def setUp(self):
        self.db = connect("sqlite:///:memory:")
        loader.ensure_raw_tables(self.db)
        self.end = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    def test_clean_data_passes_everything(self):
        load_messages(self.db, generate(defects={}, end=self.end))
        result = runner.run(self.db)
        self.assertTrue(result["ok"], result["checks"])
        q = self.db.query("SELECT * FROM fct_ingestion_quality")[0]
        self.assertEqual((q["raw_rows"], q["staged_rows"], q["rejected_rows"]), (480, 480, 0))

    def test_dirty_data_is_cleaned(self):
        msgs = generate(seed=7, end=self.end)
        load_messages(self.db, msgs)
        result = runner.run(self.db)
        self.assertTrue(result["ok"], [c for c in result["checks"] if c["status"] != "pass"])
        q = self.db.query("SELECT * FROM fct_ingestion_quality")[0]
        labels = Counter(label for *_, label in msgs)
        self.assertEqual(q["rejected_rows"], labels["missing_field"] + labels["garbage"])
        self.assertGreater(q["duplicates_removed"], 0)
        self.assertEqual(q["implausible_rows"], labels["spike"])

    def test_redelivery_is_idempotent(self):
        msgs = generate(defects={}, end=self.end)
        load_messages(self.db, msgs)
        before = self.db.query("SELECT COUNT(*) n FROM raw_readings")[0]["n"]
        load_messages(self.db, msgs)  # at-least-once: everything delivered twice
        self.assertEqual(self.db.query("SELECT COUNT(*) n FROM raw_readings")[0]["n"], before)

    def test_etl_rerun_is_deterministic(self):
        load_messages(self.db, generate(seed=5, end=self.end))
        runner.run(self.db)
        a = self.db.query("SELECT * FROM fct_hourly_metrics ORDER BY device_id, event_hour")
        runner.run(self.db)
        self.assertEqual(a, self.db.query("SELECT * FROM fct_hourly_metrics ORDER BY device_id, event_hour"))

    def test_low_battery_device_flagged(self):
        load_messages(self.db, generate(defects={}, end=self.end))
        runner.run(self.db)
        status = {r["device_id"]: r["status"] for r in self.db.query("SELECT device_id, status FROM dim_device_health")}
        self.assertEqual(status["esp32-04"], "low_battery")
        self.assertEqual(status["esp32-01"], "ok")

    def test_assertion_actually_fails_on_bad_data(self):
        load_messages(self.db, generate(defects={}, end=self.end))
        runner.run(self.db)
        self.db.execute("INSERT INTO stg_readings (reading_id, device_id, event_ts, temperature_c, humidity_pct, is_plausible) "
                        "SELECT reading_id, device_id, event_ts, temperature_c, humidity_pct, 1 FROM stg_readings LIMIT 1")
        failing = runner.run_assertions(self.db, "t")
        self.assertTrue(any(c["status"] == "FAIL" for c in failing))

    def test_toposort_order_and_cycle_detection(self):
        order = [m.name for m in runner.toposort(runner.discover())]
        self.assertLess(order.index("stg_readings"), order.index("fct_hourly_metrics"))
        a = runner.Model("a", "x", "", ["b"])
        b = runner.Model("b", "x", "", ["a"])
        with self.assertRaises(ValueError):
            runner.toposort([a, b])

    def test_lineage_recorded(self):
        load_messages(self.db, generate(defects={}, end=self.end))
        runner.run(self.db)
        edges = {(r["source"], r["target"]) for r in self.db.query("SELECT source, target FROM gov_lineage")}
        self.assertIn(("raw_readings", "stg_readings"), edges)
        self.assertIn(("stg_readings", "fct_hourly_metrics"), edges)
