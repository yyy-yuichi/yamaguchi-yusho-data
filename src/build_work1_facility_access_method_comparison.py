"""Build a separate trial comparing two facility access judgements.

The accepted resident prototype remains unchanged.  This technical page uses
only its saved GTFS, OSM, display-area, and official-facility inputs to compare:

1. whether the facility coordinate is inside the road-derived display area;
2. whether a provisional stop-to-nearest-road-point + graph-edge +
   facility-to-nearest-road-point distance is within the same temporary
   5, 10, or 15 minute budget.

Neither method verifies a facility entrance, the connector to the road, field
walkability, opening hours, usability, or a complete outbound/return journey.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
from typing import Any

try:
    from . import build_iwakuni_station_walk_network_isochrone_trial as network_builder
    from . import build_work1_resident_walk_access_prototype as resident_builder
except ImportError:  # Direct script execution from src/.
    import build_iwakuni_station_walk_network_isochrone_trial as network_builder
    import build_work1_resident_walk_access_prototype as resident_builder


ROOT = Path(__file__).resolve().parents[1]
HTML_OUTPUT = ROOT / "internal" / "work1_facility_access_method_comparison.html"
BUILD_DATE = "2026-09-01"
ACCEPTED_RESIDENT_PROTOTYPE_SHA256 = (
    "1279fb38deab3229fc6aca9a55df74d8979427ee57f64163c7891125af5513b5"
)
CLASSIFICATIONS = (
    {"key": "both", "label": "2つの方法で同じ結果", "color": "#247447"},
    {
        "key": "area_only",
        "label": "表示面では内側、暫定道路試算では時間外",
        "color": "#a85d00",
    },
    {
        "key": "road_only",
        "label": "暫定道路試算では時間内、表示面では外側",
        "color": "#1769a5",
    },
    {
        "key": "neither",
        "label": "2つの方法とも時間外",
        "color": "#687785",
    },
)

LEAFLET_VERSION = resident_builder.LEAFLET_VERSION
LEAFLET_CSS_URL = resident_builder.LEAFLET_CSS_URL
LEAFLET_CSS_INTEGRITY = resident_builder.LEAFLET_CSS_INTEGRITY
LEAFLET_JS_URL = resident_builder.LEAFLET_JS_URL
LEAFLET_JS_INTEGRITY = resident_builder.LEAFLET_JS_INTEGRITY
OSM_TILE_URL = resident_builder.OSM_TILE_URL
OSM_ATTRIBUTION = resident_builder.OSM_ATTRIBUTION


def file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def classify(area_included: bool, road_included: bool) -> str:
    if area_included and road_included:
        return "both"
    if area_included:
        return "area_only"
    if road_included:
        return "road_only"
    return "neither"


def nearest_edge_snap(
    graph: dict[str, Any],
    point: tuple[float, float],
) -> dict[str, Any]:
    if not graph["edges"]:
        raise ValueError("walk graph has no edges")

    lon, lat = point
    longitude_meters_per_degree = 111_320.0 * math.cos(math.radians(lat))
    latitude_meters_per_degree = 111_320.0
    best: tuple[tuple[float, str, int], dict[str, Any]] | None = None
    for edge_index, edge in enumerate(graph["edges"]):
        a = graph["coordinates"][edge["u"]]
        b = graph["coordinates"][edge["v"]]
        ax = (a[0] - lon) * longitude_meters_per_degree
        ay = (a[1] - lat) * latitude_meters_per_degree
        bx = (b[0] - lon) * longitude_meters_per_degree
        by = (b[1] - lat) * latitude_meters_per_degree
        dx = bx - ax
        dy = by - ay
        denominator = dx * dx + dy * dy
        fraction = (
            0.0
            if denominator == 0
            else max(0.0, min(1.0, -(ax * dx + ay * dy) / denominator))
        )
        edge_coordinate = (
            a[0] + (b[0] - a[0]) * fraction,
            a[1] + (b[1] - a[1]) * fraction,
        )
        snap_distance = network_builder.haversine_meters(point, edge_coordinate)
        snap = {
            "edge_index": edge_index,
            "edge_id": edge["edge_id"],
            "edge_u": edge["u"],
            "edge_v": edge["v"],
            "edge_fraction": fraction,
            "edge_coordinate": list(edge_coordinate),
            "snap_distance_m": snap_distance,
            "distance_to_u_m": edge["length_m"] * fraction,
            "distance_to_v_m": edge["length_m"] * (1.0 - fraction),
        }
        key = (snap_distance, str(edge["edge_id"]), edge_index)
        if best is None or key < best[0]:
            best = (key, snap)
    assert best is not None
    return best[1]


def edge_to_edge_graph_distance(
    start: dict[str, Any],
    target: dict[str, Any],
    distances_from_start_u: dict[int, float],
    distances_from_start_v: dict[int, float],
) -> float:
    candidates = [
        start["distance_to_u_m"]
        + distances_from_start_u.get(target["edge_u"], math.inf)
        + target["distance_to_u_m"],
        start["distance_to_u_m"]
        + distances_from_start_u.get(target["edge_v"], math.inf)
        + target["distance_to_v_m"],
        start["distance_to_v_m"]
        + distances_from_start_v.get(target["edge_u"], math.inf)
        + target["distance_to_u_m"],
        start["distance_to_v_m"]
        + distances_from_start_v.get(target["edge_v"], math.inf)
        + target["distance_to_v_m"],
    ]
    if start["edge_index"] == target["edge_index"]:
        edge_length = start["distance_to_u_m"] + start["distance_to_v_m"]
        candidates.append(
            abs(start["edge_fraction"] - target["edge_fraction"]) * edge_length
        )
    return min(candidates)


def build_facility_snaps(
    facilities: list[dict[str, Any]],
    graph: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    snaps: dict[str, dict[str, Any]] = {}
    for facility in facilities:
        snaps[facility["facility_id"]] = nearest_edge_snap(
            graph,
            (facility["longitude"], facility["latitude"]),
        )
    return snaps


def build_stop_comparison(
    stop_record: dict[str, Any],
    facilities: list[dict[str, Any]],
    facility_snaps: dict[str, dict[str, Any]],
    graph: dict[str, Any],
) -> dict[str, Any]:
    stop = stop_record["stop"]
    stop_snap = nearest_edge_snap(
        graph,
        (stop["stop_lon"], stop["stop_lat"]),
    )
    stop_snap_distance = stop_snap["snap_distance_m"]
    distances_from_start_u = network_builder.dijkstra(
        graph["adjacency"],
        stop_snap["edge_u"],
    )
    distances_from_start_v = network_builder.dijkstra(
        graph["adjacency"],
        stop_snap["edge_v"],
    )
    area_by_minutes = {
        str(feature["properties"]["minutes"]): feature
        for feature in stop_record["area_payload"]["features"]
    }
    comparisons = []
    for facility in facilities:
        facility_id = facility["facility_id"]
        facility_snap = facility_snaps[facility_id]
        graph_distance = edge_to_edge_graph_distance(
            stop_snap,
            facility_snap,
            distances_from_start_u,
            distances_from_start_v,
        )
        estimated_distance = (
            stop_snap_distance
            + graph_distance
            + facility_snap["snap_distance_m"]
        )
        by_minutes: dict[str, dict[str, Any]] = {}
        for minutes in network_builder.MINUTES:
            key = str(minutes)
            budget = minutes * network_builder.TEMPORARY_SPEED_METERS_PER_MINUTE
            area_included = resident_builder.point_is_in_area_feature(
                (facility["longitude"], facility["latitude"]),
                area_by_minutes[key],
            )
            road_included = estimated_distance <= budget
            by_minutes[key] = {
                "budget_m": budget,
                "area_included": area_included,
                "road_included": road_included,
                "classification": classify(area_included, road_included),
            }
        comparisons.append({
            "facility_id": facility_id,
            "graph_edge_id": facility_snap["edge_id"],
            "graph_edge_coordinate": [
                round(value, 7) for value in facility_snap["edge_coordinate"]
            ],
            "graph_edge_fraction": round(facility_snap["edge_fraction"], 7),
            "road_distance_available": not math.isinf(graph_distance),
            "stop_snap_distance_m": round(stop_snap_distance, 3),
            "graph_distance_m": None if math.isinf(graph_distance) else round(graph_distance, 3),
            "facility_snap_distance_m": round(facility_snap["snap_distance_m"], 3),
            "estimated_access_distance_m": (
                None if math.isinf(estimated_distance) else round(estimated_distance, 3)
            ),
            "estimated_access_minutes": (
                None
                if math.isinf(estimated_distance)
                else round(
                    estimated_distance
                    / network_builder.TEMPORARY_SPEED_METERS_PER_MINUTE,
                    3,
                )
            ),
            "by_minutes": by_minutes,
        })

    summaries: dict[str, dict[str, Any]] = {}
    previous_area_ids: set[str] = set()
    previous_road_ids: set[str] = set()
    for minutes in network_builder.MINUTES:
        key = str(minutes)
        classification_ids = {
            item["key"]: [
                comparison["facility_id"]
                for comparison in comparisons
                if comparison["by_minutes"][key]["classification"] == item["key"]
            ]
            for item in CLASSIFICATIONS
        }
        area_ids = set(classification_ids["both"] + classification_ids["area_only"])
        road_ids = set(classification_ids["both"] + classification_ids["road_only"])
        if not previous_area_ids <= area_ids:
            raise ValueError("display-area results must be cumulative")
        if not previous_road_ids <= road_ids:
            raise ValueError("road-distance results must be cumulative")
        summaries[key] = {
            "budget_m": minutes * network_builder.TEMPORARY_SPEED_METERS_PER_MINUTE,
            "classification_counts": {
                classification: len(facility_ids)
                for classification, facility_ids in classification_ids.items()
            },
            "classification_facility_ids": classification_ids,
            "area_method_count": len(area_ids),
            "road_method_count": len(road_ids),
            "difference_count": len(classification_ids["area_only"])
            + len(classification_ids["road_only"]),
            "road_distance_unavailable_count": sum(
                not comparison["road_distance_available"]
                for comparison in comparisons
            ),
        }
        previous_area_ids = area_ids
        previous_road_ids = road_ids

    return {
        "stop": stop,
        "stop_graph_edge_id": stop_snap["edge_id"],
        "stop_graph_edge_coordinate": [
            round(value, 7) for value in stop_snap["edge_coordinate"]
        ],
        "stop_graph_edge_fraction": round(stop_snap["edge_fraction"], 7),
        "stop_snap_distance_m": round(stop_snap_distance, 3),
        "area_features": stop_record["area_payload"]["features"],
        "facility_comparisons": comparisons,
        "summaries": summaries,
    }


def build_comparison_payload(
    gtfs_path: Path = resident_builder.GTFS_INPUT,
    osm_path: Path = resident_builder.OSM_INPUT,
    facility_path: Path = resident_builder.FACILITY_INPUT,
    accepted_prototype_path: Path = resident_builder.HTML_OUTPUT,
) -> dict[str, Any]:
    accepted_prototype = file_record(accepted_prototype_path)
    if accepted_prototype["sha256"] != ACCEPTED_RESIDENT_PROTOTYPE_SHA256:
        raise ValueError("accepted resident prototype changed before the separate comparison trial")

    resident_payload, _gtfs_sha256, _osm_sha256 = resident_builder.load_prototype_payloads(
        gtfs_path,
        osm_path,
        facility_path,
    )
    osm = json.loads(osm_path.read_text(encoding="utf-8"))
    graph = network_builder.build_graph(osm)
    facilities = resident_payload["facility_records"]
    facility_snaps = build_facility_snaps(facilities, graph)
    stops = [
        build_stop_comparison(stop_record, facilities, facility_snaps, graph)
        for stop_record in resident_payload["stops"]
    ]
    return {
        "metadata": {
            "task_id": "WORK1-FACILITY-ACCESS-METHOD-COMPARISON-TRIAL-1",
            "status": "SEPARATE_TECHNICAL_TRIAL_NOT_ACCEPTED_PRODUCT_SPECIFICATION",
            "build_date": BUILD_DATE,
            "default_stop_id": resident_payload["metadata"]["default_stop_id"],
            "minutes": list(network_builder.MINUTES),
            "temporary_speed_m_per_min": network_builder.TEMPORARY_SPEED_METERS_PER_MINUTE,
            "facility_record_count": len(facilities),
            "classifications": [dict(item) for item in CLASSIFICATIONS],
            "sources": {
                "gtfs": file_record(gtfs_path),
                "osm": file_record(osm_path),
                "facilities": file_record(facility_path),
                "accepted_resident_prototype": accepted_prototype,
            },
            "calculation": {
                "display_area_method": "facility coordinate inside the existing road-derived display MultiPolygon",
                "road_distance_method": "stop connector to nearest road edge point + shortest distance between edge points on accepted saved OSM graph + facility connector from nearest road edge point",
                "road_budget_method": "minutes multiplied by temporary speed",
                "facility_snap_method": "nearest accepted saved OSM graph edge point",
            },
            "boundaries": {
                "separate_trial": "受入済み住民画面へ混ぜず、判定方法の差だけを見る別の技術試験",
                "connector": "バス停・施設座標と最寄りの道路上の地点との直線接続は、入口や実際に歩ける接続を証明しない",
                "walking": "5分・10分・15分と80m/分は比較用の仮条件で、正式な徒歩条件ではない",
                "facility_scope": "保存済み公式3分類は試験入力で、生活施設の最終定義や優先順位ではない",
                "not_verified": "入口、営業時間、利用条件、坂、歩道、横断安全性、工事、現地通行可否、往路・用事・復路",
                "municipal_mode": "住民モード完成後の別段階であり、この試験には含めない",
                "new_data_acquired": False,
            },
        },
        "facility_records": facilities,
        "stops": stops,
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>内部技術画面｜作品①</title>
<link rel="stylesheet" href="__LEAFLET_CSS_URL__" integrity="__LEAFLET_CSS_INTEGRITY__" crossorigin="anonymous">
<style>
:root{--ink:#173043;--muted:#536a78;--line:#cfdbe1;--paper:#f4f7f8;--card:#fff;--navy:#123c59;--teal:#176f78;--green:#247447;--orange:#a85d00;--blue:#1769a5;--gray:#687785;--focus:#ffb900}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"Yu Gothic UI","Hiragino Kaku Gothic ProN",Meiryo,sans-serif;line-height:1.6}header{padding:20px clamp(15px,4vw,48px);background:linear-gradient(125deg,#123c59,#176f78);color:#fff}header p{margin:3px 0 0;max-width:900px}header h1{margin:0;font-size:clamp(1.35rem,3vw,2.15rem)}main{max-width:1450px;margin:auto;padding:16px}.notice{margin-bottom:14px;padding:13px 15px;border-left:6px solid var(--orange);border-radius:10px;background:#fff4df}.notice strong{display:block}.reference{border-left-color:var(--blue);background:#edf6ff}.controls{display:grid;grid-template-columns:minmax(230px,1fr) minmax(260px,1.3fr);gap:12px;margin-bottom:14px;padding:14px;border:1px solid var(--line);border-radius:14px;background:#fff}.field{display:grid;gap:5px}.field label,.time-label{font-weight:900}.field select{min-height:44px;padding:8px 10px;border:1px solid #879ca9;border-radius:8px;background:#fff;color:var(--ink);font:inherit}.time-buttons{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.time-buttons button{min-height:44px;border:1px solid #879ca9;border-radius:8px;background:#fff;color:var(--ink);font:inherit;font-weight:900;cursor:pointer}.time-buttons button[aria-pressed="true"]{border-color:var(--navy);background:var(--navy);color:#fff}.layout{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(340px,.8fr);gap:14px;align-items:start}.card{border:1px solid var(--line);border-radius:14px;background:#fff;box-shadow:0 8px 24px rgba(18,60,89,.08);overflow:hidden}.card-head{padding:13px 15px;border-bottom:1px solid var(--line)}.card-head h2{margin:0;font-size:1.08rem}.card-head p{margin:3px 0 0;color:var(--muted);font-size:.8rem}.map-frame{position:relative}#map{height:min(68vh,680px);min-height:500px;background:#dfe9ed}.map-fallback{display:grid;place-items:center;height:100%;padding:30px;background:#fff4df;color:#6d2f00;text-align:center;font-weight:900}.legend{position:absolute;z-index:500;left:12px;bottom:12px;display:grid;gap:5px;padding:8px 10px;border-radius:9px;background:rgba(255,255,255,.96);box-shadow:0 2px 8px rgba(20,42,80,.16);font-size:.7rem;pointer-events:none}.legend span{display:flex;align-items:center;gap:7px}.swatch{display:inline-block;width:13px;height:13px;border:2px solid #fff;border-radius:50%;box-shadow:0 0 0 1px #40556a}.swatch.area{width:28px;border:2px solid #2f694d;border-radius:3px;background:rgba(117,170,135,.42)}.both{background:var(--green)}.area-only{background:var(--orange)}.road-only{background:var(--blue)}.map-alt{margin:0;padding:10px 14px;border-top:1px solid var(--line);color:var(--muted);font-size:.78rem}.side{display:grid;gap:12px}.summary{padding:15px;border-top:7px solid var(--teal)}.summary h2{margin:0;font-size:1.25rem}.summary p{margin:3px 0 0}.counts{display:grid;grid-template-columns:repeat(2,1fr);gap:7px;margin:12px 0 0;padding:0;list-style:none}.counts li{padding:9px;border-radius:9px;background:#eef3f6}.counts strong{display:block;font-size:1.2rem}.counts small{color:var(--muted)}.difference{margin-top:10px;padding:10px;border-left:4px solid var(--orange);background:#fff7e8;font-weight:900}.results{padding:15px}.results h2{margin:0;font-size:1rem}.result-list{display:grid;gap:6px;max-height:440px;margin:10px 0 0;padding:0;overflow:auto;list-style:none}.result-list button{display:grid;grid-template-columns:13px 1fr;gap:8px;width:100%;min-height:44px;padding:8px;border:1px solid #d6e0e5;border-radius:8px;background:#f9fbfc;color:var(--ink);text-align:left;cursor:pointer}.result-list button[aria-current="true"]{border:3px solid var(--navy);background:#e7f2f7}.result-list i{width:11px;height:11px;margin-top:5px;border-radius:50%}.result-list strong,.result-list small{display:block}.result-list small{color:var(--muted);font-size:.7rem}.zero{padding:12px;border-radius:9px;background:#eef3f6;color:var(--muted);font-weight:800}.method{padding:15px}.method h2{margin:0;font-size:1rem}.method dl{margin:8px 0 0}.method dt{margin-top:8px;font-weight:900}.method dd{margin:1px 0 0;color:var(--muted);font-size:.78rem}.source{margin-top:14px;padding:12px;border:1px solid var(--line);border-radius:10px;background:#fff;color:var(--muted);font-size:.72rem;overflow-wrap:anywhere}:focus-visible{outline:3px solid var(--focus);outline-offset:3px}@media(max-width:760px){main{padding:9px}.controls,.layout{grid-template-columns:1fr}.controls{padding:11px}#map{height:54vh;min-height:390px}.side{gap:9px}.counts{grid-template-columns:1fr 1fr}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition-duration:.01ms!important;animation-duration:.01ms!important;animation-iteration-count:1!important}}
</style></head><body>
<header><h1>施設の判定方法を比べる</h1><p>受入済みの住民画面とは別に、「表示面の内側」と「暫定道路試算が時間内」の違いだけを確認する内部技術画面です。</p></header>
<main id="main"><section class="notice"><strong>このページは、どちらが正解かを決める画面ではありません。</strong>2つは距離の使い方が違います。暫定道路試算は、バス停と施設をそれぞれ最寄りの道路上の地点へつなぎます。入口、歩道、横断安全性、営業時間、利用条件、帰りの便は未確認です。</section>
<section class="notice"><strong>道路上の地点へ接続した再試算</strong>__EDGE_SNAP_FINDING__</section>
<section class="notice reference"><strong>外部参考（2026-09-01）：以前の市役所5分で確認した4施設は、Googleマップ徒歩ではすべて4～5分でした。</strong>友田ファミリークリニック5分・350m、村岡整形外科5分・400m、三吉歯科5分・350m、山元歯科医院4分・300mです。その時点の手動確認であり、経路形状は保存・転載せず、この画面の判定入力にも使っていません。</section>
<section class="controls" aria-label="比較条件"><div class="field"><label for="stop-select">試験するバス停</label><select id="stop-select">__STOP_OPTIONS__</select></div><div><span class="time-label" id="time-label">歩く時間（仮条件）</span><div class="time-buttons" aria-labelledby="time-label"><button type="button" data-minutes="5" aria-pressed="false">5分</button><button type="button" data-minutes="10" aria-pressed="true">10分</button><button type="button" data-minutes="15" aria-pressed="false">15分</button></div></div></section>
<div class="layout"><article class="card" aria-labelledby="map-title"><div class="card-head"><h2 id="map-title">岩国駅・10分の比較地図</h2><p>現在の表示面と暫定道路試算を、正誤ではなく方法の違いとして色分けします。</p></div><div class="map-frame"><div id="map" role="region" aria-label="岩国駅バス停の10分比較地図"></div><div class="legend" aria-hidden="true"><span><i class="swatch area"></i>現在の試験用表示面</span><span><i class="swatch both"></i>2つの方法で同じ結果</span><span><i class="swatch area-only"></i>表示面では内側</span><span><i class="swatch road-only"></i>暫定道路試算では時間内</span></div></div><p class="map-alt" id="map-alt">文字での比較結果を準備しています。</p></article>
<aside class="side"><section class="card summary" aria-labelledby="summary-title"><h2 id="summary-title">岩国駅・10分</h2><p id="summary-status" aria-live="polite">比較結果を準備しています。</p><ul class="counts" id="counts" aria-label="比較結果の施設数"><li><strong id="matched-count">0件</strong><small>2つの方法で同じ結果</small></li><li><strong id="needs-check-count">0件</strong><small>計算方法で結果が分かれる</small></li></ul><div class="difference" id="check-reasons"><strong>結果が分かれた内訳</strong><ul><li>表示面では内側、暫定道路試算では時間外：<strong id="area-needs-check">0件</strong></li><li>暫定道路試算では時間内、表示面では外側：<strong id="road-needs-check">0件</strong></li></ul></div><p class="zero" id="unconnected">保存道路がつながらず計算できない施設：0件</p><details><summary>参考：2つの方法とも時間外の施設</summary><p id="not-in-time"></p></details></section><section class="card results" aria-labelledby="results-title"><h2 id="results-title">時間内になった施設と、方法で結果が分かれた施設</h2><p class="zero" id="zero" hidden>この条件では、方法による結果の違いは0件です。</p><ul class="result-list" id="result-list" aria-label="施設ごとの比較結果"></ul></section><section class="card method" aria-labelledby="method-title"><h2 id="method-title">2つの見方</h2><dl><dt>表示面（現在の緑）</dt><dd>道路到達線に40mの仮幅を付けて作った面の内側に、施設座標があるか。</dd><dt>暫定道路試算（保存OSM）</dt><dd>バス停と施設を最寄りの道路上の地点へつなぎ、その間の保存道路上の最短距離と両端の仮接続を足して、時間の距離枠内か。</dd><dt>まだ分からないこと</dt><dd>仮接続が本当に歩けるか、入口・坂・歩道・安全・営業時間・利用条件・往復行程。</dd></dl></section></aside></div>
<p class="source" id="source-record"></p></main>
<script type="application/json" id="comparison-data">__PAYLOAD__</script>
<script src="__LEAFLET_JS_URL__" integrity="__LEAFLET_JS_INTEGRITY__" crossorigin="anonymous"></script>
<script>
(function(){const payload=JSON.parse(document.getElementById("comparison-data").textContent);const facilityById=new Map(payload.facility_records.map(function(item){return [item.facility_id,item];}));const stopSelect=document.getElementById("stop-select");const mapNode=document.getElementById("map");const mapTitle=document.getElementById("map-title");const summaryTitle=document.getElementById("summary-title");const summaryStatus=document.getElementById("summary-status");const matchedCount=document.getElementById("matched-count");const needsCheckCount=document.getElementById("needs-check-count");const areaNeedsCheck=document.getElementById("area-needs-check");const roadNeedsCheck=document.getElementById("road-needs-check");const unconnected=document.getElementById("unconnected");const notInTime=document.getElementById("not-in-time");const resultList=document.getElementById("result-list");const zero=document.getElementById("zero");const alt=document.getElementById("map-alt");document.getElementById("source-record").textContent="保存GTFS："+payload.metadata.sources.gtfs.path+"（SHA-256 "+payload.metadata.sources.gtfs.sha256+"）｜保存OSM："+payload.metadata.sources.osm.path+"（SHA-256 "+payload.metadata.sources.osm.sha256+"）｜保存公式施設："+payload.metadata.sources.facilities.path+"（SHA-256 "+payload.metadata.sources.facilities.sha256+"）｜受入済み住民画面："+payload.metadata.sources.accepted_resident_prototype.sha256;
if(typeof L==="undefined"){mapNode.className="map-fallback";mapNode.textContent="地図を読み込めませんでした。右側の文字による比較結果は確認できます。";return;}const map=L.map("map",{scrollWheelZoom:false});L.tileLayer("__OSM_TILE_URL__",{maxZoom:19,attribution:'__OSM_ATTRIBUTION__',crossOrigin:true}).on("tileerror",function(){summaryStatus.textContent="背景地図の一部を読み込めませんでした。比較件数は保存済みデータで確認できます。";}).addTo(map);let selectedMinutes=10;let selectedStop=payload.stops.find(function(item){return item.stop.stop_id===payload.metadata.default_stop_id;})||payload.stops[0];let areaLayer=null;let facilityLayer=null;let selectedFacilityId=null;const markerById=new Map();const stopLayer=L.layerGroup().addTo(map);const stopMarkerById=new Map();payload.stops.forEach(function(item){const stop=item.stop;const marker=L.circleMarker([stop.stop_lat,stop.stop_lon],{radius:9,color:"#fff",weight:3,fillColor:"#607b8c",fillOpacity:1}).addTo(stopLayer);marker.bindTooltip(stop.stop_name);marker.on("click",function(){showStop(stop.stop_id);});stopMarkerById.set(stop.stop_id,marker);const element=marker.getElement();if(element){element.setAttribute("role","button");element.setAttribute("tabindex","0");element.setAttribute("aria-label",stop.stop_name+"バス停を選択");element.addEventListener("keydown",function(event){if(event.key==="Enter"||event.key===" "){event.preventDefault();showStop(stop.stop_id);}});}});
function classMeta(key){return payload.metadata.classifications.find(function(item){return item.key===key;});}function roadDescription(comparison){if(!comparison.road_distance_available){return "暫定道路試算は未接続（施設側の仮接続 "+comparison.facility_snap_distance_m.toFixed(1)+"m）";}return "暫定道路試算 "+comparison.estimated_access_distance_m.toFixed(1)+"m（道路 "+comparison.graph_distance_m.toFixed(1)+"m、両端の仮接続 "+(comparison.stop_snap_distance_m+comparison.facility_snap_distance_m).toFixed(1)+"m）";}function updateStops(){stopMarkerById.forEach(function(marker,stopId){const selected=stopId===selectedStop.stop.stop_id;marker.setRadius(selected?12:9);marker.setStyle({fillColor:selected?"#123c59":"#607b8c",weight:selected?4:3});const element=marker.getElement();if(element){element.setAttribute("aria-pressed",String(selected));}});}
function focusFacility(facilityId){const marker=markerById.get(facilityId);const facility=facilityById.get(facilityId);if(!marker||!facility){return;}selectedFacilityId=facilityId;markerById.forEach(function(item,id){const comparison=selectedStop.facility_comparisons.find(function(value){return value.facility_id===id;});const meta=classMeta(comparison.by_minutes[String(selectedMinutes)].classification);item.setRadius(id===facilityId?10:6);item.setStyle({color:id===facilityId?"#ffb900":"#fff",weight:id===facilityId?4:2,fillColor:meta.color,fillOpacity:1});});marker.bringToFront();marker.openPopup();let chosen=null;resultList.querySelectorAll("[data-facility-id]").forEach(function(button){const selected=button.dataset.facilityId===facilityId;button.setAttribute("aria-current",String(selected));if(selected){chosen=button;}});if(chosen){chosen.scrollIntoView({block:"nearest"});}summaryStatus.textContent=facility.facility_name+"の比較詳細を表示しました。";}
function render(){const key=String(selectedMinutes);const summary=selectedStop.summaries[key];const feature=selectedStop.area_features.find(function(item){return String(item.properties.minutes)===key;});if(areaLayer){map.removeLayer(areaLayer);}if(facilityLayer){map.removeLayer(facilityLayer);}areaLayer=L.geoJSON(feature,{style:{color:"#2f694d",weight:2,fillColor:"#75aa87",fillOpacity:.3},interactive:false}).addTo(map);facilityLayer=L.layerGroup().addTo(map);markerById.clear();selectedFacilityId=null;matchedCount.textContent=summary.classification_counts.both+"件";needsCheckCount.textContent=summary.difference_count+"件";areaNeedsCheck.textContent=summary.classification_counts.area_only+"件";roadNeedsCheck.textContent=summary.classification_counts.road_only+"件";unconnected.textContent="保存道路がつながらず計算できない施設："+summary.road_distance_unavailable_count+"件";notInTime.textContent=summary.classification_counts.neither+"件です。ここには、保存道路がつながらず暫定道路試算ができない施設が含まれる場合があります。";const shown=selectedStop.facility_comparisons.filter(function(item){return item.by_minutes[key].classification!=="neither";}).sort(function(a,b){const order={area_only:0,road_only:1,both:2};const aClass=a.by_minutes[key].classification;const bClass=b.by_minutes[key].classification;const aFacility=facilityById.get(a.facility_id);const bFacility=facilityById.get(b.facility_id);return order[aClass]-order[bClass]||aFacility.facility_name.localeCompare(bFacility.facility_name,"ja");});resultList.replaceChildren();shown.forEach(function(comparison){const facility=facilityById.get(comparison.facility_id);const classification=comparison.by_minutes[key].classification;const meta=classMeta(classification);const marker=L.circleMarker([facility.latitude,facility.longitude],{radius:6,color:"#fff",weight:2,fillColor:meta.color,fillOpacity:1}).addTo(facilityLayer);const popup=document.createElement("div");const name=document.createElement("strong");name.textContent=facility.facility_name;const detail=document.createElement("div");detail.textContent=meta.label+"｜"+roadDescription(comparison);popup.append(name,detail);marker.bindPopup(popup,{autoPan:false});marker.on("click",function(){focusFacility(facility.facility_id);});markerById.set(facility.facility_id,marker);const li=document.createElement("li");const button=document.createElement("button");button.type="button";button.dataset.facilityId=facility.facility_id;button.setAttribute("aria-current","false");button.setAttribute("aria-label",facility.facility_name+"。"+meta.label+"。"+roadDescription(comparison));const dot=document.createElement("i");dot.style.backgroundColor=meta.color;dot.setAttribute("aria-hidden","true");const text=document.createElement("span");const title=document.createElement("strong");title.textContent=facility.facility_name;const detailText=document.createElement("small");detailText.textContent=meta.label+"｜"+roadDescription(comparison);text.append(title,detailText);button.append(dot,text);li.appendChild(button);resultList.appendChild(li);});zero.hidden=summary.difference_count!==0;resultList.hidden=shown.length===0;summaryTitle.textContent=selectedStop.stop.stop_name+"・"+selectedMinutes+"分";summaryStatus.textContent="2つの方法で同じ結果の施設は"+summary.classification_counts.both+"件、計算方法で結果が分かれる施設は"+summary.difference_count+"件です。";mapTitle.textContent=selectedStop.stop.stop_name+"・"+selectedMinutes+"分の比較地図";alt.textContent="文字での説明："+selectedStop.stop.stop_name+"の"+selectedMinutes+"分条件で、2つの方法で同じ結果の施設は"+summary.classification_counts.both+"件、計算方法で結果が分かれる施設は"+summary.difference_count+"件、2つの方法とも時間外の施設は"+summary.classification_counts.neither+"件です。保存道路がつながらず暫定道路試算ができない施設は"+summary.road_distance_unavailable_count+"件です。";mapNode.setAttribute("aria-label",selectedStop.stop.stop_name+"バス停の"+selectedMinutes+"分比較地図");const bounds=areaLayer.getBounds();payload.stops.forEach(function(item){bounds.extend([item.stop.stop_lat,item.stop.stop_lon]);});if(bounds.isValid()){map.fitBounds(bounds,{padding:[28,28],maxZoom:16,animate:false});}document.querySelectorAll("[data-minutes]").forEach(function(button){button.setAttribute("aria-pressed",String(Number(button.dataset.minutes)===selectedMinutes));});updateStops();}
function showStop(stopId){selectedStop=payload.stops.find(function(item){return item.stop.stop_id===stopId;})||payload.stops[0];stopSelect.value=selectedStop.stop.stop_id;render();}stopSelect.addEventListener("change",function(){showStop(stopSelect.value);});document.querySelector(".time-buttons").addEventListener("click",function(event){const button=event.target.closest("[data-minutes]");if(button){selectedMinutes=Number(button.dataset.minutes);render();}});resultList.addEventListener("click",function(event){const button=event.target.closest("[data-facility-id]");if(button){focusFacility(button.dataset.facilityId);}});showStop(payload.metadata.default_stop_id);})();
</script></body></html>'''


def render_html(payload: dict[str, Any]) -> str:
    options = []
    for stop_record in payload["stops"]:
        stop = stop_record["stop"]
        selected = " selected" if stop["stop_id"] == payload["metadata"]["default_stop_id"] else ""
        options.append(
            f'<option value="{html.escape(stop["stop_id"], quote=True)}"{selected}>'
            f'{html.escape(stop["stop_name"])}</option>'
        )
    embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    city_hall = next(
        stop for stop in payload["stops"]
        if stop["stop"]["stop_name"] == "市役所"
    )
    city_hall_differences = [
        city_hall["summaries"][str(minutes)]["difference_count"]
        for minutes in network_builder.MINUTES
    ]
    edge_snap_finding = (
        "市役所では、結果が分かれる施設が"
        "5分7件・10分3件・15分4件から、"
        f"5分{city_hall_differences[0]}件・"
        f"10分{city_hall_differences[1]}件・"
        f"15分{city_hall_differences[2]}件になりました。"
        "5分で残る1件は村岡整形外科です。"
    )
    return (
        HTML_TEMPLATE
        .replace("__LEAFLET_CSS_URL__", LEAFLET_CSS_URL)
        .replace("__LEAFLET_CSS_INTEGRITY__", LEAFLET_CSS_INTEGRITY)
        .replace("__LEAFLET_JS_URL__", LEAFLET_JS_URL)
        .replace("__LEAFLET_JS_INTEGRITY__", LEAFLET_JS_INTEGRITY)
        .replace("__OSM_TILE_URL__", OSM_TILE_URL)
        .replace("__OSM_ATTRIBUTION__", OSM_ATTRIBUTION)
        .replace("__STOP_OPTIONS__", "".join(options))
        .replace("__EDGE_SNAP_FINDING__", html.escape(edge_snap_finding))
        .replace("__PAYLOAD__", embedded)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gtfs-input", type=Path, default=resident_builder.GTFS_INPUT)
    parser.add_argument("--osm-input", type=Path, default=resident_builder.OSM_INPUT)
    parser.add_argument("--facility-input", type=Path, default=resident_builder.FACILITY_INPUT)
    parser.add_argument("--accepted-prototype", type=Path, default=resident_builder.HTML_OUTPUT)
    parser.add_argument("--output", type=Path, default=HTML_OUTPUT)
    args = parser.parse_args()
    payload = build_comparison_payload(
        args.gtfs_input,
        args.osm_input,
        args.facility_input,
        args.accepted_prototype,
    )
    rendered = render_html(payload).encode("utf-8")
    args.output.write_bytes(rendered)
    print(
        f"WROTE {args.output} bytes={len(rendered)} "
        f"sha256={hashlib.sha256(rendered).hexdigest()}"
    )
    for stop_record in payload["stops"]:
        for minutes in payload["metadata"]["minutes"]:
            summary = stop_record["summaries"][str(minutes)]
            counts = summary["classification_counts"]
            print(
                f"RESULT stop={stop_record['stop']['stop_id']} minutes={minutes} "
                f"both={counts['both']} area_only={counts['area_only']} "
                f"road_only={counts['road_only']} neither={counts['neither']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
