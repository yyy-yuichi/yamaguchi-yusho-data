"""Build the public-safe municipality information-gap dataset for Work 1."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PRESENTATION_PATH = "data/work1_supply_side_information_gap_presentation_spec.json"
INTEGRATION_SPEC_PATH = "data/work1_supply_side_information_gap_public_integration_spec.json"
OUTPUT_PATH = REPO_ROOT / "docs" / "data" / "work1_supply_side_information_gap.json"

TASK_ID = "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PUBLIC-INTEGRATION-1"
SCHEMA_VERSION = f"{TASK_ID}-PUBLIC-DATA-1"
DATA_AS_OF = "2026-08-21"
MAXIMUM_BYTES = 1_500_000

PUBLIC_STATE_MAP = {
    "PUBLICLY_VISIBLE_CURRENT": "CURRENTLY_VISIBLE_INFORMATION",
    "MEASURED_BOUNDED_INTERNAL": "ACCEPTED_SOURCE_MEASURED_BOUNDED",
    "MEASUREMENT_GAP_PARTIAL_SOURCE": "MEASUREMENT_GAP_PARTIAL_SOURCE",
    "MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED": "MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED",
    "INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED": "INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED",
    "DEMAND_COMPARATOR_REQUIRED": "DEMAND_COMPARATOR_REQUIRED",
}

STATUS_LABELS = {
    "CURRENTLY_VISIBLE_INFORMATION": "現在の公開情報で確認",
    "ACCEPTED_SOURCE_MEASURED_BOUNDED": "受入原本の限定範囲で確認",
    "MEASUREMENT_GAP_PARTIAL_SOURCE": "原本内の一部情報のみ",
    "MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED": "測定前提の追加入力が必要",
    "INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED": "確認できる原本が不足",
    "DEMAND_COMPARATOR_REQUIRED": "生活・需要との比較が必要",
}

PUBLIC_ROW_FIELDS = (
    "municipality_code",
    "municipality",
    "category_id",
    "category_label",
    "item_id",
    "item_label",
    "source_presentation_state",
    "public_state",
    "information_condition",
    "status_label",
    "accepted_source_ids",
    "evidence_date",
    "display_explanation",
    "source_scope_note",
    "scope_note",
    "value_rendering_rule",
    "next_confirmation",
    "claim_boundary",
)

PROHIBITED_PUBLIC_KEYS = {
    "measurement_result_ids",
    "detail_spec_id",
    "measurement_status",
    "upstream_status",
    "internal_path",
    "local_path",
}

PROHIBITED_PUBLIC_TEXT = (
    "measurement_result_ids",
    "detail_spec_id",
    "限定測定result",
    "internal/",
    "C:\\Users\\",
)

MEASURED_PUBLIC_EXPLANATION = (
    "受入済み原本の限定範囲で確認済みです。原本の粒度・範囲・非主張とともに示します。"
)
MEASURED_PUBLIC_RENDERING_RULE = (
    "確認済みであることだけを表示し、限定測定値は公開しません。原本範囲と非主張を併記します。"
)

PUBLIC_GLOBAL_BOUNDARIES = [
    "情報の不足と交通サービスの不足は別であり、このデータだけで交通の充足・不足を判定しない。",
    "4登録簿上の該当記載0件を、交通手段・移動支援・別制度の不存在へ変換しない。",
    "GTFSアクセス状態を交通の有無・質へ変換しない。",
    "GTFSフィード全体値を市町内供給量へ変換・配賦しない。",
    "JRバス中国の県外を含む広域値を関係4市へ配賦しない。",
    "予定値を実運行、現在利用可能性、需要充足へ変換しない。",
    "部分情報、追加入力必要、情報不足を0件・0%・不存在へ変換しない。",
    "需要比較必要を現在の需要値またはservice_gap判定へ変換しない。",
]

PROHIBITED_STATE_ASSERTIONS = (
    "公開値が県内交通全体を網羅し、需要を満たしている。",
    "実運行、現在利用可能性、市町内供給量、需要充足を測定済み。",
    "不足部分は0、存在しない、または確認済み。",
    "対象範囲は0件、0%、または交通が存在しない。",
    "情報対象または交通サービスが存在しない。",
    "現在の交通は足りている、または足りていない。",
)


def _load_json(relative_path: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def _file_record(relative_path: str) -> dict[str, Any]:
    payload = (REPO_ROOT / relative_path).read_bytes()
    return {
        "path": relative_path,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _public_description(source: dict[str, Any]) -> str:
    if source["presentation_state"] == "MEASURED_BOUNDED_INTERNAL":
        return MEASURED_PUBLIC_EXPLANATION
    return source["display_explanation"]


def _public_rendering_rule(source: dict[str, Any]) -> str:
    if source["presentation_state"] == "MEASURED_BOUNDED_INTERNAL":
        return MEASURED_PUBLIC_RENDERING_RULE
    return source["value_rendering_rule"]


def _public_claim_boundary(source: dict[str, Any]) -> str:
    boundary = source["claim_boundary"]
    matched = 0
    for assertion in PROHIBITED_STATE_ASSERTIONS:
        if assertion not in boundary:
            continue
        explicit_denial = f"「{assertion.removesuffix('。')}」とは主張しない。"
        boundary = boundary.replace(assertion, explicit_denial)
        matched += 1
    if matched != 1:
        raise ValueError("public claim boundary must negate exactly one state assertion")
    return boundary


def _build_row(source: dict[str, Any]) -> dict[str, Any]:
    source_state = source["presentation_state"]
    public_state = PUBLIC_STATE_MAP[source_state]
    row = {
        "municipality_code": source["municipality_code"],
        "municipality": source["municipality"],
        "category_id": source["category_id"],
        "category_label": source["category_label"],
        "item_id": source["item_id"],
        "item_label": source["item_label"],
        "source_presentation_state": source_state,
        "public_state": public_state,
        "information_condition": source["information_condition"],
        "status_label": STATUS_LABELS[public_state],
        "accepted_source_ids": source["accepted_source_ids"],
        "evidence_date": source["evidence_date"],
        "display_explanation": _public_description(source),
        "source_scope_note": source["source_scope_note"],
        "scope_note": source["scope_note"],
        "value_rendering_rule": _public_rendering_rule(source),
        "next_confirmation": source["next_confirmation"],
        "claim_boundary": _public_claim_boundary(source),
    }
    if tuple(row) != PUBLIC_ROW_FIELDS:
        raise AssertionError("public row field order drifted")
    serialized = json.dumps(row, ensure_ascii=False)
    for token in PROHIBITED_PUBLIC_TEXT:
        if token in serialized:
            raise ValueError(f"public row contains internal token: {token}")
    return row


def build_dataset() -> dict[str, Any]:
    presentation = _load_json(PRESENTATION_PATH)
    integration = _load_json(INTEGRATION_SPEC_PATH)

    if presentation["task_id"] != "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PRESENTATION-SPEC-1":
        raise ValueError("unexpected presentation specification task")
    if integration["task_id"] != "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PUBLIC-INTEGRATION-SPEC-1":
        raise ValueError("unexpected public integration specification task")
    if integration["spec_status"] != "DEFINED_NOT_IMPLEMENTED_PUBLICLY":
        raise ValueError("public integration specification status drifted")

    configured_map = {
        item["source_state"]: item["public_state"]
        for item in integration["public_state_mapping"]
    }
    if configured_map != PUBLIC_STATE_MAP:
        raise ValueError("public state mapping drifted from the accepted integration specification")
    if tuple(integration["public_data_contract"]["required_row_fields"]) != PUBLIC_ROW_FIELDS:
        raise ValueError("public row schema drifted from the accepted integration specification")
    if set(integration["public_data_contract"]["prohibited_row_fields"]) != PROHIBITED_PUBLIC_KEYS:
        raise ValueError("prohibited public fields drifted")

    rows = [
        _build_row(source)
        for source in presentation["municipality_item_presentation_specs"]
    ]
    if len(rows) != 665:
        raise ValueError("public dataset must contain exactly 665 rows")
    if len({(row["municipality_code"], row["item_id"]) for row in rows}) != 665:
        raise ValueError("public dataset contains duplicate municipality-item rows")
    if any(row["information_condition"] == "SERVICE_GAP" for row in rows):
        raise ValueError("public dataset cannot contain a service-gap decision")

    state_counts = Counter(row["source_presentation_state"] for row in rows)
    expected_counts = integration["state_counts"]
    if dict(state_counts) != expected_counts:
        raise ValueError("public dataset state counts drifted")

    state_vocabulary = []
    for source in presentation["presentation_state_vocabulary"]:
        public_state = PUBLIC_STATE_MAP[source["code"]]
        description = source["label"]
        if source["code"] == "MEASURED_BOUNDED_INTERNAL":
            description = (
                "受入済み原本の限定範囲で確認済み。実運行、現在利用可能性、"
                "市町内供給量、需要充足を確認済みとは扱わない。"
            )
        state_vocabulary.append(
            {
                "source_presentation_state": source["code"],
                "public_state": public_state,
                "information_condition": source["information_condition"],
                "status_label": STATUS_LABELS[public_state],
                "description": description,
            }
        )

    municipality_summaries = []
    for source in presentation["municipality_summaries"]:
        public_counts = {
            PUBLIC_STATE_MAP[state]: count
            for state, count in source["presentation_state_counts"].items()
        }
        municipality_summaries.append(
            {
                "municipality_code": source["municipality_code"],
                "municipality": source["municipality"],
                "item_count": source["item_count"],
                "public_state_counts": public_counts,
                "information_condition_counts": source["information_condition_counts"],
                "next_confirmation_count": source["next_confirmation_count"],
                "demand_comparator_count": source["demand_comparator_count"],
            }
        )

    categories = [
        {
            "category_id": source["category_id"],
            "category_label": source["category_label"],
            "item_count_per_municipality": source["item_count_per_municipality"],
        }
        for source in presentation["category_summaries"]
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "published_data_as_of": DATA_AS_OF,
        "generated_from": [
            _file_record(PRESENTATION_PATH),
            _file_record(INTEGRATION_SPEC_PATH),
        ],
        "dimensions": {
            "municipality_count": 19,
            "category_count": 8,
            "item_count_per_municipality": 35,
            "municipality_item_row_count": 665,
            "public_state_count": 6,
        },
        "state_vocabulary": state_vocabulary,
        "categories": categories,
        "municipality_summaries": municipality_summaries,
        "rows": rows,
        "global_boundaries": PUBLIC_GLOBAL_BOUNDARIES,
    }


def build_bytes() -> bytes:
    payload = (json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(payload) > MAXIMUM_BYTES:
        raise ValueError(f"public dataset exceeds {MAXIMUM_BYTES} bytes")
    return payload


def write_dataset(output_path: Path | None = None) -> Path:
    output = output_path or OUTPUT_PATH
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_bytes())
    return output


if __name__ == "__main__":
    write_dataset()
