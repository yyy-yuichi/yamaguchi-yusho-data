"""WORK1-SITE-CLARITY-BEFORE-USER-EVALUATION-CORRECTION-1 contracts."""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"


class SiteClarityContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = {
            name: (DOCS / name).read_text(encoding="utf-8")
            for name in (
                "index.html",
                "entry.html",
                "municipality-memo.html",
                "status.html",
            )
        }

    def test_all_four_pages_share_the_same_role_navigation(self):
        labels = (
            "1. データを見る",
            "2. 作品を知る",
            "3. 協議前メモ",
            "4. 検証を確かめる",
        )
        links = (
            'href="index.html"',
            'href="entry.html"',
            'href="municipality-memo.html"',
            'href="status.html"',
        )
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertIn('aria-label="このサイトの4ページ"', html)
                for label in labels:
                    self.assertIn(label, html)
                for link in links:
                    self.assertIn(link, html)

    def test_each_page_marks_its_current_role(self):
        expected = {
            "index.html": '<a href="index.html" aria-current="page">',
            "entry.html": '<a href="entry.html" aria-current="page">',
            "municipality-memo.html": '<a href="municipality-memo.html" aria-current="page">',
            "status.html": '<a href="status.html" aria-current="page">',
        }
        for name, marker in expected.items():
            with self.subTest(page=name):
                self.assertIn(marker, self.pages[name])

    def test_main_view_separates_basic_municipality_flow_from_analysis(self):
        html = self.pages["index.html"]
        details_start = html.index('<details id="advanced-analysis"')
        main_start = html.index('<main id="main"')
        details_end = html.index("</details>", details_start)
        self.assertLess(details_start, details_end)
        self.assertLess(details_end, main_start)
        details = html[details_start:details_end]
        self.assertIn("市町を選ぶ基本手順には必須ではありません", details)
        self.assertIn('id="supply-comparison"', details)
        self.assertIn('id="jrbus-supply-metric"', details)
        self.assertNotIn("<details id=\"advanced-analysis\" open", html)

    def test_direct_analysis_links_open_the_collapsed_analysis(self):
        html = self.pages["index.html"]
        for marker in (
            '"#supply-comparison"',
            '"#jrbus-supply-metric"',
            "advancedAnalysis.open = true",
            'window.addEventListener("hashchange", revealAdvancedAnalysis)',
        ):
            self.assertIn(marker, html)

    def test_entry_presents_three_basic_steps_and_optional_analysis(self):
        html = self.pages["entry.html"]
        steps_start = html.index('<ol class="steps">')
        steps_end = html.index("</ol>", steps_start)
        steps = html[steps_start:steps_end]
        self.assertEqual(steps.count("<li>"), 3)
        for marker in (
            "市町を選ぶ。",
            "現在の範囲と不足を確かめる。",
            "協議前の確認メモにする。",
        ):
            self.assertIn(marker, steps)
        self.assertIn('<details class="optional-analysis">', html)
        self.assertIn("全市町に共通する必須手順ではありません", html)

    def test_status_page_puts_beginner_summary_before_technical_history(self):
        html = self.pages["status.html"]
        summary = html.index('id="reader-status"')
        technical = html.index('<details class="technical-record">')
        internal = html.index("WORK1-SITE-CLARITY-BEFORE-USER-EVALUATION-CORRECTION-1")
        self.assertLess(summary, technical)
        self.assertLess(technical, internal)
        for marker in (
            "現在使えるもの",
            "確認していること",
            "まだ分からないこと",
            "開発・検証の詳しい記録を開く",
        ):
            self.assertIn(marker, html)

    def test_clarity_changes_do_not_remove_why_or_memo_unknowns(self):
        why = "自家用車に頼れない人も、地域で通学・通院・買物などの生活を続けられる交通"
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertIn(why, html)
        memo = self.pages["municipality-memo.html"]
        self.assertIn("5. この公開情報だけでは分からないこと", memo)
        self.assertIn("6. 行政・事業者へ確認すること", memo)


if __name__ == "__main__":
    unittest.main()
