"""I-2 static municipal supply view: build outputs and acceptance invariants."""
from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import build_gtfs_status  # noqa: E402
import build_site_data  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_DATA_DIR = DOCS_DIR / "data"

# I-5完了時点の実測テスト件数（tests/test_site.py + tests/test_verify.py）。
# `python -m unittest discover -s tests -v` の実測値と一致させる
# （README.md・docs/status.html・verification.mdでも同じ値を使う。SPEC.md §13.6.6）。
TOTAL_TEST_COUNT = 67


def setUpModule():
    build_site_data.main()
    build_gtfs_status.main()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class PublishedSourceDataTest(unittest.TestCase):
    def test_published_source_json_is_byte_identical(self):
        for filename in ("operators.json", "vehicles.json"):
            self.assertEqual(
                (DATA_DIR / filename).read_bytes(),
                (DOCS_DATA_DIR / filename).read_bytes(),
                f"docs/data/{filename} が検証済みdata/{filename}と一致しない",
            )

    def test_public_json_has_no_representative_schema(self):
        suspicious = ("代表者", "氏名", "representative", "daihyo")
        for filename in ("operators.json", "vehicles.json", "municipal_supply.json"):
            data = read_json(DOCS_DATA_DIR / filename)
            keys = set()

            def collect(value):
                if isinstance(value, dict):
                    keys.update(value)
                    for child in value.values():
                        collect(child)
                elif isinstance(value, list):
                    for child in value:
                        collect(child)

            collect(data)
            joined = "\n".join(sorted(keys)).lower()
            for marker in suspicious:
                self.assertNotIn(marker.lower(), joined, f"{filename}のスキーマに{marker!r}がある")


class MunicipalSupplyDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = read_json(DOCS_DATA_DIR / "municipal_supply.json")
        cls.by_name = {item["municipality"]: item for item in cls.data["municipalities"]}

    def test_official_roster_has_all_19_in_source_order(self):
        self.assertEqual(
            list(self.by_name),
            [
                "下関市", "宇部市", "山口市", "萩市", "防府市", "下松市", "岩国市",
                "光市", "長門市", "柳井市", "美祢市", "周南市", "山陽小野田市",
                "周防大島町", "和木町", "上関町", "田布施町", "平生町", "阿武町",
            ],
        )
        meta = self.data["meta"]
        self.assertEqual(meta["municipality_count"], 19)
        self.assertEqual(
            meta["municipality_source_sha256"],
            "c947ebd3e02ae11772db8aa4d28828747037e6d6d47113c5ee233213c61860e1",
        )

    def test_prefecture_unique_totals_are_not_municipal_sums(self):
        meta = self.data["meta"]
        self.assertEqual(meta["municipalities_with_records"], 15)
        self.assertEqual(
            meta["unique_prefecture_totals"],
            {"operator_count": 23, "vehicles_total": 136, "vehicles_total_kei": 20},
        )
        self.assertGreater(
            sum(item["vehicles_total"] for item in self.data["municipalities"]),
            meta["unique_prefecture_totals"]["vehicles_total"],
            "複数区域団体による市町ビュー間の重複が検出できない",
        )

    def test_zero_record_municipalities_are_exact(self):
        zero = {name for name, item in self.by_name.items() if item["operator_count"] == 0}
        self.assertEqual(zero, {"宇部市", "防府市", "山陽小野田市", "平生町"})
        for name in zero:
            item = self.by_name[name]
            self.assertEqual((item["vehicles_total"], item["vehicles_total_kei"]), (0, 0))
            self.assertEqual(item["operators"], [])

    def test_shimonoseki_and_yamaguchi_hardcoded_totals(self):
        shimonoseki = self.by_name["下関市"]
        self.assertEqual(
            (shimonoseki["operator_count"], shimonoseki["vehicles_total"], shimonoseki["vehicles_total_kei"]),
            (5, 49, 13),
        )
        self.assertEqual(
            {
                group["transport_type"]: (
                    group["operator_count"], group["vehicles_total"], group["vehicles_total_kei"]
                )
                for group in shimonoseki["by_transport_type"]
            },
            {"福祉有償運送": (4, 20, 13), "交通空白地有償運送": (1, 29, 0)},
        )

        yamaguchi = self.by_name["山口市"]
        self.assertEqual(
            (yamaguchi["operator_count"], yamaguchi["vehicles_total"], yamaguchi["vehicles_total_kei"]),
            (2, 7, 2),
        )

    def test_each_municipality_has_no_duplicate_operator_and_breakdown_reconciles(self):
        for item in self.data["municipalities"]:
            keys = [(operator["source_pdf"], operator["registration_no"]) for operator in item["operators"]]
            self.assertEqual(len(keys), len(set(keys)), item["municipality"])
            self.assertEqual(sum(group["operator_count"] for group in item["by_transport_type"]), item["operator_count"])
            self.assertEqual(sum(group["vehicles_total"] for group in item["by_transport_type"]), item["vehicles_total"])
            self.assertEqual(
                sum(group["vehicles_total_kei"] for group in item["by_transport_type"]),
                item["vehicles_total_kei"],
            )


class GtfsStatusDataTest(unittest.TestCase):
    """I-4: GTFS/GTFS-JP official-status data built from the accepted GTFS-1 inventory."""

    @classmethod
    def setUpClass(cls):
        cls.feeds = read_json(DOCS_DATA_DIR / "gtfs_feeds.json")
        cls.municipalities = read_json(DOCS_DATA_DIR / "municipality_gtfs.json")
        cls.feeds_by_id = {row["feed_id"]: row for row in cls.feeds}

    def test_feeds_row_count_and_unique_ids(self):
        self.assertEqual(len(self.feeds), 3)
        self.assertEqual(len({row["feed_id"] for row in self.feeds}), 3)

    def test_municipality_row_count_official_order_and_unique_codes(self):
        self.assertEqual(len(self.municipalities), 19)
        self.assertEqual(
            [row["municipality"] for row in self.municipalities],
            list(build_site_data.MUNICIPALITIES),
        )
        self.assertEqual(len({row["municipality_code"] for row in self.municipalities}), 19)

    def test_availability_status_counts(self):
        counts = {}
        for row in self.municipalities:
            counts[row["availability_status"]] = counts.get(row["availability_status"], 0) + 1
        self.assertEqual(counts, {"confirmed": 5, "not_confirmed_in_checked_sources": 14})
        self.assertNotIn("unassessed", counts, "unassessed は0件のはずで、キー自体が現れてはいけない")

    def test_three_feeds_map_to_five_municipalities_without_double_counting(self):
        confirmed = [row for row in self.municipalities if row["availability_status"] == "confirmed"]
        self.assertEqual(
            {row["municipality"] for row in confirmed},
            {"岩国市", "光市", "宇部市", "美祢市", "山陽小野田市"},
        )
        for row in confirmed:
            # Each confirmed municipality maps to exactly one feed_id; a
            # shared feed (Sentetsu) must never be recorded as though it
            # were 3 separate feeds.
            self.assertEqual(len(row["feed_ids"].split(";")), 1, row["municipality"])
        sentetsu_municipalities = {
            row["municipality"]
            for row in confirmed
            if row["feed_ids"] == "sentetsu-odpt-gtfsjp"
        }
        self.assertEqual(sentetsu_municipalities, {"宇部市", "美祢市", "山陽小野田市"})
        self.assertEqual(
            {row["municipality"] for row in confirmed if row["feed_ids"] == "iwakuni-gtfsjp"}, {"岩国市"}
        )
        self.assertEqual(
            {row["municipality"] for row in confirmed if row["feed_ids"] == "hikari-gtfs"}, {"光市"}
        )

    def test_iwakuni_and_hikari_reference_dates_and_validity(self):
        for feed_id, catalog_updated_date in (
            ("iwakuni-gtfsjp", "2026-04-10"),
            ("hikari-gtfs", "2026-03-03"),
        ):
            feed = self.feeds_by_id[feed_id]
            self.assertEqual(feed["official_reference_date"], "2026-04-01")
            self.assertEqual(feed["reference_date_status"], "confirmed")
            self.assertEqual(feed["catalog_updated_date"], catalog_updated_date)
            self.assertEqual(feed["validity_status_at_check"], "not_confirmed")
            self.assertEqual(feed["official_valid_from"], "")
            self.assertEqual(feed["official_valid_to"], "")

    def test_sentetsu_validity_period_and_access_status(self):
        sentetsu = self.feeds_by_id["sentetsu-odpt-gtfsjp"]
        self.assertEqual(sentetsu["official_valid_from"], "2025-11-17")
        self.assertEqual(sentetsu["official_valid_to"], "2026-11-16")
        self.assertEqual(sentetsu["validity_status_at_check"], "within_official_period")
        self.assertEqual(sentetsu["access_status"], "authentication_required_not_retrieved")
        self.assertEqual(sentetsu["reference_date_status"], "not_stated")
        self.assertEqual(sentetsu["official_reference_date"], "")

    def test_access_status_is_limited_to_spec_enum(self):
        allowed = {"public_head_confirmed", "authentication_required_not_retrieved"}
        for row in self.feeds:
            self.assertIn(row["access_status"], allowed)

    def test_no_real_access_token_is_recorded(self):
        # Only the literal placeholder printed on the official ODPT page may
        # appear; an actual issued token value must never be committed.
        joined = json.dumps(self.feeds, ensure_ascii=False)
        self.assertIn("[アクセストークン/YOUR_ACCESS_TOKEN]", joined)

    def test_source_evidence_files_exist(self):
        referenced = set()
        for row in (*self.feeds, *self.municipalities):
            referenced.update(row["source_evidence"].split(";"))
        self.assertGreater(len(referenced), 0)
        for filename in referenced:
            self.assertTrue((REPO_ROOT / filename).is_file(), f"証拠ファイルが存在しない: {filename}")

    def test_csv_and_json_match(self):
        for stem, columns in (
            ("gtfs_feeds", build_gtfs_status.FEEDS_COLUMNS),
            ("municipality_gtfs", build_gtfs_status.MUNICIPALITY_COLUMNS),
        ):
            with (DATA_DIR / f"{stem}.csv").open(encoding="utf-8", newline="") as f:
                csv_rows = list(csv.DictReader(f))
            json_rows = read_json(DATA_DIR / f"{stem}.json")
            self.assertEqual(len(csv_rows), len(json_rows))
            for csv_row, json_row in zip(csv_rows, json_rows):
                self.assertEqual(csv_row, {k: json_row[k] for k in columns})

    def test_published_gtfs_json_is_byte_identical(self):
        for filename in ("gtfs_feeds.json", "municipality_gtfs.json"):
            self.assertEqual(
                (DATA_DIR / filename).read_bytes(),
                (DOCS_DATA_DIR / filename).read_bytes(),
                f"docs/data/{filename} が data/{filename} と一致しない",
            )

    def test_csv_files_use_lf_line_endings(self):
        for filename in ("gtfs_feeds.csv", "municipality_gtfs.csv"):
            raw = (DATA_DIR / filename).read_bytes()
            self.assertNotIn(b"\r", raw, f"{filename} にCRが含まれる")


class IndexHtmlContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")

    def test_user_outcome_and_controls_are_present(self):
        required = (
            "山口県 市町別の登録供給ビュー",
            'id="municipality-select"',
            'id="metric-operators"',
            'id="metric-vehicles"',
            'id="metric-light"',
            'id="records-body"',
            "福祉有償運送",
            "交通空白地有償運送",
        )
        for marker in required:
            self.assertIn(marker, self.html)
        self.assertNotIn("準備中", self.html)

    def test_limitations_attribution_and_licenses_are_present(self):
        required = (
            "交通手段や移動支援が存在しないことを意味しません",
            "市町値は県計として足し合わせない",
            "運行頻度、予約可否、実際の稼働台数",
            "https://wwwtb.mlit.go.jp/chugoku/00001_00903.html",
            "https://www.pref.yamaguchi.lg.jp/soshiki/21/26969.html",
            "PDL1.0",
            "CC BY 4.0",
            "国土交通省が作成したものではありません",
        )
        for marker in required:
            self.assertIn(marker, self.html)

    def test_gtfs_status_does_not_assert_coverage_or_maturity_metrics(self):
        banned = ("GTFSなし", "未整備", "整備率", "網羅率", "交通カバー率")
        for phrase in banned:
            self.assertNotIn(phrase, self.html)

    def test_gtfs_status_elements_are_present(self):
        # official_reference_date / official_valid_from / official_valid_to are
        # rendered client-side from gtfs_feeds.json (verified precisely in
        # GtfsStatusDataTest), not hardcoded as static HTML text; only the
        # page scaffolding and confirmation date are checked as static text here.
        required = (
            'id="gtfs-feed-count"',
            'id="gtfs-municipality-count"',
            'id="gtfs-result"',
            'id="gtfs-availability-badge"',
            'id="gtfs-availability-body"',
            'id="gtfs-caveat"',
            "今回確認した公式資料の範囲ではGTFS/GTFS-JPを確認できませんでした。",
            "2026-08-09",
            "data/gtfs_feeds.json",
            "data/municipality_gtfs.json",
            "https://yamaguchi-opendata.jp/",
            "https://ckan.odpt.org/organization/sentetsu_bus",
        )
        for marker in required:
            self.assertIn(marker, self.html)


class StatusHtmlContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (DOCS_DIR / "status.html").read_text(encoding="utf-8")

    def test_stale_progress_claims_are_absent(self):
        stale = (
            "1 / 4",
            "3 / 7",
            "7工程中3工程完了",
            "残り3本",
            "3本とも未着手",
            "現在データがあるのは2市町",
            "確認せずに埋めない6項目",
            'class="unknown-id">U6',
            "run_record.md を初回コミットする",
            "README.md を直す",
            # I-3受入時点でI-5が同期対象とした古い現況表示（SPEC.md §13.5.1）
            "I-1 / I-2",
            "41テスト",
            "7工程中4工程",
            "I-3後に一つだけ再評価",
            "I-3受入後に一つだけ再評価",
            "I-3はここまでで止める",
            'href="index.html?v=20260809"',
        )
        for marker in stale:
            self.assertNotIn(marker, self.html)

    def test_current_status_reflects_i1_to_i4_and_main_view_link_is_present(self):
        required = (
            "I-1〜I-4",
            "4 / 4",
            "23団体・90車種行",
            "実車両136台",
            "軽20台",
            f"{TOTAL_TEST_COUNT}テスト",
            "T1",
            "T2",
            "T3",
            "T4",
            'href="index.html?v=20260810"',
            "I-5はここまでで止める",
            "PDL1.0",
            "CC BY 4.0",
        )
        for marker in required:
            self.assertIn(marker, self.html)
        self.assertEqual(self.html.count("処理・検証済み"), 4)

    def test_i1_to_i4_accepted_outcomes_have_short_purpose_linked_descriptions(self):
        # SPEC.md §13.5.2: I-1〜I-4の受け入れ済み成果を、目的との関係が分かる
        # 短い説明で表示する。各増分に対応する見出しと、供給側データ・原本追跡・
        # 現況導線・GTFS確認といった目的語の両方が本文にあることを確認する。
        for marker in (
            "I-1: 登録簿データ基盤",
            "I-2: 市町別の登録供給ビュー",
            "I-3: 状況ページから作品への導線",
            "I-4: GTFS/GTFS-JP公式確認状況",
        ):
            self.assertIn(marker, self.html)

    def test_pdf_numbers_and_gtfs_numbers_are_not_conflated(self):
        # SPEC.md §13.5.3: 登録簿4PDFの数値とI-4の3フィード・5/19・14/19を
        # 混同せず表示する。GTFSセクションが登録簿集計と別集計だと明記し、
        # 4PDFの実車両合計(136)がGTFSフィード件数(3)として現れないことを確認する。
        gtfs_start = self.html.index('id="gtfs-title"')
        gtfs_end = self.html.index("</section>", gtfs_start)
        gtfs_section = self.html[gtfs_start:gtfs_end]
        self.assertIn("別の集計であり、混同していません", gtfs_section)
        self.assertIn("136", self.html)  # 4PDFの実車両合計は他セクションに存在する
        self.assertNotIn("136", gtfs_section)

    def test_gtfs_relationship_matches_built_data_without_banned_terms(self):
        # SPEC.md §13.5.4, §13.6.4: 3フィード・5/19・14/19の関係を、
        # ビルド済みデータの実測値と突き合わせて検査し、禁止表現による
        # 不存在・率の断定を防ぐ。
        feeds = read_json(DOCS_DATA_DIR / "gtfs_feeds.json")
        municipalities = read_json(DOCS_DATA_DIR / "municipality_gtfs.json")
        confirmed = sum(1 for row in municipalities if row["availability_status"] == "confirmed")
        not_confirmed = sum(
            1 for row in municipalities if row["availability_status"] == "not_confirmed_in_checked_sources"
        )
        total = len(municipalities)

        self.assertIn(str(len(feeds)), self.html)
        self.assertIn(f"{confirmed} / {total}", self.html)
        self.assertIn(f"{not_confirmed} / {total}", self.html)

        banned = ("整備率", "網羅率", "交通カバー率", "GTFSなし", "未整備")
        for phrase in banned:
            self.assertNotIn(phrase, self.html)

        # 未確認をGTFS不存在と断定しない: 断定を否定する文言が必ずあること
        self.assertIn("存在しないと断定するものではありません", self.html)
        self.assertIn("今回確認した公式資料の範囲では未確認", self.html)

    def test_t1_to_t3_and_t4_are_separated_and_marked_not_met(self):
        # SPEC.md §13.5.5: T1〜T3は自力終了条件、T4は成果条件として分離し、
        # いずれも未達と表示する。
        self.assertIn("自力で終えられる終了条件", self.html)
        self.assertIn("他者評価に依存する成果条件", self.html)
        self.assertGreaterEqual(self.html.count("未達"), 4)
        for marker in ("T1", "T2", "T3", "T4"):
            self.assertIn(marker, self.html)
        banned_completion_claims = (
            "T1は達成", "T2は達成", "T3は達成", "T4は達成",
            "受賞しました", "受賞済み",
        )
        for phrase in banned_completion_claims:
            self.assertNotIn(phrase, self.html)

    def test_real_links_to_index_json_and_terms_are_present(self):
        # SPEC.md §13.5.7: docs/index.html、公開JSON、出典・利用条件へ
        # 実在するリンクで到達できる。リンク先は実ファイルとして存在する。
        required_hrefs = (
            'href="index.html?v=20260810"',
            'href="data/gtfs_feeds.json"',
            'href="data/municipality_gtfs.json"',
            'href="data/operators.json"',
            'href="data/vehicles.json"',
            'href="https://www.mlit.go.jp/link.html"',
        )
        for href in required_hrefs:
            self.assertIn(href, self.html)
        for filename in ("gtfs_feeds.json", "municipality_gtfs.json", "operators.json", "vehicles.json"):
            self.assertTrue((DOCS_DATA_DIR / filename).is_file(), f"リンク先が実在しない: {filename}")
        self.assertTrue((DOCS_DIR / "index.html").is_file())

    def test_no_external_publication_or_award_claims(self):
        # SPEC.md §13.5.8: 外部公開済み、応募済み、受賞済みとは表示しない。
        banned = ("公開済み", "応募済み", "受賞済み", "GitHub Pagesで公開中", "外部公開済み")
        for phrase in banned:
            self.assertNotIn(phrase, self.html)


class ReadmeContractTest(unittest.TestCase):
    """I-5: README.mdを受け入れ済みI-1〜I-4の現在地へ同期する（SPEC.md §13.4）。"""

    @classmethod
    def setUpClass(cls):
        cls.text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    def test_stale_fixed_test_count_is_absent(self):
        # SPEC.md §13.4.6・§13.6.3: 「30テスト」の固定値を除く。
        self.assertNotIn("30テスト", self.text)

    def test_current_state_spans_i1_to_i4_with_pdf_baseline(self):
        required = (
            "I-1〜I-4",
            "4団体＋3団体＋12団体＋4団体",
            "23団体",
            "90行",
            "136台",
            "軽20台",
            f"{TOTAL_TEST_COUNT}件成功",
        )
        for marker in required:
            self.assertIn(marker, self.text)

    def test_role_description_covers_municipal_view_and_gtfs_status(self):
        # SPEC.md §13.4.1: 登録簿の機械可読化だけでなく、市町別登録供給と
        # 公式GTFS/GTFS-JP確認状況を表示する静的ビューまで含む現況へ直す。
        for marker in ("市町別の登録供給", "GTFS/GTFS-JP"):
            self.assertIn(marker, self.text)

    def test_gtfs_summary_present_without_banned_rate_terms(self):
        required = (
            "公式フィード",
            "3件",
            "5 / 19",
            "14 / 19",
            "今回確認した公式資料の範囲",
        )
        for marker in required:
            self.assertIn(marker, self.text)
        banned = ("整備率", "網羅率", "交通カバー率", "GTFSなし", "未整備")
        for phrase in banned:
            self.assertNotIn(phrase, self.text)
        # 未確認をGTFS不存在と断定しない
        self.assertIn("存在しないと断定するものではない", self.text)

    def test_included_artifacts_and_screens_are_listed(self):
        # SPEC.md §13.4.5: data/gtfs_feeds.*、data/municipality_gtfs.*、
        # docs/index.htmlを収録物・利用画面として案内する。
        for marker in (
            "data/gtfs_feeds.csv", "data/gtfs_feeds.json",
            "data/municipality_gtfs.csv", "data/municipality_gtfs.json",
            "docs/index.html", "docs/status.html",
        ):
            self.assertIn(marker, self.text)

    def test_repo_is_not_treated_as_submission_publication_or_award(self):
        # SPEC.md §13.4.7: このリポジトリやローカル実装をUDC応募・公開・
        # 受賞の完了と扱わない。
        self.assertIn("UDC応募・公開・受賞の完了", self.text)
        banned = ("応募済み", "公開済み", "受賞済み", "受賞しました")
        for phrase in banned:
            self.assertNotIn(phrase, self.text)


if __name__ == "__main__":
    unittest.main()
