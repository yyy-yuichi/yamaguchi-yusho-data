from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import build_supply_side_information_gap_internal_prototype as prototype  # noqa: E402


EXPECTED_STATES = {
    "PUBLICLY_VISIBLE_CURRENT": 128,
    "MEASURED_BOUNDED_INTERNAL": 61,
    "MEASUREMENT_GAP_PARTIAL_SOURCE": 30,
    "MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED": 7,
    "INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED": 344,
    "DEMAND_COMPARATOR_REQUIRED": 95,
}


class StructureParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = Counter()
        self.ids = set()
        self.script_srcs = []
        self.link_hrefs = []

    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(attributes["id"])
        if tag == "script" and attributes.get("src"):
            self.script_srcs.append(attributes["src"])
        if tag == "link" and attributes.get("href"):
            self.link_hrefs.append(attributes["href"])


def embedded_data(html):
    match = re.search(
        r'<script id="prototype-data" type="application/json">(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    if not match:
        raise AssertionError("prototype data script not found")
    return json.loads(match.group(1))


class SupplySideInformationGapInternalPrototypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specification = json.loads(
            (ROOT / prototype.INPUT_PATH).read_text(encoding="utf-8")
        )
        cls.prototype_data = prototype.build_prototype_data(cls.specification)
        cls.html = prototype.OUTPUT_PATH.read_text(encoding="utf-8")
        cls.embedded = embedded_data(cls.html)
        cls.parser = StructureParser()
        cls.parser.feed(cls.html)

    def test_identity_status_dimensions_and_input_hash(self):
        data = self.prototype_data
        self.assertEqual(data["task_id"], prototype.TASK_ID)
        self.assertEqual(data["prototype_as_of"], "2026-08-20")
        self.assertEqual(data["prototype_status"], "LOCAL_ONLY_NOT_PUBLIC")
        self.assertEqual(
            data["dimensions"],
            {
                "municipality_count": 19,
                "category_count": 8,
                "item_count_per_municipality": 35,
                "row_count": 665,
                "state_count": 6,
            },
        )
        payload = (ROOT / prototype.INPUT_PATH).read_bytes()
        self.assertEqual(data["input_file"]["bytes"], len(payload))
        self.assertEqual(
            data["input_file"]["sha256"], hashlib.sha256(payload).hexdigest()
        )

    def test_saved_html_contains_exact_embedded_prototype_data(self):
        self.assertEqual(self.embedded, self.prototype_data)
        self.assertEqual(self.embedded["prototype_contract"]["network_dependencies"], 0)
        self.assertEqual(self.embedded["prototype_contract"]["public_files_changed"], 0)
        self.assertEqual(self.embedded["prototype_contract"]["measurement_values_copied"], 0)

    def test_all_nineteen_municipalities_have_thirty_five_unique_rows(self):
        rows = self.embedded["rows"]
        self.assertEqual(len(rows), 665)
        self.assertEqual(
            len({(row["municipality_code"], row["item_id"]) for row in rows}),
            665,
        )
        municipality_counts = Counter(row["municipality_code"] for row in rows)
        self.assertEqual(len(municipality_counts), 19)
        self.assertEqual(set(municipality_counts.values()), {35})
        self.assertEqual(len(self.embedded["municipalities"]), 19)

    def test_six_state_counts_are_preserved_without_reclassification(self):
        counts = Counter(row["presentation_state"] for row in self.embedded["rows"])
        self.assertEqual(dict(counts), EXPECTED_STATES)
        self.assertEqual(
            {state["code"] for state in self.embedded["states"]},
            set(EXPECTED_STATES),
        )

    def test_municipality_summaries_reconcile_to_thirty_five(self):
        summaries = self.embedded["municipality_summaries"]
        self.assertEqual(len(summaries), 19)
        for summary in summaries:
            conditions = summary["information_condition_counts"]
            self.assertEqual(sum(conditions.values()), 35)
            self.assertEqual(
                summary["next_confirmation_count"],
                conditions["MEASUREMENT_GAP"] + conditions["INFORMATION_GAP"],
            )
            self.assertEqual(
                summary["demand_comparator_count"],
                conditions["DEMAND_COMPARATOR_REQUIRED"],
            )

    def test_internal_heading_and_information_service_boundary_are_visible(self):
        self.assertIn("作品①・ローカル内部プロトタイプ｜公開ページではありません", self.html)
        self.assertIn("確認できる情報と、次に必要な確認", self.html)
        self.assertIn("情報の不足と、現実の交通サービスの不足は別です", self.html)
        self.assertIn("この画面だけで交通の充足・不足は判断しません", self.html)
        self.assertIn('content="noindex,nofollow,noarchive"', self.html)

    def test_default_filter_prioritizes_next_confirmation(self):
        contract = self.embedded["prototype_contract"]
        self.assertEqual(contract["default_filter"], "NEXT_CONFIRMATION")
        self.assertEqual(
            contract["available_filters"],
            [
                "NEXT_CONFIRMATION",
                "CONFIRMED_INFORMATION",
                "DEMAND_COMPARATOR_REQUIRED",
                "ALL",
            ],
        )
        self.assertIn('data-filter="NEXT_CONFIRMATION" aria-pressed="true"', self.html)
        self.assertIn('data-filter="ALL" aria-pressed="false"', self.html)

    def test_self_contained_html_has_no_network_dependency(self):
        lower = self.html.lower()
        self.assertNotRegex(lower, r"https?://")
        self.assertEqual(self.parser.script_srcs, [])
        self.assertEqual(self.parser.link_hrefs, [])
        for network_api in ("fetch(", "xmlhttprequest", "websocket(", "eventsource("):
            self.assertNotIn(network_api, lower)

    def test_accessible_controls_status_and_details_are_present(self):
        self.assertIn('<html lang="ja">', self.html)
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1"', self.html)
        self.assertIn('<label class="field-label" for="municipality-select">', self.html)
        self.assertIn('role="group" aria-labelledby="filter-label"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn("状態は色だけ", " ".join(self.specification["screen_contract"]["accessibility"]))
        self.assertIn("根拠・日付・範囲・次の確認を見る", self.html)
        self.assertGreaterEqual(self.parser.tags["button"], 4)
        self.assertIn("municipality-select", self.parser.ids)
        self.assertIn("results-status", self.parser.ids)

    def test_evidence_disclosure_contains_all_required_fields(self):
        required = set(self.specification["screen_contract"]["evidence_drawer_fields"])
        self.assertEqual(
            required,
            {
                "accepted_source_ids",
                "evidence_date",
                "source_scope_note",
                "scope_note",
                "next_confirmation",
                "claim_boundary",
            },
        )
        for label in (
            "受入原本ID",
            "証拠日",
            "範囲",
            "次の確認",
            "表示ルール",
            "非主張",
            "内部詳細仕様",
            "内部測定result",
        ):
            self.assertIn(label, self.html)

    def test_responsive_contract_covers_tablet_and_phone_widths(self):
        self.assertEqual(
            self.embedded["prototype_contract"]["responsive_breakpoints_px"],
            [720, 390],
        )
        self.assertIn("@media (max-width: 720px)", self.html)
        self.assertIn("@media (max-width: 390px)", self.html)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", self.html)
        self.assertIn("overflow-wrap: anywhere", self.html)
        self.assertIn("width: min(100% - 20px, 1180px)", self.html)

    def test_public_and_internal_measured_rows_remain_distinct(self):
        rows = self.embedded["rows"]
        public = [row for row in rows if row["presentation_state"] == "PUBLICLY_VISIBLE_CURRENT"]
        measured = [row for row in rows if row["presentation_state"] == "MEASURED_BOUNDED_INTERNAL"]
        self.assertEqual((len(public), len(measured)), (128, 61))
        self.assertTrue(all(row["public_visibility"] == "CURRENTLY_PUBLIC" for row in public))
        self.assertTrue(
            all(row["public_visibility"] == "INTERNAL_ONLY_NOT_PUBLIC" for row in measured)
        )
        self.assertTrue(all(not row["measurement_result_ids"] for row in public))
        self.assertTrue(all(row["measurement_result_ids"] for row in measured))

    def test_gap_rows_show_status_without_fake_zero_or_measurement_results(self):
        gap_rows = [
            row
            for row in self.embedded["rows"]
            if row["information_condition"] in {"MEASUREMENT_GAP", "INFORMATION_GAP"}
        ]
        self.assertEqual(len(gap_rows), 381)
        self.assertTrue(all(row["measurement_result_ids"] == [] for row in gap_rows))
        self.assertTrue(all(row["detail_spec_id"] is None for row in gap_rows))
        self.assertTrue(all("0件・0%" in row["value_rendering_rule"] for row in gap_rows))

    def test_registered_zero_is_qualified_and_not_transport_absence(self):
        contract = self.embedded["zero_and_missing_value_contract"]
        self.assertEqual(contract["registered_zero_label"], "4登録簿上の該当記載0件")
        self.assertIn("不存在を意味しない", contract["registered_zero_boundary"])
        self.assertIn("4登録簿上の該当記載0件", self.html)
        self.assertIn("交通手段・移動支援・別制度がないことを意味しません", self.html)

    def test_gtfs_and_jrbus_rows_keep_feed_wide_nonallocation_boundaries(self):
        gtfs_items = {
            "route_identity_and_name",
            "stop_name_and_coordinates",
            "route_shape",
            "service_calendar",
            "stop_level_timetable",
            "time_band_frequency",
        }
        gtfs_rows = [
            row
            for row in self.embedded["rows"]
            if row["presentation_state"] == "MEASURED_BOUNDED_INTERNAL"
            and row["item_id"] in gtfs_items
        ]
        self.assertEqual(len(gtfs_rows), 42)
        self.assertTrue(all("フィード全体" in row["source_scope_note"] for row in gtfs_rows))
        jrbus_rows = [
            row for row in gtfs_rows if "jrbus-chugoku-gtfs" in row["accepted_source_ids"]
        ]
        self.assertEqual(len(jrbus_rows), 24)
        self.assertTrue(all("関係4市へ配賦しない" in row["claim_boundary"] for row in jrbus_rows))

    def test_no_service_gap_decision_or_deep_motivation_content_is_created(self):
        self.assertEqual(self.embedded["prototype_contract"]["service_gap_decisions"], 0)
        self.assertNotIn("SERVICE_GAP", {row["information_condition"] for row in self.embedded["rows"]})
        self.assertIn("service_gapを自動判定しない", " ".join(self.embedded["global_boundaries"]))
        self.assertNotIn("deeper_motivation", self.html)

    def test_browser_readback_hook_reports_selected_filter_and_visible_count(self):
        self.assertIn("window.__WORK1_PROTOTYPE__", self.html)
        self.assertIn("get activeFilter()", self.html)
        self.assertIn("get selectedMunicipalityCode()", self.html)
        self.assertIn("get visibleItemCount()", self.html)

    def test_deterministic_output_and_public_isolation(self):
        first = prototype.build_html().encode("utf-8")
        second = prototype.build_html().encode("utf-8")
        self.assertEqual(first, second)
        self.assertEqual(first, prototype.OUTPUT_PATH.read_bytes())
        self.assertTrue(prototype.OUTPUT_PATH.is_relative_to(ROOT / "internal"))
        self.assertFalse((ROOT / "docs" / prototype.OUTPUT_PATH.name).exists())
        self.assertFalse((ROOT / "docs" / "data" / prototype.OUTPUT_PATH.name).exists())


if __name__ == "__main__":
    unittest.main()
