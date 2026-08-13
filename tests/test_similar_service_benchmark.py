import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = REPO_ROOT / "evidence" / "20260813_work1_similar_service_benchmark_research.json"
ENTRY_PATH = REPO_ROOT / "docs" / "entry.html"
STATUS_PATH = REPO_ROOT / "docs" / "status.html"


class SimilarServiceBenchmarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        cls.entry = ENTRY_PATH.read_text(encoding="utf-8")
        cls.status = STATUS_PATH.read_text(encoding="utf-8")

    def test_three_comparators_cover_the_selected_pipeline_roles(self):
        comparators = self.evidence["comparators"]
        self.assertEqual(3, len(comparators))
        self.assertEqual(
            {
                "gtfs_data_repository": "discover_and_obtain_gtfs",
                "gtfs_go": "visualize_and_aggregate_gtfs",
                "links_mobilys": "analyze_and_test_planning_scenarios",
            },
            {item["comparator_id"]: item["pipeline_role"] for item in comparators},
        )

    def test_six_primary_sources_are_current_https_and_first_party(self):
        sources = [
            source
            for comparator in self.evidence["comparators"]
            for source in comparator["primary_sources"]
        ]
        self.assertEqual(6, len(sources))
        for source in sources:
            self.assertEqual("2026-08-13", source["verified_at"])
            self.assertTrue(source["url"].startswith("https://"), source)
            self.assertTrue(source["publisher"], source)
            self.assertTrue(source["supports"], source)

    def test_work1_boundary_and_non_claims_are_explicit(self):
        self.assertEqual("WORK1", self.evidence["work_id"])
        self.assertEqual(0, self.evidence["selection_policy"]["other_work_input_count"])
        self.assertEqual(6, len(self.evidence["comparison_axes"]))
        limits = "\n".join(self.evidence["synthesis"]["limits"])
        for marker in ("uniqueness", "superiority", "national completeness", "scorecard is unchanged"):
            self.assertIn(marker, limits)

    def test_entry_publishes_roles_sources_and_limits_without_scores(self):
        for marker in (
            'id="benchmark-title"',
            "既存のGTFS関連ツールと比べた役割",
            "GTFSデータリポジトリ",
            "GTFS-GO",
            "LINKS Mobilys",
            "優劣を決めるランキングではなく",
            "存在しないとは判断していません",
            "代替するものではありません",
            "国内唯一・網羅・優位とは主張しません",
        ):
            self.assertIn(marker, self.entry)
        for url in (
            "https://gtfs-data.jp/",
            "https://docs.gtfs-data.jp/api.v2.html",
            "https://qgis.mierune.co.jp/posts/howto_plugin_gtfsgo",
            "https://github.com/MIERUNE/GTFS-GO",
            "https://www.mlit.go.jp/commmmons/document/008/",
            "https://www.mlit.go.jp/commmmons/document/008/commmmons_doc_008_ver01.pdf",
        ):
            self.assertIn(f'href="{url}"', self.entry)
        for marker in ("総合比較指数70.0", "実用度3.5", "work1_award_scorecard.json"):
            self.assertNotIn(marker, self.entry)

    def test_public_external_sources_use_safe_link_attributes(self):
        benchmark = self.entry.split('id="benchmark-title"', 1)[1].split("</section>", 1)[0]
        self.assertEqual(6, benchmark.count('target="_blank" rel="noopener noreferrer"'))

    def test_status_records_the_completed_stage_and_next_read_only_audit(self):
        for marker in (
            "WORK1-SIMILAR-SERVICE-BENCHMARK-1",
            "一次資料6件・公開説明・最終受入済み",
            "WORK1-SIMILAR-SERVICE-BENCHMARK-AUDIT-1",
            "次のread-only監査・未着手",
        ):
            self.assertIn(marker, self.status)
        self.assertNotIn("比較スコアカードは公開済み", self.status)


if __name__ == "__main__":
    unittest.main()
