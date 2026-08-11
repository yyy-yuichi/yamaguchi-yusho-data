"""SUPPLY-METRIC-2: SPEC.md §15（SUPPLY-METRIC-1が定義した指標）を、岩国市・光市の
受入済みGTFS ZIP 2件から決定論的に計算する。

対象は次の2件だけ（SPEC.md §15.2 のローカル入力）。他17市町・船木鉄道・地図・
経路検索・比較週の一般選定アルゴリズム（SPEC.md §15.5 手順1〜7）はこの工程の対象外。
岩国市・光市の比較週は SPEC.md §15.5 が 2026-04-06〜2026-04-12 と既に確定しているため、
本モジュールはこの1週間だけを対象日として扱う。

- raw/gtfs/iwakuni_gtfsjp_20260401.zip
- raw/gtfs/hikari_gtfs_20260401.zip

ZIPは読み取り専用。`zipfile.ZipFile.read()` でメモリ上に読むだけで、`extract()` /
`extractall()` は呼ばない（既存の `inspect_gtfs_archives.py` と同じ方針）。
低レベルのCSVデコード・日付検証・列統計は `inspect_gtfs_archives.py`（GTFS-2で受入済み）
の関数を再利用し、同じロジックの重複実装を避ける。

## 実装上の判断（SPEC.mdの記載を推測で埋めた箇所。仕様そのものは変更していない）

- **`checked_at`** は SPEC.md §15.4.1 の表が指す元データ（`data/gtfs_feeds.csv`）の値
  （2026-08-09、公式ページ側の確認日）をそのまま使う。今回の指標計算そのものを実行した日は
  別に `metric_computed_at` フィールドとして追加した（§15.8は「最低限」の一覧であり、
  追加フィールドはこの一覧を上書きしない）。
- **`location_type` 列が丸ごと無い場合**、GTFS Schedule Reference の既定値（省略時は
  停留所/プラットフォームを意味する）に従い、全行を「空欄」として扱う（乗降場所として数える）。
  岩国市・光市の実ZIPはどちらも列が存在し全行`0`のため、この分岐は実データの値には影響しない。
- **`scheduled_trip_count_by_date`（§15.4.3）の「必須列が無い」「参照関係が不正」
  「同一主キーが重複する」は、その判定が生じた時点でその週7日すべてを`invalid_input`にする。**
  日付ごとの部分的な有効/無効ではなく、フィード全体のGTFS構造としての不整合だと判断した
  （§15.4.3本文が「両方が無い」を含め列挙する条件は、いずれも特定の1日に限定されない
  構造上の不備であるため）。`trips.txt`が丸ごと存在しない場合も同じ扱いとする
  （calendar.txt/calendar_dates.txtが両方無い場合と同じ性質の構造的欠落のため）。
- **`frequencies.txt`の`exact_times=1`行は、SPEC.md §15.4.3手順5「時刻範囲が正で割り切れる
  ことを検証し」のとおり、`(end_time - start_time)`が`headway_secs`で正確に割り切れる
  （余り0）場合だけを有効とする。**割り切れない場合は`scheduled_trip_count_by_date`を
  `invalid_input`にする（部分値・端数丸めの便数を出さない）。割り切れる場合は
  `(end_time - start_time) / headway_secs`便を数え、元のテンプレートtripを別に1便加算しない。
  岩国市・光市の実ZIPはどちらも`frequencies.txt`を持たないため、この分岐は実データの値には
  影響しない。
- **`scheduled_trip_count_by_date`の計算対象trip判定は、`trips.txt`の`route_id`が`routes.txt`の
  `route_id`集合に、`service_id`が`calendar.txt`∪`calendar_dates.txt`のservice_id集合に、
  それぞれ含まれることを要求する。**`routes.txt`が無い・`route_id`列が無い・空欄・重複が
  ある場合や、`trips.txt`の`route_id`/`service_id`が参照先に存在しない場合は
  `invalid_input`とする（SPEC.md §15.2・§15.4.3の「必須列」「参照関係」の要件）。
  `calendar_dates.txt`だけで定義されたservice_id（`calendar.txt`に対応する行が無いもの）は
  引き続き有効な参照先として扱う。`calendar.txt`の`start_date > end_date`となる行も
  `invalid_input`とする。
"""
from __future__ import annotations

import csv
import dataclasses
import json
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import inspect_gtfs_archives as gi

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

METRIC_VERSION = "SUPPLY-METRIC-1"

# このSUPPLY-METRIC-2実行日（計算そのものを行った日）。壁時計を読まず固定値にすることで
# `data/gtfs_supply_metrics.json` の再生成をバイト決定論的にする。
METRIC_COMPUTED_AT = "2026-08-10"

WEEKDAY_COLUMNS: Tuple[str, ...] = (
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)

# SPEC.md §15.5 が岩国市・光市2フィードについて確定した最初の比較週。
# 比較週の一般選定アルゴリズム（同§手順1〜7）の実装はSUPPLY-METRIC-2の対象外。
TARGET_WEEK_DATES: Tuple[date, ...] = tuple(
    date(2026, 4, 6) + timedelta(days=i) for i in range(7)
)

# SPEC.md §15.2 のローカル入力。対象はこの2フィードのみ。
FEED_IDS_IN_SCOPE: Tuple[str, ...] = ("iwakuni-gtfsjp", "hikari-gtfs")
FEED_ZIP_RELATIVE_PATHS: Dict[str, str] = {
    "iwakuni-gtfsjp": "raw/gtfs/iwakuni_gtfsjp_20260401.zip",
    "hikari-gtfs": "raw/gtfs/hikari_gtfs_20260401.zip",
}

_GTFS_TIME_RE = re.compile(r"^(\d{1,3}):([0-5]\d):([0-5]\d)$")
_POSITIVE_INT_RE = re.compile(r"^\d+$")


# ---------------------------------------------------------------------------
# 値オブジェクト
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class MetricValue:
    """SPEC.md §15.6 の `metric_status` を持つ1つの指標値。

    `metric_status != "measured"` のとき `value` は必ず `None`（0へ補正しない）。
    """

    value: Optional[int]
    metric_status: str
    reason: Optional[str]

    def to_json(self) -> dict:
        return {"value": self.value, "metric_status": self.metric_status, "reason": self.reason}


@dataclasses.dataclass(frozen=True)
class FileTable:
    present: bool
    decode_error: Optional[str]
    header: Optional[Tuple[str, ...]]
    rows: Optional[List[List[str]]]


@dataclasses.dataclass(frozen=True)
class FrequencyWindow:
    start_sec: int
    end_sec: int
    headway_secs: int
    exact_times: str  # "", "0", "1" のいずれか（検証済み）


@dataclasses.dataclass(frozen=True)
class TripCountContext:
    """§15.4.3の計算に必要な、検証済みの中間データ。"""

    calendar_rows: Tuple[Tuple[str, Dict[str, str], str, str], ...]
    calendar_dates_by_date: Dict[str, Tuple[Tuple[str, str], ...]]
    service_to_trip_ids: Dict[str, Tuple[str, ...]]
    freq_by_trip: Dict[str, Tuple[FrequencyWindow, ...]]


@dataclasses.dataclass(frozen=True)
class FeedMetricsResult:
    metric_version: str
    feed_id: str
    municipality_code: str
    municipality: str
    source_zip_path: Optional[str]
    source_zip_sha256: Optional[str]
    source_zip_size_bytes: Optional[int]
    scope_note: str
    official_reference_date: str
    checked_at: str
    metric_computed_at: str
    comparison_week_start: str
    comparison_week_end: str
    date_basis: dict
    metrics: Dict[str, MetricValue]
    scheduled_trip_count_by_date: Dict[str, MetricValue]

    def to_json(self) -> dict:
        return {
            "metric_version": self.metric_version,
            "feed_id": self.feed_id,
            "municipality_code": self.municipality_code,
            "municipality": self.municipality,
            "source_zip_path": self.source_zip_path,
            "source_zip_sha256": self.source_zip_sha256,
            "source_zip_size_bytes": self.source_zip_size_bytes,
            "scope_note": self.scope_note,
            "official_reference_date": self.official_reference_date,
            "checked_at": self.checked_at,
            "metric_computed_at": self.metric_computed_at,
            "comparison_week_start": self.comparison_week_start,
            "comparison_week_end": self.comparison_week_end,
            "date_basis": self.date_basis,
            "metrics": {k: v.to_json() for k, v in self.metrics.items()},
            "scheduled_trip_count_by_date": {
                k: v.to_json() for k, v in self.scheduled_trip_count_by_date.items()
            },
        }


# ---------------------------------------------------------------------------
# CSV読み込み（`inspect_gtfs_archives.py` の低レベル関数を再利用）
# ---------------------------------------------------------------------------


def read_table(zf: zipfile.ZipFile, name: str) -> FileTable:
    if name not in zf.namelist():
        return FileTable(present=False, decode_error=None, header=None, rows=None)
    raw = zf.read(name)
    try:
        decoded = gi.decode_csv_bytes(raw)
    except UnicodeDecodeError as exc:
        return FileTable(present=True, decode_error=str(exc), header=None, rows=None)
    header, rows = gi.read_csv_rows(decoded.text)
    return FileTable(present=True, decode_error=None, header=header, rows=rows)


# ---------------------------------------------------------------------------
# SPEC.md §15.4.2 — GTFS収録構造の件数
# ---------------------------------------------------------------------------


def compute_agency_record_count(table: FileTable) -> MetricValue:
    if not table.present:
        return MetricValue(None, "not_calculable", "agency.txtが存在しない")
    if table.decode_error:
        return MetricValue(None, "invalid_input", f"agency.txtの文字コードが不正: {table.decode_error}")
    return MetricValue(len(table.rows), "measured", None)


def compute_route_id_count(table: FileTable) -> MetricValue:
    if not table.present:
        return MetricValue(None, "not_calculable", "routes.txtが存在しない")
    if table.decode_error:
        return MetricValue(None, "invalid_input", f"routes.txtの文字コードが不正: {table.decode_error}")
    stats = gi.compute_id_stats(table.header, table.rows, "route_id")
    if stats.column is None:
        return MetricValue(None, "not_calculable", "routes.txtにroute_id列が無い")
    if stats.blank_count:
        return MetricValue(None, "invalid_input", f"routes.txtのroute_idが空欄の行が{stats.blank_count}件ある")
    if stats.duplicate_count:
        return MetricValue(None, "invalid_input", f"routes.txtのroute_idが重複する行が{stats.duplicate_count}件ある")
    return MetricValue(stats.unique_count, "measured", None)


def compute_boarding_location_id_count(table: FileTable) -> MetricValue:
    if not table.present:
        return MetricValue(None, "not_calculable", "stops.txtが存在しない")
    if table.decode_error:
        return MetricValue(None, "invalid_input", f"stops.txtの文字コードが不正: {table.decode_error}")
    stats = gi.compute_id_stats(table.header, table.rows, "stop_id")
    if stats.column is None:
        return MetricValue(None, "not_calculable", "stops.txtにstop_id列が無い")
    if stats.blank_count:
        return MetricValue(None, "invalid_input", f"stops.txtのstop_idが空欄の行が{stats.blank_count}件ある")
    if stats.duplicate_count:
        return MetricValue(None, "invalid_input", f"stops.txtのstop_idが重複する行が{stats.duplicate_count}件ある")
    id_idx = table.header.index("stop_id")
    if "location_type" in table.header:
        lt_idx = table.header.index("location_type")
        count = sum(
            1
            for row in table.rows
            if (row[id_idx] if id_idx < len(row) else "").strip() != ""
            and (row[lt_idx] if lt_idx < len(row) else "").strip() in ("", "0")
        )
    else:
        # location_type列が丸ごと無い場合はGTFS Schedule Referenceの既定値（空欄=乗降場所）に従う。
        # モジュールdocstring「実装上の判断」参照。
        count = stats.unique_count
    return MetricValue(count, "measured", None)


# ---------------------------------------------------------------------------
# SPEC.md §15.4.3 — 実日付別の予定運行便数
# ---------------------------------------------------------------------------


def parse_gtfs_time_to_seconds(value: str) -> Optional[int]:
    m = _GTFS_TIME_RE.match(value)
    if not m:
        return None
    hh, mm, ss = (int(x) for x in m.groups())
    return hh * 3600 + mm * 60 + ss


def parse_positive_int(value: str) -> Optional[int]:
    if not _POSITIVE_INT_RE.match(value):
        return None
    n = int(value)
    return n if n > 0 else None


def _prepare_trip_count_context(
    routes: FileTable,
    calendar: FileTable,
    calendar_dates: FileTable,
    trips: FileTable,
    frequencies: FileTable,
) -> Tuple[Optional[TripCountContext], Optional[str]]:
    """検証に成功すれば `(context, None)`、失敗すれば `(None, 理由)` を返す。"""

    # SPEC.md §15.2・§15.4.3: trips.txtのroute_idが参照する「有効なroutes.txtのroute_id集合」を
    # 先に確定する。routes.txt自体が無い・列が無い・空欄・重複がある場合は
    # route_idの参照先を確定できないため、trip数計算そのものをinvalid_inputにする。
    if not routes.present:
        return None, "routes.txtが存在しない"
    if routes.decode_error:
        return None, f"routes.txtの文字コードが不正: {routes.decode_error}"
    if "route_id" not in routes.header:
        return None, "routes.txtにroute_id列が無い"
    route_stats = gi.compute_id_stats(routes.header, routes.rows, "route_id")
    if route_stats.blank_count:
        return None, f"routes.txtのroute_idが空欄の行が{route_stats.blank_count}件ある"
    if route_stats.duplicate_count:
        return None, f"routes.txtのroute_idが重複する行が{route_stats.duplicate_count}件ある"
    route_id_idx = routes.header.index("route_id")
    valid_route_ids = {row[route_id_idx] for row in routes.rows if route_id_idx < len(row)}

    if not calendar.present and not calendar_dates.present:
        return None, "calendar.txtとcalendar_dates.txtが両方とも存在しない"

    calendar_service_ids: set = set()

    calendar_rows: List[Tuple[str, Dict[str, str], str, str]] = []
    if calendar.present:
        if calendar.decode_error:
            return None, f"calendar.txtの文字コードが不正: {calendar.decode_error}"
        required = ("service_id",) + WEEKDAY_COLUMNS + ("start_date", "end_date")
        missing = [c for c in required if c not in calendar.header]
        if missing:
            return None, f"calendar.txtに必須列が無い: {','.join(missing)}"
        sid_idx = calendar.header.index("service_id")
        start_idx = calendar.header.index("start_date")
        end_idx = calendar.header.index("end_date")
        wd_idx = {d: calendar.header.index(d) for d in WEEKDAY_COLUMNS}
        seen_sid: set = set()
        for i, row in enumerate(calendar.rows):
            sid = row[sid_idx] if sid_idx < len(row) else ""
            if sid.strip() == "":
                return None, f"calendar.txt {i}行目のservice_idが空欄"
            if sid in seen_sid:
                return None, f"calendar.txtのservice_id '{sid}' が重複している"
            seen_sid.add(sid)
            start = row[start_idx] if start_idx < len(row) else ""
            end = row[end_idx] if end_idx < len(row) else ""
            if not gi.is_valid_gtfs_date(start) or not gi.is_valid_gtfs_date(end):
                return None, (
                    f"calendar.txtのservice_id '{sid}' の日付が不正 "
                    f"(start_date={start!r}, end_date={end!r})"
                )
            if start > end:
                return None, (
                    f"calendar.txtのservice_id '{sid}' の日付範囲が不正 "
                    f"(start_date={start!r} > end_date={end!r})"
                )
            flags: Dict[str, str] = {}
            for d in WEEKDAY_COLUMNS:
                v = row[wd_idx[d]] if wd_idx[d] < len(row) else ""
                if v not in ("0", "1"):
                    return None, f"calendar.txtのservice_id '{sid}' の{d}列の値が不正: {v!r}"
                flags[d] = v
            calendar_rows.append((sid, flags, start, end))
            calendar_service_ids.add(sid)

    calendar_dates_by_date: Dict[str, List[Tuple[str, str]]] = {}
    if calendar_dates.present:
        if calendar_dates.decode_error:
            return None, f"calendar_dates.txtの文字コードが不正: {calendar_dates.decode_error}"
        required = ("service_id", "date", "exception_type")
        missing = [c for c in required if c not in calendar_dates.header]
        if missing:
            return None, f"calendar_dates.txtに必須列が無い: {','.join(missing)}"
        sid_idx = calendar_dates.header.index("service_id")
        date_idx = calendar_dates.header.index("date")
        exc_idx = calendar_dates.header.index("exception_type")
        seen_key: set = set()
        for i, row in enumerate(calendar_dates.rows):
            sid = row[sid_idx] if sid_idx < len(row) else ""
            dt = row[date_idx] if date_idx < len(row) else ""
            exc = row[exc_idx] if exc_idx < len(row) else ""
            if sid.strip() == "":
                return None, f"calendar_dates.txt {i}行目のservice_idが空欄"
            if not gi.is_valid_gtfs_date(dt):
                return None, f"calendar_dates.txtの日付が不正: {dt!r}"
            if exc not in ("1", "2"):
                return None, f"calendar_dates.txtのexception_typeが不正: {exc!r}"
            key = (sid, dt)
            if key in seen_key:
                return None, f"calendar_dates.txtの(service_id, date)が重複: {key}"
            seen_key.add(key)
            calendar_dates_by_date.setdefault(dt, []).append((sid, exc))
            calendar_service_ids.add(sid)

    if not trips.present:
        return None, "trips.txtが存在しない"
    if trips.decode_error:
        return None, f"trips.txtの文字コードが不正: {trips.decode_error}"
    missing = [c for c in ("route_id", "service_id", "trip_id") if c not in trips.header]
    if missing:
        return None, f"trips.txtに必須列が無い: {','.join(missing)}"
    rid_idx = trips.header.index("route_id")
    sid_idx = trips.header.index("service_id")
    tid_idx = trips.header.index("trip_id")
    seen_trip: set = set()
    service_to_trip_ids: Dict[str, List[str]] = {}
    for i, row in enumerate(trips.rows):
        tid = row[tid_idx] if tid_idx < len(row) else ""
        sid = row[sid_idx] if sid_idx < len(row) else ""
        rid = row[rid_idx] if rid_idx < len(row) else ""
        if tid.strip() == "":
            return None, f"trips.txt {i}行目のtrip_idが空欄"
        if tid in seen_trip:
            return None, f"trips.txtのtrip_id '{tid}' が重複している"
        if sid.strip() == "":
            return None, f"trips.txtのtrip_id '{tid}' のservice_idが空欄"
        if rid.strip() == "":
            return None, f"trips.txtのtrip_id '{tid}' のroute_idが空欄"
        if rid not in valid_route_ids:
            return None, f"trips.txtのtrip_id '{tid}' のroute_id '{rid}' がroutes.txtに存在しない"
        if sid not in calendar_service_ids:
            return None, (
                f"trips.txtのtrip_id '{tid}' のservice_id '{sid}' が"
                "calendar.txt/calendar_dates.txtのいずれにも存在しない"
            )
        seen_trip.add(tid)
        service_to_trip_ids.setdefault(sid, []).append(tid)

    freq_by_trip: Dict[str, List[FrequencyWindow]] = {}
    if frequencies.present:
        if frequencies.decode_error:
            return None, f"frequencies.txtの文字コードが不正: {frequencies.decode_error}"
        required = ("trip_id", "start_time", "end_time", "headway_secs")
        missing = [c for c in required if c not in frequencies.header]
        if missing:
            return None, f"frequencies.txtに必須列が無い: {','.join(missing)}"
        tid_idx2 = frequencies.header.index("trip_id")
        start_idx2 = frequencies.header.index("start_time")
        end_idx2 = frequencies.header.index("end_time")
        hw_idx2 = frequencies.header.index("headway_secs")
        exact_idx2 = frequencies.header.index("exact_times") if "exact_times" in frequencies.header else None
        seen_freq_key: set = set()
        for row in frequencies.rows:
            tid = row[tid_idx2] if tid_idx2 < len(row) else ""
            if tid not in seen_trip:
                return None, f"frequencies.txtのtrip_id '{tid}' がtrips.txtに存在しない"
            start_raw = row[start_idx2] if start_idx2 < len(row) else ""
            end_raw = row[end_idx2] if end_idx2 < len(row) else ""
            hw_raw = row[hw_idx2] if hw_idx2 < len(row) else ""
            start_sec = parse_gtfs_time_to_seconds(start_raw)
            end_sec = parse_gtfs_time_to_seconds(end_raw)
            headway = parse_positive_int(hw_raw)
            if start_sec is None or end_sec is None:
                return None, (
                    f"frequencies.txtのtrip_id '{tid}' の時刻表記が不正 "
                    f"(start_time={start_raw!r}, end_time={end_raw!r})"
                )
            if headway is None:
                return None, f"frequencies.txtのtrip_id '{tid}' のheadway_secsが不正: {hw_raw!r}"
            if end_sec <= start_sec:
                return None, (
                    f"frequencies.txtのtrip_id '{tid}' の時刻範囲が正でない "
                    f"(start_time={start_raw!r}, end_time={end_raw!r})"
                )
            exact = row[exact_idx2] if (exact_idx2 is not None and exact_idx2 < len(row)) else ""
            if exact not in ("", "0", "1"):
                return None, f"frequencies.txtのtrip_id '{tid}' のexact_timesが不正: {exact!r}"
            if exact == "1" and (end_sec - start_sec) % headway != 0:
                return None, (
                    f"frequencies.txtのtrip_id '{tid}' はexact_times=1だが時刻範囲が"
                    f"headway_secsで割り切れない (start_time={start_raw!r}, end_time={end_raw!r}, "
                    f"headway_secs={hw_raw!r})"
                )
            key = (tid, start_raw)
            if key in seen_freq_key:
                return None, f"frequencies.txtの(trip_id, start_time)が重複: {key}"
            seen_freq_key.add(key)
            freq_by_trip.setdefault(tid, []).append(
                FrequencyWindow(start_sec, end_sec, headway, exact)
            )

    context = TripCountContext(
        calendar_rows=tuple(calendar_rows),
        calendar_dates_by_date={k: tuple(v) for k, v in calendar_dates_by_date.items()},
        service_to_trip_ids={k: tuple(v) for k, v in service_to_trip_ids.items()},
        freq_by_trip={k: tuple(v) for k, v in freq_by_trip.items()},
    )
    return context, None


def compute_scheduled_trip_count_for_date(context: TripCountContext, target_date: date) -> MetricValue:
    dstr = target_date.strftime("%Y%m%d")
    weekday_name = WEEKDAY_COLUMNS[target_date.weekday()]

    valid: set = set()
    for sid, flags, start, end in context.calendar_rows:
        if start <= dstr <= end and flags[weekday_name] == "1":
            valid.add(sid)
    for sid, exc in context.calendar_dates_by_date.get(dstr, ()):
        if exc == "1":
            valid.add(sid)
        else:
            valid.discard(sid)

    valid_trip_ids: List[str] = []
    for sid in valid:
        valid_trip_ids.extend(context.service_to_trip_ids.get(sid, ()))

    not_exact = False
    total = 0
    for tid in valid_trip_ids:
        windows = context.freq_by_trip.get(tid)
        if not windows:
            total += 1
            continue
        if any(w.exact_times in ("", "0") for w in windows):
            not_exact = True
            continue
        for w in windows:
            # exact_times=1のwindowは_prepare_trip_count_context()で
            # (end_sec - start_sec) % headway_secs == 0 を検証済み（SPEC.md §15.4.3手順5）。
            total += (w.end_sec - w.start_sec) // w.headway_secs

    if not_exact:
        return MetricValue(
            None,
            "not_exact_frequency_based",
            "有効tripにexact_times=0または空欄の定間隔運行が含まれ、正確な発車回数が時刻表に固定されない",
        )
    return MetricValue(total, "measured", None)


# ---------------------------------------------------------------------------
# フィード単位の集約
# ---------------------------------------------------------------------------


def _build_date_basis(zf: zipfile.ZipFile) -> dict:
    """SPEC.md §15.8「feed_info、calendar、calendar_datesの日付根拠を分離した値」。

    既存の `inspect_gtfs_archives.py`（GTFS-2で受入済み）の関数をそのまま呼び、
    ここで独自に再パースしない。
    """
    feed_info = gi.inspect_feed_info(zf)
    calendar = gi.inspect_calendar(zf)
    calendar_dates = gi.inspect_calendar_dates(zf)
    return {
        "feed_info": {
            "present": feed_info.present,
            "feed_start_date": feed_info.feed_start_date,
            "feed_end_date": feed_info.feed_end_date,
        },
        "calendar": {
            "present": calendar.present,
            "min_start_date": calendar.min_start_date,
            "max_end_date": calendar.max_end_date,
            "service_id_unique_count": calendar.service_id_unique_count,
        },
        "calendar_dates": {
            "present": calendar_dates.present,
            "added_date_min": calendar_dates.added_date_min,
            "added_date_max": calendar_dates.added_date_max,
            "removed_date_min": calendar_dates.removed_date_min,
            "removed_date_max": calendar_dates.removed_date_max,
            "service_id_unique_count": calendar_dates.service_id_unique_count,
        },
    }


def compute_feed_metrics_from_zipfile(
    zf: zipfile.ZipFile,
    *,
    feed_id: str,
    municipality_code: str,
    municipality: str,
    official_reference_date: str,
    checked_at: str,
    scope_note: str,
    metric_computed_at: str = METRIC_COMPUTED_AT,
    week_dates: Sequence[date] = TARGET_WEEK_DATES,
) -> FeedMetricsResult:
    safety = gi.inspect_safety(zf)
    if not safety.ok:
        raise ValueError(f"安全検査に失敗したZIPは計算対象にしない: {safety.failures}")

    agency = read_table(zf, "agency.txt")
    routes = read_table(zf, "routes.txt")
    stops = read_table(zf, "stops.txt")
    calendar = read_table(zf, "calendar.txt")
    calendar_dates = read_table(zf, "calendar_dates.txt")
    trips = read_table(zf, "trips.txt")
    frequencies = read_table(zf, "frequencies.txt")

    metrics = {
        "gtfs_agency_record_count": compute_agency_record_count(agency),
        "gtfs_route_id_count": compute_route_id_count(routes),
        "gtfs_boarding_location_id_count": compute_boarding_location_id_count(stops),
    }

    context, reason = _prepare_trip_count_context(routes, calendar, calendar_dates, trips, frequencies)
    trip_counts: Dict[str, MetricValue] = {}
    for d in week_dates:
        if context is None:
            trip_counts[d.isoformat()] = MetricValue(None, "invalid_input", reason)
        else:
            trip_counts[d.isoformat()] = compute_scheduled_trip_count_for_date(context, d)

    return FeedMetricsResult(
        metric_version=METRIC_VERSION,
        feed_id=feed_id,
        municipality_code=municipality_code,
        municipality=municipality,
        source_zip_path=None,
        source_zip_sha256=None,
        source_zip_size_bytes=None,
        scope_note=scope_note,
        official_reference_date=official_reference_date,
        checked_at=checked_at,
        metric_computed_at=metric_computed_at,
        comparison_week_start=week_dates[0].isoformat(),
        comparison_week_end=week_dates[-1].isoformat(),
        date_basis=_build_date_basis(zf),
        metrics=metrics,
        scheduled_trip_count_by_date=trip_counts,
    )


def compute_feed_metrics(zip_path: str, **kwargs) -> FeedMetricsResult:
    """リポジトリ内に保存済みのZIPファイルを検査する（`raw/gtfs/*.zip`用）。"""
    file_sha256, file_size = gi.sha256_of_file(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        result = compute_feed_metrics_from_zipfile(zf, **kwargs)
    return dataclasses.replace(
        result, source_zip_path=zip_path, source_zip_sha256=file_sha256, source_zip_size_bytes=file_size
    )


# ---------------------------------------------------------------------------
# データセット組み立てとJSON出力
# ---------------------------------------------------------------------------


def _load_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def build_dataset() -> List[dict]:
    """SPEC.md §15.2 対象2フィード分のレコードを、`FEED_IDS_IN_SCOPE` の順に組み立てる。"""
    feed_rows = {r["feed_id"]: r for r in _load_csv_rows(DATA_DIR / "gtfs_feeds.csv")}
    municipality_rows = _load_csv_rows(DATA_DIR / "municipality_gtfs.csv")

    records: List[dict] = []
    for feed_id in FEED_IDS_IN_SCOPE:
        feed_row = feed_rows[feed_id]
        municipality_row = next(
            r for r in municipality_rows if feed_id in r["feed_ids"].split(";")
        )
        rel_path = FEED_ZIP_RELATIVE_PATHS[feed_id]
        zip_path = REPO_ROOT.joinpath(*rel_path.split("/"))
        scope_note = (
            f"{feed_row['scope_note']} {municipality_row['scope_note']} "
            "この値は当該市町に関連付けて確認したフィード全体の収録値であり、"
            "市町内だけの値・市町の全公共交通の値ではない（SPEC.md §15.3）。"
        )
        result = compute_feed_metrics(
            str(zip_path),
            feed_id=feed_id,
            municipality_code=municipality_row["municipality_code"],
            municipality=municipality_row["municipality"],
            official_reference_date=feed_row["official_reference_date"],
            checked_at=feed_row["checked_at"],
            scope_note=scope_note,
        )
        # `compute_feed_metrics()` に渡した絶対パスではなく、環境非依存でリポジトリ相対の
        # POSIX形式パスをJSONへ記録する（バイト決定論的にするため）。
        result = dataclasses.replace(result, source_zip_path=rel_path)
        records.append(result.to_json())
    return records


def render_dataset_json(records: List[dict]) -> str:
    return json.dumps(records, ensure_ascii=False, indent=2) + "\n"


def main() -> None:
    records = build_dataset()
    out_path = DATA_DIR / "gtfs_supply_metrics.json"
    # `write_text()` はWindows既定でテキストモードの改行変換（\n→\r\n）が入り、
    # OSによって出力バイト列が変わってしまう。この出力は「再生成してバイト一致」を
    # テストで確認する決定論的な成果物なので、改行変換のない`write_bytes()`でLFのまま書く。
    out_path.write_bytes(render_dataset_json(records).encode("utf-8"))


if __name__ == "__main__":
    main()
