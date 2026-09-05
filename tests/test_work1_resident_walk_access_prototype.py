import hashlib
import unittest

from src import build_work1_resident_walk_access_prototype as builder


class Work1ResidentWalkAccessPrototypeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload, cls.gtfs_sha256, cls.osm_sha256 = builder.load_prototype_payloads()
        cls.expected = builder.render_html(
            cls.payload,
            cls.gtfs_sha256,
            cls.osm_sha256,
        ).encode("utf-8")
        cls.saved = builder.HTML_OUTPUT.read_bytes()
        cls.html = cls.saved.decode("utf-8")

    def test_saved_output_exactly_matches_builder(self):
        self.assertEqual(self.saved, self.expected)
        self.assertEqual(self.saved.count(b"\r\n"), 0)

    def test_resident_question_and_four_step_flow_are_primary(self):
        for marker in (
            "<title>住民向け画面｜作品①</title>",
            "このバス停から、車なしで暮らせそう？",
            "バス停を見る",
            "バス停を選ぶ",
            "歩く時間を選ぶ",
            "施設を見る",
            "確かめたい用事（任意の仮例）",
            "今の答えを見る",
            "まだ判断できません",
        ):
            self.assertIn(marker, self.html)
        self.assertLess(
            self.html.index('class="card answer"'),
            self.html.index('aria-labelledby="map-title"'),
        )

    def test_area_is_a_display_transform_of_the_same_road_calculation(self):
        for marker in (
            "5分・10分・15分で届く道路が変わる計算は前の線表示と同じです",
            "保存済み施設のうち、表示面内にある座標を点で重ねます",
            'id="prototype-data"',
            'feature.properties.kind==="reachable_road"',
            "selectedRecord.area_payload.features.find",
        ):
            self.assertIn(marker, self.html)
        for item in self.payload["stops"]:
            area_payload = item["area_payload"]
            self.assertEqual(
                [feature["properties"]["minutes"] for feature in area_payload["features"]],
                [5, 10, 15],
            )
            cell_counts = [
                feature["properties"]["occupied_cell_count"]
                for feature in area_payload["features"]
            ]
            self.assertLess(cell_counts[0], cell_counts[1])
            self.assertLess(cell_counts[1], cell_counts[2])

    def test_three_gtfs_stops_have_independent_road_and_area_results(self):
        self.assertEqual(builder.TRIAL_STOP_EXPECTATIONS, (
            ("684_01", "岩国駅"),
            ("677_01", "市役所"),
            ("665_01", "今津"),
        ))
        self.assertEqual(self.payload["metadata"]["stop_count"], 3)
        self.assertEqual(self.payload["metadata"]["default_stop_id"], "684_01")
        self.assertEqual(
            [(item["stop"]["stop_id"], item["stop"]["stop_name"]) for item in self.payload["stops"]],
            list(builder.TRIAL_STOP_EXPECTATIONS),
        )
        for item in self.payload["stops"]:
            self.assertLess(item["road_payload"]["metadata"]["graph"]["snap_distance_m"], 50)
            self.assertEqual(len(item["area_payload"]["features"]), 3)
        for marker in (
            'id="stop-select"',
            '<option value="684_01" selected>岩国駅</option>',
            '<option value="677_01">市役所</option>',
            '<option value="665_01">今津</option>',
            'stopSelect.addEventListener("change"',
            "function showStop(stopId)",
            "3停留所・公式3施設データで表示試験中",
        ):
            self.assertIn(marker, self.html)

    def test_all_three_map_stops_are_clickable_and_synced_with_the_select(self):
        for marker in (
            'const stopLayer=L.layerGroup().addTo(map)',
            'const stopMarkerById=new Map()',
            'records.forEach(function(record){const stop=record.stop;const marker=L.circleMarker',
            'marker.on("click",function(){showStop(stop.stop_id);})',
            'element.setAttribute("role","button")',
            'element.setAttribute("tabindex","0")',
            'element.setAttribute("aria-label",stop.stop_name+"バス停を選択")',
            'event.key==="Enter"||event.key===" "',
            'element.setAttribute("aria-pressed",String(selected))',
            'stopSelect.value=selectedRecord.stop.stop_id',
            'records.forEach(function(record){viewBounds.extend([record.stop.stop_lat,record.stop.stop_lon]);})',
            '地図上の3停留所は選択できます',
        ):
            self.assertIn(marker, self.html)
        self.assertNotIn("map.removeLayer(stopMarker)", self.html)

    def test_compact_stop_card_precedes_controls_and_keeps_facility_details(self):
        for marker in (
            'class="card stop-card"',
            'id="stop-card-title"',
            'id="stop-card-time"',
            'バス停カルテ（試験表示）',
            '詳しく見る｜保存済み公式データ',
            'stopCardTitle.textContent=selectedRecord.stop.stop_name',
            'stopCardTime.textContent=selectedMinutes+"分以内の生活インフラ候補"',
            'id="facility-summary" aria-live="polite"',
            'id="facility-counts" aria-label="施設分類別の件数"',
            'id="facility-list" aria-label="範囲内の保存済み施設一覧"',
        ):
            self.assertIn(marker, self.html)
        self.assertLess(
            self.html.index('class="card stop-card"'),
            self.html.index('class="card controls"'),
        )
        self.assertLess(
            self.html.index('class="card controls"'),
            self.html.index('class="card facilities"'),
        )

    def test_area_is_primary_and_road_lines_are_optional(self):
        for marker in (
            "バス停から時間内に歩いて届く範囲",
            "詳しい道を表示",
            'id="road-toggle" type="button" aria-pressed="false"',
            'id="road-legend" hidden',
            'id="bridge-legend" hidden',
            ".legend [hidden]{display:none}",
            "fillOpacity:.30",
            'if(roadToggle.getAttribute("aria-pressed")!=="true")',
        ):
            self.assertIn(marker, self.html)
        show_stop = self.html[
            self.html.index("function showStop("):
            self.html.index('stopSelect.addEventListener("change"')
        ]
        self.assertNotIn(".openPopup()", show_stop)

    def test_real_road_evidence_and_unknowns_are_kept_separate(self):
        for marker in (
            "確認済み：道路到達",
            "確認済み：保存済み施設位置",
            "未確認：入口・営業時間",
            "未確認：坂・安全",
            "未確認：帰りの便",
        ):
            self.assertIn(marker, self.html)
        self.assertIn(self.gtfs_sha256, self.html)
        self.assertIn(self.osm_sha256, self.html)
        self.assertEqual(
            self.gtfs_sha256,
            hashlib.sha256(builder.GTFS_INPUT.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.osm_sha256,
            hashlib.sha256(builder.OSM_INPUT.read_bytes()).hexdigest(),
        )
        self.assertEqual(
            self.payload["metadata"]["facility_source"]["sha256"],
            hashlib.sha256(builder.FACILITY_INPUT.read_bytes()).hexdigest(),
        )

    def test_saved_official_facilities_are_preserved_as_trial_source_categories(self):
        self.assertEqual(self.payload["metadata"]["facility_record_count"], 304)
        self.assertEqual(len(self.payload["facility_records"]), 304)
        self.assertEqual(
            [item["key"] for item in self.payload["metadata"]["facility_categories"]],
            ["public_facility", "medical_facility", "childcare_facility"],
        )
        counts = {
            category: sum(
                item["common_category"] == category
                for item in self.payload["facility_records"]
            )
            for category in ("public_facility", "medical_facility", "childcare_facility")
        }
        self.assertEqual(counts, {
            "public_facility": 88,
            "medical_facility": 164,
            "childcare_facility": 52,
        })
        self.assertEqual(
            len({item["facility_id"] for item in self.payload["facility_records"]}),
            304,
        )

    def test_each_stop_and_time_has_recomputed_facility_results(self):
        facility_by_id = {
            item["facility_id"]: item
            for item in self.payload["facility_records"]
        }
        expected_counts = {
            "684_01": {"5": 6, "10": 24, "15": 52},
            "677_01": {"5": 21, "10": 45, "15": 60},
            "665_01": {"5": 11, "10": 33, "15": 58},
        }
        for item in self.payload["stops"]:
            previous_ids = set()
            for area_feature in item["area_payload"]["features"]:
                minutes = str(area_feature["properties"]["minutes"])
                summary = item["facility_reachability"]["by_minutes"][minutes]
                current_ids = set(summary["facility_ids"])
                self.assertEqual(
                    summary["facility_count"],
                    expected_counts[item["stop"]["stop_id"]][minutes],
                )
                self.assertEqual(summary["facility_count"], len(current_ids))
                self.assertLessEqual(previous_ids, current_ids)
                self.assertEqual(
                    sum(summary["category_counts"].values()),
                    summary["facility_count"],
                )
                for facility_id in current_ids:
                    facility = facility_by_id[facility_id]
                    self.assertTrue(builder.point_is_in_area_feature(
                        (facility["longitude"], facility["latitude"]),
                        area_feature,
                    ))
                previous_ids = current_ids

    def test_zero_facility_result_is_supported(self):
        area_feature = self.payload["stops"][0]["area_payload"]["features"][0]
        far_away = {
            "facility_id": "synthetic:outside",
            "facility_name": "試験範囲外",
            "common_category": "public_facility",
            "source_category": "公共施設",
            "latitude": 0.0,
            "longitude": 0.0,
            "source_id": "synthetic",
        }
        self.assertEqual(builder.facilities_in_area([far_away], area_feature), [])
        self.assertIn("この条件で範囲内に該当する保存済み施設は0件です", self.html)
        self.assertIn("facilityZero.hidden=facilities.length!==0", self.html)

    def test_facilities_are_rendered_on_the_map_and_in_an_accessible_list(self):
        for marker in (
            'id="facility-summary" aria-live="polite"',
            'id="facility-counts" aria-label="施設分類別の件数"',
            'id="facility-list" aria-label="範囲内の保存済み施設一覧"',
            "function drawFacilities()",
            "L.circleMarker(",
            "facilityList.appendChild(listItem)",
            "表示面内の保存済み公式施設：",
        ):
            self.assertIn(marker, self.html)

    def test_facility_list_selection_links_to_marker_without_moving_map(self):
        for marker in (
            'id="facility-selection" aria-live="polite"',
            'button.type="button"',
            'button.dataset.facilityId=facility.facility_id',
            'button.setAttribute("aria-current","false")',
            'facilityList.addEventListener("click"',
            'function focusFacility(facilityId)',
            'marker.bindPopup(popup,{autoPan:false})',
            'marker.setRadius(10)',
            'marker.setStyle({color:"#ffb900",weight:4,fillOpacity:1})',
            'marker.bringToFront()',
            'marker.openPopup()',
            'button.setAttribute("aria-current",String(selected))',
            'min-height:44px',
        ):
            self.assertIn(marker, self.html)
        focus_facility = self.html[
            self.html.index("function focusFacility("):
            self.html.index("function showMinutes(")
        ]
        self.assertNotIn("map.setView(", focus_facility)
        self.assertIn("地図を動かさずに一覧と施設情報を連動します", self.html)
        self.assertNotIn('facilityList.addEventListener("keydown"', self.html)

    def test_map_point_selection_highlights_and_scrolls_matching_list_item(self):
        for marker in (
            'marker.on("click",function(){focusFacility(facility.facility_id);})',
            'let selectedButton=null',
            'const selected=button.dataset.facilityId===facilityId',
            'if(selected){selectedButton=button;}',
            'selectedButton.scrollIntoView({block:"nearest",inline:"nearest"})',
            "施設名か地図上の点を選ぶと、地図を動かさずに一覧と施設情報を連動します",
            "地図上と一覧で強調し、施設情報を表示しました",
        ):
            self.assertIn(marker, self.html)

    def test_examples_do_not_become_final_facility_or_walking_specification(self):
        for marker in (
            "用事の仮例と、保存済み公式3データセットの分類は別です",
            "生活施設の優先順位や最終分類ではありません",
            "最終対象地域や優先停留所ではありません",
            "80m/分は正式条件ではありません",
            "40mの仮幅も表示試験用で、徒歩条件ではありません",
        ):
            self.assertIn(marker, self.html)
        self.assertEqual(
            self.payload["metadata"]["status"],
            "LOCAL_MULTI_STOP_FACILITY_OVERLAY_TRIAL_NOT_ACCEPTED_PRODUCT_SPEC",
        )
        for item in self.payload["stops"]:
            self.assertEqual(
                item["area_payload"]["metadata"]["status"],
                "LOCAL_DISPLAY_TRIAL_NOT_WALKING_SPECIFICATION",
            )
        self.assertNotIn("総合点", self.html)
        self.assertNotIn("自治体モード", self.html)
        self.assertIn("生活施設の定義や優先順位ではありません", self.html)
        self.assertIn("施設座標が試験用表示面の内側にあるかだけ", self.html)

    def test_time_life_need_and_detail_controls_are_keyboard_native(self):
        for minutes in (5, 10, 15):
            self.assertIn(f'data-minutes="{minutes}"', self.html)
        for need in ("shopping", "medical", "procedure", "undecided"):
            self.assertIn(f'data-need="{need}"', self.html)
        self.assertIn('id="road-toggle"', self.html)
        self.assertIn("min-height:44px", self.html)
        self.assertIn(":focus-visible", self.html)
        self.assertIn('aria-live="polite"', self.html)

    def test_map_uses_pinned_leaflet_openstreetmap_and_opens_popup_only_after_selection(self):
        self.assertIn(builder.LEAFLET_CSS_INTEGRITY, self.html)
        self.assertIn(builder.LEAFLET_JS_INTEGRITY, self.html)
        self.assertIn(builder.OSM_TILE_URL, self.html)
        self.assertIn("openstreetmap.org/copyright", self.html)
        self.assertIn(".bindPopup(", self.html)
        draw_facilities = self.html[
            self.html.index("function drawFacilities()"):
            self.html.index("function focusFacility(")
        ]
        focus_facility = self.html[
            self.html.index("function focusFacility("):
            self.html.index("function showMinutes(")
        ]
        self.assertNotIn(".openPopup()", draw_facilities)
        self.assertIn("marker.openPopup()", focus_facility)
        self.assertNotIn("maps.gsi.go.jp", self.html)
        self.assertNotIn("fetch(", self.html)

    def test_mobile_and_map_failure_fallbacks_exist(self):
        self.assertIn("@media(max-width:650px)", self.html)
        self.assertIn("prefers-reduced-motion:reduce", self.html)
        self.assertIn("地図を読み込めませんでした", self.html)
        self.assertIn("背景地図の一部を読み込めませんでした", self.html)
        self.assertIn('<html lang="ja">', self.html)
        self.assertIn('<meta name="viewport"', self.html)


if __name__ == "__main__":
    unittest.main()
