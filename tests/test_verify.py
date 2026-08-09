"""SPEC.md §5 の完了条件のうち、自動テストで担保すべき項目（§5-1〜§5-4, §5-7, §5-8）を検証する。

現在の増分は 000271730.pdf（福祉・NPO等、4団体）と 000230003.pdf（福祉・市町村営、3団体）の
2PDF・7団体（SPEC.md §5）。団体の主キー、および operators/vehicles 間の結合キーは
`(source_pdf, registration_no)` の複合キーである（SPEC.md §3、rev.4.3）。
`registration_no` 単独は主キーではなく、`中山福第3号` が2ファイルに1件ずつ正常に重複する。

pytest は依存に無い（requirements.txt は pdfplumber の1行のみ）ため、
標準ライブラリの unittest で書く。

実行方法:
    C:\\Users\\user\\dev\\udc2026\\.venv\\Scripts\\python.exe -m unittest tests.test_verify -v
（リポジトリ直下から実行すること。素の `python` は使わない。CLAUDE.md 参照）
"""
from __future__ import annotations

import csv
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import parse as parse_module  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
RAW_DIR = REPO_ROOT / "raw"
TEXT_DIR = REPO_ROOT / "raw" / "text"

PDF1 = RAW_DIR / "000271730.pdf"  # 福祉有償運送・NPO等、4団体
PDF2 = RAW_DIR / "000230003.pdf"  # 福祉有償運送・市町村営、3団体
PDF_PATHS = [PDF1, PDF2]

RAW_TEXT_FILES = [
    TEXT_DIR / "000271730_p1.txt",
    TEXT_DIR / "000271730_p2.txt",
    TEXT_DIR / "000271730_p3.txt",
    TEXT_DIR / "000271730_p4.txt",
    TEXT_DIR / "000230003_p1.txt",
    TEXT_DIR / "000230003_p2.txt",
    TEXT_DIR / "000230003_p3.txt",
]

EVIDENCE_DIR = REPO_ROOT / "evidence"

# SPEC.md §5-8: 「テキスト形式の evidence」にも代表者氏名が含まれないことを検査対象にする。
# data/*.csv, *.json / raw/text/*.txt に加え、コード・検証記録・証拠テキストまで動的検査の
# 対象を広げる（今回の増分「代表者氏名非出力の残件」）。raw/*.pdf・evidence/*.png は対象外
# （SPEC.md §5-8「出典原本raw/*.pdfは検査対象外」、画像はテキストではないため）。
# run_record.md はチャット側専有ファイルでCLAUDE.mdによりClaude Codeは読み書きしないため、
# ここでもスキャン対象に含めない。
NAME_SCAN_ROOT_FILES = [
    REPO_ROOT / "verification.md",
    REPO_ROOT / "PROGRESS.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "SPEC.md",
    REPO_ROOT / "CLAUDE.md",
]


# 「代表者の氏名」欄には役職語が氏名の前に付記される(理事長 姓 名、市長 姓 名 等)。
# 役職語は個人を特定しないため、氏名候補から除外する。市町村営(000230003.pdf)では
# 自治体名+役職が1語に結合される(例: ○○市長)ため、完全一致ではなく部分一致で除外する。
ROLE_WORDS = ("理事長", "代表理事", "代表者", "代表", "所長", "市長", "町長", "村長", "会長")


def _is_role_word(word):
    return any(role in word for role in ROLE_WORDS)


def _normalize_spaces(text):
    """半角/全角スペース・タブを除去する(改行はまたぐ誤検知を避けるため除去しない)。"""
    return re.sub(r"[ \t　]+", "", text)


def discover_name_scan_targets():
    """代表者氏名が含まれないことを検査する対象ファイルの一覧を動的に集める。

    data/*.csv・*.json、raw/text/*.txt、リポジトリ直下の記録・仕様ファイル、
    src/**/*.py、tests/**/*.py、evidence/**/*.txt・*.md（いずれもUTF-8テキスト）を含む。
    """
    targets = [
        DATA_DIR / "operators.csv",
        DATA_DIR / "operators.json",
        DATA_DIR / "vehicles.csv",
        DATA_DIR / "vehicles.json",
    ]
    targets += list(RAW_TEXT_FILES)
    targets += list(NAME_SCAN_ROOT_FILES)
    targets += sorted((REPO_ROOT / "src").rglob("*.py"))
    targets += sorted((REPO_ROOT / "tests").rglob("*.py"))
    targets += sorted(EVIDENCE_DIR.rglob("*.txt"))
    targets += sorted(EVIDENCE_DIR.rglob("*.md"))
    return targets


def setUpModule():
    # data/ を今回のパーサ実装で最新化してからテストする
    parse_module.main()


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class RegistrationBlockRealPdfTest(unittest.TestCase):
    """extract_registration_block() の実測テスト（今回の増分の必須実装1・2）。

    SPEC.md §3.4(b) の旧市町村運営番号「中山市」接頭辞を、明示マップだけで
    安全に分解できること、既存の000271730.pdfも退行がないことを両方確認する。
    000230003.pdf の3団体は同一ファイル内で旧体系（第1号・第4号 = 中山市福）と
    現行表記（第3号 = 中山福、市なし）が混在するが、いずれも authority_code=中山 になる。
    """

    EXPECTED = {
        (PDF1.name, 1): ("中山", "福", "1"),  # 中山福第1号
        (PDF1.name, 2): ("中山", "福", "3"),  # 中山福第3号
        (PDF1.name, 3): ("中山", "福", "4"),  # 中山福第4号
        (PDF1.name, 4): ("中山", "福", "6"),  # 中山福第6号
        (PDF2.name, 1): ("中山", "福", "1"),  # 中山市福第1号
        (PDF2.name, 2): ("中山", "福", "3"),  # 中山福第3号（市なし）
        (PDF2.name, 3): ("中山", "福", "4"),  # 中山市福第4号
    }

    def test_extract_registration_block_matches_expected(self):
        import pdfplumber

        checked = 0
        for pdf_path in PDF_PATHS:
            with pdfplumber.open(pdf_path) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    words = page.extract_words()
                    reg = parse_module.extract_registration_block(words)
                    key = (pdf_path.name, page_no)
                    expected = self.EXPECTED[key]
                    self.assertEqual(
                        (reg["authority_code"], reg["service_type_code"], reg["serial_no"]),
                        expected,
                        f"{key}: registration block ({reg['authority_code']}, "
                        f"{reg['service_type_code']}, {reg['serial_no']}) != {expected}",
                    )
                    checked += 1
        self.assertEqual(checked, 7, "7ページ全件を確認できていない")


class CompositeKeyTotalsTest(unittest.TestCase):
    """SPEC.md §5-1, §5-4: 2PDF・7団体の件数と複合キーの一意性。"""

    @classmethod
    def setUpClass(cls):
        cls.operators = read_csv(DATA_DIR / "operators.csv")
        cls.vehicles = read_csv(DATA_DIR / "vehicles.csv")

    def test_operator_counts_per_file_and_total(self):
        self.assertEqual(len(self.operators), 7, "団体数の合計が7件でない")
        by_file = {}
        for op in self.operators:
            by_file[op["source_pdf"]] = by_file.get(op["source_pdf"], 0) + 1
        self.assertEqual(by_file.get(PDF1.name), 4, f"{PDF1.name}の団体数が4件でない")
        self.assertEqual(by_file.get(PDF2.name), 3, f"{PDF2.name}の団体数が3件でない")

    def test_composite_key_is_unique(self):
        keys = [(op["source_pdf"], op["registration_no"]) for op in self.operators]
        self.assertEqual(
            len(keys), len(set(keys)),
            f"(source_pdf, registration_no) の複合キーに重複がある: {keys}",
        )

    def test_registration_no_alone_duplicates_only_for_dai3gou(self):
        """registration_no単独の重複は正常。中山福第3号が2ファイルに1件ずつ(SPEC.md §5-4)。"""
        regs = [op["registration_no"] for op in self.operators]
        dup = sorted({r for r in regs if regs.count(r) > 1})
        self.assertEqual(dup, ["中山福第3号"], f"registration_no単独の重複が想定と違う: {dup}")
        files_for_dup = sorted(
            op["source_pdf"] for op in self.operators if op["registration_no"] == "中山福第3号"
        )
        self.assertEqual(files_for_dup, sorted([PDF1.name, PDF2.name]))

    def test_vehicle_row_and_grand_totals(self):
        self.assertEqual(len(self.vehicles), 23, "vehicles.csvの行数が23行でない")
        by_file = {}
        for v in self.vehicles:
            by_file[v["source_pdf"]] = by_file.get(v["source_pdf"], 0) + 1
        self.assertEqual(by_file.get(PDF1.name), 11, f"{PDF1.name}のvehicles行数が11行でない")
        self.assertEqual(by_file.get(PDF2.name), 12, f"{PDF2.name}のvehicles行数が12行でない")

        total = sum(int(v["count"]) for v in self.vehicles if v["vehicle_type"] != "合計")
        total_kei = sum(
            int(v["count_kei"]) for v in self.vehicles
            if v["vehicle_type"] != "合計" and v["count_kei"] != ""
        )
        self.assertEqual(total, 23, "全団体の車両合計(count)が23台でない")
        self.assertEqual(total_kei, 16, "全団体の車両合計(count_kei)が16台でない")


class VehicleTotalsTest(unittest.TestCase):
    """SPEC.md §5-2, §5-3: 車両合計の照合と count_kei <= count の不変条件。

    団体の識別は複合キー (source_pdf, registration_no)。中山福第3号は2ファイルに
    1件ずつ存在するため、registration_no単独でグループ化してはならない。
    """

    @classmethod
    def setUpClass(cls):
        cls.operators = read_csv(DATA_DIR / "operators.csv")
        cls.vehicles = read_csv(DATA_DIR / "vehicles.csv")

    def test_count_sum_matches_vehicles_total(self):
        by_key = {}
        for v in self.vehicles:
            if v["vehicle_type"] == "合計":
                continue  # 合計行自体は内訳の合計に含めない(§5-2「合計以外の行」)
            key = (v["source_pdf"], v["registration_no"])
            by_key.setdefault(key, {"count": 0, "count_kei": 0})
            by_key[key]["count"] += int(v["count"])
            kei = v["count_kei"]
            by_key[key]["count_kei"] += int(kei) if kei != "" else 0

        self.assertEqual(len(self.operators), 7, "団体数が7件でない")
        for op in self.operators:
            key = (op["source_pdf"], op["registration_no"])
            totals = by_key.get(key, {"count": 0, "count_kei": 0})
            self.assertEqual(
                totals["count"], int(op["vehicles_total"]),
                f"{key}: vehicles.csvのcount合計({totals['count']}) != "
                f"operators.csvのvehicles_total({op['vehicles_total']})",
            )
            self.assertEqual(
                totals["count_kei"], int(op["vehicles_total_kei"]),
                f"{key}: vehicles.csvのcount_kei合計({totals['count_kei']}) != "
                f"operators.csvのvehicles_total_kei({op['vehicles_total_kei']})",
            )

    def test_count_kei_le_count(self):
        """count_kei が空文字列の行は、その車種列に(軽)欄が構造的に無い(バス列のみ)ため対象外。"""
        checked = 0
        for v in self.vehicles:
            if v["count_kei"] == "":
                continue
            checked += 1
            self.assertLessEqual(
                int(v["count_kei"]), int(v["count"]),
                f"{v['source_pdf']} {v['registration_no']} {v['vehicle_type']}: "
                f"count_kei({v['count_kei']}) > count({v['count']})。抽出誤りの疑い",
            )
        self.assertGreater(checked, 0, "count_kei を持つ行が1件も無い(抽出漏れの疑い)")


class NewPdfVehicleDetailTest(unittest.TestCase):
    """SPEC.md §5-1, §7: 000230003.pdf(新規増分)の車両12行の実測値。"""

    @classmethod
    def setUpClass(cls):
        cls.vehicles = [v for v in read_csv(DATA_DIR / "vehicles.csv") if v["source_pdf"] == PDF2.name]
        cls.operators = {
            op["registration_no"]: op
            for op in read_csv(DATA_DIR / "operators.csv")
            if op["source_pdf"] == PDF2.name
        }

    def test_row_count_is_12(self):
        self.assertEqual(len(self.vehicles), 12, f"{PDF2.name}のvehicles行数が12行でない")

    def test_all_ownership_is_empty(self):
        """所有区分の列が無いファイルなのでownershipは全行空(SPEC.md §3.2)。"""
        for v in self.vehicles:
            self.assertEqual(v["ownership"], "", f"{v}: ownershipが空でない")

    def test_dai4gou_office_seq_1_to_4_with_kei_1_0_1_0(self):
        rows = [
            v for v in self.vehicles
            if v["registration_no"] == "中山市福第4号" and v["vehicle_type"] == "車いす車"
        ]
        by_seq = {int(v["office_seq"]): v for v in rows}
        self.assertEqual(sorted(by_seq), [1, 2, 3, 4], "第4号のoffice_seqが1..4でない")
        expected_kei = {1: "1", 2: "0", 3: "1", 4: "0"}
        for seq, kei in expected_kei.items():
            self.assertEqual(by_seq[seq]["count"], "1", f"office_seq={seq}のcountが1でない")
            self.assertEqual(
                by_seq[seq]["count_kei"], kei, f"office_seq={seq}のcount_keiが{kei}でない",
            )

    def test_operator_totals_and_pages(self):
        op1 = self.operators["中山市福第1号"]
        self.assertEqual(op1["source_page"], "1")
        self.assertEqual(op1["vehicles_total"], "1")
        self.assertEqual(op1["vehicles_total_kei"], "1")

        op3 = self.operators["中山福第3号"]
        self.assertEqual(op3["source_page"], "2")
        self.assertEqual(op3["vehicles_total"], "1")
        self.assertEqual(op3["vehicles_total_kei"], "1")

        op4 = self.operators["中山市福第4号"]
        self.assertEqual(op4["vehicles_total"], "4")
        self.assertEqual(op4["vehicles_total_kei"], "2")


class RegistrationConsistencyTest(unittest.TestCase):
    """SPEC.md §5-4: 登録番号の整合(7団体全件)。"""

    @classmethod
    def setUpClass(cls):
        cls.operators = read_csv(DATA_DIR / "operators.csv")

    def test_service_type_code_is_fukushi_for_all(self):
        self.assertEqual(len(self.operators), 7)
        for op in self.operators:
            self.assertEqual(
                op["service_type_code"], "福",
                f"{op['source_pdf']} {op['registration_no']}: service_type_codeが福でない",
            )

    def test_authority_code_is_uniform_nakayama(self):
        codes = {op["authority_code"] for op in self.operators}
        self.assertEqual(codes, {"中山"}, f"authority_codeが全件「中山」でない: {codes}")

    def test_operator_type_by_file(self):
        for op in self.operators:
            if op["source_pdf"] == PDF1.name:
                self.assertEqual(op["operator_type"], "NPO等", f"{PDF1.name}のoperator_typeがNPO等でない")
            elif op["source_pdf"] == PDF2.name:
                self.assertEqual(op["operator_type"], "市町村営", f"{PDF2.name}のoperator_typeが市町村営でない")
            else:
                self.fail(f"想定外のsource_pdf: {op['source_pdf']}")


class OfficeFlagsTest(unittest.TestCase):
    """SPEC.md §5-7, §3.6: 事務所情報の不一致フラグ(複合キー版、2PDF・7団体)。

    比較の前処理(全角→半角、空白除去)で解消する表記差(中山福第1号の位置、
    中山福第3号の名称)はフラグを立てない。前処理をしても一致しない場合、
    office_name が不一致なら office_mismatch、office_name は一致し
    office_location のみ不一致なら office_notation_diff とする。
    """

    EXPECTED_FLAGS = {
        (PDF1.name, "中山福第1号"): "",
        (PDF1.name, "中山福第3号"): "",
        (PDF1.name, "中山福第4号"): "office_notation_diff",
        (PDF1.name, "中山福第6号"): "office_mismatch",
        (PDF2.name, "中山市福第1号"): "office_mismatch",
        (PDF2.name, "中山福第3号"): "",
        (PDF2.name, "中山市福第4号"): "",
    }

    @classmethod
    def setUpClass(cls):
        cls.operators = read_csv(DATA_DIR / "operators.csv")
        cls.vehicles = read_csv(DATA_DIR / "vehicles.csv")

    def test_office_flags_match_composite_key_expected_values(self):
        by_key = {(op["source_pdf"], op["registration_no"]): op["flags"] for op in self.operators}
        self.assertEqual(
            set(by_key), set(self.EXPECTED_FLAGS),
            "operators.csv の複合キー集合が期待値と一致しない",
        )
        for key, expected in self.EXPECTED_FLAGS.items():
            self.assertEqual(
                by_key[key], expected,
                f"{key}: flags({by_key[key]!r}) != 期待値({expected!r})",
            )

    def test_dai4gou_office_name_location_element_counts_and_seq(self):
        """中山市福第4号は4事務所。名称/位置の要素数・順序が欠落せず、
        車両欄側の office_seq も 1..4 で揃うことを確認する(SPEC.md §5-7)。"""
        op = next(
            op for op in self.operators
            if (op["source_pdf"], op["registration_no"]) == (PDF2.name, "中山市福第4号")
        )
        names = op["office_name"].split(";")
        locations = op["office_location"].split(";")
        self.assertEqual(len(names), 4, "第4号のoffice_nameが4要素でない")
        self.assertEqual(len(locations), 4, "第4号のoffice_locationが4要素でない")

        veh_seqs = sorted({
            int(v["office_seq"]) for v in self.vehicles
            if v["source_pdf"] == PDF2.name and v["registration_no"] == "中山市福第4号"
        })
        self.assertEqual(veh_seqs, [1, 2, 3, 4], "第4号の車両側office_seqが1..4でない")


class RepresentativeNameNotOutputTest(unittest.TestCase):
    """SPEC.md §5-8, CLAUDE.md「代表者の氏名は抽出も出力もしない」。

    実際の氏名をこのテストファイル自体に書き残さないため、2PDF・7ページ全件から
    「代表者の氏名」ラベルの右側の語を都度動的に抽出し、その値が
    `discover_name_scan_targets()` が返す全ファイル（data/配下、raw/text/配下、
    src/**/*.py、tests/**/*.py、verification.md・PROGRESS.md・README.md・SPEC.md・
    CLAUDE.md、evidence/**/*.txt・*.md）のいずれにも含まれていないことを確認する
    （SPEC.md §5-8「テキスト形式のevidenceに含まれないことを自動テストに入れる」）。
    raw/text/ 側は氏名の値そのものではなく [氏名-非出力] に置換されていること
    （SPEC.md §4.4, rev.4.4）も併せて確認する。raw/*.pdf・evidence/*.png は
    検査対象外（SPEC.md §5-8、テキストではないため）。
    """

    def test_representative_name_absent_from_derived_text(self):
        """discover_name_scan_targets() の全対象に、代表者の実氏名(役職語を除く)が
        1文字も残っていないことを検査する。

        役職語(理事長・市長など、ROLE_WORDS)は個人を特定しないため候補から除外し、
        役職語だけが一致しても失敗にしない(要件2)。assertion失敗時のメッセージには
        氏名候補やファイル全文を含めない(assertNotInではなくassertFalseで、operandに
        機密文字列を渡さない、要件4)。
        """
        import pdfplumber

        targets = discover_name_scan_targets()
        # 対象ファイルごとにスペース類を除去した内容を1度だけ用意する(要件3の「空白等を正規化」)。
        normalized_contents = {
            p: _normalize_spaces(p.read_text(encoding="utf-8")) for p in targets
        }

        checked_pages = 0
        checked_candidates = 0
        for pdf_path in PDF_PATHS:
            with pdfplumber.open(pdf_path) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    words = page.extract_words()
                    label = parse_module.find_word(words, "代表者の氏名", x_max=150, top_max=220)
                    self.assertIsNotNone(label, f"{pdf_path.name} p{page_no}: 「代表者の氏名」ラベルが見つからない")
                    row = parse_module.words_in_box(
                        words, x0=150, top=label["top"] - 2, bottom=label["bottom"] + 2
                    )
                    self.assertTrue(row, f"{pdf_path.name} p{page_no}: 代表者の氏名が空で取得できていない")

                    # 役職語(理事長・市長 等)は氏名候補から除外する(要件2)。
                    name_words = [w["text"] for w in row if not _is_role_word(w["text"])]
                    self.assertTrue(
                        name_words,
                        f"{pdf_path.name} p{page_no}: 役職語を除くと氏名候補が空になった"
                        "(抽出範囲がラベル自体しか捉えていない疑い)",
                    )
                    checked_pages += 1

                    # 空白等を正規化した実氏名全体、および役職を除いた氏名構成語(2文字以上)を候補にする。
                    candidates = {_normalize_spaces("".join(name_words))}
                    candidates.update(
                        _normalize_spaces(part) for part in name_words if len(part) >= 2
                    )
                    candidates = {c for c in candidates if c}

                    for candidate in candidates:
                        checked_candidates += 1
                        for path, ncontent in normalized_contents.items():
                            found = candidate in ncontent
                            # assertNotInは失敗時にoperand(氏名候補・ファイル全文)をそのまま
                            # 差分表示に出すため使わない。assertFalseなら真偽値のみが表示される。
                            self.assertFalse(
                                found,
                                f"{pdf_path.name} p{page_no}: 代表者氏名に由来する文字列が "
                                f"{path.relative_to(REPO_ROOT)} に含まれている疑い"
                                "(絶対厳守違反、詳細は氏名漏えい防止のため非表示)",
                            )
        self.assertEqual(checked_pages, 7, "2PDF・7ページ全件を確認できていない")
        self.assertGreater(checked_candidates, 0, "氏名候補が1件も生成されていない")
        self.assertGreaterEqual(
            len(targets), 12,
            f"検査対象ファイル数が想定より少ない({len(targets)}件)。discover_name_scan_targets()を確認",
        )

    def test_raw_text_files_have_redaction_marker(self):
        """各raw/textファイルに[氏名-非出力]が1件以上あること(SPEC.md §4.4)。"""
        for path in RAW_TEXT_FILES:
            content = path.read_text(encoding="utf-8")
            self.assertGreaterEqual(
                content.count("[氏名-非出力]"), 1,
                f"{path.name}: 伏字マーカー[氏名-非出力]が1件も無い",
            )

    def test_no_representative_column_in_schema(self):
        suspicious = ("代表者", "氏名", "daihyo", "representative")
        for path in (DATA_DIR / "operators.csv", DATA_DIR / "vehicles.csv"):
            with path.open(encoding="utf-8") as f:
                header = f.readline()
            for word in suspicious:
                self.assertNotIn(word, header, f"{path.name} の列見出しに {word!r} を示唆する語がある")


class CsvJsonEquivalenceTest(unittest.TestCase):
    """CSVとJSONの行内容が同じであることを確認する(今回の増分の必須実装8)。"""

    def _assert_rows_equal(self, csv_path, json_path):
        csv_rows = read_csv(csv_path)
        with json_path.open(encoding="utf-8") as f:
            json_rows = json.load(f)
        self.assertEqual(
            len(csv_rows), len(json_rows),
            f"{csv_path.name}({len(csv_rows)}行) と {json_path.name}({len(json_rows)}行) の行数が違う",
        )
        for i, (csv_row, json_row) in enumerate(zip(csv_rows, json_rows)):
            json_row_as_str = {k: ("" if v is None else str(v)) for k, v in json_row.items()}
            self.assertEqual(
                csv_row, json_row_as_str,
                f"{csv_path.name}/{json_path.name} の{i}行目の内容が一致しない",
            )

    def test_operators_csv_and_json_match(self):
        self._assert_rows_equal(DATA_DIR / "operators.csv", DATA_DIR / "operators.json")

    def test_vehicles_csv_and_json_match(self):
        self._assert_rows_equal(DATA_DIR / "vehicles.csv", DATA_DIR / "vehicles.json")


if __name__ == "__main__":
    unittest.main()
