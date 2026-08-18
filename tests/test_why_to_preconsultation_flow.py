"""WORK1-WHY-TO-PRECONSULTATION-FLOW-CORRECTION-1 acceptance tests."""
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"
WHY = "自家用車に頼れない人も、地域で通学・通院・買物などの生活を続けられる交通になっているかを確かめたい"


class WhyToPreconsultationFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (DOCS / "index.html").read_text(encoding="utf-8")
        cls.entry = (DOCS / "entry.html").read_text(encoding="utf-8")
        cls.memo = (DOCS / "municipality-memo.html").read_text(encoding="utf-8")
        cls.status = (DOCS / "status.html").read_text(encoding="utf-8")

    def test_ultimate_why_and_current_first_stage_are_public(self):
        for name, html in {
            "index": self.index,
            "entry": self.entry,
            "memo": self.memo,
            "status": self.status,
        }.items():
            self.assertIn(WHY, html, name)
            self.assertIn("第一段階", html, name)

    def test_main_page_has_a_visible_municipality_call_to_action(self):
        self.assertIn('id="municipality-cta"', self.index)
        self.assertIn('href="#municipality-select"', self.index)
        self.assertIn("市町を選んで確認する", self.index)
        self.assertIn(".primary-action", self.index)

    def test_gtfs_explanation_uses_the_selected_rows_check_date(self):
        self.assertIn('id="gtfs-check-date"', self.index)
        self.assertIn('setText("gtfs-check-date", row.checked_at || "要再確認")', self.index)
        self.assertNotIn("確認日 2026-08-09）。GTFS本体のダウンロード・認証・解析は行っていません", self.index)
        self.assertIn("受入・安全確認・解析済み", self.index)
        self.assertIn("認証が必要、一般配布なし、現在取得不能の原本は取得していません", self.index)

    def test_memo_separates_unknowns_from_questions(self):
        for identifier in ("unknowns-title", "unknowns", "checklist-title", "checklist"):
            self.assertIn(f'id="{identifier}"', self.memo)
        self.assertIn("5. この公開情報だけでは分からないこと", self.memo)
        self.assertIn("6. 行政・事業者へ確認すること", self.memo)
        self.assertIn("function renderUnknowns(item, gtfsRow)", self.memo)
        self.assertIn("renderUnknowns(item, gtfsRow);", self.memo)
        self.assertLess(self.memo.index("renderUnknowns(item, gtfsRow);"), self.memo.index("renderChecklist(item, gtfsRow);"))

    def test_unknowns_cover_registry_gtfs_and_metric_branches(self):
        for marker in (
            "登録簿上0件だけから、地域の交通手段や移動支援が存在しないとは分かりません",
            "現在の運行状況や予約可能性までは分かりません",
            "認証後の原本内容と利用可能な範囲は、まだ分かりません",
            "一般配布の可否、提供条件、現在の内容は、まだ分かりません",
            "現行の配布先、復旧時期、現在の内容は、まだ分かりません",
            "市町内だけの供給量や、通学・通院・買物に足りるかは分かりません",
            "予定便などの供給指標は、まだ測定できていません",
        ):
            self.assertIn(marker, self.memo)

    def test_memo_step_order_is_explicit(self):
        headings = (
            "1. いま確認できる範囲",
            "2. 福祉有償運送・交通空白地有償運送の登録供給",
            "3. GTFSの公開確認状況",
            "4. 測定済みのGTFS指標",
            "5. この公開情報だけでは分からないこと",
            "6. 行政・事業者へ確認すること",
            "7. この確認を次の行動へつなぐ",
            "8. 読み方・限界・根拠",
        )
        positions = [self.memo.index(heading) for heading in headings]
        self.assertEqual(positions, sorted(positions))


if __name__ == "__main__":
    unittest.main()
