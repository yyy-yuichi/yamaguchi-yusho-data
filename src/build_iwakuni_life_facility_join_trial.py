"""岩国市公式3施設データと既存バス停の小規模な座標結合試験を決定的に生成する。

この処理はデータ結合可能性だけを確認する。岩国市を最終対象地域に固定せず、徒歩経路、
徒歩圏、所要時間、施設の利用可能性、生活行程の成立を判定しない。公式CSVは ``raw/`` の
保存済み原本を読み取り専用で使い、GTFS ZIPも展開せず ``stops.txt`` だけをメモリ上で読む。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import unicodedata
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_REGISTRY_PATH = REPO_ROOT / "data" / "iwakuni_life_facility_sources.json"
OUTPUT_PATH = REPO_ROOT / "data" / "iwakuni_life_facility_join_trial.json"

TASK_ID = "WORK1-IWAKUNI-LIFE-FACILITY-JOIN-TRIAL-1"
GENERATED_AT = "2026-08-27"
DUPLICATE_DISTANCE_THRESHOLD_METERS = 30.0
BUS_STOP_SAMPLE_SIZE = 5
EARTH_RADIUS_METERS = 6_371_008.8


def sha256_file(path: Path) -> Tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def load_source_registry(path: Path = SOURCE_REGISTRY_PATH) -> dict:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("task_id") != TASK_ID:
        raise ValueError("source_registry_task_id_mismatch")
    sources = registry.get("facility_sources")
    if not isinstance(sources, list) or len(sources) != 3:
        raise ValueError("exactly_three_facility_sources_required")
    return registry


def _repo_path(relative_path: str) -> Path:
    path = REPO_ROOT.joinpath(*relative_path.split("/"))
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise ValueError("source_path_outside_repository") from error
    return path


def verify_registered_file(source: Mapping[str, object]) -> Path:
    path = _repo_path(str(source["raw_path"]))
    actual_size, actual_sha256 = sha256_file(path)
    if actual_size != int(source["bytes"]):
        raise ValueError(f"source_size_mismatch:{source['source_id'] if 'source_id' in source else source['feed_id']}")
    if actual_sha256 != str(source["sha256"]):
        raise ValueError(f"source_sha256_mismatch:{source['source_id'] if 'source_id' in source else source['feed_id']}")
    return path


def parse_coordinate(value: object, minimum: float, maximum: float) -> Tuple[float | None, str]:
    text = "" if value is None else str(value).strip()
    if not text:
        return None, "missing"
    try:
        number = float(text)
    except ValueError:
        return None, "invalid"
    if not math.isfinite(number) or not minimum <= number <= maximum:
        return None, "invalid"
    return number, "valid"


def normalize_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", "" if value is None else str(value))
    return "".join(text.split()).casefold()


def _source_category(source: Mapping[str, object], row: Mapping[str, str]) -> str:
    classification = source["source_classification"]
    if not isinstance(classification, Mapping):
        raise ValueError("invalid_source_classification")
    mode = classification.get("mode")
    if mode == "dataset":
        return str(classification.get("value") or "").strip()
    if mode == "record":
        return str(row.get(str(classification.get("field")), "")).strip()
    raise ValueError("unknown_source_classification_mode")


def read_facility_rows(source: Mapping[str, object]) -> List[Dict[str, str]]:
    path = verify_registered_file(source)
    raw = path.read_bytes()
    text = raw.decode(str(source["encoding"]))
    return list(csv.DictReader(io.StringIO(text, newline="")))


def normalize_facility_source(
    source: Mapping[str, object], rows: Sequence[Mapping[str, str]]
) -> Tuple[List[dict], dict]:
    records: List[dict] = []
    quality = {
        "source_id": source["source_id"],
        "dataset_label": source["dataset_label"],
        "source_row_count": len(rows),
        "normalized_record_count": 0,
        "excluded_from_join_count": 0,
        "missing_name_count": 0,
        "missing_coordinate_count": 0,
        "invalid_coordinate_count": 0,
        "missing_classification_count": 0,
        "duplicate_candidate_record_count": 0,
        "duplicate_candidate_pair_count": 0,
        "classification_mode": source["source_classification"]["mode"],
    }

    for row_number, row in enumerate(rows, start=2):
        name = str(row.get(str(source["name_field"]), "")).strip()
        latitude, latitude_status = parse_coordinate(row.get(str(source["latitude_field"])), -90.0, 90.0)
        longitude, longitude_status = parse_coordinate(
            row.get(str(source["longitude_field"])), -180.0, 180.0
        )
        category = _source_category(source, row)

        if not name:
            quality["missing_name_count"] += 1
        if "missing" in (latitude_status, longitude_status):
            quality["missing_coordinate_count"] += 1
            coordinate_status = "missing"
        elif "invalid" in (latitude_status, longitude_status):
            quality["invalid_coordinate_count"] += 1
            coordinate_status = "invalid"
        else:
            coordinate_status = "valid"
        if not category:
            quality["missing_classification_count"] += 1

        if not name or coordinate_status != "valid":
            continue

        record_id = str(row.get(str(source["record_id_field"]), "")).strip()
        stable_record_id = record_id or f"row-{row_number}"
        records.append(
            {
                "facility_id": f"{source['source_id']}:{stable_record_id}",
                "facility_name": name,
                "common_category": source["common_category"],
                "source_category": category or None,
                "latitude": latitude,
                "longitude": longitude,
                "source_updated_at": source["resource_last_modified"],
                "source": {
                    "source_id": source["source_id"],
                    "dataset_id": source["dataset_id"],
                    "resource_id": source["resource_id"],
                    "raw_path": source["raw_path"],
                    "source_row_number": row_number,
                    "source_record_id": record_id or None,
                    "dataset_page_url": source["dataset_page_url"],
                    "resource_url": source["resource_url"],
                    "retrieved_at": GENERATED_AT,
                },
                "license": {
                    "id": source["license_id"],
                    "name": source["license_name"],
                    "url": source["license_url"],
                },
            }
        )

    quality["normalized_record_count"] = len(records)
    quality["excluded_from_join_count"] = len(rows) - len(records)
    return records, quality


def haversine_meters(latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float) -> float:
    lat_a, lon_a, lat_b, lon_b = map(
        math.radians, (latitude_a, longitude_a, latitude_b, longitude_b)
    )
    delta_latitude = lat_b - lat_a
    delta_longitude = lon_b - lon_a
    haversine = (
        math.sin(delta_latitude / 2.0) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_longitude / 2.0) ** 2
    )
    return EARTH_RADIUS_METERS * 2.0 * math.asin(min(1.0, math.sqrt(haversine)))


def find_duplicate_candidates(records: Sequence[Mapping[str, object]]) -> List[dict]:
    candidates: List[dict] = []
    for index, first in enumerate(records):
        first_name = normalize_name(first["facility_name"])
        if not first_name:
            continue
        for second in records[index + 1 :]:
            if first_name != normalize_name(second["facility_name"]):
                continue
            distance = haversine_meters(
                float(first["latitude"]),
                float(first["longitude"]),
                float(second["latitude"]),
                float(second["longitude"]),
            )
            if distance <= DUPLICATE_DISTANCE_THRESHOLD_METERS:
                candidates.append(
                    {
                        "first_facility_id": first["facility_id"],
                        "second_facility_id": second["facility_id"],
                        "normalized_name": first_name,
                        "straight_line_distance_m": round(distance, 1),
                    }
                )
    return candidates


def apply_duplicate_quality_counts(
    records: Sequence[Mapping[str, object]], quality: Sequence[dict], candidates: Sequence[Mapping[str, object]]
) -> None:
    source_by_facility_id = {
        str(record["facility_id"]): str(record["source"]["source_id"]) for record in records
    }
    candidate_records: Dict[str, set[str]] = {str(item["source_id"]): set() for item in quality}
    candidate_pairs: Dict[str, int] = {str(item["source_id"]): 0 for item in quality}
    for candidate in candidates:
        pair_sources = set()
        for key in ("first_facility_id", "second_facility_id"):
            facility_id = str(candidate[key])
            source_id = source_by_facility_id[facility_id]
            candidate_records[source_id].add(facility_id)
            pair_sources.add(source_id)
        for source_id in pair_sources:
            candidate_pairs[source_id] += 1
    for item in quality:
        source_id = str(item["source_id"])
        item["duplicate_candidate_record_count"] = len(candidate_records[source_id])
        item["duplicate_candidate_pair_count"] = candidate_pairs[source_id]


def read_valid_bus_stops(bus_source: Mapping[str, object]) -> Tuple[List[dict], dict]:
    path = verify_registered_file(bus_source)
    with zipfile.ZipFile(path) as archive:
        member = next(
            (
                name
                for name in archive.namelist()
                if name.replace("\\", "/").lower().endswith("stops.txt")
            ),
            None,
        )
        if member is None:
            raise ValueError("gtfs_stops_missing")
        rows = list(csv.DictReader(io.StringIO(archive.read(member).decode("utf-8-sig"), newline="")))

    valid_stops: List[dict] = []
    missing_coordinate_count = 0
    invalid_coordinate_count = 0
    excluded_location_type_count = 0
    for row in rows:
        if str(row.get("location_type", "")).strip() not in ("", "0"):
            excluded_location_type_count += 1
            continue
        latitude, latitude_status = parse_coordinate(row.get("stop_lat"), -90.0, 90.0)
        longitude, longitude_status = parse_coordinate(row.get("stop_lon"), -180.0, 180.0)
        if "missing" in (latitude_status, longitude_status):
            missing_coordinate_count += 1
            continue
        if "invalid" in (latitude_status, longitude_status):
            invalid_coordinate_count += 1
            continue
        stop_name = str(row.get("stop_name", "")).strip()
        stop_id = str(row.get("stop_id", "")).strip()
        if not stop_name or not stop_id:
            continue
        valid_stops.append(
            {
                "stop_id": stop_id,
                "stop_name": stop_name,
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    summary = {
        "source_row_count": len(rows),
        "valid_boarding_location_count": len(valid_stops),
        "missing_coordinate_count": missing_coordinate_count,
        "invalid_coordinate_count": invalid_coordinate_count,
        "excluded_location_type_count": excluded_location_type_count,
    }
    return valid_stops, summary


def select_bus_stop_sample(stops: Iterable[Mapping[str, object]], sample_size: int = BUS_STOP_SAMPLE_SIZE) -> List[dict]:
    selected: List[dict] = []
    seen_names = set()
    for stop in sorted(stops, key=lambda item: (str(item["stop_id"]), str(item["stop_name"]))):
        name_key = normalize_name(stop["stop_name"])
        if not name_key or name_key in seen_names:
            continue
        seen_names.add(name_key)
        selected.append(dict(stop))
        if len(selected) == sample_size:
            break
    if len(selected) != sample_size:
        raise ValueError("not_enough_unique_bus_stop_names")
    return selected


def build_join_trial(sample_stops: Sequence[Mapping[str, object]], facilities: Sequence[Mapping[str, object]]) -> dict:
    categories = ("public_facility", "medical_facility", "childcare_facility")
    by_category = {
        category: [record for record in facilities if record["common_category"] == category]
        for category in categories
    }
    if any(not by_category[category] for category in categories):
        raise ValueError("all_three_facility_categories_required")

    results = []
    for stop in sample_stops:
        nearest = []
        for category in categories:
            facility = min(
                by_category[category],
                key=lambda record: haversine_meters(
                    float(stop["latitude"]),
                    float(stop["longitude"]),
                    float(record["latitude"]),
                    float(record["longitude"]),
                ),
            )
            distance = haversine_meters(
                float(stop["latitude"]),
                float(stop["longitude"]),
                float(facility["latitude"]),
                float(facility["longitude"]),
            )
            nearest.append(
                {
                    "common_category": category,
                    "facility_id": facility["facility_id"],
                    "facility_name": facility["facility_name"],
                    "straight_line_distance_m": round(distance, 1),
                }
            )
        results.append(
            {
                "stop_id": stop["stop_id"],
                "stop_name": stop["stop_name"],
                "latitude": stop["latitude"],
                "longitude": stop["longitude"],
                "nearest_facility_by_category": nearest,
            }
        )

    return {
        "method": "haversine_straight_line_distance",
        "sample_selection": (
            "GTFSの有効な乗降場所をstop_id、stop_name順に並べ、正規化したstop_nameが重なる方向別停留所を"
            "除いた先頭5名称を使う。代表性や最終対象停留所を意味しない。"
        ),
        "sample_stop_count": len(sample_stops),
        "category_count": len(categories),
        "distance_calculation_count": len(sample_stops) * len(categories),
        "all_distance_calculations_succeeded": all(
            len(result["nearest_facility_by_category"]) == len(categories) for result in results
        ),
        "results": results,
    }


def build_dataset(registry: Mapping[str, object] | None = None) -> dict:
    registry = dict(registry or load_source_registry())
    facilities: List[dict] = []
    quality: List[dict] = []
    for source in registry["facility_sources"]:
        source_records, source_quality = normalize_facility_source(source, read_facility_rows(source))
        facilities.extend(source_records)
        quality.append(source_quality)

    duplicate_candidates = find_duplicate_candidates(facilities)
    apply_duplicate_quality_counts(facilities, quality, duplicate_candidates)

    bus_stops, bus_stop_quality = read_valid_bus_stops(registry["bus_stop_source"])
    sample_stops = select_bus_stop_sample(bus_stops)
    join_trial = build_join_trial(sample_stops, facilities)

    return {
        "schema_version": "WORK1-IWAKUNI-LIFE-FACILITY-JOIN-TRIAL-1-SCHEMA-1",
        "task_id": TASK_ID,
        "generated_at": GENERATED_AT,
        "purpose": (
            "岩国市公式の公共施設・医療機関・子育て施設を同じ座標形式にそろえ、"
            "既存GTFSバス停から距離計算へ渡せるかを小規模に確認する。"
        ),
        "boundaries": [
            "岩国市を最終対象地域に固定しない。",
            "3分類は同等の結合検証対象で、医療を中心にしない。",
            "直線距離だけを計算し、徒歩経路、徒歩圏、所要時間、施設利用可能性を判定しない。",
            "施設やバス停の存在から、生活可能性、交通充足、需要、施策必要性を断定しない。",
        ],
        "quality_definitions": {
            "missing_coordinate_count": "緯度または経度の一方以上が空欄の元CSV行数。",
            "invalid_coordinate_count": "値が数値でない、有限でない、または緯度・経度の世界範囲外となる元CSV行数。",
            "missing_classification_count": "データセット級または行級の元分類を共通形式へ入れられない元CSV行数。",
            "duplicate_candidate": (
                "3データを合わせ、NFKC正規化・空白除去した施設名が同じで、直線距離30m以内の2記録。"
                "同一施設とは断定しない。"
            ),
        },
        "source_registry": registry,
        "quality_by_source": quality,
        "facility_record_count": len(facilities),
        "facility_records": facilities,
        "duplicate_candidates": duplicate_candidates,
        "bus_stop_quality": bus_stop_quality,
        "bus_stop_join_trial": join_trial,
    }


def render_dataset_json(dataset: Mapping[str, object]) -> str:
    return json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    OUTPUT_PATH.write_bytes(render_dataset_json(build_dataset()).encode("utf-8"))


if __name__ == "__main__":
    main()
