from __future__ import annotations

from collections import Counter
import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_supply_side_information_gap_presentation_spec as presentation  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def row_key(row):
    return row["municipality_code"], row["item_id"]


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


class SupplySideInformationGapPresentationSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = presentation.build_dataset()
        cls.rows = cls.dataset["municipality_item_presentation_specs"]
        cls.matrix = load_json(
            ROOT / "data" / "work1_supply_side_information_coverage_matrix.json"
        )
        cls.measurement = load_json(
            ROOT / "data" / "work1_supply_side_accepted_source_bounded_measurement.json"
        )
        cls.feedback = load_json(
            ROOT
            / "evidence"
            / "20260820_work1_udc_yamaguchi_coordinator_qualitative_feedback.json"
        )

    def test_identity_dimensions_and_internal_status(self):
        self.assertEqual(self.dataset["schema_version"], presentation.SCHEMA_VERSION)
        self.assertEqual(self.dataset["task_id"], presentation.TASK_ID)
        self.assertEqual(self.dataset["spec_as_of"], "2026-08-20")
        self.assertEqual(
            self.dataset["spec_status"],
            "DEFINED_INTERNAL_NOT_IMPLEMENTED_PUBLICLY",
        )
        self.assertEqual(
            self.dataset["dimensions"],
            {
                "municipality_count": 19,
                "category_count": 8,
                "item_count_per_municipality": 35,
                "municipality_item_row_count": 665,
                "presentation_state_count": 6,
                "measured_detail_spec_count": 8,
                "input_file_count": 4,
            },
        )

    def test_four_inputs_are_byte_and_hash_fixed(self):
        inputs = self.dataset["input_files"]
        self.assertEqual([item["path"] for item in inputs], list(presentation.INPUT_PATHS))
        for item in inputs:
            payload = ROOT.joinpath(*item["path"].split("/")).read_bytes()
            self.assertEqual(item["bytes"], len(payload), item["path"])
            self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest(), item["path"])

    def test_all_nineteen_municipalities_have_thirty_five_closed_rows(self):
        self.assertEqual(len(self.rows), 665)
        self.assertEqual(len({row_key(row) for row in self.rows}), 665)
        counts = Counter(row["municipality_code"] for row in self.rows)
        self.assertEqual(len(counts), 19)
        self.assertEqual(set(counts.values()), {35})
        required_fields = tuple(self.dataset["required_row_fields"])
        self.assertEqual(required_fields, presentation.REQUIRED_ROW_FIELDS)
        self.assertTrue(all(tuple(row) == required_fields for row in self.rows))

    def test_six_presentation_states_have_exact_counts(self):
        counts = Counter(row["presentation_state"] for row in self.rows)
        self.assertEqual(dict(counts), presentation.EXPECTED_STATE_COUNTS)
        vocabulary = {
            item["code"]: item for item in self.dataset["presentation_state_vocabulary"]
        }
        self.assertEqual(set(vocabulary), set(presentation.EXPECTED_STATE_COUNTS))
        self.assertTrue(all(item["short_label"] for item in vocabulary.values()))
        self.assertTrue(all(item["prohibited_statement"] for item in vocabulary.values()))

    def test_information_conditions_reconcile_without_service_gap_state(self):
        self.assertEqual(
            self.dataset["information_condition_counts"],
            {
                "CONFIRMED_INFORMATION": 189,
                "MEASUREMENT_GAP": 37,
                "INFORMATION_GAP": 344,
                "DEMAND_COMPARATOR_REQUIRED": 95,
            },
        )
        conditions = {row["information_condition"] for row in self.rows}
        self.assertNotIn("SERVICE_GAP", conditions)
        self.assertEqual(keys_named(self.dataset, "service_gap"), [])

    def test_visible_and_measured_information_remain_publicly_distinct(self):
        visible = [
            row for row in self.rows
            if row["presentation_state"] == presentation.PUBLICLY_VISIBLE_CURRENT
        ]
        measured = [
            row for row in self.rows
            if row["presentation_state"] == presentation.MEASURED_BOUNDED_INTERNAL
        ]
        self.assertEqual(len(visible), 128)
        self.assertEqual(len(measured), 61)
        self.assertTrue(all(row["public_visibility"] == "CURRENTLY_PUBLIC" for row in visible))
        self.assertTrue(
            all(row["public_visibility"] == "INTERNAL_ONLY_NOT_PUBLIC" for row in measured)
        )
        self.assertTrue(all(row["measurement_status"] is None for row in visible))
        self.assertTrue(
            all(row["measurement_status"] == "MEASURED_BOUNDED" for row in measured)
        )

    def test_the_ninety_eight_upstream_measurement_gaps_resolve_to_61_30_7(self):
        upstream = {
            row_key(row)
            for row in self.matrix["rows"]
            if row["current_status"] == "ACCEPTED_SOURCE_UNMEASURED"
        }
        measured = {
            row_key(row)
            for row in self.rows
            if row["presentation_state"] == presentation.MEASURED_BOUNDED_INTERNAL
        }
        partial = {
            row_key(row)
            for row in self.rows
            if row["presentation_state"] == presentation.MEASUREMENT_GAP_PARTIAL_SOURCE
        }
        additional = {
            row_key(row)
            for row in self.rows
            if row["presentation_state"]
            == presentation.MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED
        }
        self.assertEqual(len(upstream), 98)
        self.assertEqual((len(measured), len(partial), len(additional)), (61, 30, 7))
        self.assertEqual(upstream, measured | partial | additional)
        self.assertFalse(measured & partial)
        self.assertFalse(measured & additional)
        self.assertFalse(partial & additional)

    def test_measurement_gap_rows_render_status_only_without_fake_zero(self):
        gap_rows = [
            row for row in self.rows if row["information_condition"] == "MEASUREMENT_GAP"
        ]
        self.assertEqual(len(gap_rows), 37)
        self.assertTrue(all(row["measurement_status"] is None for row in gap_rows))
        self.assertTrue(all(row["measurement_result_ids"] == [] for row in gap_rows))
        self.assertTrue(all(row["detail_spec_id"] is None for row in gap_rows))
        self.assertTrue(all("0件・0%" in row["value_rendering_rule"] for row in gap_rows))
        self.assertTrue(all(row["display_explanation"] for row in gap_rows))

    def test_information_gap_rows_match_upstream_additional_source_rows(self):
        expected = {
            row_key(row)
            for row in self.matrix["rows"]
            if row["current_status"] == "ADDITIONAL_SOURCE_REQUIRED"
        }
        actual = {
            row_key(row)
            for row in self.rows
            if row["presentation_state"]
            == presentation.INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED
        }
        self.assertEqual(len(actual), 344)
        self.assertEqual(actual, expected)
        self.assertTrue(
            all(
                row["accepted_source_ids"] == []
                for row in self.rows
                if row_key(row) in actual
            )
        )

    def test_demand_comparator_is_separate_and_does_not_decide_sufficiency(self):
        rows = [
            row for row in self.rows
            if row["presentation_state"] == presentation.DEMAND_COMPARATOR_REQUIRED
        ]
        self.assertEqual(len(rows), 95)
        self.assertEqual({row["category_id"] for row in rows}, {"C8_DEMAND_AND_ACTIVITY_COMPARATOR"})
        self.assertTrue(all(row["measurement_result_ids"] == [] for row in rows))
        self.assertTrue(all("充足・不足の判定値を作らない" in row["value_rendering_rule"] for row in rows))

    def test_eight_detail_specs_cover_every_measured_row_and_result_reference(self):
        detail_specs = self.dataset["measured_detail_presentation_specs"]
        by_id = {item["detail_spec_id"]: item for item in detail_specs}
        by_item = {item["item_id"]: item for item in detail_specs}
        self.assertEqual(len(by_id), 8)
        self.assertEqual(len(by_item), 8)
        result_ids = {
            result["measurement_result_id"]
            for result in self.measurement["measurement_results"]
        }
        measured_rows = [
            row for row in self.rows
            if row["presentation_state"] == presentation.MEASURED_BOUNDED_INTERNAL
        ]
        for row in measured_rows:
            self.assertIn(row["detail_spec_id"], by_id)
            self.assertEqual(by_id[row["detail_spec_id"]]["item_id"], row["item_id"])
            self.assertTrue(row["measurement_result_ids"])
            self.assertTrue(set(row["measurement_result_ids"]) <= result_ids)
        self.assertEqual({row["item_id"] for row in measured_rows}, set(by_item))

    def test_gtfs_and_jrbus_scope_boundaries_are_not_municipal_allocations(self):
        measured_gtfs = [
            row for row in self.rows
            if row["presentation_state"] == presentation.MEASURED_BOUNDED_INTERNAL
            and row["item_id"] in presentation.GTFS_MEASURED_ITEMS
        ]
        self.assertEqual(len(measured_gtfs), 42)
        self.assertTrue(all("フィード全体" in row["source_scope_note"] for row in measured_gtfs))
        self.assertTrue(all("市町内配賦は未実施" in row["source_scope_note"] for row in measured_gtfs))
        jrbus_rows = [
            row for row in measured_gtfs
            if "jrbus-chugoku-gtfs" in row["accepted_source_ids"]
        ]
        self.assertEqual(len(jrbus_rows), 24)
        self.assertTrue(all("関係4市へ配賦しない" in row["claim_boundary"] for row in jrbus_rows))

    def test_screen_copy_zero_and_accessibility_contracts_prevent_misreading(self):
        screen = self.dataset["screen_contract"]
        self.assertEqual(screen["page_title"], "確認できる情報と、次に必要な確認")
        self.assertEqual(screen["default_summary_order"][0]["section_id"], "NEXT_CONFIRMATION")
        self.assertIn("claim_boundary", screen["evidence_drawer_fields"])
        self.assertTrue(any("色だけ" in item for item in screen["accessibility"]))
        copy = self.dataset["copy_contract"]
        self.assertIn("交通が足りない", copy["prohibited_unqualified_phrases"])
        self.assertIn("情報の不足と交通サービスの不足", copy["required_distinction"])
        zero = self.dataset["zero_and_missing_value_contract"]
        self.assertEqual(zero["registered_zero_label"], "4登録簿上の該当記載0件")
        self.assertIn("不存在を意味しない", zero["registered_zero_boundary"])

    def test_municipality_and_category_summaries_reconcile_to_rows(self):
        municipalities = self.dataset["municipality_summaries"]
        self.assertEqual(len(municipalities), 19)
        self.assertTrue(all(item["item_count"] == 35 for item in municipalities))
        for item in municipalities:
            self.assertEqual(sum(item["presentation_state_counts"].values()), 35)
            conditions = item["information_condition_counts"]
            self.assertEqual(sum(conditions.values()), 35)
            self.assertEqual(
                item["next_confirmation_count"],
                conditions["MEASUREMENT_GAP"] + conditions["INFORMATION_GAP"],
            )
        categories = self.dataset["category_summaries"]
        self.assertEqual(len(categories), 8)
        self.assertEqual(sum(item["row_count"] for item in categories), 665)
        self.assertTrue(all(item["row_count"] % 19 == 0 for item in categories))

    def test_external_feedback_is_direction_only_not_measurement_or_validation(self):
        direction = self.dataset["external_feedback_direction"]
        self.assertEqual(direction["concrete_external_feedback_count"], 1)
        self.assertEqual(direction["directional_improvement_suggestion_count"], 1)
        self.assertEqual(direction["used_for_direction"], "何が不足しているかを明確にする表示方向")
        for key in (
            "used_to_assign_row_states",
            "measurement_input",
            "formal_user_test_result",
            "co_design_result",
            "user_value_validation",
            "service_gap_validation",
        ):
            self.assertFalse(direction[key], key)
        feedback_bytes = (
            ROOT
            / "evidence"
            / "20260820_work1_udc_yamaguchi_coordinator_qualitative_feedback.json"
        ).read_bytes()
        self.assertEqual(direction["sha256"], hashlib.sha256(feedback_bytes).hexdigest())

    def test_determinism_internal_only_gate_and_next_stage(self):
        first = presentation.render_dataset_json(presentation.build_dataset()).encode("utf-8")
        second = presentation.render_dataset_json(presentation.build_dataset()).encode("utf-8")
        self.assertEqual(first, second)
        self.assertEqual(first, presentation.OUTPUT_PATH.read_bytes())
        self.assertFalse((ROOT / "docs" / "data" / presentation.OUTPUT_PATH.name).exists())
        gate = self.dataset["publication_gate"]
        self.assertEqual(gate["public_files_changed_by_this_stage"], [])
        self.assertFalse(gate["docs_data_copy_created"])
        self.assertEqual(gate["public_implementation_status"], "NOT_STARTED")
        self.assertTrue(gate["human_approval_required_before_public_change"])
        next_stage = self.dataset["next_stage"]
        self.assertEqual(
            next_stage["task_id"],
            "WORK1-SUPPLY-SIDE-INFORMATION-GAP-INTERNAL-PROTOTYPE-1",
        )
        self.assertEqual(next_stage["status"], "DEFINED_NOT_STARTED")


if __name__ == "__main__":
    unittest.main()
