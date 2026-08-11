"""SPEC.md §14.5（ZIP安全検査）・§14.6（実測する内容）の自動テスト。

§14.7の指示どおり、検出可能な新規テストメソッドは正確に1件だけとし、
各条件は名前付き `subTest` で分離する。ネットワークへは一切接続しない。
合成ZIPはすべて `io.BytesIO` 上でのみ構築し、ディスク（一時ディレクトリを含む）へは
書き込まない。CLAUDE.md「リポジトリの外に一切書かない。作業用の中間ファイルも例外ではない」
を、テスト用の一時ファイルすら作らないことで満たすための設計判断であり、SPEC.md §14.7の
「一時ディレクトリ内の合成ZIP」は、実ファイルを介さないメモリ上のZIPとして満たす
（詳細はPROGRESS.mdに記録）。保存済みの2つの公式ZIP（`raw/gtfs/*.zip`）だけを実ファイルとして読む。
"""
from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import inspect_gtfs_archives as gi  # noqa: E402

IWAKUNI_ZIP = REPO_ROOT / "raw" / "gtfs" / "iwakuni_gtfsjp_20260401.zip"
HIKARI_ZIP = REPO_ROOT / "raw" / "gtfs" / "hikari_gtfs_20260401.zip"


# ---------------------------------------------------------------------------
# 合成ZIPを完全にメモリ上に作るためのヘルパー（ディスクには一切書かない）
# ---------------------------------------------------------------------------


def _build_zip(entries):
    """entries: [(name または zipfile.ZipInfo, bytes), ...]。`io.BytesIO` のみを使う。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name_or_info, data in entries:
            zf.writestr(name_or_info, data)
    buf.seek(0)
    return buf


def _build_simple_zip_bytes(name: str, data: bytes = b"x") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr(name, data)
    return buf.getvalue()


def _patch_name(zip_bytes: bytes, placeholder: str, real_name_bytes: bytes) -> bytes:
    """ローカルヘッダ・セントラルディレクトリのファイル名バイト列を直接置換する。

    `zipfile.writestr` はASCII文字列しか安全に渡せない場面（NUL・単独バックスラッシュを
    含む名前は書き込み経路そのものが正規化・拒否してしまう）があるため、
    プレースホルダと同じバイト長の名前に生バイトレベルで置換する。
    """
    placeholder_bytes = placeholder.encode("ascii")
    if len(placeholder_bytes) != len(real_name_bytes):
        raise ValueError("placeholder length must match real name byte length")
    if zip_bytes.count(placeholder_bytes) != 2:
        raise ValueError("placeholder must appear exactly twice (local header + central directory)")
    return zip_bytes.replace(placeholder_bytes, real_name_bytes)


def _patch_flag_bit0(zip_bytes: bytes) -> bytes:
    """ローカルヘッダ・セントラルディレクトリの汎用ビットフラグのbit0（暗号化）を立てる。

    `zipfile.writestr` は書き込み時にこのビットを常にクリアするため、暗号化メンバーの
    検出（SPEC.md §14.5）を検査するには生バイトを直接書き換える必要がある。
    """
    data = bytearray(zip_bytes)
    idx = data.find(b"PK\x03\x04")
    while idx != -1:
        data[idx + 6] |= 0x1
        idx = data.find(b"PK\x03\x04", idx + 4)
    idx = data.find(b"PK\x01\x02")
    while idx != -1:
        data[idx + 8] |= 0x1
        idx = data.find(b"PK\x01\x02", idx + 4)
    return bytes(data)


_MINIMAL_GTFS_ENTRIES = [
    (
        "agency.txt",
        b"agency_id,agency_name,agency_url,agency_timezone\n"
        b"A1,Test Agency,https://example.test,Asia/Tokyo\n",
    ),
    (
        "stops.txt",
        b"stop_id,stop_name,stop_lat,stop_lon,location_type\n"
        b"S1,Stop 1,34.0,131.0,0\nS2,Stop 2,34.1,131.1,0\n",
    ),
    ("routes.txt", b"route_id,agency_id,route_short_name,route_long_name,route_type\nR1,A1,1,Route 1,3\n"),
    ("trips.txt", b"route_id,service_id,trip_id\nR1,WEEKDAY,T1\n"),
    (
        "stop_times.txt",
        b"trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
        b"T1,08:00:00,08:00:00,S1,1\nT1,08:10:00,08:10:00,S2,2\n",
    ),
    (
        "calendar.txt",
        b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
        b"WEEKDAY,1,1,1,1,1,0,0,20260401,20270331\n",
    ),
    ("calendar_dates.txt", b"service_id,date,exception_type\nWEEKDAY,20260503,2\n"),
    (
        "feed_info.txt",
        b"feed_publisher_name,feed_publisher_url,feed_lang,feed_start_date,feed_end_date,feed_version\n"
        b"Test,https://example.test,ja,20260401,20270331,v1\n",
    ),
]


class GtfsArchiveInspectionTest(unittest.TestCase):
    """SPEC.md §14.5・§14.6の実装を検査する。SPEC.md §14.7が定める唯一の新規テストメソッド。"""

    def test_gtfs_archive_safety_and_measurement(self):
        # === 1. 正常な最小GTFS ZIPから、ヘッダー・行数・ID・日付候補を再現できる ===
        with self.subTest("1a_minimal_gtfs_safety_ok_and_core_files"):
            with zipfile.ZipFile(_build_zip(_MINIMAL_GTFS_ENTRIES)) as zf:
                result = gi.inspect_zipfile(zf, "minimal")
            self.assertTrue(result.safety.ok)
            self.assertEqual(result.safety.failures, ())
            agency = result.core_files["agency.txt"]
            self.assertTrue(agency.present)
            self.assertIsNone(agency.decode_error)
            self.assertFalse(agency.had_bom)
            self.assertEqual(agency.header, ("agency_id", "agency_name", "agency_url", "agency_timezone"))
            self.assertEqual(agency.row_count, 1)
            self.assertEqual(agency.id_stats, gi.IdColumnStats("agency_id", 0, 1, 0))
            stops = result.core_files["stops.txt"]
            self.assertEqual(stops.row_count, 2)
            self.assertEqual(stops.id_stats, gi.IdColumnStats("stop_id", 0, 2, 0))
            self.assertEqual(result.stops_location_type, gi.LocationTypeStats({"0": 2}))
            stop_times = result.core_files["stop_times.txt"]
            self.assertEqual(stop_times.row_count, 2)
            # 複合主キー(trip_id, stop_sequence)。2行とも(T1,1)(T1,2)で重複なし・空欄なし。
            self.assertEqual(
                stop_times.id_stats,
                gi.IdColumnStats("trip_id+stop_sequence", blank_count=0, unique_count=2, duplicate_count=0),
            )

        with self.subTest("1b_minimal_gtfs_calendar_calendar_dates_feed_info_cross_check"):
            with zipfile.ZipFile(_build_zip(_MINIMAL_GTFS_ENTRIES)) as zf:
                result = gi.inspect_zipfile(zf, "minimal")
            self.assertEqual(result.calendar.row_count, 1)
            self.assertEqual(result.calendar.service_ids, frozenset({"WEEKDAY"}))
            self.assertEqual(result.calendar.min_start_date, "20260401")
            self.assertEqual(result.calendar.max_end_date, "20270331")
            self.assertEqual(result.calendar.invalid_dates, ())
            weekday = result.calendar.weekday
            for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
                self.assertEqual(weekday.counts[day], {"1": 1})
            for day in ("saturday", "sunday"):
                self.assertEqual(weekday.counts[day], {"0": 1})
            self.assertEqual(weekday.invalid_count, 0)
            self.assertEqual(result.calendar_dates.row_count, 1)
            self.assertEqual(result.calendar_dates.exception_type_counts, {"2": 1})
            self.assertIsNone(result.calendar_dates.added_date_min)
            self.assertEqual(result.calendar_dates.removed_date_min, "20260503")
            self.assertEqual(result.calendar_dates.removed_date_max, "20260503")
            self.assertEqual(result.feed_info.feed_start_date, "20260401")
            self.assertEqual(result.feed_info.feed_end_date, "20270331")
            self.assertEqual(result.feed_info.feed_version, "v1")
            cross = result.service_id_cross_check
            self.assertEqual(cross.trips_service_ids, frozenset({"WEEKDAY"}))
            self.assertEqual(cross.trips_only, frozenset())
            self.assertEqual(cross.calendar_union_only, frozenset())

        # === 2. パストラバーサル、絶対パス、階層、重複名、暗号化、シンボリックリンクを拒否する ===
        with self.subTest("2a_path_traversal_dotdot_rejected"):
            with zipfile.ZipFile(_build_zip([("../evil.txt", b"x")])) as zf:
                result = gi.inspect_zipfile(zf, "traversal")
            self.assertFalse(result.safety.ok)
            self.assertTrue(any(f.check == "member_name" for f in result.safety.failures))

        with self.subTest("2b_absolute_path_rejected"):
            with zipfile.ZipFile(_build_zip([("/etc/passwd", b"x")])) as zf:
                result = gi.inspect_zipfile(zf, "absolute")
            self.assertFalse(result.safety.ok)
            self.assertTrue(any(f.check == "member_name" for f in result.safety.failures))

        with self.subTest("2c_drive_letter_rejected"):
            with zipfile.ZipFile(_build_zip([("C:/evil.txt", b"x")])) as zf:
                result = gi.inspect_zipfile(zf, "drive")
            self.assertFalse(result.safety.ok)
            self.assertTrue(any(f.check == "member_name" for f in result.safety.failures))

        with self.subTest("2d_directory_hierarchy_rejected"):
            with zipfile.ZipFile(_build_zip([("dir/agency.txt", b"x")])) as zf:
                result = gi.inspect_zipfile(zf, "hierarchy")
            self.assertFalse(result.safety.ok)
            self.assertTrue(any(f.check == "member_name" for f in result.safety.failures))

        with self.subTest("2e_duplicate_name_case_insensitive_rejected"):
            with zipfile.ZipFile(_build_zip([("Agency.txt", b"x"), ("agency.TXT", b"y")])) as zf:
                result = gi.inspect_zipfile(zf, "dup")
            self.assertFalse(result.safety.ok)
            self.assertTrue(any(f.check == "duplicate_name" for f in result.safety.failures))

        with self.subTest("2f_encrypted_member_rejected"):
            # zipfile.writestr()は書き込み時に暗号化ビットを常にクリアするため、
            # 生バイトのローカルヘッダ・セントラルディレクトリを直接書き換えて検査する。
            raw = _build_simple_zip_bytes("agency.txt", b"agency_id\nA1\n")
            patched = _patch_flag_bit0(raw)
            with zipfile.ZipFile(io.BytesIO(patched)) as zf:
                self.assertEqual(zf.infolist()[0].flag_bits & 0x1, 0x1)
                result = gi.inspect_zipfile(zf, "encrypted")
            self.assertFalse(result.safety.ok)
            self.assertTrue(any(f.check == "member_type" for f in result.safety.failures))

        with self.subTest("2g_symlink_member_rejected"):
            zi = zipfile.ZipInfo("agency.txt")
            zi.external_attr = (0o120777) << 16  # S_IFLNK | 0777
            with zipfile.ZipFile(_build_zip([(zi, b"target.txt")])) as zf:
                result = gi.inspect_zipfile(zf, "symlink")
            self.assertFalse(result.safety.ok)
            self.assertTrue(any(f.check == "member_type" for f in result.safety.failures))

        with self.subTest("2h_nul_byte_in_name_pure_function"):
            # zipfile自体が central directory 読み込み時にNUL以降を切り詰めるため（標準ライブラリ側の
            # 多層防御）、実ZIP経由では`ZipInfo.filename`にNULを含む値を再現できない。
            # 判定ロジック自体（`check_member_name`）を直接検査する。
            self.assertEqual(gi.check_member_name("agency\x00.txt"), "メンバー名にNULを含む")

        with self.subTest("2i_backslash_only_name_pure_function"):
            # zipfile自体が読み込み時にバックスラッシュをフォワードスラッシュへ正規化するため
            # （これも標準ライブラリ側の多層防御。結果として"/"を含む名前になりディレクトリ階層
            # 検査で拒否される）、単独バックスラッシュを持つ`ZipInfo.filename`を実ZIP経由で
            # 再現できない。判定ロジック自体を直接検査する。
            self.assertEqual(
                gi.check_member_name("dir\\agency.txt"), "メンバー名にバックスラッシュを含む"
            )
            # 実ZIP経由では正規化されて"/"を含む名前になり、階層検査で拒否されることを確認する。
            raw = _build_simple_zip_bytes("dirXagency.txt")
            patched = _patch_name(raw, "dirXagency.txt", b"dir\\agency.txt")
            with zipfile.ZipFile(io.BytesIO(patched)) as zf:
                normalized_name = zf.infolist()[0].filename
                result = gi.inspect_zipfile(zf, "backslash_normalized")
            self.assertEqual(normalized_name, "dir/agency.txt")
            self.assertFalse(result.safety.ok)
            self.assertTrue(any(f.check == "member_name" for f in result.safety.failures))

        # === 3. メンバー数、個別・合計サイズ、圧縮比の境界値を検査する ===
        with self.subTest("3a_member_count_at_limit_200_passes"):
            self.assertIsNone(gi.check_member_count_limit(200))

        with self.subTest("3b_member_count_over_limit_201_fails"):
            failure = gi.check_member_count_limit(201)
            self.assertIsNotNone(failure)
            self.assertEqual(failure.check, "member_count")

        with self.subTest("3c_member_size_at_limit_passes"):
            limit = gi.MAX_MEMBER_UNCOMPRESSED_BYTES
            failures = gi.check_size_and_ratio_limits([gi.MemberSizeInfo("a", limit, limit)])
            self.assertEqual(failures, [])

        with self.subTest("3d_member_size_over_limit_fails"):
            limit = gi.MAX_MEMBER_UNCOMPRESSED_BYTES
            failures = gi.check_size_and_ratio_limits([gi.MemberSizeInfo("a", limit + 1, limit + 1)])
            self.assertEqual([f.check for f in failures], ["member_size"])

        with self.subTest("3e_total_size_at_limit_passes"):
            per_member = gi.MAX_MEMBER_UNCOMPRESSED_BYTES
            sizes = [gi.MemberSizeInfo(f"m{i}", per_member, per_member) for i in range(5)]
            self.assertEqual(sum(s.file_size for s in sizes), gi.MAX_TOTAL_UNCOMPRESSED_BYTES)
            self.assertEqual(gi.check_size_and_ratio_limits(sizes), [])

        with self.subTest("3f_total_size_over_limit_fails"):
            per_member = gi.MAX_MEMBER_UNCOMPRESSED_BYTES
            sizes = [gi.MemberSizeInfo(f"m{i}", per_member, per_member) for i in range(5)]
            sizes.append(gi.MemberSizeInfo("extra", 1, 1))
            failures = gi.check_size_and_ratio_limits(sizes)
            self.assertEqual([f.check for f in failures], ["total_size"])

        with self.subTest("3g_compression_ratio_at_limit_200_passes"):
            failures = gi.check_size_and_ratio_limits([gi.MemberSizeInfo("a", 200 * 1000, 1000)])
            self.assertEqual(failures, [])

        with self.subTest("3h_compression_ratio_over_limit_fails"):
            failures = gi.check_size_and_ratio_limits([gi.MemberSizeInfo("a", 200 * 1000 + 1, 1000)])
            self.assertEqual([f.check for f in failures], ["compression_ratio"])

        # === 4. UTF-8、UTF-8 BOMを区別して読み、非UTF-8を拒否する ===
        with self.subTest("4a_utf8_no_bom"):
            decoded = gi.decode_csv_bytes("agency_id\nA1\n".encode("utf-8"))
            self.assertFalse(decoded.had_bom)
            self.assertEqual(decoded.text, "agency_id\nA1\n")

        with self.subTest("4b_utf8_with_bom"):
            decoded = gi.decode_csv_bytes(b"\xef\xbb\xbf" + "agency_id\nA1\n".encode("utf-8"))
            self.assertTrue(decoded.had_bom)
            self.assertEqual(decoded.text, "agency_id\nA1\n")

        with self.subTest("4c_non_utf8_rejected_no_shift_jis_fallback"):
            shift_jis_bytes = "agency_id\n日本語".encode("shift_jis")
            with self.assertRaises(UnicodeDecodeError):
                gi.decode_csv_bytes(shift_jis_bytes)

        # === 5. 不正日付、必須列不足、空ID、重複IDを黙って補正・重複排除しない ===
        with self.subTest("5a_invalid_date_not_8_digits"):
            self.assertFalse(gi.is_valid_gtfs_date("2026-04-01"))
            self.assertFalse(gi.is_valid_gtfs_date(""))

        with self.subTest("5b_invalid_date_not_a_real_calendar_date"):
            self.assertFalse(gi.is_valid_gtfs_date("20261301"))  # 13月
            self.assertFalse(gi.is_valid_gtfs_date("20260230"))  # 2月30日は存在しない
            self.assertTrue(gi.is_valid_gtfs_date("20260401"))

        with self.subTest("5c_missing_primary_id_column_not_guessed"):
            entries = [("agency.txt", b"agency_name\nOnly Name\n")]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = gi.inspect_zipfile(zf, "missingcol")
            agency = result.core_files["agency.txt"]
            self.assertEqual(agency.header, ("agency_name",))
            self.assertEqual(
                agency.id_stats, gi.IdColumnStats(column=None, blank_count=None, unique_count=None, duplicate_count=None)
            )

        with self.subTest("5d_blank_and_duplicate_id_counted_not_silently_fixed"):
            entries = [("stops.txt", b"stop_id,stop_name\n,Empty ID\nS1,Stop1\nS1,Stop1 dup\n")]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = gi.inspect_zipfile(zf, "dupid")
            stops = result.core_files["stops.txt"]
            self.assertEqual(stops.row_count, 3)
            self.assertEqual(stops.id_stats, gi.IdColumnStats("stop_id", blank_count=1, unique_count=1, duplicate_count=1))

        with self.subTest("5e_weekday_flag_invalid_value_and_missing_column_not_silently_fixed"):
            # sunday列自体が無い（列不足）ケースと、monday列に0/1以外の値があるケースを
            # 同じ合成calendar.txtで両方検査する。どちらも黙って補正・穴埋めしない。
            entries = [
                (
                    "calendar.txt",
                    b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,start_date,end_date\n"
                    b"X,2,1,1,1,1,0,20260401,20270331\n",
                )
            ]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = gi.inspect_zipfile(zf, "weekday_invalid")
            weekday = result.calendar.weekday
            self.assertEqual(weekday.counts["monday"], {"2": 1})
            self.assertEqual(weekday.counts["saturday"], {"0": 1})
            self.assertIsNone(weekday.counts["sunday"])  # 列不足は未測定のまま
            self.assertEqual(weekday.invalid_count, 1)

        # === 6. calendar.txtのみ、calendar_dates.txtのみ、両方あり、両方なしを区別する ===
        _CALENDAR_ONLY_ROW = (
            b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
            b"X,1,1,1,1,1,0,0,20260401,20270331\n"
        )
        with self.subTest("6a_calendar_only"):
            with zipfile.ZipFile(_build_zip([("calendar.txt", _CALENDAR_ONLY_ROW)])) as zf:
                result = gi.inspect_zipfile(zf, "cal_only")
            self.assertTrue(result.calendar.present)
            self.assertFalse(result.calendar_dates.present)

        with self.subTest("6b_calendar_dates_only"):
            entries = [("calendar_dates.txt", b"service_id,date,exception_type\nX,20260401,1\n")]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = gi.inspect_zipfile(zf, "cd_only")
            self.assertFalse(result.calendar.present)
            self.assertTrue(result.calendar_dates.present)

        with self.subTest("6c_both_present"):
            entries = [
                ("calendar.txt", _CALENDAR_ONLY_ROW),
                ("calendar_dates.txt", b"service_id,date,exception_type\nX,20260401,1\n"),
            ]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = gi.inspect_zipfile(zf, "both")
            self.assertTrue(result.calendar.present)
            self.assertTrue(result.calendar_dates.present)

        with self.subTest("6d_neither_present"):
            with zipfile.ZipFile(_build_zip([])) as zf:
                result = gi.inspect_zipfile(zf, "neither")
            self.assertFalse(result.calendar.present)
            self.assertFalse(result.calendar_dates.present)

        # === 7. 岩国市・光市の保存済みZIPについてSHA256と実測結果を固定値で検査する ===
        with self.subTest("7a_iwakuni_saved_zip_fixed_values"):
            self.assertTrue(IWAKUNI_ZIP.is_file())
            result = gi.inspect_archive(str(IWAKUNI_ZIP))
            self.assertEqual(
                result.file_sha256,
                "d236a58ff4a0edb4812a8bed543d4897670441164a1019e88d5e35ded5052de2",
            )
            self.assertEqual(result.file_size, 719723)
            self.assertTrue(result.safety.ok)
            self.assertEqual(result.safety.failures, ())
            self.assertEqual(len(result.safety.members), 12)
            self.assertEqual(result.core_files["agency.txt"].row_count, 1)
            self.assertEqual(result.core_files["stops.txt"].row_count, 800)
            self.assertEqual(result.core_files["stops.txt"].id_stats, gi.IdColumnStats("stop_id", 0, 800, 0))
            self.assertEqual(result.stops_location_type, gi.LocationTypeStats({"0": 800}))
            self.assertEqual(result.core_files["routes.txt"].row_count, 46)
            self.assertEqual(result.core_files["trips.txt"].row_count, 267)
            self.assertEqual(result.core_files["stop_times.txt"].row_count, 7362)
            self.assertEqual(
                result.core_files["stop_times.txt"].id_stats,
                gi.IdColumnStats("trip_id+stop_sequence", blank_count=0, unique_count=7362, duplicate_count=0),
            )
            self.assertEqual(result.calendar.row_count, 1)
            self.assertEqual(result.calendar.service_id_unique_count, 1)
            self.assertEqual(result.calendar.min_start_date, "20260327")
            self.assertEqual(result.calendar.max_end_date, "20270326")
            for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
                self.assertEqual(result.calendar.weekday.counts[day], {"1": 1})
            for day in ("saturday", "sunday"):
                self.assertEqual(result.calendar.weekday.counts[day], {"0": 1})
            self.assertEqual(result.calendar.weekday.invalid_count, 0)
            self.assertEqual(result.calendar_dates.row_count, 1641)
            self.assertEqual(result.calendar_dates.service_id_unique_count, 22)
            self.assertEqual(result.calendar_dates.exception_type_counts, {"1": 1641})
            self.assertEqual(result.calendar_dates.added_date_min, "20260327")
            self.assertEqual(result.calendar_dates.added_date_max, "20260930")
            self.assertIsNone(result.calendar_dates.removed_date_min)
            self.assertEqual(result.feed_info.feed_start_date, "20260327")
            self.assertEqual(result.feed_info.feed_end_date, "20270326")
            self.assertEqual(result.service_id_cross_check.trips_only, frozenset())
            self.assertEqual(result.service_id_cross_check.calendar_union_only, frozenset({"平日"}))

        with self.subTest("7b_hikari_saved_zip_fixed_values"):
            self.assertTrue(HIKARI_ZIP.is_file())
            result = gi.inspect_archive(str(HIKARI_ZIP))
            self.assertEqual(
                result.file_sha256,
                "f3403ebaf481805fff0e2316be3a986732f443a06a64eab5b579ea17191adde7",
            )
            self.assertEqual(result.file_size, 86273)
            self.assertTrue(result.safety.ok)
            self.assertEqual(result.safety.failures, ())
            self.assertEqual(len(result.safety.members), 14)
            self.assertEqual(result.core_files["agency.txt"].row_count, 1)
            self.assertEqual(result.core_files["stops.txt"].row_count, 172)
            self.assertEqual(result.core_files["stops.txt"].id_stats, gi.IdColumnStats("stop_id", 0, 172, 0))
            self.assertEqual(result.stops_location_type, gi.LocationTypeStats({"0": 172}))
            self.assertEqual(result.core_files["routes.txt"].row_count, 7)
            self.assertEqual(result.core_files["trips.txt"].row_count, 63)
            self.assertEqual(result.core_files["stop_times.txt"].row_count, 1344)
            self.assertEqual(
                result.core_files["stop_times.txt"].id_stats,
                gi.IdColumnStats("trip_id+stop_sequence", blank_count=0, unique_count=1344, duplicate_count=0),
            )
            self.assertEqual(result.calendar.row_count, 4)
            self.assertEqual(result.calendar.service_id_unique_count, 4)
            self.assertEqual(result.calendar.min_start_date, "20260401")
            self.assertEqual(result.calendar.max_end_date, "20270331")
            for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
                self.assertEqual(result.calendar.weekday.counts[day], {"0": 1, "1": 3})
            for day in ("saturday", "sunday"):
                self.assertEqual(result.calendar.weekday.counts[day], {"0": 2, "1": 2})
            self.assertEqual(result.calendar.weekday.invalid_count, 0)
            self.assertEqual(result.calendar_dates.row_count, 61)
            self.assertEqual(result.calendar_dates.service_id_unique_count, 3)
            self.assertEqual(result.calendar_dates.exception_type_counts, {"1": 22, "2": 39})
            self.assertEqual(result.calendar_dates.added_date_min, "20260429")
            self.assertEqual(result.calendar_dates.added_date_max, "20270322")
            self.assertEqual(result.calendar_dates.removed_date_min, "20260429")
            self.assertEqual(result.calendar_dates.removed_date_max, "20270322")
            self.assertEqual(result.feed_info.feed_start_date, "20260401")
            self.assertEqual(result.feed_info.feed_end_date, "20270331")
            self.assertEqual(result.service_id_cross_check.trips_only, frozenset())
            self.assertEqual(result.service_id_cross_check.calendar_union_only, frozenset())


if __name__ == "__main__":
    unittest.main()
