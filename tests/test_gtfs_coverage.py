"""WORK1-GTFS-COVERAGE-2: accepted-feed municipal coverage evidence tests."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HIKARI_ZIP = REPO_ROOT / "raw" / "gtfs" / "hikari_gtfs_20260401.zip"
EVIDENCE_PATH = REPO_ROOT / "evidence" / "20260812_work1_gtfs_coverage_hikari_route7.json"
DATA_DIR = REPO_ROOT / "data"
DOCS_DATA_DIR = REPO_ROOT / "docs" / "data"
MEMO_PATH = REPO_ROOT / "docs" / "municipality-memo.html"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_zip_csv(zf: zipfile.ZipFile, name: str):
    with zf.open(name) as raw:
        return list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")))


class HikariRoute7EvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = read_json(EVIDENCE_PATH)
        with zipfile.ZipFile(HIKARI_ZIP) as zf:
            cls.routes = {row["route_id"]: row for row in read_zip_csv(zf, "routes.txt")}
            cls.trips = read_zip_csv(zf, "trips.txt")
            cls.stop_times = read_zip_csv(zf, "stop_times.txt")
            cls.stops = {row["stop_id"]: row for row in read_zip_csv(zf, "stops.txt")}

    def test_accepted_zip_size_and_hash_are_fixed(self):
        source = self.evidence["source_zip"]
        payload = HIKARI_ZIP.read_bytes()
        self.assertEqual(len(payload), source["size_bytes"])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), source["sha256"])

    def test_route_7_trip_and_boarding_stop_counts_match_evidence(self):
        route = self.evidence["route"]
        self.assertEqual(self.routes["7"]["route_long_name"], "広域生活交通")
        trip_ids = {row["trip_id"] for row in self.trips if row["route_id"] == "7"}
        stop_ids = {row["stop_id"] for row in self.stop_times if row["trip_id"] in trip_ids}
        self.assertEqual(len(trip_ids), route["trip_count"])
        self.assertEqual(len(stop_ids), route["boarding_stop_id_count"])
        self.assertEqual(len(stop_ids), 94)
        self.assertTrue(stop_ids <= self.stops.keys())

    def test_all_recorded_shunan_stop_names_exist_on_route_7(self):
        trip_ids = {row["trip_id"] for row in self.trips if row["route_id"] == "7"}
        stop_ids = {row["stop_id"] for row in self.stop_times if row["trip_id"] in trip_ids}
        route_names = {self.stops[stop_id]["stop_name"] for stop_id in stop_ids}
        shunan = next(
            row for row in self.evidence["municipality_summary"]
            if row["municipality_code"] == "35215"
        )
        self.assertEqual(shunan["stop_id_count"], 31)
        self.assertEqual(shunan["unique_stop_name_count"], 17)
        self.assertEqual(len(shunan["unique_stop_names"]), 17)
        self.assertTrue(set(shunan["unique_stop_names"]) <= route_names)

    def test_representative_gsi_coordinates_match_gtfs_and_route(self):
        trip_ids = {row["trip_id"] for row in self.trips if row["route_id"] == "7"}
        route_stop_ids = {row["stop_id"] for row in self.stop_times if row["trip_id"] in trip_ids}
        for sample in self.evidence["representative_gsi_results"]:
            with self.subTest(stop_id=sample["stop_id"]):
                self.assertIn(sample["stop_id"], route_stop_ids)
                stop = self.stops[sample["stop_id"]]
                self.assertEqual(stop["stop_name"], sample["stop_name"])
                self.assertEqual(stop["stop_lat"], sample["stop_lat"])
                self.assertEqual(stop["stop_lon"], sample["stop_lon"])
        self.assertEqual(
            {row["municipality_code"] for row in self.evidence["representative_gsi_results"]},
            {"35210", "35215"},
        )


class MunicipalCoveragePublicationTest(unittest.TestCase):
    def test_public_json_copies_are_byte_identical(self):
        for name in ("gtfs_feeds.json", "municipality_gtfs.json", "gtfs_supply_metrics.json"):
            self.assertEqual((DATA_DIR / name).read_bytes(), (DOCS_DATA_DIR / name).read_bytes(), name)

    def test_four_access_states_and_shunan_relation(self):
        rows = read_json(DATA_DIR / "municipality_gtfs.json")
        counts = {}
        for row in rows:
            counts[row["availability_status"]] = counts.get(row["availability_status"], 0) + 1
        self.assertEqual(counts, {
            "public_download_confirmed": 7,
            "authentication_required": 2,
            "not_publicly_distributed": 9,
            "official_resource_unavailable": 1,
        })
        shunan = next(row for row in rows if row["municipality"] == "周南市")
        self.assertEqual(shunan["municipality_code"], "352152")
        self.assertEqual(shunan["feed_ids"].split(";")[0], "hikari-gtfs")
        self.assertIn("路線7", shunan["scope_note"])
        self.assertIn("一般配布なし", shunan["scope_note"])

    def test_metrics_remain_two_feed_records_not_municipality_duplicates(self):
        metrics = read_json(DATA_DIR / "gtfs_supply_metrics.json")
        self.assertEqual([row["feed_id"] for row in metrics], ["iwakuni-gtfsjp", "hikari-gtfs"])
        self.assertEqual(len(metrics), 2)
        self.assertNotIn("周南市", {row["municipality"] for row in metrics})
        self.assertIn("関連付けた市町から参照する", metrics[1]["scope_note"])

    def test_memo_associates_metrics_by_feed_id_and_keeps_scope_limit(self):
        html = MEMO_PATH.read_text(encoding="utf-8")
        self.assertIn("associatedFeedIds.has(row.feed_id)", html)
        self.assertIn("複数市町に関連し得るフィード全体の測定値", html)
        for forbidden in ("整備率", "網羅率", "交通カバー率", "GTFSなし", "未整備"):
            self.assertNotIn(forbidden, html)


if __name__ == "__main__":
    unittest.main()
