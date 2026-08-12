"""Build I-4 GTFS/GTFS-JP official-status data for the municipal supply view.

Source of truth for every fact in this module is the accepted GTFS-1 inventory
(`evidence/20260809_gtfs_yamaguchi_inventory.txt`) and the individual
`evidence/20260809_gtfs_source_*.txt` files it cites, confirmed 2026-08-09
(SPEC.md SS12.2). Local government codes come from the Ministry of Internal
Affairs and Communications official code list, confirmed separately
(`evidence/20260809_i4_soumu_local_gov_code_list.pdf` / the companion
`_inspection.txt`).

This module only re-expresses already-confirmed facts as structured data.
It does not look up, download, authenticate against, or parse any GTFS feed
(SPEC.md SS12.7).
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from build_site_data import MUNICIPALITIES

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DOCS_DATA_DIR = REPO_ROOT / "docs" / "data"

CHECKED_AT = "2026-08-12"

_COVERAGE_DISCOVERY_EVIDENCE = "evidence/20260812_work1_gtfs_coverage_discovery.json"
_COVERAGE_ROUTE7_EVIDENCE = "evidence/20260812_work1_gtfs_coverage_hikari_route7.json"
_COVERAGE_LIVE_CHECKS_EVIDENCE = "evidence/20260812_work1_gtfs_coverage_live_checks.json"

FEEDS_COLUMNS = [
    "feed_id", "publisher", "dataset_name", "official_page_url",
    "download_url_or_template", "access_status", "format_label",
    "official_reference_date", "reference_date_status", "catalog_updated_date",
    "official_valid_from", "official_valid_to", "validity_status_at_check",
    "checked_at", "license_name", "license_url", "scope_note", "source_evidence",
]

MUNICIPALITY_COLUMNS = [
    "municipality_code", "municipality", "availability_status", "feed_ids",
    "scope_note", "checked_at", "source_evidence",
]

# The 3 officially confirmed feeds (SPEC.md SS12.2, SS12.3 axis A/B/C).
FEEDS = [
    {
        "feed_id": "iwakuni-gtfsjp",
        "publisher": "岩国市",
        "dataset_name": "岩国市（生活交通バス・由宇地区バス）GTFS-JPデータ",
        "official_page_url": "https://yamaguchi-opendata.jp/ckan/dataset/352080-gtfsjp",
        "download_url_or_template": (
            "https://yamaguchi-opendata.jp/ckan/dataset/2dbaeb43-5134-4880-90a3-62870504f1d3/"
            "resource/bac76226-a946-466f-a94c-d61dcb6ab0dc/download/gtfs-jp2026-03-27_1458_.zip"
        ),
        "access_status": "public_head_confirmed",
        "format_label": "GTFS-JP（データセット名称）。カタログの「データ形式」欄はZIP",
        "official_reference_date": "2026-04-01",
        "reference_date_status": "confirmed",
        "catalog_updated_date": "2026-04-10",
        "official_valid_from": "",
        "official_valid_to": "",
        "validity_status_at_check": "not_confirmed",
        "checked_at": CHECKED_AT,
        "license_name": "クリエイティブ・コモンズ 表示（CC BY）",
        "license_url": "http://www.opendefinition.org/licenses/cc-by",
        "scope_note": (
            "対象は公式データセット名称にある生活交通バス・由宇地区バス（岩国市）。"
            "市域全体・全路線を網羅するとは公式記載からは確認していない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_ds_352080-gtfsjp.txt;"
            "evidence/20260809_gtfs_source_ydata_res_iwakuni_gtfs.txt;"
            "evidence/20260809_gtfs_source_zip_head_check.txt;"
            + _COVERAGE_LIVE_CHECKS_EVIDENCE
        ),
    },
    {
        "feed_id": "hikari-gtfs",
        "publisher": "光市",
        "dataset_name": "光市（広域生活交通、ひかりぐるりんバス、光市営バス）GTFSデータ",
        "official_page_url": "https://yamaguchi-opendata.jp/ckan/dataset/352101_kotsu001",
        "download_url_or_template": (
            "https://yamaguchi-opendata.jp/ckan/dataset/db885818-b1bd-4848-986f-45119e8acb31/"
            "resource/c804039c-7d37-4e45-9288-f09fc1bbd249/download/hikari_gtfs_20260401_.zip"
        ),
        "access_status": "public_head_confirmed",
        "format_label": "GTFS（データセット名称）。カタログの「データ形式」欄はZIP",
        "official_reference_date": "2026-04-01",
        "reference_date_status": "confirmed",
        "catalog_updated_date": "2026-03-03",
        "official_valid_from": "",
        "official_valid_to": "",
        "validity_status_at_check": "not_confirmed",
        "checked_at": CHECKED_AT,
        "license_name": "クリエイティブ・コモンズ 表示（CC BY）",
        "license_url": "http://www.opendefinition.org/licenses/cc-by",
        "scope_note": (
            "対象は公式データセット名称にある広域生活交通、ひかりぐるりんバス、光市営バス（光市）。"
            "受入済みGTFSの広域生活交通には、国土地理院逆ジオコードで周南市コード35215となる"
            "乗降停留所IDを31件確認した。光市・周南市の市域全体・全事業者・全路線を網羅するとは"
            "確認していない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_ds_352101_kotsu001.txt;"
            "evidence/20260809_gtfs_source_ydata_res_hikari_gtfs.txt;"
            "evidence/20260809_gtfs_source_zip_head_check.txt;"
            + _COVERAGE_LIVE_CHECKS_EVIDENCE + ";"
            + _COVERAGE_ROUTE7_EVIDENCE
        ),
    },
    {
        "feed_id": "sentetsu-odpt-gtfsjp",
        "publisher": "船木鉄道株式会社",
        "dataset_name": "船木鉄道株式会社 GTFS/GTFS-JP（船鉄バス）",
        "official_page_url": "https://ckan.odpt.org/dataset/sentetsu_bus_all_lines",
        "download_url_or_template": (
            "https://api.odpt.org/api/v4/files/odpt/SentetsuBus/AllLines.zip"
            "?date=20251117&acl:consumerKey=[アクセストークン/YOUR_ACCESS_TOKEN]"
        ),
        "access_status": "authentication_required_not_retrieved",
        "format_label": "GTFS/GTFS-JP（カタログの「データ形式」欄に明記）",
        "official_reference_date": "",
        "reference_date_status": "not_stated",
        "catalog_updated_date": "",
        "official_valid_from": "2025-11-17",
        "official_valid_to": "2026-11-16",
        "validity_status_at_check": "within_official_period",
        "checked_at": CHECKED_AT,
        "license_name": "公共交通オープンデータ基本ライセンス（ODPT基本ライセンス）",
        "license_url": "https://developer.odpt.org/terms",
        "scope_note": (
            "公式記載は「山口県宇部市・山陽小野田市・美祢市を運行するバス事業者のGTFSデータです」。"
            "市域全体・全路線を網羅するとは公式記載からは確認していない。"
            "認証キーを含むURL雛形は確認済みだが、認証済みファイル本体は未取得。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_odpt_sentetsu.txt;"
            "evidence/20260809_gtfs_source_odpt_sentetsu_res_latest.txt;"
            + _COVERAGE_DISCOVERY_EVIDENCE
        ),
    },
]

# MIC ("Soumu") official local government codes, "都道府県コード及び市区町村コード"
# (令和6年1月1日更新). evidence/20260809_i4_soumu_local_gov_code_list.pdf p.24;
# verbatim extracted text in evidence/20260809_i4_soumu_local_gov_code_list_inspection.txt
MUNICIPALITY_CODES = {
    "下関市": "352012", "宇部市": "352021", "山口市": "352039", "萩市": "352047",
    "防府市": "352063", "下松市": "352071", "岩国市": "352080", "光市": "352101",
    "長門市": "352110", "柳井市": "352128", "美祢市": "352136", "周南市": "352152",
    "山陽小野田市": "352161", "周防大島町": "353051", "和木町": "353213",
    "上関町": "353418", "田布施町": "353434", "平生町": "353442", "阿武町": "355020",
}

_CODE_SOURCE_EVIDENCE = (
    "evidence/20260809_i4_soumu_local_gov_code_list.pdf;"
    "evidence/20260809_i4_soumu_local_gov_code_list_inspection.txt"
)

# Axis A per municipality (SPEC.md SS12.3), plus the GTFS-1 evidence backing it.
MUNICIPALITY_STATUS = {
    "下関市": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": (
            "山口県オープンデータカタログサイトの下関市データセット47件（全3ページ）に"
            "バス・GTFS関連は無かった。市内主要バス事業者サンデン交通の公式バス情報ページにも"
            "GTFSの記載は無い。今回確認した公式資料の範囲での結果であり、GTFSが存在しないと"
            "断定するものではない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_org_35201.txt;"
            "evidence/20260809_gtfs_source_ydata_org_35201_p2.txt;"
            "evidence/20260809_gtfs_source_ydata_org_35201_p3.txt;"
            "evidence/20260809_gtfs_source_official_sandenkotsu_bus.txt"
        ),
    },
    "宇部市": {
        "availability_status": "confirmed",
        "feed_ids": ("sentetsu-odpt-gtfsjp",),
        "scope_note": (
            "宇部市自身の公式データセットにGTFSの記載は無く、市が自ら公開しているとは確認できない。"
            "市内で運行する船木鉄道の公式GTFSが対象地域に宇部市を明記している。"
            "市域全体・全路線を網羅するとは公式記載からは確認していない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_res_352021_bus.txt;"
            "evidence/20260809_gtfs_source_official_ube.txt;"
            "evidence/20260809_gtfs_source_odpt_sentetsu.txt"
        ),
    },
    "山口市": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": "公式データセットページに「本市では該当するデータを保有しておりません。」と明記。",
        "source_evidence": "evidence/20260809_gtfs_source_ydata_ds_busdata.txt",
    },
    "萩市": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": (
            "「萩循環まぁーるバス」関連の公式データセット2件のうち1件はリンク先ページが404、"
            "もう1件のリンク先ページにGTFSの記載は無かった。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_official_hagi1.txt;"
            "evidence/20260809_gtfs_source_official_hagi2.txt"
        ),
    },
    "防府市": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": (
            "公式データセットページに「『標準的なバス情報フォーマット』につきましては、"
            "データを保有しておりません。」と明記。"
        ),
        "source_evidence": "evidence/20260809_gtfs_source_ydata_res_352063-bus_information.txt",
    },
    "下松市": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": (
            "「バス情報」は下松市公式ページへのリンクのみでGTFSの記載は無い。"
            "「公共交通マップ」（下松市・周南市合同作成）はPDF/PNG/ZIP資源を持つが、"
            "内容は路線図・時刻表・乗換案内リンクでありGTFSの記載は無い。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_official_kudamatsu.txt;"
            "evidence/20260809_gtfs_source_ydata_ds_352071_public_transport.txt"
        ),
    },
    "岩国市": {
        "availability_status": "confirmed",
        "feed_ids": ("iwakuni-gtfsjp",),
        "scope_note": (
            "公式データセット名称にある生活交通バス・由宇地区バスが対象。"
            "市域全体・全路線を網羅するとは公式記載からは確認していない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_ds_352080-gtfsjp.txt;"
            "evidence/20260809_gtfs_source_ydata_res_iwakuni_gtfs.txt"
        ),
    },
    "光市": {
        "availability_status": "confirmed",
        "feed_ids": ("hikari-gtfs",),
        "scope_note": (
            "公式データセット名称にある広域生活交通、ひかりぐるりんバス、光市営バスが対象。"
            "広域生活交通は周南市内停留所も含む。光市の市域全体・全事業者・全路線を網羅するとは"
            "確認していない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_ds_352101_kotsu001.txt;"
            "evidence/20260809_gtfs_source_ydata_res_hikari_gtfs.txt;"
            + _COVERAGE_ROUTE7_EVIDENCE
        ),
    },
    "長門市": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": "公式データセット「R7.10バス・JR時刻表」はPDF時刻表で、GTFSの記載は無い。",
        "source_evidence": "evidence/20260809_gtfs_source_ydata_ds_r6-4-jr.txt",
    },
    "柳井市": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": (
            "公式データセットページに「柳井市では標準的なバス情報フォーマットに該当する"
            "データを保有しておりません。」と明記。"
        ),
        "source_evidence": "evidence/20260809_gtfs_source_ydata_res_352128_bus.txt",
    },
    "美祢市": {
        "availability_status": "confirmed",
        "feed_ids": ("sentetsu-odpt-gtfsjp",),
        "scope_note": (
            "美祢市自身の公式データセットページには「標準的なバス情報フォーマット（GTFS-JP）に"
            "ついて公開しておりません」と明記されているが、市内で運行する船木鉄道の公式GTFSが"
            "対象地域に美祢市を明記している。市域全体・全路線を網羅するとは公式記載からは"
            "確認していない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_ds_352136_gtfs-jp.txt;"
            "evidence/20260809_gtfs_source_odpt_sentetsu.txt"
        ),
    },
    "周南市": {
        "availability_status": "confirmed",
        "feed_ids": ("hikari-gtfs",),
        "scope_note": (
            "周南市自身の公式カタログではGTFS配布を確認できなかったが、光市が公式配布するGTFSの"
            "広域生活交通に、国土地理院逆ジオコードで周南市コード35215となる乗降停留所IDを31件"
            "（17停留所名）確認した。周南市内の全事業者・全路線を網羅するとは確認していない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_official_shunan.txt;"
            "evidence/20260809_gtfs_source_ydata_ds_352152_public_transport.txt;"
            + _COVERAGE_ROUTE7_EVIDENCE
        ),
    },
    "山陽小野田市": {
        "availability_status": "confirmed",
        "feed_ids": ("sentetsu-odpt-gtfsjp",),
        "scope_note": (
            "山陽小野田市自身の公式データセットは市公式ページへのリンクのみでGTFSの記載は無いが、"
            "市内で運行する船木鉄道の公式GTFSが対象地域に山陽小野田市を明記している。"
            "市域全体・全路線を網羅するとは公式記載からは確認していない。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_ds_352161_bus.txt;"
            "evidence/20260809_gtfs_source_official_sanyoonoda.txt;"
            "evidence/20260809_gtfs_source_odpt_sentetsu.txt"
        ),
    },
    "周防大島町": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": "公式データセット「公共交通機関時刻表」のリンク先ページが404で到達できなかった。",
        "source_evidence": "evidence/20260809_gtfs_source_official_suooshima.txt",
    },
    "和木町": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": (
            "山口県オープンデータカタログサイトの全文検索「和木町」25件（全2ページ）を確認したが、"
            "交通・バス関連データセット自体が無かった。"
        ),
        "source_evidence": (
            "evidence/20260809_gtfs_source_ydata_q_wakicho.txt;"
            "evidence/20260809_gtfs_source_ydata_q_wakicho_p2.txt"
        ),
    },
    "上関町": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": (
            "公式データセット「町営バス　時刻表」は令和元年10月1日時点のPDF時刻表で、"
            "GTFSの記載は無い。"
        ),
        "source_evidence": "evidence/20260809_gtfs_source_ydata_ds_353418-tyoueibas.txt",
    },
    "田布施町": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": "公式データセットページに「本町では町営バス事業を実施しておりません。」と明記。",
        "source_evidence": "evidence/20260809_gtfs_source_ydata_res_33.txt",
    },
    "平生町": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": "公式データセットページに「平生町では町営バス事業を実施していません。」と明記。",
        "source_evidence": "evidence/20260809_gtfs_source_ydata_res_353442_gtfs-jp.txt",
    },
    "阿武町": {
        "availability_status": "not_confirmed_in_checked_sources",
        "feed_ids": (),
        "scope_note": "公式データセット「町営バス時刻表」のリンク先ページにGTFSの記載は無い。",
        "source_evidence": "evidence/20260809_gtfs_source_official_abu.txt",
    },
}


def _check_data_consistency():
    """Fail loudly instead of silently drifting from the 19-municipality roster."""
    muni_set = set(MUNICIPALITIES)
    missing_codes = muni_set - set(MUNICIPALITY_CODES)
    missing_status = muni_set - set(MUNICIPALITY_STATUS)
    if missing_codes:
        raise ValueError(f"MUNICIPALITY_CODES に無い市町: {sorted(missing_codes)}")
    if missing_status:
        raise ValueError(f"MUNICIPALITY_STATUS に無い市町: {sorted(missing_status)}")

    feed_ids = {feed["feed_id"] for feed in FEEDS}
    for name, status in MUNICIPALITY_STATUS.items():
        for feed_id in status["feed_ids"]:
            if feed_id not in feed_ids:
                raise ValueError(f"{name} が未知の feed_id を参照: {feed_id}")


def build_municipality_rows():
    _check_data_consistency()
    rows = []
    for name in MUNICIPALITIES:
        status = MUNICIPALITY_STATUS[name]
        rows.append({
            "municipality_code": MUNICIPALITY_CODES[name],
            "municipality": name,
            "availability_status": status["availability_status"],
            "feed_ids": ";".join(status["feed_ids"]),
            "scope_note": status["scope_note"],
            "checked_at": CHECKED_AT,
            "source_evidence": (
                status["source_evidence"] + ";" + _CODE_SOURCE_EVIDENCE + ";"
                + _COVERAGE_DISCOVERY_EVIDENCE
            ),
        })
    return rows


def write_csv(path: Path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    write_csv(DATA_DIR / "gtfs_feeds.csv", FEEDS_COLUMNS, FEEDS)
    (DATA_DIR / "gtfs_feeds.json").write_text(
        json.dumps(FEEDS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    municipality_rows = build_municipality_rows()
    write_csv(DATA_DIR / "municipality_gtfs.csv", MUNICIPALITY_COLUMNS, municipality_rows)
    (DATA_DIR / "municipality_gtfs.json").write_text(
        json.dumps(municipality_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for filename in ("gtfs_feeds.json", "municipality_gtfs.json"):
        shutil.copyfile(DATA_DIR / filename, DOCS_DATA_DIR / filename)

    confirmed = sum(1 for r in municipality_rows if r["availability_status"] == "confirmed")
    not_confirmed = sum(
        1 for r in municipality_rows if r["availability_status"] == "not_confirmed_in_checked_sources"
    )
    unassessed = sum(1 for r in municipality_rows if r["availability_status"] == "unassessed")
    print(
        f"gtfs feeds: {len(FEEDS)}, municipalities: confirmed={confirmed} "
        f"not_confirmed={not_confirmed} unassessed={unassessed}"
    )


if __name__ == "__main__":
    main()
