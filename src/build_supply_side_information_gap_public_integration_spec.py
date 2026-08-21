from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK_ID = "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PUBLIC-INTEGRATION-SPEC-1"
SCHEMA_VERSION = f"{TASK_ID}-SCHEMA-1"
SPEC_AS_OF = "2026-08-21"

INPUT_PATHS = (
    "data/work1_supply_side_information_gap_presentation_spec.json",
    "evidence/20260820_work1_supply_side_information_gap_internal_prototype_local_acceptance.json",
    "evidence/20260821_work1_supply_side_information_gap_internal_prototype_human_review.json",
    "docs/index.html",
    "docs/entry.html",
    "docs/municipality-memo.html",
    "docs/status.html",
    "docs/data/municipal_supply.json",
    "docs/data/municipality_gtfs.json",
    "docs/data/gtfs_feeds.json",
    "docs/data/gtfs_supply_metrics.json",
)

IMPLEMENTATION_TARGET_PATH = "docs/municipality-memo.html"
IMPLEMENTATION_TARGET_BASELINE = {
    "path": IMPLEMENTATION_TARGET_PATH,
    "bytes": 44032,
    "sha256": "024f4ba8d3f8fc437621093690f25340fe0bda2aae8e07990973e2f379aea1a0",
}

PUBLIC_STATE_MAP = {
    "PUBLICLY_VISIBLE_CURRENT": "CURRENTLY_VISIBLE_INFORMATION",
    "MEASURED_BOUNDED_INTERNAL": "ACCEPTED_SOURCE_MEASURED_BOUNDED",
    "MEASUREMENT_GAP_PARTIAL_SOURCE": "MEASUREMENT_GAP_PARTIAL_SOURCE",
    "MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED": "MEASUREMENT_GAP_ADDITIONAL_INPUT_REQUIRED",
    "INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED": "INFORMATION_GAP_ADDITIONAL_SOURCE_REQUIRED",
    "DEMAND_COMPARATOR_REQUIRED": "DEMAND_COMPARATOR_REQUIRED",
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

PROHIBITED_PUBLIC_FIELDS = (
    "measurement_result_ids",
    "detail_spec_id",
    "measurement_status",
    "upstream_status",
    "internal_path",
    "local_path",
)


def load_json(relative_path: str):
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def file_record(relative_path: str) -> dict:
    if relative_path == IMPLEMENTATION_TARGET_PATH:
        # This accepted specification records the page before its authorized
        # implementation. Keep that historical baseline stable after the page
        # itself changes in the succeeding implementation stage.
        return dict(IMPLEMENTATION_TARGET_BASELINE)
    payload = (ROOT / relative_path).read_bytes()
    return {
        "path": relative_path,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def state_counts(presentation: dict) -> dict:
    counts = Counter(
        row["presentation_state"]
        for row in presentation["municipality_item_presentation_specs"]
    )
    return {state: counts[state] for state in PUBLIC_STATE_MAP}


def build_dataset() -> dict:
    presentation = load_json(INPUT_PATHS[0])
    prototype_acceptance = load_json(INPUT_PATHS[1])
    human_review = load_json(INPUT_PATHS[2])

    if presentation["dimensions"]["municipality_item_row_count"] != 665:
        raise ValueError("presentation spec must contain 665 municipality-item rows")
    if prototype_acceptance["decision"] != "LOCAL_GO":
        raise ValueError("local prototype acceptance must be LOCAL_GO")
    if human_review["decision"]["code"] != "GO_TO_PUBLIC_INTEGRATION_SPEC":
        raise ValueError("creator review did not authorize the public integration spec")
    if human_review["decision"]["public_page_mutation_authorized"]:
        raise ValueError("human review must not be converted into public page mutation approval")

    counts = state_counts(presentation)
    information_counts = presentation["information_condition_counts"]

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "spec_as_of": SPEC_AS_OF,
        "spec_status": "DEFINED_NOT_IMPLEMENTED_PUBLICLY",
        "input_files": [file_record(path) for path in INPUT_PATHS],
        "creator_review_gate": {
            "review_task_id": human_review["task_id"],
            "reviewed_on": human_review["reviewed_on"],
            "decision": human_review["decision"]["code"],
            "reported_blocking_issue_count": human_review["decision"]["reported_blocking_issue_count"],
            "reported_revision_request_count": human_review["decision"]["reported_revision_request_count"],
            "formal_user_test": human_review["validation_boundary"]["formal_user_test"],
            "user_value_validation": human_review["validation_boundary"]["user_value_validation"],
        },
        "dimensions": {
            "municipality_count": 19,
            "category_count": 8,
            "item_count_per_municipality": 35,
            "municipality_item_row_count": 665,
            "source_state_count": 6,
            "public_state_count": 6,
            "existing_public_page_count": 4,
            "public_page_change_count": 1,
            "new_public_data_file_count": 1,
        },
        "state_counts": counts,
        "information_condition_counts": information_counts,
        "public_state_mapping": [
            {
                "source_state": source_state,
                "public_state": public_state,
                "row_count": counts[source_state],
                "meaning_changed": False,
            }
            for source_state, public_state in PUBLIC_STATE_MAP.items()
        ],
        "integration_target": {
            "page": "docs/municipality-memo.html",
            "reason": "市町選択、公開情報の事実・不足・次の確認を協議前にそろえる既存ページであり、内部プロトタイプの利用目的と一致する。",
            "placement": "既存の『1. いま確認できる範囲』の直後",
            "section_heading": "2. 確認できる情報と、次に必要な確認",
            "reuse_existing_municipality_selector": True,
            "default_filter": "NEXT_CONFIRMATION",
            "filter_order": [
                "NEXT_CONFIRMATION",
                "CONFIRMED_INFORMATION",
                "DEMAND_COMPARISON",
                "ALL_ITEMS",
            ],
            "summary_order": [
                "NEXT_CONFIRMATION",
                "CONFIRMED_INFORMATION",
                "DEMAND_COMPARISON",
            ],
            "renumber_following_sections": True,
            "preserve_existing_registry_gtfs_metrics_unknowns_checklist_handoff_limits": True,
            "new_fifth_public_page": False,
        },
        "unchanged_public_pages": [
            "docs/index.html",
            "docs/entry.html",
            "docs/status.html",
        ],
        "public_data_contract": {
            "output_path": "docs/data/work1_supply_side_information_gap.json",
            "direct_source": "data/work1_supply_side_information_gap_presentation_spec.json",
            "deterministic_generation": "UTF-8, LF, sort_keys=false, indent=2, one trailing newline",
            "required_top_level_fields": [
                "schema_version",
                "generated_from",
                "dimensions",
                "state_vocabulary",
                "municipality_summaries",
                "rows",
                "global_boundaries",
            ],
            "required_row_fields": list(PUBLIC_ROW_FIELDS),
            "prohibited_row_fields": list(PROHIBITED_PUBLIC_FIELDS),
            "row_count": 665,
            "source_state_preserved_for_traceability": True,
            "measurement_values_copied": False,
            "measurement_result_ids_published": False,
            "detail_spec_ids_published": False,
            "local_or_internal_paths_published": False,
            "maximum_uncompressed_bytes": 1500000,
        },
        "screen_contract": {
            "required_boundary_notice": "情報の不足と交通サービスの不足は別です。この画面だけで交通が足りないとは判定しません。",
            "registered_zero_notice": "4登録簿上の該当記載0件は、交通手段や移動支援の不存在を意味しません。",
            "summary_card_count": 3,
            "filter_count": 4,
            "state_legend_count": 6,
            "category_count": 8,
            "evidence_detail_fields": [
                "accepted_source_ids",
                "evidence_date",
                "source_scope_note",
                "scope_note",
                "next_confirmation",
                "claim_boundary",
            ],
            "measured_internal_label_replaced_before_publication": True,
            "no_javascript_fallback": "公開JSONへのリンクと、この節以外の既存確認メモを利用可能にする。",
        },
        "interaction_and_accessibility": {
            "municipality_change_updates_existing_memo_and_new_section_together": True,
            "filter_buttons_use_aria_pressed": True,
            "result_count_uses_aria_live": True,
            "state_not_conveyed_by_color_alone": True,
            "keyboard_focus_visible": True,
            "minimum_filter_target_height_px": 42,
            "desktop_horizontal_overflow": False,
            "smartphone_390_horizontal_overflow": False,
            "print_contract": "選択市町の表示中filterだけを印刷し、証拠detailsは閉じた状態でも状態名・次の確認・境界が読める。",
        },
        "compatibility_contract": {
            "existing_query_parameter": "municipality",
            "existing_share_url_behavior_preserved": True,
            "existing_print_button_behavior_preserved": True,
            "existing_four_page_navigation_preserved": True,
            "existing_source_urls_preserved": True,
            "existing_public_values_changed": False,
            "existing_registered_supply_gtfs_and_metric_rendering_changed": False,
        },
        "claim_boundaries": {
            "registered_zero_as_transport_absence": False,
            "gtfs_access_status_as_transport_presence_or_quality": False,
            "feed_wide_values_as_municipality_supply": False,
            "jrbus_wide_values_allocated_to_four_municipalities": False,
            "scheduled_values_as_actual_operation": False,
            "information_or_measurement_gap_as_service_gap": False,
            "demand_comparator_as_current_demand_measurement": False,
            "creator_review_as_formal_user_test": False,
            "external_suggestion_as_measurement_or_validation": False,
        },
        "scope_direction": {
            "current_main_line": "公開情報から地域ごとの交通供給について確認できること・不足していることを協議前にそろえる。",
            "future_comparator_reference": [
                "移動を必要とする人との比較",
                "定員・車種・運転手・時間を含む輸送能力",
                "停留所や集合場所までの到達条件",
            ],
            "not_integrated_now": [
                "災害予測",
                "避難開始判断",
                "車両配車",
                "リアルタイムAI",
            ],
        },
        "implementation_change_allowlist": [
            "src/build_supply_side_information_gap_public_data.py",
            "docs/data/work1_supply_side_information_gap.json",
            "docs/municipality-memo.html",
            "tests/test_supply_side_information_gap_public_integration.py",
            "evidence/20260821_work1_supply_side_information_gap_public_integration_local_acceptance.json",
            "SPEC.md",
            "run_record.md",
            "PROGRESS.md",
            "verification.md",
        ],
        "implementation_prohibitions": [
            "新原本の探索・取得・採用",
            "需要比較値の作成",
            "認証付き・非公開データへのアクセス",
            "外部連絡または利用者テスト依頼",
            "災害予測・避難判断・配車機能の追加",
            "UDC応募またはBODIK登録",
            "pushまたはPages更新",
        ],
        "implementation_acceptance_conditions": [
            "公開JSONが19市町×35項目=665行、6状態、8分類を保持する。",
            "同じ入力から公開JSONを完全byte一致で再生成できる。",
            "協議前メモの既存市町selectと4 filterが同じ市町を表示する。",
            "情報不足と交通サービス不足、登録0件、GTFS全体値、JRバス広域値の境界を表示する。",
            "内部測定ID、内部path、限定測定値を公開JSONへ出さない。",
            "既存登録供給・GTFS・測定指標・共有URL・印刷の動作を維持する。",
            "PC 1280×720とsmartphone 390×844で横overflow 0を読戻す。",
            "専用・全体テスト、scope checker、git diff --checkを成功させる。",
            "index.html、entry.html、status.html、既存docs/dataを開始HEADから不変にする。",
            "push・Pages更新を行わずローカル受入で停止する。",
        ],
        "approval_gates": {
            "public_page_mutation": {
                "status": "HUMAN_APPROVAL_REQUIRED",
                "reason": "§49.9で公開ページ変更は作成者レビューと分離した別承認ゲートである。",
            },
            "push_and_pages_update": {
                "status": "SEPARATE_HUMAN_APPROVAL_REQUIRED",
                "reason": "ローカル公開実装受入後も、外部公開は別承認とする。",
            },
        },
        "next_stage": {
            "task_id": "WORK1-SUPPLY-SIDE-INFORMATION-GAP-PUBLIC-INTEGRATION-1",
            "status": "DEFINED_NOT_STARTED",
            "start_condition": "creator explicitly approves public page mutation after reviewing this specification",
        },
    }


def write_dataset(output_path: Path | None = None) -> Path:
    output = output_path or ROOT / "data" / "work1_supply_side_information_gap_public_integration_spec.json"
    payload = json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n"
    output.write_text(payload, encoding="utf-8", newline="\n")
    return output


if __name__ == "__main__":
    write_dataset()
