"""Build the internal 19-municipality x 35-item supply-side coverage matrix.

Only the five inputs fixed by SPEC.md section 44 are read.  The matrix records
evidence coverage, not transport adequacy: zero registry rows, GTFS access
states, and feed-wide metrics are never converted into service absence,
municipal supply quantities, or an automatic ``service_gap`` decision.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "work1_supply_side_information_coverage_matrix.json"

TASK_ID = "WORK1-SUPPLY-SIDE-INFORMATION-COVERAGE-MATRIX-1"
SCHEMA_VERSION = "WORK1-SUPPLY-SIDE-INFORMATION-COVERAGE-MATRIX-1"

INPUT_PATHS = (
    "data/work1_supply_side_information_model.json",
    "docs/data/municipal_supply.json",
    "data/municipality_gtfs.json",
    "data/gtfs_supply_metrics.json",
    "data/jrbus_chugoku_supply_metrics.json",
)

REQUIRED_ROW_FIELDS = (
    "municipality_code",
    "municipality",
    "category_id",
    "item_id",
    "current_status",
    "accepted_source_ids",
    "evidence_date",
    "scope_note",
    "next_confirmation",
    "claim_boundary",
)

VISIBLE_CURRENT = "VISIBLE_CURRENT"
ACCEPTED_SOURCE_UNMEASURED = "ACCEPTED_SOURCE_UNMEASURED"
ADDITIONAL_SOURCE_REQUIRED = "ADDITIONAL_SOURCE_REQUIRED"
DEMAND_COMPARATOR_REQUIRED = "DEMAND_COMPARATOR_REQUIRED"

REGISTRY_VISIBLE_ITEM_IDS = frozenset({
    "registered_operator_and_type",
    "registered_vehicle_count",
})
WELFARE_ITEM_ID = "welfare_eligibility_scope"

GTFS_RELATED_ITEM_IDS = frozenset({
    "gtfs_agency_and_feed_inventory",
    "route_identity_and_name",
    "stop_name_and_coordinates",
    "route_shape",
    "municipality_feed_spatial_coverage",
    "scheduled_trip_count_by_date",
    "service_calendar",
    "stop_level_timetable",
    "time_band_frequency",
    "transfer_wait_and_travel_time",
    "fare_and_payment",
})


def _path(relative_path: str) -> Path:
    return REPO_ROOT.joinpath(*relative_path.split("/"))


def _load_json(relative_path: str) -> Any:
    return json.loads(_path(relative_path).read_text(encoding="utf-8"))


def _sha256(relative_path: str) -> str:
    return hashlib.sha256(_path(relative_path).read_bytes()).hexdigest()


def _split_feed_ids(value: str) -> tuple[str, ...]:
    return tuple(item for item in value.split(";") if item)


def _unique_in_order(values: list[str], source_order: tuple[str, ...]) -> list[str]:
    present = set(values)
    return [source_id for source_id in source_order if source_id in present]


def _registry_sources_for_operators(
    operators: list[dict[str, Any]],
    source_id_by_pdf: dict[str, str],
    *,
    welfare_only: bool = False,
) -> list[str]:
    source_ids: list[str] = []
    for operator in operators:
        if welfare_only and operator["transport_type"] != "福祉有償運送":
            continue
        source_pdf = operator["source_pdf"]
        if source_pdf not in source_id_by_pdf:
            raise ValueError(f"accepted registry source is unknown: {source_pdf}")
        source_ids.append(source_id_by_pdf[source_pdf])
    return source_ids


def _metric_note(source_ids: list[str], metric_by_feed: dict[str, dict[str, Any]]) -> str:
    if not source_ids:
        return ""
    parts = []
    for source_id in source_ids:
        metric = metric_by_feed[source_id]
        scope = metric.get("measurement_scope", "whole_feed_record")
        parts.append(
            f"{source_id}:公式基準日{metric['official_reference_date']}・確認日"
            f"{metric['checked_at']}・測定範囲{scope}"
        )
    return "受入済みGTFS=" + " / ".join(parts) + "。"


def _build_scope_note(
    item: dict[str, Any],
    municipality_supply: dict[str, Any],
    municipality_gtfs: dict[str, Any],
    current_status: str,
    selected_source_ids: list[str],
    registry_source_ids: frozenset[str],
    gtfs_source_ids: frozenset[str],
    metric_by_feed: dict[str, dict[str, Any]],
    registry_data_as_of: str,
) -> str:
    notes = [item["scope_note"]]
    item_sources = set(item["accepted_source_ids"])
    has_registry_dimension = bool(item_sources & registry_source_ids)
    has_gtfs_dimension = item["item_id"] in GTFS_RELATED_ITEM_IDS or bool(
        item_sources & gtfs_source_ids
    )

    if item["category_id"] == "C1_EVIDENCE_PROVENANCE" or has_registry_dimension:
        if item["category_id"] == "C1_EVIDENCE_PROVENANCE" or item["item_id"] in REGISTRY_VISIBLE_ITEM_IDS:
            notes.append(
                f"登録供給は{registry_data_as_of}時点の4登録簿全体を市町名で照合した派生入力。"
                f"該当記載は{municipality_supply['operator_count']}件。"
            )
        elif selected_source_ids:
            notes.append(
                f"4登録簿の派生入力に該当行があり、この項目に対応する受入原本を市町単位で付与した。"
            )
        elif current_status == ADDITIONAL_SOURCE_REQUIRED:
            notes.append(
                "4登録簿の派生入力にこの項目を測定できる該当行がない。"
                "登録簿範囲外の交通・支援の不存在は示さない。"
            )

    if has_gtfs_dimension:
        feed_ids = _split_feed_ids(municipality_gtfs["feed_ids"])
        notes.append(
            f"既存GTFS入力のアクセス状態={municipality_gtfs['availability_status']}、"
            f"関連フィード={';'.join(feed_ids)}。"
        )
        selected_gtfs = [source_id for source_id in selected_source_ids if source_id in gtfs_source_ids]
        if selected_gtfs:
            notes.append(_metric_note(selected_gtfs, metric_by_feed))
            notes.append(
                "測定済み値がある場合も受入フィード全体の収録値であり、市町境界内だけの供給量ではない。"
            )
        else:
            notes.append(
                "現在の受入済み3 GTFS原本には、この市町へ対応付けられる原本がない。"
                "アクセス状態をGTFSまたは交通サービスの不存在へ変換しない。"
            )

    if current_status == DEMAND_COMPARATOR_REQUIRED:
        notes.append("供給側行列とは分離した需要比較入力が必要。")
    return " ".join(note for note in notes if note)


def _build_claim_boundary(
    item: dict[str, Any],
    selected_source_ids: list[str],
    registry_source_ids: frozenset[str],
    gtfs_source_ids: frozenset[str],
) -> str:
    boundaries = ["情報不足・測定不足からservice_gapを自動判定しない。"]
    item_sources = set(item["accepted_source_ids"])
    if item["category_id"] == "C1_EVIDENCE_PROVENANCE" or item_sources & registry_source_ids:
        boundaries.append(
            "登録0件は4登録簿上の該当記載0件だけを表し、交通手段・移動支援・別制度の不存在を意味しない。"
        )
    if item["item_id"] == "registered_vehicle_count" or item["item_id"] == "accessibility_features":
        boundaries.append("登録車両数・車種は実稼働容量や実利用可能性を意味しない。")
    if item["item_id"] in GTFS_RELATED_ITEM_IDS or item_sources & gtfs_source_ids:
        boundaries.append(
            "GTFSアクセス状態は交通の有無・質・網羅率を意味せず、フィード全体値を市町内供給量にしない。"
        )
    if item["item_id"] == "scheduled_trip_count_by_date":
        boundaries.append("予定便数は実運行・利用実績・利便性を意味しない。")
    if "jrbus-chugoku-gtfs" in selected_source_ids:
        boundaries.append("JRバス中国の県外を含む広域指標を市町へ配賦しない。")
    if item["current_status"] == DEMAND_COMPARATOR_REQUIRED:
        boundaries.append("供給を需要・活動機会・実運行と比較する前に交通不足を結論づけない。")
    return " ".join(boundaries)


def _select_state_and_sources(
    category_id: str,
    item: dict[str, Any],
    operators: list[dict[str, Any]],
    related_accepted_gtfs: list[str],
    source_order: tuple[str, ...],
    registry_source_ids: frozenset[str],
    gtfs_source_ids: frozenset[str],
    source_id_by_pdf: dict[str, str],
) -> tuple[str, list[str]]:
    model_status = item["current_status"]
    item_source_ids = set(item["accepted_source_ids"])

    if model_status in {ADDITIONAL_SOURCE_REQUIRED, DEMAND_COMPARATOR_REQUIRED}:
        return model_status, []

    if category_id == "C1_EVIDENCE_PROVENANCE":
        selected = list(registry_source_ids)
        selected.extend(related_accepted_gtfs)
        return model_status, _unique_in_order(selected, source_order)

    if item["item_id"] in REGISTRY_VISIBLE_ITEM_IDS:
        return model_status, [
            source_id for source_id in source_order if source_id in registry_source_ids
        ]

    registry_sources = _registry_sources_for_operators(
        operators,
        source_id_by_pdf,
        welfare_only=item["item_id"] == WELFARE_ITEM_ID,
    )
    selected = [source_id for source_id in registry_sources if source_id in item_source_ids]
    selected.extend(
        source_id
        for source_id in related_accepted_gtfs
        if source_id in item_source_ids and source_id in gtfs_source_ids
    )
    selected = _unique_in_order(selected, source_order)
    if selected:
        return model_status, selected
    return ADDITIONAL_SOURCE_REQUIRED, []


def build_dataset() -> dict[str, Any]:
    model = _load_json(INPUT_PATHS[0])
    municipal_supply = _load_json(INPUT_PATHS[1])
    municipality_gtfs = _load_json(INPUT_PATHS[2])
    gtfs_metrics = _load_json(INPUT_PATHS[3])
    jrbus_metrics = _load_json(INPUT_PATHS[4])

    categories = model["categories"]
    items = [
        (category["category_id"], item)
        for category in categories
        for item in category["items"]
    ]
    if len(categories) != 8 or len(items) != 35:
        raise ValueError("information model must contain exactly 8 categories and 35 items")

    allowed_statuses = tuple(item["code"] for item in model["status_vocabulary"])
    if set(allowed_statuses) != {
        VISIBLE_CURRENT,
        ACCEPTED_SOURCE_UNMEASURED,
        ADDITIONAL_SOURCE_REQUIRED,
        DEMAND_COMPARATOR_REQUIRED,
    }:
        raise ValueError("information model status vocabulary is not the fixed four-state set")
    next_action_by_status = {
        item["code"]: item["next_action"] for item in model["status_vocabulary"]
    }

    source_mapping = model["accepted_source_mapping"]
    source_order = tuple(item["source_id"] for item in source_mapping)
    if len(source_order) != 7 or len(source_order) != len(set(source_order)):
        raise ValueError("accepted source mapping must contain seven unique sources")
    source_type_by_id = {
        item["source_id"]: item["source_type"] for item in source_mapping
    }
    registry_source_ids = frozenset(
        source_id
        for source_id, source_type in source_type_by_id.items()
        if source_type == "registry_pdf"
    )
    gtfs_source_ids = frozenset(
        source_id
        for source_id, source_type in source_type_by_id.items()
        if source_type == "gtfs_zip"
    )
    if len(registry_source_ids) != 4 or len(gtfs_source_ids) != 3:
        raise ValueError("accepted sources must remain four registries and three GTFS archives")
    source_id_by_pdf = {
        Path(item["local_path"]).name: item["source_id"]
        for item in source_mapping
        if item["source_type"] == "registry_pdf"
    }

    supply_rows = municipal_supply["municipalities"]
    supply_by_name = {item["municipality"]: item for item in supply_rows}
    gtfs_by_name = {item["municipality"]: item for item in municipality_gtfs}
    if len(supply_rows) != 19 or len(municipality_gtfs) != 19:
        raise ValueError("both municipality inputs must contain exactly 19 rows")
    if len(supply_by_name) != 19 or set(supply_by_name) != set(gtfs_by_name):
        raise ValueError("municipality inputs do not contain the same 19 unique names")
    municipality_codes = [item["municipality_code"] for item in municipality_gtfs]
    if len(municipality_codes) != len(set(municipality_codes)):
        raise ValueError("municipality_code must be unique")

    metric_records = list(gtfs_metrics) + [jrbus_metrics]
    metric_by_feed = {item["feed_id"]: item for item in metric_records}
    if set(metric_by_feed) != gtfs_source_ids:
        raise ValueError("the three accepted GTFS sources must each have one metrics input")
    if metric_by_feed["jrbus-chugoku-gtfs"].get("measurement_scope") != "whole_feed":
        raise ValueError("JR Bus Chugoku metrics must remain whole_feed")

    rows: list[dict[str, Any]] = []
    for gtfs_row in municipality_gtfs:
        municipality = gtfs_row["municipality"]
        supply_row = supply_by_name[municipality]
        related_feed_ids = _split_feed_ids(gtfs_row["feed_ids"])
        related_accepted_gtfs = [
            source_id for source_id in source_order
            if source_id in gtfs_source_ids and source_id in related_feed_ids
        ]
        for category_id, item in items:
            current_status, selected_sources = _select_state_and_sources(
                category_id,
                item,
                supply_row["operators"],
                related_accepted_gtfs,
                source_order,
                registry_source_ids,
                gtfs_source_ids,
                source_id_by_pdf,
            )
            row = {
                "municipality_code": gtfs_row["municipality_code"],
                "municipality": municipality,
                "category_id": category_id,
                "item_id": item["item_id"],
                "current_status": current_status,
                "accepted_source_ids": selected_sources,
                "evidence_date": model["model_as_of"],
                "scope_note": _build_scope_note(
                    {**item, "category_id": category_id},
                    supply_row,
                    gtfs_row,
                    current_status,
                    selected_sources,
                    registry_source_ids,
                    gtfs_source_ids,
                    metric_by_feed,
                    municipal_supply["meta"]["data_as_of"],
                ),
                "next_confirmation": next_action_by_status[current_status],
                "claim_boundary": _build_claim_boundary(
                    {**item, "category_id": category_id},
                    selected_sources,
                    registry_source_ids,
                    gtfs_source_ids,
                ),
            }
            if tuple(row) != REQUIRED_ROW_FIELDS:
                raise AssertionError("matrix row field order drifted")
            rows.append(row)

    expected_rows = 19 * 35
    if len(rows) != expected_rows:
        raise AssertionError(f"matrix row count is {len(rows)}, expected {expected_rows}")
    status_counts = {
        status: sum(row["current_status"] == status for row in rows)
        for status in allowed_statuses
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "matrix_as_of": model["model_as_of"],
        "dimensions": {
            "municipality_count": 19,
            "category_count": 8,
            "item_count_per_municipality": 35,
            "row_count": expected_rows,
        },
        "required_row_fields": list(REQUIRED_ROW_FIELDS),
        "input_files": [
            {"path": relative_path, "sha256": _sha256(relative_path)}
            for relative_path in INPUT_PATHS
        ],
        "state_rules": [
            "モデルのVISIBLE_CURRENTまたはACCEPTED_SOURCE_UNMEASUREDは、市町に対応する受入原本がある場合だけ維持する。",
            "4登録簿全体を照合した登録団体・登録車両の表示項目は、0件の市町もVISIBLE_CURRENTとするが、交通不存在を意味しない。",
            "市町に対応する受入原本がない項目はADDITIONAL_SOURCE_REQUIREDとし、GTFSアクセス状態を交通の有無・質に変換しない。",
            "フィード全体値は市町内供給量にせず、JRバス中国の広域指標は市町へ配賦しない。",
            "どの行からもservice_gapを自動判定しない。",
        ],
        "status_counts": status_counts,
        "rows": rows,
    }


def render_dataset_json(dataset: dict[str, Any]) -> str:
    return json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    OUTPUT_PATH.write_bytes(render_dataset_json(build_dataset()).encode("utf-8"))


if __name__ == "__main__":
    main()
