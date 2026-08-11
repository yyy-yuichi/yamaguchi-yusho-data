"""GTFS ZIP アーカイブの安全検査と構造実測（SPEC.md §14.5, §14.6）。

標準ライブラリのみを使う（`pdfplumber` はI-1側の依存であり、ここでは使わない）。
ZIP を作業ディレクトリへ展開せず、`zipfile.ZipFile` でメンバーをメモリ上に
読み込んで検査・集計する。`extract()` / `extractall()` は一切呼ばない。

この工程は構造と候補値の実測であり、GTFS仕様への完全適合を認証するものではない
（SPEC.md §14.6 末尾）。`feed_info` の期間・`calendar` の範囲・`calendar_dates` の
追加日/削除日は、ここで一つの「内部運行期間」へ統合しない。
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import re
import stat
import unicodedata
import zipfile
from datetime import date
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

# --- SPEC.md §14.5 の閾値 ---
MAX_MEMBER_COUNT = 200
MAX_MEMBER_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

# SPEC.md §14.6-2 が名指しする5ファイル。
CORE_FILES: Tuple[str, ...] = (
    "agency.txt",
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
)

# GTFS Schedule Reference（https://gtfs.org/documentation/schedule/reference/、
# SPEC.md §14.2で2026-08-10確認・同ページ表示は2026-04-27改訂）が定める単一列の主キー。
PRIMARY_ID_COLUMN: Dict[str, str] = {
    "agency.txt": "agency_id",
    "stops.txt": "stop_id",
    "routes.txt": "route_id",
    "trips.txt": "trip_id",
}

# stop_times.txt は同じReferenceが Primary key (trip_id, stop_sequence) と明記する複合主キー
# を持つ（単一列ではない）。単一列扱いへ推測で寄せず、複合キーとして別に扱う。
COMPOSITE_PRIMARY_ID_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "stop_times.txt": ("trip_id", "stop_sequence"),
}

_GTFS_DATE_RE = re.compile(r"^[0-9]{8}$")


# ---------------------------------------------------------------------------
# データ構造
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class MemberRecord:
    name: str
    compress_size: int
    file_size: int
    crc32: int


@dataclasses.dataclass(frozen=True)
class SafetyFailure:
    check: str
    detail: str


@dataclasses.dataclass(frozen=True)
class SafetyReport:
    ok: bool
    failures: Tuple[SafetyFailure, ...]
    members: Tuple[MemberRecord, ...]


@dataclasses.dataclass(frozen=True)
class DateIssue:
    row_index: int
    column: str
    raw_value: str


@dataclasses.dataclass(frozen=True)
class IdColumnStats:
    column: Optional[str]
    blank_count: Optional[int]
    unique_count: Optional[int]
    duplicate_count: Optional[int]


@dataclasses.dataclass(frozen=True)
class CoreFileStats:
    name: str
    present: bool
    decode_error: Optional[str] = None
    had_bom: Optional[bool] = None
    header: Optional[Tuple[str, ...]] = None
    row_count: Optional[int] = None
    id_stats: Optional[IdColumnStats] = None


@dataclasses.dataclass(frozen=True)
class LocationTypeStats:
    counts: Dict[str, int]


# calendar.txt の曜日フラグ列名（GTFS Schedule Reference）。
WEEKDAY_COLUMNS: Tuple[str, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


@dataclasses.dataclass(frozen=True)
class WeekdayFlagStats:
    """曜日ごとの生の値別件数。列が無い曜日は`None`のまま「未測定」とする。

    0/1以外の値は黙って補正・除外せず、その値のまま`counts`に数え、
    合計を`invalid_count`にも記録する。
    """

    counts: Dict[str, Optional[Dict[str, int]]]
    invalid_count: int


def compute_weekday_flag_stats(
    header: Tuple[str, ...], data_rows: List[List[str]]
) -> WeekdayFlagStats:
    counts: Dict[str, Optional[Dict[str, int]]] = {}
    invalid_count = 0
    for day in WEEKDAY_COLUMNS:
        if day not in header:
            counts[day] = None
            continue
        idx = header.index(day)
        day_counts: Dict[str, int] = {}
        for row in data_rows:
            v = row[idx] if idx < len(row) else ""
            day_counts[v] = day_counts.get(v, 0) + 1
            if v not in ("0", "1"):
                invalid_count += 1
        counts[day] = day_counts
    return WeekdayFlagStats(counts=counts, invalid_count=invalid_count)


@dataclasses.dataclass(frozen=True)
class CalendarStats:
    present: bool
    decode_error: Optional[str] = None
    header: Optional[Tuple[str, ...]] = None
    row_count: Optional[int] = None
    service_id_unique_count: Optional[int] = None
    service_ids: Optional[FrozenSet[str]] = None
    min_start_date: Optional[str] = None
    max_end_date: Optional[str] = None
    invalid_dates: Tuple[DateIssue, ...] = ()
    weekday: Optional[WeekdayFlagStats] = None


@dataclasses.dataclass(frozen=True)
class CalendarDatesStats:
    present: bool
    decode_error: Optional[str] = None
    header: Optional[Tuple[str, ...]] = None
    row_count: Optional[int] = None
    service_id_unique_count: Optional[int] = None
    service_ids: Optional[FrozenSet[str]] = None
    exception_type_counts: Optional[Dict[str, int]] = None
    added_date_min: Optional[str] = None
    added_date_max: Optional[str] = None
    removed_date_min: Optional[str] = None
    removed_date_max: Optional[str] = None
    invalid_dates: Tuple[DateIssue, ...] = ()


@dataclasses.dataclass(frozen=True)
class FeedInfoStats:
    present: bool
    decode_error: Optional[str] = None
    header: Optional[Tuple[str, ...]] = None
    row_count: Optional[int] = None
    feed_start_date: Optional[str] = None
    feed_end_date: Optional[str] = None
    feed_version: Optional[str] = None
    invalid_dates: Tuple[DateIssue, ...] = ()


@dataclasses.dataclass(frozen=True)
class ServiceIdCrossCheck:
    trips_service_ids: Optional[FrozenSet[str]]
    calendar_union_service_ids: Optional[FrozenSet[str]]
    trips_only: Optional[FrozenSet[str]]
    calendar_union_only: Optional[FrozenSet[str]]


@dataclasses.dataclass(frozen=True)
class InspectionResult:
    source_label: str
    file_sha256: Optional[str]
    file_size: Optional[int]
    safety: SafetyReport
    core_files: Dict[str, CoreFileStats] = dataclasses.field(default_factory=dict)
    stops_location_type: Optional[LocationTypeStats] = None
    calendar: Optional[CalendarStats] = None
    calendar_dates: Optional[CalendarDatesStats] = None
    feed_info: Optional[FeedInfoStats] = None
    service_id_cross_check: Optional[ServiceIdCrossCheck] = None


# ---------------------------------------------------------------------------
# 安全検査（SPEC.md §14.5）
# ---------------------------------------------------------------------------


def check_member_name(name: str) -> Optional[str]:
    """絶対パス・ドライブ名・".."・バックスラッシュ・NUL・ディレクトリ階層を検出する。

    zipfile はメンバー名の区切りを常に "/" で保持する（OSに関わらず）ため、
    "/" を含むかどうかでディレクトリ階層の有無を判定できる。
    """
    if not name:
        return "空のメンバー名"
    if "\x00" in name:
        return "メンバー名にNULを含む"
    if "\\" in name:
        return "メンバー名にバックスラッシュを含む"
    if name.startswith("/"):
        return "メンバー名が絶対パス"
    if re.match(r"^[A-Za-z]:", name):
        return "メンバー名にドライブ名を含む"
    parts = name.split("/")
    if ".." in parts:
        return "メンバー名に'..'を含む"
    if len(parts) > 1:
        return "メンバー名がディレクトリ階層を含む"
    return None


def find_case_insensitive_duplicates(names: Sequence[str]) -> List[Tuple[str, str]]:
    """Unicode正規化（NFKC）・大文字小文字を無視して重複するメンバー名の組を返す。

    NFKCはこのリポジトリの`tools/spec_coverage.py`が全角/半角比較に使っている
    正規化形式と揃えた。
    """
    seen: Dict[str, str] = {}
    dups: List[Tuple[str, str]] = []
    for n in names:
        key = unicodedata.normalize("NFKC", n).casefold()
        if key in seen:
            dups.append((seen[key], n))
        else:
            seen[key] = n
    return dups


def check_special_entry(zi: zipfile.ZipInfo) -> Optional[str]:
    """暗号化・シンボリックリンク・通常ファイル以外（ディレクトリ含む）を検出する。

    unixモードのファイル種別ビット（`stat.S_IFMT`）が0（種別情報なし）の場合は
    通常ファイルとみなす。DOS/Windows由来のZIP（本プロジェクトの岩国市ZIPを含む）や、
    `zipfile.writestr(name, data)`の既定動作はパーミッションのみを設定し種別ビットを
    立てないため、これを一律で「通常ファイル以外」と誤検出しない。
    """
    if zi.is_dir():
        return "ディレクトリエントリ"
    if zi.flag_bits & 0x1:
        return "暗号化されたメンバー"
    mode = (zi.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK:
        return "シンボリックリンク"
    if file_type not in (0, stat.S_IFREG):
        return f"通常ファイルではないunixモード（{oct(mode)}）"
    return None


@dataclasses.dataclass(frozen=True)
class MemberSizeInfo:
    name: str
    file_size: int
    compress_size: int


def check_member_count_limit(count: int) -> Optional[SafetyFailure]:
    if count > MAX_MEMBER_COUNT:
        return SafetyFailure("member_count", f"メンバー数{count}件 > 上限{MAX_MEMBER_COUNT}件")
    return None


def check_size_and_ratio_limits(sizes: Sequence[MemberSizeInfo]) -> List[SafetyFailure]:
    """個別サイズ・合計サイズ・圧縮比の境界を検査する（サイズ情報だけで判定できる純関数）。

    実ZIPからも、テスト用の軽量な合成サイズ一覧からも同じロジックで検査できるように
    `zipfile.ZipInfo` に依存しない形で切り出した。
    """
    failures: List[SafetyFailure] = []
    total_uncompressed = 0
    for m in sizes:
        total_uncompressed += m.file_size
        if m.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
            failures.append(
                SafetyFailure(
                    "member_size",
                    f"{m.name!r}: 非圧縮{m.file_size}バイト > 上限{MAX_MEMBER_UNCOMPRESSED_BYTES}バイト",
                )
            )
        if m.file_size > 0:
            ratio = m.file_size / m.compress_size if m.compress_size > 0 else float("inf")
            if ratio > MAX_COMPRESSION_RATIO:
                failures.append(
                    SafetyFailure(
                        "compression_ratio",
                        f"{m.name!r}: 圧縮比{ratio} > 上限{MAX_COMPRESSION_RATIO}",
                    )
                )
    if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
        failures.append(
            SafetyFailure(
                "total_size",
                f"全メンバー合計{total_uncompressed}バイト > 上限{MAX_TOTAL_UNCOMPRESSED_BYTES}バイト",
            )
        )
    return failures


def inspect_safety(zf: zipfile.ZipFile) -> SafetyReport:
    """SPEC.md §14.5 の全項目を検査する。該当が1件でもあれば `ok=False`。"""
    infos = zf.infolist()
    failures: List[SafetyFailure] = []

    count_failure = check_member_count_limit(len(infos))
    if count_failure:
        failures.append(count_failure)

    names = [zi.filename for zi in infos]
    for a, b in find_case_insensitive_duplicates(names):
        failures.append(
            SafetyFailure(
                "duplicate_name",
                f"{a!r} と {b!r} が正規化後に同一名になる",
            )
        )

    skip_read = set()
    for zi in infos:
        bad_name = check_member_name(zi.filename)
        if bad_name:
            failures.append(SafetyFailure("member_name", f"{zi.filename!r}: {bad_name}"))
            skip_read.add(id(zi))
        special = check_special_entry(zi)
        if special:
            failures.append(SafetyFailure("member_type", f"{zi.filename!r}: {special}"))
            skip_read.add(id(zi))

    sizes = [MemberSizeInfo(zi.filename, zi.file_size, zi.compress_size) for zi in infos]
    failures.extend(check_size_and_ratio_limits(sizes))

    # CRC検査。zf.read()は常にメモリ上での復号のみで、ディスクへの展開は行わない。
    # 既に名前・種別で失敗が確定したメンバーは、その理由と重複するため読み直さない。
    for zi in infos:
        if id(zi) in skip_read:
            continue
        try:
            zf.read(zi)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            failures.append(SafetyFailure("crc_or_read", f"{zi.filename!r}: {exc}"))

    members = tuple(
        MemberRecord(zi.filename, zi.compress_size, zi.file_size, zi.CRC) for zi in infos
    )
    return SafetyReport(ok=not failures, failures=tuple(failures), members=members)


# ---------------------------------------------------------------------------
# CSV復号（SPEC.md §14.5 末尾）
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class DecodedText:
    text: str
    had_bom: bool


def decode_csv_bytes(data: bytes) -> DecodedText:
    """`utf-8-sig`相当で厳格に復号する。UTF-8として読めない場合は例外を送出し、

    Shift_JIS等へフォールバックしない（SPEC.md §14.5末尾）。BOMの有無は呼び出し側で
    証拠へ記録する。
    """
    if data.startswith(b"\xef\xbb\xbf"):
        return DecodedText(text=data[3:].decode("utf-8"), had_bom=True)
    return DecodedText(text=data.decode("utf-8"), had_bom=False)


def read_csv_rows(text: str) -> Tuple[Tuple[str, ...], List[List[str]]]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return tuple(), []
    return tuple(rows[0]), rows[1:]


def is_valid_gtfs_date(value: str) -> bool:
    """8桁`YYYYMMDD`かつ実在日付かを検証する（SPEC.md §14.6-8）。補正はしない。"""
    if not value or not _GTFS_DATE_RE.match(value):
        return False
    try:
        date(int(value[0:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# 内容集計（SPEC.md §14.6）
# ---------------------------------------------------------------------------


def compute_id_stats(
    header: Tuple[str, ...], data_rows: List[List[str]], column: str
) -> IdColumnStats:
    if column not in header:
        return IdColumnStats(column=None, blank_count=None, unique_count=None, duplicate_count=None)
    idx = header.index(column)
    values = [row[idx] if idx < len(row) else "" for row in data_rows]
    blank = sum(1 for v in values if v.strip() == "")
    nonblank = [v for v in values if v.strip() != ""]
    unique = len(set(nonblank))
    duplicate = len(nonblank) - unique
    return IdColumnStats(column=column, blank_count=blank, unique_count=unique, duplicate_count=duplicate)


def compute_composite_id_stats(
    header: Tuple[str, ...], data_rows: List[List[str]], columns: Tuple[str, ...]
) -> IdColumnStats:
    """複合主キー（例: stop_times.txtの(trip_id, stop_sequence)）を明示的に扱う。

    列がいずれか欠けている場合は列不足として補わず未測定（全項目None）を返す。
    行のいずれかの構成列が空欄なら、その行は空欄として`blank_count`に数え、
    一意数・重複数の対象から外す。重複数は初出以降の行数（初出は数えない）。
    """
    if any(c not in header for c in columns):
        return IdColumnStats(column=None, blank_count=None, unique_count=None, duplicate_count=None)
    idxs = [header.index(c) for c in columns]
    label = "+".join(columns)
    blank = 0
    seen: set = set()
    duplicate = 0
    for row in data_rows:
        values = tuple(row[i] if i < len(row) else "" for i in idxs)
        if any(v.strip() == "" for v in values):
            blank += 1
            continue
        if values in seen:
            duplicate += 1
        else:
            seen.add(values)
    return IdColumnStats(column=label, blank_count=blank, unique_count=len(seen), duplicate_count=duplicate)


def inspect_core_file(zf: zipfile.ZipFile, name: str) -> CoreFileStats:
    if name not in zf.namelist():
        return CoreFileStats(name=name, present=False)
    raw = zf.read(name)
    try:
        decoded = decode_csv_bytes(raw)
    except UnicodeDecodeError as exc:
        return CoreFileStats(name=name, present=True, decode_error=str(exc))
    header, data_rows = read_csv_rows(decoded.text)
    id_stats = None
    column = PRIMARY_ID_COLUMN.get(name)
    if column is not None:
        id_stats = compute_id_stats(header, data_rows, column)
    else:
        composite_columns = COMPOSITE_PRIMARY_ID_COLUMNS.get(name)
        if composite_columns is not None:
            id_stats = compute_composite_id_stats(header, data_rows, composite_columns)
    return CoreFileStats(
        name=name,
        present=True,
        had_bom=decoded.had_bom,
        header=header,
        row_count=len(data_rows),
        id_stats=id_stats,
    )


def inspect_stops_location_type(zf: zipfile.ZipFile) -> Optional[LocationTypeStats]:
    if "stops.txt" not in zf.namelist():
        return None
    raw = zf.read("stops.txt")
    try:
        decoded = decode_csv_bytes(raw)
    except UnicodeDecodeError:
        return None
    header, data_rows = read_csv_rows(decoded.text)
    if "location_type" not in header:
        return LocationTypeStats(counts={})
    idx = header.index("location_type")
    counts: Dict[str, int] = {}
    for row in data_rows:
        v = row[idx] if idx < len(row) else ""
        counts[v] = counts.get(v, 0) + 1
    return LocationTypeStats(counts=counts)


def inspect_calendar(zf: zipfile.ZipFile) -> CalendarStats:
    if "calendar.txt" not in zf.namelist():
        return CalendarStats(present=False)
    raw = zf.read("calendar.txt")
    try:
        decoded = decode_csv_bytes(raw)
    except UnicodeDecodeError as exc:
        return CalendarStats(present=True, decode_error=str(exc))
    header, data_rows = read_csv_rows(decoded.text)
    sid_idx = header.index("service_id") if "service_id" in header else None
    start_idx = header.index("start_date") if "start_date" in header else None
    end_idx = header.index("end_date") if "end_date" in header else None

    service_ids: set = set()
    invalid_dates: List[DateIssue] = []
    valid_starts: List[str] = []
    valid_ends: List[str] = []
    for i, row in enumerate(data_rows):
        if sid_idx is not None and sid_idx < len(row):
            service_ids.add(row[sid_idx])
        if start_idx is not None:
            v = row[start_idx] if start_idx < len(row) else ""
            if is_valid_gtfs_date(v):
                valid_starts.append(v)
            else:
                invalid_dates.append(DateIssue(i, "start_date", v))
        if end_idx is not None:
            v = row[end_idx] if end_idx < len(row) else ""
            if is_valid_gtfs_date(v):
                valid_ends.append(v)
            else:
                invalid_dates.append(DateIssue(i, "end_date", v))

    return CalendarStats(
        present=True,
        header=header,
        row_count=len(data_rows),
        service_id_unique_count=len(service_ids),
        service_ids=frozenset(service_ids),
        min_start_date=min(valid_starts) if valid_starts else None,
        max_end_date=max(valid_ends) if valid_ends else None,
        invalid_dates=tuple(invalid_dates),
        weekday=compute_weekday_flag_stats(header, data_rows),
    )


def inspect_calendar_dates(zf: zipfile.ZipFile) -> CalendarDatesStats:
    if "calendar_dates.txt" not in zf.namelist():
        return CalendarDatesStats(present=False)
    raw = zf.read("calendar_dates.txt")
    try:
        decoded = decode_csv_bytes(raw)
    except UnicodeDecodeError as exc:
        return CalendarDatesStats(present=True, decode_error=str(exc))
    header, data_rows = read_csv_rows(decoded.text)
    sid_idx = header.index("service_id") if "service_id" in header else None
    date_idx = header.index("date") if "date" in header else None
    exc_idx = header.index("exception_type") if "exception_type" in header else None

    service_ids: set = set()
    exception_counts: Dict[str, int] = {}
    invalid_dates: List[DateIssue] = []
    added_dates: List[str] = []
    removed_dates: List[str] = []
    for i, row in enumerate(data_rows):
        if sid_idx is not None and sid_idx < len(row):
            service_ids.add(row[sid_idx])
        exc_val = row[exc_idx] if (exc_idx is not None and exc_idx < len(row)) else None
        if exc_idx is not None:
            key = exc_val if exc_val is not None else ""
            exception_counts[key] = exception_counts.get(key, 0) + 1
        if date_idx is not None:
            date_val = row[date_idx] if date_idx < len(row) else ""
            if is_valid_gtfs_date(date_val):
                if exc_val == "1":
                    added_dates.append(date_val)
                elif exc_val == "2":
                    removed_dates.append(date_val)
            else:
                invalid_dates.append(DateIssue(i, "date", date_val))

    return CalendarDatesStats(
        present=True,
        header=header,
        row_count=len(data_rows),
        service_id_unique_count=len(service_ids),
        service_ids=frozenset(service_ids),
        exception_type_counts=exception_counts,
        added_date_min=min(added_dates) if added_dates else None,
        added_date_max=max(added_dates) if added_dates else None,
        removed_date_min=min(removed_dates) if removed_dates else None,
        removed_date_max=max(removed_dates) if removed_dates else None,
        invalid_dates=tuple(invalid_dates),
    )


def inspect_feed_info(zf: zipfile.ZipFile) -> FeedInfoStats:
    if "feed_info.txt" not in zf.namelist():
        return FeedInfoStats(present=False)
    raw = zf.read("feed_info.txt")
    try:
        decoded = decode_csv_bytes(raw)
    except UnicodeDecodeError as exc:
        return FeedInfoStats(present=True, decode_error=str(exc))
    header, data_rows = read_csv_rows(decoded.text)
    start_idx = header.index("feed_start_date") if "feed_start_date" in header else None
    end_idx = header.index("feed_end_date") if "feed_end_date" in header else None
    ver_idx = header.index("feed_version") if "feed_version" in header else None

    feed_start = feed_end = feed_version = None
    invalid_dates: List[DateIssue] = []
    if data_rows:
        row = data_rows[0]
        if start_idx is not None:
            v = row[start_idx] if start_idx < len(row) else ""
            if is_valid_gtfs_date(v):
                feed_start = v
            elif v:
                invalid_dates.append(DateIssue(0, "feed_start_date", v))
        if end_idx is not None:
            v = row[end_idx] if end_idx < len(row) else ""
            if is_valid_gtfs_date(v):
                feed_end = v
            elif v:
                invalid_dates.append(DateIssue(0, "feed_end_date", v))
        if ver_idx is not None:
            feed_version = row[ver_idx] if ver_idx < len(row) else ""

    return FeedInfoStats(
        present=True,
        header=header,
        row_count=len(data_rows),
        feed_start_date=feed_start,
        feed_end_date=feed_end,
        feed_version=feed_version,
        invalid_dates=tuple(invalid_dates),
    )


def inspect_service_id_cross_check(
    zf: zipfile.ZipFile, calendar: CalendarStats, calendar_dates: CalendarDatesStats
) -> ServiceIdCrossCheck:
    if "trips.txt" not in zf.namelist():
        return ServiceIdCrossCheck(None, None, None, None)
    raw = zf.read("trips.txt")
    try:
        decoded = decode_csv_bytes(raw)
    except UnicodeDecodeError:
        return ServiceIdCrossCheck(None, None, None, None)
    header, data_rows = read_csv_rows(decoded.text)
    if "service_id" not in header:
        empty: FrozenSet[str] = frozenset()
        return ServiceIdCrossCheck(empty, empty, empty, empty)
    idx = header.index("service_id")
    trips_ids: FrozenSet[str] = frozenset(row[idx] for row in data_rows if idx < len(row))

    cal_ids = calendar.service_ids if (calendar.present and calendar.service_ids is not None) else frozenset()
    cd_ids = (
        calendar_dates.service_ids
        if (calendar_dates.present and calendar_dates.service_ids is not None)
        else frozenset()
    )
    union_ids: FrozenSet[str] = frozenset(cal_ids | cd_ids)

    return ServiceIdCrossCheck(
        trips_service_ids=trips_ids,
        calendar_union_service_ids=union_ids,
        trips_only=frozenset(trips_ids - union_ids),
        calendar_union_only=frozenset(union_ids - trips_ids),
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def inspect_zipfile(zf: zipfile.ZipFile, source_label: str = "<memory>") -> InspectionResult:
    """開かれた`zipfile.ZipFile`を検査する。ネットワークにもディスクにも触れない。

    自動テストは、`zipfile.ZipFile(io.BytesIO(...))`で完全にメモリ上に作った
    合成ZIPをここへ渡す（CLAUDE.md『リポジトリの外に一切書かない』を、テスト用の
    一時ファイルすら作らずに守るため。SPEC.md §14.7の『一時ディレクトリ内の合成ZIP』は
    ディスク上の一時ファイルではなく、実ファイルを介さないメモリ上のZIPとして満たす）。
    """
    safety = inspect_safety(zf)
    if not safety.ok:
        return InspectionResult(
            source_label=source_label, file_sha256=None, file_size=None, safety=safety
        )

    core = {name: inspect_core_file(zf, name) for name in CORE_FILES}
    stops_lt = inspect_stops_location_type(zf)
    calendar = inspect_calendar(zf)
    calendar_dates = inspect_calendar_dates(zf)
    feed_info = inspect_feed_info(zf)
    cross = inspect_service_id_cross_check(zf, calendar, calendar_dates)

    return InspectionResult(
        source_label=source_label,
        file_sha256=None,
        file_size=None,
        safety=safety,
        core_files=core,
        stops_location_type=stops_lt,
        calendar=calendar,
        calendar_dates=calendar_dates,
        feed_info=feed_info,
        service_id_cross_check=cross,
    )


def sha256_of_file(path: str) -> Tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def inspect_archive(zip_path: str) -> InspectionResult:
    """リポジトリ内に保存済みのZIPファイルを検査する（`raw/gtfs/*.zip`用）。"""
    file_sha256, file_size = sha256_of_file(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        result = inspect_zipfile(zf, source_label=zip_path)
    return dataclasses.replace(result, file_sha256=file_sha256, file_size=file_size)
