"""WORK1-TASK-MEMO-1: public-data-only municipal meeting memo acceptance tests."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DOCS_DATA_DIR = DOCS_DIR / "data"
MEMO_PATH = DOCS_DIR / "municipality-memo.html"


def read_json(name: str):
    return json.loads((DOCS_DATA_DIR / name).read_text(encoding="utf-8"))


class TaskMemoPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = MEMO_PATH.read_text(encoding="utf-8")

    def test_page_has_memo_structure_and_navigation(self):
        self.assertIn("市町別 交通協議前確認メモ", self.html)
        for identifier in (
            "municipality-select", "memo", "summary-grid", "registry-metrics",
            "feed-cards", "measured-metrics", "checklist", "limits", "source-links",
        ):
            self.assertIn(f'id="{identifier}"', self.html)
        for target in ("index.html", "entry.html", "status.html"):
            self.assertIn(f'href="{target}"', self.html)

    def test_page_loads_only_the_four_accepted_public_json_inputs(self):
        json_paths = re.findall(r'\b(?:supply|municipalityGtfs|feeds|metrics): "([^"]+\.json)"', self.html)
        self.assertEqual(
            json_paths,
            [
                "data/municipal_supply.json",
                "data/municipality_gtfs.json",
                "data/gtfs_feeds.json",
                "data/gtfs_supply_metrics.json",
            ],
        )
        self.assertNotIn("raw/", self.html)

    def test_page_does_not_hardcode_municipality_or_metric_values(self):
        supply = read_json("municipal_supply.json")
        for row in supply["municipalities"]:
            self.assertNotIn(row["municipality"], self.html)
        for row in read_json("gtfs_supply_metrics.json"):
            self.assertNotIn(row["feed_id"], self.html)
            for metric in row["metrics"].values():
                self.assertNotIn(f">{metric['value']}<", self.html)

    def test_page_uses_safe_dom_construction(self):
        for forbidden in ("innerHTML", "outerHTML", "document.write", "eval("):
            self.assertNotIn(forbidden, self.html)
        self.assertIn("textContent", self.html)
        self.assertIn("createElement", self.html)
        self.assertIn("replaceChildren", self.html)

    def test_query_parameter_has_exact_match_and_safe_default(self):
        self.assertIn('searchParams.get("municipality")', self.html)
        self.assertIn("some(row => row.municipality === requested)", self.html)
        self.assertIn("state.supply.municipalities[0].municipality", self.html)
        self.assertIn('searchParams.set("municipality", item.municipality)', self.html)
        self.assertIn("window.history.replaceState", self.html)

    def test_copy_print_and_manual_share_fallback_are_wired(self):
        self.assertIn('id="share-url" type="text" readonly', self.html)
        self.assertIn("navigator.clipboard.writeText", self.html)
        self.assertIn("window.print()", self.html)
        self.assertIn("自動コピーできませんでした", self.html)
        self.assertIn("@media print", self.html)
        self.assertIn(".no-print", self.html)

    def test_states_and_limits_do_not_claim_absence_or_rank(self):
        for required in (
            "確認範囲では未確認", "不存在を意味しません", "0件をサービス不存在と解釈しない",
            "市町値を足して県計にしない", "値を推定せず", "利便性の順位ではありません",
        ):
            self.assertIn(required, self.html)

    def test_related_feed_metrics_are_selected_by_feed_id(self):
        self.assertIn("function renderMeasuredMetrics(item, gtfsRow)", self.html)
        self.assertIn("const associatedFeedIds = new Set(feedIds(gtfsRow));", self.html)
        self.assertIn("associatedFeedIds.has(row.feed_id)", self.html)
        self.assertNotIn("state.metrics.filter(row => row.municipality === item.municipality)", self.html)

    def test_all_external_links_are_restricted_to_https(self):
        self.assertIn('url.startsWith("https://")', self.html)
        self.assertIn('link.rel = "noopener noreferrer"', self.html)
        self.assertIn("#page=${operator.source_page}", self.html)
        self.assertNotRegex(self.html, r'href="http://')

    def test_runtime_and_loading_failures_are_isolated(self):
        self.assertIn("window.__taskMemoRuntimeErrors", self.html)
        self.assertIn('id="load-error"', self.html)
        self.assertIn("Promise.all", self.html)
        for filename in (
            "municipal_supply.json", "municipality_gtfs.json", "gtfs_feeds.json",
            "gtfs_supply_metrics.json",
        ):
            self.assertGreaterEqual(self.html.count(filename), 1)


class TaskMemoDataContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.supply = read_json("municipal_supply.json")
        cls.gtfs = read_json("municipality_gtfs.json")
        cls.feeds = read_json("gtfs_feeds.json")
        cls.metrics = read_json("gtfs_supply_metrics.json")

    def test_all_municipalities_have_exactly_one_gtfs_status(self):
        supply_names = [row["municipality"] for row in self.supply["municipalities"]]
        gtfs_names = [row["municipality"] for row in self.gtfs]
        self.assertEqual(len(supply_names), 19)
        self.assertEqual(len(gtfs_names), 19)
        self.assertEqual(len(set(gtfs_names)), 19)
        self.assertEqual(set(supply_names), set(gtfs_names))

    def test_feed_and_metric_references_resolve(self):
        feed_ids = {row["feed_id"] for row in self.feeds}
        for row in self.gtfs:
            for feed_id in filter(None, row["feed_ids"].split(";")):
                self.assertIn(feed_id, feed_ids)
        for row in self.metrics:
            self.assertIn(row["feed_id"], feed_ids)
            self.assertIn(row["municipality"], {item["municipality"] for item in self.supply["municipalities"]})

    def test_representative_acceptance_branches_exist_in_public_data(self):
        supply_by_name = {row["municipality"]: row for row in self.supply["municipalities"]}
        gtfs_by_name = {row["municipality"]: row for row in self.gtfs}
        metric_names = {row["municipality"] for row in self.metrics}

        self.assertGreater(supply_by_name["下関市"]["operator_count"], 0)
        self.assertEqual(gtfs_by_name["下関市"]["availability_status"], "not_confirmed_in_checked_sources")
        self.assertEqual(supply_by_name["宇部市"]["operator_count"], 0)
        self.assertEqual(gtfs_by_name["宇部市"]["availability_status"], "confirmed")
        self.assertNotIn("宇部市", metric_names)
        self.assertGreater(supply_by_name["岩国市"]["operator_count"], 0)
        self.assertEqual(gtfs_by_name["岩国市"]["availability_status"], "confirmed")
        self.assertIn("岩国市", metric_names)

        shunan = gtfs_by_name["周南市"]
        self.assertEqual(shunan["availability_status"], "confirmed")
        self.assertEqual(shunan["feed_ids"], "hikari-gtfs")
        self.assertNotIn("周南市", metric_names, "実測レコードを市町別に複製してはいけない")
        self.assertIn("hikari-gtfs", {row["feed_id"] for row in self.metrics})


class TaskMemoEntryPointTest(unittest.TestCase):
    def test_main_view_links_selected_municipality_to_memo(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="memo-link"', html)
        self.assertIn('new URL("municipality-memo.html", window.location.href)', html)
        self.assertIn('memoUrl.searchParams.set("municipality", item.municipality)', html)

    def test_public_explanation_status_and_scope_link_the_memo(self):
        for path in (
            DOCS_DIR / "entry.html", DOCS_DIR / "status.html",
            REPO_ROOT / "README.md", REPO_ROOT / "WORK_SCOPE.md",
        ):
            content = path.read_text(encoding="utf-8")
            self.assertIn("municipality-memo", content, str(path))
        self.assertIn("WORK1-TASK-MEMO-1", (REPO_ROOT / "WORK_SCOPE.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
