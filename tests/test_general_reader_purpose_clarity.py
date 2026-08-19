"""WORK1-GENERAL-READER-PURPOSE-CLARITY-CORRECTION-1 contracts."""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"


class GeneralReaderPurposeClarityContractTest(unittest.TestCase):
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

    def test_all_four_pages_lead_with_the_same_plain_purpose_bridge(self):
        markers = (
            "このサイトがしたいこと",
            "自家用車に頼れない人も、地域で通学・通院・買物などの生活を続けられる交通になっているかを確かめたい。",
            "市町の担当者、交通事業者、地域で活動する人",
            "最初の相談を始める準備に使います",
            "市町を選ぶと",
            "まだ分からないこと",
            "行政や交通事業者へ尋ねること",
        )
        for name, html in self.pages.items():
            with self.subTest(page=name):
                self.assertEqual(html.count('id="general-reader-purpose"'), 1)
                purpose = html.index('id="general-reader-purpose"')
                self.assertLess(html.index("<h1"), purpose)
                for marker in markers:
                    self.assertIn(marker, html[purpose:])

    def test_data_terms_are_explained_as_consultation_clues(self):
        markers = (
            "自治体やNPOなどの登録団体・登録車両",
            "GTFSというデータに入ったバスなどの予定時刻・乗降場所",
            "このサイトだけで決めるものではありません",
        )
        for name, html in self.pages.items():
            with self.subTest(page=name):
                purpose = html.index('id="general-reader-purpose"')
                purpose_end = html.index("</div>", purpose)
                purpose_html = html[purpose:purpose_end]
                for marker in markers:
                    self.assertIn(marker, purpose_html)

    def test_plain_purpose_precedes_first_specialist_explanation(self):
        specialist_markers = {
            "index.html": "Official GTFS / GTFS-JP coverage check",
            "entry.html": "静的Webアプリ",
            "municipality-memo.html": "福祉有償運送",
            "status.html": "福祉有償運送",
        }
        for name, marker in specialist_markers.items():
            with self.subTest(page=name):
                html = self.pages[name]
                self.assertLess(html.index('id="general-reader-purpose"'), html.index(marker))

    def test_status_beginner_summary_precedes_progress_metrics_and_history(self):
        html = self.pages["status.html"]
        summary = html.index('id="reader-status"')
        metrics = html.index('aria-label="主要な進捗数値"')
        technical = html.index('<details class="technical-record">')
        self.assertLess(summary, metrics)
        self.assertLess(metrics, technical)

    def test_existing_action_flow_and_unknowns_remain_present(self):
        index = self.pages["index.html"]
        memo = self.pages["municipality-memo.html"]
        self.assertIn("市町を選んで確認する", index)
        self.assertIn("5. この公開情報だけでは分からないこと", memo)
        self.assertIn("6. 行政・事業者へ確認すること", memo)
        self.assertIn("7. この確認を次の行動へつなぐ", memo)
        self.assertIn("8. 読み方・限界・根拠", memo)


if __name__ == "__main__":
    unittest.main()
