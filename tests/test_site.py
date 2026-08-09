"""I-2 static municipal supply view: build outputs and acceptance invariants."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import build_site_data  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_DATA_DIR = DOCS_DIR / "data"


def setUpModule():
    build_site_data.main()


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


if __name__ == "__main__":
    unittest.main()
