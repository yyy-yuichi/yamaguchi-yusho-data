"""Acceptance tests for WORK1-OFFICIAL-GTFS-COVERAGE-EXTENSION-1."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import unittest
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = REPO_ROOT / "evidence" / "20260813_work1_official_gtfs_coverage_extension_research.json"
ZIP_PATH = REPO_ROOT / "raw" / "gtfs" / "jrbus_chugoku_gtfs_20260813.zip"
MUNICIPALITIES = REPO_ROOT / "data" / "municipality_gtfs.json"
FEEDS = REPO_ROOT / "data" / "gtfs_feeds.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def zip_rows(archive: zipfile.ZipFile, name: str):
    with archive.open(name) as raw:
        return list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")))


class OfficialGtfsCoverageExtensionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = read_json(EVIDENCE)
        cls.municipalities = read_json(MUNICIPALITIES)
        cls.feeds = read_json(FEEDS)

    def test_approved_zip_identity_and_safe_container(self):
        accepted = self.evidence["accepted_jrbus_zip"]
        payload = ZIP_PATH.read_bytes()
        self.assertEqual(len(payload), accepted["size_bytes"])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), accepted["sha256"])
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(len(archive.infolist()), accepted["zip_entry_count"])
            self.assertEqual(sum(item.file_size for item in archive.infolist()), accepted["zip_uncompressed_bytes"])
            self.assertFalse(any(item.flag_bits & 1 for item in archive.infolist()))
            unsafe = [
                item.filename for item in archive.infolist()
                if item.filename.startswith(("/", "\\")) or ".." in PurePosixPath(item.filename).parts
            ]
            self.assertEqual(unsafe, [])

    def test_core_counts_dates_and_yamaguchi_route_ids_match_zip(self):
        accepted = self.evidence["accepted_jrbus_zip"]
        with zipfile.ZipFile(ZIP_PATH) as archive:
            for filename, expected in accepted["core_counts"].items():
                self.assertEqual(len(zip_rows(archive, filename)), expected, filename)
            feed_info = zip_rows(archive, "feed_info.txt")
            self.assertEqual(len(feed_info), 1)
            for key, expected in accepted["feed_info"].items():
                self.assertEqual(feed_info[0][key], expected)
            routes = {row["route_id"]: row["route_long_name"] for row in zip_rows(archive, "routes.txt")}
        for row in accepted["yamaguchi_related_routes"]:
            self.assertEqual(routes[row["route_id"]], row["route_long_name"])

    def test_four_state_counts_and_every_municipality_has_evidence(self):
        expected = self.evidence["all_municipality_state_counts"]
        self.assertEqual(dict(Counter(row["availability_status"] for row in self.municipalities)), expected)
        self.assertEqual(len(self.municipalities), 19)
        feed_ids = {row["feed_id"] for row in self.feeds}
        for row in self.municipalities:
            related = [value for value in row["feed_ids"].split(";") if value]
            self.assertTrue(related, row["municipality"])
            self.assertTrue(set(related) <= feed_ids, row["municipality"])
            self.assertIn(EVIDENCE.relative_to(REPO_ROOT).as_posix(), row["source_evidence"])

    def test_all_thirteen_formerly_unconfirmed_municipalities_are_resolved(self):
        outcomes = self.evidence["former_unconfirmed_municipality_outcomes"]
        self.assertEqual(len(outcomes), 13)
        self.assertEqual(len({row["municipality"] for row in outcomes}), 13)
        actual = {row["municipality"]: row["availability_status"] for row in self.municipalities}
        for outcome in outcomes:
            self.assertEqual(actual[outcome["municipality"]], outcome["status"])

    def test_nonpublic_and_unavailable_feeds_have_no_fabricated_local_raw_file(self):
        access_by_id = {row["feed_id"]: row["access_status"] for row in self.feeds}
        self.assertEqual(access_by_id["bocho-kotsu-gtfsjp"], "not_publicly_distributed")
        self.assertEqual(access_by_id["sanden-kotsu-gtfs"], "not_publicly_distributed")
        self.assertEqual(access_by_id["blueline-kotsu-gtfs"], "not_publicly_distributed")
        self.assertEqual(access_by_id["waki-community-bus-gtfsjp"], "official_resource_unavailable")
        raw_names = {path.name for path in (REPO_ROOT / "raw" / "gtfs").iterdir() if path.is_file()}
        for forbidden in ("bocho.zip", "sanden.zip", "blueline.zip", "waki.zip"):
            self.assertNotIn(forbidden, raw_names)


if __name__ == "__main__":
    unittest.main()
