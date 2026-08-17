import hashlib
import json
import re
import unittest
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCORECARD_PATH = REPO_ROOT / "data" / "work1_award_scorecard.json"
ATTESTATION_PATH = REPO_ROOT / "src" / "build_release_attestation.py"


def round_half(value: float) -> float:
    return float(
        (Decimal(str(value)) * 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 2
    )


class AwardScorecardRecalibrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scorecard = json.loads(SCORECARD_PATH.read_text(encoding="utf-8"))
        cls.criteria = {
            item["criterion_id"]: item for item in cls.scorecard["criteria"]
        }

    def test_recalibration_date_and_supported_score_change(self):
        self.assertEqual("2026-08-17", self.scorecard["evaluation_as_of"])
        challenge = {
            item["subcriterion_id"]: item
            for item in self.criteria["challenge"]["subcriteria"]
        }
        novelty = challenge["novelty"]
        self.assertEqual(4.0, novelty["score"])
        self.assertIn("国内3サービス・6一次資料", novelty["rationale"])
        self.assertIn("唯一性は主張しない", novelty["rationale"])
        output = challenge["output_comprehensiveness"]
        self.assertEqual(4.0, output["score"])
        self.assertIn("広域1フィードを条件分離して独立表示", output["rationale"])
        self.assertNotIn("採用済みJRバス中国GTFSの供給指標化", output["missing_evidence"])

    def test_criteria_and_overall_stay_recomputable_without_score_inflation(self):
        for criterion in self.criteria.values():
            sub_scores = [item["score"] for item in criterion["subcriteria"]]
            self.assertEqual(round_half(sum(sub_scores) / len(sub_scores)), criterion["score"])
        self.assertEqual(
            {"utility": 3.5, "completeness": 4.5, "challenge": 3.5},
            {key: value["score"] for key, value in self.criteria.items()},
        )
        self.assertEqual(76.7, self.scorecard["overall"]["comparison_index"])

    def test_missing_user_and_actor_evidence_remain_unscored(self):
        utility = {
            item["subcriterion_id"]: item
            for item in self.criteria["utility"]["subcriteria"]
        }
        challenge = {
            item["subcriterion_id"]: item
            for item in self.criteria["challenge"]["subcriteria"]
        }
        self.assertEqual(2.0, utility["user_value_evidence"]["score"])
        self.assertEqual(1.0, challenge["actor_diversity"]["score"])
        self.assertIn("利用者本人による評価", utility["user_value_evidence"]["rationale"])
        self.assertIn("参加した公開証拠はない", challenge["actor_diversity"]["rationale"])

    def test_completed_benchmark_is_replaced_by_ranked_remaining_actions(self):
        improvements = self.scorecard["top_improvements"]
        self.assertEqual(
            [
                "remote_user_evaluation",
                "independent_reproduction_drill",
                "remaining_public_gtfs_supply_measurement",
            ],
            [item["improvement_id"] for item in improvements],
        )
        self.assertEqual([True, False, True], [item["external_dependency"] for item in improvements])
        completed = [
            "similar_service_benchmark",
            "official_gtfs_coverage_extension",
            "jrbus_supply_metrics_extension",
        ]
        self.assertTrue(
            all(item not in [action["improvement_id"] for action in improvements] for item in completed)
        )

    def test_internal_scores_and_json_stay_out_of_pages(self):
        self.assertFalse((REPO_ROOT / "docs" / "award-comparison.html").exists())
        self.assertFalse((REPO_ROOT / "docs" / "data" / SCORECARD_PATH.name).exists())
        self.assertFalse((REPO_ROOT / "docs" / "data" / "award_scorecard_schema.json").exists())
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPO_ROOT / "docs").glob("*.html")
        )
        for marker in ("実用度3.5", "完成度4.5", "挑戦度3.5", "総合比較指数76.7", SCORECARD_PATH.name):
            self.assertNotIn(marker, combined)

    def test_release_attestation_protects_the_current_internal_scorecard(self):
        digest = hashlib.sha256(SCORECARD_PATH.read_bytes()).hexdigest()
        source = ATTESTATION_PATH.read_text(encoding="utf-8")
        match = re.search(
            r'"data/work1_award_scorecard\.json": "([0-9a-f]{64})"', source
        )
        self.assertIsNotNone(match)
        self.assertEqual(digest, match.group(1))


if __name__ == "__main__":
    unittest.main()
