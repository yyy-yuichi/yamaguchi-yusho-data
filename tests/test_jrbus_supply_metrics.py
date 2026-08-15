"""JRバス中国の広域フィード独立指標に関する回帰契約。"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import build_site_data  # noqa: E402
import calculate_jrbus_supply_metrics as jrbus  # noqa: E402


class JrBusSupplyMetricsTest(unittest.TestCase):
    def setUp(self):
        self.record = jrbus.build_dataset()

    def test_source_and_scope_are_fixed(self):
        source = REPO_ROOT.joinpath(*jrbus.SOURCE_ZIP_RELATIVE_PATH.split("/"))
        payload = source.read_bytes()
        self.assertEqual(jrbus.SOURCE_ZIP_SIZE_BYTES, len(payload))
        self.assertEqual(jrbus.SOURCE_ZIP_SHA256, hashlib.sha256(payload).hexdigest())
        self.assertEqual("JRBUS-SUPPLY-METRIC-1", self.record["metric_version"])
        self.assertEqual("jrbus-chugoku-gtfs", self.record["feed_id"])
        self.assertEqual("whole_feed", self.record["measurement_scope"])
        self.assertEqual("independent_not_comparable", self.record["comparison_mode"])
        self.assertNotIn("municipality", self.record)
        self.assertNotIn("municipality_code", self.record)

    def test_structural_and_daily_values_are_fixed(self):
        self.assertEqual(
            [1, 18, 890],
            [self.record["metrics"][key]["value"] for key in jrbus.STRUCTURE_METRIC_KEYS],
        )
        self.assertEqual(
            [436, 436, 436, 436, 436, 323, 242],
            [item["value"] for item in self.record["scheduled_trip_count_by_date"].values()],
        )
        measured = list(self.record["metrics"].values())
        measured.extend(self.record["scheduled_trip_count_by_date"].values())
        self.assertTrue(all(item == {"value": item["value"], "metric_status": "measured", "reason": None} for item in measured))

    def test_yamaguchi_routes_are_relationship_anchors_only(self):
        self.assertEqual(
            list(jrbus.CONFIRMED_YAMAGUCHI_ROUTES),
            [
                (item["route_id"], item["route_long_name"])
                for item in self.record["confirmed_yamaguchi_routes"]
            ],
        )
        self.assertIn("4路線だけ", self.record["scope_note"])
        self.assertIn("市町間の順位", self.record["scope_note"])
        self.assertTrue(any("4市それぞれの市内供給量ではない" in item for item in self.record["limitations"]))

    def test_generator_is_deterministic_and_matches_both_copies(self):
        first = jrbus.render_dataset_json(jrbus.build_dataset()).encode("utf-8")
        second = jrbus.render_dataset_json(jrbus.build_dataset()).encode("utf-8")
        data_copy = (REPO_ROOT / "data" / "jrbus_chugoku_supply_metrics.json").read_bytes()
        docs_copy = (REPO_ROOT / "docs" / "data" / "jrbus_chugoku_supply_metrics.json").read_bytes()
        self.assertEqual(first, second)
        self.assertEqual(first, data_copy)
        self.assertEqual(data_copy, docs_copy)
        self.assertEqual(build_site_data.JRBUS_SUPPLY_METRICS_SHA256, hashlib.sha256(first).hexdigest())
        build_site_data.validate_jrbus_supply_metrics(json.loads(first))

    def test_existing_two_feed_comparison_is_byte_unchanged(self):
        existing = (REPO_ROOT / "data" / "gtfs_supply_metrics.json").read_bytes()
        published = (REPO_ROOT / "docs" / "data" / "gtfs_supply_metrics.json").read_bytes()
        self.assertEqual(
            "c277e1050086da6ad5cc703051deb672458f7bf2829e1aca92fd0b17b4d20930",
            hashlib.sha256(existing).hexdigest(),
        )
        self.assertEqual(existing, published)
        self.assertEqual(["iwakuni-gtfsjp", "hikari-gtfs"], [item["feed_id"] for item in json.loads(existing)])

    def test_public_pages_explain_independent_scope(self):
        index = (REPO_ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        status = (REPO_ROOT / "docs" / "status.html").read_text(encoding="utf-8")
        entry = (REPO_ROOT / "docs" / "entry.html").read_text(encoding="utf-8")
        for marker in (
            "jrbus_chugoku_supply_metrics.json",
            "jrbus-metric-status",
            "jrbus-structure-body",
            "jrbus-daily-body",
            "jrbus-route-list",
            "independent_not_comparable",
        ):
            self.assertIn(marker, index)
        self.assertIn("既存2フィード比較とは別枠", index)
        self.assertIn("広域フィード全体", status)
        self.assertIn("市町別の値ではない", status)
        self.assertIn("独立指標", entry)
        self.assertNotIn("[436, 436, 436, 436, 436, 323, 242]", index)


if __name__ == "__main__":
    unittest.main()
