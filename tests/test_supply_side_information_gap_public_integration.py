from __future__ import annotations

from collections import Counter
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_supply_side_information_gap_public_data as public_data  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class SupplySideInformationGapPublicIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = public_data.build_dataset()
        cls.rows = cls.dataset["rows"]
        cls.integration_spec = load_json(
            ROOT / "data" / "work1_supply_side_information_gap_public_integration_spec.json"
        )
        cls.presentation = load_json(
            ROOT / "data" / "work1_supply_side_information_gap_presentation_spec.json"
        )
        cls.html = (ROOT / "docs" / "municipality-memo.html").read_text(encoding="utf-8")

    def test_identity_dimensions_and_public_status(self):
        self.assertEqual(self.dataset["schema_version"], public_data.SCHEMA_VERSION)
        self.assertEqual(self.dataset["task_id"], public_data.TASK_ID)
        self.assertEqual(self.dataset["published_data_as_of"], "2026-08-21")
        self.assertEqual(
            self.dataset["dimensions"],
            {
                "municipality_count": 19,
                "category_count": 8,
                "item_count_per_municipality": 35,
                "municipality_item_row_count": 665,
                "public_state_count": 6,
            },
        )

    def test_two_inputs_are_byte_and_hash_fixed(self):
        self.assertEqual(
            [item["path"] for item in self.dataset["generated_from"]],
            [public_data.PRESENTATION_PATH, public_data.INTEGRATION_SPEC_PATH],
        )
        for item in self.dataset["generated_from"]:
            payload = ROOT.joinpath(*item["path"].split("/")).read_bytes()
            self.assertEqual(item["bytes"], len(payload), item["path"])
            self.assertEqual(item["sha256"], hashlib.sha256(payload).hexdigest(), item["path"])

    def test_all_nineteen_municipalities_have_thirty_five_exact_rows(self):
        self.assertEqual(len(self.rows), 665)
        self.assertEqual(
            len({(row["municipality_code"], row["item_id"]) for row in self.rows}),
            665,
        )
        counts = Counter(row["municipality_code"] for row in self.rows)
        self.assertEqual(len(counts), 19)
        self.assertEqual(set(counts.values()), {35})
        self.assertTrue(all(tuple(row) == public_data.PUBLIC_ROW_FIELDS for row in self.rows))

    def test_six_states_map_one_to_one_with_exact_counts(self):
        source_counts = Counter(row["source_presentation_state"] for row in self.rows)
        public_counts = Counter(row["public_state"] for row in self.rows)
        self.assertEqual(dict(source_counts), self.integration_spec["state_counts"])
        self.assertEqual(set(public_counts), set(public_data.PUBLIC_STATE_MAP.values()))
        self.assertEqual(sum(public_counts.values()), 665)
        self.assertEqual(len(self.dataset["state_vocabulary"]), 6)

    def test_measured_rows_use_public_safe_copy_without_internal_ids_or_values(self):
        rows = [
            row for row in self.rows
            if row["public_state"] == "ACCEPTED_SOURCE_MEASURED_BOUNDED"
        ]
        self.assertEqual(len(rows), 61)
        self.assertTrue(
            all(row["display_explanation"] == public_data.MEASURED_PUBLIC_EXPLANATION for row in rows)
        )
        self.assertTrue(
            all(row["value_rendering_rule"] == public_data.MEASURED_PUBLIC_RENDERING_RULE for row in rows)
        )
        self.assertTrue(all("限定測定値は公開しません" in row["value_rendering_rule"] for row in rows))

    def test_prohibited_internal_fields_and_tokens_are_absent(self):
        serialized = json.dumps(self.dataset, ensure_ascii=False)
        for key in public_data.PROHIBITED_PUBLIC_KEYS:
            self.assertNotIn(f'"{key}"', serialized)
        for token in public_data.PROHIBITED_PUBLIC_TEXT:
            self.assertNotIn(token, serialized)
        self.assertNotIn("INTERNAL_ONLY_NOT_PUBLIC", serialized)

    def test_prohibited_state_assertions_are_explicitly_negated(self):
        for row in self.rows:
            boundary = row["claim_boundary"]
            denials = [
                f"「{assertion.removesuffix('。')}」とは主張しない。"
                for assertion in public_data.PROHIBITED_STATE_ASSERTIONS
                if f"「{assertion.removesuffix('。')}」とは主張しない。" in boundary
            ]
            self.assertEqual(len(denials), 1, (row["municipality"], row["item_id"]))
            for assertion in public_data.PROHIBITED_STATE_ASSERTIONS:
                self.assertNotIn(assertion, boundary)

    def test_information_conditions_reconcile_without_service_gap(self):
        counts = Counter(row["information_condition"] for row in self.rows)
        self.assertEqual(
            dict(counts),
            {
                "CONFIRMED_INFORMATION": 189,
                "MEASUREMENT_GAP": 37,
                "INFORMATION_GAP": 344,
                "DEMAND_COMPARATOR_REQUIRED": 95,
            },
        )
        self.assertNotIn("SERVICE_GAP", counts)
        self.assertTrue(all("value" not in row for row in self.rows))

    def test_municipality_summaries_reconcile_to_rows(self):
        summaries = self.dataset["municipality_summaries"]
        self.assertEqual(len(summaries), 19)
        for summary in summaries:
            rows = [row for row in self.rows if row["municipality_code"] == summary["municipality_code"]]
            public_counts = Counter(row["public_state"] for row in rows)
            condition_counts = Counter(row["information_condition"] for row in rows)
            self.assertEqual(
                {
                    state: public_counts[state]
                    for state in public_data.PUBLIC_STATE_MAP.values()
                },
                summary["public_state_counts"],
            )
            self.assertEqual(
                {
                    condition: condition_counts[condition]
                    for condition in (
                        "CONFIRMED_INFORMATION",
                        "MEASUREMENT_GAP",
                        "INFORMATION_GAP",
                        "DEMAND_COMPARATOR_REQUIRED",
                    )
                },
                summary["information_condition_counts"],
            )
            self.assertEqual(summary["next_confirmation_count"], condition_counts["MEASUREMENT_GAP"] + condition_counts["INFORMATION_GAP"])
            self.assertEqual(summary["demand_comparator_count"], condition_counts["DEMAND_COMPARATOR_REQUIRED"])

    def test_eight_categories_keep_the_model_order_and_counts(self):
        categories = self.dataset["categories"]
        self.assertEqual(len(categories), 8)
        self.assertEqual(
            [item["category_id"] for item in categories],
            [item["category_id"] for item in self.presentation["category_summaries"]],
        )
        self.assertEqual(sum(item["item_count_per_municipality"] for item in categories), 35)

    def test_global_boundaries_are_public_safe_and_prohibit_false_claims(self):
        boundaries = "\n".join(self.dataset["global_boundaries"])
        self.assertIn("情報の不足と交通サービスの不足", boundaries)
        self.assertIn("該当記載0件", boundaries)
        self.assertIn("フィード全体値", boundaries)
        self.assertIn("JRバス中国", boundaries)
        self.assertIn("service_gap", boundaries)
        self.assertNotIn("内部表示仕様", boundaries)
        self.assertNotIn("measurement_result_ids", boundaries)

    def test_saved_public_json_is_deterministic_and_within_size_limit(self):
        first = public_data.build_bytes()
        second = public_data.build_bytes()
        saved = (ROOT / "docs" / "data" / "work1_supply_side_information_gap.json").read_bytes()
        self.assertEqual(first, second)
        self.assertEqual(saved, first)
        self.assertLessEqual(len(saved), public_data.MAXIMUM_BYTES)
        self.assertTrue(saved.endswith(b"\n"))
        self.assertFalse(saved.endswith(b"\n\n"))

    def test_write_dataset_reproduces_saved_bytes(self):
        saved = (ROOT / "docs" / "data" / "work1_supply_side_information_gap.json").read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "public.json"
            public_data.write_dataset(output)
            self.assertEqual(output.read_bytes(), saved)

    def test_public_integration_section_uses_existing_selector_and_four_filters(self):
        self.assertIn('id="information-gap-section"', self.html)
        self.assertEqual(self.html.count('id="municipality-select"'), 1)
        self.assertIn("2. 確認できる情報と、次に必要な確認", self.html)
        self.assertEqual(self.html.count('class="gap-filter-button"'), 4)
        self.assertIn('data-gap-filter="NEXT_CONFIRMATION" aria-pressed="true"', self.html)
        self.assertIn('id="gap-results-status" aria-live="polite"', self.html)

    def test_public_section_has_three_summaries_six_state_legend_and_evidence_fields(self):
        self.assertEqual(self.html.count('class="gap-summary-card'), 3)
        self.assertIn('id="gap-legend-list"', self.html)
        self.assertIn('id="gap-category-container"', self.html)
        for label in ["受入原本ID", "証拠日", "原本範囲", "市町行の範囲", "次の確認", "非主張"]:
            self.assertIn(label, self.html)

    def test_required_boundary_and_registered_zero_copy_are_visible(self):
        self.assertIn(self.integration_spec["screen_contract"]["required_boundary_notice"], self.html)
        self.assertIn(self.integration_spec["screen_contract"]["registered_zero_notice"], self.html)

    def test_existing_memo_sections_are_preserved_and_renumbered(self):
        expected = [
            "3. 福祉有償運送・交通空白地有償運送の登録供給",
            "4. GTFSの公開確認状況",
            "5. 測定済みのGTFS指標",
            "6. この公開情報だけでは分からないこと",
            "7. 行政・事業者へ確認すること",
            "8. この確認を次の行動へつなぐ",
            "9. 読み方・限界・根拠",
        ]
        for heading in expected:
            self.assertIn(heading, self.html)
        for dom_id in ["registry-metrics", "feed-cards", "measured-metrics", "unknowns", "checklist", "handoff-section", "limits"]:
            self.assertIn(f'id="{dom_id}"', self.html)

    def test_existing_query_share_print_and_render_functions_remain(self):
        for fragment in [
            'url.searchParams.set("municipality", item.municipality)',
            "navigator.clipboard.writeText(shareUrl.value)",
            'printButton.addEventListener("click", () => window.print())',
            "renderRegistry(item)",
            "renderGtfs(gtfsRow)",
            "renderMeasuredMetrics(item, gtfsRow)",
        ]:
            self.assertIn(fragment, self.html)

    def test_new_public_json_is_loaded_and_rendered_with_the_existing_municipality(self):
        self.assertIn('informationGap: "data/work1_supply_side_information_gap.json"', self.html)
        self.assertIn("renderInformationGap(item.municipality)", self.html)
        self.assertIn("window.__WORK1_INFORMATION_GAP__", self.html)
        self.assertIn("state.informationGap", self.html)

    def test_no_javascript_fallback_links_to_public_json(self):
        self.assertIn("<noscript>", self.html)
        self.assertIn('href="data/work1_supply_side_information_gap.json"', self.html)
        self.assertIn("JavaScript", self.html)

    def test_three_other_public_pages_and_four_existing_json_inputs_remain_byte_fixed(self):
        protected = {
            item["path"]: item
            for item in self.integration_spec["input_files"]
            if item["path"] in {
                "docs/index.html",
                "docs/entry.html",
                "docs/status.html",
                "docs/data/municipal_supply.json",
                "docs/data/municipality_gtfs.json",
                "docs/data/gtfs_feeds.json",
                "docs/data/gtfs_supply_metrics.json",
            }
        }
        self.assertEqual(len(protected), 7)
        for path, record in protected.items():
            payload = ROOT.joinpath(*path.split("/")).read_bytes()
            self.assertEqual(len(payload), record["bytes"], path)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), record["sha256"], path)

    def test_disaster_prediction_dispatch_and_realtime_ai_are_not_added(self):
        for phrase in ["線状降水帯", "避難輸送モード", "避難開始を推奨", "Evacuation Window", "リアルタイムAI"]:
            self.assertNotIn(phrase, self.html)
            self.assertNotIn(phrase, json.dumps(self.dataset, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
