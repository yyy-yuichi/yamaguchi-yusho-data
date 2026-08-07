"""SPEC.md §5 の完了条件のうち、自動テストで担保すべき項目（§5-2, §5-3, §5-8）を検証する。

pytest は依存に無い（requirements.txt は pdfplumber の1行のみ）ため、
標準ライブラリの unittest で書く。

実行方法:
    C:\\Users\\user\\dev\\udc2026\\.venv\\Scripts\\python.exe -m unittest tests.test_verify -v
（リポジトリ直下から実行すること。素の `python` は使わない。CLAUDE.md 参照）
"""
from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import parse as parse_module  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
PDF_PATH = REPO_ROOT / "raw" / "000271730.pdf"


def setUpModule():
    # data/ を今回のパーサ実装で最新化してからテストする
    parse_module.main()


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class VehicleTotalsTest(unittest.TestCase):
    """SPEC.md §5-2: 車両合計の照合（自動テスト）。"""

    @classmethod
    def setUpClass(cls):
        cls.operators = read_csv(DATA_DIR / "operators.csv")
        cls.vehicles = read_csv(DATA_DIR / "vehicles.csv")

    def test_count_sum_matches_vehicles_total(self):
        by_reg = {}
        for v in self.vehicles:
            if v["vehicle_type"] == "合計":
                continue  # 合計行自体は内訳の合計に含めない(§5-2「合計以外の行」)
            by_reg.setdefault(v["registration_no"], {"count": 0, "count_kei": 0})
            by_reg[v["registration_no"]]["count"] += int(v["count"])
            kei = v["count_kei"]
            by_reg[v["registration_no"]]["count_kei"] += int(kei) if kei != "" else 0

        self.assertEqual(len(self.operators), 4, "団体数が4件でない")
        for op in self.operators:
            reg = op["registration_no"]
            totals = by_reg.get(reg, {"count": 0, "count_kei": 0})
            self.assertEqual(
                totals["count"], int(op["vehicles_total"]),
                f"{reg}: vehicles.csvのcount合計({totals['count']}) != "
                f"operators.csvのvehicles_total({op['vehicles_total']})",
            )
            self.assertEqual(
                totals["count_kei"], int(op["vehicles_total_kei"]),
                f"{reg}: vehicles.csvのcount_kei合計({totals['count_kei']}) != "
                f"operators.csvのvehicles_total_kei({op['vehicles_total_kei']})",
            )

    def test_count_kei_le_count(self):
        """SPEC.md §5-3: count_kei <= count が全行で成立（様式上の不変条件）。

        count_kei が空文字列の行は、その車種列に(軽)欄が構造的に無い（バス列のみ）ため対象外。
        """
        checked = 0
        for v in self.vehicles:
            if v["count_kei"] == "":
                continue
            checked += 1
            self.assertLessEqual(
                int(v["count_kei"]), int(v["count"]),
                f"{v['registration_no']} {v['vehicle_type']}: "
                f"count_kei({v['count_kei']}) > count({v['count']})。抽出誤りの疑い",
            )
        self.assertGreater(checked, 0, "count_kei を持つ行が1件も無い(抽出漏れの疑い)")


class RegistrationConsistencyTest(unittest.TestCase):
    """SPEC.md §5-4: 登録番号の整合。"""

    @classmethod
    def setUpClass(cls):
        cls.operators = read_csv(DATA_DIR / "operators.csv")

    def test_service_type_code_is_fukushi(self):
        for op in self.operators:
            self.assertEqual(
                op["service_type_code"], "福",
                f"{op['registration_no']}: service_type_codeが福でない(福祉有償運送ファイルのため全件福のはず)",
            )

    def test_authority_code_is_uniform(self):
        codes = {op["authority_code"] for op in self.operators}
        self.assertEqual(len(codes), 1, f"authority_codeが全件同一でない: {codes}")


class RepresentativeNameNotOutputTest(unittest.TestCase):
    """SPEC.md §5-8, CLAUDE.md「代表者の氏名は抽出も出力もしない」。

    実際の氏名をこのテストファイル自体に書き残さないため、PDFから「代表者の氏名」
    ラベルの右側の語を都度動的に抽出し、その値がdata/配下のどのファイルにも
    含まれていないことを確認する。
    """

    OUTPUT_FILES = [
        DATA_DIR / "operators.csv",
        DATA_DIR / "operators.json",
        DATA_DIR / "vehicles.csv",
        DATA_DIR / "vehicles.json",
    ]

    def test_representative_name_absent_from_all_outputs(self):
        import pdfplumber

        contents = {p: p.read_text(encoding="utf-8") for p in self.OUTPUT_FILES}

        checked_pages = 0
        with pdfplumber.open(PDF_PATH) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                words = page.extract_words()
                label = parse_module.find_word(words, "代表者の氏名", x_max=150, top_max=220)
                self.assertIsNotNone(label, f"p{page_no}: 「代表者の氏名」ラベルが見つからない")
                row = parse_module.words_in_box(
                    words, x0=150, top=label["top"] - 2, bottom=label["bottom"] + 2
                )
                name_text = parse_module.join_words(row)
                self.assertTrue(name_text, f"p{page_no}: 代表者の氏名が空で取得できていない")
                checked_pages += 1
                for path, content in contents.items():
                    self.assertNotIn(
                        name_text, content,
                        f"p{page_no}の代表者氏名が {path.name} に含まれている(絶対厳守違反)",
                    )
                    # 氏(姓)だけでも部分一致しないか、念のため確認する
                    for part in name_text.split():
                        if len(part) >= 2:
                            self.assertNotIn(
                                part, content,
                                f"p{page_no}の代表者氏名の一部 {part!r} が {path.name} に含まれている",
                            )
        self.assertEqual(checked_pages, 4, "4ページ全件を確認できていない")

    def test_no_representative_column_in_schema(self):
        suspicious = ("代表者", "氏名", "daihyo", "representative")
        for path in (DATA_DIR / "operators.csv", DATA_DIR / "vehicles.csv"):
            with path.open(encoding="utf-8") as f:
                header = f.readline()
            for word in suspicious:
                self.assertNotIn(word, header, f"{path.name} の列見出しに {word!r} を示唆する語がある")


if __name__ == "__main__":
    unittest.main()
