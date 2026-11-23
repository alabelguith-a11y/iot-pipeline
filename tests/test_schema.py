import unittest

from iotpipe.schema import validate

GOOD = {"reading_id": "esp32-01-abcdef12", "device_id": "esp32-01", "ts": "2026-01-01T10:00:00Z",
        "temperature_c": 21.5, "humidity_pct": 50.0}


class SchemaTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(GOOD), [])

    def test_missing_required(self):
        bad = {k: v for k, v in GOOD.items() if k != "humidity_pct"}
        self.assertTrue(any("humidity_pct" in e for e in validate(bad)))

    def test_wrong_type_and_range(self):
        self.assertTrue(validate({**GOOD, "temperature_c": "hot"}))
        self.assertTrue(validate({**GOOD, "temperature_c": 500}))

    def test_bool_is_not_a_number(self):
        self.assertTrue(validate({**GOOD, "temperature_c": True}))

    def test_unknown_field_and_bad_ts(self):
        self.assertTrue(validate({**GOOD, "foo": 1}))
        self.assertTrue(validate({**GOOD, "ts": "yesterday"}))

    def test_not_an_object(self):
        self.assertTrue(validate([1, 2, 3]))
