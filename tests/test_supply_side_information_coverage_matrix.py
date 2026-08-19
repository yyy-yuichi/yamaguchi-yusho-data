from __future__ import annotations

import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_supply_side_information_coverage_matrix as matrix  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class SupplySideInformationCoverageMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = matrix.build_dataset()
        cls.rows = cls.dataset["rows"]
        cls.model = load_json(ROOT / "data" / "work1_supply_side_information_model.json")
        cls.supply = load_json(ROOT / "docs" / "data" / "municipal_supply.json")
        cls.gtfs = load_json(ROOT / "data" / "municipality_gtfs.json")
        cls.by_key = {
            (row["municipality"], row["item_id"]): row for row in cls.rows
        }
        cls.accepted_source_ids = {
            source["source_id"] for source in cls.model["accepted_source_mapping"]
        }
        cls.registry_source_ids = {
            source["source_id"]
            for source in cls.model["accepted_source_mapping"]
            if source["source_type"] == "registry_pdf"
        }

    def test_identity_dimensions_and_fixed_inputs(self):
        self.assertEqual(
            self.dataset["schema_version"],
            "WORK1-SUPPLY-SIDE-INFORMATION-COVERAGE-MATRIX-1",
        )
        self.assertEqual(self.dataset["task_id"], matrix.TASK_ID)
        self.assertEqual(self.dataset["matrix_as_of"], "2026-08-19")
        self.assertEqual(
            self.dataset["dimensions"],
            {
                "municipality_count": 19,
                "category_count": 8,
                "item_count_per_municipality": 35,
                "row_count": 665,
            },
        )
        self.assertEqual(
            [item["path"] for item in self.dataset["input_files"]],
            list(matrix.INPUT_PATHS),
        )
        for item in self.dataset["input_files"]:
            payload = ROOT.joinpath(*item["path"].split("/")).read_bytes()
            self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest())

    def test_every_municipality_has_every_model_item_once(self):
        model_items = [
            item["item_id"]
            for category in self.model["categories"]
            for item in category["items"]
        ]
        municipality_codes = {
            item["municipality"]: item["municipality_code"] for item in self.gtfs
        }
        self.assertEqual(len(self.rows), 665)
        self.assertEqual(len(self.by_key), 665)
        for municipality, municipality_code in municipality_codes.items():
            municipal_rows = [
                row for row in self.rows if row["municipality"] == municipality
            ]
            self.assertEqual(len(municipal_rows), 35, municipality)
            self.assertEqual(
                [row["item_id"] for row in municipal_rows],
                model_items,
                municipality,
            )
            self.assertTrue(
                all(row["municipality_code"] == municipality_code for row in municipal_rows)
            )

    def test_rows_have_exact_required_fields_and_only_four_states(self):
        allowed = {
            "VISIBLE_CURRENT",
            "ACCEPTED_SOURCE_UNMEASURED",
            "ADDITIONAL_SOURCE_REQUIRED",
            "DEMAND_COMPARATOR_REQUIRED",
        }
        self.assertEqual(self.dataset["required_row_fields"], list(matrix.REQUIRED_ROW_FIELDS))
        for row in self.rows:
            self.assertEqual(list(row), list(matrix.REQUIRED_ROW_FIELDS))
            self.assertIn(row["current_status"], allowed)
            self.assertEqual(row["evidence_date"], "2026-08-19")
            self.assertTrue(set(row["accepted_source_ids"]).issubset(self.accepted_source_ids))
            self.assertEqual(len(row["accepted_source_ids"]), len(set(row["accepted_source_ids"])))
        self.assertEqual(
            self.dataset["status_counts"],
            dict(Counter(row["current_status"] for row in self.rows)),
        )
        self.assertEqual(
            self.dataset["status_counts"],
            {
                "VISIBLE_CURRENT": 128,
                "ACCEPTED_SOURCE_UNMEASURED": 98,
                "ADDITIONAL_SOURCE_REQUIRED": 344,
                "DEMAND_COMPARATOR_REQUIRED": 95,
            },
        )

    def test_additional_and_demand_rows_do_not_claim_an_accepted_source(self):
        for row in self.rows:
            if row["current_status"] in {
                "ADDITIONAL_SOURCE_REQUIRED",
                "DEMAND_COMPARATOR_REQUIRED",
            }:
                self.assertEqual(row["accepted_source_ids"], [], row)

    def test_registry_zero_is_visible_only_within_the_four_registry_scope(self):
        zero_municipalities = {
            item["municipality"]
            for item in self.supply["municipalities"]
            if item["operator_count"] == 0
        }
        self.assertEqual(
            zero_municipalities,
            {"宇部市", "防府市", "山陽小野田市", "平生町"},
        )
        for municipality in zero_municipalities:
            for item_id in ("registered_operator_and_type", "registered_vehicle_count"):
                row = self.by_key[(municipality, item_id)]
                self.assertEqual(row["current_status"], "VISIBLE_CURRENT")
                self.assertEqual(set(row["accepted_source_ids"]), self.registry_source_ids)
                self.assertIn("交通手段・移動支援・別制度の不存在を意味しない", row["claim_boundary"])
            detail = self.by_key[(municipality, "registered_service_area_detail")]
            self.assertEqual(detail["current_status"], "ADDITIONAL_SOURCE_REQUIRED")
            self.assertEqual(detail["accepted_source_ids"], [])

    def test_registry_measurement_rows_require_a_matching_source_row(self):
        supply_by_name = {
            item["municipality"]: item for item in self.supply["municipalities"]
        }
        for municipality, supply_row in supply_by_name.items():
            area = self.by_key[(municipality, "registered_service_area_detail")]
            if supply_row["operators"]:
                self.assertEqual(area["current_status"], "ACCEPTED_SOURCE_UNMEASURED")
                self.assertTrue(area["accepted_source_ids"])
            welfare = self.by_key[(municipality, "welfare_eligibility_scope")]
            has_welfare = any(
                operator["transport_type"] == "福祉有償運送"
                for operator in supply_row["operators"]
            )
            self.assertEqual(
                welfare["current_status"],
                "ACCEPTED_SOURCE_UNMEASURED" if has_welfare else "ADDITIONAL_SOURCE_REQUIRED",
            )

    def test_gtfs_state_is_localized_only_by_accepted_source_relationship(self):
        expected = {
            "岩国市": "iwakuni-gtfsjp",
            "光市": "hikari-gtfs",
            "周南市": "hikari-gtfs",
            "山口市": "jrbus-chugoku-gtfs",
            "萩市": "jrbus-chugoku-gtfs",
            "防府市": "jrbus-chugoku-gtfs",
            "美祢市": "jrbus-chugoku-gtfs",
        }
        for gtfs_row in self.gtfs:
            municipality = gtfs_row["municipality"]
            inventory = self.by_key[(municipality, "gtfs_agency_and_feed_inventory")]
            route = self.by_key[(municipality, "route_identity_and_name")]
            if municipality in expected:
                self.assertEqual(inventory["current_status"], "VISIBLE_CURRENT")
                self.assertEqual(inventory["accepted_source_ids"], [expected[municipality]])
                self.assertEqual(route["current_status"], "ACCEPTED_SOURCE_UNMEASURED")
                self.assertEqual(route["accepted_source_ids"], [expected[municipality]])
            else:
                self.assertEqual(inventory["current_status"], "ADDITIONAL_SOURCE_REQUIRED")
                self.assertEqual(route["current_status"], "ADDITIONAL_SOURCE_REQUIRED")
                self.assertEqual(inventory["accepted_source_ids"], [])
                self.assertEqual(route["accepted_source_ids"], [])
            self.assertIn(
                f"アクセス状態={gtfs_row['availability_status']}",
                inventory["scope_note"],
            )
            self.assertIn("交通の有無・質・網羅率を意味せず", inventory["claim_boundary"])

    def test_feed_metrics_are_not_emitted_as_municipal_values(self):
        for row in self.rows:
            self.assertNotIn("value", row)
            self.assertNotIn("metric_value", row)
        for municipality in ("山口市", "萩市", "防府市", "美祢市"):
            row = self.by_key[(municipality, "scheduled_trip_count_by_date")]
            self.assertEqual(row["current_status"], "VISIBLE_CURRENT")
            self.assertEqual(row["accepted_source_ids"], ["jrbus-chugoku-gtfs"])
            self.assertIn("県外を含む広域指標を市町へ配賦しない", row["claim_boundary"])
            self.assertIn("市町境界内だけの供給量ではない", row["scope_note"])

    def test_no_row_automatically_decides_service_gap(self):
        for row in self.rows:
            self.assertNotIn("service_gap", row)
            self.assertIn("service_gapを自動判定しない", row["claim_boundary"])
        comparator_rows = [
            row for row in self.rows
            if row["current_status"] == "DEMAND_COMPARATOR_REQUIRED"
        ]
        self.assertEqual(len(comparator_rows), 19 * 5)
        self.assertTrue(
            all("比較する前に交通不足を結論づけない" in row["claim_boundary"] for row in comparator_rows)
        )

    def test_generator_is_byte_deterministic_and_matches_internal_output(self):
        first = matrix.render_dataset_json(matrix.build_dataset()).encode("utf-8")
        second = matrix.render_dataset_json(matrix.build_dataset()).encode("utf-8")
        self.assertEqual(first, second)
        self.assertTrue(matrix.OUTPUT_PATH.is_file())
        self.assertEqual(first, matrix.OUTPUT_PATH.read_bytes())
        self.assertFalse(
            (ROOT / "docs" / "data" / matrix.OUTPUT_PATH.name).exists(),
            "coverage matrix must remain internal",
        )


if __name__ == "__main__":
    unittest.main()
