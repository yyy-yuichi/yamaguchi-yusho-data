"""自家用有償旅客運送者登録簿（道路運送法施行規則 第2号様式）のパーサ。

対象は raw/000271730.pdf（福祉有償運送・NPO等）、raw/000230003.pdf（福祉有償運送・
市町村営）、raw/000359215.pdf（交通空白地有償運送・市町村営）の3本
（SPEC.md §1、山口県4ファイルのうち取得済みの3ファイル）。
実装方針は SPEC.md §4 に従う:

- pdfplumber の extract_words() で座標付きの語を取り、ラベル語の位置を基準に
  その右側・下側の語を拾う（extract_text() は空欄セルが消えるため使わない）。
- 車両欄の列境界・行境界はページごとに縦罫線/横罫線（page.edges）から導出する。
  テンプレート座標を固定で使い回さない（SPEC.md §4.1）。
- ファイル固有の値（実施主体の別など）はファイルごとの設定として渡す。
  グローバル定数1組に固定しない（実施主体はファイルにより異なる。SPEC.md §2）。
- 代表者の氏名は抽出しない（絶対厳守）。

生の中間テキストは raw/text/{pdfname}_p{n}.txt に保存する（SPEC.md §4.4）。
代表者の氏名の値だけは座標で特定して [氏名-非出力] に置換する。
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import pdfplumber

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "raw"
TEXT_DIR = REPO_ROOT / "raw" / "text"
DATA_DIR = REPO_ROOT / "data"

PREF = "山口県"

# 処理対象ファイルとファイル固有の設定（SPEC.md §2 の対応表・一覧ページ照合済み）。
# ファイルごとに異なる値（実施主体の別）を1か所にまとめ、グローバル定数として
# 1組に固定しない。処理順はこのリストの順とし、3PDFの統合出力を決定的にする。
FILE_CONFIGS = [
    {"filename": "000271730.pdf", "operator_type": "NPO等", "parser": "coordinate_page"},
    {"filename": "000230003.pdf", "operator_type": "市町村営", "parser": "coordinate_page"},
    {
        "filename": "000359215.pdf",
        "operator_type": "市町村営",
        "parser": "table_block",
        "appendix_marker": "輸送人員実績報告提出状況",
    },
]

YAMAGUCHI_MUNICIPALITIES = (
    "下関市", "宇部市", "山口市", "萩市", "防府市", "下松市", "岩国市", "光市",
    "長門市", "柳井市", "美祢市", "周南市", "山陽小野田市", "周防大島町", "和木町",
    "上関町", "田布施町", "平生町", "阿武町",
)

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
# 000230003.pdf は登録年月日を「R5.10.1」のような和暦の頭文字略記で記載する
# （000271730.pdf の「令和6年4月24日」形式とは異なる。実測で確認、SPEC.md未規定）。
ERA_ABBR = {"R": "令和", "H": "平成", "S": "昭和"}

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
    """x座標(またはy座標)の列を、差がtol未満のものを1本として畳んで昇順に返す
    (SPEC.md §4.1 手順2-3)。"""
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

# 登録番号の構造（SPEC.md §3.4(b)）。
# 現行方式: 〔運輸局頭1字〕〔運輸支局頭1字〕〔種別1字〕第〔一連番号〕号
#           または 〔地方公共団体の名称〕〔種別1字〕第〔一連番号〕号
# 旧市町村運営番号: 〔運輸局頭1字〕〔運輸支局頭1字〕市〔種別1字〕第〔一連番号〕号
#
# どちらも「(接頭辞)(福|交)第(連番)号」という同じ外形をしている。接頭辞が「市」で
# 終わることだけを根拠に旧体系と判定する実装（例: 汎用の `^(..)市([福交])`）は、
# 地方公共団体の名称そのものが「〇〇市」で終わる現行の権限移譲番号（例: 神戸市福第1号。
# 山口県スコープでは出現しないが、この正規表現は他県にも及びうる）から「市」を
# 誤って剥ぎ取り、authority_code を「神戸」にしてしまう。この2つは文字列だけでは
# 区別できず、公式原本と通達別記1で確認できた実例だけを根拠にする必要がある
# （SPEC.md §3.4(b)、今回の増分の必須実装1）。
#
# そのため、まず汎用形式で接頭辞と種別・連番に分解し、接頭辞が原本で確認済みの
# 旧体系接頭辞と一致する場合だけ、明示的なマップで「市」を旧体系マーカーとして
# 除去する。マップに無い「〇〇市」接頭辞は、旧体系と決め打たず地方公共団体名の
# 一部として authority_code にそのまま残す（現行の地方公共団体権限として扱う）。
# `registration_no`（正規化値）自体からは「市」を一切削除しない。
STANDARD_REGISTRATION_RE = re.compile(r"^(.+?)([福交])第(\d+)号$")

# 旧体系登録番号の接頭辞マップ: {「市」を除いた接頭辞: authority_code}。
# 山口県スコープで原本と照合済みのものだけをここに列挙する。
OLD_MUNICIPAL_AUTHORITY_PREFIXES = {
    # 中国運輸局(中)・山口運輸支局(山)。000230003.pdf 第1号・第4号
    # （中山市福第１号・中山市福第４号）で実測（SPEC.md §3.4(b)）。
    "中山": "中山",
}


def extract_registration_block(words):
    """「登録番号」ラベルの位置から registration_no_raw を取り、構造を分解する。"""
    label = find_word(words, "登", x_max=150, top_max=150)
    if label is None:
        raise ValueError("「登録番号」ラベルが見つからない")
    row = words_in_box(words, x0=200, top=label["top"] - 3, bottom=label["bottom"] + 3)
    raw = join_words(row)
    return parse_registration_text(raw)


def parse_registration_text(raw):
    """原文登録番号を保持したまま、全角英数字と空白だけを正規化して分解する。"""
    normalized = re.sub(r"\s+", "", to_halfwidth(raw))

    m = STANDARD_REGISTRATION_RE.match(normalized)
    if not m:
        raise ValueError(f"登録番号の形式が想定と違う: {normalized!r}")
    prefix, service_type_code, serial_no = m.groups()

    authority_code = prefix
    for old_prefix, mapped_code in OLD_MUNICIPAL_AUTHORITY_PREFIXES.items():
        if prefix == f"{old_prefix}市":
            authority_code = mapped_code
            break

    return {
        "registration_no": normalized,
        "registration_no_raw": raw,
        "authority_code": authority_code,
        "service_type_code": service_type_code,
        "serial_no": serial_no,
    }


WAREKI_FULL_RANGE_RE = re.compile(
    r"(令和|平成|昭和)(\d+)年(\d+)月(\d+)日\s*~\s*(令和|平成|昭和)(\d+)年(\d+)月(\d+)日"
)
# 000230003.pdf は登録年月日を「R5.10.1〜R8.9.30」のように和暦の頭文字略記＋ドット区切りで
# 記載する（000271730.pdf のみを見て確定した「令和6年4月24日」形式とは異なる。実測で確認）。
WAREKI_ABBR_RANGE_RE = re.compile(
    r"([RHS])(\d+)\.(\d+)\.(\d+)\s*~\s*([RHS])(\d+)\.(\d+)\.(\d+)"
)


def _abbr_date_to_iso(groups):
    return wareki_to_iso(ERA_ABBR[groups[0]], groups[1], groups[2], groups[3])


def extract_dates_text(text):
    """登録日・更新日・有効期間を、全表記形式に共通の文字列から抽出する。"""
    text = to_halfwidth(text)
    m_reg_full = re.search(
        r"登録年月日[：:]\s*(令和|平成|昭和)(\d+)年(\d+)月(\d+)日", text
    )
    m_reg_abbr = re.search(r"登録年月日[：:]\s*([RHS])(\d+)\.(\d+)\.(\d+)", text)
    m_upd_full = re.search(
        r"更新登録年月日[：:]\s*(令和|平成|昭和)(\d+)年(\d+)月(\d+)日\s*~\s*"
        r"(令和|平成|昭和)(\d+)年(\d+)月(\d+)日",
        text,
    )
    m_upd_abbr = re.search(
        r"更新登録年月日[：:]\s*([RHS])(\d+)\.(\d+)\.(\d+)\s*~\s*"
        r"([RHS])(\d+)\.(\d+)\.(\d+)",
        text,
    )

    if m_upd_full or m_upd_abbr:
        if m_reg_full:
            registered_date = wareki_to_iso(*m_reg_full.groups())
        elif m_reg_abbr:
            registered_date = _abbr_date_to_iso(m_reg_abbr.groups())
        else:
            registered_date = ""
        if m_upd_full:
            groups = m_upd_full.groups()
            renewed_date = wareki_to_iso(*groups[:4])
            valid_to = wareki_to_iso(*groups[4:])
        else:
            groups = m_upd_abbr.groups()
            renewed_date = _abbr_date_to_iso(groups[:4])
            valid_to = _abbr_date_to_iso(groups[4:])
        return registered_date, renewed_date, renewed_date, valid_to

    m_range = WAREKI_FULL_RANGE_RE.search(text)
    if m_range:
        valid_from = wareki_to_iso(*m_range.groups()[0:4])
        valid_to = wareki_to_iso(*m_range.groups()[4:8])
        return "", valid_from, valid_from, valid_to

    m_abbr = WAREKI_ABBR_RANGE_RE.search(text)
    if m_abbr:
        groups = m_abbr.groups()
        valid_from = _abbr_date_to_iso(groups[:4])
        valid_to = _abbr_date_to_iso(groups[4:])
        return "", valid_from, valid_from, valid_to

    raise ValueError(f"登録年月日の形式が想定と違う: {text!r}")


def extract_dates(words):
    """登録年月日及び更新登録年月日を抽出する。

    実物では2パターンが混在する（evidence/20260807_explore_words_edges.txt で全ページ確認、
    evidence/20260807_page_render-*.png で目視確認済み）:

    - 「登録年月日：」「更新登録年月日：」の接頭辞付きで両方が別行に印字される
      （000271730.pdf p3=中山福第４号のみ。原登録日と更新後の有効期間が別々にわかる）
    - 接頭辞なしで「開始日～終了日」の1行のみが印字される
      （000271730.pdf p1・p2・p4、000230003.pdf 全ページ）。
      この場合、原登録年月日はこの様式上どこにも印字されておらず空とする。
      更新登録年月日・有効期間の開始は同じ日付、終了は範囲の終わりを使う。
      日付の表記は、和暦の漢字表記（令和6年4月24日）と、頭文字＋ドットの略記
      （R5.10.1）の両方があり得る。
    """
    label1 = find_word(words, "登録年月日及び", x_max=200, top_max=200)
    label2 = find_word(words, "更新登録年月日", x_max=200, top_max=200)
    if label1 is None or label2 is None:
        raise ValueError("登録年月日ラベルが見つからない")
    row = words_in_box(words, x0=150, top=label1["top"] - 2, bottom=label2["bottom"] + 2)
    text = to_halfwidth(join_words(row, gap_threshold=3.0))

    return extract_dates_text(text)


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
    # 値の位置はファイルにより異なる。000271730.pdfはラベルの上2〜16ptに
    # 1文字ずつ別語として印字される（「福」「祉」等、字間約5.04pt）。
    # 000230003.pdfは1つの語「福祉有償運送」がラベルとほぼ同じ高さ（同一行〜
    # 上9pt程度）に印字される。どちらも拾えるよう縦方向に広めの窓を取り、
    # 詰めて連結する（意味的な区切りではないため）。
    row = words_in_box(words, x0=150, x1=450, top=label["top"] - 20, bottom=label["top"] + 5)
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
    # 実測では「イ．」〜「ヘ．」は説明文と結合した1語のまま分割されないが、
    # 「ト」だけは「その他」が改行等で分離して単独語になりうる
    # (000271730.pdf p1は"ト"+"そ"+"の他）"の3語、p3は"その他"のみ単独語、p4は3行に
    # 折り返して"ト"と"その他）"が別々の行、000230003.pdf p1は"ト"+"その"+"他）"の3語に
    # 分裂。全てevidence/20260807_page_render-*.pngで目視確認済み)。
    # そこで、欄内に「その他」を含む語、または「その」「そ」のように「その他」の
    # 先頭部分だけの単独語が1つでもあれば、候補「ト」は凡例の断片とみなして除外する。
    # 無ければ(凡例が無いページ)「ト」候補もそのままマークとして採用する。
    # イ〜ヘは常に説明文と結合しているため、裸の1文字で出現するのは選択マークの
    # 場合のみであり、除外判定は不要。
    legend_has_sonota = any(
        ("その他" in w["text"]) or (w["text"] in ("そ", "その"))
        for w in row
    )

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


def extract_office_rows(page, words):
    """事務所の名称及び位置（ページ上部）を抽出する。上から順に複数件あり得る
    （SPEC.md §4.2, §9 U2）。000230003.pdf 第4号（p3）は1団体4事務所。

    行の区切りはこの欄の横罫線（page.edges）から導出し、ページごとに固定件数を
    仮定しない。行の中に文字が無い行（フォーム上のあらかじめ用意された空欄）は
    実在する事務所ではないので読み飛ばす（000230003.pdf p2で確認、SPEC未規定・
    実物のみで判断）。

    戻り値: [(name, location), ...] を上から順に並べたリスト。
    """
    label_meishou = find_word(words, "事務所の名称", x_max=150, top_max=300)
    label_oyobi = find_word(words, "及び位置", x_max=150, top_max=300)
    label_next = find_word(words, "路線又は", x_max=150, top_max=350)
    if label_meishou is None or label_oyobi is None or label_next is None:
        raise ValueError("「事務所の名称及び位置」ラベルが見つからない")
    next_label_top = label_next["top"]

    # ミニ見出し「名称」「位置」の下端から、次のラベル行までがデータ行。
    # 座標ボックスではなくテキスト完全一致で拾う（座標ボックスだと実データ行まで
    # 巻き込んでしまうことが実測で判明した。データ行を含めると header_bottom が
    # ずれて名称/位置が空になる）。label_meishou/label_oyobi自体の位置は、複数行
    # ある場合はブロック全体の中央付近に来る（ラベルが縦方向に中央寄せされる
    # ため）ことがあるので、ミニ見出しの探索窓はラベル位置に依存させず
    # next_label_top までの全域から探す。
    mini_headers = [w for w in words
                    if w["x0"] > 150 and w["top"] < next_label_top
                    and w["text"] in ("名", "称", "位", "置")]
    if not mini_headers:
        raise ValueError("事務所名称/位置のミニ見出し（名/称/位/置）が見つからない")
    header_bottom = max(w["bottom"] for w in mini_headers)

    h_edges = [e for e in page.edges
               if e.get("orientation") == "h"
               and (e["x1"] - e["x0"]) > 100
               and e["top"] > header_bottom - 2
               and e["top"] <= next_label_top + 2]
    row_bounds = cluster_x([e["top"] for e in h_edges])
    if len(row_bounds) < 2:
        raise ValueError(f"事務所の名称及び位置欄の行境界が見つからない: {row_bounds}")

    all_data_words = words_in_box(words, x0=150, top=header_bottom, bottom=next_label_top - 2)
    if not all_data_words:
        raise ValueError("事務所の名称/位置のデータ行が見つからない")
    data_top = min(w["top"] for w in all_data_words)
    data_bottom = max(w["bottom"] for w in all_data_words)
    # 名称列・位置列の境界を、実データ行の縦範囲と重なる罫線から導出する。
    row_v_edges = [e for e in page.edges
                   if e.get("orientation") == "v"
                   and e["top"] <= data_bottom
                   and e["bottom"] >= data_top
                   and 200 < e["x0"] < 500]  # 500以上は表右端の外枠罫線を除外するため
    dividers = cluster_x([e["x0"] for e in row_v_edges])
    if len(dividers) != 1:
        raise ValueError(f"事務所名称/位置の列境界が1本にならない: {dividers}")
    divider = dividers[0]

    offices = []
    for i in range(len(row_bounds) - 1):
        top, bottom = row_bounds[i], row_bounds[i + 1]
        row_words = words_in_box(words, x0=150, top=top, bottom=bottom)
        if not row_words:
            continue  # 予備の空欄行（実在する事務所ではない）
        name = join_words(words_in_box(row_words, x1=divider))
        location = join_words(words_in_box(row_words, x0=divider))
        offices.append((name, location))
    if not offices:
        raise ValueError("事務所の名称及び位置が1件も取得できない")
    return offices


def extract_partner_operator(words):
    """事業者協力型自家用有償運送の協力事業者欄を抽出する。

    表側の見出し語「氏名又は名称」（左半分の列見出し）から、左マージンの
    折り返しラベル（「事業者協力型…名称及び住所」）の最終行までのデータ域を読む。
    座標パーサを使う2PDF・7ページ（000271730.pdf 全4ページ、000230003.pdf 全3ページ）では
    全件空欄（実測、evidence/20260807_page_render-{1..4}.png、
    evidence/20260809_000230003_page1.png で目視確認）。000359215.pdf は
    表セル型パーサ側で全12団体の空欄を検証する。000268896.pdf は未確認。
    この結果を一般化しない。見出しの縦位置は
    ファイルにより異なるため固定オフセットは使わず、ラベル自体の位置から都度算出する。

    下端は「備」（備考）ラベルではなく、左マージンラベルの最終行「名称及び住所」の
    位置を基準にする。000230003.pdf では備考欄自体の説明文（「〜へ業務委託」）が、
    「備」の文字そのものより上、この欄の直下に印字されており、「備」の位置を
    下端にすると備考の内容を誤って拾ってしまう（実測で確認。目視は
    evidence/20260809_000230003_page1.pngで、備考欄の1行目「山口市社会福祉協議会へ
    業務委託」が「事業者協力型…」欄ではなく備考欄自体の内容であることを確認済み）。
    """
    subheader = find_word(words, "氏名又は名称", x_max=250, top_max=470)
    label_margin_end = find_word(words, "名称及び住所", x_max=150, top_max=550)
    if subheader is None or label_margin_end is None:
        raise ValueError("事業者協力型欄の見出しが見つからない")
    row = words_in_box(words, x0=150, top=subheader["bottom"] + 1, bottom=label_margin_end["bottom"] + 5)
    text = join_words(row)
    return text.strip()


# ---------------------------------------------------------------------------
# 車両欄の抽出（SPEC.md §4.1, §4.2）
# ---------------------------------------------------------------------------

CELL_TOTAL_RE = re.compile(r"^\d+$")
CELL_KEI_RE = re.compile(r"^[(（]\s*(\d*)\s*[)）]$")


def read_cell_value(cell_words, has_kei_flag):
    """1セル分の語から (総数, 内数) を読む。

    括弧付きの数字が軽自動車の内数(SPEC.md §3.4(a))。空の括弧・括弧なし・素の0は
    いずれも0として扱う。000230003.pdf 第4号の一部の事務所では、内数の欄に
    括弧ではなく素の「0」がそのまま印字される（総数行の数字とは別の、より下の
    行に現れる。SPEC.md §4.2「持込行に(　)ではなく素の0が入るページもある」と
    同じ現象が、所有区分の無いファイルの内数欄でも起きている。実測で確認）。
    このため、括弧の無い数字トークンが同一セル内に複数ある場合は、上端(top)が
    最も小さいものを総数、それより下にあるものを内数(通常0)とみなす。
    """
    digit_tokens = []
    kei_val = None
    for w in cell_words:
        t = w["text"]
        if CELL_TOTAL_RE.match(t):
            digit_tokens.append((w["top"], int(t)))
        else:
            m = CELL_KEI_RE.match(t)
            if m:
                kei_val = int(m.group(1)) if m.group(1) else 0
    digit_tokens.sort(key=lambda item: item[0])
    if digit_tokens:
        total = digit_tokens[0][1]
        if kei_val is None and len(digit_tokens) > 1:
            kei_val = digit_tokens[-1][1]
    else:
        total = 0
    if kei_val is None and has_kei_flag:
        kei_val = 0
    return total, (kei_val if has_kei_flag else "")


def extract_vehicle_table(page, words, office_count):
    """車両欄を抽出し、事務所ごとのエントリのリストを返す。

    各エントリ: {"office_seq", "ownership", "cells", "name_text", "location_text"}

    列境界(7列=8本)はページごとに縦罫線から導出する(SPEC.md §4.1)。
    所有区分の列(所有/持込)があるかどうかは、事務所名・位置列と車両欄本体の間に
    もう1本罫線があるかどうかで判定する(列見出しと罫線から判断し、登録番号ごとの
    ハードコード分岐はしない。今回の増分の必須実装4)。
      - 所有区分の列があるファイル(000271730.pdf): 事務所は1件のみで、
        物理行2行がそれぞれ「所有」「持込」の1エントリになる。
      - 所有区分の列が無いファイル(000230003.pdf): 事務所ごとに物理行2行
        (名称+総数の行、位置+内数の行)が1組で1エントリになる。
    """
    header_label = find_word(words, "自家用有償旅客運送自動車の数", top_max=None)
    if header_label is None:
        raise ValueError("車両欄の見出しが見つからない")

    v_edges = [e for e in page.edges if e.get("orientation") == "v" and e["top"] >= header_label["top"] - 5]
    if not v_edges:
        raise ValueError("車両欄の罫線が見つからない")
    table_top = min(e["top"] for e in v_edges)
    table_bottom = max(e["bottom"] for e in v_edges)

    # 表の最下端まで届く縦罫線のうち、事務所名・位置列より右側にあるものを
    # 右から7列分(境界8本)取る。所有区分の列がある場合、その境界は右から8番目
    # より左に残るので自動的に除外される。
    reach_bottom_edges = [e for e in v_edges if e["bottom"] >= table_bottom - 2 and e["x0"] > 200]
    all_bounds = cluster_x([e["x0"] for e in reach_bottom_edges])
    if len(all_bounds) < 8:
        raise ValueError(f"車両欄の列境界が7列に満たない: {all_bounds}")
    col_bounds = all_bounds[-8:]

    # 所有区分の列があるかどうかは、残りの(より左側の)境界の有無で判定する。
    owner_candidates = [b for b in all_bounds if b < col_bounds[0] - 5]

    header_words = words_in_box(words, top=table_top, bottom=table_top + 65)
    header_text_bottom = max(w["bottom"] for w in header_words) if header_words else table_top

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

    col_headers = []
    for x0, x1 in zip(col_bounds[:-1], col_bounds[1:]):
        hw = words_in_box(header_words, x0=x0, x1=x1)
        col_headers.append(join_words(hw, gap_threshold=100))  # このセル内は詰めて連結
    vehicle_types = [map_vehicle_type(h) for h in col_headers]
    has_kei = ["軽" in h for h in col_headers]

    # 行境界: 表内の横罫線のうち、幅100pt超で、列見出しの下端より下にあるもの
    h_edges = [e for e in page.edges
               if e.get("orientation") == "h"
               and (e["x1"] - e["x0"]) > 100
               and e["top"] > header_text_bottom - 2
               and e["top"] <= table_bottom + 2]
    row_bounds = cluster_x([e["top"] for e in h_edges])
    n_phys_rows = len(row_bounds) - 1
    if n_phys_rows < 1:
        raise ValueError(f"車両欄の行境界が見つからない: {row_bounds}")

    def build_cells(top, bottom):
        cells = []
        for ci, (x0, x1) in enumerate(zip(col_bounds[:-1], col_bounds[1:])):
            cell_words = words_in_box(words, x0=x0, x1=x1, top=top, bottom=bottom)
            total, kei = read_cell_value(cell_words, has_kei[ci])
            cells.append({
                "vehicle_type": vehicle_types[ci],
                "vehicle_type_label": col_headers[ci],
                "count": total,
                "count_kei": kei,
            })
        return cells

    entries = []
    if owner_candidates:
        # 所有/持込あり(SPEC.md §3.5型)。事務所は1件のみ。
        if len(owner_candidates) != 1:
            raise ValueError(f"所有区分の列境界が1本にならない: {owner_candidates}")
        owner_divider = owner_candidates[0]
        if n_phys_rows != 2:
            raise ValueError(f"所有/持込の行境界が2行にならない: {row_bounds}")
        for i in range(2):
            top, bottom = row_bounds[i], row_bounds[i + 1]
            label_words = words_in_box(words, x0=owner_divider, x1=col_bounds[0], top=top, bottom=bottom)
            label_text = join_words(label_words)
            if "所有" in label_text:
                ownership = "所有"
            elif "持込" in label_text:
                ownership = "持込"
            else:
                raise ValueError(f"所有区分ラベルを解釈できない: {label_text!r}")
            # 事務所名/位置(車両欄側): 所有行に名称、持込行に位置が印字される
            # (evidence/20260807_explore_words_edges.txt 全4ページで確認。SPEC.md 未規定・実物のみで判断)
            office_text_words = [w for w in words_in_box(words, x0=150, x1=owner_divider, top=top, bottom=bottom)
                                  if w["text"] not in ("所有", "持込")]
            office_text = join_words(office_text_words)
            entries.append({
                "office_seq": 1,
                "ownership": ownership,
                "cells": build_cells(top, bottom),
                "name_text": office_text if ownership == "所有" else "",
                "location_text": office_text if ownership == "持込" else "",
            })
    else:
        # 所有区分の列なし(SPEC.md §7想定・000230003.pdfで確認)。事務所ごとに
        # 「名称+総数」の物理行と「位置+内数」の物理行が1組で1エントリになる。
        if n_phys_rows % 2 != 0:
            raise ValueError(f"事務所モードの車両欄の物理行数が偶数でない: {row_bounds}")
        n_table_entries = n_phys_rows // 2
        seq = 0
        for k in range(n_table_entries):
            top, mid, bottom = row_bounds[2 * k], row_bounds[2 * k + 1], row_bounds[2 * k + 2]
            name_text = join_words(words_in_box(words, x0=150, x1=col_bounds[0], top=top, bottom=mid))
            location_text = join_words(words_in_box(words, x0=150, x1=col_bounds[0], top=mid, bottom=bottom))
            if not name_text and not location_text:
                continue  # 予備の空欄エントリ（000230003.pdf p2で確認。実在する事務所ではない）
            if not name_text or not location_text:
                raise ValueError(
                    f"事務所名または位置が片方だけ空: name={name_text!r} location={location_text!r}"
                )
            seq += 1
            entries.append({
                "office_seq": seq,
                "ownership": "",
                "cells": build_cells(top, bottom),
                "name_text": name_text,
                "location_text": location_text,
            })
        if len(entries) != office_count:
            raise ValueError(
                f"車両欄の事務所数({len(entries)})と上部の事務所数({office_count})が一致しない"
            )

    return entries


# ---------------------------------------------------------------------------
# 複数ページ・表セル型の交通空白地登録簿（000359215.pdf）
# ---------------------------------------------------------------------------

def compact_table_text(value):
    """表ラベル比較用。改行・全角半角空白を除く。"""
    return re.sub(r"\s+", "", value or "")


def flatten_table_value(value):
    """セル内の折返し改行だけを除き、原文の語間空白は保持する。"""
    return re.sub(r"\s*\n\s*", "", value or "").strip()


def table_has_marker(rows, marker):
    return any(
        marker in compact_table_text(cell)
        for row in rows
        for cell in row
        if cell
    )


def find_table_row(rows, marker):
    for index, row in enumerate(rows):
        if row and marker in compact_table_text(row[0]):
            return index, row
    raise ValueError(f"表の行ラベルが見つからない: {marker}")


def first_nonempty(cells):
    for cell in cells:
        value = flatten_table_value(cell)
        if value:
            return value
    return ""


def extract_metadata_table(page):
    tables = page.extract_tables()
    matches = [table for table in tables if table_has_marker(table, "登録番号")]
    if len(matches) != 1:
        raise ValueError(f"登録事項表が1件でない: {len(matches)}")
    return matches[0]


def extract_table_field(rows, marker):
    _, row = find_table_row(rows, marker)
    value = first_nonempty(row[1:])
    if not value:
        raise ValueError(f"表の値が空: {marker}")
    return value


def extract_table_offices(rows):
    header_index, header = find_table_row(rows, "事務所の名称")
    name_indexes = [i for i, cell in enumerate(header) if compact_table_text(cell) == "名称"]
    if not name_indexes:
        raise ValueError("事務所表の名称列が見つからない")
    name_index = name_indexes[0]  # 光市の複数群は、○と値がある交通空白地側の先頭群
    location_indexes = [
        i for i, cell in enumerate(header)
        if i > name_index and compact_table_text(cell) == "位置"
    ]
    if not location_indexes:
        raise ValueError("事務所表の位置列が見つからない")
    location_index = location_indexes[0]

    offices = []
    for row in rows[header_index + 1:]:
        if compact_table_text(row[0]):
            break
        name = flatten_table_value(row[name_index]) if name_index < len(row) else ""
        location = flatten_table_value(row[location_index]) if location_index < len(row) else ""
        if not name and not location:
            continue
        if not name or not location:
            raise ValueError(f"上部事務所の名称または位置が片方だけ空: {name!r} / {location!r}")
        offices.append((name, location))
    if not offices:
        raise ValueError("上部事務所が1件も取得できない")
    return offices


def clean_service_area_fragment(text):
    lines = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line in ("路線又は", "運送の区域", "路線又は運送の区域"):
            continue
        line = line.replace("路線又は", "").replace("運送の区域", "").strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def extract_service_area_block(block):
    """表セルと、表として認識されない改ページ継続領域の双方から区域を得る。"""
    parts = []
    for page_no, page in block:
        table_objects = page.find_tables()
        table_rows = [(table, table.extract()) for table in table_objects]
        service_rows_found = False
        for _, rows in table_rows:
            for row in rows:
                if row and ("路線又は" in compact_table_text(row[0]) or
                            "運送の区域" in compact_table_text(row[0])):
                    value = "\n".join(
                        flatten_table_value(cell) for cell in row[1:] if flatten_table_value(cell)
                    )
                    if value:
                        parts.append(value)
                    service_rows_found = True

        if len(block) == 1 or service_rows_found:
            continue

        registration_tables = [
            table for table, rows in table_rows if table_has_marker(rows, "登録番号")
        ]
        passenger_tables = [
            table for table, rows in table_rows
            if table_has_marker(rows, "旅客の範囲") or table_has_marker(rows, "運送する旅客")
        ]
        top = max((table.bbox[3] for table in registration_tables), default=0)
        bottom = min((table.bbox[1] for table in passenger_tables), default=page.height)
        if bottom > top + 2:
            fragment = page.crop((0, top, page.width, bottom)).extract_text() or ""
            fragment = clean_service_area_fragment(fragment)
            if fragment:
                parts.append(fragment)

    raw = "\n".join(part for part in parts if part).strip()
    if not raw:
        raise ValueError(
            f"路線又は運送の区域が取得できない: pages={[page_no for page_no, _ in block]}"
        )
    return to_halfwidth(raw), raw


def extract_service_area_municipalities(service_area, org_name):
    hits = []
    for municipality in YAMAGUCHI_MUNICIPALITIES:
        position = service_area.find(municipality)
        if position >= 0:
            hits.append((position, municipality))
    if re.search(r"[市町村]$", org_name) and not any(name == org_name for _, name in hits):
        hits.append((-1, org_name))
    return ";".join(name for _, name in sorted(hits) if name)


def validate_empty_partner_block(block):
    for page_no, page in block:
        for rows in page.extract_tables():
            active = False
            for row in rows:
                label = compact_table_text(row[0]) if row else ""
                if "事業者協力型" in label:
                    active = True
                    continue
                if active and "備考" in label:
                    active = False
                    continue
                if not active:
                    continue
                values = [
                    compact_table_text(cell) for cell in row[1:]
                    if compact_table_text(cell) not in ("", "氏名又は名称", "住所")
                ]
                if values:
                    raise ValueError(
                        f"000359215.pdf p{page_no}: 事業者協力型欄に想定外の値: {values}"
                    )


def read_table_cell_value(text, has_kei_flag):
    normalized = to_halfwidth(text or "")
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    plain_numbers = [int(line) for line in lines if re.fullmatch(r"\d+", line)]
    parenthesized = [
        int(match.group(1)) if match.group(1) else 0
        for line in lines
        for match in [re.fullmatch(r"\(\s*(\d*)\s*\)", line)]
        if match
    ]
    total = plain_numbers[0] if plain_numbers else 0
    if not has_kei_flag:
        return total, ""
    if parenthesized:
        kei = parenthesized[-1]
    elif len(plain_numbers) > 1:
        kei = plain_numbers[-1]
    else:
        kei = 0
    return total, kei


def map_table_vehicle_type(label, transport_type):
    compact = compact_table_text(label)
    mapping = (
        ("寝台車", "寝台車"), ("車いす", "車いす車"), ("兼用車", "兼用車"),
        ("回転", "回転シート車"), ("セダン", "セダン等"), ("バス", "バス"),
        ("合計", "合計"),
    )
    for marker, vehicle_type in mapping:
        if marker in compact:
            if vehicle_type == "セダン等" and transport_type == "交通空白地有償運送":
                return "普通自動車"
            return vehicle_type
    raise ValueError(f"車種列のラベルを解釈できない: {label!r}")


def extract_table_vehicle_entries(block, office_count, transport_type):
    matches = []
    for page_no, page in block:
        for table in page.find_tables():
            rows = table.extract()
            if table_has_marker(rows, "自家用有償旅客運送自動車の数"):
                matches.append((page_no, page, table, rows))
    if len(matches) != 1:
        raise ValueError(f"車両表が1件でない: {len(matches)}")
    page_no, page, table, rows = matches[0]
    header_index = next(
        index for index, row in enumerate(rows)
        if table_has_marker([row], "自家用有償旅客運送自動車の数")
    )
    type_header = rows[header_index + 1]
    col_headers = [flatten_table_value(cell) for cell in type_header[2:9]]
    vehicle_types = [map_table_vehicle_type(label, transport_type) for label in col_headers]
    has_kei = ["軽" in compact_table_text(label) for label in col_headers]

    entries = []
    printed_aggregate = None
    for row in rows[header_index + 2:]:
        office_cell = row[1] or ""
        office_lines = [flatten_table_value(line) for line in office_cell.splitlines() if line.strip()]
        if not office_lines:
            continue
        cells = []
        for index, (vehicle_type, label, kei_flag) in enumerate(
            zip(vehicle_types, col_headers, has_kei), start=2
        ):
            total, kei = read_table_cell_value(row[index] if index < len(row) else "", kei_flag)
            cells.append({
                "vehicle_type": vehicle_type,
                "vehicle_type_label": label,
                "count": total,
                "count_kei": kei,
            })
        if compact_table_text(office_lines[0]) == "合計":
            printed_aggregate = cells
            continue
        name = office_lines[0]
        location = "".join(office_lines[1:])
        if not location:
            raise ValueError(f"車両欄の事務所位置が空: {name!r}")
        entries.append({
            "office_seq": len(entries) + 1,
            "ownership": "",
            "cells": cells,
            "name_text": name,
            "location_text": location,
            "source_page": page_no,
        })

    if len(entries) != office_count:
        raise ValueError(f"車両欄の事務所数({len(entries)})と上部({office_count})が一致しない")

    derived_total = sum(
        cell["count"] for entry in entries for cell in entry["cells"]
        if cell["vehicle_type"] == "合計"
    )
    derived_kei = sum(
        cell["count_kei"] for entry in entries for cell in entry["cells"]
        if cell["vehicle_type"] == "合計" and cell["count_kei"] != ""
    )
    if printed_aggregate:
        aggregate_total = next(cell["count"] for cell in printed_aggregate if cell["vehicle_type"] == "合計")
        aggregate_kei = next(cell["count_kei"] for cell in printed_aggregate if cell["vehicle_type"] == "合計")
        if (aggregate_total, aggregate_kei) != (derived_total, derived_kei):
            raise ValueError(
                f"団体集計と事務所合計が不一致: printed={(aggregate_total, aggregate_kei)} "
                f"derived={(derived_total, derived_kei)}"
            )

    below_words = [
        w for w in page.extract_words()
        if w["top"] >= table.bbox[3] - 1 and re.fullmatch(r"\d+", to_halfwidth(w["text"]))
    ]
    outside_totals = [int(to_halfwidth(w["text"])) for w in sorted(below_words, key=lambda w: w["x0"])]
    if outside_totals and outside_totals[-1] != derived_total:
        raise ValueError(f"表外団体集計が不一致: {outside_totals} / derived={derived_total}")
    return entries, derived_total, derived_kei


def normalize_office_for_compare(value):
    return re.sub(r"\s+", "", to_halfwidth(value))


def parse_table_block(block, source_pdf_name, operator_type):
    start_page_no, start_page = block[0]
    metadata = extract_metadata_table(start_page)
    reg = parse_registration_text(extract_table_field(metadata, "登録番号"))
    registered_date, renewed_date, valid_from, valid_to = extract_dates_text(
        extract_table_field(metadata, "登録年月日及び")
    )
    org_name = extract_table_field(metadata, "名称")
    org_address_raw = extract_table_field(metadata, "住所")
    org_address = to_halfwidth(org_address_raw)
    transport_type = extract_table_field(metadata, "運送の種別")
    if transport_type != "交通空白地有償運送":
        raise ValueError(f"運送の種別が交通空白地でない: {transport_type!r}")
    scope_flags = {column: 0 for column in SCOPE_COLUMNS.values()}
    office_rows = extract_table_offices(metadata)
    service_area, service_area_raw = extract_service_area_block(block)
    service_area_municipalities = extract_service_area_municipalities(service_area, org_name)
    validate_empty_partner_block(block)
    entries, vehicles_total, vehicles_total_kei = extract_table_vehicle_entries(
        block, len(office_rows), transport_type
    )

    flags = []
    for sequence, (top_office, entry) in enumerate(zip(office_rows, entries), start=1):
        top_name, top_location = top_office
        name_mismatch = normalize_office_for_compare(top_name) != normalize_office_for_compare(entry["name_text"])
        location_mismatch = (
            normalize_office_for_compare(top_location) !=
            normalize_office_for_compare(entry["location_text"])
        )
        if name_mismatch and "office_mismatch" not in flags:
            flags.append("office_mismatch")
        elif location_mismatch and "office_notation_diff" not in flags:
            flags.append("office_notation_diff")

    operator = {
        "registration_no": reg["registration_no"],
        "registration_no_raw": reg["registration_no_raw"],
        "authority_code": reg["authority_code"],
        "service_type_code": reg["service_type_code"],
        "serial_no": reg["serial_no"],
        "pref": PREF,
        "transport_type": transport_type,
        "operator_type": operator_type,
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
        "office_name": ";".join(name for name, _ in office_rows),
        "office_location": ";".join(location for _, location in office_rows),
        "partner_operator_name": "",
        "partner_operator_address": "",
        "vehicles_total": vehicles_total,
        "vehicles_total_kei": vehicles_total_kei,
        "source_pdf": source_pdf_name,
        "source_page": start_page_no,
        "flags": ";".join(flags),
    }

    vehicles = []
    for entry in entries:
        for cell in entry["cells"]:
            if cell["count"] == 0 and (cell["count_kei"] == "" or cell["count_kei"] == 0):
                continue
            vehicles.append({
                "registration_no": reg["registration_no"],
                "office_seq": entry["office_seq"],
                "office_name": entry["name_text"],
                "office_location": entry["location_text"],
                "ownership": "",
                "vehicle_type": cell["vehicle_type"],
                "vehicle_type_label": cell["vehicle_type_label"],
                "count": cell["count"],
                "count_kei": cell["count_kei"],
                "source_pdf": source_pdf_name,
                "source_page": entry["source_page"],
            })
    return operator, vehicles


# ---------------------------------------------------------------------------
# 既存2PDFの1ページ1団体処理
# ---------------------------------------------------------------------------

def parse_page(page, page_no, source_pdf_name, operator_type):
    words = page.extract_words()

    reg = extract_registration_block(words)
    registered_date, renewed_date, valid_from, valid_to = extract_dates(words)
    org_name = extract_org_name(words)
    org_address, org_address_raw = extract_org_address(words)
    transport_type = extract_transport_type(words)
    service_area, service_area_raw, service_area_municipalities = extract_service_area(words)
    scope_flags = extract_scope_flags(words)
    office_rows = extract_office_rows(page, words)  # [(name, location), ...] 上から順

    # 事業者協力型自家用有償運送の氏名又は名称/住所は山口県で確認した範囲では
    # 全件空欄と実測済み。空欄前提でハードコードするのではなく、想定外の値が
    # 入っていたら止める(推定で先に進まない)。
    partner_text = extract_partner_operator(words)
    if partner_text:
        raise ValueError(
            f"{source_pdf_name} p{page_no}: 事業者協力型の氏名又は名称/住所欄に想定外の値がある: {partner_text!r}。"
            "空欄前提の実装なので、パーサを直す前にPROGRESS.mdに報告して止まること。"
        )

    entries = extract_vehicle_table(page, words, office_count=len(office_rows))

    # vehicles_total / vehicles_total_kei: 合計列の値を全事務所・全エントリで合算する
    vehicles_total = 0
    vehicles_total_kei = 0
    for entry in entries:
        for cell in entry["cells"]:
            if cell["vehicle_type"] == "合計":
                vehicles_total += cell["count"]
                vehicles_total_kei += cell["count_kei"] if cell["count_kei"] != "" else 0

    # 車両欄側の事務所名・位置を office_seq ごとにまとめる。
    # 所有区分ありのファイルは単一事務所で、所有行の名称・持込行の位置を
    # その事務所の値として1件にまとめる(SPEC.md §3.2)。所有区分なしのファイルは
    # エントリごとに既に1事務所分の名称・位置を持つ。
    veh_offices = {}
    if entries and entries[0]["ownership"]:
        name = next((e["name_text"] for e in entries if e["ownership"] == "所有"), "")
        location = next((e["location_text"] for e in entries if e["ownership"] == "持込"), "")
        veh_offices[1] = (name, location)
    else:
        for e in entries:
            veh_offices[e["office_seq"]] = (e["name_text"], e["location_text"])

    # 事務所情報の不一致フラグ(SPEC.md §3.6)。比較の前処理は次の2段のみ
    # (出力する値自体は正規化しない。SPEC.md §4.3の「原文保持」を尊重する):
    #   1. 全角→半角
    #   2. 空白(全角・半角)をすべて除去
    # 事務所数が上部と車両欄で違う場合、またはoffice_seqごとの名称が不一致なら
    # office_mismatch、名称が一致し位置だけが不一致ならoffice_notation_diffとする。
    # operators.flags は団体内の全事務所で生じたフラグの重複を除き ; 区切りで持つ。
    def normalize_for_compare(s):
        return to_halfwidth(s).replace(" ", "")

    flags = []
    if len(office_rows) != len(veh_offices):
        flags.append("office_mismatch")
    else:
        for seq in range(1, len(office_rows) + 1):
            top_name, top_loc = office_rows[seq - 1]
            veh_name, veh_loc = veh_offices[seq]
            name_mismatch = bool(veh_name) and normalize_for_compare(veh_name) != normalize_for_compare(top_name)
            loc_mismatch = bool(veh_loc) and normalize_for_compare(veh_loc) != normalize_for_compare(top_loc)
            if name_mismatch:
                if "office_mismatch" not in flags:
                    flags.append("office_mismatch")
            elif loc_mismatch:
                if "office_notation_diff" not in flags:
                    flags.append("office_notation_diff")

    operator = {
        "registration_no": reg["registration_no"],
        "registration_no_raw": reg["registration_no_raw"],
        "authority_code": reg["authority_code"],
        "service_type_code": reg["service_type_code"],
        "serial_no": reg["serial_no"],
        "pref": PREF,
        "transport_type": transport_type,
        "operator_type": operator_type,
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
        "office_name": ";".join(name for name, _ in office_rows),
        "office_location": ";".join(loc for _, loc in office_rows),
        "partner_operator_name": "",
        "partner_operator_address": "",
        "vehicles_total": vehicles_total,
        "vehicles_total_kei": vehicles_total_kei,
        "source_pdf": source_pdf_name,
        "source_page": page_no,
        "flags": ";".join(flags),
    }

    vehicles = []
    for entry in entries:
        office_seq = entry["office_seq"]
        office_name, office_location = veh_offices.get(office_seq, ("", ""))
        for cell in entry["cells"]:
            if cell["count"] == 0 and (cell["count_kei"] == "" or cell["count_kei"] == 0):
                continue  # 台数0の行は出力しない(SPEC.md §3.5「持込は0台なので行を出さない」)
            vehicles.append({
                "registration_no": reg["registration_no"],
                "office_seq": office_seq,
                "office_name": office_name,
                "office_location": office_location,
                "ownership": entry["ownership"],
                "vehicle_type": cell["vehicle_type"],
                "vehicle_type_label": cell["vehicle_type_label"],
                "count": cell["count"],
                "count_kei": cell["count_kei"],
                "source_pdf": source_pdf_name,
                "source_page": page_no,
            })

    return operator, vehicles


# ---------------------------------------------------------------------------
# 代表者氏名の伏字化（SPEC.md §4.4, rev.4.4）
# ---------------------------------------------------------------------------

def redact_representative_name(words, raw_text, pdf_name, page_no, required=True):
    """ページの抽出テキストから代表者氏名の値だけを [氏名-非出力] に置換する。

    実際の氏名値をコードや例外へ保持しないため、extract_text() が出す行単位で置換する。
    「代表者の氏名」ラベルは他の内容と同じ行に同居しない(全ページで確認済み)
    ため、そのラベルで始まる行の残り全部を伏字にすれば十分かつ安全。登録開始ページは
    required=True で1件を必須にし、継続・付録ページは required=False で0件を必須にする。
    """
    label_text = "代表者の氏名"
    lines = raw_text.split("\n")
    matched = 0
    out_lines = []
    for line in lines:
        if line.startswith(label_text):
            if not line[len(label_text):].strip():
                raise ValueError(f"{pdf_name} p{page_no}: 代表者の氏名の値が空")
            out_lines.append(f"{label_text} [氏名-非出力]")
            matched += 1
        else:
            out_lines.append(line)
    expected = 1 if required else 0
    if matched != expected:
        raise ValueError(
            f"{pdf_name} p{page_no}: extract_text()内で「代表者の氏名」から始まる行が"
            f"期待件数{expected}と一致しない({matched}件)。置換不能。推定で先に進まず報告すること"
        )
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------

def main():
    TEXT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    operators = []
    vehicles = []

    for cfg in FILE_CONFIGS:
        pdf_path = RAW_DIR / cfg["filename"]
        with pdfplumber.open(pdf_path) as pdf:
            page_infos = []
            for page_no, page in enumerate(pdf.pages, start=1):
                words = page.extract_words()
                raw_text = page.extract_text() or ""
                has_anchor = bool(re.search(r"登\s*録\s*番\s*号", raw_text))
                is_appendix = bool(cfg.get("appendix_marker") and cfg["appendix_marker"] in raw_text)

                # 生テキストの保存(SPEC.md §4.4)。代表者氏名の値だけを伏字化する。
                redacted_text = redact_representative_name(
                    words, raw_text, cfg["filename"], page_no, required=has_anchor
                )
                text_path = TEXT_DIR / f"{pdf_path.stem}_p{page_no}.txt"
                text_path.write_text(redacted_text, encoding="utf-8")
                page_infos.append((page_no, page, has_anchor, is_appendix))

            blocks = []
            current = []
            for page_no, page, has_anchor, is_appendix in page_infos:
                if is_appendix:
                    if current:
                        blocks.append(current)
                        current = []
                    continue
                if has_anchor:
                    if current:
                        blocks.append(current)
                    current = [(page_no, page)]
                elif current:
                    current.append((page_no, page))
                else:
                    raise ValueError(
                        f"{cfg['filename']} p{page_no}: 登録番号なしで開始する継続ページ"
                    )
            if current:
                blocks.append(current)

            for block in blocks:
                if cfg["parser"] == "coordinate_page":
                    if len(block) != 1:
                        raise ValueError(
                            f"{cfg['filename']}: 既存座標パーサに複数ページ団体が入った: "
                            f"{[page_no for page_no, _ in block]}"
                        )
                    page_no, page = block[0]
                    operator, page_vehicles = parse_page(
                        page, page_no, cfg["filename"], cfg["operator_type"]
                    )
                elif cfg["parser"] == "table_block":
                    operator, page_vehicles = parse_table_block(
                        block, cfg["filename"], cfg["operator_type"]
                    )
                else:
                    raise ValueError(f"未知のパーサ種別: {cfg['parser']}")
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
