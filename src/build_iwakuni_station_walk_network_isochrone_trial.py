"""Build a small, reproducible walk-network trial around Iwakuni Station.

The trial uses a saved OpenStreetMap Overpass response and the saved Iwakuni
GTFS archive.  It calculates distance on OSM road geometry with a small
standard-library Dijkstra implementation.  The output deliberately draws
reachable road lines instead of inventing a filled isochrone polygon.

This is not an accepted walking specification.  The temporary 80 m/min speed,
OSM pedestrian-tag filter, and 5/10/15-minute controls exist only to test the
resident-facing map idea with real road topology.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import heapq
import io
import json
import math
from pathlib import Path
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RAW_OSM = ROOT / "raw" / "osm" / "iwakuni_station_walk_network_overpass_20260829.json"
GTFS_ARCHIVE = ROOT / "raw" / "gtfs" / "iwakuni_gtfsjp_20260401.zip"
GEOJSON_OUTPUT = ROOT / "data" / "iwakuni_station_walk_network_isochrone_trial.geojson"
HTML_OUTPUT = ROOT / "internal" / "work1_leaflet_network_isochrone_trial.html"

GTFS_MEMBER = "stops.txt"
STOP_ID = "684_01"
BUILD_DATE = "2026-08-29"
MINUTES = (5, 10, 15)
TEMPORARY_SPEED_METERS_PER_MINUTE = 80
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
OVERPASS_BBOX = [34.1543, 132.2026, 34.1903, 132.2466]
OVERPASS_QUERY = (
    '[out:json][timeout:60];('
    'way["highway"](34.1543,132.2026,34.1903,132.2466);'
    'nwr["natural"="water"](34.1543,132.2026,34.1903,132.2466);'
    'nwr["waterway"="riverbank"](34.1543,132.2026,34.1903,132.2466);'
    'way["waterway"~"river|stream|canal"](34.1543,132.2026,34.1903,132.2466);'
    ');out body geom;'
)

LEAFLET_VERSION = "1.9.4"
LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_CSS_INTEGRITY = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
LEAFLET_JS_INTEGRITY = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
GSI_PALE_TILE_URL = "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png"

ALWAYS_EXCLUDED_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "construction",
    "proposed",
    "raceway",
}
CONSERVATIVE_HIGHWAYS = {"trunk", "trunk_link"}
FOOT_ALLOWED_VALUES = {"yes", "designated", "permissive"}
FOOT_DENIED_VALUES = {"no", "private", "use_sidepath"}
ACCESS_DENIED_VALUES = {"no", "private"}


def file_record(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_stop() -> dict[str, Any]:
    with zipfile.ZipFile(GTFS_ARCHIVE) as archive:
        text = archive.read(GTFS_MEMBER).decode("utf-8-sig")
    matches = [
        row
        for row in csv.DictReader(io.StringIO(text, newline=""))
        if row.get("stop_id") == STOP_ID
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one {STOP_ID} row, found {len(matches)}")
    row = matches[0]
    if row["stop_name"] != "岩国駅":
        raise ValueError(f"unexpected stop name: {row['stop_name']!r}")
    return {
        "stop_id": row["stop_id"],
        "stop_name": row["stop_name"],
        "stop_lat": float(row["stop_lat"]),
        "stop_lon": float(row["stop_lon"]),
        "location_type": row.get("location_type", ""),
    }


def haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    radius = 6_371_008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    value = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def walking_rejection_reason(tags: dict[str, str]) -> str | None:
    highway = tags.get("highway")
    foot = tags.get("foot")
    access = tags.get("access")
    if not highway:
        return "not_highway"
    if highway in ALWAYS_EXCLUDED_HIGHWAYS:
        return f"excluded_highway:{highway}"
    if foot in FOOT_DENIED_VALUES:
        return f"foot:{foot}"
    if access in ACCESS_DENIED_VALUES and foot not in FOOT_ALLOWED_VALUES:
        return f"access:{access}"
    if highway in CONSERVATIVE_HIGHWAYS and foot not in FOOT_ALLOWED_VALUES:
        return f"conservative_highway:{highway}"
    return None


def build_graph(osm: dict[str, Any]) -> dict[str, Any]:
    coordinates: dict[int, tuple[float, float]] = {}
    adjacency: dict[int, list[tuple[int, float, int]]] = {}
    edges: list[dict[str, Any]] = []
    accepted_way_count = 0
    rejection_reasons: Counter[str] = Counter()
    highway_types: Counter[str] = Counter()

    for element in osm.get("elements", []):
        tags = element.get("tags", {})
        if element.get("type") != "way" or "highway" not in tags:
            continue
        reason = walking_rejection_reason(tags)
        if reason:
            rejection_reasons[reason] += 1
            continue
        node_ids = element.get("nodes", [])
        geometry = element.get("geometry", [])
        if len(node_ids) != len(geometry) or len(node_ids) < 2:
            rejection_reasons["missing_or_misaligned_geometry"] += 1
            continue
        accepted_way_count += 1
        highway_types[tags["highway"]] += 1
        is_bridge = tags.get("bridge") not in {None, "", "no"}
        for node_id, point in zip(node_ids, geometry):
            coordinates[node_id] = (float(point["lon"]), float(point["lat"]))
        for index, (u, v) in enumerate(zip(node_ids, node_ids[1:])):
            length = haversine_meters(coordinates[u], coordinates[v])
            if length <= 0:
                continue
            edge_index = len(edges)
            edge = {
                "edge_id": f"{element['id']}:{index}",
                "way_id": element["id"],
                "u": u,
                "v": v,
                "length_m": length,
                "highway": tags["highway"],
                "name": tags.get("name"),
                "is_bridge": is_bridge,
                "bridge": tags.get("bridge"),
                "surface": tags.get("surface"),
                "foot": tags.get("foot"),
                "access": tags.get("access"),
            }
            edges.append(edge)
            adjacency.setdefault(u, []).append((v, length, edge_index))
            adjacency.setdefault(v, []).append((u, length, edge_index))

    return {
        "coordinates": coordinates,
        "adjacency": adjacency,
        "edges": edges,
        "accepted_way_count": accepted_way_count,
        "rejection_reasons": dict(sorted(rejection_reasons.items())),
        "highway_types": dict(sorted(highway_types.items())),
    }


def nearest_node(
    coordinates: dict[int, tuple[float, float]],
    point: tuple[float, float],
) -> tuple[int, float]:
    if not coordinates:
        raise ValueError("walk graph has no coordinates")
    return min(
        ((node_id, haversine_meters(point, coordinate)) for node_id, coordinate in coordinates.items()),
        key=lambda item: item[1],
    )


def dijkstra(
    adjacency: dict[int, list[tuple[int, float, int]]],
    start_node: int,
) -> dict[int, float]:
    distances = {start_node: 0.0}
    queue = [(0.0, start_node)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        for neighbor, length, _edge_index in adjacency.get(node, []):
            candidate = distance + length
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return distances


def interpolate(
    a: tuple[float, float],
    b: tuple[float, float],
    fraction: float,
) -> list[float]:
    fraction = max(0.0, min(1.0, fraction))
    return [
        round(a[0] + (b[0] - a[0]) * fraction, 7),
        round(a[1] + (b[1] - a[1]) * fraction, 7),
    ]


def reachable_parts(
    edge: dict[str, Any],
    coordinates: dict[int, tuple[float, float]],
    distances: dict[int, float],
    budget_m: float,
) -> list[tuple[list[list[float]], float]]:
    u = edge["u"]
    v = edge["v"]
    a = coordinates[u]
    b = coordinates[v]
    length = edge["length_m"]
    from_u = max(0.0, min(length, budget_m - distances.get(u, math.inf)))
    from_v = max(0.0, min(length, budget_m - distances.get(v, math.inf)))
    if from_u <= 0 and from_v <= 0:
        return []
    if from_u + from_v >= length - 1e-6:
        return [([[round(a[0], 7), round(a[1], 7)], [round(b[0], 7), round(b[1], 7)]], length)]
    parts: list[tuple[list[list[float]], float]] = []
    if from_u > 0:
        parts.append(([[round(a[0], 7), round(a[1], 7)], interpolate(a, b, from_u / length)], from_u))
    if from_v > 0:
        parts.append(([[round(b[0], 7), round(b[1], 7)], interpolate(b, a, from_v / length)], from_v))
    return parts


def water_features(osm: dict[str, Any]) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for element in osm.get("elements", []):
        tags = element.get("tags", {})
        is_water = (
            tags.get("natural") == "water"
            or tags.get("waterway") in {"riverbank", "river", "stream", "canal"}
        )
        if not is_water:
            continue
        if element.get("type") == "way" and element.get("geometry"):
            coords = [
                [round(float(point["lon"]), 7), round(float(point["lat"]), 7)]
                for point in element["geometry"]
            ]
            closed = len(coords) >= 4 and coords[0] == coords[-1]
            geometry = {
                "type": "Polygon" if closed else "LineString",
                "coordinates": [coords] if closed else coords,
            }
            features.append({
                "type": "Feature",
                "properties": {
                    "kind": "water",
                    "osm_type": "way",
                    "osm_id": element["id"],
                    "name": tags.get("name"),
                    "natural": tags.get("natural"),
                    "water": tags.get("water"),
                    "waterway": tags.get("waterway"),
                },
                "geometry": geometry,
            })
        elif element.get("type") == "relation":
            for member_index, member in enumerate(element.get("members", [])):
                geometry = member.get("geometry") or []
                if len(geometry) < 2:
                    continue
                coords = [
                    [round(float(point["lon"]), 7), round(float(point["lat"]), 7)]
                    for point in geometry
                ]
                features.append({
                    "type": "Feature",
                    "properties": {
                        "kind": "water_relation_member",
                        "osm_type": "relation",
                        "osm_id": element["id"],
                        "member_index": member_index,
                        "role": member.get("role"),
                        "name": tags.get("name"),
                    },
                    "geometry": {"type": "LineString", "coordinates": coords},
                })
    return features


def build_geojson() -> dict[str, Any]:
    osm = load_json(RAW_OSM)
    stop = load_stop()
    graph = build_graph(osm)
    stop_point = (stop["stop_lon"], stop["stop_lat"])
    snap_node, snap_distance = nearest_node(graph["coordinates"], stop_point)
    distances = dijkstra(graph["adjacency"], snap_node)

    features = water_features(osm)
    summaries: dict[str, dict[str, Any]] = {}
    for minutes in MINUTES:
        budget = minutes * TEMPORARY_SPEED_METERS_PER_MINUTE
        segment_count = 0
        bridge_segment_count = 0
        displayed_length = 0.0
        for edge in graph["edges"]:
            for part_index, (coordinates, length) in enumerate(
                reachable_parts(edge, graph["coordinates"], distances, budget)
            ):
                segment_count += 1
                displayed_length += length
                if edge["is_bridge"]:
                    bridge_segment_count += 1
                features.append({
                    "type": "Feature",
                    "properties": {
                        "kind": "reachable_road",
                        "minutes": minutes,
                        "budget_m": budget,
                        "edge_id": edge["edge_id"],
                        "part_index": part_index,
                        "way_id": edge["way_id"],
                        "highway": edge["highway"],
                        "name": edge["name"],
                        "is_bridge": edge["is_bridge"],
                        "bridge": edge["bridge"],
                        "surface": edge["surface"],
                        "foot": edge["foot"],
                        "access": edge["access"],
                        "segment_length_m": round(length, 3),
                    },
                    "geometry": {"type": "LineString", "coordinates": coordinates},
                })
        summaries[str(minutes)] = {
            "budget_m": budget,
            "segment_count": segment_count,
            "bridge_segment_count": bridge_segment_count,
            "displayed_road_length_m": round(displayed_length, 1),
            "reachable_node_count": sum(1 for value in distances.values() if value <= budget),
        }

    features.append({
        "type": "Feature",
        "properties": {
            "kind": "selected_stop",
            "stop_id": stop["stop_id"],
            "stop_name": stop["stop_name"],
        },
        "geometry": {"type": "Point", "coordinates": [stop["stop_lon"], stop["stop_lat"]]},
    })
    snap_coordinate = graph["coordinates"][snap_node]
    features.append({
        "type": "Feature",
        "properties": {
            "kind": "graph_snap",
            "node_id": snap_node,
            "snap_distance_m": round(snap_distance, 3),
        },
        "geometry": {"type": "Point", "coordinates": list(snap_coordinate)},
    })

    return {
        "type": "FeatureCollection",
        "metadata": {
            "task_id": "WORK1-IWAKUNI-WALK-NETWORK-ISOCHRONE-TRIAL-1",
            "status": "LOCAL_TECHNICAL_TRIAL_NOT_ACCEPTED_PRODUCT_SPEC",
            "build_date": BUILD_DATE,
            "calculation": {
                "algorithm": "Dijkstra on saved OSM highway geometry",
                "temporary_speed_m_per_min": TEMPORARY_SPEED_METERS_PER_MINUTE,
                "minutes": list(MINUTES),
                "filled_polygon_created": False,
                "slope_used": False,
                "field_walkability_verified": False,
            },
            "osm_source": {
                **file_record(RAW_OSM),
                "endpoint": OVERPASS_ENDPOINT,
                "query": OVERPASS_QUERY,
                "bbox_south_west_north_east": OVERPASS_BBOX,
                "osm_base_timestamp": osm.get("osm3s", {}).get("timestamp_osm_base"),
                "generator": osm.get("generator"),
                "encoding": "UTF-8",
                "crs": "WGS84 (EPSG:4326)",
                "licence": "OpenStreetMap data © OpenStreetMap contributors, ODbL 1.0",
                "licence_url": "https://www.openstreetmap.org/copyright",
            },
            "gtfs_source": {**file_record(GTFS_ARCHIVE), "member": GTFS_MEMBER},
            "stop": stop,
            "graph": {
                "accepted_way_count": graph["accepted_way_count"],
                "edge_count": len(graph["edges"]),
                "node_count": len(graph["coordinates"]),
                "snap_node": snap_node,
                "snap_distance_m": round(snap_distance, 3),
                "highway_types": graph["highway_types"],
                "rejection_reasons": graph["rejection_reasons"],
            },
            "water_feature_count": sum(
                feature["properties"]["kind"].startswith("water")
                for feature in features
            ),
            "summaries": summaries,
            "boundaries": {
                "target_region": "岩国駅周辺は今回の技術試験範囲であり、最終対象地域ではない",
                "walking_condition": "80m/分と5・10・15分は仮条件で、本人またはチームの決定ではない",
                "water": "保存OSMの水域・河川を表示するが、水域網羅性や全横断箇所は現地確認していない",
                "bridge": "OSMでbridgeタグがある到達道路を強調する。タグの完全性は現地確認していない",
                "scope": "生活施設、点数、順位、マトリクス、自治体向け分析、自宅、完全行程を含めない",
            },
        },
        "features": features,
    }


def serialize_geojson(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


HTML_TEMPLATE = r'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <meta name="work1-prototype-status" content="LOCAL_TECHNICAL_TRIAL_NOT_ACCEPTED_PRODUCT_SPEC">
  <meta http-equiv="Permissions-Policy" content="geolocation=(), camera=(), microphone=()">
  <title>岩国駅から実際の道でどこまで歩ける？｜実道路の小規模試験</title>
  <link rel="stylesheet" href="__LEAFLET_CSS_URL__" integrity="__LEAFLET_CSS_INTEGRITY__" crossorigin="">
  <style>
    :root{--ink:#14263b;--muted:#5b6b7e;--paper:#eef3f6;--card:#fff;--line:#d5dee6;--navy:#063b70;--teal:#087f8c;--teal-soft:#e4f6f7;--bridge:#d45b16;--water:#4098cf;--amber:#7b5200;--amber-soft:#fff3d6}
    *{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--paper);color:var(--ink)}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP","Yu Gothic",Meiryo,sans-serif;line-height:1.6}button{font:inherit}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #ffb900;outline-offset:3px}.skip{position:fixed;left:12px;top:-80px;z-index:1200;padding:10px 14px;border-radius:8px;background:#fff;color:var(--navy);font-weight:800}.skip:focus{top:12px}
    header{display:flex;align-items:end;justify-content:space-between;gap:20px;padding:18px max(18px,calc((100vw - 1280px)/2));background:linear-gradient(120deg,#07386d,#087b8f);color:#fff}.eyebrow{margin:0 0 3px;font-size:.76rem;font-weight:900;letter-spacing:.07em}h1{margin:0;font-size:clamp(1.35rem,3.1vw,2.05rem);line-height:1.25}.lead{margin:5px 0 0;color:#e5f7fa;font-size:.9rem}.badge{flex:0 0 auto;padding:6px 11px;border:1px solid rgba(255,255,255,.7);border-radius:999px;background:rgba(255,255,255,.12);font-size:.75rem;font-weight:800}
    main{width:min(1280px,100%);margin:0 auto;padding:16px}.scope{display:flex;gap:11px;align-items:center;margin-bottom:12px;padding:11px 13px;border:1px solid #9bcbd0;border-radius:12px;background:var(--teal-soft);color:#174b55;font-size:.85rem}.scope b{white-space:nowrap}.layout{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:14px;align-items:start}.card{min-width:0;border:1px solid var(--line);border-radius:15px;background:var(--card);box-shadow:0 10px 28px rgba(18,43,79,.09);overflow:hidden}
    .map-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px}.map-head h2,.panel h2{margin:0;font-size:1.06rem}.map-sub{margin:2px 0 0;color:var(--muted);font-size:.78rem}.time-buttons{display:flex;gap:6px}.time-buttons button{min-width:56px;min-height:44px;padding:7px 10px;border:1px solid #aab9c4;border-radius:9px;background:#fff;color:var(--ink);font-weight:900;cursor:pointer}.time-buttons button[aria-pressed="true"]{border-color:var(--navy);background:var(--navy);color:#fff}
    .map-frame{position:relative}#map{width:100%;height:min(68vh,680px);min-height:480px;background:#dfe9ed}.map-fallback{display:grid;place-items:center;height:100%;padding:30px;text-align:center;color:#6d2f00;background:#fff4df;font-weight:800}.legend{position:absolute;z-index:500;left:12px;bottom:12px;display:grid;gap:4px;padding:7px 9px;border:1px solid rgba(9,73,122,.18);border-radius:8px;background:rgba(255,255,255,.95);color:#25425e;font-size:.68rem;box-shadow:0 2px 8px rgba(20,42,80,.14);pointer-events:none}.legend span{display:flex;align-items:center;gap:6px}.swatch{display:inline-block;width:24px;height:5px;border-radius:4px}.road{background:#07828d}.bridge{background:repeating-linear-gradient(90deg,#d45b16 0 6px,transparent 6px 10px);border:1px solid #d45b16}.water{background:#4098cf}.map-alt{padding:10px 15px;border-top:1px solid var(--line);font-size:.8rem;color:var(--muted)}
    .side{display:grid;gap:12px}.panel{padding:16px}.kicker{margin:0 0 4px;color:var(--navy);font-size:.73rem;font-weight:900;letter-spacing:.05em}.stop-name{margin:0;font-size:1.5rem;line-height:1.25}.status{margin:12px 0;padding:12px;border-left:5px solid var(--teal);border-radius:5px 10px 10px 5px;background:var(--teal-soft);font-weight:800}.plain-guide{margin:0;color:#314b61;font-size:.88rem}.notice{margin:10px 0 0;padding:10px 11px;border-radius:9px;background:var(--amber-soft);color:#654500;font-size:.81rem}.facts{display:grid;gap:8px;margin:10px 0 0;padding:0;list-style:none}.facts li{padding:9px 10px;border-radius:9px;background:#f3f6f8}.facts b{display:block;font-size:.78rem}.facts span{display:block;color:var(--muted);font-size:.78rem;overflow-wrap:anywhere}details{margin-top:12px;border-top:1px solid var(--line);padding-top:10px;color:var(--muted);font-size:.78rem}summary{min-height:44px;display:flex;align-items:center;cursor:pointer;color:var(--navy);font-weight:800}.detail-body h3{margin:10px 0 2px;color:var(--ink);font-size:.84rem}.detail-body p{margin:3px 0}.not-now{margin-top:14px;padding:8px 14px;border:1px solid #e6cf91;border-radius:12px;background:#fffaf0}.not-now summary{color:#664b1e}.not-now p{margin:4px 0 6px;color:#664b1e;font-size:.8rem}footer{padding:16px;text-align:center;color:var(--muted);font-size:.72rem}.leaflet-control-attribution{font-size:10px}.leaflet-popup-content{font-family:inherit;line-height:1.5}
    @media(max-width:880px){.layout{grid-template-columns:1fr}.side{grid-template-columns:1fr 1fr}#map{height:58vh;min-height:440px}}@media(max-width:620px){header{display:block;padding:16px}.badge{display:inline-block;margin-top:10px}main{padding:10px}.scope{display:block}.scope b{display:block;margin-bottom:3px}.map-head{display:block}.time-buttons{display:grid;grid-template-columns:repeat(3,1fr);margin-top:10px}.time-buttons button{width:100%}#map{height:54vh;min-height:400px}.side{grid-template-columns:1fr}.stop-name{font-size:1.35rem}.legend{max-width:82%}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
  </style>
</head>
<body>
  <a class="skip" href="#map-card">地図へ移動</a>
  <header><div><p class="eyebrow">作品①｜実道路を使う小規模試験</p><h1>岩国駅から、実際の道でどこまで歩ける？</h1><p class="lead">住民がバス停を選び、生活に必要な場所へ歩いて行けるかを確かめる本線の、地図部分だけを検証します。</p></div><span class="badge">ローカル限定・未公開</span></header>
  <main>
    <section class="scope" aria-label="今回の試験範囲"><b>今回確かめること</b><span>直線の円ではなく、地図に登録された道を実際にたどって、5・10・15分でどこまで届くかを確認します。</span></section>
    <div class="layout">
      <article class="card" id="map-card">
        <div class="map-head"><div><h2>岩国駅バス停から歩いて届く道</h2><p class="map-sub">色のついた線が、今回の計算で時間内に届いた道です。色で囲まれた内側すべてを歩けるという意味ではありません。</p></div><div class="time-buttons" aria-label="表示する徒歩時間"><button type="button" data-minutes="5" aria-pressed="false">5分</button><button type="button" data-minutes="10" aria-pressed="true">10分</button><button type="button" data-minutes="15" aria-pressed="false">15分</button></div></div>
        <div class="map-frame"><div id="map" role="region" aria-label="岩国駅周辺の地図。岩国駅バス停から10分以内に歩いて届く道を表示"></div><div class="legend" aria-hidden="true"><span><i class="swatch road"></i>時間内に歩いて届く道</span><span><i class="swatch bridge"></i>橋として登録された道</span><span><i class="swatch water"></i>川・水面</span></div></div>
        <p class="map-alt" id="map-alt">文字での説明：岩国駅バス停から、実道路上で10分以内に届く道路を表示しています。</p>
      </article>
      <aside class="side" aria-label="選択したバス停の説明">
        <section class="card panel"><p class="kicker">選択中のバス停</p><h2 class="stop-name" id="stop-name"></h2><p class="status" id="range-status" aria-live="polite"></p><p class="plain-guide">地図の色がついた道を見て、このバス停から時間内に歩いて届く方向を確認できます。</p><details><summary>分かること・まだ分からないこと</summary><div class="detail-body"><h3>この表示で分かること</h3><p>同じ徒歩時間でも、道路のつながり方によって届く方向が変わることを確認できます。</p><h3>まだ分からないこと</h3><p>坂を無理なく歩けるか、横断歩道が安全か、公開地図にすべての橋と水域が正しく登録されているか、生活施設へ本当に入れるかは未確認です。</p><p class="notice"><strong>仮条件：</strong>徒歩速度は80m/分です。チームの正式条件ではありません。坂、歩道、横断安全性、工事、現地の通行可否はまだ計算していません。</p></div></details><details><summary>使ったデータと地図の見方</summary><ul class="facts"><li><b>今回、実際のデータを使った部分</b><span>地図に登録された道路の形とつながり、岩国駅バス停の位置、道をたどった距離</span></li><li><b>川と橋の見方</b><span>川と水面は青、橋として登録された道は橙の破線で表示</span></li><li><b>背景地図</b><span>国土地理院の淡色地図。表示にはネット接続が必要</span></li></ul><p id="source-record"></p></details></section>
      </aside>
    </div>
    <details class="not-now"><summary>この試験にまだ入れていないもの</summary><p>生活施設、点数、順位、マトリクス、自治体向け分析、自宅からバス停まで、往路・用事・復路の完全行程。岩国市を最終対象地域にも、80m/分を正式条件にも決めていません。</p></details>
  </main>
  <footer>生成日 __BUILD_DATE__｜保存した公開地図の道路データとバス停データを使ったローカル技術試験｜公開用ではありません</footer>
  <script src="__LEAFLET_JS_URL__" integrity="__LEAFLET_JS_INTEGRITY__" crossorigin="" defer></script>
  <script type="application/json" id="prototype-data">__PAYLOAD__</script>
  <script>
  "use strict";
  window.addEventListener("DOMContentLoaded",function(){
    const payload=JSON.parse(document.getElementById("prototype-data").textContent);const metadata=payload.metadata;const stop=metadata.stop;const mapNode=document.getElementById("map");const statusNode=document.getElementById("range-status");const altNode=document.getElementById("map-alt");document.getElementById("stop-name").textContent=stop.stop_name;document.getElementById("source-record").textContent="道路：誰でも利用できる公開地図（OpenStreetMap）｜バス停：岩国市が公開している公共交通データ";
    if(!window.L){mapNode.innerHTML='<div class="map-fallback">Leafletを読み込めませんでした。ネット接続を確認してください。</div>';statusNode.textContent="地図ライブラリを読み込めませんでした。";statusNode.setAttribute("role","alert");return;}
    const map=L.map("map",{center:[stop.stop_lat,stop.stop_lon],zoom:15,minZoom:5,maxZoom:18,scrollWheelZoom:false});const tiles=L.tileLayer("__GSI_TILE_URL__",{minZoom:5,maxZoom:18,attribution:'背景：<a href="https://maps.gsi.go.jp/development/ichiran.html">国土地理院</a> | 道路：<a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'}).addTo(map);let tileErrors=0;tiles.on("tileerror",function(){tileErrors+=1;if(tileErrors===1){mapNode.setAttribute("aria-label","背景地図の一部を読み込めませんでした。時間内に歩いて届く道を表示");}});
    const waterFeatures=payload.features.filter(function(feature){return feature.properties.kind.indexOf("water")===0;});L.geoJSON({type:"FeatureCollection",features:waterFeatures},{style:function(feature){return feature.geometry.type==="Polygon"?{color:"#2f86bb",weight:1,fillColor:"#56aee0",fillOpacity:.34}:{color:"#3d99ce",weight:3,opacity:.7};},interactive:false}).addTo(map);
    const popup=document.createElement("div");const title=document.createElement("strong");title.textContent=stop.stop_name;const detail=document.createElement("div");detail.textContent="岩国市のバス停データ";popup.appendChild(title);popup.appendChild(detail);L.marker([stop.stop_lat,stop.stop_lon],{title:stop.stop_name,alt:stop.stop_name+"バス停",keyboard:true}).addTo(map).bindPopup(popup);
    let currentLayer=null;function showMinutes(minutes){if(currentLayer){map.removeLayer(currentLayer);}const roads=payload.features.filter(function(feature){return feature.properties.kind==="reachable_road"&&feature.properties.minutes===minutes;});currentLayer=L.geoJSON({type:"FeatureCollection",features:roads},{style:function(feature){return feature.properties.is_bridge?{color:"#d45b16",weight:5,opacity:.9,dashArray:"8 5"}:{color:"#087f8c",weight:3,opacity:.5};},onEachFeature:function(feature,layer){const label=(feature.properties.name||"名前のない道")+(feature.properties.is_bridge?" / 橋として登録":"");layer.bindTooltip(label);}}).addTo(map);if(currentLayer.getBounds().isValid()){map.fitBounds(currentLayer.getBounds(),{padding:[28,28],maxZoom:16});}document.querySelectorAll("[data-minutes]").forEach(function(button){button.setAttribute("aria-pressed",String(Number(button.dataset.minutes)===minutes));});statusNode.textContent=minutes+"分以内に届く道を表示中";altNode.textContent="文字での説明：岩国駅バス停から、地図に登録された道をたどって"+minutes+"分以内に届く道を表示しています。橙の破線は橋として登録された道です。";mapNode.setAttribute("aria-label","岩国駅周辺の地図。岩国駅バス停から"+minutes+"分以内に歩いて届く道を表示");}
    document.querySelector(".time-buttons").addEventListener("click",function(event){const button=event.target.closest("[data-minutes]");if(button){showMinutes(Number(button.dataset.minutes));}});showMinutes(10);
  });
  </script>
</body>
</html>
'''


def render_html(payload: dict[str, Any]) -> str:
    embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (
        HTML_TEMPLATE
        .replace("__LEAFLET_CSS_URL__", LEAFLET_CSS_URL)
        .replace("__LEAFLET_CSS_INTEGRITY__", LEAFLET_CSS_INTEGRITY)
        .replace("__LEAFLET_JS_URL__", LEAFLET_JS_URL)
        .replace("__LEAFLET_JS_INTEGRITY__", LEAFLET_JS_INTEGRITY)
        .replace("__GSI_TILE_URL__", GSI_PALE_TILE_URL)
        .replace("__BUILD_DATE__", BUILD_DATE)
        .replace("__PAYLOAD__", embedded)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geojson-output", type=Path, default=GEOJSON_OUTPUT)
    parser.add_argument("--html-output", type=Path, default=HTML_OUTPUT)
    args = parser.parse_args()
    payload = build_geojson()
    geojson_bytes = serialize_geojson(payload)
    html_bytes = render_html(payload).encode("utf-8")
    args.geojson_output.write_bytes(geojson_bytes)
    args.html_output.write_bytes(html_bytes)
    print(f"WROTE {args.geojson_output} bytes={len(geojson_bytes)} sha256={hashlib.sha256(geojson_bytes).hexdigest()}")
    print(f"WROTE {args.html_output} bytes={len(html_bytes)} sha256={hashlib.sha256(html_bytes).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
