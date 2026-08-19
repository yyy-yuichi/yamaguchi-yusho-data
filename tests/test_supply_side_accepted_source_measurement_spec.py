from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_supply_side_accepted_source_measurement_spec as spec  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class SupplySideAcceptedSourceMeasurementSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = spec.build_dataset()
        cls.matrix = load_json(ROOT / "data" / "work1_supply_side_information_coverage_matrix.json")
        cls.manifest = load_json(ROOT / "data" / "source_freshness_manifest.json")
        cls.profiles = {
            item["source_id"]: item for item in cls.dataset["accepted_source_profiles"]
        }
        cls.item_specs = {
            item["item_id"]: item for item in cls.dataset["item_specifications"]
        }
        cls.applications = cls.dataset["municipality_item_applications"]
        cls.app_by_key = {
            (item["municipality_code"], item["item_id"]): item
            for item in cls.applications
        }

    def test_identity_dimensions_and_readiness_counts(self):
        self.assertEqual(self.dataset["schema_version"], spec.SCHEMA_VERSION)
        self.assertEqual(self.dataset["task_id"], spec.TASK_ID)
        self.assertEqual(self.dataset["spec_as_of"], "2026-08-19")
        self.assertEqual(self.dataset["execution_status"], "SPECIFIED_NOT_EXECUTED")
        self.assertEqual(
            self.dataset["dimensions"],
            {
                "accepted_source_count": 7,
                "measurement_item_count": 12,
                "municipality_item_application_count": 98,
                "input_file_count": 12,
            },
        )
        self.assertEqual(
            self.dataset["readiness_counts"],
            {
                "READY_FOR_BOUNDED_MEASUREMENT": 61,
                "PARTIAL_SOURCE_ONLY": 30,
                "ADDITIONAL_INPUT_REQUIRED": 7,
            },
        )

    def test_input_hashes_cover_metadata_derivatives_and_seven_originals(self):
        inputs = self.dataset["input_files"]
        self.assertEqual(len(inputs), 12)
        self.assertEqual(
            [item["path"] for item in inputs[:5]],
            list(spec.METADATA_INPUT_PATHS),
        )
        self.assertEqual(
            {item["path"] for item in inputs[5:]},
            {item["local_path"] for item in self.manifest["sources"]},
        )
        for item in inputs:
            payload = ROOT.joinpath(*item["path"].split("/")).read_bytes()
            self.assertEqual(item["bytes"], len(payload), item["path"])
            self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest())

    def test_source_profiles_match_manifest_and_gtfs_headers_without_extraction(self):
        manifest_by_id = {item["source_id"]: item for item in self.manifest["sources"]}
        self.assertEqual(set(self.profiles), set(manifest_by_id))
        self.assertEqual(
            {item["source_type"] for item in self.profiles.values()},
            {"registry_pdf", "gtfs_zip"},
        )
        self.assertEqual(
            sum(item["source_type"] == "registry_pdf" for item in self.profiles.values()),
            4,
        )
        self.assertEqual(
            sum(item["source_type"] == "gtfs_zip" for item in self.profiles.values()),
            3,
        )
        for source_id, profile in self.profiles.items():
            manifest = manifest_by_id[source_id]
            self.assertEqual(profile["original_path"], manifest["local_path"])
            self.assertEqual(profile["original_bytes"], manifest["baseline_bytes"])
            self.assertEqual(profile["original_sha256"], manifest["baseline_sha256"])
        hikari = self.profiles["hikari-gtfs"]["tables"]
        self.assertTrue(hikari["transfers.txt"]["present"])
        self.assertEqual(hikari["transfers.txt"]["row_count"], 0)
        self.assertFalse(self.profiles["iwakuni-gtfsjp"]["tables"]["transfers.txt"]["present"])
        self.assertFalse(self.profiles["jrbus-chugoku-gtfs"]["tables"]["transfers.txt"]["present"])
        self.assertIn(
            "wheelchair_accessible",
            self.profiles["jrbus-chugoku-gtfs"]["tables"]["trips.txt"]["columns"],
        )
        source_code = (ROOT / "src" / "build_supply_side_accepted_source_measurement_spec.py").read_text(encoding="utf-8")
        self.assertNotIn(".extract(", source_code)
        self.assertNotIn("extractall", source_code)

    def test_twelve_item_specs_cover_upstream_unmeasured_items_once(self):
        upstream = [
            row for row in self.matrix["rows"]
            if row["current_status"] == "ACCEPTED_SOURCE_UNMEASURED"
        ]
        self.assertEqual(len(upstream), 98)
        self.assertEqual(len(self.item_specs), 12)
        self.assertEqual(
            set(self.item_specs),
            {row["item_id"] for row in upstream},
        )
        ids = [item["measurement_spec_id"] for item in self.item_specs.values()]
        self.assertEqual(len(ids), len(set(ids)))
        for item in self.item_specs.values():
            self.assertTrue(item["measurement_outputs"])
            self.assertTrue(item["source_requirements"])
            self.assertTrue(item["derivation_steps"])
            self.assertTrue(item["verification_rules"])
            self.assertTrue(item["missing_value_rule"])
            self.assertTrue(item["claim_boundary"])

    def test_ninety_eight_applications_match_upstream_rows_and_sources(self):
        upstream = {
            (row["municipality_code"], row["item_id"]): row
            for row in self.matrix["rows"]
            if row["current_status"] == "ACCEPTED_SOURCE_UNMEASURED"
        }
        self.assertEqual(len(self.applications), 98)
        self.assertEqual(len(self.app_by_key), 98)
        self.assertEqual(set(self.app_by_key), set(upstream))
        for key, application in self.app_by_key.items():
            row = upstream[key]
            self.assertEqual(application["municipality"], row["municipality"])
            self.assertEqual(application["category_id"], row["category_id"])
            self.assertEqual(application["accepted_source_ids"], row["accepted_source_ids"])
            self.assertEqual(
                [item["source_id"] for item in application["source_locators"]],
                row["accepted_source_ids"],
            )

    def test_application_fields_are_closed_and_values_are_not_executed(self):
        self.assertEqual(
            self.dataset["required_application_fields"],
            list(spec.REQUIRED_APPLICATION_FIELDS),
        )
        allowed_readiness = {
            "READY_FOR_BOUNDED_MEASUREMENT",
            "PARTIAL_SOURCE_ONLY",
            "ADDITIONAL_INPUT_REQUIRED",
        }
        for application in self.applications:
            self.assertEqual(list(application), list(spec.REQUIRED_APPLICATION_FIELDS))
            self.assertIn(application["execution_readiness"], allowed_readiness)
            self.assertEqual(application["execution_status"], "SPECIFIED_NOT_EXECUTED")
            self.assertNotIn("value", application)
            self.assertNotIn("measurement_value", application)
            self.assertNotIn("result", application)

    def test_all_source_locators_resolve_to_profiles_tables_and_columns(self):
        for application in self.applications:
            for locator in application["source_locators"]:
                profile = self.profiles[locator["source_id"]]
                self.assertEqual(locator["source_type"], profile["source_type"])
                self.assertEqual(locator["original_path"], profile["original_path"])
                for table in locator["tables"]:
                    if profile["source_type"] == "registry_pdf":
                        available = profile["accepted_derivative_tables"][table["table"]]
                        self.assertTrue(table["present"])
                        self.assertTrue(set(table["columns"]).issubset(available["columns"]))
                    else:
                        available = profile["tables"][table["table"]]
                        self.assertEqual(table["present"], available["present"])
                        self.assertTrue(set(table["columns"]).issubset(available["columns"]))
                        if table["required"]:
                            self.assertTrue(table["present"])

    def test_registry_specs_keep_composite_keys_and_limited_meaning(self):
        area = self.item_specs["registered_service_area_detail"]
        welfare = self.item_specs["welfare_eligibility_scope"]
        accessibility = self.item_specs["accessibility_features"]
        self.assertIn("(source_pdf, registration_no)", " ".join(area["derivation_steps"]))
        self.assertIn("service_area_raw", {item["name"] for item in area["measurement_outputs"]})
        self.assertEqual(
            sum(item["item_id"] == "welfare_eligibility_scope" for item in self.applications),
            4,
        )
        self.assertIn("会員条件", welfare["claim_boundary"])
        self.assertIn("(source_pdf, registration_no)", " ".join(accessibility["derivation_steps"]))
        self.assertIn("実稼働車両", accessibility["claim_boundary"])
        for application in self.applications:
            for locator in application["source_locators"]:
                if locator["source_type"] == "registry_pdf":
                    self.assertIn("service_area_municipalities", locator["row_selection"])

    def test_gtfs_specs_remain_feed_wide_and_jrbus_is_not_allocated(self):
        gtfs_locator_count = 0
        jrbus_applications = 0
        for application in self.applications:
            for locator in application["source_locators"]:
                if locator["source_type"] == "gtfs_zip":
                    gtfs_locator_count += 1
                    self.assertEqual(locator["locator_scope"], "accepted_feed_whole_feed_reference")
                    self.assertIn("市町境界による行フィルターなし", locator["row_selection"])
                    self.assertIn("市町内行への割当ではない", application["municipality_applicability"])
            if "jrbus-chugoku-gtfs" in application["accepted_source_ids"]:
                jrbus_applications += 1
                self.assertIn("広域値を関係市へ配賦しない", application["claim_boundary"])
        self.assertGreater(gtfs_locator_count, 0)
        self.assertEqual(jrbus_applications, 40)

    def test_readiness_partition_and_prerequisites_are_explicit(self):
        ready_items = {
            item_id for item_id, item in self.item_specs.items()
            if item["execution_readiness"] == "READY_FOR_BOUNDED_MEASUREMENT"
        }
        partial_items = {
            item_id for item_id, item in self.item_specs.items()
            if item["execution_readiness"] == "PARTIAL_SOURCE_ONLY"
        }
        additional_items = {
            item_id for item_id, item in self.item_specs.items()
            if item["execution_readiness"] == "ADDITIONAL_INPUT_REQUIRED"
        }
        self.assertEqual(len(ready_items), 8)
        self.assertEqual(
            partial_items,
            {"transfer_wait_and_travel_time", "fare_and_payment", "accessibility_features"},
        )
        self.assertEqual(additional_items, {"municipality_feed_spatial_coverage"})
        spatial_apps = [
            item for item in self.applications
            if item["item_id"] == "municipality_feed_spatial_coverage"
        ]
        self.assertEqual(len(spatial_apps), 7)
        self.assertTrue(
            all("市町境界geometryがない" in item["municipality_applicability"] for item in spatial_apps)
        )
        self.assertTrue(
            all("0%・0件ではなく" in item["missing_value_rule"] for item in spatial_apps)
        )

    def test_missing_rules_and_claim_boundaries_never_decide_service_gap(self):
        for application in self.applications:
            self.assertTrue(application["missing_value_rule"])
            self.assertIn("service_gapを示さない", application["claim_boundary"])
            self.assertNotIn("service_gap", application)
        boundaries = "\n".join(self.dataset["global_boundaries"])
        self.assertIn("service_gapを自動判定しない", boundaries)
        self.assertIn("測定値はまだ生成・公開していない", boundaries)

    def test_generator_is_byte_deterministic_and_internal_only(self):
        first = spec.render_dataset_json(spec.build_dataset()).encode("utf-8")
        second = spec.render_dataset_json(spec.build_dataset()).encode("utf-8")
        self.assertEqual(first, second)
        self.assertTrue(spec.OUTPUT_PATH.is_file())
        self.assertEqual(first, spec.OUTPUT_PATH.read_bytes())
        self.assertFalse(
            (ROOT / "docs" / "data" / spec.OUTPUT_PATH.name).exists(),
            "measurement specification must remain internal",
        )
        next_stage = self.dataset["next_stage"]
        self.assertEqual(
            next_stage["task_id"],
            "WORK1-SUPPLY-SIDE-ACCEPTED-SOURCE-BOUNDED-MEASUREMENT-1",
        )
        self.assertEqual(next_stage["status"], "DEFINED_NOT_STARTED")


if __name__ == "__main__":
    unittest.main()
