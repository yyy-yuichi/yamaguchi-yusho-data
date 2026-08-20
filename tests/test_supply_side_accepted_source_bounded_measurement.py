from __future__ import annotations

import hashlib
import json
import sys
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_supply_side_accepted_source_bounded_measurement as bounded  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def table_by_name(result):
    return {table["name"]: table for table in result["output_tables"]}


def keys_named(value, target):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key == target:
                found.append(child)
            found.extend(keys_named(child, target))
    elif isinstance(value, list):
        for child in value:
            found.extend(keys_named(child, target))
    return found


class SupplySideAcceptedSourceBoundedMeasurementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = bounded.build_dataset()
        cls.specification = load_json(
            ROOT / "data" / "work1_supply_side_accepted_source_measurement_spec.json"
        )
        cls.feedback = load_json(
            ROOT / "evidence" / "20260820_work1_udc_yamaguchi_coordinator_qualitative_feedback.json"
        )
        cls.results = cls.dataset["measurement_results"]
        cls.applications = cls.dataset["municipality_item_measurements"]
        cls.result_by_id = {
            result["measurement_result_id"]: result for result in cls.results
        }
        cls.gtfs_results = {
            (result["source_ids"][0], result["item_id"]): result
            for result in cls.results
            if result["source_scope"]["scope_type"] == "accepted_feed_whole_feed"
        }

    def test_identity_dimensions_and_status(self):
        self.assertEqual(self.dataset["schema_version"], bounded.SCHEMA_VERSION)
        self.assertEqual(self.dataset["task_id"], bounded.TASK_ID)
        self.assertEqual(self.dataset["measurement_as_of"], "2026-08-20")
        self.assertEqual(self.dataset["measurement_status"], "MEASURED_BOUNDED")
        self.assertEqual(
            self.dataset["dimensions"],
            {
                "accepted_source_count": 7,
                "measured_item_count": 8,
                "measured_application_count": 61,
                "normalized_measurement_result_count": 37,
                "excluded_partial_application_count": 30,
                "excluded_additional_input_application_count": 7,
                "input_file_count": 13,
            },
        )

    def test_inputs_are_spec_plus_twelve_frozen_files_and_exclude_feedback(self):
        inputs = self.dataset["input_files"]
        self.assertEqual(len(inputs), 13)
        self.assertEqual(inputs[0]["path"], bounded.MEASUREMENT_SPEC_PATH)
        self.assertEqual(
            [item["path"] for item in inputs[1:]],
            [item["path"] for item in self.specification["input_files"]],
        )
        for item in inputs:
            payload = ROOT.joinpath(*item["path"].split("/")).read_bytes()
            self.assertEqual(item["bytes"], len(payload), item["path"])
            self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest(), item["path"])
        input_paths = {item["path"] for item in inputs}
        self.assertNotIn(
            "evidence/20260820_work1_udc_yamaguchi_coordinator_qualitative_feedback.json",
            input_paths,
        )
        self.assertFalse(self.dataset["external_feedback_separation"]["included_in_input_files"])
        self.assertFalse(self.dataset["external_feedback_separation"]["used_to_create_measurement_values"])

    def test_only_the_sixty_one_ready_applications_are_measured(self):
        ready = {
            (item["municipality_code"], item["item_id"])
            for item in self.specification["municipality_item_applications"]
            if item["execution_readiness"] == "READY_FOR_BOUNDED_MEASUREMENT"
        }
        partial = [
            item for item in self.specification["municipality_item_applications"]
            if item["execution_readiness"] == "PARTIAL_SOURCE_ONLY"
        ]
        additional = [
            item for item in self.specification["municipality_item_applications"]
            if item["execution_readiness"] == "ADDITIONAL_INPUT_REQUIRED"
        ]
        measured = {(item["municipality_code"], item["item_id"]) for item in self.applications}
        self.assertEqual(len(ready), 61)
        self.assertEqual(measured, ready)
        self.assertEqual(len(partial), 30)
        self.assertEqual(len(additional), 7)
        self.assertEqual(len(self.dataset["excluded_applications"]["PARTIAL_SOURCE_ONLY"]), 30)
        self.assertEqual(len(self.dataset["excluded_applications"]["ADDITIONAL_INPUT_REQUIRED"]), 7)
        self.assertTrue(all(item["measurement_status"] == "MEASURED_BOUNDED" for item in self.applications))

    def test_application_and_result_contracts_are_closed_and_resolve(self):
        self.assertEqual(
            self.dataset["required_application_fields"], list(bounded.APPLICATION_FIELDS)
        )
        self.assertEqual(self.dataset["required_result_fields"], list(bounded.RESULT_FIELDS))
        self.assertEqual(len(self.applications), 61)
        self.assertEqual(len(self.results), 37)
        self.assertEqual(len(self.result_by_id), 37)
        for application in self.applications:
            self.assertEqual(list(application), list(bounded.APPLICATION_FIELDS))
            self.assertTrue(application["measurement_result_ids"])
            for result_id in application["measurement_result_ids"]:
                self.assertIn(result_id, self.result_by_id)
                result = self.result_by_id[result_id]
                self.assertEqual(result["item_id"], application["item_id"])
        for result in self.results:
            self.assertEqual(list(result), list(bounded.RESULT_FIELDS))
            self.assertTrue(result["output_tables"])
            self.assertTrue(result["summary"])
            self.assertTrue(result["verification"])

    def test_registry_measurements_keep_composite_keys_pages_and_direct_matches(self):
        registry_results = [
            result for result in self.results
            if result["source_scope"]["scope_type"] == "municipality_matched_registry_records"
        ]
        self.assertEqual(len(registry_results), 19)
        self.assertEqual(
            Counter(result["item_id"] for result in registry_results),
            Counter({"registered_service_area_detail": 15, "welfare_eligibility_scope": 4}),
        )
        for result in registry_results:
            self.assertEqual(
                result["source_scope"]["allocation"],
                "direct_existing_match_not_apportionment",
            )
            for table in result["output_tables"]:
                self.assertEqual(table["key_fields"], ["source_pdf", "registration_no"])
                page_index = table["columns"].index("source_page")
                pdf_index = table["columns"].index("source_pdf")
                reg_index = table["columns"].index("registration_no")
                keys = {(row[pdf_index], row[reg_index]) for row in table["rows"]}
                self.assertEqual(len(keys), table["row_count"])
                self.assertTrue(all(row[page_index] > 0 for row in table["rows"]))

    def test_welfare_flags_are_limited_original_values_not_membership_conditions(self):
        welfare_results = [
            result for result in self.results
            if result["item_id"] == "welfare_eligibility_scope"
        ]
        self.assertEqual(len(welfare_results), 4)
        for result in welfare_results:
            table = result["output_tables"][0]
            flag_indexes = [table["columns"].index(column) for column in bounded.WELFARE_FLAG_COLUMNS]
            for row in table["rows"]:
                self.assertTrue(all(row[index] in (0, 1, None) for index in flag_indexes))
            self.assertIn("会員条件", result["claim_boundary"])

    def test_gtfs_results_are_whole_feed_and_shared_without_municipal_allocation(self):
        self.assertEqual(len(self.gtfs_results), 18)
        gtfs_applications = [
            item for item in self.applications
            if item["result_scope"] == "accepted_feed_whole_feed_reference"
        ]
        self.assertEqual(len(gtfs_applications), 42)
        for result in self.gtfs_results.values():
            self.assertFalse(result["source_scope"]["municipality_filtering"])
            self.assertFalse(result["source_scope"]["municipality_allocation"])
        for application in gtfs_applications:
            self.assertIn("フィード全体値を市町内供給量へ配賦しない", application["allocation_boundary"])
        jrbus_apps = [
            item for item in gtfs_applications
            if item["accepted_source_ids"] == ["jrbus-chugoku-gtfs"]
        ]
        self.assertEqual(len(jrbus_apps), 24)
        for application in jrbus_apps:
            result = self.result_by_id[application["measurement_result_ids"][0]]
            self.assertIn("関係4市へ配賦しない", result["claim_boundary"])

    def test_route_results_match_accepted_feed_records_and_references(self):
        expected = {
            "iwakuni-gtfsjp": (46, 267),
            "hikari-gtfs": (7, 63),
            "jrbus-chugoku-gtfs": (18, 1113),
        }
        for source_id, counts in expected.items():
            result = self.gtfs_results[(source_id, "route_identity_and_name")]
            tables = table_by_name(result)
            self.assertEqual(tables["route_records"]["row_count"], counts[0])
            self.assertEqual(tables["trip_pattern_references"]["row_count"], counts[1])
            self.assertTrue(result["verification"]["trip_route_references_resolved"])

    def test_stop_results_keep_names_coordinates_and_optional_column_absence(self):
        expected = {
            "iwakuni-gtfsjp": 800,
            "hikari-gtfs": 172,
            "jrbus-chugoku-gtfs": 891,
        }
        for source_id, count in expected.items():
            result = self.gtfs_results[(source_id, "stop_name_and_coordinates")]
            table = table_by_name(result)["stop_records"]
            self.assertEqual(table["row_count"], count)
            self.assertTrue(result["verification"]["coordinates_numeric_in_range"])
            self.assertLessEqual(result["summary"]["latitude_min"], result["summary"]["latitude_max"])
            self.assertLessEqual(result["summary"]["longitude_min"], result["summary"]["longitude_max"])
        hikari = self.gtfs_results[("hikari-gtfs", "stop_name_and_coordinates")]
        self.assertNotIn("parent_station", hikari["summary"]["present_optional_columns"])
        parent_index = table_by_name(hikari)["stop_records"]["columns"].index("parent_station")
        self.assertTrue(
            all(row[parent_index] is None for row in table_by_name(hikari)["stop_records"]["rows"])
        )

    def test_shape_results_keep_ordered_points_and_resolved_trip_references(self):
        expected = {
            "iwakuni-gtfsjp": (157, 33890),
            "hikari-gtfs": (23, 8119),
            "jrbus-chugoku-gtfs": (100, 39428),
        }
        for source_id, counts in expected.items():
            result = self.gtfs_results[(source_id, "route_shape")]
            tables = table_by_name(result)
            self.assertEqual(tables["ordered_shape_points"]["row_count"], counts[0])
            self.assertEqual(result["summary"]["shape_point_count"], counts[1])
            for shape_row in tables["ordered_shape_points"]["rows"]:
                sequences = [point[0] for point in shape_row[2]]
                self.assertEqual(sequences, sorted(sequences))
                self.assertEqual(len(sequences), len(set(sequences)))
            statuses = {row[3] for row in tables["trip_shape_references"]["rows"]}
            self.assertTrue(statuses <= {"resolved", "shape_id_blank"})

    def test_calendar_results_expand_only_active_service_ids_with_source_date_basis(self):
        expected = {
            "iwakuni-gtfsjp": (365, 315),
            "hikari-gtfs": (365, 365),
            "jrbus-chugoku-gtfs": (185, 185),
        }
        for source_id, counts in expected.items():
            result = self.gtfs_results[(source_id, "service_calendar")]
            tables = table_by_name(result)
            active = tables["active_service_by_date"]
            self.assertEqual(active["row_count"], counts[0])
            self.assertEqual(result["summary"]["date_with_active_service_count"], counts[1])
            dates = [row[0] for row in active["rows"]]
            self.assertEqual(dates, sorted(dates))
            self.assertEqual(len(dates), len(set(dates)))
            self.assertTrue(result["verification"]["zero_active_service_dates_not_read_as_service_absence"])

    def test_timetable_results_are_normalized_templates_with_valid_references(self):
        expected = {
            "iwakuni-gtfsjp": 7362,
            "hikari-gtfs": 1344,
            "jrbus-chugoku-gtfs": 35515,
        }
        for source_id, count in expected.items():
            result = self.gtfs_results[(source_id, "stop_level_timetable")]
            table = table_by_name(result)["scheduled_stop_call_templates"]
            self.assertEqual(table["row_count"], count)
            self.assertEqual(result["summary"]["stop_call_template_count"], count)
            self.assertEqual(
                result["summary"]["date_resolution"]["active_service_result_id"],
                f"BMR-{source_id}-MS-06-GTFS-SERVICE-CALENDAR",
            )
            self.assertTrue(result["verification"]["trip_stop_sequence_keys_unique"])
            self.assertIn("実績ではない", result["claim_boundary"])

    def test_frequency_results_reconcile_to_timetable_templates(self):
        for source_id in ("iwakuni-gtfsjp", "hikari-gtfs", "jrbus-chugoku-gtfs"):
            result = self.gtfs_results[(source_id, "time_band_frequency")]
            timetable = self.gtfs_results[(source_id, "stop_level_timetable")]
            self.assertEqual(
                result["summary"]["scheduled_departure_template_count"],
                timetable["summary"]["stop_call_template_count"],
            )
            self.assertTrue(result["verification"]["hour_group_counts_reconcile_to_stop_call_templates"])
            self.assertTrue(result["verification"]["first_last_counts_reconcile_to_stop_call_templates"])
            hour_table = table_by_name(result)["scheduled_departure_count_by_service_route_stop_hour"]
            hour_index = hour_table["columns"].index("hour_start")
            self.assertTrue(all(row[hour_index].endswith(":00:00") for row in hour_table["rows"]))

    def test_external_feedback_is_one_separate_directional_record_not_validation(self):
        self.assertEqual(self.feedback["work_id"], "WORK1")
        self.assertEqual(self.feedback["record_type"], "EXTERNAL_QUALITATIVE_FEEDBACK")
        classification = self.feedback["evidence_classification"]
        self.assertEqual(classification["concrete_external_feedback_count"], 1)
        self.assertEqual(classification["directional_improvement_suggestion_count"], 1)
        self.assertFalse(classification["formal_user_test"])
        self.assertFalse(classification["co_design_established"])
        self.assertFalse(classification["pre_discussion_memo_workflow_validated"])
        self.assertFalse(classification["service_gap_validated"])
        separation = self.feedback["measurement_separation"]
        self.assertFalse(separation["used_as_bounded_measurement_input"])
        self.assertFalse(separation["used_to_create_or_modify_measurement_values"])

    def test_determinism_internal_only_boundaries_and_next_stage(self):
        first = bounded.render_dataset_json(bounded.build_dataset()).encode("utf-8")
        second = bounded.render_dataset_json(bounded.build_dataset()).encode("utf-8")
        self.assertEqual(first, second)
        self.assertEqual(first, bounded.OUTPUT_PATH.read_bytes())
        self.assertFalse((ROOT / "docs" / "data" / bounded.OUTPUT_PATH.name).exists())
        self.assertFalse(self.dataset["normalization_contract"]["municipality_allocation"])
        self.assertFalse(self.dataset["normalization_contract"]["municipality_geometry_filtering"])
        self.assertEqual(keys_named(self.dataset, "service_gap"), [])
        boundaries = "\n".join(self.dataset["global_boundaries"])
        self.assertIn("service_gapを判定しない", boundaries)
        self.assertIn("外部定性意見は測定入力", boundaries)
        next_stage = self.dataset["next_stage"]
        self.assertEqual(
            next_stage["task_id"],
            "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PRESENTATION-SPEC-1",
        )
        self.assertEqual(next_stage["status"], "DEFINED_NOT_STARTED")


if __name__ == "__main__":
    unittest.main()
