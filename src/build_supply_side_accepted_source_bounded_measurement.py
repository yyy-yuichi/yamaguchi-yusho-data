"""Build bounded internal measurements for the 61 ready applications.

Only the accepted-source measurement specification, its twelve frozen inputs,
and the seven already accepted originals are used.  GTFS measurements remain
whole-feed results that municipality applications reference; they are never
allocated or filtered into municipality supply quantities.

Date-specific timetable and frequency values are stored as a deterministic
normal form: active service_ids by date plus stop-call/frequency templates by
service_id.  Joining those two internal tables recreates the date granularity
without duplicating a whole regional feed once for every related municipality.
"""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import calculate_gtfs_supply_metrics as gm
import inspect_gtfs_archives as gi


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "work1_supply_side_accepted_source_bounded_measurement.json"

TASK_ID = "WORK1-SUPPLY-SIDE-ACCEPTED-SOURCE-BOUNDED-MEASUREMENT-1"
SCHEMA_VERSION = "WORK1-SUPPLY-SIDE-ACCEPTED-SOURCE-BOUNDED-MEASUREMENT-1"
MEASUREMENT_AS_OF = "2026-08-20"
MEASUREMENT_SPEC_PATH = "data/work1_supply_side_accepted_source_measurement_spec.json"

READY = "READY_FOR_BOUNDED_MEASUREMENT"
PARTIAL = "PARTIAL_SOURCE_ONLY"
ADDITIONAL = "ADDITIONAL_INPUT_REQUIRED"
MEASURED = "MEASURED_BOUNDED"

REGISTRY_ITEM_IDS = {
    "registered_service_area_detail",
    "welfare_eligibility_scope",
}
GTFS_ITEM_IDS = {
    "route_identity_and_name",
    "stop_name_and_coordinates",
    "route_shape",
    "service_calendar",
    "stop_level_timetable",
    "time_band_frequency",
}

APPLICATION_FIELDS = (
    "municipality_code",
    "municipality",
    "category_id",
    "item_id",
    "measurement_spec_id",
    "accepted_source_ids",
    "measurement_result_ids",
    "measurement_status",
    "measurement_scope",
    "result_scope",
    "allocation_boundary",
    "claim_boundary",
)

RESULT_FIELDS = (
    "measurement_result_id",
    "measurement_spec_id",
    "item_id",
    "source_scope",
    "source_ids",
    "measurement_status",
    "output_tables",
    "summary",
    "verification",
    "claim_boundary",
)

WELFARE_FLAG_COLUMNS = (
    "scope_i_physical",
    "scope_ro_mental",
    "scope_ha_intellectual",
    "scope_ni_care",
    "scope_ho_support",
    "scope_he_checklist",
    "scope_to_other",
)


def _path(relative_path: str) -> Path:
    return REPO_ROOT.joinpath(*relative_path.split("/"))


def _load_json(relative_path: str) -> Any:
    return json.loads(_path(relative_path).read_text(encoding="utf-8"))


def _sha256_and_size(relative_path: str) -> tuple[str, int]:
    payload = _path(relative_path).read_bytes()
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _read_csv(relative_path: str) -> tuple[list[str], list[dict[str, str]]]:
    with _path(relative_path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV header is missing: {relative_path}")
        return list(reader.fieldnames), list(reader)


def _nullable(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def _split_semicolon(value: str) -> list[str]:
    if value == "":
        return []
    return [part for part in value.split(";") if part != ""]


def _table(
    name: str,
    columns: Iterable[str],
    key_fields: Iterable[str],
    rows: list[list[Any]],
) -> dict[str, Any]:
    return {
        "name": name,
        "columns": list(columns),
        "key_fields": list(key_fields),
        "row_count": len(rows),
        "rows": rows,
    }


def _result(
    *,
    result_id: str,
    item_spec: dict[str, Any],
    source_scope: dict[str, Any],
    source_ids: list[str],
    output_tables: list[dict[str, Any]],
    summary: dict[str, Any],
    verification: dict[str, Any],
    claim_boundary: str,
) -> dict[str, Any]:
    value = {
        "measurement_result_id": result_id,
        "measurement_spec_id": item_spec["measurement_spec_id"],
        "item_id": item_spec["item_id"],
        "source_scope": source_scope,
        "source_ids": source_ids,
        "measurement_status": MEASURED,
        "output_tables": output_tables,
        "summary": summary,
        "verification": verification,
        "claim_boundary": claim_boundary,
    }
    if tuple(value) != RESULT_FIELDS:
        raise AssertionError("measurement result field order drifted")
    return value


def _verify_spec_inputs(specification: dict[str, Any]) -> list[dict[str, Any]]:
    spec_sha, spec_size = _sha256_and_size(MEASUREMENT_SPEC_PATH)
    verified = [{"path": MEASUREMENT_SPEC_PATH, "bytes": spec_size, "sha256": spec_sha}]
    for item in specification["input_files"]:
        sha256, size = _sha256_and_size(item["path"])
        if size != item["bytes"] or sha256 != item["sha256"]:
            raise ValueError(f"measurement specification input drifted: {item['path']}")
        verified.append({"path": item["path"], "bytes": size, "sha256": sha256})
    if len(verified) != 13:
        raise ValueError("bounded measurement must have specification plus twelve frozen inputs")
    return verified


def _validate_registry_rows(rows: list[dict[str, str]]) -> None:
    required = {
        "source_pdf", "source_page", "registration_no", "transport_type", "org_name",
        "service_area_raw", "service_area_municipalities", "office_name", "office_location",
        *WELFARE_FLAG_COLUMNS,
    }
    if not rows:
        raise ValueError("operators.csv has no rows")
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"operators.csv columns missing: {sorted(missing)}")
    keys: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["source_pdf"], row["registration_no"])
        if "" in key or key in keys:
            raise ValueError(f"invalid registry composite key: {key}")
        keys.add(key)
        try:
            source_page = int(row["source_page"])
        except ValueError as exc:
            raise ValueError(f"invalid source_page for {key}") from exc
        if source_page <= 0:
            raise ValueError(f"source_page must be positive for {key}")
        office_names = _split_semicolon(row["office_name"])
        office_locations = _split_semicolon(row["office_location"])
        if len(office_names) != len(office_locations):
            raise ValueError(f"office name/location count mismatch for {key}")


def _matched_registry_rows(
    application: dict[str, Any],
    operator_rows: list[dict[str, str]],
    source_id_by_pdf: dict[str, str],
    source_order: dict[str, int],
) -> list[tuple[str, dict[str, str]]]:
    accepted = set(application["accepted_source_ids"])
    municipality = application["municipality"]
    matched: list[tuple[str, dict[str, str]]] = []
    for row in operator_rows:
        source_id = source_id_by_pdf.get(row["source_pdf"])
        municipalities = _split_semicolon(row["service_area_municipalities"])
        if source_id in accepted and municipality in municipalities:
            matched.append((source_id, row))
    matched.sort(
        key=lambda pair: (
            source_order[pair[0]],
            int(pair[1]["source_page"]),
            pair[1]["registration_no"],
        )
    )
    if not matched:
        raise ValueError(
            f"no municipality-matched registry rows for {application['municipality_code']} "
            f"{application['item_id']}"
        )
    if {source_id for source_id, _ in matched} != accepted:
        raise ValueError(
            f"accepted registry sources do not all resolve for {application['municipality_code']} "
            f"{application['item_id']}"
        )
    return matched


def _build_registry_area_result(
    application: dict[str, Any],
    item_spec: dict[str, Any],
    operator_rows: list[dict[str, str]],
    source_id_by_pdf: dict[str, str],
    source_order: dict[str, int],
) -> dict[str, Any]:
    matched = _matched_registry_rows(
        application, operator_rows, source_id_by_pdf, source_order
    )
    records: list[list[Any]] = []
    office_count = 0
    for source_id, row in matched:
        office_names = _split_semicolon(row["office_name"])
        office_locations = _split_semicolon(row["office_location"])
        offices = [[name, location] for name, location in zip(office_names, office_locations)]
        office_count += len(offices)
        records.append([
            source_id,
            row["source_pdf"],
            int(row["source_page"]),
            row["registration_no"],
            row["transport_type"],
            row["org_name"],
            _nullable(row["service_area_raw"]),
            _split_semicolon(row["service_area_municipalities"]),
            offices,
        ])
    result_id = f"BMR-{application['municipality_code']}-{item_spec['measurement_spec_id']}"
    return _result(
        result_id=result_id,
        item_spec=item_spec,
        source_scope={
            "scope_type": "municipality_matched_registry_records",
            "municipality_code": application["municipality_code"],
            "municipality": application["municipality"],
            "allocation": "direct_existing_match_not_apportionment",
        },
        source_ids=application["accepted_source_ids"],
        output_tables=[_table(
            "registered_service_area_records",
            (
                "source_id", "source_pdf", "source_page", "registration_no",
                "transport_type", "org_name", "service_area_raw",
                "service_area_municipalities", "office_name_location_pairs",
            ),
            ("source_pdf", "registration_no"),
            records,
        )],
        summary={
            "matched_registration_count": len(records),
            "accepted_source_count": len(application["accepted_source_ids"]),
            "office_record_count": office_count,
            "distinct_service_area_raw_count": len({row[6] for row in records}),
        },
        verification={
            "composite_keys_unique": True,
            "source_pages_positive": True,
            "municipality_token_match": True,
            "office_pair_counts_match": True,
        },
        claim_boundary=application["claim_boundary"],
    )


def _parse_welfare_flag(value: str, key: tuple[str, str], column: str) -> int | None:
    if value == "":
        return None
    if value not in ("0", "1"):
        raise ValueError(f"invalid welfare flag {column}={value!r} for {key}")
    return int(value)


def _build_welfare_result(
    application: dict[str, Any],
    item_spec: dict[str, Any],
    operator_rows: list[dict[str, str]],
    source_id_by_pdf: dict[str, str],
    source_order: dict[str, int],
) -> dict[str, Any]:
    matched = _matched_registry_rows(
        application, operator_rows, source_id_by_pdf, source_order
    )
    records: list[list[Any]] = []
    true_counts = {column: 0 for column in WELFARE_FLAG_COLUMNS}
    null_counts = {column: 0 for column in WELFARE_FLAG_COLUMNS}
    for source_id, row in matched:
        key = (row["source_pdf"], row["registration_no"])
        if row["transport_type"] != "福祉有償運送":
            raise ValueError(f"welfare measurement resolved non-welfare record: {key}")
        flags = []
        for column in WELFARE_FLAG_COLUMNS:
            flag = _parse_welfare_flag(row[column], key, column)
            flags.append(flag)
            if flag == 1:
                true_counts[column] += 1
            if flag is None:
                null_counts[column] += 1
        records.append([
            source_id,
            row["source_pdf"],
            int(row["source_page"]),
            row["registration_no"],
            row["org_name"],
            row["transport_type"],
            _split_semicolon(row["service_area_municipalities"]),
            *flags,
        ])
    result_id = f"BMR-{application['municipality_code']}-{item_spec['measurement_spec_id']}"
    return _result(
        result_id=result_id,
        item_spec=item_spec,
        source_scope={
            "scope_type": "municipality_matched_registry_records",
            "municipality_code": application["municipality_code"],
            "municipality": application["municipality"],
            "allocation": "direct_existing_match_not_apportionment",
        },
        source_ids=application["accepted_source_ids"],
        output_tables=[_table(
            "welfare_eligibility_flag_records",
            (
                "source_id", "source_pdf", "source_page", "registration_no",
                "org_name", "transport_type", "service_area_municipalities",
                *WELFARE_FLAG_COLUMNS,
            ),
            ("source_pdf", "registration_no"),
            records,
        )],
        summary={
            "matched_welfare_registration_count": len(records),
            "flag_true_record_counts": true_counts,
            "flag_unrecorded_counts": null_counts,
        },
        verification={
            "composite_keys_unique": True,
            "source_pages_positive": True,
            "municipality_token_match": True,
            "flags_are_zero_one_or_null": True,
        },
        claim_boundary=application["claim_boundary"],
    )


def _require_table(table: gm.FileTable, name: str, columns: Iterable[str]) -> None:
    if not table.present:
        raise ValueError(f"required GTFS table is absent: {name}")
    if table.decode_error:
        raise ValueError(f"GTFS decode failed for {name}: {table.decode_error}")
    if table.header is None or table.rows is None:
        raise ValueError(f"GTFS table is unreadable: {name}")
    missing = [column for column in columns if column not in table.header]
    if missing:
        raise ValueError(f"GTFS columns missing from {name}: {missing}")


def _dict_rows(table: gm.FileTable) -> list[dict[str, str]]:
    if table.header is None or table.rows is None:
        raise ValueError("GTFS table must be validated before row conversion")
    return [
        {
            column: row[index] if index < len(row) else ""
            for index, column in enumerate(table.header)
        }
        for row in table.rows
    ]


def _unique_index(rows: list[dict[str, str]], field: str, table_name: str) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        value = row.get(field, "")
        if value == "" or value in index:
            raise ValueError(f"{table_name}.{field} is blank or duplicated: {value!r}")
        index[value] = row
    return index


def _parse_int(value: str, label: str, *, positive: bool = False) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"invalid integer {label}: {value!r}") from exc
    if positive and parsed <= 0:
        raise ValueError(f"integer must be positive {label}: {value!r}")
    if not positive and parsed < 0:
        raise ValueError(f"integer must be non-negative {label}: {value!r}")
    return parsed


def _parse_coordinate(value: str, label: str, lower: float, upper: float) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"invalid coordinate {label}: {value!r}") from exc
    if not lower <= parsed <= upper:
        raise ValueError(f"coordinate outside range {label}: {value!r}")
    return parsed


def _load_gtfs_source(profile: dict[str, Any]) -> dict[str, gm.FileTable]:
    path = _path(profile["original_path"])
    sha256, size = _sha256_and_size(profile["original_path"])
    if sha256 != profile["original_sha256"] or size != profile["original_bytes"]:
        raise ValueError(f"accepted GTFS source drifted: {profile['source_id']}")
    names = (
        "routes.txt", "trips.txt", "stops.txt", "shapes.txt", "stop_times.txt",
        "calendar.txt", "calendar_dates.txt", "feed_info.txt", "frequencies.txt",
    )
    with zipfile.ZipFile(path) as archive:
        safety = gi.inspect_safety(archive)
        if not safety.ok:
            raise ValueError(f"GTFS safety inspection failed: {profile['source_id']}")
        tables = {name: gm.read_table(archive, name) for name in names}
    frequencies = tables["frequencies.txt"]
    if frequencies.present and frequencies.rows:
        raise ValueError(
            f"bounded normal form does not materialize frequency-based trips: {profile['source_id']}"
        )
    return tables


def _validate_gtfs_core(tables: dict[str, gm.FileTable]) -> dict[str, Any]:
    _require_table(tables["routes.txt"], "routes.txt", ("route_id",))
    _require_table(tables["trips.txt"], "trips.txt", ("route_id", "service_id", "trip_id", "shape_id"))
    routes = _dict_rows(tables["routes.txt"])
    trips = _dict_rows(tables["trips.txt"])
    route_by_id = _unique_index(routes, "route_id", "routes.txt")
    trip_by_id = _unique_index(trips, "trip_id", "trips.txt")
    for trip in trips:
        if trip["route_id"] not in route_by_id:
            raise ValueError(f"trip route reference unresolved: {trip['trip_id']}")
        if trip["service_id"] == "":
            raise ValueError(f"trip service_id blank: {trip['trip_id']}")
    return {
        "routes": routes,
        "trips": trips,
        "route_by_id": route_by_id,
        "trip_by_id": trip_by_id,
    }


def _build_route_result(
    profile: dict[str, Any], item_spec: dict[str, Any], tables: dict[str, gm.FileTable]
) -> dict[str, Any]:
    core = _validate_gtfs_core(tables)
    route_columns = tuple(item_spec["source_requirements"][0]["required_columns"])
    trip_columns = tuple(item_spec["source_requirements"][1]["required_columns"])
    _require_table(tables["routes.txt"], "routes.txt", route_columns)
    _require_table(tables["trips.txt"], "trips.txt", trip_columns)
    route_rows = [
        [row.get(column, "") for column in route_columns]
        for row in sorted(core["routes"], key=lambda row: row["route_id"])
    ]
    trip_rows = [
        [row.get(column, "") for column in trip_columns]
        for row in sorted(core["trips"], key=lambda row: row["trip_id"])
    ]
    result_id = f"BMR-{profile['source_id']}-{item_spec['measurement_spec_id']}"
    return _result(
        result_id=result_id,
        item_spec=item_spec,
        source_scope={
            "scope_type": "accepted_feed_whole_feed",
            "source_id": profile["source_id"],
            "municipality_filtering": False,
            "municipality_allocation": False,
        },
        source_ids=[profile["source_id"]],
        output_tables=[
            _table("route_records", route_columns, ("route_id",), route_rows),
            _table("trip_pattern_references", trip_columns, ("trip_id",), trip_rows),
        ],
        summary={
            "route_id_count": len(route_rows),
            "trip_id_count": len(trip_rows),
            "route_short_name_recorded_count": sum(bool(row.get("route_short_name", "")) for row in core["routes"]),
            "route_long_name_recorded_count": sum(bool(row.get("route_long_name", "")) for row in core["routes"]),
        },
        verification={
            "route_ids_unique_nonblank": True,
            "trip_ids_unique_nonblank": True,
            "trip_route_references_resolved": True,
        },
        claim_boundary=item_spec["claim_boundary"] + _jrbus_boundary(profile),
    )


def _build_stop_result(
    profile: dict[str, Any], item_spec: dict[str, Any], tables: dict[str, gm.FileTable]
) -> dict[str, Any]:
    required = tuple(item_spec["source_requirements"][0]["required_columns"])
    optional = tuple(item_spec["source_requirements"][0]["optional_columns"])
    _require_table(tables["stops.txt"], "stops.txt", required)
    stops = _dict_rows(tables["stops.txt"])
    _unique_index(stops, "stop_id", "stops.txt")
    latitudes: list[float] = []
    longitudes: list[float] = []
    rows: list[list[Any]] = []
    for stop in sorted(stops, key=lambda row: row["stop_id"]):
        latitudes.append(_parse_coordinate(stop["stop_lat"], f"{stop['stop_id']}.lat", -90, 90))
        longitudes.append(_parse_coordinate(stop["stop_lon"], f"{stop['stop_id']}.lon", -180, 180))
        rows.append([
            stop.get(column, "") if column in stop else None
            for column in (*required, *optional)
        ])
    columns = (*required, *optional)
    result_id = f"BMR-{profile['source_id']}-{item_spec['measurement_spec_id']}"
    return _result(
        result_id=result_id,
        item_spec=item_spec,
        source_scope={
            "scope_type": "accepted_feed_whole_feed",
            "source_id": profile["source_id"],
            "municipality_filtering": False,
            "municipality_allocation": False,
        },
        source_ids=[profile["source_id"]],
        output_tables=[_table("stop_records", columns, ("stop_id",), rows)],
        summary={
            "stop_id_count": len(rows),
            "boarding_location_id_count": sum(row.get("location_type", "") in ("", "0") for row in stops),
            "latitude_min": min(latitudes),
            "latitude_max": max(latitudes),
            "longitude_min": min(longitudes),
            "longitude_max": max(longitudes),
            "present_optional_columns": [column for column in optional if column in stops[0]],
        },
        verification={
            "stop_ids_unique_nonblank": True,
            "coordinates_numeric_in_range": True,
            "missing_optional_columns_kept_as_null": True,
        },
        claim_boundary=item_spec["claim_boundary"] + _jrbus_boundary(profile),
    )


def _build_shape_result(
    profile: dict[str, Any], item_spec: dict[str, Any], tables: dict[str, gm.FileTable]
) -> dict[str, Any]:
    _require_table(
        tables["shapes.txt"], "shapes.txt",
        ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"),
    )
    core = _validate_gtfs_core(tables)
    shapes = _dict_rows(tables["shapes.txt"])
    has_distance = "shape_dist_traveled" in (tables["shapes.txt"].header or ())
    grouped: dict[str, list[tuple[int, str, str, str | None]]] = defaultdict(list)
    seen_keys: set[tuple[str, int]] = set()
    latitudes: list[float] = []
    longitudes: list[float] = []
    for row in shapes:
        shape_id = row.get("shape_id", "")
        if shape_id == "":
            raise ValueError("shapes.txt shape_id is blank")
        sequence = _parse_int(row.get("shape_pt_sequence", ""), f"{shape_id}.shape_pt_sequence")
        key = (shape_id, sequence)
        if key in seen_keys:
            raise ValueError(f"duplicated shape point key: {key}")
        seen_keys.add(key)
        latitudes.append(_parse_coordinate(row["shape_pt_lat"], f"{shape_id}.lat", -90, 90))
        longitudes.append(_parse_coordinate(row["shape_pt_lon"], f"{shape_id}.lon", -180, 180))
        grouped[shape_id].append((
            sequence,
            row["shape_pt_lat"],
            row["shape_pt_lon"],
            _nullable(row.get("shape_dist_traveled", "")) if has_distance else None,
        ))
    shape_rows: list[list[Any]] = []
    for shape_id in sorted(grouped):
        points = sorted(grouped[shape_id], key=lambda point: point[0])
        shape_rows.append([shape_id, len(points), [list(point) for point in points]])
    shape_ids = set(grouped)
    trip_shape_rows: list[list[Any]] = []
    referenced: set[str] = set()
    missing_trip_shape_count = 0
    for trip in sorted(core["trips"], key=lambda row: row["trip_id"]):
        shape_id = trip.get("shape_id", "")
        if shape_id == "":
            status = "shape_id_blank"
            missing_trip_shape_count += 1
        elif shape_id not in shape_ids:
            raise ValueError(f"trip shape reference unresolved: {trip['trip_id']} -> {shape_id}")
        else:
            status = "resolved"
            referenced.add(shape_id)
        trip_shape_rows.append([trip["trip_id"], trip["route_id"], _nullable(shape_id), status])
    result_id = f"BMR-{profile['source_id']}-{item_spec['measurement_spec_id']}"
    return _result(
        result_id=result_id,
        item_spec=item_spec,
        source_scope={
            "scope_type": "accepted_feed_whole_feed",
            "source_id": profile["source_id"],
            "municipality_filtering": False,
            "municipality_allocation": False,
        },
        source_ids=[profile["source_id"]],
        output_tables=[
            _table(
                "ordered_shape_points",
                ("shape_id", "point_count", "points_sequence_lat_lon_distance"),
                ("shape_id",),
                shape_rows,
            ),
            _table(
                "trip_shape_references",
                ("trip_id", "route_id", "shape_id", "reference_status"),
                ("trip_id",),
                trip_shape_rows,
            ),
        ],
        summary={
            "shape_id_count": len(shape_rows),
            "shape_point_count": len(shapes),
            "trip_shape_reference_count": len(trip_shape_rows),
            "trip_shape_id_blank_count": missing_trip_shape_count,
            "unreferenced_shape_id_count": len(shape_ids - referenced),
            "latitude_min": min(latitudes),
            "latitude_max": max(latitudes),
            "longitude_min": min(longitudes),
            "longitude_max": max(longitudes),
        },
        verification={
            "shape_point_keys_unique": True,
            "shape_sequences_sorted": True,
            "coordinates_numeric_in_range": True,
            "nonblank_trip_shape_references_resolved": True,
        },
        claim_boundary=item_spec["claim_boundary"] + _jrbus_boundary(profile),
    )


def _gtfs_date(value: str, label: str) -> date:
    if not gi.is_valid_gtfs_date(value):
        raise ValueError(f"invalid GTFS date {label}: {value!r}")
    return datetime.strptime(value, "%Y%m%d").date()


def _active_services_for_date(context: gm.TripCountContext, target: date) -> list[str]:
    dstr = target.strftime("%Y%m%d")
    weekday = gm.WEEKDAY_COLUMNS[target.weekday()]
    active: set[str] = set()
    for service_id, flags, start, end in context.calendar_rows:
        if start <= dstr <= end and flags[weekday] == "1":
            active.add(service_id)
    for service_id, exception_type in context.calendar_dates_by_date.get(dstr, ()):
        if exception_type == "1":
            active.add(service_id)
        else:
            active.discard(service_id)
    return sorted(active)


def _calendar_context(tables: dict[str, gm.FileTable]) -> gm.TripCountContext:
    _require_table(tables["feed_info.txt"], "feed_info.txt", ("feed_start_date", "feed_end_date"))
    context, reason = gm._prepare_trip_count_context(
        tables["routes.txt"],
        tables["calendar.txt"],
        tables["calendar_dates.txt"],
        tables["trips.txt"],
        tables["frequencies.txt"],
    )
    if context is None:
        raise ValueError(f"GTFS calendar/trip validation failed: {reason}")
    return context


def _build_calendar_result(
    profile: dict[str, Any], item_spec: dict[str, Any], tables: dict[str, gm.FileTable]
) -> dict[str, Any]:
    context = _calendar_context(tables)
    feed_info = _dict_rows(tables["feed_info.txt"])
    if not feed_info:
        raise ValueError("feed_info.txt has no rows")
    feed_rows: list[list[Any]] = []
    for row in feed_info:
        start = row.get("feed_start_date", "")
        end = row.get("feed_end_date", "")
        _gtfs_date(start, "feed_start_date")
        _gtfs_date(end, "feed_end_date")
        if start > end:
            raise ValueError("feed_info date range is reversed")
        feed_rows.append([start, end])
    bound_values: list[str] = []
    for _, _, start, end in context.calendar_rows:
        bound_values.extend((start, end))
    bound_values.extend(context.calendar_dates_by_date)
    if not bound_values:
        raise ValueError("active service date bounds cannot be established")
    start_date = _gtfs_date(min(bound_values), "active_service_start")
    end_date = _gtfs_date(max(bound_values), "active_service_end")
    active_rows: list[list[Any]] = []
    cursor = start_date
    while cursor <= end_date:
        active_services = _active_services_for_date(context, cursor)
        scheduled_trip_templates = sum(
            len(context.service_to_trip_ids.get(service_id, ()))
            for service_id in active_services
        )
        active_rows.append([cursor.isoformat(), active_services, scheduled_trip_templates])
        cursor += timedelta(days=1)
    calendar_rows = [
        [service_id, flags, start, end]
        for service_id, flags, start, end in sorted(context.calendar_rows, key=lambda item: item[0])
    ]
    exception_rows = [
        [day, service_id, exception]
        for day in sorted(context.calendar_dates_by_date)
        for service_id, exception in sorted(context.calendar_dates_by_date[day])
    ]
    result_id = f"BMR-{profile['source_id']}-{item_spec['measurement_spec_id']}"
    return _result(
        result_id=result_id,
        item_spec=item_spec,
        source_scope={
            "scope_type": "accepted_feed_whole_feed",
            "source_id": profile["source_id"],
            "municipality_filtering": False,
            "municipality_allocation": False,
        },
        source_ids=[profile["source_id"]],
        output_tables=[
            _table(
                "feed_validity_period",
                ("feed_start_date", "feed_end_date"),
                (),
                feed_rows,
            ),
            _table(
                "calendar_service_rules",
                ("service_id", "weekday_flags", "start_date", "end_date"),
                ("service_id",),
                calendar_rows,
            ),
            _table(
                "calendar_date_exceptions",
                ("date", "service_id", "exception_type"),
                ("date", "service_id"),
                exception_rows,
            ),
            _table(
                "active_service_by_date",
                ("date", "active_service_ids", "scheduled_trip_template_count"),
                ("date",),
                active_rows,
            ),
        ],
        summary={
            "active_service_date_range_start": start_date.isoformat(),
            "active_service_date_range_end": end_date.isoformat(),
            "date_row_count": len(active_rows),
            "date_with_active_service_count": sum(bool(row[1]) for row in active_rows),
            "calendar_service_id_count": len(context.calendar_rows),
            "calendar_exception_count": len(exception_rows),
        },
        verification={
            "service_id_references_resolved": True,
            "gtfs_dates_valid": True,
            "weekday_flags_zero_or_one": True,
            "exception_types_one_or_two": True,
            "zero_active_service_dates_not_read_as_service_absence": True,
        },
        claim_boundary=item_spec["claim_boundary"] + _jrbus_boundary(profile),
    )


def _stop_call_rows(tables: dict[str, gm.FileTable]) -> tuple[list[list[Any]], dict[str, Any]]:
    core = _validate_gtfs_core(tables)
    _calendar_context(tables)
    _require_table(
        tables["stops.txt"], "stops.txt", ("stop_id", "stop_name")
    )
    _require_table(
        tables["stop_times.txt"], "stop_times.txt",
        (
            "trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence",
            "pickup_type", "drop_off_type", "timepoint",
        ),
    )
    stops = _dict_rows(tables["stops.txt"])
    stop_by_id = _unique_index(stops, "stop_id", "stops.txt")
    stop_times = _dict_rows(tables["stop_times.txt"])
    seen: set[tuple[str, int]] = set()
    calls: list[list[Any]] = []
    after_midnight_count = 0
    for row in stop_times:
        trip_id = row.get("trip_id", "")
        stop_id = row.get("stop_id", "")
        if trip_id not in core["trip_by_id"]:
            raise ValueError(f"stop_times trip reference unresolved: {trip_id}")
        if stop_id not in stop_by_id:
            raise ValueError(f"stop_times stop reference unresolved: {stop_id}")
        sequence = _parse_int(row.get("stop_sequence", ""), f"{trip_id}.stop_sequence", positive=True)
        key = (trip_id, sequence)
        if key in seen:
            raise ValueError(f"stop_times key duplicated: {key}")
        seen.add(key)
        arrival_seconds = gm.parse_gtfs_time_to_seconds(row.get("arrival_time", ""))
        departure_seconds = gm.parse_gtfs_time_to_seconds(row.get("departure_time", ""))
        if arrival_seconds is None or departure_seconds is None:
            raise ValueError(f"invalid stop_times time for {key}")
        if arrival_seconds >= 86400 or departure_seconds >= 86400:
            after_midnight_count += 1
        trip = core["trip_by_id"][trip_id]
        calls.append([
            trip["service_id"],
            trip["route_id"],
            trip_id,
            trip.get("trip_headsign", ""),
            trip.get("direction_id", ""),
            sequence,
            stop_id,
            stop_by_id[stop_id].get("stop_name", ""),
            row["arrival_time"],
            row["departure_time"],
            arrival_seconds,
            departure_seconds,
            row.get("pickup_type", ""),
            row.get("drop_off_type", ""),
            row.get("timepoint", ""),
        ])
    calls.sort(key=lambda row: (row[2], row[5]))
    return calls, {
        "stop_call_template_count": len(calls),
        "trip_id_count": len({row[2] for row in calls}),
        "route_id_count": len({row[1] for row in calls}),
        "stop_id_count": len({row[6] for row in calls}),
        "after_midnight_time_record_count": after_midnight_count,
    }


STOP_CALL_COLUMNS = (
    "service_id", "route_id", "trip_id", "trip_headsign", "direction_id",
    "stop_sequence", "stop_id", "stop_name", "arrival_time", "departure_time",
    "arrival_seconds", "departure_seconds", "pickup_type", "drop_off_type", "timepoint",
)


def _build_timetable_result(
    profile: dict[str, Any], item_spec: dict[str, Any], tables: dict[str, gm.FileTable]
) -> dict[str, Any]:
    calls, summary = _stop_call_rows(tables)
    calendar_result_id = f"BMR-{profile['source_id']}-MS-06-GTFS-SERVICE-CALENDAR"
    result_id = f"BMR-{profile['source_id']}-{item_spec['measurement_spec_id']}"
    summary = dict(summary)
    summary["date_resolution"] = {
        "mode": "normalized_service_id_join",
        "active_service_result_id": calendar_result_id,
        "join_field": "service_id",
    }
    return _result(
        result_id=result_id,
        item_spec=item_spec,
        source_scope={
            "scope_type": "accepted_feed_whole_feed",
            "source_id": profile["source_id"],
            "municipality_filtering": False,
            "municipality_allocation": False,
        },
        source_ids=[profile["source_id"]],
        output_tables=[_table(
            "scheduled_stop_call_templates",
            STOP_CALL_COLUMNS,
            ("trip_id", "stop_sequence"),
            calls,
        )],
        summary=summary,
        verification={
            "trip_route_service_stop_references_resolved": True,
            "trip_stop_sequence_keys_unique": True,
            "gtfs_times_valid_including_after_midnight": True,
            "date_granularity_recreated_by_service_id_join": True,
        },
        claim_boundary=(
            item_spec["claim_boundary"]
            + " 日付別値はactive_service_by_dateとservice_idで結合する正規形であり、実績ではない。"
            + _jrbus_boundary(profile)
        ),
    )


def _format_hour_start(hour_index: int) -> str:
    return f"{hour_index:02d}:00:00"


def _build_frequency_result(
    profile: dict[str, Any], item_spec: dict[str, Any], tables: dict[str, gm.FileTable]
) -> dict[str, Any]:
    calls, _ = _stop_call_rows(tables)
    groups: dict[tuple[str, str, str, int], list[tuple[int, str]]] = defaultdict(list)
    first_last: dict[tuple[str, str, str], list[tuple[int, str]]] = defaultdict(list)
    for call in calls:
        service_id, route_id, stop_id = call[0], call[1], call[6]
        departure_time, departure_seconds = call[9], call[11]
        hour_index = departure_seconds // 3600
        groups[(service_id, route_id, stop_id, hour_index)].append(
            (departure_seconds, departure_time)
        )
        first_last[(service_id, route_id, stop_id)].append(
            (departure_seconds, departure_time)
        )
    group_rows: list[list[Any]] = []
    for key in sorted(groups):
        values = sorted(groups[key])
        group_rows.append([
            key[0], key[1], key[2], _format_hour_start(key[3]),
            len(values), values[0][1], values[-1][1],
        ])
    first_last_rows: list[list[Any]] = []
    for key in sorted(first_last):
        values = sorted(first_last[key])
        first_last_rows.append([
            key[0], key[1], key[2], len(values), values[0][1], values[-1][1],
        ])
    result_id = f"BMR-{profile['source_id']}-{item_spec['measurement_spec_id']}"
    calendar_result_id = f"BMR-{profile['source_id']}-MS-06-GTFS-SERVICE-CALENDAR"
    return _result(
        result_id=result_id,
        item_spec=item_spec,
        source_scope={
            "scope_type": "accepted_feed_whole_feed",
            "source_id": profile["source_id"],
            "municipality_filtering": False,
            "municipality_allocation": False,
        },
        source_ids=[profile["source_id"]],
        output_tables=[
            _table(
                "scheduled_departure_count_by_service_route_stop_hour",
                (
                    "service_id", "route_id", "stop_id", "hour_start",
                    "scheduled_departure_count", "first_departure_time", "last_departure_time",
                ),
                ("service_id", "route_id", "stop_id", "hour_start"),
                group_rows,
            ),
            _table(
                "scheduled_first_last_departure_by_service_route_stop",
                (
                    "service_id", "route_id", "stop_id", "scheduled_departure_count",
                    "first_departure_time", "last_departure_time",
                ),
                ("service_id", "route_id", "stop_id"),
                first_last_rows,
            ),
        ],
        summary={
            "scheduled_departure_template_count": len(calls),
            "hour_group_count": len(group_rows),
            "service_route_stop_group_count": len(first_last_rows),
            "date_resolution": {
                "mode": "normalized_service_id_join",
                "active_service_result_id": calendar_result_id,
                "join_field": "service_id",
            },
        },
        verification={
            "hour_bins_left_closed_right_open": True,
            "hour_group_counts_reconcile_to_stop_call_templates": (
                sum(row[4] for row in group_rows) == len(calls)
            ),
            "first_last_counts_reconcile_to_stop_call_templates": (
                sum(row[3] for row in first_last_rows) == len(calls)
            ),
            "date_granularity_recreated_by_service_id_join": True,
        },
        claim_boundary=(
            item_spec["claim_boundary"]
            + " 時間帯頻度はservice_id別予定テンプレートで、日付別にはactive_service_by_dateと結合する。"
            + _jrbus_boundary(profile)
        ),
    )


def _jrbus_boundary(profile: dict[str, Any]) -> str:
    if profile["source_id"] == "jrbus-chugoku-gtfs":
        return " JRバス中国の県外を含むフィード全体値であり、関係4市へ配賦しない。"
    return ""


GTFS_BUILDERS = {
    "route_identity_and_name": _build_route_result,
    "stop_name_and_coordinates": _build_stop_result,
    "route_shape": _build_shape_result,
    "service_calendar": _build_calendar_result,
    "stop_level_timetable": _build_timetable_result,
    "time_band_frequency": _build_frequency_result,
}


def build_dataset() -> dict[str, Any]:
    specification = _load_json(MEASUREMENT_SPEC_PATH)
    if specification["task_id"] != "WORK1-SUPPLY-SIDE-ACCEPTED-SOURCE-MEASUREMENT-SPEC-1":
        raise ValueError("unexpected upstream measurement specification")
    if specification["readiness_counts"] != {
        READY: 61,
        PARTIAL: 30,
        ADDITIONAL: 7,
    }:
        raise ValueError("upstream readiness partition drifted")
    input_files = _verify_spec_inputs(specification)

    applications = specification["municipality_item_applications"]
    ready_applications = [item for item in applications if item["execution_readiness"] == READY]
    excluded_partial = [item for item in applications if item["execution_readiness"] == PARTIAL]
    excluded_additional = [item for item in applications if item["execution_readiness"] == ADDITIONAL]
    if len(ready_applications) != 61 or len(excluded_partial) != 30 or len(excluded_additional) != 7:
        raise ValueError("application readiness partition is not 61/30/7")
    if {item["item_id"] for item in ready_applications} != REGISTRY_ITEM_IDS | GTFS_ITEM_IDS:
        raise ValueError("ready item set drifted")

    item_spec_by_id = {
        item["item_id"]: item for item in specification["item_specifications"]
    }
    profiles = specification["accepted_source_profiles"]
    profile_by_id = {item["source_id"]: item for item in profiles}
    source_order = {item["source_id"]: index for index, item in enumerate(profiles)}
    source_id_by_pdf = {
        Path(item["original_path"]).name: item["source_id"]
        for item in profiles
        if item["source_type"] == "registry_pdf"
    }
    _, operator_rows = _read_csv("data/operators.csv")
    _validate_registry_rows(operator_rows)

    results: list[dict[str, Any]] = []
    result_by_key: dict[tuple[str, str], str] = {}

    for application in ready_applications:
        item_id = application["item_id"]
        if item_id not in REGISTRY_ITEM_IDS:
            continue
        item_spec = item_spec_by_id[item_id]
        if item_id == "registered_service_area_detail":
            result = _build_registry_area_result(
                application, item_spec, operator_rows, source_id_by_pdf, source_order
            )
        else:
            result = _build_welfare_result(
                application, item_spec, operator_rows, source_id_by_pdf, source_order
            )
        results.append(result)
        result_by_key[(application["municipality_code"], item_id)] = result["measurement_result_id"]

    gtfs_profiles = [item for item in profiles if item["source_type"] == "gtfs_zip"]
    gtfs_item_order = [
        item["item_id"]
        for item in specification["item_specifications"]
        if item["item_id"] in GTFS_ITEM_IDS
    ]
    gtfs_tables = {
        profile["source_id"]: _load_gtfs_source(profile)
        for profile in gtfs_profiles
    }
    for profile in gtfs_profiles:
        source_id = profile["source_id"]
        for item_id in gtfs_item_order:
            item_spec = item_spec_by_id[item_id]
            result = GTFS_BUILDERS[item_id](profile, item_spec, gtfs_tables[source_id])
            results.append(result)
            result_by_key[(source_id, item_id)] = result["measurement_result_id"]

    result_ids = [item["measurement_result_id"] for item in results]
    if len(result_ids) != len(set(result_ids)):
        raise ValueError("measurement result ids are duplicated")

    measured_applications: list[dict[str, Any]] = []
    for application in ready_applications:
        item_id = application["item_id"]
        if item_id in REGISTRY_ITEM_IDS:
            result_ids_for_application = [
                result_by_key[(application["municipality_code"], item_id)]
            ]
            result_scope = "municipality_matched_registry_records"
            allocation_boundary = "登録簿の既存市町対応に直接一致した記録だけ。比例配賦・推測なし。"
        else:
            if len(application["accepted_source_ids"]) != 1:
                raise ValueError(
                    f"GTFS ready application must reference one whole feed: "
                    f"{application['municipality_code']} {item_id}"
                )
            source_id = application["accepted_source_ids"][0]
            if profile_by_id[source_id]["source_type"] != "gtfs_zip":
                raise ValueError("GTFS application resolved a non-GTFS source")
            result_ids_for_application = [result_by_key[(source_id, item_id)]]
            result_scope = "accepted_feed_whole_feed_reference"
            allocation_boundary = "市町境界フィルターなし。フィード全体値を市町内供給量へ配賦しない。"
        measured = {
            "municipality_code": application["municipality_code"],
            "municipality": application["municipality"],
            "category_id": application["category_id"],
            "item_id": item_id,
            "measurement_spec_id": application["measurement_spec_id"],
            "accepted_source_ids": application["accepted_source_ids"],
            "measurement_result_ids": result_ids_for_application,
            "measurement_status": MEASURED,
            "measurement_scope": application["measurement_scope"],
            "result_scope": result_scope,
            "allocation_boundary": allocation_boundary,
            "claim_boundary": application["claim_boundary"],
        }
        if tuple(measured) != APPLICATION_FIELDS:
            raise AssertionError("measured application field order drifted")
        measured_applications.append(measured)

    if len(results) != 37:
        raise ValueError(f"expected 37 normalized measurement results, got {len(results)}")
    if len(measured_applications) != 61:
        raise ValueError("expected exactly 61 measured applications")

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "measurement_as_of": MEASUREMENT_AS_OF,
        "measurement_status": MEASURED,
        "dimensions": {
            "accepted_source_count": 7,
            "measured_item_count": 8,
            "measured_application_count": 61,
            "normalized_measurement_result_count": len(results),
            "excluded_partial_application_count": 30,
            "excluded_additional_input_application_count": 7,
            "input_file_count": len(input_files),
        },
        "required_application_fields": list(APPLICATION_FIELDS),
        "required_result_fields": list(RESULT_FIELDS),
        "input_files": input_files,
        "normalization_contract": {
            "registry": "市町対応済み登録記録を複合キー・原本ページ付きで直接保持する。",
            "gtfs": "受入フィードごとに一度だけ全体測定し、関係市町はresult_idを参照する。",
            "date_resolution": "active_service_by_dateとservice_id別予定テンプレートを結合し、日付×予定値を再現する。",
            "municipality_allocation": False,
            "municipality_geometry_filtering": False,
        },
        "measurement_results": results,
        "municipality_item_measurements": measured_applications,
        "excluded_applications": {
            "PARTIAL_SOURCE_ONLY": [
                {
                    "municipality_code": item["municipality_code"],
                    "item_id": item["item_id"],
                    "reason": "部分情報を項目全体の測定値へ変換しない。",
                }
                for item in excluded_partial
            ],
            "ADDITIONAL_INPUT_REQUIRED": [
                {
                    "municipality_code": item["municipality_code"],
                    "item_id": item["item_id"],
                    "reason": "受入済み市町境界geometryなしで0件・0%を生成しない。",
                }
                for item in excluded_additional
            ],
        },
        "external_feedback_separation": {
            "recorded_separately": "evidence/20260820_work1_udc_yamaguchi_coordinator_qualitative_feedback.json",
            "included_in_input_files": False,
            "used_to_create_measurement_values": False,
            "treated_as_user_test": False,
        },
        "global_boundaries": [
            "限定測定値は受入済み7原本と受入済み派生列の記録内容だけを表す。",
            "GTFS結果はフィード全体値で、市町内供給量・市町内カバー率ではない。",
            "JRバス中国の県外を含む広域値を関係4市へ配賦しない。",
            "予定時刻・運行予定日・予定頻度は実運行、遅延、現在利用可能性を示さない。",
            "登録区域・福祉対象フラグは現在の実運行区域、会員条件、配車可能性を示さない。",
            "0件・空欄・0予定・未収録・部分情報からサービス不存在やservice_gapを判定しない。",
            "外部定性意見は測定入力・利用者テスト・共同設計の証拠へ変換しない。",
            "本内部JSONはdocs/dataへ複製せず公開しない。",
        ],
        "next_stage": {
            "task_id": "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PRESENTATION-SPEC-1",
            "status": "DEFINED_NOT_STARTED",
            "goal": "測定済み・測定不足・情報不足・需要比較必要を混同せず、市町別に何が不足しているかを伝える内部表示仕様を定義する。",
            "boundary": "公開4ページをまだ変更せず、外部定性意見1件を方向性証拠としてのみ参照し、service_gapや利用者検証済みを主張しない。",
        },
    }


def render_dataset_json(dataset: dict[str, Any]) -> str:
    return json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    OUTPUT_PATH.write_bytes(render_dataset_json(build_dataset()).encode("utf-8"))


if __name__ == "__main__":
    main()
