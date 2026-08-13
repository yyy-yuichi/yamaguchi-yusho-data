"""Build the accepted official-GTFS access status for all 19 municipalities.

The facts in this module are fixed by the accepted evidence referenced below.
It never downloads, authenticates, or silently adopts a remote feed.  Running it
only regenerates the CSV/JSON public views from those accepted facts.
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

CHECKED_AT = "2026-08-13"
_EXTENSION_EVIDENCE = (
    "evidence/20260813_work1_official_gtfs_coverage_extension_research.json"
)
_CODE_SOURCE_EVIDENCE = (
    "evidence/20260809_i4_soumu_local_gov_code_list.pdf;"
    "evidence/20260809_i4_soumu_local_gov_code_list_inspection.txt"
)
_LEGACY_COVERAGE_EVIDENCE = (
    "evidence/20260812_work1_gtfs_coverage_discovery.json;"
    "evidence/20260812_work1_gtfs_coverage_live_checks.json"
)

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


def _feed(
    feed_id: str,
    publisher: str,
    dataset_name: str,
    official_page_url: str,
    download_url_or_template: str,
    access_status: str,
    format_label: str,
    official_reference_date: str = "",
    reference_date_status: str = "not_confirmed",
    catalog_updated_date: str = "",
    official_valid_from: str = "",
    official_valid_to: str = "",
    validity_status_at_check: str = "not_confirmed",
    license_name: str = "要配布元確認",
    license_url: str = "",
    scope_note: str = "",
    source_evidence: str = _EXTENSION_EVIDENCE,
) -> dict[str, str]:
    return {
        "feed_id": feed_id,
        "publisher": publisher,
        "dataset_name": dataset_name,
        "official_page_url": official_page_url,
        "download_url_or_template": download_url_or_template,
        "access_status": access_status,
        "format_label": format_label,
        "official_reference_date": official_reference_date,
        "reference_date_status": reference_date_status,
        "catalog_updated_date": catalog_updated_date,
        "official_valid_from": official_valid_from,
        "official_valid_to": official_valid_to,
        "validity_status_at_check": validity_status_at_check,
        "checked_at": CHECKED_AT,
        "license_name": license_name,
        "license_url": license_url,
        "scope_note": scope_note,
        "source_evidence": source_evidence,
    }


# One row is one actual or historically recorded feed, not one municipality.
FEEDS = [
    _feed(
        "iwakuni-gtfsjp", "岩国市",
        "岩国市（生活交通バス・由宇地区バス）GTFS-JPデータ",
        "https://yamaguchi-opendata.jp/ckan/dataset/352080-gtfsjp",
        "https://yamaguchi-opendata.jp/ckan/dataset/2dbaeb43-5134-4880-90a3-62870504f1d3/resource/bac76226-a946-466f-a94c-d61dcb6ab0dc/download/gtfs-jp2026-03-27_1458_.zip",
        "public_download_confirmed", "GTFS-JP（ZIP）",
        "2026-04-01", "confirmed", "2026-04-10",
        license_name="クリエイティブ・コモンズ 表示（CC BY）",
        license_url="http://www.opendefinition.org/licenses/cc-by",
        scope_note="生活交通バス・由宇地区バスのフィード。市域の全交通を示すものではない。",
        source_evidence=(
            "evidence/20260809_gtfs_source_ydata_ds_352080-gtfsjp.txt;"
            "evidence/20260809_gtfs_source_ydata_res_iwakuni_gtfs.txt;"
            + _LEGACY_COVERAGE_EVIDENCE
        ),
    ),
    _feed(
        "hikari-gtfs", "光市",
        "光市（広域生活交通、ひかりぐるりんバス、光市営バス）GTFSデータ",
        "https://yamaguchi-opendata.jp/ckan/dataset/352101_kotsu001",
        "https://yamaguchi-opendata.jp/ckan/dataset/db885818-b1bd-4848-986f-45119e8acb31/resource/c804039c-7d37-4e45-9288-f09fc1bbd249/download/hikari_gtfs_20260401_.zip",
        "public_download_confirmed", "GTFS（ZIP）",
        "2026-04-01", "confirmed", "2026-03-03",
        license_name="クリエイティブ・コモンズ 表示（CC BY）",
        license_url="http://www.opendefinition.org/licenses/cc-by",
        scope_note=(
            "光市の3系統群に加え、受入済みZIPの路線7で周南市内の停留所を確認。"
            "両市の全交通を示すものではない。"
        ),
        source_evidence=(
            "evidence/20260809_gtfs_source_ydata_ds_352101_kotsu001.txt;"
            "evidence/20260809_gtfs_source_ydata_res_hikari_gtfs.txt;"
            "evidence/20260812_work1_gtfs_coverage_hikari_route7.json;"
            + _LEGACY_COVERAGE_EVIDENCE
        ),
    ),
    _feed(
        "sentetsu-odpt-gtfsjp", "船木鉄道株式会社", "船木鉄道株式会社 GTFS/GTFS-JP（船鉄バス）",
        "https://ckan.odpt.org/dataset/sentetsu_bus_all_lines",
        "https://api.odpt.org/api/v4/files/odpt/SentetsuBus/AllLines.zip?date=20251117&acl:consumerKey=[アクセストークン/YOUR_ACCESS_TOKEN]",
        "authentication_required", "GTFS/GTFS-JP（認証が必要なZIP）",
        "", "not_stated", "", "2025-11-17", "2026-11-16",
        "within_official_period", "公共交通オープンデータ基本ライセンス（ODPT基本ライセンス）",
        "https://developer.odpt.org/terms",
        scope_note=(
            "宇部市・山陽小野田市・美祢市を運行対象とする公式記載。"
            "認証キーを含むURL雛形は確認済みだが、認証済み本体は未取得。"
        ),
        source_evidence=(
            "evidence/20260809_gtfs_source_odpt_sentetsu.txt;"
            "evidence/20260809_gtfs_source_odpt_sentetsu_res_latest.txt;"
            + _LEGACY_COVERAGE_EVIDENCE
        ),
    ),
    _feed(
        "jrbus-chugoku-gtfs", "JRバス中国株式会社", "JRバス中国 GTFS-JP 現在データ",
        "https://www.bus-kyo.or.jp/gtfs-open-data",
        "https://ajt-mobusta-gtfs.mcapps.jp/static/15/current_data.zip",
        "public_download_confirmed", "GTFS-JP（ZIP）",
        "2026-08-13", "confirmed", "", "2026-08-13", "2027-02-13",
        "valid_on_checked_date", "クリエイティブ・コモンズ CC0",
        "https://creativecommons.org/publicdomain/zero/1.0/deed.ja",
        (
            "受入済みZIPのうち、防長線、スーパーはぎ号、秋吉線、秋芳洞循環バスから"
            "山口市・萩市・防府市・美祢市との関係を確認。フィード全18路線の値を"
            "各市内だけの供給量としては扱わない。"
        ),
    ),
    _feed(
        "bocho-kotsu-gtfsjp", "防長交通株式会社", "防長交通 GTFS-JP（静的）",
        "https://www.city.yamaguchi.lg.jp/uploaded/attachment/116769.pdf", "",
        "not_publicly_distributed", "GTFS-JP（静的・一般配布なし）",
        scope_note=(
            "山口市公式資料は一般路線等のGTFS-JP整備と非公開を明記。"
            "事業者公式の営業所案内で関係市町を対応付けた。データ本体は未取得。"
        ),
    ),
    _feed(
        "sanden-kotsu-gtfs", "サンデン交通株式会社", "サンデン交通 GTFSデータ",
        "https://www.city.shimonoseki.lg.jp/uploaded/attachment/88084.pdf", "",
        "not_publicly_distributed", "GTFS（一般配布先未確認）",
        "2024-03-01", "confirmed",
        scope_note="下関市公式計画がR6.3時点のGTFSデータを資料として使用。一般向け配布URLは確認できていない。",
    ),
    _feed(
        "blueline-kotsu-gtfs", "ブルーライン交通株式会社", "ブルーライン交通 GTFSデータ",
        "https://www.city.shimonoseki.lg.jp/uploaded/attachment/88088.pdf", "",
        "not_publicly_distributed", "GTFS（一般配布先未確認）",
        "2024-04-01", "confirmed",
        scope_note="下関市公式計画がR6.4時点のGTFSデータを資料として使用。一般向け配布URLは確認できていない。",
    ),
    _feed(
        "waki-community-bus-gtfsjp", "和木町", "和木町コミュニティバスGTFS-JPデータ",
        "https://hiroshima-opendata.dataeye.jp/datasets/1242",
        "https://yamaguchi-opendata.jp/ckan/dataset/366cff59-5ba5-4a54-9d9f-5312172f1b83/resource/c2b5f413-de36-44bf-bcd8-e91848b35640/download/gtfs20210922.zip",
        "official_resource_unavailable", "GTFS-JP（過去の公式配布記録・現在404）",
        "2021-09-22", "confirmed", "2022-02-15", validity_status_at_check="not_current_resource",
        license_name="公共データ利用規約（第1.0版）",
        license_url="https://www.digital.go.jp/resources/open_data/public_data_license_v1.0",
        scope_note="公式ポータルに配布記録は残るが、2026-08-13時点でZIP URLはHTTP 404。本体は採用していない。",
    ),
]

MUNICIPALITY_CODES = {
    "下関市": "352012", "宇部市": "352021", "山口市": "352039", "萩市": "352047",
    "防府市": "352063", "下松市": "352071", "岩国市": "352080", "光市": "352101",
    "長門市": "352110", "柳井市": "352128", "美祢市": "352136", "周南市": "352152",
    "山陽小野田市": "352161", "周防大島町": "353051", "和木町": "353213",
    "上関町": "353418", "田布施町": "353434", "平生町": "353442", "阿武町": "355020",
}


def _status(availability_status: str, feed_ids: tuple[str, ...], scope_note: str) -> dict:
    return {
        "availability_status": availability_status,
        "feed_ids": feed_ids,
        "scope_note": scope_note,
        "source_evidence": _EXTENSION_EVIDENCE,
    }


MUNICIPALITY_STATUS = {
    "下関市": _status("not_publicly_distributed", ("sanden-kotsu-gtfs", "blueline-kotsu-gtfs"), "市公式計画で2事業者のGTFS利用を確認したが、一般向け配布先は確認できていない。"),
    "宇部市": _status("authentication_required", ("sentetsu-odpt-gtfsjp",), "船木鉄道の公式GTFS-JPは認証が必要。本体は未取得。"),
    "山口市": _status("public_download_confirmed", ("jrbus-chugoku-gtfs", "bocho-kotsu-gtfsjp"), "JRバス中国は公開取得済み。防長交通は存在確認済みだが一般配布なし。"),
    "萩市": _status("public_download_confirmed", ("jrbus-chugoku-gtfs", "bocho-kotsu-gtfsjp"), "JRバス中国は公開取得済み。防長交通は存在確認済みだが一般配布なし。"),
    "防府市": _status("public_download_confirmed", ("jrbus-chugoku-gtfs", "bocho-kotsu-gtfsjp"), "JRバス中国は公開取得済み。防長交通は存在確認済みだが一般配布なし。"),
    "下松市": _status("not_publicly_distributed", ("bocho-kotsu-gtfsjp",), "防長交通の運行地域とGTFS-JP存在を確認したが、一般配布はない。"),
    "岩国市": _status("public_download_confirmed", ("iwakuni-gtfsjp",), "岩国市公式ZIPを取得・安全確認済み。市内全交通を示すものではない。"),
    "光市": _status("public_download_confirmed", ("hikari-gtfs", "bocho-kotsu-gtfsjp"), "光市公式ZIPを取得済み。防長交通は存在確認済みだが一般配布なし。"),
    "長門市": _status("not_publicly_distributed", ("bocho-kotsu-gtfsjp",), "防長交通の運行地域とGTFS-JP存在を確認したが、一般配布はない。"),
    "柳井市": _status("not_publicly_distributed", ("bocho-kotsu-gtfsjp",), "防長交通の運行地域とGTFS-JP存在を確認したが、一般配布はない。"),
    "美祢市": _status("public_download_confirmed", ("jrbus-chugoku-gtfs", "sentetsu-odpt-gtfsjp", "bocho-kotsu-gtfsjp"), "JRバス中国は公開取得済み。船木鉄道は認証必要、防長交通は一般配布なし。"),
    "周南市": _status("public_download_confirmed", ("hikari-gtfs", "bocho-kotsu-gtfsjp"), "光市公式ZIPの路線7で関係を確認。防長交通は一般配布なし。"),
    "山陽小野田市": _status("authentication_required", ("sentetsu-odpt-gtfsjp",), "船木鉄道の公式GTFS-JPは認証が必要。本体は未取得。"),
    "周防大島町": _status("not_publicly_distributed", ("bocho-kotsu-gtfsjp",), "防長交通の運行地域とGTFS-JP存在を確認したが、一般配布はない。"),
    "和木町": _status("official_resource_unavailable", ("waki-community-bus-gtfsjp",), "公式配布記録はあるが、現在のZIP URLはHTTP 404。本体は採用していない。"),
    "上関町": _status("not_publicly_distributed", ("bocho-kotsu-gtfsjp",), "防長交通の運行地域とGTFS-JP存在を確認したが、一般配布はない。"),
    "田布施町": _status("not_publicly_distributed", ("bocho-kotsu-gtfsjp",), "防長交通の運行地域とGTFS-JP存在を確認したが、一般配布はない。"),
    "平生町": _status("not_publicly_distributed", ("bocho-kotsu-gtfsjp",), "防長交通の運行地域とGTFS-JP存在を確認したが、一般配布はない。"),
    "阿武町": _status("not_publicly_distributed", ("bocho-kotsu-gtfsjp",), "防長交通の運行地域とGTFS-JP存在を確認したが、一般配布はない。"),
}

AVAILABILITY_STATUSES = frozenset({
    "public_download_confirmed", "authentication_required",
    "not_publicly_distributed", "official_resource_unavailable",
})


def _check_data_consistency() -> None:
    municipality_set = set(MUNICIPALITIES)
    if municipality_set != set(MUNICIPALITY_CODES):
        raise ValueError("MUNICIPALITY_CODES must contain exactly the 19 official municipalities")
    if municipality_set != set(MUNICIPALITY_STATUS):
        raise ValueError("MUNICIPALITY_STATUS must contain exactly the 19 official municipalities")
    feed_ids = [feed["feed_id"] for feed in FEEDS]
    if len(feed_ids) != len(set(feed_ids)):
        raise ValueError("duplicate feed_id")
    known_feed_ids = set(feed_ids)
    for name, status in MUNICIPALITY_STATUS.items():
        if status["availability_status"] not in AVAILABILITY_STATUSES:
            raise ValueError(f"{name}: unknown availability_status")
        if not status["feed_ids"]:
            raise ValueError(f"{name}: accepted status must cite at least one feed")
        unknown = set(status["feed_ids"]) - known_feed_ids
        if unknown:
            raise ValueError(f"{name}: unknown feed_id {sorted(unknown)}")


def build_municipality_rows() -> list[dict[str, str]]:
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
            "source_evidence": status["source_evidence"] + ";" + _CODE_SOURCE_EVIDENCE,
        })
    return rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
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
    counts = {
        status: sum(row["availability_status"] == status for row in municipality_rows)
        for status in sorted(AVAILABILITY_STATUSES)
    }
    print(f"gtfs feed records: {len(FEEDS)}, municipality access states: {counts}")


if __name__ == "__main__":
    main()
