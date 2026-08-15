"""Build deterministic static data for the municipal supply view (I-2)."""
from __future__ import annotations

import json
import hashlib
import shutil
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DOCS_DATA_DIR = REPO_ROOT / "docs" / "data"

MUNICIPALITY_SOURCE_URL = "https://www.pref.yamaguchi.lg.jp/soshiki/21/26969.html"
MUNICIPALITY_SOURCE_SHA256 = "c947ebd3e02ae11772db8aa4d28828747037e6d6d47113c5ee233213c61860e1"
MUNICIPALITIES = (
    "下関市", "宇部市", "山口市", "萩市", "防府市", "下松市", "岩国市",
    "光市", "長門市", "柳井市", "美祢市", "周南市", "山陽小野田市",
    "周防大島町", "和木町", "上関町", "田布施町", "平生町", "阿武町",
)
TRANSPORT_TYPES = ("福祉有償運送", "交通空白地有償運送")
SOURCE_INDEX_URL = "https://wwwtb.mlit.go.jp/chugoku/00001_00903.html"
SOURCE_ACQUIRED_DATES = {
    "000271730.pdf": "2026-08-07",
    "000230003.pdf": "2026-08-09",
    "000359215.pdf": "2026-08-09",
    "000268896.pdf": "2026-08-09",
}
SUPPLY_METRICS_FILENAME = "gtfs_supply_metrics.json"
SUPPLY_METRICS_SHA256 = "c277e1050086da6ad5cc703051deb672458f7bf2829e1aca92fd0b17b4d20930"
SUPPLY_FEED_ORDER = ("iwakuni-gtfsjp", "hikari-gtfs")
SUPPLY_METRIC_KEYS = (
    "gtfs_agency_record_count",
    "gtfs_route_id_count",
    "gtfs_boarding_location_id_count",
)
SUPPLY_METRIC_STATUSES = {
    "measured",
    "not_confirmed",
    "not_calculable",
    "invalid_input",
    "not_comparable_scope",
    "not_exact_frequency_based",
    "not_comparable_no_common_week",
}
JRBUS_SUPPLY_METRICS_FILENAME = "jrbus_chugoku_supply_metrics.json"
JRBUS_SUPPLY_METRICS_SHA256 = "eac7e55b0b548f2fe69cf8ce17a03d6d7f4516edf089da362ecbfcc371c6fc05"
JRBUS_FEED_ID = "jrbus-chugoku-gtfs"
JRBUS_ROUTE_ANCHORS = (
    ("2229846746", "防長線"),
    ("435934628", "新山口駅～東萩駅線（スーパーはぎ号）"),
    ("2196404353", "秋吉線"),
    ("3240589115", "秋芳洞循環バス"),
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_metric_value(metric, location):
    if not isinstance(metric, dict):
        raise ValueError(f"{location}: metric must be an object")
    status = metric.get("metric_status")
    value = metric.get("value")
    reason = metric.get("reason")
    if status not in SUPPLY_METRIC_STATUSES:
        raise ValueError(f"{location}: unknown metric_status {status!r}")
    if status == "measured":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{location}: measured value must be a non-negative integer")
        if reason is not None:
            raise ValueError(f"{location}: measured reason must be null")
        return
    if value is not None:
        raise ValueError(f"{location}: non-measured value must be null")
    if status != "not_confirmed" and (not isinstance(reason, str) or not reason.strip()):
        raise ValueError(f"{location}: {status} requires a reason")
    if reason is not None and not isinstance(reason, str):
        raise ValueError(f"{location}: reason must be text or null")


def validate_supply_metrics(records):
    if not isinstance(records, list) or len(records) != len(SUPPLY_FEED_ORDER):
        raise ValueError("supply metrics must contain exactly two feed records")
    if tuple(record.get("feed_id") for record in records) != SUPPLY_FEED_ORDER:
        raise ValueError("supply metric feed order or IDs do not match the accepted input")

    versions = {record.get("metric_version") for record in records}
    week_ranges = {
        (record.get("comparison_week_start"), record.get("comparison_week_end"))
        for record in records
    }
    if versions != {"SUPPLY-METRIC-1"}:
        raise ValueError("supply metric_version mismatch")
    if len(week_ranges) != 1:
        raise ValueError("supply comparison week mismatch")

    common_dates = None
    for record in records:
        required_text = (
            "municipality", "municipality_code", "source_zip_path", "source_zip_sha256",
            "scope_note", "official_reference_date", "checked_at", "metric_computed_at",
        )
        for key in required_text:
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f"{record.get('feed_id')}: missing {key}")
        source_hash = record["source_zip_sha256"]
        if len(source_hash) != 64 or any(character not in "0123456789abcdef" for character in source_hash):
            raise ValueError(f"{record['feed_id']}: invalid source ZIP SHA256")
        if not isinstance(record.get("date_basis"), dict):
            raise ValueError(f"{record['feed_id']}: date_basis must be an object")

        metrics = record.get("metrics")
        if not isinstance(metrics, dict) or tuple(metrics) != SUPPLY_METRIC_KEYS:
            raise ValueError(f"{record['feed_id']}: structural metric keys or order mismatch")
        for metric_id in SUPPLY_METRIC_KEYS:
            _validate_metric_value(metrics[metric_id], f"{record['feed_id']}.{metric_id}")

        scheduled = record.get("scheduled_trip_count_by_date")
        if not isinstance(scheduled, dict) or len(scheduled) != 7:
            raise ValueError(f"{record['feed_id']}: comparison week must contain seven dates")
        date_keys = tuple(scheduled)
        if common_dates is None:
            common_dates = date_keys
        elif date_keys != common_dates:
            raise ValueError("supply comparison date keys mismatch")
        parsed_dates = [date.fromisoformat(key) for key in date_keys]
        if any(right - left != timedelta(days=1) for left, right in zip(parsed_dates, parsed_dates[1:])):
            raise ValueError(f"{record['feed_id']}: comparison dates are not consecutive")
        if date_keys[0] != record["comparison_week_start"] or date_keys[-1] != record["comparison_week_end"]:
            raise ValueError(f"{record['feed_id']}: comparison week bounds mismatch")
        for date_key, metric in scheduled.items():
            _validate_metric_value(metric, f"{record['feed_id']}.{date_key}")


def publish_supply_metrics(source: Path, destination: Path):
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != SUPPLY_METRICS_SHA256:
        raise ValueError(f"unexpected {SUPPLY_METRICS_FILENAME} SHA256: {digest}")
    try:
        records = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {SUPPLY_METRICS_FILENAME}: {error}") from error
    validate_supply_metrics(records)
    shutil.copyfile(source, destination)
    if destination.read_bytes() != raw:
        raise RuntimeError(f"published {SUPPLY_METRICS_FILENAME} is not byte-identical")


def validate_jrbus_supply_metrics(record):
    if not isinstance(record, dict):
        raise ValueError("JR Bus supply metrics must be an object")
    expected = {
        "metric_version": "JRBUS-SUPPLY-METRIC-1",
        "feed_id": JRBUS_FEED_ID,
        "measurement_scope": "whole_feed",
        "comparison_mode": "independent_not_comparable",
    }
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError(f"JR Bus {key} mismatch")

    required_text = (
        "source_zip_path", "source_zip_sha256", "scope_note",
        "official_reference_date", "checked_at", "metric_computed_at",
        "comparison_week_start", "comparison_week_end",
    )
    for key in required_text:
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"JR Bus missing {key}")
    source_hash = record["source_zip_sha256"]
    if len(source_hash) != 64 or any(character not in "0123456789abcdef" for character in source_hash):
        raise ValueError("JR Bus invalid source ZIP SHA256")
    if isinstance(record.get("source_zip_size_bytes"), bool) or not isinstance(record.get("source_zip_size_bytes"), int):
        raise ValueError("JR Bus source ZIP size must be an integer")
    if record["source_zip_size_bytes"] <= 0:
        raise ValueError("JR Bus source ZIP size must be positive")
    if not isinstance(record.get("date_basis"), dict):
        raise ValueError("JR Bus date_basis must be an object")

    routes = record.get("confirmed_yamaguchi_routes")
    route_pairs = tuple(
        (item.get("route_id"), item.get("route_long_name"))
        for item in routes
    ) if isinstance(routes, list) else ()
    if route_pairs != JRBUS_ROUTE_ANCHORS:
        raise ValueError("JR Bus Yamaguchi route anchors mismatch")

    metrics = record.get("metrics")
    if not isinstance(metrics, dict) or tuple(metrics) != SUPPLY_METRIC_KEYS:
        raise ValueError("JR Bus structural metric keys or order mismatch")
    for metric_id in SUPPLY_METRIC_KEYS:
        _validate_metric_value(metrics[metric_id], f"{JRBUS_FEED_ID}.{metric_id}")

    scheduled = record.get("scheduled_trip_count_by_date")
    if not isinstance(scheduled, dict) or len(scheduled) != 7:
        raise ValueError("JR Bus comparison week must contain seven dates")
    date_keys = tuple(scheduled)
    parsed_dates = [date.fromisoformat(key) for key in date_keys]
    if any(right - left != timedelta(days=1) for left, right in zip(parsed_dates, parsed_dates[1:])):
        raise ValueError("JR Bus comparison dates are not consecutive")
    if date_keys[0] != record["comparison_week_start"] or date_keys[-1] != record["comparison_week_end"]:
        raise ValueError("JR Bus comparison week bounds mismatch")
    for date_key, metric in scheduled.items():
        _validate_metric_value(metric, f"{JRBUS_FEED_ID}.{date_key}")

    limitations = record.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 4:
        raise ValueError("JR Bus limitations must contain at least four items")
    if any(not isinstance(item, str) or not item.strip() for item in limitations):
        raise ValueError("JR Bus limitations must be non-empty text")


def publish_jrbus_supply_metrics(source: Path, destination: Path):
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != JRBUS_SUPPLY_METRICS_SHA256:
        raise ValueError(f"unexpected {JRBUS_SUPPLY_METRICS_FILENAME} SHA256: {digest}")
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {JRBUS_SUPPLY_METRICS_FILENAME}: {error}") from error
    validate_jrbus_supply_metrics(record)
    shutil.copyfile(source, destination)
    if destination.read_bytes() != raw:
        raise RuntimeError(f"published {JRBUS_SUPPLY_METRICS_FILENAME} is not byte-identical")


def in_municipality(operator, municipality):
    values = [value for value in operator["service_area_municipalities"].split(";") if value]
    return municipality in values


def summarize_operators(operators):
    return {
        "operator_count": len(operators),
        "vehicles_total": sum(int(operator["vehicles_total"]) for operator in operators),
        "vehicles_total_kei": sum(int(operator["vehicles_total_kei"]) for operator in operators),
    }


def public_operator(operator):
    source_pdf = operator["source_pdf"]
    return {
        "registration_no": operator["registration_no"],
        "org_name": operator["org_name"],
        "transport_type": operator["transport_type"],
        "operator_type": operator["operator_type"],
        "valid_to": operator["valid_to"],
        "vehicles_total": int(operator["vehicles_total"]),
        "vehicles_total_kei": int(operator["vehicles_total_kei"]),
        "source_pdf": source_pdf,
        "source_page": int(operator["source_page"]),
        "source_url": f"https://wwwtb.mlit.go.jp/chugoku/content/{source_pdf}",
    }


def build_supply(operators):
    municipalities = []
    for municipality in MUNICIPALITIES:
        related = [operator for operator in operators if in_municipality(operator, municipality)]
        by_transport_type = []
        for transport_type in TRANSPORT_TYPES:
            grouped = [operator for operator in related if operator["transport_type"] == transport_type]
            by_transport_type.append({
                "transport_type": transport_type,
                **summarize_operators(grouped),
            })
        municipalities.append({
            "municipality": municipality,
            **summarize_operators(related),
            "by_transport_type": by_transport_type,
            "operators": [public_operator(operator) for operator in related],
        })

    unique_totals = summarize_operators(operators)
    return {
        "meta": {
            "title": "山口県 市町別の登録供給ビュー",
            "data_as_of": "2026-08-09",
            "source_index_url": SOURCE_INDEX_URL,
            "source_files": list(SOURCE_ACQUIRED_DATES),
            "source_acquired_dates": SOURCE_ACQUIRED_DATES,
            "municipality_source_url": MUNICIPALITY_SOURCE_URL,
            "municipality_source_sha256": MUNICIPALITY_SOURCE_SHA256,
            "municipality_count": len(MUNICIPALITIES),
            "municipalities_with_records": sum(item["operator_count"] > 0 for item in municipalities),
            "unique_prefecture_totals": unique_totals,
        },
        "municipalities": municipalities,
    }


def main():
    operators = read_json(DATA_DIR / "operators.json")
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Published source tables must remain byte-for-byte identical to the verified outputs.
    for filename in ("operators.json", "vehicles.json"):
        shutil.copyfile(DATA_DIR / filename, DOCS_DATA_DIR / filename)
    publish_supply_metrics(
        DATA_DIR / SUPPLY_METRICS_FILENAME,
        DOCS_DATA_DIR / SUPPLY_METRICS_FILENAME,
    )
    publish_jrbus_supply_metrics(
        DATA_DIR / JRBUS_SUPPLY_METRICS_FILENAME,
        DOCS_DATA_DIR / JRBUS_SUPPLY_METRICS_FILENAME,
    )

    supply = build_supply(operators)
    (DOCS_DATA_DIR / "municipal_supply.json").write_text(
        json.dumps(supply, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"municipalities: {supply['meta']['municipality_count']}, "
        f"with records: {supply['meta']['municipalities_with_records']}, "
        f"operators: {supply['meta']['unique_prefecture_totals']['operator_count']}"
    )


if __name__ == "__main__":
    main()
