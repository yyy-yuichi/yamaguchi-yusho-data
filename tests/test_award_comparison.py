from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_DATA_DIR = DOCS_DIR / "data"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def round_to_half(value: float) -> float:
    return float((Decimal(str(value)) * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2)


class AwardComparisonContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = read_json(DATA_DIR / "award_scorecard_schema.json")
        cls.scorecard = read_json(DATA_DIR / "work1_award_scorecard.json")
        cls.html = (DOCS_DIR / "award-comparison.html").read_text(encoding="utf-8")
        cls.status_html = (DOCS_DIR / "status.html").read_text(encoding="utf-8")

    def test_public_json_copies_are_byte_identical(self):
        for filename in ("award_scorecard_schema.json", "work1_award_scorecard.json"):
            self.assertEqual(
                (DATA_DIR / filename).read_bytes(),
                (DOCS_DATA_DIR / filename).read_bytes(),
                f"docs/data/{filename} がdata/{filename}と一致しない",
            )

    def test_schema_declares_internal_not_official_scale(self):
        self.assertEqual("1.0.0", self.scorecard["schema_version"])
        self.assertEqual(0.0, self.scorecard["scoring_method"]["scale_min"])
        self.assertEqual(5.0, self.scorecard["scoring_method"]["scale_max"])
        self.assertEqual(0.5, self.scorecard["scoring_method"]["step"])
        self.assertIs(False, self.scorecard["scoring_method"]["official_score"])
        self.assertIs(False, self.scorecard["official_source"]["numeric_weights_published"])
        self.assertEqual(
            "https://yyy-yuichi.github.io/yamaguchi-yusho-data/data/award_scorecard_schema.json",
            self.schema["$id"],
        )

    def test_official_source_and_2026_classification_are_fixed(self):
        source = self.scorecard["official_source"]
        self.assertEqual("https://urbandata-challenge.jp/udc2026_entry", source["url"])
        self.assertEqual("2026-06-20", source["page_updated_at"])
        self.assertEqual("2026-08-12", source["verified_at"])
        classification = self.scorecard["classification"]
        self.assertEqual("アプリケーション", classification["work_type"])
        self.assertEqual("道路・交通", classification["theme"])
        self.assertIs(True, classification["priority_field"])

    def test_criteria_and_subcriteria_sets_are_complete(self):
        criteria = {item["criterion_id"]: item for item in self.scorecard["criteria"]}
        self.assertEqual({"utility", "completeness", "challenge"}, set(criteria))
        self.assertEqual(
            {"problem_value_clarity", "method_fit", "user_value_evidence"},
            {item["subcriterion_id"] for item in criteria["utility"]["subcriteria"]},
        )
        self.assertEqual(
            {"public_implementation", "reproducibility_verifiability", "scope_reliability"},
            {item["subcriterion_id"] for item in criteria["completeness"]["subcriteria"]},
        )
        self.assertEqual(
            {"novelty", "output_comprehensiveness", "continuity", "actor_diversity"},
            {item["subcriterion_id"] for item in criteria["challenge"]["subcriteria"]},
        )

    def test_scores_are_half_steps_and_recompute_from_subcriteria(self):
        for criterion in self.scorecard["criteria"]:
            self.assertIsNone(criterion["official_weight"])
            self.assertAlmostEqual(1 / 3, criterion["comparison_weight"])
            scores = [item["score"] for item in criterion["subcriteria"]]
            for score in [criterion["score"], *scores]:
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 5)
                self.assertEqual(score * 2, int(score * 2))
            self.assertEqual(round_to_half(sum(scores) / len(scores)), criterion["score"])

    def test_overall_index_recomputes_from_equal_criteria(self):
        scores = [item["score"] for item in self.scorecard["criteria"]]
        expected = round(sum(scores) / len(scores) / 5 * 100, 1)
        self.assertEqual(expected, self.scorecard["overall"]["comparison_index"])
        self.assertEqual(70.0, expected)

    def test_comparison2_updates_only_supported_scores_and_scope_counts(self):
        self.assertEqual(
            "work1-award-comparison-2-2026-08-12",
            self.scorecard["scorecard_id"],
        )
        criteria = {item["criterion_id"]: item for item in self.scorecard["criteria"]}
        self.assertEqual(
            {"utility": 3.5, "completeness": 4.0, "challenge": 3.0},
            {key: value["score"] for key, value in criteria.items()},
        )
        utility = {
            item["subcriterion_id"]: item
            for item in criteria["utility"]["subcriteria"]
        }
        self.assertEqual(4.0, utility["problem_value_clarity"]["score"])
        self.assertEqual(4.5, utility["method_fit"]["score"])
        self.assertEqual(2.0, utility["user_value_evidence"]["score"])

        encoded = json.dumps(self.scorecard, ensure_ascii=False)
        for marker in (
            "municipality-memo.html",
            "関連確認6/19市町",
            "未確認13/19市町",
            "関連実測表示3市町",
            "実測2フィード",
            "総合比較値70.0は据え置く",
        ):
            self.assertIn(marker, encoded)

    def test_every_score_has_public_evidence_confidence_and_missing_evidence(self):
        scored_items = []
        for criterion in self.scorecard["criteria"]:
            scored_items.append(criterion)
            scored_items.extend(criterion["subcriteria"])
        for item in scored_items:
            self.assertIn(item["confidence"], {"high", "medium", "low"})
            self.assertEqual("2026-08-12", item["as_of"])
            self.assertTrue(item["rationale"].strip())
            self.assertTrue(item["evidence"])
            self.assertTrue(item["missing_evidence"])
            for evidence in item["evidence"]:
                parsed = urlparse(evidence["url"])
                self.assertEqual("https", parsed.scheme)
                allowed = (
                    parsed.netloc == "urbandata-challenge.jp"
                    and parsed.path == "/udc2026_entry"
                ) or (
                    parsed.netloc == "yyy-yuichi.github.io"
                    and parsed.path.startswith("/yamaguchi-yusho-data/")
                ) or (
                    parsed.netloc == "github.com"
                    and parsed.path.startswith("/yyy-yuichi/yamaguchi-yusho-data")
                )
                self.assertTrue(allowed, evidence["url"])
                self.assertEqual("2026-08-12", evidence["as_of"])

    def test_special_award_statuses_match_2026_rules(self):
        awards = {item["award_id"]: item["status"] for item in self.scorecard["special_awards"]}
        self.assertEqual(
            {
                "gtfs": "eligible",
                "bodik": "condition_unmet",
                "datakids": "not_claimed",
                "jacic": "not_listed_2026",
            },
            awards,
        )
        for award in self.scorecard["special_awards"]:
            self.assertTrue(award["evidence"])
            self.assertTrue(award["next_gate"].strip())

    def test_top_three_improvements_are_ranked_and_verifiable(self):
        improvements = self.scorecard["top_improvements"]
        self.assertEqual([1, 2, 3], [item["priority"] for item in improvements])
        self.assertEqual(
            [
                "remote_user_evaluation",
                "similar_service_benchmark",
                "independent_reproduction_drill",
            ],
            [item["improvement_id"] for item in improvements],
        )
        self.assertEqual(
            [True, False, False],
            [item["external_dependency"] for item in improvements],
        )
        self.assertEqual(3, len({item["improvement_id"] for item in improvements}))
        for item in improvements:
            low, high = item["expected_index_gain_range"]
            self.assertGreaterEqual(low, 0)
            self.assertGreaterEqual(high, low)
            self.assertTrue(item["target_subcriteria"])
            self.assertTrue(item["acceptance_evidence"])

    def test_other_work_is_not_an_input_and_human_owns_decision(self):
        boundary = self.scorecard["evidence_boundary"]
        self.assertEqual("WORK1", self.scorecard["work_id"])
        self.assertEqual(0, boundary["other_work_input_count"])
        self.assertEqual("human", boundary["decision_owner"])
        self.assertEqual("yyy-yuichi/yamaguchi-yusho-data", boundary["repository_id"])

    def test_public_page_loads_json_and_uses_safe_dom_api(self):
        for marker in (
            'const scorecardUrl = "data/work1_award_scorecard.json"',
            "fetch(scorecardUrl",
            "renderScorecard",
            "textContent",
            "document.createElement",
            "window.__awardRuntimeErrors = runtimeErrors",
            "WORK1-AWARD-COMPARISON-2",
            "増えた証拠と、点数を据え置いた理由",
            "総合比較指数70.0は据え置きます",
            "人間承認ゲート",
            "自力実行可能",
            "公式点・順位・受賞確率ではありません",
            "他作品のパス、URL、ファイル、Git履歴、公開物、得点は入力していません",
        ):
            self.assertIn(marker, self.html)
        self.assertNotIn("innerHTML", self.html)
        self.assertNotIn(">70.0<", self.html)
        self.assertNotIn(">3.5 / 5<", self.html)

    def test_status_uses_continuous_improvement_not_finite_submission_countdown(self):
        for marker in (
            "公開基盤を保持して受賞品質を継続改善",
            "WORK1-AWARD-COMPARISON-2",
            "WORK1-AWARD-COMPARISON-2 公開・最終受入済み",
            "WORK1-AWARD-COMPARISON-AUDIT-2",
            "独立した人間承認ゲート",
        ):
            self.assertIn(marker, self.status_html)
        for stale in (
            "9 / 10",
            "9 / 10完了",
            "10工程中9工程",
            "残る工程08は外部提出",
            "公開適用待ち",
        ):
            self.assertNotIn(stale, self.status_html)

    def test_navigation_links_are_present_on_public_entry_points(self):
        for path in (REPO_ROOT / "README.md", DOCS_DIR / "entry.html", DOCS_DIR / "status.html"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("award-comparison.html", text, str(path))
        work_scope = (REPO_ROOT / "WORK_SCOPE.md").read_text(encoding="utf-8")
        self.assertIn("award-comparison.html", work_scope)


if __name__ == "__main__":
    unittest.main()
