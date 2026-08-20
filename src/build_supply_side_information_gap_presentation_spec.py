"""Build the internal presentation specification for Work 1 information gaps.

The specification classifies all 665 municipality-item rows without changing
the public site.  It distinguishes public facts, bounded internal measurements,
measurement gaps, information gaps, and demand-comparator requirements.  It
does not copy the large measurement values, allocate feed-wide values to a
municipality, or decide that a transport service is sufficient or insufficient.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = (
    REPO_ROOT / "data" / "work1_supply_side_information_gap_presentation_spec.json"
)

TASK_ID = "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PRESENTATION-SPEC-1"
SCHEMA_VERSION = "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PRESENTATION-SPEC-1"
SPEC_AS_OF = "2026-08-20"

MODEL_PATH = "data/work1_supply_side_information_model.json"
MATRIX_PATH = "data/work1_supply_side_information_coverage_matrix.json"
MEASUREMENT_PATH = "data/work1_supply_side_accepted_source_bounded_measurement.json"
FEEDBACK_PATH = "evidence/20260820_work1_udc_yamaguchi_coordinator_qualitative_feedback.json"
INPUT_PATHS = (MODEL_PATH, MATRIX_PATH, MEASUREMENT_PATH, FEEDBACK_PATH)

PUBLICLY_VISIBLE_CURRENT = "PUBLICLY_VISIBLE_CURRENT"
MEASURED_BOUNDED_INTERNAL = "MEASURED_BOUNDED_INTERNAL"
MEASUREMENT_GAP_PARTIAL_SOURCE = "MEASUREMENT_GAP_PARTIAL_SOURCE"
MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED = (
    "MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED"
)
INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED = (
    "INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED"
)
DEMAND_COMPARATOR_REQUIRED = "DEMAND_COMPARATOR_REQUIRED"

PRESENTATION_STATE_ORDER = (
    MEASUREMENT_GAP_PARTIAL_SOURCE,
    MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED,
    INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED,
    PUBLICLY_VISIBLE_CURRENT,
    MEASURED_BOUNDED_INTERNAL,
    DEMAND_COMPARATOR_REQUIRED,
)

EXPECTED_STATE_COUNTS = {
    PUBLICLY_VISIBLE_CURRENT: 128,
    MEASURED_BOUNDED_INTERNAL: 61,
    MEASUREMENT_GAP_PARTIAL_SOURCE: 30,
    MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED: 7,
    INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED: 344,
    DEMAND_COMPARATOR_REQUIRED: 95,
}

STATE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "code": PUBLICLY_VISIBLE_CURRENT,
        "information_condition": "CONFIRMED_INFORMATION",
        "public_visibility": "CURRENTLY_PUBLIC",
        "short_label": "公開中の確認情報",
        "label": "現在の公開画面または公開JSONで確認できる情報",
        "meaning": "受入済み原本に基づく既存公開値を、現在の範囲・日付・非主張とともに示す。",
        "allowed_statement": "現在の公開範囲で確認できる。",
        "prohibited_statement": "公開値が県内交通全体を網羅し、需要を満たしている。",
    },
    {
        "code": MEASURED_BOUNDED_INTERNAL,
        "information_condition": "CONFIRMED_INFORMATION",
        "public_visibility": "INTERNAL_ONLY_NOT_PUBLIC",
        "short_label": "原本から限定測定済み",
        "label": "受入済み原本から限定測定済みだが、公開画面には未反映の情報",
        "meaning": "限定測定resultを出典・粒度・非主張付きで参照できる。",
        "allowed_statement": "受入済み原本の限定範囲で測定済み。",
        "prohibited_statement": "実運行、現在利用可能性、市町内供給量、需要充足を測定済み。",
    },
    {
        "code": MEASUREMENT_GAP_PARTIAL_SOURCE,
        "information_condition": "MEASUREMENT_GAP",
        "public_visibility": "STATUS_ONLY_NO_VALUE",
        "short_label": "原本内の一部情報のみ",
        "label": "受入済み原本に部分情報はあるが、項目全体の測定が不足",
        "meaning": "部分列・部分表を項目全体の充足へ読み替えず、次の測定確認を示す。",
        "allowed_statement": "受入原本内に関連情報があるが、必要な単位では未測定。",
        "prohibited_statement": "不足部分は0、存在しない、または確認済み。",
    },
    {
        "code": MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED,
        "information_condition": "MEASUREMENT_GAP",
        "public_visibility": "STATUS_ONLY_NO_VALUE",
        "short_label": "測定前提の追加入力が必要",
        "label": "受入済み原本を必要単位で測るための前提入力が不足",
        "meaning": "市町境界等の未受入入力を補わず、測定未実行として示す。",
        "allowed_statement": "原本は受入済みだが、この単位の測定には追加入力が必要。",
        "prohibited_statement": "対象範囲は0件、0%、または交通が存在しない。",
    },
    {
        "code": INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED,
        "information_condition": "INFORMATION_GAP",
        "public_visibility": "STATUS_ONLY_NO_VALUE",
        "short_label": "確認できる原本が不足",
        "label": "現在の受入済み7原本だけでは確認できない情報",
        "meaning": "候補原本の検討が必要であり、存在・不存在の値は表示しない。",
        "allowed_statement": "現在の受入原本だけでは確認できず、追加原本の検討が必要。",
        "prohibited_statement": "情報対象または交通サービスが存在しない。",
    },
    {
        "code": DEMAND_COMPARATOR_REQUIRED,
        "information_condition": "DEMAND_COMPARATOR_REQUIRED",
        "public_visibility": "STATUS_ONLY_NO_VALUE",
        "short_label": "生活・需要との比較が必要",
        "label": "供給情報と分離した生活・需要の比較入力が必要",
        "meaning": "人口、目的地、移動需要、利用経験等との比較前には充足を判断しない。",
        "allowed_statement": "供給情報だけでは判断できず、比較入力が必要。",
        "prohibited_statement": "現在の交通は足りている、または足りていない。",
    },
)

STATE_BY_CODE = {item["code"]: item for item in STATE_DEFINITIONS}

REQUIRED_ROW_FIELDS = (
    "municipality_code",
    "municipality",
    "category_id",
    "category_label",
    "item_id",
    "item_label",
    "upstream_status",
    "presentation_state",
    "information_condition",
    "public_visibility",
    "accepted_source_ids",
    "measurement_status",
    "measurement_result_ids",
    "detail_spec_id",
    "evidence_date",
    "primary_label",
    "display_explanation",
    "source_scope_note",
    "scope_note",
    "value_rendering_rule",
    "next_confirmation",
    "claim_boundary",
)

COMMON_CLAIM_BOUNDARY = (
    "これは情報の確認状態であり、交通サービスの充足・不足、実運行、現在利用可能性、"
    "需要充足、service_gapを判定しない。"
)

GTFS_MEASURED_ITEMS = {
    "route_identity_and_name",
    "stop_name_and_coordinates",
    "route_shape",
    "service_calendar",
    "stop_level_timetable",
    "time_band_frequency",
}

DETAIL_SPEC_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "detail_spec_id": "PD-01-REGISTERED-SERVICE-AREA",
        "item_id": "registered_service_area_detail",
        "display_form": "source_record_table",
        "allowed_fields": [
            "source_id",
            "source_pdf",
            "source_page",
            "registration_no",
            "transport_type",
            "org_name",
            "service_area_raw",
            "service_area_municipalities",
            "office_name_location_pairs",
        ],
        "required_scope_badge": "4登録簿の市町照合済み記録",
        "default_mode": "collapsed_summary_then_evidence_table",
        "prohibited_transformations": [
            "登録区域を現在の実運行区域または予約受付区域とする",
            "複数市町の登録記録を市町別供給量へ配賦する",
        ],
    },
    {
        "detail_spec_id": "PD-02-GTFS-ROUTE-IDENTITY",
        "item_id": "route_identity_and_name",
        "display_form": "feed_scoped_route_table",
        "allowed_fields": ["route_records", "trip_references"],
        "required_scope_badge": "受入GTFSフィード全体（市町内値ではない）",
        "default_mode": "collapsed_feed_summary_then_route_table",
        "prohibited_transformations": [
            "route_id件数を現実の路線本数または市町内路線本数とする",
            "関係市町へフィード全体値を配賦する",
        ],
    },
    {
        "detail_spec_id": "PD-03-GTFS-STOP-LOCATION",
        "item_id": "stop_name_and_coordinates",
        "display_form": "feed_scoped_stop_table",
        "allowed_fields": ["stop_records"],
        "required_scope_badge": "受入GTFSフィード全体（市町内停留所ではない）",
        "default_mode": "collapsed_feed_summary_then_stop_table",
        "prohibited_transformations": [
            "stop_id件数を物理停留所数または市町内停留所数とする",
            "市町境界がないまま市町内分布として地図表示する",
        ],
    },
    {
        "detail_spec_id": "PD-04-GTFS-ROUTE-SHAPE",
        "item_id": "route_shape",
        "display_form": "feed_scoped_shape_reference",
        "allowed_fields": ["shape_records", "trip_shape_references"],
        "required_scope_badge": "受入GTFSフィード全体（市町境界未適用）",
        "default_mode": "collapsed_feed_summary_then_shape_reference",
        "prohibited_transformations": [
            "市町境界で切り分けていない形状を市町内カバー範囲とする",
            "shapeの存在を現在運行の証明とする",
        ],
    },
    {
        "detail_spec_id": "PD-05-GTFS-SERVICE-CALENDAR",
        "item_id": "service_calendar",
        "display_form": "feed_scoped_calendar",
        "allowed_fields": [
            "calendar_rules",
            "calendar_date_exceptions",
            "active_service_by_date",
        ],
        "required_scope_badge": "受入GTFSの予定運行日",
        "default_mode": "date_selector_then_active_service_ids",
        "prohibited_transformations": [
            "予定運行日を実運行実績とする",
            "feed期間外を運行なしと断定する",
        ],
    },
    {
        "detail_spec_id": "PD-06-GTFS-STOP-TIMETABLE",
        "item_id": "stop_level_timetable",
        "display_form": "normalized_feed_timetable",
        "allowed_fields": ["stop_call_templates", "active_service_result_id"],
        "required_scope_badge": "受入GTFSの予定時刻・フィード全体",
        "default_mode": "service_date_join_then_collapsed_trip_detail",
        "prohibited_transformations": [
            "予定時刻を実発着または定時性とする",
            "日付とservice_idを結合せず全日運行とする",
        ],
    },
    {
        "detail_spec_id": "PD-07-GTFS-TIME-BAND-FREQUENCY",
        "item_id": "time_band_frequency",
        "display_form": "normalized_feed_frequency",
        "allowed_fields": ["frequency_templates", "active_service_result_id"],
        "required_scope_badge": "受入GTFSの予定頻度・フィード全体",
        "default_mode": "service_date_join_then_hour_group_summary",
        "prohibited_transformations": [
            "予定頻度を実運行頻度または待ち時間保証とする",
            "フィード全体頻度を市町内供給量へ配賦する",
        ],
    },
    {
        "detail_spec_id": "PD-08-WELFARE-ELIGIBILITY",
        "item_id": "welfare_eligibility_scope",
        "display_form": "registry_original_flag_table",
        "allowed_fields": [
            "source_id",
            "source_pdf",
            "source_page",
            "registration_no",
            "welfare_transport_flag_raw_values",
        ],
        "required_scope_badge": "福祉有償運送登録簿のイ〜ト原値",
        "default_mode": "collapsed_record_summary_then_original_flags",
        "prohibited_transformations": [
            "フラグを会員条件・予約条件・配車可能性の完全判定とする",
            "未記載を対象外または利用不可とする",
        ],
    },
)

DETAIL_SPEC_BY_ITEM = {
    item["item_id"]: item for item in DETAIL_SPEC_DEFINITIONS
}


def _load_json(relative_path: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def _sha256_and_size(relative_path: str) -> tuple[str, int]:
    data = (REPO_ROOT / relative_path).read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return row["municipality_code"], row["item_id"]


def _state_for_row(
    matrix_row: dict[str, Any],
    measured_by_key: dict[tuple[str, str], dict[str, Any]],
    partial_by_key: dict[tuple[str, str], dict[str, Any]],
    additional_input_by_key: dict[tuple[str, str], dict[str, Any]],
) -> str:
    upstream_status = matrix_row["current_status"]
    key = _row_key(matrix_row)
    if upstream_status == "VISIBLE_CURRENT":
        return PUBLICLY_VISIBLE_CURRENT
    if upstream_status == "ACCEPTED_SOURCE_UNMEASURED":
        if key in measured_by_key:
            return MEASURED_BOUNDED_INTERNAL
        if key in partial_by_key:
            return MEASUREMENT_GAP_PARTIAL_SOURCE
        if key in additional_input_by_key:
            return MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED
        raise ValueError(f"unresolved measurement-gap row: {key}")
    if upstream_status == "ADDITIONAL_SOURCE_REQUIRED":
        return INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED
    if upstream_status == "DEMAND_COMPARATOR_REQUIRED":
        return DEMAND_COMPARATOR_REQUIRED
    raise ValueError(f"unexpected upstream status: {upstream_status}")


def _source_scope_note(state: str, item_id: str) -> str:
    if state == PUBLICLY_VISIBLE_CURRENT:
        return "現在の公開画面または公開JSON。既存の根拠・日付・範囲を維持する。"
    if state == MEASURED_BOUNDED_INTERNAL:
        if item_id in GTFS_MEASURED_ITEMS:
            return "関係する受入GTFSフィード全体。市町境界フィルター・市町内配賦は未実施。"
        return "4登録簿の市町照合済み記録。複数市町記録の供給量配賦は未実施。"
    if state == MEASUREMENT_GAP_PARTIAL_SOURCE:
        return "受入済み原本の部分表・部分列。項目全体を確認済みとは扱わない。"
    if state == MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED:
        return "受入済み原本に加え、市町境界等の未受入測定前提が必要。"
    if state == INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED:
        return "現在の受入済み7原本では裏づけられない。"
    return "供給側情報と分離した人口・目的地・需要・利用経験等の比較入力。"


def _value_rendering_rule(state: str) -> str:
    if state == PUBLICLY_VISIBLE_CURRENT:
        return "既存公開値を既存の根拠・日付・範囲・非主張とともに参照する。"
    if state == MEASURED_BOUNDED_INTERNAL:
        return "detail_spec_idとmeasurement_result_idsを参照し、内部値を複製せず範囲badge付きで示す。"
    if state in {
        MEASUREMENT_GAP_PARTIAL_SOURCE,
        MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED,
        INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED,
    }:
        return "状態説明と次の確認事項だけを示し、0件・0%・不存在の数値placeholderを作らない。"
    return "比較入力が必要であることだけを示し、充足・不足の判定値を作らない。"


def _display_explanation(
    state: str,
    matrix_row: dict[str, Any],
    partial: dict[str, Any] | None,
    additional_input: dict[str, Any] | None,
) -> str:
    definition = STATE_BY_CODE[state]
    if partial is not None:
        return definition["meaning"] + " " + partial["reason"]
    if additional_input is not None:
        return definition["meaning"] + " " + additional_input["reason"]
    if state == INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED:
        return definition["meaning"] + " " + matrix_row["next_confirmation"]
    return definition["meaning"]


def _claim_boundary(state: str, matrix_row: dict[str, Any]) -> str:
    definition = STATE_BY_CODE[state]
    boundary = (
        COMMON_CLAIM_BOUNDARY
        + " "
        + definition["prohibited_statement"]
        + " "
        + matrix_row["claim_boundary"]
    )
    if "jrbus-chugoku-gtfs" in matrix_row["accepted_source_ids"]:
        boundary += " JRバス中国の県外を含む広域値を関係4市へ配賦しない。"
    return boundary


def _count_states(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(row["presentation_state"] for row in rows)
    return {state: counts[state] for state in EXPECTED_STATE_COUNTS}


def _count_conditions(rows: list[dict[str, Any]]) -> dict[str, int]:
    order = (
        "CONFIRMED_INFORMATION",
        "MEASUREMENT_GAP",
        "INFORMATION_GAP",
        "DEMAND_COMPARATOR_REQUIRED",
    )
    counts = Counter(row["information_condition"] for row in rows)
    return {condition: counts[condition] for condition in order}


def build_dataset() -> dict[str, Any]:
    model = _load_json(MODEL_PATH)
    matrix = _load_json(MATRIX_PATH)
    measurement = _load_json(MEASUREMENT_PATH)
    feedback = _load_json(FEEDBACK_PATH)

    if model["working_hypothesis"]["deeper_motivation"] != "intentionally_not_recorded_or_inferred":
        raise ValueError("deep motivation boundary drifted")
    if matrix["dimensions"] != {
        "municipality_count": 19,
        "category_count": 8,
        "item_count_per_municipality": 35,
        "row_count": 665,
    }:
        raise ValueError("coverage matrix dimensions drifted")
    if measurement["measurement_status"] != "MEASURED_BOUNDED":
        raise ValueError("bounded measurement is not accepted as measured")

    feedback_classification = feedback["evidence_classification"]
    if feedback_classification["concrete_external_feedback_count"] != 1:
        raise ValueError("exactly one external qualitative feedback record is required")
    for forbidden_flag in (
        "formal_user_test",
        "observed_task_completion",
        "co_design_established",
        "stakeholder_diversity_validated",
        "pre_discussion_memo_workflow_validated",
        "service_gap_validated",
    ):
        if feedback_classification[forbidden_flag]:
            raise ValueError(f"feedback boundary is not safe: {forbidden_flag}")
    if feedback["measurement_separation"]["used_as_bounded_measurement_input"]:
        raise ValueError("external feedback cannot be a measurement input")

    category_by_id = {item["category_id"]: item for item in model["categories"]}
    item_by_id = {
        item["item_id"]: item
        for category in model["categories"]
        for item in category["items"]
    }
    if len(category_by_id) != 8 or len(item_by_id) != 35:
        raise ValueError("information model category or item count drifted")

    measured_by_key = {
        _row_key(item): item for item in measurement["municipality_item_measurements"]
    }
    partial_by_key = {
        _row_key(item): item
        for item in measurement["excluded_applications"]["PARTIAL_SOURCE_ONLY"]
    }
    additional_input_by_key = {
        _row_key(item): item
        for item in measurement["excluded_applications"]["ADDITIONAL_INPUT_REQUIRED"]
    }
    if len(measured_by_key) != 61 or len(partial_by_key) != 30 or len(additional_input_by_key) != 7:
        raise ValueError("bounded measurement 61/30/7 partition drifted")
    if set(measured_by_key) & set(partial_by_key):
        raise ValueError("measured and partial application sets overlap")
    if set(measured_by_key) & set(additional_input_by_key):
        raise ValueError("measured and additional-input application sets overlap")
    if set(partial_by_key) & set(additional_input_by_key):
        raise ValueError("excluded application sets overlap")

    upstream_unmeasured_keys = {
        _row_key(row)
        for row in matrix["rows"]
        if row["current_status"] == "ACCEPTED_SOURCE_UNMEASURED"
    }
    partition_keys = set(measured_by_key) | set(partial_by_key) | set(additional_input_by_key)
    if upstream_unmeasured_keys != partition_keys:
        raise ValueError("98 measurement-gap rows do not resolve to 61/30/7 exactly")

    rows: list[dict[str, Any]] = []
    for matrix_row in matrix["rows"]:
        key = _row_key(matrix_row)
        measured = measured_by_key.get(key)
        partial = partial_by_key.get(key)
        additional_input = additional_input_by_key.get(key)
        state = _state_for_row(
            matrix_row, measured_by_key, partial_by_key, additional_input_by_key
        )
        definition = STATE_BY_CODE[state]
        detail_spec = DETAIL_SPEC_BY_ITEM.get(matrix_row["item_id"])
        row = {
            "municipality_code": matrix_row["municipality_code"],
            "municipality": matrix_row["municipality"],
            "category_id": matrix_row["category_id"],
            "category_label": category_by_id[matrix_row["category_id"]]["label"],
            "item_id": matrix_row["item_id"],
            "item_label": item_by_id[matrix_row["item_id"]]["label"],
            "upstream_status": matrix_row["current_status"],
            "presentation_state": state,
            "information_condition": definition["information_condition"],
            "public_visibility": definition["public_visibility"],
            "accepted_source_ids": matrix_row["accepted_source_ids"],
            "measurement_status": measured["measurement_status"] if measured else None,
            "measurement_result_ids": measured["measurement_result_ids"] if measured else [],
            "detail_spec_id": detail_spec["detail_spec_id"] if measured else None,
            "evidence_date": matrix_row["evidence_date"],
            "primary_label": definition["short_label"],
            "display_explanation": _display_explanation(
                state, matrix_row, partial, additional_input
            ),
            "source_scope_note": _source_scope_note(state, matrix_row["item_id"]),
            "scope_note": matrix_row["scope_note"],
            "value_rendering_rule": _value_rendering_rule(state),
            "next_confirmation": matrix_row["next_confirmation"],
            "claim_boundary": _claim_boundary(state, matrix_row),
        }
        if tuple(row) != REQUIRED_ROW_FIELDS:
            raise AssertionError("presentation row field order drifted")
        rows.append(row)

    if len(rows) != 665 or len({_row_key(row) for row in rows}) != 665:
        raise ValueError("presentation rows must be 665 unique municipality-item pairs")
    state_counts = _count_states(rows)
    if state_counts != EXPECTED_STATE_COUNTS:
        raise ValueError(f"presentation state counts drifted: {state_counts}")
    condition_counts = _count_conditions(rows)
    if condition_counts != {
        "CONFIRMED_INFORMATION": 189,
        "MEASUREMENT_GAP": 37,
        "INFORMATION_GAP": 344,
        "DEMAND_COMPARATOR_REQUIRED": 95,
    }:
        raise ValueError(f"information-condition counts drifted: {condition_counts}")

    municipalities: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for row in matrix["rows"]:
        if row["municipality_code"] not in seen_codes:
            seen_codes.add(row["municipality_code"])
            municipalities.append({
                "municipality_code": row["municipality_code"],
                "municipality": row["municipality"],
            })
    municipality_summaries = []
    for municipality in municipalities:
        municipal_rows = [
            row for row in rows
            if row["municipality_code"] == municipality["municipality_code"]
        ]
        state_summary = _count_states(municipal_rows)
        condition_summary = _count_conditions(municipal_rows)
        municipality_summaries.append({
            **municipality,
            "item_count": len(municipal_rows),
            "presentation_state_counts": state_summary,
            "information_condition_counts": condition_summary,
            "next_confirmation_count": (
                condition_summary["MEASUREMENT_GAP"]
                + condition_summary["INFORMATION_GAP"]
            ),
            "demand_comparator_count": condition_summary["DEMAND_COMPARATOR_REQUIRED"],
        })
    if len(municipality_summaries) != 19:
        raise ValueError("municipality summary count drifted")
    if any(item["item_count"] != 35 for item in municipality_summaries):
        raise ValueError("each municipality must summarize 35 information items")

    category_summaries = []
    for category in model["categories"]:
        category_rows = [
            row for row in rows if row["category_id"] == category["category_id"]
        ]
        category_summaries.append({
            "category_id": category["category_id"],
            "category_label": category["label"],
            "item_count_per_municipality": len(category["items"]),
            "row_count": len(category_rows),
            "presentation_state_counts": _count_states(category_rows),
            "information_condition_counts": _count_conditions(category_rows),
        })

    input_files = []
    for relative_path in INPUT_PATHS:
        sha256, size = _sha256_and_size(relative_path)
        input_files.append({"path": relative_path, "bytes": size, "sha256": sha256})

    feedback_sha256, feedback_size = _sha256_and_size(FEEDBACK_PATH)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "spec_as_of": SPEC_AS_OF,
        "spec_status": "DEFINED_INTERNAL_NOT_IMPLEMENTED_PUBLICLY",
        "dimensions": {
            "municipality_count": 19,
            "category_count": 8,
            "item_count_per_municipality": 35,
            "municipality_item_row_count": 665,
            "presentation_state_count": len(STATE_DEFINITIONS),
            "measured_detail_spec_count": len(DETAIL_SPEC_DEFINITIONS),
            "input_file_count": len(input_files),
        },
        "input_files": input_files,
        "information_condition_counts": condition_counts,
        "presentation_state_counts": state_counts,
        "presentation_state_vocabulary": list(STATE_DEFINITIONS),
        "required_row_fields": list(REQUIRED_ROW_FIELDS),
        "screen_contract": {
            "purpose": "市町別に、確認できる情報と次に必要な確認を、交通サービスの充足判定と混同せず示す。",
            "page_title": "確認できる情報と、次に必要な確認",
            "default_summary_order": [
                {
                    "section_id": "NEXT_CONFIRMATION",
                    "label": "次に確認する情報",
                    "information_conditions": ["MEASUREMENT_GAP", "INFORMATION_GAP"],
                },
                {
                    "section_id": "CONFIRMED_INFORMATION",
                    "label": "確認できる情報",
                    "information_conditions": ["CONFIRMED_INFORMATION"],
                },
                {
                    "section_id": "DEMAND_COMPARISON",
                    "label": "生活・需要との比較が必要な情報",
                    "information_conditions": ["DEMAND_COMPARATOR_REQUIRED"],
                },
            ],
            "category_order": [category["category_id"] for category in model["categories"]],
            "state_order_within_section": list(PRESENTATION_STATE_ORDER),
            "initial_view": "municipality_summary_counts_and_category_rows",
            "detail_disclosure": "項目行から出典・日付・範囲・次の確認・非主張を展開する。",
            "evidence_drawer_fields": [
                "accepted_source_ids",
                "evidence_date",
                "source_scope_note",
                "scope_note",
                "next_confirmation",
                "claim_boundary",
            ],
            "accessibility": [
                "状態は色だけで伝えず、短い状態名を常に表示する。",
                "フィード全体・市町照合済み・公開中・内部のみの範囲badgeを文字で示す。",
                "表形式詳細には見出しと範囲説明を付ける。",
            ],
        },
        "copy_contract": {
            "required_heading": "確認できる情報と、次に必要な確認",
            "required_distinction": "情報の不足と交通サービスの不足を別概念として明記する。",
            "missing_value_copy": "確認できる原本が不足" ,
            "prohibited_unqualified_phrases": [
                "交通がない",
                "交通が足りない",
                "データなし",
                "未対応",
                "利用できない",
                "市町内の路線数",
                "市町内の停留所数",
            ],
            "prohibited_decisions": [
                "登録0件から交通不存在を決める",
                "GTFSアクセス状態から交通の有無・質を決める",
                "予定値から実運行または利便性を決める",
                "情報不足・測定不足からservice_gapを決める",
            ],
        },
        "zero_and_missing_value_contract": {
            "registered_zero_label": "4登録簿上の該当記載0件",
            "registered_zero_boundary": "交通手段・移動支援・別制度の不存在を意味しない。",
            "gap_value_rule": "gap状態では0件・0%・不存在のplaceholderを生成しない。",
            "blank_rule": "原本空欄・表なし・0行・未受入入力を同じ欠損値へ統合しない。",
        },
        "measured_detail_presentation_specs": list(DETAIL_SPEC_DEFINITIONS),
        "municipality_summaries": municipality_summaries,
        "category_summaries": category_summaries,
        "municipality_item_presentation_specs": rows,
        "external_feedback_direction": {
            "evidence_path": FEEDBACK_PATH,
            "bytes": feedback_size,
            "sha256": feedback_sha256,
            "concrete_external_feedback_count": 1,
            "directional_improvement_suggestion_count": 1,
            "used_for_direction": "何が不足しているかを明確にする表示方向",
            "used_to_assign_row_states": False,
            "measurement_input": False,
            "formal_user_test_result": False,
            "co_design_result": False,
            "user_value_validation": False,
            "service_gap_validation": False,
        },
        "publication_gate": {
            "public_files_changed_by_this_stage": [],
            "docs_data_copy_created": False,
            "public_implementation_status": "NOT_STARTED",
            "human_approval_required_before_public_change": True,
        },
        "global_boundaries": [
            "内部表示仕様であり、公開4ページとdocs/dataを変更しない。",
            "測定JSONの大量値を複製せず、61行はmeasurement_result_idsで参照する。",
            "登録0件を交通不存在へ変換しない。",
            "GTFSアクセス状態を交通の有無・質へ変換しない。",
            "GTFSフィード全体値を市町内値へ変換・配賦しない。",
            "JRバス中国の県外を含む広域値を関係4市へ配賦しない。",
            "部分情報30・追加入力必要7を測定済みまたは0へ変換しない。",
            "情報不足・測定不足・需要比較必要からservice_gapを自動判定しない。",
            "外部定性意見1件を利用者検証・共同設計・利用者価値の証明へ変換しない。",
            "作成者の深い問題意識は記録・推測しない。",
        ],
        "next_stage": {
            "task_id": "WORK1-SUPPLY-SIDE-INFORMATION-GAP-INTERNAL-PROTOTYPE-1",
            "status": "DEFINED_NOT_STARTED",
            "goal": "本仕様からローカル限定の市町別表示プロトタイプを生成し、表示文言・粒度・範囲badgeを検証する。",
            "boundary": "公開4ページ・docs/data・新原本・需要入力・service_gap判定を変更せず、外部公開前に停止する。",
            "human_approval_required_to_start": True,
        },
    }


def render_dataset_json(dataset: dict[str, Any]) -> str:
    return json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    OUTPUT_PATH.write_bytes(render_dataset_json(build_dataset()).encode("utf-8"))


if __name__ == "__main__":
    main()
