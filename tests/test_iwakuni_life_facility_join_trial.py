"""岩国市3施設データと既存バス停の座標結合試験。

ネットワークへ接続せず、保存済み公式CSV 3件、受入済み岩国市GTFS ZIP、出典登録JSON、
生成済み結合試験JSONだけを読む。徒歩経路、徒歩圏、所要時間、生活行程は検証対象外。
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import build_iwakuni_life_facility_join_trial as trial  # noqa: E402


OUTPUT_PATH = REPO_ROOT / "data" / "iwakuni_life_facility_join_trial.json"


class IwakuniLifeFacilityJoinTrialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = trial.load_source_registry()
        cls.dataset = trial.build_dataset(cls.registry)

    def test_source_registry_has_three_equal_scope_official_sources(self):
        sources = self.registry["facility_sources"]
        self.assertEqual(len(sources), 3)
        self.assertEqual(
            [source["dataset_id"] for source in sources],
            ["352080-public", "352080-hospital", "352080-preschool"],
        )
        self.assertEqual(
            {source["common_category"] for source in sources},
            {"public_facility", "medical_facility", "childcare_facility"},
        )
        for source in sources:
            with self.subTest(source=source["source_id"]):
                self.assertEqual(source["license_id"], "cc-by")
                self.assertEqual(source["resource_last_modified"][:10], "2025-03-31")
                self.assertTrue(source["dataset_page_url"].startswith("https://yamaguchi-opendata.jp/ckan/dataset/"))
                self.assertTrue(source["resource_url"].startswith("https://yamaguchi-opendata.jp/ckan/dataset/"))

    def test_saved_official_files_match_registered_bytes_and_sha256(self):
        for source in [*self.registry["facility_sources"], self.registry["bus_stop_source"]]:
            with self.subTest(source=source.get("source_id", source.get("feed_id"))):
                path = trial.verify_registered_file(source)
                self.assertTrue(path.is_file())
                size, digest = trial.sha256_file(path)
                self.assertEqual(size, source["bytes"])
                self.assertEqual(digest, source["sha256"])

    def test_coordinate_parser_distinguishes_missing_and_invalid(self):
        self.assertEqual(trial.parse_coordinate("", -90, 90), (None, "missing"))
        self.assertEqual(trial.parse_coordinate("not-a-number", -90, 90), (None, "invalid"))
        self.assertEqual(trial.parse_coordinate("91", -90, 90), (None, "invalid"))
        self.assertEqual(trial.parse_coordinate("34.1", -90, 90), (34.1, "valid"))
        self.assertEqual(trial.parse_coordinate("nan", -90, 90), (None, "invalid"))

    def test_normalization_counts_source_rows_and_quality_problems(self):
        quality = {item["source_id"]: item for item in self.dataset["quality_by_source"]}
        expected = {
            "iwakuni-public-facility": {
                "source_row_count": 91,
                "normalized_record_count": 88,
                "excluded_from_join_count": 3,
                "missing_name_count": 3,
                "missing_coordinate_count": 3,
                "invalid_coordinate_count": 0,
                "missing_classification_count": 0,
                "duplicate_candidate_record_count": 0,
            },
            "iwakuni-medical-facility": {
                "source_row_count": 164,
                "normalized_record_count": 164,
                "excluded_from_join_count": 0,
                "missing_name_count": 0,
                "missing_coordinate_count": 0,
                "invalid_coordinate_count": 0,
                "missing_classification_count": 0,
                "duplicate_candidate_record_count": 0,
            },
            "iwakuni-childcare-facility": {
                "source_row_count": 52,
                "normalized_record_count": 52,
                "excluded_from_join_count": 0,
                "missing_name_count": 0,
                "missing_coordinate_count": 0,
                "invalid_coordinate_count": 0,
                "missing_classification_count": 0,
                "duplicate_candidate_record_count": 0,
            },
        }
        for source_id, expected_values in expected.items():
            for key, expected_value in expected_values.items():
                with self.subTest(source=source_id, field=key):
                    self.assertEqual(quality[source_id][key], expected_value)
        self.assertEqual(self.dataset["facility_record_count"], 304)
        self.assertEqual(self.dataset["duplicate_candidates"], [])

    def test_common_records_have_required_provenance_and_license_fields(self):
        records = self.dataset["facility_records"]
        self.assertEqual(len(records), 304)
        for record in records:
            with self.subTest(record=record["facility_id"]):
                self.assertTrue(record["facility_name"])
                self.assertTrue(record["source_category"])
                self.assertTrue(-90 <= record["latitude"] <= 90)
                self.assertTrue(-180 <= record["longitude"] <= 180)
                self.assertTrue(record["source_updated_at"].startswith("2025-03-31T"))
                self.assertTrue(record["source"]["raw_path"].startswith("raw/iwakuni_life_facility_join_trial/"))
                self.assertGreaterEqual(record["source"]["source_row_number"], 2)
                self.assertEqual(record["source"]["retrieved_at"], "2026-08-27")
                self.assertEqual(record["license"]["id"], "cc-by")
                self.assertTrue(record["license"]["url"])

    def test_public_uses_dataset_classification_and_other_sources_keep_row_classification(self):
        categories = {}
        for record in self.dataset["facility_records"]:
            categories.setdefault(record["common_category"], set()).add(record["source_category"])
        self.assertEqual(categories["public_facility"], {"公共施設"})
        self.assertEqual(categories["medical_facility"], {"病院", "有床診療所", "無床診療所"})
        self.assertEqual(
            categories["childcare_facility"],
            {
                "認可公立保育所",
                "認可私立保育所",
                "私立幼稚園",
                "認定こども園（幼稚園型）",
                "認定こども園（幼保連携型）",
            },
        )

    def test_duplicate_candidate_rule_is_name_and_distance_bounded(self):
        records = [
            {
                "facility_id": "a",
                "facility_name": "テスト 施設",
                "latitude": 34.0,
                "longitude": 132.0,
            },
            {
                "facility_id": "b",
                "facility_name": "テスト施設",
                "latitude": 34.0001,
                "longitude": 132.0,
            },
            {
                "facility_id": "c",
                "facility_name": "テスト施設",
                "latitude": 35.0,
                "longitude": 132.0,
            },
            {
                "facility_id": "d",
                "facility_name": "別施設",
                "latitude": 34.0001,
                "longitude": 132.0,
            },
        ]
        candidates = trial.find_duplicate_candidates(records)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["first_facility_id"], "a")
        self.assertEqual(candidates[0]["second_facility_id"], "b")
        self.assertLessEqual(candidates[0]["straight_line_distance_m"], 30.0)

    def test_haversine_is_symmetric_and_zero_for_same_point(self):
        self.assertEqual(trial.haversine_meters(34.0, 132.0, 34.0, 132.0), 0.0)
        forward = trial.haversine_meters(34.0, 132.0, 34.1, 132.1)
        backward = trial.haversine_meters(34.1, 132.1, 34.0, 132.0)
        self.assertTrue(math.isclose(forward, backward, rel_tol=0, abs_tol=1e-9))

    def test_bus_stop_join_uses_five_unique_stops_and_all_three_categories(self):
        quality = self.dataset["bus_stop_quality"]
        self.assertEqual(quality["source_row_count"], 800)
        self.assertEqual(quality["valid_boarding_location_count"], 800)
        self.assertEqual(quality["missing_coordinate_count"], 0)
        self.assertEqual(quality["invalid_coordinate_count"], 0)

        join = self.dataset["bus_stop_join_trial"]
        self.assertEqual(join["method"], "haversine_straight_line_distance")
        self.assertEqual(join["sample_stop_count"], 5)
        self.assertEqual(join["category_count"], 3)
        self.assertEqual(join["distance_calculation_count"], 15)
        self.assertTrue(join["all_distance_calculations_succeeded"])
        self.assertEqual(
            [result["stop_id"] for result in join["results"]],
            ["100_01", "101_01", "102_01", "103_01", "104_01"],
        )
        expected_categories = ["public_facility", "medical_facility", "childcare_facility"]
        for result in join["results"]:
            with self.subTest(stop=result["stop_id"]):
                nearest = result["nearest_facility_by_category"]
                self.assertEqual([item["common_category"] for item in nearest], expected_categories)
                self.assertTrue(all(item["straight_line_distance_m"] >= 0 for item in nearest))

    def test_known_join_result_is_stable(self):
        first = self.dataset["bus_stop_join_trial"]["results"][0]
        self.assertEqual(first["stop_name"], "川上")
        self.assertEqual(
            [(item["facility_name"], item["straight_line_distance_m"]) for item in first["nearest_facility_by_category"]],
            [("周東総合支所", 1818.2), ("山口平成病院", 1476.8), ("たかもり本陣保育園", 2192.8)],
        )

    def test_output_states_non_route_boundaries(self):
        boundary_text = " ".join(self.dataset["boundaries"])
        self.assertIn("徒歩経路", boundary_text)
        self.assertIn("徒歩圏", boundary_text)
        self.assertIn("所要時間", boundary_text)
        self.assertIn("最終対象地域", boundary_text)
        self.assertIn("医療を中心にしない", boundary_text)

    def test_generated_output_is_byte_identical_and_deterministic(self):
        self.assertTrue(OUTPUT_PATH.is_file())
        regenerated = trial.render_dataset_json(trial.build_dataset(self.registry)).encode("utf-8")
        self.assertEqual(regenerated, OUTPUT_PATH.read_bytes())
        self.assertEqual(
            trial.render_dataset_json(trial.build_dataset(self.registry)),
            trial.render_dataset_json(trial.build_dataset(self.registry)),
        )


if __name__ == "__main__":
    unittest.main()
