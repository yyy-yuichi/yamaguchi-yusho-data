import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MEMO_PATH = REPO_ROOT / "docs" / "municipality-memo.html"
DOCS_DATA = REPO_ROOT / "docs" / "data"


class PreconsultationHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = MEMO_PATH.read_text(encoding="utf-8")
        cls.supply = json.loads((DOCS_DATA / "municipal_supply.json").read_text(encoding="utf-8"))
        cls.gtfs = json.loads((DOCS_DATA / "municipality_gtfs.json").read_text(encoding="utf-8"))
        cls.metrics = json.loads((DOCS_DATA / "gtfs_supply_metrics.json").read_text(encoding="utf-8"))

    def test_all_19_municipalities_have_registry_and_four_state_gtfs_combinations(self):
        supply_by_name = {row["municipality"]: row for row in self.supply["municipalities"]}
        gtfs_by_name = {row["municipality"]: row for row in self.gtfs}
        self.assertEqual(19, len(supply_by_name))
        self.assertEqual(set(supply_by_name), set(gtfs_by_name))
        counts = {}
        for name, supply in supply_by_name.items():
            state = (
                "registered" if supply["operator_count"] > 0 else "no-registry",
                gtfs_by_name[name]["availability_status"],
            )
            counts[state] = counts.get(state, 0) + 1
        self.assertEqual({
            ("registered", "public_download_confirmed"): 6,
            ("no-registry", "public_download_confirmed"): 1,
            ("no-registry", "authentication_required"): 2,
            ("registered", "not_publicly_distributed"): 8,
            ("no-registry", "not_publicly_distributed"): 1,
            ("registered", "official_resource_unavailable"): 1,
        }, counts)

    def test_handoff_section_and_runtime_state_contract(self):
        for identifier in (
            "handoff-section", "handoff-summary", "handoff-facts",
            "handoff-next", "handoff-tools", "handoff-boundary",
        ):
            self.assertIn(f'id="{identifier}"', self.html)
        for marker in (
            "6. この確認を次の行動へつなぐ", "このメモで共有する", "次に確認する",
            "分析へ渡す条件", "renderHandoff(item, gtfsRow)", "root.dataset.handoffState",
            "root.dataset.hasMetrics", "public_download_confirmed", "authentication_required",
            "not_publicly_distributed", "official_resource_unavailable",
        ):
            self.assertIn(marker, self.html)

    def test_nonclaims_and_manual_boundary_are_explicit(self):
        for marker in (
            "交通手段、移動支援、別制度の不存在を意味しません",
            "公開原本があるようには扱いません",
            "フィード全体の値で、市町内供給や利便性の評価ではありません",
            "この画面は外部サービスへデータを自動送信しません",
            "必要な場合だけ手動で次の工程へ渡します",
        ):
            self.assertIn(marker, self.html)
        self.assertNotIn('fetch("https://', self.html)

    def test_downstream_links_are_stable_https_and_safe(self):
        for url in (
            "https://gtfs-data.jp/",
            "https://qgis.mierune.co.jp/posts/howto_plugin_gtfsgo",
            "https://www.mlit.go.jp/commmmons/document/008/",
        ):
            self.assertIn(url, self.html)
        self.assertNotIn("https://docs.gtfs-data.jp/api.v2.html", self.html)
        self.assertIn('link.target = "_blank"', self.html)
        self.assertIn('link.rel = "noopener noreferrer"', self.html)

    def test_measured_metrics_remain_a_separate_attribute(self):
        measured_feed_ids = {row["feed_id"] for row in self.metrics}
        self.assertEqual({"iwakuni-gtfsjp", "hikari-gtfs"}, measured_feed_ids)
        self.assertIn("const hasMetrics = state.metrics.some", self.html)
        self.assertIn('root.dataset.hasMetrics = String(hasMetrics)', self.html)
        self.assertIn("値を補完・推定しません", self.html)

    def test_share_print_and_existing_navigation_are_preserved(self):
        for marker in (
            'id="share-url"', 'id="copy-button"', 'id="print-button"',
            'id="detail-link"', "window.history.replaceState", "window.print()",
            '.handoff-card a::after', 'content: " (" attr(href) ")"',
        ):
            self.assertIn(marker, self.html)


if __name__ == "__main__":
    unittest.main()
