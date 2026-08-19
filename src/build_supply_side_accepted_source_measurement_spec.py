"""Build the bounded measurement specification for 98 unmeasured coverage rows.

This stage inspects only the seven already accepted originals and accepted local
derivatives.  It records tables, columns, units, municipality applicability,
verification rules, and claim boundaries.  It does not calculate or publish a
measurement value and never allocates feed-wide values to municipalities.
"""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import inspect_gtfs_archives as gi


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "data" / "work1_supply_side_accepted_source_measurement_spec.json"

TASK_ID = "WORK1-SUPPLY-SIDE-ACCEPTED-SOURCE-MEASUREMENT-SPEC-1"
SCHEMA_VERSION = "WORK1-SUPPLY-SIDE-ACCEPTED-SOURCE-MEASUREMENT-SPEC-1"
SPEC_AS_OF = "2026-08-19"

MODEL_PATH = "data/work1_supply_side_information_model.json"
MATRIX_PATH = "data/work1_supply_side_information_coverage_matrix.json"
MANIFEST_PATH = "data/source_freshness_manifest.json"
OPERATORS_PATH = "data/operators.csv"
VEHICLES_PATH = "data/vehicles.csv"
METADATA_INPUT_PATHS = (
    MODEL_PATH,
    MATRIX_PATH,
    MANIFEST_PATH,
    OPERATORS_PATH,
    VEHICLES_PATH,
)

READY_FOR_BOUNDED_MEASUREMENT = "READY_FOR_BOUNDED_MEASUREMENT"
PARTIAL_SOURCE_ONLY = "PARTIAL_SOURCE_ONLY"
ADDITIONAL_INPUT_REQUIRED = "ADDITIONAL_INPUT_REQUIRED"
EXECUTION_STATUS = "SPECIFIED_NOT_EXECUTED"

REQUIRED_APPLICATION_FIELDS = (
    "municipality_code",
    "municipality",
    "category_id",
    "item_id",
    "measurement_spec_id",
    "accepted_source_ids",
    "source_locators",
    "measurement_outputs",
    "measurement_scope",
    "municipality_applicability",
    "execution_readiness",
    "execution_status",
    "verification_rules",
    "missing_value_rule",
    "claim_boundary",
)

GTFS_TABLE_ORDER = (
    "agency.txt",
    "routes.txt",
    "trips.txt",
    "stops.txt",
    "stop_times.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "frequencies.txt",
    "fare_attributes.txt",
    "fare_rules.txt",
    "transfers.txt",
    "shapes.txt",
    "feed_info.txt",
)


def _registry_requirement(table: str, columns: tuple[str, ...]) -> dict[str, Any]:
    return {
        "source_type": "registry_pdf",
        "table": table,
        "required": True,
        "required_columns": list(columns),
        "optional_columns": [],
    }


def _gtfs_requirement(
    table: str,
    columns: tuple[str, ...],
    *,
    required: bool = True,
    optional_columns: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "source_type": "gtfs_zip",
        "table": table,
        "required": required,
        "required_columns": list(columns),
        "optional_columns": list(optional_columns),
    }


COMMON_GAP_BOUNDARY = (
    "これは受入済み原本に記録された限定情報の測定仕様であり、実運行、現在利用可能性、"
    "利用実績、利便性、需要充足、service_gapを示さない。"
)

ITEM_SPEC_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "measurement_spec_id": "MS-01-REGISTERED-SERVICE-AREA",
        "item_id": "registered_service_area_detail",
        "measurement_outputs": [
            {"name": "service_area_raw", "unit": "原文文字列", "granularity": "登録記録"},
            {"name": "office_name_location", "unit": "事務所記録", "granularity": "登録記録内事務所"},
            {"name": "service_area_municipalities", "unit": "市町名リスト", "granularity": "登録記録"},
        ],
        "measurement_scope": "4登録簿のうち市町照合済み登録記録の運送区域・事務所記載",
        "source_requirements": [
            _registry_requirement(
                OPERATORS_PATH,
                (
                    "source_pdf", "source_page", "registration_no", "transport_type",
                    "service_area_raw", "service_area_municipalities", "office_name",
                    "office_location", "flags",
                ),
            )
        ],
        "derivation_steps": [
            "(source_pdf, registration_no)の複合キーで登録記録を識別する。",
            "service_area_municipalitiesの市町トークンで対象市町との既存対応を再確認する。",
            "service_area_rawは正規化値へ置換せず原文列として保持する。",
            "office_nameとoffice_locationはセミコロン順を保った対として扱う。",
        ],
        "municipality_applicability_rule": "登録記録のservice_area_municipalitiesに対象市町が含まれる場合だけ適用する。",
        "verification_rules": [
            "(source_pdf, registration_no)が一意でsource_pageが正の整数である。",
            "office_nameとoffice_locationの分割件数が一致する。",
            "原文区域と市町抽出結果を別フィールドのまま保持する。",
        ],
        "missing_value_rule": "空欄は未記載としてnull相当で保持し、区域なし・事務所なしへ変換しない。",
        "execution_readiness": READY_FOR_BOUNDED_MEASUREMENT,
        "readiness_reason": "受入済み登録簿派生列と原本ページ参照だけで限定測定を再現できる。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 登録区域は現在の実運行区域・予約受付区域を保証しない。",
    },
    {
        "measurement_spec_id": "MS-02-GTFS-ROUTE-IDENTITY",
        "item_id": "route_identity_and_name",
        "measurement_outputs": [
            {"name": "route_record", "unit": "GTFS route_id", "granularity": "受入フィード"},
            {"name": "trip_pattern_reference", "unit": "GTFS trip_id", "granularity": "受入フィード"},
        ],
        "measurement_scope": "受入GTFSフィード全体の路線・便識別子と名称",
        "source_requirements": [
            _gtfs_requirement("routes.txt", ("route_id", "agency_id", "route_short_name", "route_long_name", "route_desc", "route_type")),
            _gtfs_requirement("trips.txt", ("route_id", "service_id", "trip_id", "trip_headsign", "direction_id", "shape_id")),
        ],
        "derivation_steps": [
            "routes.txtをroute_idで一意化し名称・種別を保持する。",
            "trips.txtのroute_id参照を検証し、trip_id単位の系統参照を別表にする。",
        ],
        "municipality_applicability_rule": "municipality_gtfsで受入フィードとの関係が確認された市町へ、フィード全体参照としてだけ適用する。",
        "verification_rules": [
            "route_idとtrip_idに空欄・重複がない。",
            "trips.route_idがroutes.route_idへ全件参照解決する。",
        ],
        "missing_value_rule": "名称空欄は空欄のまま保持し、route_idから名称を推測しない。",
        "execution_readiness": READY_FOR_BOUNDED_MEASUREMENT,
        "readiness_reason": "3 GTFSすべてに必要表・列がある。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " route_id件数を現実の路線・系統本数へ読み替えない。",
    },
    {
        "measurement_spec_id": "MS-03-GTFS-STOP-LOCATION",
        "item_id": "stop_name_and_coordinates",
        "measurement_outputs": [
            {"name": "stop_record", "unit": "GTFS stop_id", "granularity": "受入フィード"},
        ],
        "measurement_scope": "受入GTFSフィード全体の乗降場所名・座標・のりば属性",
        "source_requirements": [
            _gtfs_requirement(
                "stops.txt",
                ("stop_id", "stop_name", "stop_lat", "stop_lon", "location_type"),
                optional_columns=("platform_code", "parent_station", "stop_code", "stop_desc"),
            )
        ],
        "derivation_steps": [
            "stop_id単位で名称・緯度・経度・location_typeを保持する。",
            "のりば・親子関係列は原本に存在する場合だけ付加する。",
        ],
        "municipality_applicability_rule": "関係フィード全体のstop記録として適用し、市町境界内記録とは呼ばない。",
        "verification_rules": [
            "stop_idが一意で空欄でない。",
            "緯度経度は数値・有効範囲を検証し、不正値を0へ補正しない。",
            "location_type空欄はGTFS既定値として扱う場合も原値を保持する。",
        ],
        "missing_value_rule": "座標・名称の欠損はnot_measured相当とし、0座標や名称推定を作らない。",
        "execution_readiness": READY_FOR_BOUNDED_MEASUREMENT,
        "readiness_reason": "3 GTFSすべてにstop_id・名称・座標列がある。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " stop_id数は物理的停留所数や市町内停留所数とは限らない。",
    },
    {
        "measurement_spec_id": "MS-04-GTFS-ROUTE-SHAPE",
        "item_id": "route_shape",
        "measurement_outputs": [
            {"name": "ordered_shape_points", "unit": "座標点列", "granularity": "GTFS shape_id"},
        ],
        "measurement_scope": "受入GTFSフィード全体のshape_id別経路点列",
        "source_requirements": [
            _gtfs_requirement("shapes.txt", ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence"), optional_columns=("shape_dist_traveled",)),
            _gtfs_requirement("trips.txt", ("trip_id", "route_id", "shape_id")),
        ],
        "derivation_steps": [
            "shape_idごとにshape_pt_sequenceを整数順で並べる。",
            "trips.shape_idとの参照を検証し、未参照shapeとshape欠損tripを別に記録する。",
        ],
        "municipality_applicability_rule": "関係フィード全体の形状参照としてだけ適用し、市町内区間へ切り分けない。",
        "verification_rules": [
            "shape_id内のsequenceが空欄・重複・逆順でない。",
            "緯度経度が数値・有効範囲内である。",
        ],
        "missing_value_rule": "shape欠損は直線補間や経路推測を行わずnot_measured相当とする。",
        "execution_readiness": READY_FOR_BOUNDED_MEASUREMENT,
        "readiness_reason": "3 GTFSすべてにshapes.txtとtrips.shape_idがある。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 経路形状は実走行軌跡・道路通行保証・市町内提供範囲を意味しない。",
    },
    {
        "measurement_spec_id": "MS-05-MUNICIPAL-GTFS-SPATIAL-COVERAGE",
        "item_id": "municipality_feed_spatial_coverage",
        "measurement_outputs": [
            {"name": "municipal_stop_and_shape_intersection", "unit": "市町境界内GTFS地物", "granularity": "市町×受入フィード"},
        ],
        "measurement_scope": "受入GTFS座標と受入済み市町境界を重ねた市町内範囲（境界入力は現在未受入）",
        "source_requirements": [
            _gtfs_requirement("stops.txt", ("stop_id", "stop_lat", "stop_lon", "location_type")),
            _gtfs_requirement("shapes.txt", ("shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence")),
            _gtfs_requirement("trips.txt", ("trip_id", "route_id", "shape_id")),
            _gtfs_requirement("routes.txt", ("route_id",)),
        ],
        "derivation_steps": [
            "GTFS側の座標・参照整合だけを先に検証する。",
            "市町境界データが別の人間承認で受入済みになるまで空間交差を実行しない。",
            "JRバス中国を含むフィード全体値を関係市へ比率配分しない。",
        ],
        "municipality_applicability_rule": "関係フィードは候補入力に限り、市町境界との交差結果が得られるまで市町内供給量を作らない。",
        "verification_rules": [
            "GTFS座標・shape参照を検証する。",
            "境界データの発行主体・基準日・ライセンス・座標参照系・SHA-256を受入前に確認する。",
            "境界上の点・線の包含規則を測定実装前に固定する。",
        ],
        "missing_value_rule": "境界入力なしは0%・0件ではなくadditional_input_requiredとする。",
        "execution_readiness": ADDITIONAL_INPUT_REQUIRED,
        "readiness_reason": "7原本には停留所・形状座標があるが、市町境界geometryは含まれない。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 現時点では市町内カバー率・面積・人口カバーを算出しない。",
    },
    {
        "measurement_spec_id": "MS-06-GTFS-SERVICE-CALENDAR",
        "item_id": "service_calendar",
        "measurement_outputs": [
            {"name": "active_service_by_date", "unit": "service_id集合", "granularity": "受入フィード×日付"},
            {"name": "feed_validity_period", "unit": "日付範囲", "granularity": "受入フィード"},
        ],
        "measurement_scope": "受入GTFSフィード全体の通常曜日・例外日・有効期間",
        "source_requirements": [
            _gtfs_requirement("calendar.txt", ("service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date")),
            _gtfs_requirement("calendar_dates.txt", ("service_id", "date", "exception_type")),
            _gtfs_requirement("feed_info.txt", ("feed_start_date", "feed_end_date")),
            _gtfs_requirement("trips.txt", ("service_id", "trip_id")),
        ],
        "derivation_steps": [
            "calendarの曜日フラグと期間から日付別service_id集合を作る。",
            "calendar_datesの追加・削除を日付別に適用する。",
            "feed_info期間とcalendar期間は別の意味のまま併記する。",
        ],
        "municipality_applicability_rule": "関係フィード全体の運行予定日参照としてだけ適用する。",
        "verification_rules": [
            "service_id参照、YYYYMMDD、曜日0/1、exception_type 1/2を検証する。",
            "開始日が終了日を超える行をinvalid_inputとする。",
        ],
        "missing_value_rule": "日付表不足・不正は非運行日や0便へ変換しない。",
        "execution_readiness": READY_FOR_BOUNDED_MEASUREMENT,
        "readiness_reason": "3 GTFSすべてにcalendar・calendar_dates・feed_info・tripsがある。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 運行予定日は実運行・運休・定時性を示さない。",
    },
    {
        "measurement_spec_id": "MS-07-GTFS-STOP-TIMETABLE",
        "item_id": "stop_level_timetable",
        "measurement_outputs": [
            {"name": "scheduled_stop_call", "unit": "発着予定レコード", "granularity": "受入フィード×日付×trip_id×stop_sequence"},
        ],
        "measurement_scope": "受入GTFSフィード全体の便・乗降場所別発着予定",
        "source_requirements": [
            _gtfs_requirement("stop_times.txt", ("trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence", "pickup_type", "drop_off_type", "timepoint")),
            _gtfs_requirement("trips.txt", ("trip_id", "route_id", "service_id", "trip_headsign", "direction_id")),
            _gtfs_requirement("stops.txt", ("stop_id", "stop_name")),
            _gtfs_requirement("routes.txt", ("route_id", "route_short_name", "route_long_name")),
            _gtfs_requirement("calendar.txt", ("service_id", "start_date", "end_date")),
            _gtfs_requirement("calendar_dates.txt", ("service_id", "date", "exception_type")),
        ],
        "derivation_steps": [
            "stop_timesをtrip_id・stop_sequence順に検証する。",
            "trips・routes・stops・日付別service_idへ参照結合する。",
            "24時以降を含むGTFS時刻を同一service dayの秒数として保持する。",
        ],
        "municipality_applicability_rule": "関係フィード全体の時刻表参照としてだけ適用し、市町内発着だけへ絞らない。",
        "verification_rules": [
            "trip_id・stop_id・route_id・service_idの参照が全件解決する。",
            "arrival/departure時刻とstop_sequenceがGTFS形式として有効である。",
        ],
        "missing_value_rule": "時刻・参照欠損は0時・0分・運休へ補正しない。",
        "execution_readiness": READY_FOR_BOUNDED_MEASUREMENT,
        "readiness_reason": "3 GTFSすべてに必要な予定時刻・参照表がある。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 発着予定は実発着・遅延・乗車可能性を示さない。",
    },
    {
        "measurement_spec_id": "MS-08-GTFS-TIME-BAND-FREQUENCY",
        "item_id": "time_band_frequency",
        "measurement_outputs": [
            {"name": "scheduled_departure_count", "unit": "予定発車回数", "granularity": "受入フィード×日付×route_id×stop_id×1時間帯"},
            {"name": "scheduled_first_last_departure", "unit": "GTFS時刻", "granularity": "受入フィード×日付×route_id×stop_id"},
        ],
        "measurement_scope": "受入GTFSフィード全体の予定発車時刻から得る時間帯別頻度",
        "source_requirements": [
            _gtfs_requirement("stop_times.txt", ("trip_id", "departure_time", "stop_id", "stop_sequence")),
            _gtfs_requirement("trips.txt", ("trip_id", "route_id", "service_id")),
            _gtfs_requirement("calendar.txt", ("service_id", "start_date", "end_date")),
            _gtfs_requirement("calendar_dates.txt", ("service_id", "date", "exception_type")),
        ],
        "derivation_steps": [
            "日付別に有効なtripを決定し、departure_timeをservice day内の時間帯へ割り当てる。",
            "1時間帯は00分00秒以上・次時00分00秒未満の左閉右開区間とする。",
            "始発・終発は同じ集計キー内の最小・最大予定発車時刻とする。",
        ],
        "municipality_applicability_rule": "関係フィード全体の予定頻度参照としてだけ適用し、市町供給量へ集計しない。",
        "verification_rules": [
            "時刻・参照・service dayをstop timetable仕様と同じ規則で検証する。",
            "異なる比較週・フィードを暗黙に合算しない。",
        ],
        "missing_value_rule": "有効tripを確定できない場合は0回でなくnot_calculableとする。",
        "execution_readiness": READY_FOR_BOUNDED_MEASUREMENT,
        "readiness_reason": "既存予定時刻と運行日表だけで限定した時間帯集計を定義できる。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 予定頻度・始終発は実運行、待ち時間保証、利便性を示さない。",
    },
    {
        "measurement_spec_id": "MS-09-GTFS-TRANSFER-TRAVEL-TIME",
        "item_id": "transfer_wait_and_travel_time",
        "measurement_outputs": [
            {"name": "scheduled_in_vehicle_segment_minutes", "unit": "予定分", "granularity": "受入フィード×trip_id×連続stop区間"},
            {"name": "declared_transfer_rule", "unit": "GTFS transfer行", "granularity": "受入フィード"},
        ],
        "measurement_scope": "同一trip内の予定区間時間と、原本に明記されたtransfer行だけ",
        "source_requirements": [
            _gtfs_requirement("stop_times.txt", ("trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence")),
            _gtfs_requirement("trips.txt", ("trip_id", "route_id", "service_id")),
            _gtfs_requirement("stops.txt", ("stop_id", "stop_name")),
            _gtfs_requirement("transfers.txt", ("from_stop_id", "to_stop_id", "transfer_type", "min_transfer_time"), required=False),
        ],
        "derivation_steps": [
            "同一tripの連続stop間で後続arrival_timeから先行departure_timeを引く。",
            "transfers.txtは存在する場合だけ原文規則を読み、0行・表なしを乗換不能へ変換しない。",
            "異なるtrip・フィード間の候補待ち時間や接続保証はこの仕様では作らない。",
        ],
        "municipality_applicability_rule": "関係フィード全体の限定情報としてだけ適用し、市町間移動時間へ配賦しない。",
        "verification_rules": [
            "連続stopの時刻差が負にならず、参照stop・tripが解決する。",
            "transfer表の任意性と0行を明示し、表なしを0件と同一視しない。",
        ],
        "missing_value_rule": "transfer表なし・0行は乗換0件ではなくdeclared_transfer_not_availableとする。",
        "execution_readiness": PARTIAL_SOURCE_ONLY,
        "readiness_reason": "同一trip内予定時間は測れるが、原本だけでは実所要時間・乗換待ち・接続保証を確定できない。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 予定区間時間と明示transferは実所要時間・乗換成功・接続保証を示さない。",
    },
    {
        "measurement_spec_id": "MS-10-WELFARE-ELIGIBILITY",
        "item_id": "welfare_eligibility_scope",
        "measurement_outputs": [
            {"name": "registered_welfare_scope_flags", "unit": "イ〜ト7区分の0/1", "granularity": "福祉有償運送登録記録"},
        ],
        "measurement_scope": "受入済み福祉有償運送登録簿に記載された旅客範囲区分",
        "source_requirements": [
            _registry_requirement(
                OPERATORS_PATH,
                (
                    "source_pdf", "source_page", "registration_no", "transport_type",
                    "service_area_municipalities", "scope_i_physical", "scope_ro_mental",
                    "scope_ha_intellectual", "scope_ni_care", "scope_ho_support",
                    "scope_he_checklist", "scope_to_other",
                ),
            )
        ],
        "derivation_steps": [
            "transport_typeが福祉有償運送の登録記録だけを対象にする。",
            "イ〜トを身体・精神・知的・要介護・要支援・基本チェックリスト・その他の固定対応で保持する。",
            "市町別にはservice_area_municipalitiesとの既存対応だけを使う。",
        ],
        "municipality_applicability_rule": "対象市町に対応する福祉有償運送登録記録がある場合だけ適用する。",
        "verification_rules": [
            "7フラグが0または1だけである。",
            "交通空白地有償運送の0フラグを福祉利用対象なしとして混在させない。",
        ],
        "missing_value_rule": "全0・空欄を無条件利用可や利用対象者なしへ変換しない。",
        "execution_readiness": READY_FOR_BOUNDED_MEASUREMENT,
        "readiness_reason": "受入済み福祉登録簿派生列と原本ページ参照で再現できる。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 登録上の旅客区分は現在の会員条件・個人の利用可否を決定しない。",
    },
    {
        "measurement_spec_id": "MS-11-GTFS-FARE",
        "item_id": "fare_and_payment",
        "measurement_outputs": [
            {"name": "gtfs_fare_attribute", "unit": "fare_id別金額・通貨・支払時点", "granularity": "受入フィード"},
            {"name": "gtfs_fare_rule", "unit": "fare_id適用規則", "granularity": "受入フィード"},
        ],
        "measurement_scope": "受入GTFSのfare_attributes・fare_rulesに明記された静的運賃情報",
        "source_requirements": [
            _gtfs_requirement("fare_attributes.txt", ("fare_id", "price", "currency_type", "payment_method", "transfers"), optional_columns=("transfer_duration", "agency_id")),
            _gtfs_requirement("fare_rules.txt", ("fare_id", "route_id", "origin_id", "destination_id"), optional_columns=("contains_id",)),
            _gtfs_requirement("routes.txt", ("route_id",)),
            _gtfs_requirement("stops.txt", ("stop_id", "zone_id")),
        ],
        "derivation_steps": [
            "fare_idでattributesとrulesを結合し、price・currency・payment_methodを原値保持する。",
            "route_id・origin_id・destination_idの適用範囲を解決可能な範囲だけ記録する。",
            "GTFS payment_methodを現金・IC・カード等の支払媒体へ読み替えない。",
        ],
        "municipality_applicability_rule": "関係フィード全体の運賃表参照としてだけ適用し、市町内運賃へ切り分けない。",
        "verification_rules": [
            "fare_id参照、非負price、通貨コード、payment_method列挙値を検証する。",
            "参照不能なroute・zoneを推測補完しない。",
        ],
        "missing_value_rule": "fare行なし・適用不明を無料・均一運賃・現金のみへ変換しない。",
        "execution_readiness": PARTIAL_SOURCE_ONLY,
        "readiness_reason": "静的GTFS運賃は測れるが、全運賃網羅性・割引・現在の支払媒体までは確認できない。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " GTFS運賃は実請求額・割引適用・支払媒体・全サービス運賃を保証しない。",
    },
    {
        "measurement_spec_id": "MS-12-ACCESSIBILITY",
        "item_id": "accessibility_features",
        "measurement_outputs": [
            {"name": "registered_vehicle_type_count", "unit": "登録台数", "granularity": "登録記録×事務所×車種"},
            {"name": "gtfs_wheelchair_code", "unit": "GTFS列挙値", "granularity": "受入フィード×trip_idまたはstop_id"},
        ],
        "measurement_scope": "4登録簿の登録車種とJRバス中国GTFSの車いす関連列に明記された部分情報",
        "source_requirements": [
            _registry_requirement(
                VEHICLES_PATH,
                (
                    "source_pdf", "source_page", "registration_no", "office_seq",
                    "office_name", "ownership", "vehicle_type", "vehicle_type_label",
                    "count", "count_kei",
                ),
            ),
            _gtfs_requirement("trips.txt", ("trip_id", "route_id", "wheelchair_accessible")),
            _gtfs_requirement("stops.txt", ("stop_id", "stop_name", "wheelchair_boarding")),
        ],
        "derivation_steps": [
            "登録簿は(source_pdf, registration_no)でoperatorsとvehiclesを結合し、対象市町・車種別登録台数を保持する。",
            "JRバス中国GTFSはtrip.wheelchair_accessibleとstop.wheelchair_boardingの原値・件数をフィード全体で保持する。",
            "登録車種とGTFS列を相互補完・統合スコア化しない。",
        ],
        "municipality_applicability_rule": "登録簿は市町対応登録行、JRバス中国は関係4市への広域フィード参照としてだけ適用する。",
        "verification_rules": [
            "登録車両のcount・count_keiが非負で、軽内数が総数を超えない。",
            "GTFS車いす列が許容列挙値で、trip_id・stop_idが一意参照できる。",
            "登録簿値とGTFS値を加算・比率化しない。",
        ],
        "missing_value_rule": "列なし・空欄・0を実利用不可または対応なしへ変換しない。",
        "execution_readiness": PARTIAL_SOURCE_ONLY,
        "readiness_reason": "登録車種・GTFS列は測れるが、現在の配車可能性、設備状態、介助条件を確認できない。",
        "claim_boundary": COMMON_GAP_BOUNDARY + " 登録車種・GTFSコードは実稼働車両、当日利用可能性、設備状態、介助提供を保証しない。",
    },
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


def _inspect_gtfs_tables(zip_path: Path) -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(zip_path) as archive:
        safety = gi.inspect_safety(archive)
        if not safety.ok:
            raise ValueError(f"GTFS ZIP safety check failed: {zip_path}")
        members = set(archive.namelist())
        for table in GTFS_TABLE_ORDER:
            if table not in members:
                tables[table] = {"present": False, "columns": [], "row_count": None}
                continue
            decoded = gi.decode_csv_bytes(archive.read(table))
            header, rows = gi.read_csv_rows(decoded.text)
            tables[table] = {
                "present": True,
                "columns": list(header),
                "row_count": len(rows),
            }
    return tables


def _build_source_profiles(
    model: dict[str, Any],
    manifest: dict[str, Any],
    operators_header: list[str],
    operator_rows: list[dict[str, str]],
    vehicles_header: list[str],
    vehicle_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    manifest_by_id = {item["source_id"]: item for item in manifest["sources"]}
    profiles: list[dict[str, Any]] = []
    for mapping in model["accepted_source_mapping"]:
        source_id = mapping["source_id"]
        source_manifest = manifest_by_id.get(source_id)
        if source_manifest is None:
            raise ValueError(f"accepted source missing from manifest: {source_id}")
        if mapping["local_path"] != source_manifest["local_path"]:
            raise ValueError(f"source path mismatch: {source_id}")
        sha256, size = _sha256_and_size(mapping["local_path"])
        if sha256 != source_manifest["baseline_sha256"] or size != source_manifest["baseline_bytes"]:
            raise ValueError(f"accepted source bytes or SHA-256 changed: {source_id}")
        profile: dict[str, Any] = {
            "source_id": source_id,
            "source_type": mapping["source_type"],
            "original_path": mapping["local_path"],
            "original_bytes": size,
            "original_sha256": sha256,
        }
        if mapping["source_type"] == "registry_pdf":
            filename = Path(mapping["local_path"]).name
            profile["original_locator"] = "source_pdfとsource_pageで受入PDFの登録ページへ戻る"
            profile["accepted_derivative_tables"] = {
                OPERATORS_PATH: {
                    "columns": operators_header,
                    "row_count_for_source": sum(row["source_pdf"] == filename for row in operator_rows),
                },
                VEHICLES_PATH: {
                    "columns": vehicles_header,
                    "row_count_for_source": sum(row["source_pdf"] == filename for row in vehicle_rows),
                },
            }
        elif mapping["source_type"] == "gtfs_zip":
            profile["inspection_mode"] = "zipfile_read_in_memory_without_extract"
            profile["tables"] = _inspect_gtfs_tables(_path(mapping["local_path"]))
        else:
            raise ValueError(f"unsupported accepted source type: {mapping['source_type']}")
        profiles.append(profile)
    if len(profiles) != 7:
        raise ValueError("exactly seven accepted source profiles are required")
    return profiles


def _build_locator(
    item_spec: dict[str, Any],
    source_profile: dict[str, Any],
    municipality: str,
) -> dict[str, Any]:
    source_type = source_profile["source_type"]
    requirements = [
        item for item in item_spec["source_requirements"]
        if item["source_type"] == source_type
    ]
    if not requirements:
        raise ValueError(
            f"{item_spec['item_id']} has no requirement for {source_profile['source_id']}"
        )
    located_tables: list[dict[str, Any]] = []
    if source_type == "registry_pdf":
        derivative_tables = source_profile["accepted_derivative_tables"]
        for requirement in requirements:
            table = requirement["table"]
            if table not in derivative_tables:
                raise ValueError(f"accepted derivative table is missing: {table}")
            available_columns = derivative_tables[table]["columns"]
            missing = set(requirement["required_columns"]) - set(available_columns)
            if missing:
                raise ValueError(f"{table} required columns missing: {sorted(missing)}")
            located_tables.append({
                "table": table,
                "required": True,
                "present": True,
                "columns": requirement["required_columns"],
            })
        if item_spec["item_id"] == "accessibility_features":
            row_selection = (
                f"vehicles.source_pdf={Path(source_profile['original_path']).name}; "
                "operatorsへ(source_pdf,registration_no)で結合し、"
                f"service_area_municipalitiesに{municipality}を含む登録記録"
            )
        else:
            row_selection = (
                f"source_pdf={Path(source_profile['original_path']).name}; "
                f"service_area_municipalitiesに{municipality}を含む登録記録"
            )
        locator_scope = "municipality_matched_registry_records"
    else:
        gtfs_tables = source_profile["tables"]
        for requirement in requirements:
            table = requirement["table"]
            available = gtfs_tables[table]
            if requirement["required"] and not available["present"]:
                raise ValueError(f"{source_profile['source_id']} required table missing: {table}")
            if available["present"]:
                missing = set(requirement["required_columns"]) - set(available["columns"])
                if missing:
                    raise ValueError(
                        f"{source_profile['source_id']} {table} columns missing: {sorted(missing)}"
                    )
                columns = list(requirement["required_columns"])
                columns.extend(
                    column for column in requirement["optional_columns"]
                    if column in available["columns"]
                )
            else:
                columns = []
            located_tables.append({
                "table": table,
                "required": requirement["required"],
                "present": available["present"],
                "columns": columns,
            })
        row_selection = "受入フィード全体。市町境界による行フィルターなし"
        locator_scope = "accepted_feed_whole_feed_reference"
    return {
        "source_id": source_profile["source_id"],
        "source_type": source_type,
        "original_path": source_profile["original_path"],
        "tables": located_tables,
        "row_selection": row_selection,
        "locator_scope": locator_scope,
    }


def _municipality_applicability(
    item_spec: dict[str, Any], source_locators: list[dict[str, Any]]
) -> str:
    scopes = {item["locator_scope"] for item in source_locators}
    statement = item_spec["municipality_applicability_rule"]
    if "accepted_feed_whole_feed_reference" in scopes:
        statement += " GTFSは関係根拠であり、市町内行への割当ではない。"
    if item_spec["execution_readiness"] == ADDITIONAL_INPUT_REQUIRED:
        statement += " 受入済み市町境界geometryがないため空間交差は未実行。"
    return statement


def _application_claim_boundary(
    item_spec: dict[str, Any], accepted_source_ids: list[str]
) -> str:
    boundary = item_spec["claim_boundary"]
    if "jrbus-chugoku-gtfs" in accepted_source_ids:
        boundary += " JRバス中国の県外を含む広域値を関係市へ配賦しない。"
    return boundary


def build_dataset() -> dict[str, Any]:
    model = _load_json(MODEL_PATH)
    matrix = _load_json(MATRIX_PATH)
    manifest = _load_json(MANIFEST_PATH)
    operators_header, operator_rows = _read_csv(OPERATORS_PATH)
    vehicles_header, vehicle_rows = _read_csv(VEHICLES_PATH)

    source_profiles = _build_source_profiles(
        model,
        manifest,
        operators_header,
        operator_rows,
        vehicles_header,
        vehicle_rows,
    )
    source_profile_by_id = {item["source_id"]: item for item in source_profiles}
    item_label_by_id = {
        item["item_id"]: item["label"]
        for category in model["categories"]
        for item in category["items"]
    }
    item_specs: list[dict[str, Any]] = []
    for definition in ITEM_SPEC_DEFINITIONS:
        item_id = definition["item_id"]
        if item_id not in item_label_by_id:
            raise ValueError(f"measurement item is missing from model: {item_id}")
        item_specs.append({
            "measurement_spec_id": definition["measurement_spec_id"],
            "item_id": item_id,
            "label": item_label_by_id[item_id],
            "measurement_outputs": definition["measurement_outputs"],
            "measurement_scope": definition["measurement_scope"],
            "source_requirements": definition["source_requirements"],
            "derivation_steps": definition["derivation_steps"],
            "municipality_applicability_rule": definition["municipality_applicability_rule"],
            "verification_rules": definition["verification_rules"],
            "missing_value_rule": definition["missing_value_rule"],
            "execution_readiness": definition["execution_readiness"],
            "readiness_reason": definition["readiness_reason"],
            "claim_boundary": definition["claim_boundary"],
        })
    item_spec_by_id = {item["item_id"]: item for item in item_specs}
    if len(item_specs) != 12 or len(item_spec_by_id) != 12:
        raise ValueError("measurement specification must define exactly 12 unique items")

    unmeasured_rows = [
        row for row in matrix["rows"]
        if row["current_status"] == "ACCEPTED_SOURCE_UNMEASURED"
    ]
    if len(unmeasured_rows) != 98:
        raise ValueError("upstream matrix must contain exactly 98 unmeasured rows")
    if set(row["item_id"] for row in unmeasured_rows) != set(item_spec_by_id):
        raise ValueError("item specifications do not cover the 98 upstream rows exactly")

    applications: list[dict[str, Any]] = []
    for matrix_row in unmeasured_rows:
        item_spec = item_spec_by_id[matrix_row["item_id"]]
        source_locators = [
            _build_locator(
                item_spec,
                source_profile_by_id[source_id],
                matrix_row["municipality"],
            )
            for source_id in matrix_row["accepted_source_ids"]
        ]
        application = {
            "municipality_code": matrix_row["municipality_code"],
            "municipality": matrix_row["municipality"],
            "category_id": matrix_row["category_id"],
            "item_id": matrix_row["item_id"],
            "measurement_spec_id": item_spec["measurement_spec_id"],
            "accepted_source_ids": matrix_row["accepted_source_ids"],
            "source_locators": source_locators,
            "measurement_outputs": item_spec["measurement_outputs"],
            "measurement_scope": item_spec["measurement_scope"],
            "municipality_applicability": _municipality_applicability(item_spec, source_locators),
            "execution_readiness": item_spec["execution_readiness"],
            "execution_status": EXECUTION_STATUS,
            "verification_rules": item_spec["verification_rules"],
            "missing_value_rule": item_spec["missing_value_rule"],
            "claim_boundary": _application_claim_boundary(
                item_spec, matrix_row["accepted_source_ids"]
            ),
        }
        if tuple(application) != REQUIRED_APPLICATION_FIELDS:
            raise AssertionError("measurement application field order drifted")
        applications.append(application)

    readiness_order = (
        READY_FOR_BOUNDED_MEASUREMENT,
        PARTIAL_SOURCE_ONLY,
        ADDITIONAL_INPUT_REQUIRED,
    )
    readiness_counts = {
        status: sum(item["execution_readiness"] == status for item in applications)
        for status in readiness_order
    }
    input_paths = list(METADATA_INPUT_PATHS)
    input_paths.extend(profile["original_path"] for profile in source_profiles)
    input_files = []
    for relative_path in input_paths:
        sha256, size = _sha256_and_size(relative_path)
        input_files.append({"path": relative_path, "bytes": size, "sha256": sha256})

    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "spec_as_of": SPEC_AS_OF,
        "execution_status": EXECUTION_STATUS,
        "dimensions": {
            "accepted_source_count": 7,
            "measurement_item_count": 12,
            "municipality_item_application_count": 98,
            "input_file_count": len(input_files),
        },
        "readiness_vocabulary": [
            {
                "code": READY_FOR_BOUNDED_MEASUREMENT,
                "meaning": "受入済み原本だけから、非主張境界付きの限定測定を実装できる。",
            },
            {
                "code": PARTIAL_SOURCE_ONLY,
                "meaning": "原本に部分情報はあるが、項目全体の利用条件・実態・完全性は測れない。",
            },
            {
                "code": ADDITIONAL_INPUT_REQUIRED,
                "meaning": "測定実行には7原本にない前提入力が必要。0や不存在へ変換しない。",
            },
        ],
        "readiness_counts": readiness_counts,
        "required_application_fields": list(REQUIRED_APPLICATION_FIELDS),
        "input_files": input_files,
        "accepted_source_profiles": source_profiles,
        "item_specifications": item_specs,
        "municipality_item_applications": applications,
        "global_boundaries": [
            "測定値はまだ生成・公開していない。",
            "登録0件、空欄、GTFS表なし・0行をサービス不存在へ変換しない。",
            "GTFSフィード全体値を市町内供給量へ変換しない。",
            "JRバス中国の県外を含む広域値を関係4市へ配賦しない。",
            "情報不足・測定不足からservice_gapを自動判定しない。",
            "新原本・認証付き情報・需要比較・外部連絡・公開表示はこの仕様に含めない。",
        ],
        "next_stage": {
            "task_id": "WORK1-SUPPLY-SIDE-ACCEPTED-SOURCE-BOUNDED-MEASUREMENT-1",
            "status": "DEFINED_NOT_STARTED",
            "goal": "READY_FOR_BOUNDED_MEASUREMENT 61行について、仕様どおりの内部測定値を決定的に生成する。",
            "boundary": "PARTIAL_SOURCE_ONLY 30行とADDITIONAL_INPUT_REQUIRED 7行は値へ補完せず、新原本・公開表示・service_gap判定を行わない。",
        },
    }


def render_dataset_json(dataset: dict[str, Any]) -> str:
    return json.dumps(dataset, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    OUTPUT_PATH.write_bytes(render_dataset_json(build_dataset()).encode("utf-8"))


if __name__ == "__main__":
    main()
