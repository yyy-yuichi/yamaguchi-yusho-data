"""Build a local resident-facing trial of a road-derived walk area.

The saved reachable-road calculation remains the evidence.  This builder turns
those lines into a narrow, deterministic display corridor, joins adjacent grid
cells into polygons, and removes cells whose centers are inside saved OSM water
polygons.  The result is a visual trial, not an accepted walking specification
or a claim that every point in the filled area is safely walkable.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
NETWORK_INPUT = ROOT / "data" / "iwakuni_station_walk_network_isochrone_trial.geojson"
OSM_INPUT = ROOT / "raw" / "osm" / "iwakuni_station_walk_network_overpass_20260829.json"
HTML_OUTPUT = ROOT / "internal" / "work1_network_isochrone_area_trial.html"
BUILD_DATE = "2026-08-30"

MINUTES = (5, 10, 15)
CELL_SIZE_M = 10.0
ROAD_BUFFER_M = 40.0

LEAFLET_VERSION = "1.9.4"
LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_CSS_INTEGRITY = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
LEAFLET_JS_INTEGRITY = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'

GridPoint = tuple[int, int]
GridCell = tuple[int, int]
LonLat = tuple[float, float]


def read_json_with_hash(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def load_inputs(
    network_path: Path = NETWORK_INPUT,
    osm_path: Path = OSM_INPUT,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    network, network_sha256 = read_json_with_hash(network_path)
    osm, osm_sha256 = read_json_with_hash(osm_path)
    if network.get("type") != "FeatureCollection":
        raise ValueError("walk trial must be a GeoJSON FeatureCollection")
    stop = network.get("metadata", {}).get("stop", {})
    if not {"stop_name", "stop_lat", "stop_lon"} <= set(stop):
        raise ValueError("walk trial stop record is incomplete")
    summaries = network.get("metadata", {}).get("summaries", {})
    if set(summaries) != {"5", "10", "15"}:
        raise ValueError("walk trial must contain 5, 10 and 15 minute summaries")
    reachable = [
        feature
        for feature in network.get("features", [])
        if feature.get("properties", {}).get("kind") == "reachable_road"
    ]
    if not reachable or any(feature.get("geometry", {}).get("type") != "LineString" for feature in reachable):
        raise ValueError("walk trial needs reachable LineStrings")
    if not isinstance(osm.get("elements"), list):
        raise ValueError("saved OSM input must contain elements")
    return network, osm, network_sha256, osm_sha256


class LocalProjection:
    def __init__(self, lon0: float, lat0: float) -> None:
        self.lon0 = lon0
        self.lat0 = lat0
        self.meters_per_lon = 111_320.0 * math.cos(math.radians(lat0))
        self.meters_per_lat = 110_540.0

    def to_xy(self, coordinate: Iterable[float]) -> tuple[float, float]:
        lon, lat = coordinate
        return (
            (float(lon) - self.lon0) * self.meters_per_lon,
            (float(lat) - self.lat0) * self.meters_per_lat,
        )

    def to_lonlat(self, x: float, y: float) -> LonLat:
        return (
            round(self.lon0 + x / self.meters_per_lon, 7),
            round(self.lat0 + y / self.meters_per_lat, 7),
        )


def _water_tags(tags: dict[str, Any]) -> bool:
    return tags.get("natural") == "water" or tags.get("waterway") == "riverbank"


def _geometry_lonlat(geometry: list[dict[str, Any]]) -> list[LonLat]:
    return [(float(point["lon"]), float(point["lat"])) for point in geometry]


def _join_lines_into_rings(lines: list[list[LonLat]]) -> list[list[LonLat]]:
    remaining = [line[:] for line in lines if len(line) >= 2]
    rings: list[list[LonLat]] = []
    while remaining:
        ring = remaining.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for index, line in enumerate(remaining):
                if ring[-1] == line[0]:
                    ring.extend(line[1:])
                elif ring[-1] == line[-1]:
                    ring.extend(reversed(line[:-1]))
                elif ring[0] == line[-1]:
                    ring = line[:-1] + ring
                elif ring[0] == line[0]:
                    ring = list(reversed(line[1:])) + ring
                else:
                    continue
                remaining.pop(index)
                changed = True
                break
        if len(ring) >= 4 and ring[0] == ring[-1]:
            rings.append(ring)
    return rings


def water_rings(osm: dict[str, Any]) -> list[list[LonLat]]:
    rings: list[list[LonLat]] = []
    for element in osm.get("elements", []):
        tags = element.get("tags", {})
        if element.get("type") == "way" and _water_tags(tags):
            line = _geometry_lonlat(element.get("geometry", []))
            if len(line) >= 4 and line[0] == line[-1]:
                rings.append(line)
        elif element.get("type") == "relation" and _water_tags(tags):
            outer_lines = [
                _geometry_lonlat(member.get("geometry", []))
                for member in element.get("members", [])
                if member.get("role") == "outer"
            ]
            rings.extend(_join_lines_into_rings(outer_lines))
    return rings


def point_in_ring(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for first, second in zip(ring, ring[1:]):
        x1, y1 = first
        x2, y2 = second
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
    return inside


def _reachable_lines(network: dict[str, Any], minutes: int) -> list[list[LonLat]]:
    return [
        [tuple(map(float, coordinate)) for coordinate in feature["geometry"]["coordinates"]]
        for feature in network.get("features", [])
        if feature.get("properties", {}).get("kind") == "reachable_road"
        and feature["properties"].get("minutes") == minutes
    ]


def _grid_origin(
    lines: list[list[LonLat]],
    projection: LocalProjection,
) -> tuple[float, float]:
    points = [projection.to_xy(coordinate) for line in lines for coordinate in line]
    if not points:
        raise ValueError("15 minute reachable lines are missing")
    margin = ROAD_BUFFER_M + CELL_SIZE_M * 2
    return (
        math.floor((min(x for x, _ in points) - margin) / CELL_SIZE_M) * CELL_SIZE_M,
        math.floor((min(y for _, y in points) - margin) / CELL_SIZE_M) * CELL_SIZE_M,
    )


def _mark_corridor_cells(
    lines: list[list[LonLat]],
    projection: LocalProjection,
    origin: tuple[float, float],
) -> set[GridCell]:
    cells: set[GridCell] = set()
    origin_x, origin_y = origin
    reach = math.ceil(ROAD_BUFFER_M / CELL_SIZE_M) + 1
    sample_step = CELL_SIZE_M / 2
    for line in lines:
        projected = [projection.to_xy(coordinate) for coordinate in line]
        for first, second in zip(projected, projected[1:]):
            x1, y1 = first
            x2, y2 = second
            length = math.hypot(x2 - x1, y2 - y1)
            steps = max(1, math.ceil(length / sample_step))
            for step in range(steps + 1):
                ratio = step / steps
                x = x1 + (x2 - x1) * ratio
                y = y1 + (y2 - y1) * ratio
                center_i = math.floor((x - origin_x) / CELL_SIZE_M)
                center_j = math.floor((y - origin_y) / CELL_SIZE_M)
                for i in range(center_i - reach, center_i + reach + 1):
                    cell_x = origin_x + (i + 0.5) * CELL_SIZE_M
                    for j in range(center_j - reach, center_j + reach + 1):
                        cell_y = origin_y + (j + 0.5) * CELL_SIZE_M
                        if math.hypot(cell_x - x, cell_y - y) <= ROAD_BUFFER_M:
                            cells.add((i, j))
    return cells


def _close_diagonal_contacts(cells: set[GridCell]) -> set[GridCell]:
    closed = set(cells)
    additions: set[GridCell] = set()
    for i, j in cells:
        for dx, dy in ((1, 1), (1, -1)):
            diagonal = (i + dx, j + dy)
            horizontal = (i + dx, j)
            vertical = (i, j + dy)
            if diagonal in cells and horizontal not in cells and vertical not in cells:
                additions.update((horizontal, vertical))
    closed.update(additions)
    return closed


def build_area_cells(
    network: dict[str, Any],
    osm: dict[str, Any],
) -> tuple[dict[int, set[GridCell]], LocalProjection, tuple[float, float], dict[str, int]]:
    stop = network["metadata"]["stop"]
    projection = LocalProjection(float(stop["stop_lon"]), float(stop["stop_lat"]))
    lines_by_minutes = {minutes: _reachable_lines(network, minutes) for minutes in MINUTES}
    origin = _grid_origin(lines_by_minutes[15], projection)
    projected_water = [
        [projection.to_xy(coordinate) for coordinate in ring]
        for ring in water_rings(osm)
    ]
    cells_by_minutes: dict[int, set[GridCell]] = {}
    previous: set[GridCell] = set()
    removed_by_minutes: dict[int, int] = {}
    for minutes in MINUTES:
        cells = _mark_corridor_cells(lines_by_minutes[minutes], projection, origin)
        cells.update(previous)
        cells = _close_diagonal_contacts(cells)
        before_water = len(cells)
        origin_x, origin_y = origin
        cells = {
            cell
            for cell in cells
            if not any(
                point_in_ring(
                    (
                        origin_x + (cell[0] + 0.5) * CELL_SIZE_M,
                        origin_y + (cell[1] + 0.5) * CELL_SIZE_M,
                    ),
                    ring,
                )
                for ring in projected_water
            )
        }
        cells.update(previous)
        cells_by_minutes[minutes] = cells
        previous = set(cells)
        removed_by_minutes[minutes] = before_water - len(cells)
    stats = {
        "water_ring_count": len(projected_water),
        "water_removed_5": removed_by_minutes[5],
        "water_removed_10": removed_by_minutes[10],
        "water_removed_15": removed_by_minutes[15],
    }
    return cells_by_minutes, projection, origin, stats


def _boundary_edges(cells: set[GridCell]) -> set[tuple[GridPoint, GridPoint]]:
    edges: set[tuple[GridPoint, GridPoint]] = set()
    for i, j in cells:
        if (i, j - 1) not in cells:
            edges.add(((i, j), (i + 1, j)))
        if (i + 1, j) not in cells:
            edges.add(((i + 1, j), (i + 1, j + 1)))
        if (i, j + 1) not in cells:
            edges.add(((i + 1, j + 1), (i, j + 1)))
        if (i - 1, j) not in cells:
            edges.add(((i, j + 1), (i, j)))
    return edges


def _turn_priority(previous: GridPoint, current: GridPoint, candidate: GridPoint) -> int:
    directions = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    incoming = directions[(current[0] - previous[0], current[1] - previous[1])]
    outgoing = directions[(candidate[0] - current[0], candidate[1] - current[1])]
    turn = (outgoing - incoming) % 4
    return {1: 0, 0: 1, 3: 2, 2: 3}[turn]


def _simplify_grid_ring(ring: list[GridPoint]) -> list[GridPoint]:
    points = ring[:-1]
    simplified: list[GridPoint] = []
    for index, point in enumerate(points):
        previous = points[index - 1]
        following = points[(index + 1) % len(points)]
        first_direction = (point[0] - previous[0], point[1] - previous[1])
        next_direction = (following[0] - point[0], following[1] - point[1])
        if first_direction != next_direction:
            simplified.append(point)
    simplified.append(simplified[0])
    return simplified


def _trace_boundary_loops(cells: set[GridCell]) -> list[list[GridPoint]]:
    unused = _boundary_edges(cells)
    outgoing: dict[GridPoint, list[GridPoint]] = defaultdict(list)
    for start, end in unused:
        outgoing[start].append(end)
    loops: list[list[GridPoint]] = []
    while unused:
        start_edge = min(unused)
        start, end = start_edge
        loop = [start, end]
        unused.remove(start_edge)
        while loop[-1] != start:
            current = loop[-1]
            candidates = [candidate for candidate in outgoing[current] if (current, candidate) in unused]
            if not candidates:
                raise ValueError("area boundary did not close")
            candidate = min(candidates, key=lambda item: _turn_priority(loop[-2], current, item))
            unused.remove((current, candidate))
            loop.append(candidate)
        if len(loop) >= 5:
            loops.append(_simplify_grid_ring(loop))
    return loops


def _signed_area(ring: list[GridPoint]) -> float:
    return sum(
        first[0] * second[1] - second[0] * first[1]
        for first, second in zip(ring, ring[1:])
    ) / 2


def _grid_point_in_ring(point: GridPoint, ring: list[GridPoint]) -> bool:
    return point_in_ring((float(point[0]), float(point[1])), [(float(x), float(y)) for x, y in ring])


def cells_to_multipolygon(
    cells: set[GridCell],
    projection: LocalProjection,
    origin: tuple[float, float],
) -> list[list[list[list[float]]]]:
    loops = _trace_boundary_loops(cells)
    outers = [ring for ring in loops if _signed_area(ring) > 0]
    holes = [ring for ring in loops if _signed_area(ring) < 0]
    if not outers:
        raise ValueError("area must have an outer boundary")
    grouped: list[tuple[list[GridPoint], list[list[GridPoint]]]] = [(outer, []) for outer in outers]
    for hole in holes:
        containing = [
            (abs(_signed_area(outer)), index)
            for index, (outer, _assigned) in enumerate(grouped)
            if _grid_point_in_ring(hole[0], outer)
        ]
        if containing:
            grouped[min(containing)[1]][1].append(hole)

    origin_x, origin_y = origin

    def convert(ring: list[GridPoint]) -> list[list[float]]:
        return [
            list(projection.to_lonlat(origin_x + x * CELL_SIZE_M, origin_y + y * CELL_SIZE_M))
            for x, y in ring
        ]

    return [[convert(outer), *[convert(hole) for hole in assigned]] for outer, assigned in grouped]


def build_area_payload(network: dict[str, Any], osm: dict[str, Any]) -> dict[str, Any]:
    cells_by_minutes, projection, origin, stats = build_area_cells(network, osm)
    features = []
    for minutes in MINUTES:
        geometry = cells_to_multipolygon(cells_by_minutes[minutes], projection, origin)
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "kind": "reachable_area_display_trial",
                    "minutes": minutes,
                    "cell_size_m": CELL_SIZE_M,
                    "road_buffer_m": ROAD_BUFFER_M,
                    "occupied_cell_count": len(cells_by_minutes[minutes]),
                    "polygon_count": len(geometry),
                    "water_removed_cell_count": stats[f"water_removed_{minutes}"],
                },
                "geometry": {"type": "MultiPolygon", "coordinates": geometry},
            }
        )
    return {
        "type": "FeatureCollection",
        "metadata": {
            "status": "LOCAL_DISPLAY_TRIAL_NOT_WALKING_SPECIFICATION",
            "cell_size_m": CELL_SIZE_M,
            "road_buffer_m": ROAD_BUFFER_M,
            "water_ring_count": stats["water_ring_count"],
            "minutes": list(MINUTES),
        },
        "features": features,
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Permissions-Policy" content="geolocation=(),camera=(),microphone=()">
  <title>徒歩で届くエリア｜作品① ローカル試作</title>
  <link rel="stylesheet" href="__LEAFLET_CSS_URL__" integrity="__LEAFLET_CSS_INTEGRITY__" crossorigin="">
  <style>
    :root{--ink:#20302c;--muted:#5d6b67;--paper:#f2f4f1;--card:#fff;--line:#d6dfda;--green:#2f694d;--green-fill:#75aa87;--green-soft:#e7f1e9;--cream:#fff8e9;--amber:#705318}
    *{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--paper);color:var(--ink)}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP","Yu Gothic",Meiryo,sans-serif;line-height:1.65}button{font:inherit}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #b97910;outline-offset:3px}.skip{position:fixed;left:12px;top:-80px;z-index:1500;padding:10px 14px;border-radius:8px;background:#fff;color:#214f3b;font-weight:900}.skip:focus{top:12px}
    header{padding:19px max(16px,calc((100vw - 1180px)/2));background:linear-gradient(115deg,#315d4a,#68806f);color:#fff}.eyebrow{margin:0 0 3px;font-size:.75rem;font-weight:900;letter-spacing:.05em}h1{margin:0;font-size:clamp(1.45rem,3.4vw,2.2rem);line-height:1.3}.lead{max-width:880px;margin:6px 0 0;color:#f2f7f3;font-size:.92rem}
    main{width:min(1180px,100%);margin:0 auto;padding:14px}.purpose{margin-bottom:12px;padding:13px 15px;border:1px solid #a9c5b2;border-radius:12px;background:var(--green-soft)}.purpose h2{margin:0 0 4px;font-size:1rem}.purpose p{margin:0;font-size:.84rem}.purpose strong{color:#20523a}
    .controls{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px;padding:11px 13px;border:1px solid var(--line);border-radius:12px;background:#fff}.time-buttons{display:flex;gap:7px}.time-buttons button,.road-toggle{min-height:44px;border:1px solid #96a7a0;border-radius:9px;background:#fff;color:var(--ink);font-weight:900;cursor:pointer}.time-buttons button{min-width:68px;padding:7px 12px}.time-buttons button[aria-pressed="true"],.road-toggle[aria-pressed="true"]{border-color:var(--green);background:var(--green);color:#fff}.road-toggle{padding:7px 13px}.controls-help{margin:0;color:var(--muted);font-size:.77rem}
    .layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:12px}.map-card,.side-card{overflow:hidden;border:1px solid var(--line);border-radius:14px;background:var(--card);box-shadow:0 8px 22px rgba(36,59,50,.07)}.map-head{padding:12px 14px;border-bottom:1px solid var(--line)}.map-head h2{margin:0;font-size:1.03rem}.map-head p{margin:3px 0 0;color:var(--muted);font-size:.78rem}.map-wrap{position:relative}#map{height:min(67vh,650px);min-height:500px;background:#e7ece8}.map-fallback{display:grid;place-items:center;height:100%;padding:25px;background:#fff4df;color:#6d3b0c;text-align:center;font-weight:800}.legend{position:absolute;left:11px;bottom:11px;z-index:500;display:grid;gap:5px;max-width:220px;padding:8px 10px;border-radius:9px;background:rgba(255,255,255,.95);box-shadow:0 1px 6px rgba(0,0,0,.18);font-size:.69rem}.legend span{display:flex;align-items:center;gap:7px}.area-sample{display:inline-block;width:30px;height:15px;border:2px solid var(--green);border-radius:4px;background:rgba(117,170,135,.42)}.road-sample{display:inline-block;width:30px;height:2px;background:#315f4b}.map-alt{margin:0;padding:9px 13px;border-top:1px solid var(--line);color:var(--muted);font-size:.76rem}
    .legend [hidden]{display:none}
    .side-card{padding:14px}.stop-label{margin:0;color:#2b5d45;font-size:.72rem;font-weight:900}.stop-name{margin:0 0 10px;font-size:1.2rem}.status{margin:0 0 12px;padding:11px;border-left:5px solid var(--green);border-radius:8px;background:var(--green-soft);font-weight:900}.plain{margin:0 0 12px;font-size:.82rem}.section{padding-top:11px;border-top:1px solid var(--line)}.section h3{margin:0 0 5px;font-size:.88rem}.section p{margin:0 0 10px;color:var(--muted);font-size:.77rem}.unknown{padding:10px;border-radius:9px;background:var(--cream);color:#66501f;font-size:.76rem}.load-state{margin:10px 0 0;color:var(--muted);font-size:.72rem}details{margin-top:12px;border:1px solid var(--line);border-radius:12px;background:#fff;padding:0 13px}summary{display:flex;align-items:center;min-height:44px;color:#285a40;cursor:pointer;font-weight:900}details p{margin:2px 0 11px;color:var(--muted);font-size:.75rem;overflow-wrap:anywhere}footer{padding:16px;text-align:center;color:var(--muted);font-size:.7rem}.leaflet-control-attribution{font-size:9px}
    @media(max-width:820px){.layout{grid-template-columns:1fr}.side-card{display:grid;grid-template-columns:1fr 1fr;gap:10px}.side-card>.section{padding:0 0 0 11px;border-top:0;border-left:1px solid var(--line)}.load-state{grid-column:1/-1}}
    @media(max-width:650px){header{padding:16px 14px}main{padding:9px}.purpose{padding:11px 12px}.controls{display:block}.time-buttons{display:grid;grid-template-columns:repeat(3,1fr)}.time-buttons button{width:100%;min-width:0}.road-toggle{width:100%;margin-top:8px}.controls-help{margin-top:7px}.map-head{padding:11px 12px}#map{height:54vh;min-height:390px}.side-card{display:block;padding:12px}.side-card>.section{margin-top:10px;padding:10px 0 0;border-top:1px solid var(--line);border-left:0}.legend{font-size:.66rem}.map-alt{font-size:.72rem}}
    @media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
  </style>
</head>
<body>
  <a class="skip" href="#trial">地図へ移動</a>
  <header><p class="eyebrow">作品①｜住民向けエリア表示の試作</p><h1>このバス停から、徒歩でどこまで届く？</h1><p class="lead">道路を一本ずつ読むのではなく、徒歩時間内に届くおおよその広がりを先に確認します。</p></header>
  <main id="trial">
    <section class="purpose" aria-labelledby="purpose-title"><h2 id="purpose-title">今回確かめること</h2><p>5分・10分・15分で届く道路が変わる計算は、前の線表示と同じです。今回は計算を変えず、<strong>住民が生活に必要な場所へ歩いて行けそうな広がりを、面の方がひと目でつかめるか</strong>を確認します。背景はOpenStreetMap、岩国駅は技術試験の一例です。</p></section>
    <section class="controls" aria-label="徒歩時間と詳しい道路の表示"><div class="time-buttons" aria-label="歩く時間を選ぶ"><button type="button" data-minutes="5" aria-pressed="false">5分</button><button type="button" data-minutes="10" aria-pressed="true">10分</button><button type="button" data-minutes="15" aria-pressed="false">15分</button></div><button class="road-toggle" id="road-toggle" type="button" aria-pressed="false">詳しい道を表示</button><p class="controls-help">最初はエリアだけを表示します。道路線は必要なときだけ確認できます。</p></section>
    <div class="layout">
      <article class="map-card" aria-labelledby="map-title"><div class="map-head"><h2 id="map-title">岩国駅バス停から届く範囲の目安</h2><p>緑の面が今回の試算で届く範囲です。単純な円ではなく、保存済みの道路計算から作っています。</p></div><div class="map-wrap"><div id="map" role="region" aria-label="岩国駅バス停から10分以内に届く範囲の地図"></div><div class="legend"><span><i class="area-sample"></i>時間内に届く範囲の目安</span><span id="road-legend" hidden><i class="road-sample"></i>計算に使った道路</span></div></div><p class="map-alt" id="map-alt">文字での説明：岩国駅バス停から、保存済みの道路計算をもとにした10分以内の範囲を緑色で表示しています。</p></article>
      <aside class="side-card" aria-label="選択中のバス停と確認状況"><div><p class="stop-label">選択中のバス停</p><h2 class="stop-name">岩国駅</h2><p class="status" id="status" aria-live="polite">徒歩10分の範囲を表示中</p><p class="plain">地図を見て、買い物や通院などで使いたい場所がこの範囲に入りそうかを確認します。</p></div><section class="section"><h3>この表示で分かること</h3><p>道路のつながりをもとに、選んだ時間で届く方向とおおよその広がりを確認できます。</p><div class="unknown"><strong>まだ分からないこと</strong><br>坂を無理なく歩けるか、歩道や横断場所が安全か、生活施設へ実際に入れるか、帰りのバスまで含めて用事を済ませられるかは未確認です。</div></section><p class="load-state" id="load-state" aria-live="polite">OpenStreetMapを読み込み中です。</p></aside>
    </div>
    <details><summary>このエリアの作り方と限界</summary><p>保存済みの「時間内に届いた道路」の周囲40mを10m単位の面にし、隣り合う面をまとめました。保存済みOSMで水面と確認できる部分は面から外しています。40mは生活圏や徒歩条件ではなく、エリア表示を試すためだけの仮幅です。すべての地点を安全に歩けると確定した表示ではありません。</p><p id="source-record"></p></details>
  </main>
  <footer>生成日 __BUILD_DATE__｜エリア中心のローカル表示試作｜主画面・徒歩条件・対象地域は未決定</footer>
  <script src="__LEAFLET_JS_URL__" integrity="__LEAFLET_JS_INTEGRITY__" crossorigin="" defer></script>
  <script type="application/json" id="road-data">__ROAD_PAYLOAD__</script>
  <script type="application/json" id="area-data">__AREA_PAYLOAD__</script>
  <script>
  "use strict";
  window.addEventListener("DOMContentLoaded",function(){
    const roadPayload=JSON.parse(document.getElementById("road-data").textContent);const areaPayload=JSON.parse(document.getElementById("area-data").textContent);const stop=roadPayload.metadata.stop;const mapNode=document.getElementById("map");const statusNode=document.getElementById("status");const altNode=document.getElementById("map-alt");const toggle=document.getElementById("road-toggle");const roadLegend=document.getElementById("road-legend");const loadState=document.getElementById("load-state");document.getElementById("source-record").textContent="道路到達データ：__NETWORK_PATH__（SHA-256 __NETWORK_SHA256__）｜保存OSM：__OSM_PATH__（SHA-256 __OSM_SHA256__）";
    if(!window.L){mapNode.innerHTML='<div class="map-fallback">地図を読み込めませんでした。ネット接続を確認してください。</div>';mapNode.setAttribute("role","alert");loadState.textContent="表示できません：地図機能を読み込めませんでした。";return;}
    const map=L.map("map",{center:[stop.stop_lat,stop.stop_lon],zoom:15,minZoom:5,maxZoom:18,scrollWheelZoom:false});const tiles=L.tileLayer("__OSM_TILE_URL__",{minZoom:5,maxZoom:19,attribution:'__OSM_ATTRIBUTION__'}).addTo(map);let tileErrors=0;tiles.on("load",function(){loadState.textContent="OpenStreetMapを読み込みました。";});tiles.on("tileerror",function(){tileErrors+=1;loadState.textContent="背景地図の一部を読み込めませんでした（"+tileErrors+"件）。範囲を正しく見比べられない可能性があります。";});L.marker([stop.stop_lat,stop.stop_lon],{title:stop.stop_name,alt:stop.stop_name+"バス停",keyboard:true}).addTo(map).bindPopup(stop.stop_name+"バス停");
    let selectedMinutes=10;let areaLayer=null;let roadLayer=null;
    function roadFeatures(minutes){return roadPayload.features.filter(function(feature){return feature.properties.kind==="reachable_road"&&feature.properties.minutes===minutes;});}
    function drawRoads(){if(roadLayer){map.removeLayer(roadLayer);roadLayer=null;}if(toggle.getAttribute("aria-pressed")!=="true"){roadLegend.hidden=true;return;}roadLayer=L.geoJSON({type:"FeatureCollection",features:roadFeatures(selectedMinutes)},{style:function(feature){return feature.properties.is_bridge?{color:"#8a5b22",weight:2.4,opacity:.75,dashArray:"7 5"}:{color:"#315f4b",weight:1.4,opacity:.48};},interactive:false}).addTo(map);roadLegend.hidden=false;}
    function showMinutes(minutes){selectedMinutes=minutes;if(areaLayer){map.removeLayer(areaLayer);}const feature=areaPayload.features.find(function(item){return item.properties.minutes===minutes;});areaLayer=L.geoJSON(feature,{style:{color:"#2f694d",weight:2,opacity:.9,fillColor:"#75aa87",fillOpacity:.30,lineJoin:"round"},interactive:false}).addTo(map);drawRoads();if(areaLayer.getBounds().isValid()){map.fitBounds(areaLayer.getBounds(),{padding:[24,24],maxZoom:16,animate:false});}document.querySelectorAll("[data-minutes]").forEach(function(button){button.setAttribute("aria-pressed",String(Number(button.dataset.minutes)===minutes));});statusNode.textContent="徒歩"+minutes+"分の範囲を表示中";altNode.textContent="文字での説明：岩国駅バス停から、保存済みの道路計算をもとにした"+minutes+"分以内の範囲を緑色で表示しています。";mapNode.setAttribute("aria-label","岩国駅バス停から"+minutes+"分以内に届く範囲の地図");}
    document.querySelector(".time-buttons").addEventListener("click",function(event){const button=event.target.closest("[data-minutes]");if(button){showMinutes(Number(button.dataset.minutes));}});toggle.addEventListener("click",function(){const next=toggle.getAttribute("aria-pressed")!=="true";toggle.setAttribute("aria-pressed",String(next));toggle.textContent=next?"詳しい道を隠す":"詳しい道を表示";drawRoads();});showMinutes(10);
  });
  </script>
</body>
</html>
'''


def render_html(
    network: dict[str, Any],
    area_payload: dict[str, Any],
    network_sha256: str,
    osm_sha256: str,
) -> str:
    embedded_roads = json.dumps(network, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    embedded_area = json.dumps(area_payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (
        HTML_TEMPLATE
        .replace("__LEAFLET_CSS_URL__", LEAFLET_CSS_URL)
        .replace("__LEAFLET_CSS_INTEGRITY__", LEAFLET_CSS_INTEGRITY)
        .replace("__LEAFLET_JS_URL__", LEAFLET_JS_URL)
        .replace("__LEAFLET_JS_INTEGRITY__", LEAFLET_JS_INTEGRITY)
        .replace("__OSM_TILE_URL__", OSM_TILE_URL)
        .replace("__OSM_ATTRIBUTION__", OSM_ATTRIBUTION)
        .replace("__BUILD_DATE__", BUILD_DATE)
        .replace("__NETWORK_PATH__", NETWORK_INPUT.relative_to(ROOT).as_posix())
        .replace("__NETWORK_SHA256__", network_sha256)
        .replace("__OSM_PATH__", OSM_INPUT.relative_to(ROOT).as_posix())
        .replace("__OSM_SHA256__", osm_sha256)
        .replace("__ROAD_PAYLOAD__", embedded_roads)
        .replace("__AREA_PAYLOAD__", embedded_area)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-input", type=Path, default=NETWORK_INPUT)
    parser.add_argument("--osm-input", type=Path, default=OSM_INPUT)
    parser.add_argument("--output", type=Path, default=HTML_OUTPUT)
    args = parser.parse_args()
    network, osm, network_sha256, osm_sha256 = load_inputs(args.network_input, args.osm_input)
    area_payload = build_area_payload(network, osm)
    html_bytes = render_html(network, area_payload, network_sha256, osm_sha256).encode("utf-8")
    args.output.write_bytes(html_bytes)
    print(
        f"WROTE {args.output} bytes={len(html_bytes)} "
        f"sha256={hashlib.sha256(html_bytes).hexdigest()} "
        f"cells={[feature['properties']['occupied_cell_count'] for feature in area_payload['features']]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
