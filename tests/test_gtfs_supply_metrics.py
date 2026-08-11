"""SPEC.md §15（SUPPLY-METRIC-1の定義）に沿った `calculate_gtfs_supply_metrics.py`
（SUPPLY-METRIC-2の実装）の自動テスト。

`tests/test_gtfs_inspection.py` と同じ方針で、合成GTFSはすべて `io.BytesIO` 上にのみ
構築し、ディスク（一時ディレクトリを含む）へは一切書き込まない
（CLAUDE.md「リポジトリの外に一切書かない。作業用の中間ファイルも例外ではない」）。
ネットワークへは一切接続しない。保存済みの2つの公式ZIP（`raw/gtfs/*.zip`）と
`data/gtfs_supply_metrics.json` だけを実ファイルとして読む。
"""
from __future__ import annotations

import io
import sys
import unittest
import zipfile
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import calculate_gtfs_supply_metrics as csm  # noqa: E402

IWAKUNI_ZIP = REPO_ROOT / "raw" / "gtfs" / "iwakuni_gtfsjp_20260401.zip"
HIKARI_ZIP = REPO_ROOT / "raw" / "gtfs" / "hikari_gtfs_20260401.zip"
OUTPUT_JSON = REPO_ROOT / "data" / "gtfs_supply_metrics.json"


def _build_zip(entries):
    """entries: [(name, bytes), ...]。`io.BytesIO` のみを使う。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    buf.seek(0)
    return buf


# 曜日での有効判定を素直に検証できる、火曜始まり・日曜終わりの週を使う
# （2026-04-06(月)〜2026-04-12(日)は実データ用の固定週なので、合成テストは別の週にする）。
_MON, _TUE, _WED, _THU, _FRI, _SAT, _SUN = (
    date(2026, 5, 4),
    date(2026, 5, 5),
    date(2026, 5, 6),
    date(2026, 5, 7),
    date(2026, 5, 8),
    date(2026, 5, 9),
    date(2026, 5, 10),
)


def _minimal_entries(calendar=None, calendar_dates=None, trips=None, frequencies=None):
    entries = [
        ("agency.txt", b"agency_id,agency_name,agency_url,agency_timezone\nA1,Test,https://example.test,Asia/Tokyo\n"),
        (
            "routes.txt",
            b"route_id,agency_id,route_short_name,route_long_name,route_type\n"
            b"R1,A1,1,Route 1,3\nR2,A1,2,Route 2,3\n",
        ),
        (
            "stops.txt",
            b"stop_id,stop_name,stop_lat,stop_lon,location_type\n"
            b"S1,Stop 1,34.0,131.0,0\nS2,Stop 2,34.1,131.1,0\nS3,Platform,34.2,131.2,1\n",
        ),
    ]
    if calendar is not None:
        entries.append(("calendar.txt", calendar))
    if calendar_dates is not None:
        entries.append(("calendar_dates.txt", calendar_dates))
    if trips is not None:
        entries.append(("trips.txt", trips))
    if frequencies is not None:
        entries.append(("frequencies.txt", frequencies))
    return entries


_WEEKDAY_CALENDAR = (
    b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
    b"WEEKDAY,1,1,1,1,1,0,0,20260401,20270331\n"
)
_TWO_TRIPS = b"route_id,service_id,trip_id\nR1,WEEKDAY,T1\nR1,WEEKDAY,T2\n"


class GtfsSupplyMetricsTest(unittest.TestCase):
    """SPEC.md §15.4〜§15.6の実装を検査する。"""

    def test_supply_metrics_calculation(self):
        # === 1. GTFS収録構造の件数（§15.4.2） ===
        with self.subTest("1a_agency_route_stop_counts_normal"):
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                agency = csm.compute_agency_record_count(csm.read_table(zf, "agency.txt"))
                routes = csm.compute_route_id_count(csm.read_table(zf, "routes.txt"))
                stops = csm.compute_boarding_location_id_count(csm.read_table(zf, "stops.txt"))
            self.assertEqual(agency, csm.MetricValue(1, "measured", None))
            self.assertEqual(routes, csm.MetricValue(2, "measured", None))
            # S3はlocation_type=1（駅等）なので乗降場所には数えない。S1・S2の2件のみ。
            self.assertEqual(stops, csm.MetricValue(2, "measured", None))

        with self.subTest("1b_agency_absent_not_calculable"):
            with zipfile.ZipFile(_build_zip([])) as zf:
                result = csm.compute_agency_record_count(csm.read_table(zf, "agency.txt"))
            self.assertEqual(result.metric_status, "not_calculable")
            self.assertIsNone(result.value)

        with self.subTest("1c_route_id_blank_invalid_input"):
            entries = [("routes.txt", b"route_id,route_type\nR1,3\n,3\n")]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_route_id_count(csm.read_table(zf, "routes.txt"))
            self.assertEqual(result.metric_status, "invalid_input")
            self.assertIsNone(result.value)

        with self.subTest("1d_route_id_duplicate_invalid_input"):
            entries = [("routes.txt", b"route_id,route_type\nR1,3\nR1,3\n")]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_route_id_count(csm.read_table(zf, "routes.txt"))
            self.assertEqual(result.metric_status, "invalid_input")

        with self.subTest("1e_boarding_location_type_column_absent_defaults_to_counted"):
            entries = [("stops.txt", b"stop_id,stop_name\nS1,A\nS2,B\n")]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_boarding_location_id_count(csm.read_table(zf, "stops.txt"))
            self.assertEqual(result, csm.MetricValue(2, "measured", None))

        with self.subTest("1f_route_id_column_missing_not_calculable"):
            entries = [("routes.txt", b"route_short_name\n1\n")]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_route_id_count(csm.read_table(zf, "routes.txt"))
            self.assertEqual(result.metric_status, "not_calculable")

        # === 2. scheduled_trip_count_by_date（§15.4.3） ===
        with self.subTest("2a_calendar_only_weekday_active_and_inactive"):
            entries = _minimal_entries(
                calendar=_WEEKDAY_CALENDAR,
                calendar_dates=b"service_id,date,exception_type\n",
                trips=_TWO_TRIPS,
            )
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON, _SUN),
                )
            self.assertEqual(result.scheduled_trip_count_by_date["2026-05-04"], csm.MetricValue(2, "measured", None))

        with self.subTest("2b_sunday_zero_valid_trips_measured_zero"):
            # 平日のみ運行のcalendarで、日曜は有効serviceが空集合になり0便（invalid_inputではない）。
            entries = _minimal_entries(
                calendar=_WEEKDAY_CALENDAR,
                calendar_dates=b"service_id,date,exception_type\n",
                trips=_TWO_TRIPS,
            )
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_SUN,),
                )
            self.assertEqual(result.scheduled_trip_count_by_date["2026-05-10"], csm.MetricValue(0, "measured", None))

        with self.subTest("2c_calendar_dates_addition_only_service"):
            # calendar.txtに存在しないservice_idを、calendar_dates.txtのexception_type=1だけで追加する。
            cal_dates = f"service_id,date,exception_type\nSPECIAL,{_SAT.strftime('%Y%m%d')},1\n".encode("utf-8")
            trips = b"route_id,service_id,trip_id\nR1,SPECIAL,T9\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=cal_dates, trips=trips)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_SAT,),
                )
            self.assertEqual(result.scheduled_trip_count_by_date["2026-05-09"], csm.MetricValue(1, "measured", None))

        with self.subTest("2d_calendar_dates_removal_overrides_weekday"):
            # 平日運行のWEEKDAYを、月曜日だけcalendar_dates.txtのexception_type=2で除外する。
            cal_dates = f"service_id,date,exception_type\nWEEKDAY,{_MON.strftime('%Y%m%d')},2\n".encode("utf-8")
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=cal_dates, trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON, _TUE),
                )
            self.assertEqual(result.scheduled_trip_count_by_date["2026-05-04"], csm.MetricValue(0, "measured", None))
            self.assertEqual(result.scheduled_trip_count_by_date["2026-05-05"], csm.MetricValue(2, "measured", None))

        with self.subTest("2e_both_calendar_and_calendar_dates_absent_invalid_input"):
            entries = _minimal_entries(trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON, _TUE, _SUN),
                )
            for d in ("2026-05-04", "2026-05-05", "2026-05-10"):
                self.assertEqual(result.scheduled_trip_count_by_date[d].metric_status, "invalid_input")
                self.assertIsNone(result.scheduled_trip_count_by_date[d].value)
                self.assertIn("両方とも存在しない", result.scheduled_trip_count_by_date[d].reason)

        with self.subTest("2f_calendar_missing_required_column_invalid_input"):
            bad_calendar = (
                b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,start_date,end_date\n"
                b"WEEKDAY,1,1,1,1,1,0,20260401,20270331\n"
            )  # sunday列が無い
            entries = _minimal_entries(calendar=bad_calendar, calendar_dates=b"service_id,date,exception_type\n", trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("必須列が無い", mv.reason)

        with self.subTest("2g_calendar_duplicate_service_id_invalid_input"):
            dup_calendar = (
                b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                b"WEEKDAY,1,1,1,1,1,0,0,20260401,20270331\n"
                b"WEEKDAY,0,0,0,0,0,1,1,20260401,20270331\n"
            )
            entries = _minimal_entries(calendar=dup_calendar, calendar_dates=b"service_id,date,exception_type\n", trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("重複している", mv.reason)

        with self.subTest("2h_calendar_dates_duplicate_key_invalid_input"):
            dup_cd = (
                f"service_id,date,exception_type\nWEEKDAY,{_MON.strftime('%Y%m%d')},2\n"
                f"WEEKDAY,{_MON.strftime('%Y%m%d')},1\n"
            ).encode("utf-8")
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=dup_cd, trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("重複", mv.reason)

        with self.subTest("2i_calendar_dates_invalid_exception_type"):
            bad_cd = f"service_id,date,exception_type\nWEEKDAY,{_MON.strftime('%Y%m%d')},3\n".encode("utf-8")
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=bad_cd, trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("exception_typeが不正", mv.reason)

        with self.subTest("2j_calendar_invalid_weekday_flag_value"):
            bad_calendar = (
                b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                b"WEEKDAY,2,1,1,1,1,0,0,20260401,20270331\n"
            )
            entries = _minimal_entries(calendar=bad_calendar, calendar_dates=b"service_id,date,exception_type\n", trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("monday列の値が不正", mv.reason)

        with self.subTest("2k_calendar_invalid_date_format"):
            bad_calendar = (
                b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                b"WEEKDAY,1,1,1,1,1,0,0,2026-04-01,20270331\n"
            )
            entries = _minimal_entries(calendar=bad_calendar, calendar_dates=b"service_id,date,exception_type\n", trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("日付が不正", mv.reason)

        with self.subTest("2l_trips_absent_invalid_input"):
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n")
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("trips.txtが存在しない", mv.reason)

        with self.subTest("2m_trips_duplicate_trip_id_invalid_input"):
            dup_trips = b"route_id,service_id,trip_id\nR1,WEEKDAY,T1\nR1,WEEKDAY,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=dup_trips)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("trip_id 'T1' が重複している", mv.reason)

        # === 3. frequencies.txt（§15.4.3手順4〜6） ===
        with self.subTest("3a_frequencies_exact_times_1_exact_multiple"):
            freq = b"trip_id,start_time,end_time,headway_secs,exact_times\nT1,06:00:00,07:00:00,600,1\n"
            trips = b"route_id,service_id,trip_id\nR1,WEEKDAY,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=trips, frequencies=freq)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            # 3600秒/600秒 = ちょうど6便（start+n*600 < end を満たすn=0..5）。
            self.assertEqual(result.scheduled_trip_count_by_date["2026-05-04"], csm.MetricValue(6, "measured", None))

        with self.subTest("3b_frequencies_exact_times_1_non_divisible_invalid_input"):
            # SPEC.md §15.4.3手順5「時刻範囲が正で割り切れることを検証し」は文字どおりの
            # 整除（余り0）要求と読む。3900秒は600秒で割り切れない（余り300）ため、
            # 部分値・端数丸めの便数を出さずinvalid_inputにする。
            freq = b"trip_id,start_time,end_time,headway_secs,exact_times\nT1,06:00:00,07:05:00,600,1\n"
            trips = b"route_id,service_id,trip_id\nR1,WEEKDAY,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=trips, frequencies=freq)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIsNone(mv.value)
            self.assertIn("割り切れない", mv.reason)

        with self.subTest("3c_frequencies_exact_times_0_not_exact_frequency_based"):
            freq = b"trip_id,start_time,end_time,headway_secs,exact_times\nT1,06:00:00,07:00:00,600,0\n"
            trips = b"route_id,service_id,trip_id\nR1,WEEKDAY,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=trips, frequencies=freq)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "not_exact_frequency_based")
            self.assertIsNone(mv.value)

        with self.subTest("3d_frequencies_exact_times_blank_not_exact_frequency_based"):
            freq = b"trip_id,start_time,end_time,headway_secs,exact_times\nT1,06:00:00,07:00:00,600,\n"
            trips = b"route_id,service_id,trip_id\nR1,WEEKDAY,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=trips, frequencies=freq)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "not_exact_frequency_based")

        with self.subTest("3e_frequencies_mixed_normal_trip_plus_frequency_trip"):
            # T1は頻度なしの通常trip（1便）、T2はexact_times=1の頻度trip（2便: 08:00,08:30）。
            freq = b"trip_id,start_time,end_time,headway_secs,exact_times\nT2,08:00:00,09:00:00,1800,1\n"
            trips = b"route_id,service_id,trip_id\nR1,WEEKDAY,T1\nR1,WEEKDAY,T2\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=trips, frequencies=freq)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            self.assertEqual(result.scheduled_trip_count_by_date["2026-05-04"], csm.MetricValue(3, "measured", None))

        with self.subTest("3f_frequencies_unknown_trip_id_invalid_input"):
            freq = b"trip_id,start_time,end_time,headway_secs,exact_times\nGHOST,06:00:00,07:00:00,600,1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=_TWO_TRIPS, frequencies=freq)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("trips.txtに存在しない", mv.reason)

        # === 6. trips.txtのroute_id/service_id参照整合性（§15.2・§15.4.3の必須列・参照関係） ===
        with self.subTest("6a_trips_unknown_route_id_invalid_input"):
            bad_trips = b"route_id,service_id,trip_id\nR9,WEEKDAY,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=bad_trips)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIsNone(mv.value)
            self.assertIn("routes.txtに存在しない", mv.reason)

        with self.subTest("6b_trips_unknown_service_id_invalid_input"):
            bad_trips = b"route_id,service_id,trip_id\nR1,GHOST,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=bad_trips)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIsNone(mv.value)
            self.assertIn("calendar.txt/calendar_dates.txtのいずれにも存在しない", mv.reason)

        with self.subTest("6c_trips_missing_route_id_column_invalid_input"):
            no_route_col_trips = b"service_id,trip_id\nWEEKDAY,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=no_route_col_trips)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("trips.txtに必須列が無い", mv.reason)
            self.assertIn("route_id", mv.reason)

        with self.subTest("6d_trips_blank_route_id_invalid_input"):
            blank_route_trips = b"route_id,service_id,trip_id\n,WEEKDAY,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=blank_route_trips)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("route_idが空欄", mv.reason)

        with self.subTest("6e_trips_blank_service_id_invalid_input"):
            blank_service_trips = b"route_id,service_id,trip_id\nR1,,T1\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=b"service_id,date,exception_type\n", trips=blank_service_trips)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("service_idが空欄", mv.reason)

        with self.subTest("6f_routes_missing_route_id_column_invalid_input"):
            entries = [
                ("routes.txt", b"route_short_name\n1\n"),
                ("calendar.txt", _WEEKDAY_CALENDAR),
                ("calendar_dates.txt", b"service_id,date,exception_type\n"),
                ("trips.txt", _TWO_TRIPS),
            ]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("routes.txtにroute_id列が無い", mv.reason)

        with self.subTest("6g_routes_absent_invalid_input"):
            entries = [
                ("calendar.txt", _WEEKDAY_CALENDAR),
                ("calendar_dates.txt", b"service_id,date,exception_type\n"),
                ("trips.txt", _TWO_TRIPS),
            ]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("routes.txtが存在しない", mv.reason)

        with self.subTest("6h_routes_duplicate_route_id_invalid_input"):
            entries = [
                ("routes.txt", b"route_id,route_type\nR1,3\nR1,3\n"),
                ("calendar.txt", _WEEKDAY_CALENDAR),
                ("calendar_dates.txt", b"service_id,date,exception_type\n"),
                ("trips.txt", _TWO_TRIPS),
            ]
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("routes.txtのroute_idが重複する", mv.reason)

        with self.subTest("6i_calendar_start_after_end_invalid_input"):
            bad_calendar = (
                b"service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                b"WEEKDAY,1,1,1,1,1,0,0,20270331,20260401\n"
            )
            entries = _minimal_entries(calendar=bad_calendar, calendar_dates=b"service_id,date,exception_type\n", trips=_TWO_TRIPS)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_MON,),
                )
            mv = result.scheduled_trip_count_by_date["2026-05-04"]
            self.assertEqual(mv.metric_status, "invalid_input")
            self.assertIn("日付範囲が不正", mv.reason)

        with self.subTest("6j_calendar_dates_only_service_reference_remains_allowed"):
            # calendar.txtに対応する行が無いservice_id（calendar_dates.txtだけで定義）でも、
            # trips.txtからの参照は有効として扱う（岩国市の実データと同じパターン）。
            cal_dates = f"service_id,date,exception_type\nSPECIAL,{_SAT.strftime('%Y%m%d')},1\n".encode("utf-8")
            trips = b"route_id,service_id,trip_id\nR1,SPECIAL,T9\n"
            entries = _minimal_entries(calendar=_WEEKDAY_CALENDAR, calendar_dates=cal_dates, trips=trips)
            with zipfile.ZipFile(_build_zip(entries)) as zf:
                result = csm.compute_feed_metrics_from_zipfile(
                    zf,
                    feed_id="test",
                    municipality_code="000000",
                    municipality="テスト市",
                    official_reference_date="2026-04-01",
                    checked_at="2026-08-10",
                    scope_note="test",
                    week_dates=(_SAT,),
                )
            self.assertEqual(result.scheduled_trip_count_by_date["2026-05-09"], csm.MetricValue(1, "measured", None))

        # === 4. 岩国市・光市の保存済みZIPについて、SHA256・全指標・7実日付を固定値で検査する ===
        with self.subTest("4a_iwakuni_saved_zip_fixed_values"):
            self.assertTrue(IWAKUNI_ZIP.is_file())
            result = csm.compute_feed_metrics(
                str(IWAKUNI_ZIP),
                feed_id="iwakuni-gtfsjp",
                municipality_code="352080",
                municipality="岩国市",
                official_reference_date="2026-04-01",
                checked_at="2026-08-09",
                scope_note="test",
            )
            self.assertEqual(
                result.source_zip_sha256,
                "d236a58ff4a0edb4812a8bed543d4897670441164a1019e88d5e35ded5052de2",
            )
            self.assertEqual(result.source_zip_size_bytes, 719723)
            self.assertEqual(result.metrics["gtfs_agency_record_count"], csm.MetricValue(1, "measured", None))
            self.assertEqual(result.metrics["gtfs_route_id_count"], csm.MetricValue(46, "measured", None))
            self.assertEqual(result.metrics["gtfs_boarding_location_id_count"], csm.MetricValue(800, "measured", None))
            expected_daily = {
                "2026-04-06": 185,
                "2026-04-07": 186,
                "2026-04-08": 183,
                "2026-04-09": 161,
                "2026-04-10": 188,
                "2026-04-11": 146,
                "2026-04-12": 39,
            }
            for d, expected in expected_daily.items():
                self.assertEqual(
                    result.scheduled_trip_count_by_date[d], csm.MetricValue(expected, "measured", None)
                )
            self.assertEqual(result.date_basis["feed_info"]["feed_start_date"], "20260327")
            self.assertEqual(result.date_basis["calendar"]["service_id_unique_count"], 1)
            self.assertEqual(result.date_basis["calendar_dates"]["service_id_unique_count"], 22)

        with self.subTest("4b_hikari_saved_zip_fixed_values"):
            self.assertTrue(HIKARI_ZIP.is_file())
            result = csm.compute_feed_metrics(
                str(HIKARI_ZIP),
                feed_id="hikari-gtfs",
                municipality_code="352101",
                municipality="光市",
                official_reference_date="2026-04-01",
                checked_at="2026-08-09",
                scope_note="test",
            )
            self.assertEqual(
                result.source_zip_sha256,
                "f3403ebaf481805fff0e2316be3a986732f443a06a64eab5b579ea17191adde7",
            )
            self.assertEqual(result.source_zip_size_bytes, 86273)
            self.assertEqual(result.metrics["gtfs_agency_record_count"], csm.MetricValue(1, "measured", None))
            self.assertEqual(result.metrics["gtfs_route_id_count"], csm.MetricValue(7, "measured", None))
            self.assertEqual(result.metrics["gtfs_boarding_location_id_count"], csm.MetricValue(172, "measured", None))
            expected_daily = {
                "2026-04-06": 55,
                "2026-04-07": 55,
                "2026-04-08": 55,
                "2026-04-09": 55,
                "2026-04-10": 55,
                "2026-04-11": 41,
                "2026-04-12": 41,
            }
            for d, expected in expected_daily.items():
                self.assertEqual(
                    result.scheduled_trip_count_by_date[d], csm.MetricValue(expected, "measured", None)
                )

        # === 5. data/gtfs_supply_metrics.json の再生成がバイト一致すること ===
        with self.subTest("5a_output_json_regeneration_byte_identical"):
            self.assertTrue(OUTPUT_JSON.is_file())
            on_disk = OUTPUT_JSON.read_bytes()
            regenerated = csm.render_dataset_json(csm.build_dataset()).encode("utf-8")
            self.assertEqual(regenerated, on_disk)

        with self.subTest("5b_build_dataset_deterministic_across_runs"):
            first = csm.render_dataset_json(csm.build_dataset())
            second = csm.render_dataset_json(csm.build_dataset())
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
