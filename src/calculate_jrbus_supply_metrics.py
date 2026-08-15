"""JRバス中国の受入済み広域GTFSを、既存2フィード比較と分離して測定する。

出力はフィード全体の値であり、山口市・萩市・防府市・美祢市それぞれの市内値ではない。
山口県関係4路線は関係根拠として固定するが、その4路線だけへ供給値を切り分けない。
計算規則はSPEC.md §34から参照される§15.4〜§15.6を再利用する。
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import calculate_gtfs_supply_metrics as csm
import inspect_gtfs_archives as gi


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

METRIC_VERSION = "JRBUS-SUPPLY-METRIC-1"
FEED_ID = "jrbus-chugoku-gtfs"
SOURCE_ZIP_RELATIVE_PATH = "raw/gtfs/jrbus_chugoku_gtfs_20260813.zip"
SOURCE_ZIP_SHA256 = "9162224158a8a748d0365e850f2c0575c845a98063b7a469912c0a15b9201620"
SOURCE_ZIP_SIZE_BYTES = 1_863_715
OFFICIAL_REFERENCE_DATE = "2026-08-13"
CHECKED_AT = "2026-08-13"
METRIC_COMPUTED_AT = "2026-08-15"
TARGET_WEEK_DATES: Tuple[date, ...] = tuple(
    date(2026, 8, 17) + timedelta(days=offset) for offset in range(7)
)
STRUCTURE_METRIC_KEYS = (
    "gtfs_agency_record_count",
    "gtfs_route_id_count",
    "gtfs_boarding_location_id_count",
)

CONFIRMED_YAMAGUCHI_ROUTES: Tuple[Tuple[str, str], ...] = (
    ("2229846746", "防長線"),
    ("435934628", "新山口駅～東萩駅線（スーパーはぎ号）"),
    ("2196404353", "秋吉線"),
    ("3240589115", "秋芳洞循環バス"),
)

SCOPE_NOTE = (
    "JRバス中国の受入済みGTFSに含まれる県外を含む広域フィード全体の収録値。"
    "山口県関係4路線は関係根拠として示すが、表示値を4路線だけ、4市内だけ、"
    "山口県内だけの値へ分割していない。既存の岩国市・光市2フィード比較とは別枠であり、"
    "市町間の順位・比率・合計には用いない。"
)

LIMITATIONS: Tuple[str, ...] = (
    "県外を含む広域フィード全体の値であり、4市それぞれの市内供給量ではない。",
    "路線ID数はデータ作成者のID単位であり、現実の路線・系統の本数とは限らない。",
    "乗降場所ID数は方向別・のりば別に分かれ得るため、物理的な停留所数ではない。",
    "予定運行便数はGTFS上の予定であり、実運行、利用者数、利便性、定時性を表さない。",
)


def _confirmed_route_records(zf: zipfile.ZipFile) -> List[dict]:
    """routes.txtから山口県関係4路線を、仕様で固定した順序で読み戻す。"""
    table = csm.read_table(zf, "routes.txt")
    if not table.present or table.decode_error or table.header is None or table.rows is None:
        raise ValueError("routes.txtを検証済み表として読めない")
    required = ("route_id", "route_long_name")
    if any(column not in table.header for column in required):
        raise ValueError("routes.txtの必須列が不足している")
    route_id_index = table.header.index("route_id")
    route_name_index = table.header.index("route_long_name")
    route_ids = [row[route_id_index].strip() for row in table.rows]
    if any(not route_id for route_id in route_ids) or len(route_ids) != len(set(route_ids)):
        raise ValueError("routes.txtのroute_idが空欄または重複している")
    by_id: Dict[str, str] = {
        row[route_id_index].strip(): row[route_name_index].strip() for row in table.rows
    }
    records: List[dict] = []
    for route_id, expected_name in CONFIRMED_YAMAGUCHI_ROUTES:
        actual_name = by_id.get(route_id)
        if actual_name != expected_name:
            raise ValueError(
                f"確認済み路線が原本と一致しない: {route_id} {actual_name!r} != {expected_name!r}"
            )
        records.append({"route_id": route_id, "route_long_name": actual_name})
    return records


def build_dataset() -> dict:
    """固定した1原本から独立指標JSONの単一オブジェクトを組み立てる。"""
    zip_path = REPO_ROOT.joinpath(*SOURCE_ZIP_RELATIVE_PATH.split("/"))
    source_sha256, source_size = gi.sha256_of_file(str(zip_path))
    if source_sha256 != SOURCE_ZIP_SHA256 or source_size != SOURCE_ZIP_SIZE_BYTES:
        raise ValueError("JRバス中国GTFS原本のbytesまたはSHA256が固定値と一致しない")

    with zipfile.ZipFile(zip_path) as zf:
        confirmed_routes = _confirmed_route_records(zf)

    result = csm.compute_feed_metrics(
        str(zip_path),
        feed_id=FEED_ID,
        municipality_code="not_applicable",
        municipality="広域フィード全体",
        official_reference_date=OFFICIAL_REFERENCE_DATE,
        checked_at=CHECKED_AT,
        scope_note=SCOPE_NOTE,
        metric_computed_at=METRIC_COMPUTED_AT,
        week_dates=TARGET_WEEK_DATES,
    )
    return {
        "metric_version": METRIC_VERSION,
        "feed_id": FEED_ID,
        "measurement_scope": "whole_feed",
        "comparison_mode": "independent_not_comparable",
        "source_zip_path": SOURCE_ZIP_RELATIVE_PATH,
        "source_zip_sha256": source_sha256,
        "source_zip_size_bytes": source_size,
        "scope_note": SCOPE_NOTE,
        "official_reference_date": OFFICIAL_REFERENCE_DATE,
        "checked_at": CHECKED_AT,
        "metric_computed_at": METRIC_COMPUTED_AT,
        "comparison_week_start": TARGET_WEEK_DATES[0].isoformat(),
        "comparison_week_end": TARGET_WEEK_DATES[-1].isoformat(),
        "date_basis": result.date_basis,
        "confirmed_yamaguchi_routes": confirmed_routes,
        "metrics": {key: value.to_json() for key, value in result.metrics.items()},
        "scheduled_trip_count_by_date": {
            key: value.to_json() for key, value in result.scheduled_trip_count_by_date.items()
        },
        "limitations": list(LIMITATIONS),
    }


def render_dataset_json(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    payload = render_dataset_json(build_dataset()).encode("utf-8")
    output_path = DATA_DIR / "jrbus_chugoku_supply_metrics.json"
    output_path.write_bytes(payload)
    record = json.loads(payload)
    structure = [record["metrics"][key]["value"] for key in STRUCTURE_METRIC_KEYS]
    daily = [item["value"] for item in record["scheduled_trip_count_by_date"].values()]
    print(f"output={output_path.relative_to(REPO_ROOT).as_posix()}")
    print(f"bytes={len(payload)} sha256={hashlib.sha256(payload).hexdigest()}")
    print(f"structure={structure} daily={daily}")
    print(f"confirmed_yamaguchi_routes={len(record['confirmed_yamaguchi_routes'])}")


if __name__ == "__main__":
    main()
