from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_supply_side_information_gap_public_integration_spec as integration  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class SupplySideInformationGapPublicIntegrationSpecTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = integration.build_dataset()
        cls.presentation = load_json(
            ROOT / "data" / "work1_supply_side_information_gap_presentation_spec.json"
        )
        cls.human_review = load_json(
            ROOT
            / "evidence"
            / "20260821_work1_supply_side_information_gap_internal_prototype_human_review.json"
        )

    def test_identity_and_status(self):
        schema_version = self.dataset["schema_version"]
        self.assertEqual(schema_version, integration.SCHEMA_VERSION)
        self.assertEqual(
            schema_version,
            "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PUBLIC-INTEGRATION-SPEC-1-SCHEMA-1",
        )
        self.assertEqual(self.dataset["task_id"], integration.TASK_ID)
        self.assertEqual(self.dataset["spec_as_of"], "2026-08-21")
        self.assertEqual(self.dataset["spec_status"], "DEFINED_NOT_IMPLEMENTED_PUBLICLY")

    def test_creator_review_closes_only_the_spec_gate(self):
        gate = self.dataset["creator_review_gate"]
        self.assertEqual(gate["decision"], "GO_TO_PUBLIC_INTEGRATION_SPEC")
        self.assertEqual(gate["reported_blocking_issue_count"], 0)
        self.assertEqual(gate["reported_revision_request_count"], 0)
        self.assertFalse(gate["formal_user_test"])
        self.assertFalse(gate["user_value_validation"])
        self.assertTrue(self.human_review["decision"]["creator_visual_acceptance"])
        self.assertFalse(self.human_review["decision"]["public_page_mutation_authorized"])

    def test_all_eleven_inputs_are_byte_and_hash_fixed(self):
        self.assertEqual(
            [item["path"] for item in self.dataset["input_files"]],
            list(integration.INPUT_PATHS),
        )
        self.assertEqual(len(self.dataset["input_files"]), 11)
        for item in self.dataset["input_files"]:
            if item["path"] == integration.IMPLEMENTATION_TARGET_PATH:
                self.assertEqual(item, integration.IMPLEMENTATION_TARGET_BASELINE)
                current_html = ROOT.joinpath(*item["path"].split("/")).read_text(
                    encoding="utf-8"
                )
                if hashlib.sha256(current_html.encode("utf-8")).hexdigest() != item["sha256"]:
                    self.assertIn('id="information-gap-section"', current_html)
                    self.assertTrue(
                        (ROOT / "docs" / "data" / "work1_supply_side_information_gap.json").is_file()
                    )
                continue
            payload = ROOT.joinpath(*item["path"].split("/")).read_bytes()
            self.assertEqual(item["bytes"], len(payload), item["path"])
            self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest(), item["path"])

    def test_dimensions_keep_nineteen_by_thirty_five_and_four_pages(self):
        self.assertEqual(
            self.dataset["dimensions"],
            {
                "municipality_count": 19,
                "category_count": 8,
                "item_count_per_municipality": 35,
                "municipality_item_row_count": 665,
                "source_state_count": 6,
                "public_state_count": 6,
                "existing_public_page_count": 4,
                "public_page_change_count": 1,
                "new_public_data_file_count": 1,
            },
        )

    def test_six_states_map_one_to_one_without_meaning_change(self):
        mappings = self.dataset["public_state_mapping"]
        self.assertEqual(len(mappings), 6)
        self.assertEqual(
            {row["source_state"] for row in mappings}, set(integration.PUBLIC_STATE_MAP)
        )
        self.assertEqual(
            {row["public_state"] for row in mappings}, set(integration.PUBLIC_STATE_MAP.values())
        )
        self.assertTrue(all(not row["meaning_changed"] for row in mappings))
        self.assertEqual(sum(row["row_count"] for row in mappings), 665)
        self.assertEqual(self.dataset["state_counts"], {
            "PUBLICLY_VISIBLE_CURRENT": 128,
            "MEASURED_BOUNDED_INTERNAL": 61,
            "MEASUREMENT_GAP_PARTIAL_SOURCE": 30,
            "MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED": 7,
            "INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED": 344,
            "DEMAND_COMPARATOR_REQUIRED": 95,
        })

    def test_information_conditions_reconcile_without_service_gap(self):
        self.assertEqual(
            self.dataset["information_condition_counts"],
            {
                "CONFIRMED_INFORMATION": 189,
                "MEASUREMENT_GAP": 37,
                "INFORMATION_GAP": 344,
                "DEMAND_COMPARATOR_REQUIRED": 95,
            },
        )
        self.assertNotIn("SERVICE_GAP", self.dataset["information_condition_counts"])
        self.assertFalse(self.dataset["claim_boundaries"]["information_or_measurement_gap_as_service_gap"])

    def test_integration_target_is_existing_preconsultation_memo(self):
        target = self.dataset["integration_target"]
        self.assertEqual(target["page"], "docs/municipality-memo.html")
        self.assertEqual(target["section_heading"], "2. 確認できる情報と、次に必要な確認")
        self.assertTrue(target["reuse_existing_municipality_selector"])
        self.assertEqual(target["default_filter"], "NEXT_CONFIRMATION")
        self.assertEqual(len(target["filter_order"]), 4)
        self.assertTrue(target["preserve_existing_registry_gtfs_metrics_unknowns_checklist_handoff_limits"])
        self.assertFalse(target["new_fifth_public_page"])
        self.assertEqual(
            self.dataset["unchanged_public_pages"],
            ["docs/index.html", "docs/entry.html", "docs/status.html"],
        )

    def test_public_json_schema_strips_internal_only_fields_and_values(self):
        contract = self.dataset["public_data_contract"]
        self.assertEqual(contract["row_count"], 665)
        self.assertEqual(tuple(contract["required_row_fields"]), integration.PUBLIC_ROW_FIELDS)
        self.assertEqual(tuple(contract["prohibited_row_fields"]), integration.PROHIBITED_PUBLIC_FIELDS)
        self.assertFalse(contract["measurement_values_copied"])
        self.assertFalse(contract["measurement_result_ids_published"])
        self.assertFalse(contract["detail_spec_ids_published"])
        self.assertFalse(contract["local_or_internal_paths_published"])
        self.assertLessEqual(contract["maximum_uncompressed_bytes"], 1_500_000)

    def test_existing_memo_behavior_and_four_page_navigation_are_preserved(self):
        contract = self.dataset["compatibility_contract"]
        self.assertEqual(contract["existing_query_parameter"], "municipality")
        self.assertTrue(contract["existing_share_url_behavior_preserved"])
        self.assertTrue(contract["existing_print_button_behavior_preserved"])
        self.assertTrue(contract["existing_four_page_navigation_preserved"])
        self.assertFalse(contract["existing_public_values_changed"])
        self.assertFalse(contract["existing_registered_supply_gtfs_and_metric_rendering_changed"])

    def test_accessibility_and_responsive_contracts_are_explicit(self):
        contract = self.dataset["interaction_and_accessibility"]
        self.assertTrue(contract["municipality_change_updates_existing_memo_and_new_section_together"])
        self.assertTrue(contract["filter_buttons_use_aria_pressed"])
        self.assertTrue(contract["result_count_uses_aria_live"])
        self.assertTrue(contract["state_not_conveyed_by_color_alone"])
        self.assertTrue(contract["keyboard_focus_visible"])
        self.assertGreaterEqual(contract["minimum_filter_target_height_px"], 42)
        self.assertFalse(contract["desktop_horizontal_overflow"])
        self.assertFalse(contract["smartphone_390_horizontal_overflow"])

    def test_registered_gtfs_jrbus_and_demand_boundaries_remain_negative(self):
        boundaries = self.dataset["claim_boundaries"]
        self.assertTrue(all(value is False for value in boundaries.values()))
        notice = self.dataset["screen_contract"]["required_boundary_notice"]
        self.assertIn("情報の不足", notice)
        self.assertIn("交通サービスの不足", notice)
        self.assertIn("該当記載0件", self.dataset["screen_contract"]["registered_zero_notice"])

    def test_external_disaster_proposal_is_not_adopted_into_current_scope(self):
        direction = self.dataset["scope_direction"]
        self.assertIn("移動を必要とする人との比較", direction["future_comparator_reference"])
        self.assertEqual(
            direction["not_integrated_now"],
            ["災害予測", "避難開始判断", "車両配車", "リアルタイムAI"],
        )
        self.assertFalse(self.dataset["claim_boundaries"]["external_suggestion_as_measurement_or_validation"])

    def test_public_mutation_and_deployment_remain_separate_human_gates(self):
        gates = self.dataset["approval_gates"]
        self.assertEqual(gates["public_page_mutation"]["status"], "HUMAN_APPROVAL_REQUIRED")
        self.assertEqual(
            gates["push_and_pages_update"]["status"],
            "SEPARATE_HUMAN_APPROVAL_REQUIRED",
        )
        self.assertEqual(
            self.dataset["next_stage"],
            {
                "task_id": "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PUBLIC-INTEGRATION-1",
                "status": "DEFINED_NOT_STARTED",
                "start_condition": "creator explicitly approves public page mutation after reviewing this specification",
            },
        )

    def test_implementation_allowlist_has_one_public_page_and_one_new_public_json(self):
        allowlist = self.dataset["implementation_change_allowlist"]
        public_pages = [path for path in allowlist if path.startswith("docs/") and path.endswith(".html")]
        public_json = [path for path in allowlist if path.startswith("docs/data/")]
        self.assertEqual(public_pages, ["docs/municipality-memo.html"])
        self.assertEqual(public_json, ["docs/data/work1_supply_side_information_gap.json"])
        self.assertIn("pushまたはPages更新", self.dataset["implementation_prohibitions"])

    def test_dataset_is_deterministic_and_saved_bytes_match(self):
        first = json.dumps(integration.build_dataset(), ensure_ascii=False, indent=2) + "\n"
        second = json.dumps(integration.build_dataset(), ensure_ascii=False, indent=2) + "\n"
        self.assertEqual(first.encode("utf-8"), second.encode("utf-8"))
        saved = (
            ROOT / "data" / "work1_supply_side_information_gap_public_integration_spec.json"
        ).read_bytes()
        self.assertEqual(saved, first.encode("utf-8"))
        self.assertTrue(saved.endswith(b"\n"))
        self.assertFalse(saved.endswith(b"\n\n"))

    def test_write_dataset_reproduces_saved_artifact(self):
        saved = (
            ROOT / "data" / "work1_supply_side_information_gap_public_integration_spec.json"
        ).read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "spec.json"
            integration.write_dataset(output)
            self.assertEqual(output.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
