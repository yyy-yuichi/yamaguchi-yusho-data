import hashlib
import unittest

from src import build_work1_facility_access_method_comparison as builder


class Work1FacilityAccessMethodComparisonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = builder.build_comparison_payload()
        cls.expected = builder.render_html(cls.payload).encode("utf-8")
        cls.saved = builder.HTML_OUTPUT.read_bytes()
        cls.html = cls.saved.decode("utf-8")

    def test_saved_output_exactly_matches_builder(self):
        self.assertEqual(self.saved, self.expected)
        self.assertEqual(self.saved.count(b"\r\n"), 0)

    def test_accepted_resident_prototype_is_unchanged_and_separate(self):
        resident = builder.resident_builder.HTML_OUTPUT.read_bytes()
        self.assertEqual(
            hashlib.sha256(resident).hexdigest(),
            builder.ACCEPTED_RESIDENT_PROTOTYPE_SHA256,
        )
        self.assertNotEqual(builder.HTML_OUTPUT, builder.resident_builder.HTML_OUTPUT)
        self.assertEqual(
            self.payload["metadata"]["sources"]["accepted_resident_prototype"]["sha256"],
            builder.ACCEPTED_RESIDENT_PROTOTYPE_SHA256,
        )
        self.assertIn("受入済みの住民画面とは別", self.html)

    def test_saved_inputs_and_trial_boundaries_are_explicit(self):
        metadata = self.payload["metadata"]
        self.assertEqual(metadata["facility_record_count"], 304)
        self.assertEqual(metadata["minutes"], [5, 10, 15])
        self.assertEqual(metadata["temporary_speed_m_per_min"], 80)
        self.assertFalse(metadata["boundaries"]["new_data_acquired"])
        self.assertEqual(
            metadata["status"],
            "SEPARATE_TECHNICAL_TRIAL_NOT_ACCEPTED_PRODUCT_SPECIFICATION",
        )
        for name, path in (
            ("gtfs", builder.resident_builder.GTFS_INPUT),
            ("osm", builder.resident_builder.OSM_INPUT),
            ("facilities", builder.resident_builder.FACILITY_INPUT),
        ):
            record = metadata["sources"][name]
            self.assertEqual(record["bytes"], path.stat().st_size)
            self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        boundaries_text = " ".join(
            value for value in metadata["boundaries"].values()
            if isinstance(value, str)
        )
        for marker in (
            "入口や実際に歩ける接続を証明しない",
            "正式な徒歩条件ではない",
            "生活施設の最終定義や優先順位ではない",
            "住民モード完成後の別段階",
        ):
            self.assertIn(marker, boundaries_text)
        self.assertEqual(
            metadata["calculation"]["facility_snap_method"],
            "nearest accepted saved OSM graph edge point",
        )

    def test_nearest_edge_snap_uses_a_point_on_the_road_segment(self):
        graph = {
            "coordinates": {1: (132.0, 34.0), 2: (132.001, 34.0)},
            "edges": [{
                "edge_id": "trial:0",
                "u": 1,
                "v": 2,
                "length_m": builder.network_builder.haversine_meters(
                    (132.0, 34.0),
                    (132.001, 34.0),
                ),
            }],
        }
        snap = builder.nearest_edge_snap(graph, (132.0005, 34.0001))
        self.assertEqual(snap["edge_id"], "trial:0")
        self.assertAlmostEqual(snap["edge_fraction"], 0.5, delta=0.001)
        self.assertAlmostEqual(snap["edge_coordinate"][0], 132.0005, delta=0.000001)
        self.assertAlmostEqual(snap["edge_coordinate"][1], 34.0, delta=0.000001)
        self.assertAlmostEqual(
            snap["distance_to_u_m"] + snap["distance_to_v_m"],
            graph["edges"][0]["length_m"],
            delta=0.001,
        )
        self.assertLess(snap["snap_distance_m"], 12)

    def test_three_stops_and_three_times_partition_all_facilities(self):
        self.assertEqual(
            [(item["stop"]["stop_id"], item["stop"]["stop_name"]) for item in self.payload["stops"]],
            list(builder.resident_builder.TRIAL_STOP_EXPECTATIONS),
        )
        expected_keys = {item["key"] for item in builder.CLASSIFICATIONS}
        for stop in self.payload["stops"]:
            self.assertEqual(len(stop["facility_comparisons"]), 304)
            self.assertEqual(set(stop["summaries"]), {"5", "10", "15"})
            for minutes, summary in stop["summaries"].items():
                self.assertEqual(set(summary["classification_counts"]), expected_keys)
                self.assertEqual(sum(summary["classification_counts"].values()), 304)
                self.assertEqual(
                    summary["area_method_count"],
                    summary["classification_counts"]["both"]
                    + summary["classification_counts"]["area_only"],
                )
                self.assertEqual(
                    summary["road_method_count"],
                    summary["classification_counts"]["both"]
                    + summary["classification_counts"]["road_only"],
                )

    def test_road_distance_is_component_sum_and_budget_classification(self):
        for stop in self.payload["stops"]:
            for comparison in stop["facility_comparisons"]:
                total = comparison["estimated_access_distance_m"]
                if comparison["road_distance_available"]:
                    self.assertIsNotNone(total)
                    self.assertAlmostEqual(
                        total,
                        comparison["stop_snap_distance_m"]
                        + comparison["graph_distance_m"]
                        + comparison["facility_snap_distance_m"],
                        delta=0.002,
                    )
                else:
                    self.assertIsNone(total)
                    self.assertIsNone(comparison["graph_distance_m"])
                    self.assertIsNone(comparison["estimated_access_minutes"])
                for minutes in (5, 10, 15):
                    result = comparison["by_minutes"][str(minutes)]
                    self.assertEqual(result["budget_m"], minutes * 80)
                    self.assertEqual(
                        result["road_included"],
                        total is not None and total <= result["budget_m"] + 0.001,
                    )
                    self.assertEqual(
                        result["classification"],
                        builder.classify(result["area_included"], result["road_included"]),
                    )

    def test_city_hall_differences_shrink_after_edge_point_connection(self):
        city_hall = next(
            stop for stop in self.payload["stops"]
            if stop["stop"]["stop_name"] == "市役所"
        )
        self.assertLess(city_hall["stop_snap_distance_m"], 15)
        expected = {
            "5": {"both": 20, "area_only": 1, "road_only": 0, "neither": 283},
            "10": {"both": 43, "area_only": 2, "road_only": 0, "neither": 259},
            "15": {"both": 59, "area_only": 1, "road_only": 0, "neither": 244},
        }
        self.assertEqual(
            {
                minutes: summary["classification_counts"]
                for minutes, summary in city_hall["summaries"].items()
            },
            expected,
        )
        facilities = {
            item["facility_id"]: item
            for item in self.payload["facility_records"]
        }
        five_minute_difference_names = {
            facilities[facility_id]["facility_name"]
            for facility_id in city_hall["summaries"]["5"]
            ["classification_facility_ids"]["area_only"]
        }
        self.assertEqual(five_minute_difference_names, {"村岡整形外科"})

    def test_both_methods_are_cumulative_and_at_least_one_difference_is_exposed(self):
        difference_total = 0
        for stop in self.payload["stops"]:
            previous_area = set()
            previous_road = set()
            for minutes in (5, 10, 15):
                summary = stop["summaries"][str(minutes)]
                ids = summary["classification_facility_ids"]
                area = set(ids["both"] + ids["area_only"])
                road = set(ids["both"] + ids["road_only"])
                self.assertLessEqual(previous_area, area)
                self.assertLessEqual(previous_road, road)
                previous_area = area
                previous_road = road
                difference_total += summary["difference_count"]
        self.assertGreater(difference_total, 0)

    def test_comparison_ui_is_textual_keyboard_native_and_not_a_municipal_mode(self):
        for marker in (
            "<title>内部技術画面｜作品①</title>",
            'id="stop-select"',
            'data-minutes="5"',
            'data-minutes="10"',
            'data-minutes="15"',
            'aria-live="polite"',
            'id="result-list" aria-label="施設ごとの比較結果"',
            'button.type="button"',
            'element.setAttribute("role","button")',
            'element.setAttribute("tabindex","0")',
            'event.key==="Enter"||event.key===" "',
            'min-height:44px',
            ':focus-visible',
            'id="matched-count"',
            'id="needs-check-count"',
            "このページは、どちらが正解かを決める画面ではありません",
            "2つの方法で同じ結果",
            "計算方法で結果が分かれる",
            "結果が分かれた内訳",
            "表示面では内側、暫定道路試算では時間外",
            "暫定道路試算では時間内、表示面では外側",
            "保存道路がつながらず計算できない施設",
            "参考：2つの方法とも時間外の施設",
            "暫定道路試算は未接続",
            "外部参考（2026-09-01）",
            "Googleマップ徒歩ではすべて4～5分",
            "友田ファミリークリニック5分・350m",
            "村岡整形外科5分・400m",
            "三吉歯科5分・350m",
            "山元歯科医院4分・300m",
            "経路形状は保存・転載せず、この画面の判定入力にも使っていません",
            "最寄りの道路上の地点",
            "5分7件・10分3件・15分4件から、5分1件・10分2件・15分1件",
        ):
            self.assertIn(marker, self.html)
        for rejected_label in (
            "両方で時間内",
            "表示面だけ",
            "道路距離だけ",
            "どちらでもない",
            "確認が必要",
            "2つの計算が一致",
            "緑の範囲では近く見えるが、道路計算では時間内にならない",
            "道路計算では時間内だが、緑の範囲の外になる",
            "最寄りノードまでの直線",
        ):
            self.assertNotIn(rejected_label, self.html)
        self.assertNotIn('id="municipal-mode"', self.html)
        self.assertNotIn("総合点", self.html)

    def test_map_runtime_and_failure_boundaries_match_the_existing_trial(self):
        self.assertIn(builder.LEAFLET_CSS_INTEGRITY, self.html)
        self.assertIn(builder.LEAFLET_JS_INTEGRITY, self.html)
        self.assertIn(builder.OSM_TILE_URL, self.html)
        self.assertIn("openstreetmap.org/copyright", self.html)
        self.assertIn("地図を読み込めませんでした", self.html)
        self.assertIn("背景地図の一部を読み込めませんでした", self.html)
        self.assertIn("@media(max-width:760px)", self.html)
        self.assertIn("prefers-reduced-motion:reduce", self.html)
        self.assertNotIn("fetch(", self.html)


if __name__ == "__main__":
    unittest.main()
