"""I-2 static municipal supply view: build outputs and acceptance invariants."""
from __future__ import annotations

import csv
import copy
import hashlib
import json
import re
import sys
import unicodedata
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
TOTAL_TEST_COUNT = 86

ENTRY_SUMMARY = (
    "山口県の公共交通担当者・事業者向けに、分散した登録簿と公式GTFSを市町別に整理し、"
    "輸送供給・日付・根拠・データの限界を同じ画面で確認できる静的Webアプリです。"
)


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
        self.assertEqual(counts, {"confirmed": 6, "not_confirmed_in_checked_sources": 13})
        self.assertNotIn("unassessed", counts, "unassessed は0件のはずで、キー自体が現れてはいけない")

    def test_three_feeds_map_to_six_municipalities_without_double_counting(self):
        confirmed = [row for row in self.municipalities if row["availability_status"] == "confirmed"]
        self.assertEqual(
            {row["municipality"] for row in confirmed},
            {"岩国市", "光市", "周南市", "宇部市", "美祢市", "山陽小野田市"},
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
            {row["municipality"] for row in confirmed if row["feed_ids"] == "hikari-gtfs"},
            {"光市", "周南市"},
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

        # CKPT-CORR-1: evidence/20260809_gtfs_source_official_hikari.txt used to
        # contain two real client-side JWT-format tokens copied verbatim from a
        # curl fetch of the Hikari city site. They were replaced with
        # deterministic, non-secret placeholders; guard against real JWTs (or
        # any future ones) being reintroduced into that evidence file.
        hikari_evidence = REPO_ROOT / "evidence" / "20260809_gtfs_source_official_hikari.txt"
        hikari_text = hikari_evidence.read_text(encoding="utf-8")
        jwt_pattern = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
        self.assertEqual(
            jwt_pattern.findall(hikari_text),
            [],
            "evidence/20260809_gtfs_source_official_hikari.txt にJWT形式の実トークンが混入している",
        )
        placeholder_pattern = re.compile(r"REDACTED_PUBLIC_CLIENT_TOKEN_\d+_SHA256_[0-9a-f]{64}_LEN_\d+")
        self.assertEqual(
            len(placeholder_pattern.findall(hikari_text)),
            2,
            "決定論的プレースホルダーが2件ではない",
        )

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


class GtfsSupplyMetricsDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_path = DATA_DIR / "gtfs_supply_metrics.json"
        cls.public_path = DOCS_DATA_DIR / "gtfs_supply_metrics.json"
        cls.records = read_json(cls.source_path)

    def test_supply_metrics_public_copy_is_byte_identical_and_accepted_hash(self):
        source = self.source_path.read_bytes()
        published = self.public_path.read_bytes()
        self.assertEqual(source, published)
        self.assertEqual(
            hashlib.sha256(source).hexdigest(),
            "c277e1050086da6ad5cc703051deb672458f7bf2829e1aca92fd0b17b4d20930",
        )

    def test_supply_metrics_two_feeds_and_all_twenty_values_are_fixed(self):
        self.assertEqual([record["feed_id"] for record in self.records], ["iwakuni-gtfsjp", "hikari-gtfs"])
        self.assertEqual({record["metric_version"] for record in self.records}, {"SUPPLY-METRIC-1"})
        self.assertEqual(
            {(record["comparison_week_start"], record["comparison_week_end"]) for record in self.records},
            {("2026-04-06", "2026-04-12")},
        )
        expected = {
            "iwakuni-gtfsjp": ([1, 46, 800], [185, 186, 183, 161, 188, 146, 39]),
            "hikari-gtfs": ([1, 7, 172], [55, 55, 55, 55, 55, 41, 41]),
        }
        metric_ids = list(build_site_data.SUPPLY_METRIC_KEYS)
        for record in self.records:
            structure = [record["metrics"][metric_id]["value"] for metric_id in metric_ids]
            daily = [metric["value"] for metric in record["scheduled_trip_count_by_date"].values()]
            self.assertEqual((structure, daily), expected[record["feed_id"]])
            self.assertEqual(len(structure) + len(daily), 10)

    def test_supply_metrics_status_value_and_reason_are_consistent(self):
        metrics = []
        for record in self.records:
            metrics.extend(record["metrics"].values())
            metrics.extend(record["scheduled_trip_count_by_date"].values())
        self.assertEqual(len(metrics), 20)
        for metric in metrics:
            self.assertEqual(metric["metric_status"], "measured")
            self.assertIsInstance(metric["value"], int)
            self.assertGreaterEqual(metric["value"], 0)
            self.assertIsNone(metric["reason"])

    def test_supply_metrics_validator_rejects_mismatches_and_unknown_status(self):
        cases = []

        wrong_order = copy.deepcopy(self.records)
        wrong_order.reverse()
        cases.append(("feed order", wrong_order))

        wrong_version = copy.deepcopy(self.records)
        wrong_version[1]["metric_version"] = "DIFFERENT"
        cases.append(("metric version", wrong_version))

        wrong_dates = copy.deepcopy(self.records)
        wrong_dates[1]["scheduled_trip_count_by_date"].pop("2026-04-12")
        cases.append(("date keys", wrong_dates))

        unknown_status = copy.deepcopy(self.records)
        unknown_status[0]["metrics"]["gtfs_route_id_count"]["metric_status"] = "unknown"
        cases.append(("status", unknown_status))

        nonmeasured_value = copy.deepcopy(self.records)
        metric = nonmeasured_value[0]["metrics"]["gtfs_route_id_count"]
        metric.update(metric_status="not_calculable", value=46, reason="算出不能")
        cases.append(("non-measured value", nonmeasured_value))

        for label, records in cases:
            with self.subTest(label=label), self.assertRaises(ValueError):
                build_site_data.validate_supply_metrics(records)


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

    def test_supply_comparison_structure_and_general_language(self):
        required = (
            'id="supply-comparison"',
            "岩国市・光市のGTFS供給を同じ日付で確認",
            "フィードに収録された情報の件数",
            "GTFS収録の交通ブランド情報",
            "GTFS収録の路線情報ID",
            "GTFS収録の乗降場所ID",
            "この日にGTFSで予定された運行便",
            'id="supply-structure-body"',
            'id="supply-daily-body"',
            'id="supply-evidence-list"',
            "data/gtfs_supply_metrics.json",
            '<caption>岩国市関連・光市関連フィードの構造指標</caption>',
            '<caption>同じ7実日付にGTFSで予定された運行便</caption>',
            'scope="col"',
            'heading.scope = "row"',
        )
        for marker in required:
            self.assertIn(marker, self.html)
        for filename in ("gtfs_supply_metrics.json", "gtfs_feeds.json"):
            self.assertTrue((DOCS_DATA_DIR / filename).is_file(), f"リンク先が実在しない: {filename}")

    def test_supply_comparison_reads_json_without_hardcoded_values(self):
        self.assertIn('const supplyMetricsUrl = "data/gtfs_supply_metrics.json"', self.html)
        self.assertIn("renderSupplyComparison(records, feeds)", self.html)
        self.assertIn("record.metrics[metricId]", self.html)
        self.assertIn("record.scheduled_trip_count_by_date[dateKey]", self.html)
        self.assertNotIn("2026-04-06", self.html)
        self.assertNotIn("2026-04-12", self.html)
        self.assertNotIn("185/186/183/161/188/146/39", self.html)
        self.assertNotIn("55/55/55/55/55/41/41", self.html)

    def test_supply_comparison_failure_is_isolated(self):
        existing_chain = "Promise.all([fetchJson(dataUrl), fetchJson(gtfsFeedsUrl), fetchJson(municipalityGtfsUrl)])"
        supply_chain = "Promise.all([fetchJson(supplyMetricsUrl), fetchJson(gtfsFeedsUrl)])"
        self.assertIn(existing_chain, self.html)
        self.assertIn(supply_chain, self.html)
        self.assertLess(self.html.index(existing_chain), self.html.index(supply_chain))
        self.assertIn("municipal supply data load failed", self.html)
        self.assertIn("GTFS supply comparison data load failed", self.html)
        self.assertIn("既存の市町別登録供給とGTFS確認状況は引き続き利用できます", self.html)

    def test_supply_comparison_uses_safe_dom_api_and_fixed_status_words(self):
        self.assertNotIn("innerHTML", self.html)
        self.assertIn("textContent", self.html)
        self.assertIn("appendSafeExternalLink", self.html)
        for label in (
            "測定済み", "今回未確認", "算出不能", "入力異常", "範囲が異なり比較対象外",
            "正確な発車回数を固定できない", "共通の比較週なし",
        ):
            self.assertIn(label, self.html)

    def test_supply_comparison_responsive_contract(self):
        required = (
            ".comparison-table",
            "min-width: 0",
            "table-layout: fixed",
            "overflow-wrap: anywhere",
            "word-break: break-all",
            "@media (max-width: 470px)",
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
            'href="index.html?v=20260811"',
            "ENTRY-PAGE-1公開・Codex受入済み",
            "PDL1.0",
            "CC BY 4.0",
            "WORK1-RELEASE-EVIDENCE-PERMALINK-1",
            "監査証拠JSON",
            "Base64正本",
            "公開照合は6資産",
            'href="data/work1_release_attestation_audit.json"',
            'href="https://github.com/yyy-yuichi/yamaguchi-yusho-data/releases/latest"',
            "work1-release-attestation.zip",
            "release-provenance.json",
            "SHA256SUMS.txt",
            "Release/tagは検証証拠の公開",
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
            'href="index.html?v=20260811"',
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

    def test_publication_is_verifiable_without_application_or_award_claims(self):
        # SPEC.md §17.3: 公開URLと検証可能な状態を示し、応募・受賞とは分離する。
        for marker in (
            "GitHub Pagesで公開中",
            "https://yyy-yuichi.github.io/yamaguchi-yusho-data/",
            "18170b2",
        ):
            self.assertIn(marker, self.html)
        banned = ("応募済み", "外部提出済み", "受賞済み", "受賞しました")
        for phrase in banned:
            self.assertNotIn(phrase, self.html)

    def test_supply_view_current_state_and_real_json_link_are_present(self):
        for marker in (
            "SUPPLY-VIEW-1",
            "Codex受入済み",
            "岩国市・光市",
            "2026-04-06〜2026-04-12",
            f"{TOTAL_TEST_COUNT}テスト",
            'href="index.html?v=20260811#supply-comparison"',
            'href="data/gtfs_supply_metrics.json"',
            "外部提出は行っていません",
        ):
            self.assertIn(marker, self.html)
        self.assertTrue((DOCS_DATA_DIR / "gtfs_supply_metrics.json").is_file())


class EntryHtmlContractTest(unittest.TestCase):
    """ENTRY-PAGE-1: 初見の読者向け応募説明ページ（SPEC.md §18）。"""

    @classmethod
    def setUpClass(cls):
        cls.path = DOCS_DIR / "entry.html"
        cls.html = cls.path.read_text(encoding="utf-8")

    def test_fixed_application_metadata_and_summary_are_present(self):
        self.assertTrue(self.path.is_file())
        for marker in (
            "山口県 市町別の登録供給ビュー",
            "作品タイプ: アプリケーション",
            "作品テーマ: 道路・交通",
            ENTRY_SUMMARY,
            "作品概要（81字）",
        ):
            self.assertIn(marker, self.html)
        self.assertEqual(len(ENTRY_SUMMARY), 81)
        self.assertLessEqual(len(ENTRY_SUMMARY), 100)

    def test_problem_users_usage_data_criteria_and_limits_are_explicit(self):
        for marker in (
            "解決したい問題",
            "誰が、何のために使うか",
            "3段階の使い方",
            "使用データと、現在確認できる範囲",
            "実用度・完成度・挑戦度の根拠",
            "分かること／分からないこと",
            "登録簿とGTFSは公開場所も数え方も違い",
        ):
            self.assertIn(marker, self.html)

    def test_demo_repository_status_and_public_json_links_exist(self):
        for href in (
            'href="index.html"',
            'href="index.html#supply-comparison"',
            'href="status.html"',
            'href="https://github.com/yyy-yuichi/yamaguchi-yusho-data"',
            'href="data/municipal_supply.json"',
            'href="data/gtfs_feeds.json"',
            'href="data/municipality_gtfs.json"',
            'href="data/gtfs_supply_metrics.json"',
        ):
            self.assertIn(href, self.html)
        for filename in (
            "municipal_supply.json", "gtfs_feeds.json",
            "municipality_gtfs.json", "gtfs_supply_metrics.json",
        ):
            self.assertTrue((DOCS_DATA_DIR / filename).is_file(), filename)

    def test_limits_are_not_replaced_by_completion_or_coverage_claims(self):
        for marker in (
            "実際に運行した便",
            "市内だけに限定したGTFSの供給量",
            "県内すべての交通事業者・移動サービスの網羅",
            "GTFSが存在しないかどうか",
            "交通の充足度や市町の優劣を判定するものではありません",
        ):
            self.assertIn(marker, self.html)
        for phrase in ("応募済み", "外部提出済み", "受賞済み", "受賞しました", "GTFSなし"):
            self.assertNotIn(phrase, self.html)

    def test_static_responsive_contract_is_present(self):
        self.assertNotIn("<script", self.html.lower())
        for marker in (
            'name="viewport"',
            "overflow-wrap: anywhere",
            "grid-template-columns: repeat(3, minmax(0, 1fr))",
            "@media (max-width: 760px)",
            ".grid-2, .grid-3 { grid-template-columns: 1fr; }",
            'rel="icon"',
        ):
            self.assertIn(marker, self.html)

    def test_existing_pages_and_readme_link_to_entry_page(self):
        index_html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        status_html = (DOCS_DIR / "status.html").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('href="entry.html"', index_html)
        self.assertIn('href="entry.html"', status_html)
        self.assertIn("docs/entry.html", readme)
        self.assertIn("https://yyy-yuichi.github.io/yamaguchi-yusho-data/entry.html", readme)


class ReadmeContractTest(unittest.TestCase):
    """I-5: README.mdを受け入れ済みI-1〜I-4の現在地へ同期する（SPEC.md §13.4）。"""

    @classmethod
    def setUpClass(cls):
        cls.text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    def test_stale_fixed_test_count_is_absent(self):
        # SPEC.md §13.4.6・§13.6.3、I-5-CORR-1: 「30テスト」の固定値を、
        # 表記ゆれ（「30テスト成功」「30件成功」「自動テスト: 30」等）を含めて
        # まとめて除く。旧版のI-5改訂点が「自動テスト: 30件成功」という値を
        # そのまま引用していた再発を防ぐため、この4パターンは必ず検査する。
        banned_literal = ("30テスト", "30テスト成功", "30件成功", "自動テスト: 30")
        for phrase in banned_literal:
            self.assertNotIn(phrase, self.text, f"旧固定値の表記が残っている: {phrase!r}")

        # 全角数字・空白の有無といった表記ゆれを吸収した正規化テキストでも、
        # 「30」と「テスト」「件」「成功」が近接して現れないことを検査する。
        normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", self.text))
        for pattern in (
            r"30(件|本|個)?の?テスト",
            r"テスト.{0,4}30(件|本|個)",
            r"自動テスト:?30",
        ):
            match = re.search(pattern, normalized)
            self.assertIsNone(
                match, f"旧固定値30の表記ゆれが残っている: {match.group() if match else pattern!r}"
            )

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
            "6 / 19",
            "13 / 19",
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

    def test_public_demo_is_not_treated_as_application_or_award(self):
        # SPEC.md §17.3: 現行デモの公開をUDC応募・受賞の完了と扱わない。
        self.assertIn("UDC応募・受賞の完了", self.text)
        self.assertIn("https://yyy-yuichi.github.io/yamaguchi-yusho-data/", self.text)
        self.assertIn("18170b2", self.text)
        banned = ("応募済み", "外部提出済み", "受賞済み", "受賞しました")
        for phrase in banned:
            self.assertNotIn(phrase, self.text)

    def test_supply_view_is_described_with_scope_dates_and_test_count(self):
        for marker in (
            "SUPPLY-VIEW-1",
            "岩国市・光市",
            "構造3指標",
            "2026-04-06〜2026-04-12",
            "data/gtfs_supply_metrics.json",
            "docs/data/gtfs_supply_metrics.json",
            f"{TOTAL_TEST_COUNT}件成功",
            "市内だけの値",
        ):
            self.assertIn(marker, self.text)


if __name__ == "__main__":
    unittest.main()
