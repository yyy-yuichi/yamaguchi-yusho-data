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

    def test_reproduction_evidence_updates_continuity_without_overclaim(self):
        self.assertEqual("2026-08-19", self.scorecard["evaluation_as_of"])
        completeness = {
            item["subcriterion_id"]: item
            for item in self.criteria["completeness"]["subcriteria"]
        }
        reproducibility = completeness["reproducibility_verifiability"]
        self.assertEqual(4.5, reproducibility["score"])
        self.assertIn("完全byte一致", reproducibility["rationale"])
        self.assertIn("人間による実行ではない", reproducibility["rationale"])
        self.assertTrue(
            any(
                "第三者再現記録" in item
                for item in reproducibility["missing_evidence"]
            )
        )
        challenge = {
            item["subcriterion_id"]: item
            for item in self.criteria["challenge"]["subcriteria"]
        }
        continuity = challenge["continuity"]
        self.assertEqual(4.5, continuity["score"])
        self.assertIn("依存版固定", continuity["rationale"])
        self.assertIn("欠損からの復旧", continuity["rationale"])
        evidence_urls = [item["url"] for item in continuity["evidence"]]
        self.assertIn(
            "https://github.com/yyy-yuichi/yamaguchi-yusho-data/actions/runs/32069876975",
            evidence_urls,
        )

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

    def test_accessibility_audit_is_recorded_without_score_inflation(self):
        utility = {
            item["subcriterion_id"]: item
            for item in self.criteria["utility"]["subcriteria"]
        }
        completeness = {
            item["subcriterion_id"]: item
            for item in self.criteria["completeness"]["subcriteria"]
        }
        method_fit = utility["method_fit"]
        public_implementation = completeness["public_implementation"]
        self.assertEqual(4.5, method_fit["score"])
        self.assertEqual(4.5, public_implementation["score"])
        self.assertIn("操作アクセシビリティ監査", method_fit["rationale"])
        self.assertIn("支援技術利用者の受入ではない", public_implementation["rationale"])
        audit_name = "20260819_work1_operability_accessibility_audit.json"
        self.assertTrue(
            any(audit_name in item["url"] for item in method_fit["evidence"])
        )
        self.assertTrue(
            any(audit_name in item["url"] for item in public_implementation["evidence"])
        )
        self.assertTrue((REPO_ROOT / "evidence" / audit_name).is_file())

    def test_completed_work_is_replaced_by_ranked_remaining_actions(self):
        improvements = self.scorecard["top_improvements"]
        self.assertEqual(
            [
                "site_clarity_before_user_evaluation",
                "remote_user_evaluation",
                "remaining_public_gtfs_supply_measurement",
            ],
            [item["improvement_id"] for item in improvements],
        )
        self.assertEqual([False, True, True], [item["external_dependency"] for item in improvements])
        completed = [
            "similar_service_benchmark",
            "official_gtfs_coverage_extension",
            "jrbus_supply_metrics_extension",
            "independent_reproduction_drill",
            "accessibility_task_audit",
        ]
        self.assertTrue(
            all(item not in [action["improvement_id"] for action in improvements] for item in completed)
        )
        clarity = improvements[0]
        remote = improvements[1]
        self.assertEqual([0.0, 0.0], clarity["expected_index_gain_range"])
        self.assertIn("利用者テスト依頼0", " ".join(clarity["acceptance_evidence"]))
        self.assertIn("開始承認", " ".join(clarity["acceptance_evidence"]))
        self.assertIn("HUMAN_GATE_PENDING", remote["why"])
        self.assertIn("資料作成・連絡・依頼を行わず", remote["why"])

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
