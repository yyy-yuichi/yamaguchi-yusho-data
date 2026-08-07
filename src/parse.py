"""自家用有償旅客運送者登録簿（道路運送法施行規則 第2号様式）のパーサ。

対象は raw/000271730.pdf（福祉有償運送・NPO等、山口県）の1本のみ（SPEC.md §1）。
実装方針は SPEC.md §4 に従う:

- pdfplumber の extract_words() で座標付きの語を取り、ラベル語の位置を基準に
  その右側・下側の語を拾う（extract_text() は空欄セルが消えるため使わない）。
- 車両欄の列境界・行境界はページごとに縦罫線/横罫線（page.edges）から導出する。
  テンプレート座標を固定で使い回さない（SPEC.md §4.1）。
- 代表者の氏名は抽出しない（絶対厳守）。

生の中間テキストは raw/text/{pdfname}_p{n}.txt に保存する（SPEC.md §4.4）。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pdfplumber

REPO_ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = REPO_ROOT / "raw" / "000271730.pdf"
TEXT_DIR = REPO_ROOT / "raw" / "text"
DATA_DIR = REPO_ROOT / "data"

# 000271730.pdf は一覧ページ照合済みで「福祉有償運送 × NPO等」（山口県）と確定している
# （evidence/20260807_list_page_cp932_decode.txt、PROGRESS.md 2026-08-07 一覧ページ照合）。
# ファイル単位で決まる値であり、PDF本文中に自治体/NPOの別を示す記載は無いため定数として与える。
PREF = "山口県"
OPERATOR_TYPE = "NPO等"

SOURCE_PDF_NAME = PDF_PATH.name

# 旅客範囲の記号対応（道路運送法施行規則第49条第2号）。SPEC.md §3.1。
SCOPE_COLUMNS = {
    "イ": "scope_i_physical",
    "ロ": "scope_ro_mental",
    "ハ": "scope_ha_intellectual",
    "ニ": "scope_ni_care",
    "ホ": "scope_ho_support",
    "ヘ": "scope_he_checklist",
    "ト": "scope_to_other",
}
SCOPE_MARK_CHARS = set(SCOPE_COLUMNS) | {"二"}  # 「二」は「ニ」のフォント代替字（下記 normalize_scope_char 参照）

ERA_BASE = {"令和": 2018, "平成": 1988, "昭和": 1925}

OPERATORS_COLUMNS = [
    "registration_no", "registration_no_raw", "authority_code", "service_type_code",
    "serial_no", "pref", "transport_type", "operator_type", "org_name",
    "org_address", "org_address_raw", "service_area", "service_area_raw",
    "service_area_municipalities", "registered_date", "renewed_date",
    "valid_from", "valid_to",
    "scope_i_physical", "scope_ro_mental", "scope_ha_intellectual", "scope_ni_care",
    "scope_ho_support", "scope_he_checklist", "scope_to_other",
    "office_name", "office_location", "partner_operator_name", "partner_operator_address",
    "vehicles_total", "vehicles_total_kei", "source_pdf", "source_page", "flags",
]

VEHICLES_COLUMNS = [
    "registration_no", "office_seq", "office_name", "office_location", "ownership",
    "vehicle_type", "vehicle_type_label", "count", "count_kei", "source_pdf", "source_page",
]


# ---------------------------------------------------------------------------
# 正規化ユーティリティ（SPEC.md §4.3）
# ---------------------------------------------------------------------------

def to_halfwidth(s: str) -> str:
    """全角の英数字・記号を半角に正規化する。漢字・かな・カナは変更しない。

    全角 U+FF01-FF5E は ASCII 0x21-0x7E からの固定オフセット(0xFEE0)なので
    コードポイント変換で半角化できる。全角スペース(U+3000)と波ダッシュ(U+301C)は
    このレンジ外なので個別に対応する（000271730.pdf の実物で両方が出現する。
    p1等は～(U+FF5E)、p4は〜(U+301C)）。
    """
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif ch == "　":
            out.append(" ")
        elif ch == "〜":  # 〜 WAVE DASH
            out.append("~")
        else:
            out.append(ch)
    return "".join(out)


def normalize_scope_char(ch: str) -> str:
    """旅客範囲の記号を正規化する。

    000271730.pdf p2（中山福第3号）では、フォントの字形代替により
    カタカナ「ニ」が漢字「二」として抽出される
    （evidence/20260807_explore_words_edges.txt PAGE 2、
    x0=359.76 top=336.91 の語が "二"。目視確認は evidence/20260807_page_render-2.png）。
    """
    return "ニ" if ch == "二" else ch


def wareki_to_iso(era: str, year: str, month: str, day: str) -> str:
    """和暦を西暦 ISO 8601 に変換する（令和=2018+年、平成=1988+年、昭和=1925+年）。"""
    y = ERA_BASE[era] + int(year)
    return f"{y:04d}-{int(month):02d}-{int(day):02d}"


# ---------------------------------------------------------------------------
# 語・座標のユーティリティ
# ---------------------------------------------------------------------------

def word_cx(w):
    return (w["x0"] + w["x1"]) / 2


def word_cy(w):
    return (w["top"] + w["bottom"]) / 2


def words_in_box(words, x0=None, x1=None, top=None, bottom=None):
    out = []
    for w in words:
        cx, cy = word_cx(w), word_cy(w)
        if x0 is not None and cx < x0:
            continue
        if x1 is not None and cx > x1:
            continue
        if top is not None and cy < top:
            continue
        if bottom is not None and cy > bottom:
            continue
        out.append(w)
    return out


def join_words(words, gap_threshold=7.0):
    """x0順に並べ、語間の隙間が閾値を超えたら半角空白を挟んで連結する。

    第2号様式は「登 録 番 号」のように1文字ずつ広い字間で印字されたラベルと、
    「特定非営利活動法人 豆たん」のように単語間にスペースがある値が混在する。
    実測（evidence/20260807_explore_words_edges.txt）では前者の字間は約5pt、
    後者の語間は約10pt。7ptを閾値にすると両方を正しく再現できる。
    """
    ws = sorted(words, key=lambda w: w["x0"])
    parts = []
    prev_x1 = None
    for w in ws:
        if prev_x1 is not None and w["x0"] - prev_x1 > gap_threshold:
            parts.append(" ")
        parts.append(w["text"])
        prev_x1 = w["x1"]
    return "".join(parts)


def find_word(words, text, x_max=None, top_max=None):
    """text と完全一致する語を探す（x0<x_max, top<top_max で絞り込み）。"""
    candidates = [w for w in words
                  if w["text"] == text
                  and (x_max is None or w["x0"] < x_max)
                  and (top_max is None or w["top"] < top_max)]
    if not candidates:
        return None
    candidates.sort(key=lambda w: w["top"])
    return candidates[0]


def cluster_x(values, tol=2.0):
    """x座標の列を、差がtol未満のものを1本として畳んで昇順に返す（SPEC.md §4.1 手順2-3）。"""
    xs = sorted(values)
    merged = []
    for x in xs:
        if merged and x - merged[-1] < tol:
            continue
        merged.append(x)
    return merged


# ---------------------------------------------------------------------------
# ページ上部（登録事項）の抽出
# ---------------------------------------------------------------------------

def extract_registration_block(words):
    """「登録番号」ラベルの位置から registration_no_raw を取り、構造を分解する。

    構造は SPEC.md §3.4(b): 〔運輸局頭1字〕〔運輸支局頭1字〕〔種別1字〕第〔一連番号〕号
    """
    label = find_word(words, "登", x_max=150, top_max=150)
    if label is None:
        raise ValueError("「登録番号」ラベルが見つからない")
    row = words_in_box(words, x0=200, top=label["top"] - 3, bottom=label["bottom"] + 3)
    raw = join_words(row)
    normalized = to_halfwidth(raw)
    m = re.match(r"^(.+?)([福交])第(\d+)号$", normalized)
    if not m:
        raise ValueError(f"登録番号の形式が想定と違う: {normalized!r}")
    authority_code, service_type_code, serial_no = m.groups()
    return {
        "registration_no": normalized,
        "registration_no_raw": raw,
        "authority_code": authority_code,
        "service_type_code": service_type_code,
        "serial_no": serial_no,
    }


def extract_dates(words):
    """登録年月日及び更新登録年月日を抽出する。

    実物では2パターンが混在する（evidence/20260807_explore_words_edges.txt で全ページ確認、
    evidence/20260807_page_render-*.png で目視確認済み）:

    - 「登録年月日：」「更新登録年月日：」の接頭辞付きで両方が別行に印字される
      （p3=中山福第４号のみ。原登録日と更新後の有効期間が別々にわかる）
    - 接頭辞なしで「開始日～終了日」の1行のみが印字される（p1・p2・p4）。
      この場合、原登録年月日はこの様式上どこにも印字されておらず空とする。
      更新登録年月日・有効期間の開始は同じ日付、終了は範囲の終わりを使う。
    """
    label1 = find_word(words, "登録年月日及び", x_max=200, top_max=200)
    label2 = find_word(words, "更新登録年月日", x_max=200, top_max=200)
    if label1 is None or label2 is None:
        raise ValueError("登録年月日ラベルが見つからない")
    row = words_in_box(words, x0=150, top=label1["top"] - 2, bottom=label2["bottom"] + 2)
    text = to_halfwidth(join_words(row, gap_threshold=3.0))

    m_reg = re.search(r"登録年月日[：:]\s*(令和|平成|昭和)(\d+)年(\d+)月(\d+)日(?!.*~)", text)
    m_upd = re.search(r"更新登録年月日[：:]\s*(令和|平成|昭和)(\d+)年(\d+)月(\d+)日\s*~\s*(令和|平成|昭和)(\d+)年(\d+)月(\d+)日", text)

    if m_upd:
        registered_date = wareki_to_iso(*m_reg.groups()) if m_reg else ""
        renewed_date = wareki_to_iso(*m_upd.groups()[0:4])
        valid_from = renewed_date
        valid_to = wareki_to_iso(*m_upd.groups()[4:8])
        return registered_date, renewed_date, valid_from, valid_to

    # 接頭辞なし: 「開始日~終了日」の1行のみ
    m_range = re.search(r"(令和|平成|昭和)(\d+)年(\d+)月(\d+)日\s*~\s*(令和|平成|昭和)(\d+)年(\d+)月(\d+)日", text)
    if not m_range:
        raise ValueError(f"登録年月日の形式が想定と違う: {text!r}")
    valid_from = wareki_to_iso(*m_range.groups()[0:4])
    valid_to = wareki_to_iso(*m_range.groups()[4:8])
    return "", valid_from, valid_from, valid_to


def extract_org_name(words):
    label = find_word(words, "名", x_max=150, top_max=170)
    if label is None:
        raise ValueError("「名称」（団体名）ラベルが見つからない")
    row = words_in_box(words, x0=150, top=label["top"] - 2, bottom=label["bottom"] + 2)
    return join_words(row)


def extract_org_address(words):
    label = find_word(words, "住", x_max=150, top_max=220)
    if label is None:
        raise ValueError("「住所」ラベルが見つからない")
    row = words_in_box(words, x0=150, top=label["top"] - 2, bottom=label["bottom"] + 2)
    raw = join_words(row)
    return to_halfwidth(raw), raw


def extract_transport_type(words):
    label = find_word(words, "運送の種別", x_max=150, top_max=400)
    if label is None:
        raise ValueError("「運送の種別」ラベルが見つからない")
    # 値は同じ枠内でラベルより上の行（○の選択マークはラベルの下なので除外される）
    # このセルは「福」「祉」等が1文字ずつ別語として抽出される（実測で字間約5.04pt）。
    # 語間の意味的な区切りではないため、詰めて連結する
    # （extract_vehicle_table の列ヘッダ結合と同じ考え方）。
    row = words_in_box(words, x0=150, x1=450, top=label["top"] - 16, bottom=label["top"] - 2)
    text = join_words(row, gap_threshold=100)
    if text not in ("福祉有償運送", "交通空白地有償運送"):
        raise ValueError(f"運送の種別が想定と違う: {text!r}")
    return text


def extract_service_area(words):
    label1 = find_word(words, "路線又は", x_max=150, top_max=350)
    label2 = find_word(words, "運送の区域", x_max=150, top_max=350)
    if label1 is None or label2 is None:
        raise ValueError("「運送の区域」ラベルが見つからない")
    row = words_in_box(words, x0=150, top=label1["top"] - 2, bottom=label2["bottom"] + 2)
    raw = join_words(row)
    normalized = to_halfwidth(raw)
    # 市町名: 最初の全角/半角括弧より前の部分から「〜市/町/村」を取る
    # （括弧内の注記にも「町」等が出現しうるため、括弧の前だけを見る。SPEC.md 未規定・実物のみで判断）
    prefix = re.split(r"[（(]", normalized)[0]
    muni = []
    for chunk in re.split(r"[、,]", prefix):
        m = re.match(r"^(.+?[市町村])", chunk)
        if m:
            muni.append(m.group(1))
    return normalized, raw, ";".join(muni)


def extract_scope_flags(words):
    label1 = find_word(words, "運送する", x_max=150, top_max=400)
    label2 = find_word(words, "旅客の範囲", x_max=150, top_max=400)
    if label1 is None or label2 is None:
        raise ValueError("「旅客の範囲」ラベルが見つからない")
    row = words_in_box(words, x0=150, top=label1["top"] - 2, bottom=label2["bottom"] + 2)
    row = sorted(row, key=lambda w: w["x0"])

    # 凡例文言(SPEC.md §3.1: 「…ヘ．基本チェックリスト ト その他」)は固定であり、
    # 実測(全4ページ)では「イ．」〜「ヘ．」は説明文と結合した1語のまま分割されないが、
    # 「ト」だけは「その他」が改行等で分離して単独語になりうる
    # (p1は"ト"+"そ"+"の他）"の3語に分裂、p3は"その他"のみ単独語、p4は3行に折り返して
    # "ト"と"その他）"が別々の行になる。全てevidence/20260807_page_render-*.pngで目視確認済み)。
    # そこで、欄内に「その他」を含む語(または単独の「そ」)が1つでもあれば、
    # 候補「ト」は凡例の断片とみなして除外する。無ければ(p2のように凡例が無いページ)
    # 「ト」候補もそのままマークとして採用する。イ〜ヘは常に説明文と結合しているため、
    # 裸の1文字で出現するのは選択マークの場合のみであり、除外判定は不要。
    legend_has_sonota = any(("その他" in w["text"]) or (w["text"] == "そ") for w in row)

    marks = []
    for w in row:
        ch = normalize_scope_char(w["text"])
        if ch not in SCOPE_MARK_CHARS:
            continue
        if ch == "ト" and legend_has_sonota:
            continue
        marks.append(w)

    flags = {col: 0 for col in SCOPE_COLUMNS.values()}
    for w in marks:
        ch = normalize_scope_char(w["text"])
        flags[SCOPE_COLUMNS[ch]] = 1
    return flags


def extract_office_block(words):
    """事務所の名称及び位置（ページ上部）を1件抽出する。

    観測範囲（000271730.pdf 全4ページ）では事務所は1団体1件のみ。
    複数事務所が続く場合の分割は未確認（SPEC.md §9 U2）。
    """
    label_meishou = find_word(words, "事務所の名称", x_max=150, top_max=300)
    label_oyobi = find_word(words, "及び位置", x_max=150, top_max=300)
    label_next = find_word(words, "路線又は", x_max=150, top_max=350)
    if label_meishou is None or label_oyobi is None or label_next is None:
        raise ValueError("「事務所の名称及び位置」ラベルが見つからない")

    # ミニ見出し「名称」「位置」の下端から、次のラベル行までがデータ行。
    # 座標ボックスではなくテキスト完全一致で拾う（座標ボックスだと実データ行まで
    # 巻き込んでしまうことが実測で判明した。データ行を含めると header_bottom が
    # ずれて office_name/office_location が空になる）。
    mini_header_words = words_in_box(words, x0=150, top=label_meishou["top"] - 2, bottom=label_oyobi["bottom"] + 15)
    mini_headers = [w for w in mini_header_words if w["text"] in ("名", "称", "位", "置")]
    if not mini_headers:
        raise ValueError("事務所名称/位置のミニ見出し（名/称/位/置）が見つからない")
    header_bottom = max(w["bottom"] for w in mini_headers)

    return header_bottom, label_next["top"]


def extract_partner_operator(words, top, bottom):
    row = words_in_box(words, x0=150, top=top, bottom=bottom)
    text = join_words(row)
    # 未記入なら空。氏名又は名称/住所が2組あるが、山口県4ファイルでは全件空欄（実測）。
    return text.strip()


# ---------------------------------------------------------------------------
# 車両欄の抽出（SPEC.md §4.1, §4.2）
# ---------------------------------------------------------------------------

CELL_TOTAL_RE = re.compile(r"^\d+$")
CELL_KEI_RE = re.compile(r"^[(（]\s*(\d*)\s*[)）]$")


def extract_vehicle_table(page, words):
    header_label = find_word(words, "自家用有償旅客運送自動車の数", top_max=None)
    if header_label is None:
        raise ValueError("車両欄の見出しが見つからない")

    v_edges = [e for e in page.edges if e.get("orientation") == "v" and e["top"] >= header_label["top"] - 5]
    if not v_edges:
        raise ValueError("車両欄の罫線が見つからない")
    table_top = min(e["top"] for e in v_edges)
    table_bottom = max(e["bottom"] for e in v_edges)

    # 列境界: 表の最下端まで届く縦罫線のうち、事務所名・位置列より右側(x>260)にあるもの
    col_edges = [e for e in v_edges if e["bottom"] >= table_bottom - 2 and e["x0"] > 260]
    col_bounds = cluster_x([e["x0"] for e in col_edges])
    if len(col_bounds) != 8:
        raise ValueError(f"車両欄の列境界が7列(境界8本)にならない: {col_bounds}")

    # 事務所名称/位置列と所有区分列の境界。「所有」「持込」の実測中心xは全4ページで
    # 260を超える(264.48〜271.44)ため、x1=260 の固定しきい値では拾えない。
    # この境界の縦罫線(p1=247.92, p2=243.84, p3=245.88, p4=246.36 付近、表全高)から動的に導出する。
    owner_edges = [e for e in v_edges if e["bottom"] >= table_bottom - 2 and 200 < e["x0"] <= 260]
    owner_dividers = cluster_x([e["x0"] for e in owner_edges])
    if len(owner_dividers) != 1:
        raise ValueError(f"事務所名称/位置と所有区分の列境界が1本にならない: {owner_dividers}")
    owner_divider = owner_dividers[0]

    # 行境界: 表内の横罫線のうち、幅100pt超で、列見出しの下端より下にあるもの
    header_words = words_in_box(words, top=table_top, bottom=table_top + 65)
    header_text_bottom = max(w["bottom"] for w in header_words) if header_words else table_top
    h_edges = [e for e in page.edges
               if e.get("orientation") == "h"
               and (e["x1"] - e["x0"]) > 100
               and e["top"] > header_text_bottom - 2
               and e["top"] <= table_bottom + 2]
    row_bounds = cluster_x([e["top"] for e in h_edges])
    if len(row_bounds) != 3:
        raise ValueError(f"車両欄の行境界が2行(境界3本)にならない: {row_bounds}")

    # 列ヘッダの文字列を列ごとに再構成し、種別名にマップする（SPEC.md §3.4(c): 動的にマップ）
    col_headers = []
    for x0, x1 in zip(col_bounds[:-1], col_bounds[1:]):
        hw = words_in_box(header_words, x0=x0, x1=x1)
        label_text = join_words(hw, gap_threshold=100)  # このセル内は詰めて連結
        col_headers.append(label_text)

    def map_vehicle_type(label_text):
        mapping = [
            ("寝台車", "寝台車"), ("車いす", "車いす車"), ("兼用車", "兼用車"),
            ("回転", "回転シート車"), ("シート", "回転シート車"),
            ("セダン", "セダン等"), ("バス", "バス"), ("合計", "合計"),
        ]
        for key, vtype in mapping:
            if key in label_text:
                return vtype
        raise ValueError(f"車種列のラベルを解釈できない: {label_text!r}")

    vehicle_types = [map_vehicle_type(h) for h in col_headers]
    has_kei = ["軽" in h for h in col_headers]

    ownership_rows = []
    for i in range(len(row_bounds) - 1):
        top, bottom = row_bounds[i], row_bounds[i + 1]
        row_words = words_in_box(words, x0=owner_divider, top=top, bottom=bottom)
        # 所有区分ラベル(所有/持込)は owner_divider と車両欄(col_bounds[0])の間の列にある
        # (事務所名称/位置は owner_divider より左)
        label_words = words_in_box(words, x0=owner_divider, x1=col_bounds[0], top=top, bottom=bottom)
        label_text = join_words(label_words)
        if "所有" in label_text:
            ownership = "所有"
        elif "持込" in label_text:
            ownership = "持込"
        else:
            raise ValueError(f"所有区分ラベルを解釈できない: {label_text!r}")

        cells = []
        for ci, (x0, x1) in enumerate(zip(col_bounds[:-1], col_bounds[1:])):
            cell_words = words_in_box(row_words, x0=x0, x1=x1)
            total = 0
            kei = None
            for w in cell_words:
                t = w["text"]
                if CELL_TOTAL_RE.match(t):
                    total = int(t)
                else:
                    m = CELL_KEI_RE.match(t)
                    if m:
                        kei = int(m.group(1)) if m.group(1) else 0
            # 空の括弧・括弧なし・素の0はいずれも軽0台として扱う(SPEC.md §3.4(a))。
            # 持込行の合計列など、括弧自体が全く印字されないセルもある(実測)。
            if kei is None and has_kei[ci]:
                kei = 0
            cells.append({
                "vehicle_type": vehicle_types[ci],
                "vehicle_type_label": col_headers[ci],
                "count": total,
                "count_kei": kei if has_kei[ci] else "",
            })

        # 事務所名/位置(車両欄側): 所有行に名称、持込行に位置が印字される
        # (evidence/20260807_explore_words_edges.txt 全4ページで確認。SPEC.md 未規定・実物のみで判断)
        office_text_words = words_in_box(words, x0=150, x1=owner_divider, top=top, bottom=bottom)
        office_text_words = [w for w in office_text_words if w["text"] not in ("所有", "持込")]
        office_text = join_words(office_text_words)

        ownership_rows.append({"ownership": ownership, "cells": cells, "office_text": office_text})

    return ownership_rows


# ---------------------------------------------------------------------------
# 1ページ(1団体)の処理
# ---------------------------------------------------------------------------

def parse_page(page, page_no):
    words = page.extract_words()

    reg = extract_registration_block(words)
    registered_date, renewed_date, valid_from, valid_to = extract_dates(words)
    org_name = extract_org_name(words)
    org_address, org_address_raw = extract_org_address(words)
    transport_type = extract_transport_type(words)
    service_area, service_area_raw, service_area_municipalities = extract_service_area(words)
    scope_flags = extract_scope_flags(words)
    office_header_bottom, next_label_top = extract_office_block(words)

    office_value_words = words_in_box(words, x0=150, top=office_header_bottom, bottom=next_label_top - 2)
    if not office_value_words:
        raise ValueError("事務所の名称/位置のデータ行が見つからない")
    data_top = min(w["top"] for w in office_value_words)
    data_bottom = max(w["bottom"] for w in office_value_words)
    # 名称列・位置列の境界を、実データ行の縦範囲と重なる罫線から導出する。
    # (次ラベル位置の直前まで届く前提だと、実測でp1は7.06pt・p2は6.31pt罫線が
    #  短く、罫線が1本も見つからなかった。実データ行の範囲を基準にする)
    row_v_edges = [e for e in page.edges
                   if e.get("orientation") == "v"
                   and e["top"] <= data_bottom
                   and e["bottom"] >= data_top
                   and 200 < e["x0"] < 500]  # 500以上は表右端の外枠罫線(x~578)を除外するため
    dividers = cluster_x([e["x0"] for e in row_v_edges])
    if len(dividers) != 1:
        raise ValueError(f"事務所名称/位置の列境界が1本にならない: {dividers}")
    divider = dividers[0]
    office_name_top = join_words(words_in_box(office_value_words, x1=divider))
    office_location_top = join_words(words_in_box(office_value_words, x0=divider))

    # 事業者協力型の氏名又は名称/住所は山口県4ファイルでは全件空欄と実測済み
    # (evidence/20260807_page_render-{1..4}.png で目視確認)。空欄前提でハードコードするのではなく、
    # 想定外の値が入っていたら止める(推定で先に進まない)。
    partner_text = extract_partner_operator(words, top=office_header_bottom + 130, bottom=next_label_top + 90)
    if partner_text:
        raise ValueError(
            f"p{page_no}: 事業者協力型の氏名又は名称/住所欄に想定外の値がある: {partner_text!r}。"
            "空欄前提の実装なので、パーサを直す前にPROGRESS.mdに報告して止まること。"
        )

    vehicle_rows = extract_vehicle_table(page, words)

    # vehicles_total / vehicles_total_kei: 合計列の値を所有・持込の両行で合算する
    vehicles_total = 0
    vehicles_total_kei = 0
    for row in vehicle_rows:
        for cell in row["cells"]:
            if cell["vehicle_type"] == "合計":
                vehicles_total += cell["count"]
                vehicles_total_kei += cell["count_kei"] if cell["count_kei"] != "" else 0

    # 事務所名不一致フラグ(SPEC.md §3.6)。比較の直前だけ、全角/半角と語間スペースの
    # 有無を正規化する(保存する値自体は正規化しない。SPEC.md §4.3の「原文保持」を尊重する)。
    # 正規化しないと、以下のような表記差だけの箇所に誤ってフラグが立つ:
    # - 中山福第1号: 上部"下関市内日下１０２７－３"(全角) / 車両欄"1027-3"(半角)
    # - 中山福第3号: 上部"特定非営利活動法人 らいと"(語間9.84ptでjoin_wordsが空白を挿入) /
    #   車両欄"特定非営利活動法人らいと"(語間4.8ptで空白なし)。同一文字列の再現差であり、
    #   実際に印字された内容は同じ
    def normalize_for_compare(s):
        return to_halfwidth(s).replace(" ", "")

    flags = []
    vehicle_office_names = {r["ownership"]: r["office_text"] for r in vehicle_rows}
    veh_name = vehicle_office_names.get("所有", "")
    veh_loc = vehicle_office_names.get("持込", "")
    name_mismatch = bool(veh_name) and normalize_for_compare(veh_name) != normalize_for_compare(office_name_top)
    loc_mismatch = bool(veh_loc) and normalize_for_compare(veh_loc) != normalize_for_compare(office_location_top)
    if name_mismatch or loc_mismatch:
        flags.append("office_mismatch")

    operator = {
        "registration_no": reg["registration_no"],
        "registration_no_raw": reg["registration_no_raw"],
        "authority_code": reg["authority_code"],
        "service_type_code": reg["service_type_code"],
        "serial_no": reg["serial_no"],
        "pref": PREF,
        "transport_type": transport_type,
        "operator_type": OPERATOR_TYPE,
        "org_name": org_name,
        "org_address": org_address,
        "org_address_raw": org_address_raw,
        "service_area": service_area,
        "service_area_raw": service_area_raw,
        "service_area_municipalities": service_area_municipalities,
        "registered_date": registered_date,
        "renewed_date": renewed_date,
        "valid_from": valid_from,
        "valid_to": valid_to,
        **scope_flags,
        "office_name": office_name_top,
        "office_location": office_location_top,
        "partner_operator_name": "",
        "partner_operator_address": "",
        "vehicles_total": vehicles_total,
        "vehicles_total_kei": vehicles_total_kei,
        "source_pdf": SOURCE_PDF_NAME,
        "source_page": page_no,
        "flags": ";".join(flags),
    }

    vehicles = []
    office_seq = 1
    # SPEC.md §3.2: vehicles.csv の office_name/office_location は「車両欄側」の値であり
    # (ページ上部の office_name_top/office_location_top とは別)、所有/持込どちらの行にも
    # 同じ値(その事務所の名称・位置)を入れる。所有/持込は同一事務所の内訳にすぎない。
    for row in vehicle_rows:
        office_name = veh_name
        office_location = veh_loc
        for cell in row["cells"]:
            if cell["count"] == 0 and (cell["count_kei"] == "" or cell["count_kei"] == 0):
                continue  # 台数0の行は出力しない(SPEC.md §3.5「持込は0台なので行を出さない」)
            vehicles.append({
                "registration_no": reg["registration_no"],
                "office_seq": office_seq,
                "office_name": office_name,
                "office_location": office_location,
                "ownership": row["ownership"],
                "vehicle_type": cell["vehicle_type"],
                "vehicle_type_label": cell["vehicle_type_label"],
                "count": cell["count"],
                "count_kei": cell["count_kei"],
                "source_pdf": SOURCE_PDF_NAME,
                "source_page": page_no,
            })

    return operator, vehicles


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

def main():
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    operators = []
    vehicles = []

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            # 生テキストの保存(SPEC.md §4.4)
            text_path = TEXT_DIR / f"{PDF_PATH.stem}_p{page_no}.txt"
            text_path.write_text(page.extract_text() or "", encoding="utf-8")

            words = page.extract_words()
            # 団体の区切りは登録番号の出現で判定する(SPEC.md §4)。
            # このファイルは実測で1ページ1団体・登録番号ラベルはページ内に1回のみ
            # (evidence/20260807_explore_words_edges.txt で全4ページ確認)。
            anchors = [w for w in words if w["text"] == "登" and w["x0"] < 150 and w["top"] < 150]
            if len(anchors) != 1:
                raise ValueError(
                    f"p{page_no}: 登録番号ラベルの出現回数が1でない({len(anchors)}件)。"
                    "団体の区切り方の前提が崩れている可能性がある。止めて報告すること。"
                )

            operator, page_vehicles = parse_page(page, page_no)
            operators.append(operator)
            vehicles.extend(page_vehicles)

    with (DATA_DIR / "operators.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OPERATORS_COLUMNS)
        w.writeheader()
        w.writerows(operators)
    with (DATA_DIR / "operators.json").open("w", encoding="utf-8") as f:
        json.dump(operators, f, ensure_ascii=False, indent=2)

    with (DATA_DIR / "vehicles.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=VEHICLES_COLUMNS)
        w.writeheader()
        w.writerows(vehicles)
    with (DATA_DIR / "vehicles.json").open("w", encoding="utf-8") as f:
        json.dump(vehicles, f, ensure_ascii=False, indent=2)

    print(f"operators: {len(operators)} 件")
    print(f"vehicles: {len(vehicles)} 行")


if __name__ == "__main__":
    main()
