"""Build a resident-first local prototype from the saved Iwakuni walk trial.

This page tests the order in which a resident should receive information.  It
does not accept Iwakuni, the temporary walking speed, the saved facility
categories, or the example life needs as final product specifications.  The
saved road-reachability and official-facility trial data are reused as
evidence; facility positions inside the display area are calculated during
the build and are not claims about entrances, opening hours, or usability.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
from pathlib import Path
from typing import Any
import zipfile

try:
    from . import build_iwakuni_station_walk_network_isochrone_trial as network_builder
    from . import build_work1_network_isochrone_area_trial as area_builder
except ImportError:  # Direct script execution from src/.
    import build_iwakuni_station_walk_network_isochrone_trial as network_builder
    import build_work1_network_isochrone_area_trial as area_builder


ROOT = Path(__file__).resolve().parents[1]
GTFS_INPUT = ROOT / "raw" / "gtfs" / "iwakuni_gtfsjp_20260401.zip"
OSM_INPUT = ROOT / "raw" / "osm" / "iwakuni_station_walk_network_overpass_20260829.json"
FACILITY_INPUT = ROOT / "data" / "iwakuni_life_facility_join_trial.json"
HTML_OUTPUT = ROOT / "internal" / "work1_resident_walk_access_prototype.html"
BUILD_DATE = "2026-09-01"
DEFAULT_STOP_ID = "684_01"
TRIAL_STOP_EXPECTATIONS = (
    ("684_01", "岩国駅"),
    ("677_01", "市役所"),
    ("665_01", "今津"),
)
FACILITY_CATEGORY_PRESENTATION = (
    {
        "key": "public_facility",
        "label": "公共施設",
        "color": "#6648a3",
    },
    {
        "key": "medical_facility",
        "label": "医療機関",
        "color": "#b13f3f",
    },
    {
        "key": "childcare_facility",
        "label": "子育て施設",
        "color": "#b56600",
    },
)

LEAFLET_VERSION = "1.9.4"
LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
LEAFLET_CSS_INTEGRITY = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
LEAFLET_JS_INTEGRITY = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'


def file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def load_trial_stops(path: Path = GTFS_INPUT) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(network_builder.GTFS_MEMBER).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text, newline="")))
    stops = []
    south, west, north, east = network_builder.OVERPASS_BBOX
    for stop_id, expected_name in TRIAL_STOP_EXPECTATIONS:
        matches = [row for row in rows if row.get("stop_id") == stop_id]
        if len(matches) != 1:
            raise ValueError(f"expected one {stop_id} row, found {len(matches)}")
        row = matches[0]
        if row.get("stop_name") != expected_name:
            raise ValueError(f"unexpected stop name for {stop_id}: {row.get('stop_name')!r}")
        stop = {
            "stop_id": stop_id,
            "stop_name": expected_name,
            "stop_lat": float(row["stop_lat"]),
            "stop_lon": float(row["stop_lon"]),
            "location_type": row.get("location_type", ""),
        }
        if not (south <= stop["stop_lat"] <= north and west <= stop["stop_lon"] <= east):
            raise ValueError(f"trial stop {stop_id} is outside the saved OSM bounds")
        stops.append(stop)
    return stops, hashlib.sha256(raw).hexdigest()


def load_facility_records(
    path: Path = FACILITY_INPUT,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    raw = path.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    records = document.get("facility_records")
    if not isinstance(records, list):
        raise ValueError("saved facility trial must contain facility_records")
    if document.get("facility_record_count") != len(records):
        raise ValueError("saved facility trial record count does not match its records")

    expected_categories = {item["key"] for item in FACILITY_CATEGORY_PRESENTATION}
    normalized = []
    seen_ids: set[str] = set()
    for record in records:
        required = {
            "facility_id",
            "facility_name",
            "common_category",
            "source_category",
            "latitude",
            "longitude",
            "source",
        }
        if not required <= set(record):
            raise ValueError("saved facility record is incomplete")
        facility_id = str(record["facility_id"])
        if facility_id in seen_ids:
            raise ValueError(f"duplicate facility id: {facility_id}")
        seen_ids.add(facility_id)
        common_category = str(record["common_category"])
        if common_category not in expected_categories:
            raise ValueError(f"unexpected saved facility category: {common_category}")
        normalized.append({
            "facility_id": facility_id,
            "facility_name": str(record["facility_name"]),
            "common_category": common_category,
            "source_category": str(record["source_category"]),
            "latitude": float(record["latitude"]),
            "longitude": float(record["longitude"]),
            "source_id": str(record["source"]["source_id"]),
        })

    source_registry = document.get("source_registry", {})
    sources = source_registry.get("facility_sources", [])
    if not isinstance(sources, list) or len(sources) != len(FACILITY_CATEGORY_PRESENTATION):
        raise ValueError("saved facility source registry must contain the three trial datasets")
    source_summary = [
        {
            "source_id": str(source["source_id"]),
            "dataset_label": str(source["dataset_label"]),
            "common_category": str(source["common_category"]),
            "dataset_page_url": str(source["dataset_page_url"]),
            "license_name": str(source["license_name"]),
            "retrieved_at": str(source_registry["retrieved_at"]),
        }
        for source in sources
    ]
    return normalized, {
        "source": {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
        "record_count": len(normalized),
        "datasets": source_summary,
        "boundaries": list(document.get("boundaries", [])),
    }, hashlib.sha256(raw).hexdigest()


def point_is_in_area_feature(
    point: tuple[float, float],
    area_feature: dict[str, Any],
) -> bool:
    geometry = area_feature.get("geometry", {})
    if geometry.get("type") != "MultiPolygon":
        raise ValueError("facility overlay requires a MultiPolygon area feature")
    for polygon in geometry.get("coordinates", []):
        if not polygon:
            continue
        outer = [tuple(map(float, coordinate)) for coordinate in polygon[0]]
        if not area_builder.point_in_ring(point, outer):
            continue
        holes = [
            [tuple(map(float, coordinate)) for coordinate in ring]
            for ring in polygon[1:]
        ]
        if not any(area_builder.point_in_ring(point, hole) for hole in holes):
            return True
    return False


def facilities_in_area(
    facilities: list[dict[str, Any]],
    area_feature: dict[str, Any],
) -> list[dict[str, Any]]:
    category_order = {
        item["key"]: index
        for index, item in enumerate(FACILITY_CATEGORY_PRESENTATION)
    }
    matches = [
        facility
        for facility in facilities
        if point_is_in_area_feature(
            (facility["longitude"], facility["latitude"]),
            area_feature,
        )
    ]
    return sorted(
        matches,
        key=lambda item: (
            category_order[item["common_category"]],
            item["facility_name"],
            item["facility_id"],
        ),
    )


def build_facility_reachability(
    facilities: list[dict[str, Any]],
    area_payload: dict[str, Any],
) -> dict[str, Any]:
    categories = [item["key"] for item in FACILITY_CATEGORY_PRESENTATION]
    by_minutes: dict[str, dict[str, Any]] = {}
    previous_ids: set[str] = set()
    for feature in area_payload["features"]:
        minutes = int(feature["properties"]["minutes"])
        matches = facilities_in_area(facilities, feature)
        facility_ids = [item["facility_id"] for item in matches]
        current_ids = set(facility_ids)
        if not previous_ids <= current_ids:
            raise ValueError("facility display results must be cumulative by walking time")
        category_counts = {
            category: sum(item["common_category"] == category for item in matches)
            for category in categories
        }
        by_minutes[str(minutes)] = {
            "facility_count": len(matches),
            "category_counts": category_counts,
            "facility_ids": facility_ids,
        }
        previous_ids = current_ids
    return {
        "status": "DISPLAY_AREA_POINT_OVERLAY_TRIAL_NOT_FACILITY_ACCESS_SPECIFICATION",
        "by_minutes": by_minutes,
        "boundaries": {
            "area_meaning": "道路到達から作った試験用表示面の内側にある施設座標だけを数える",
            "not_verified": "入口、営業時間、利用条件、歩行安全、往路・用事・復路は判定しない",
            "classification": "保存済み公式3データセットの分類を試験表示し、生活施設の最終分類や優先順位にはしない",
        },
    }


def build_stop_network_payload(
    stop: dict[str, Any],
    osm: dict[str, Any],
    graph: dict[str, Any],
    gtfs_record: dict[str, Any],
    osm_record: dict[str, Any],
) -> dict[str, Any]:
    stop_point = (stop["stop_lon"], stop["stop_lat"])
    snap_node, snap_distance = network_builder.nearest_node(graph["coordinates"], stop_point)
    distances = network_builder.dijkstra(graph["adjacency"], snap_node)
    features = []
    summaries: dict[str, dict[str, Any]] = {}
    for minutes in network_builder.MINUTES:
        budget = minutes * network_builder.TEMPORARY_SPEED_METERS_PER_MINUTE
        segment_count = 0
        bridge_segment_count = 0
        displayed_length = 0.0
        for edge in graph["edges"]:
            for part_index, (coordinates, length) in enumerate(
                network_builder.reachable_parts(
                    edge,
                    graph["coordinates"],
                    distances,
                    budget,
                )
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
    features.extend([
        {
            "type": "Feature",
            "properties": {
                "kind": "selected_stop",
                "stop_id": stop["stop_id"],
                "stop_name": stop["stop_name"],
            },
            "geometry": {
                "type": "Point",
                "coordinates": [stop["stop_lon"], stop["stop_lat"]],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "kind": "graph_snap",
                "node_id": snap_node,
                "snap_distance_m": round(snap_distance, 3),
            },
            "geometry": {
                "type": "Point",
                "coordinates": list(graph["coordinates"][snap_node]),
            },
        },
    ])
    return {
        "type": "FeatureCollection",
        "metadata": {
            "task_id": "WORK1-RESIDENT-MULTI-STOP-WALK-AREA-TRIAL-1",
            "status": "LOCAL_MULTI_STOP_TRIAL_NOT_ACCEPTED_PRODUCT_SPEC",
            "build_date": BUILD_DATE,
            "calculation": {
                "algorithm": "Dijkstra on saved OSM highway geometry",
                "temporary_speed_m_per_min": network_builder.TEMPORARY_SPEED_METERS_PER_MINUTE,
                "minutes": list(network_builder.MINUTES),
                "slope_used": False,
                "field_walkability_verified": False,
            },
            "osm_source": osm_record,
            "gtfs_source": {**gtfs_record, "member": network_builder.GTFS_MEMBER},
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
            "summaries": summaries,
            "boundaries": {
                "target_region": "3停留所は保存範囲で切替を試す例であり、最終対象地域ではない",
                "walking_condition": "80m/分と5・10・15分は仮条件で、本人またはチームの最終決定ではない",
                "scope": "生活施設、点数、順位、自治体向け分析、自宅、完全行程を含めない",
            },
        },
        "features": features,
    }


def load_prototype_payloads(
    gtfs_path: Path = GTFS_INPUT,
    osm_path: Path = OSM_INPUT,
    facility_path: Path = FACILITY_INPUT,
) -> tuple[dict[str, Any], str, str]:
    stops, gtfs_sha256 = load_trial_stops(gtfs_path)
    facilities, facility_metadata, _facility_sha256 = load_facility_records(facility_path)
    osm_raw = osm_path.read_bytes()
    osm = json.loads(osm_raw.decode("utf-8"))
    osm_sha256 = hashlib.sha256(osm_raw).hexdigest()
    graph = network_builder.build_graph(osm)
    gtfs_record = file_record(gtfs_path)
    osm_record = file_record(osm_path)
    stop_payloads = []
    for stop in stops:
        road_payload = build_stop_network_payload(
            stop,
            osm,
            graph,
            gtfs_record,
            osm_record,
        )
        area_payload = area_builder.build_area_payload(road_payload, osm)
        stop_payloads.append({
            "stop": stop,
            "road_payload": road_payload,
            "area_payload": area_payload,
            "facility_reachability": build_facility_reachability(
                facilities,
                area_payload,
            ),
        })
    return ({
        "metadata": {
            "task_id": "WORK1-RESIDENT-MULTI-STOP-FACILITY-OVERLAY-TRIAL-1",
            "status": "LOCAL_MULTI_STOP_FACILITY_OVERLAY_TRIAL_NOT_ACCEPTED_PRODUCT_SPEC",
            "build_date": BUILD_DATE,
            "default_stop_id": DEFAULT_STOP_ID,
            "stop_count": len(stop_payloads),
            "gtfs_source": gtfs_record,
            "osm_source": osm_record,
            "facility_source": facility_metadata["source"],
            "facility_record_count": facility_metadata["record_count"],
            "facility_categories": [dict(item) for item in FACILITY_CATEGORY_PRESENTATION],
            "facility_datasets": facility_metadata["datasets"],
            "boundaries": {
                "selection": "保存範囲で切替差を試す3停留所で、最終対象停留所ではない",
                "direction": "同名の上下方向を重複表示せず、各名称から1乗降場所だけを試験に使う",
                "facility_scope": "保存済み公式3データセットを表示方法の試験に使い、生活施設の最終定義や優先順位にはしない",
                "facility_access": "表示面内の施設座標を数えるだけで、入口、営業時間、利用条件、歩行安全、完全行程は判定しない",
            },
        },
        "facility_records": facilities,
        "stops": stop_payloads,
    }, gtfs_sha256, osm_sha256)


HTML_TEMPLATE = r'''<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta http-equiv="Permissions-Policy" content="geolocation=(),camera=(),microphone=()">
  <title>住民向け画面｜作品①</title>
  <link rel="stylesheet" href="__LEAFLET_CSS_URL__" integrity="__LEAFLET_CSS_INTEGRITY__" crossorigin="">
  <style>
    :root{--ink:#14263b;--muted:#566a7c;--paper:#edf3f5;--card:#fff;--line:#d5e0e5;--navy:#073d70;--teal:#087f8c;--teal-soft:#e3f5f6;--green:#2f694d;--green-fill:#75aa87;--orange:#c95112;--amber:#765000;--amber-soft:#fff2cf;--unknown:#67552b}
    *{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--paper);color:var(--ink)}body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP","Yu Gothic",Meiryo,sans-serif;line-height:1.65}button,select{font:inherit}button:focus-visible,select:focus-visible,summary:focus-visible,a:focus-visible{outline:3px solid #ffb900;outline-offset:3px}.skip{position:fixed;left:12px;top:-80px;z-index:1500;padding:10px 14px;border-radius:8px;background:#fff;color:var(--navy);font-weight:900}.skip:focus{top:12px}
    header{padding:20px max(18px,calc((100vw - 1260px)/2));background:linear-gradient(120deg,#07386d,#07818e);color:#fff}.eyebrow{margin:0 0 4px;font-size:.76rem;font-weight:900;letter-spacing:.07em}h1{max-width:850px;margin:0;font-size:clamp(1.55rem,3.4vw,2.45rem);line-height:1.25}.lead{max-width:820px;margin:7px 0 0;color:#e5f8fa;font-size:.95rem}
    main{width:min(1260px,100%);margin:0 auto;padding:16px}.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:0 0 14px;padding:0;list-style:none}.flow li{display:flex;align-items:center;gap:8px;min-height:52px;padding:9px 11px;border:1px solid #b8ced5;border-radius:11px;background:#fff;color:#40576b;font-size:.78rem;font-weight:800}.flow b{display:grid;flex:0 0 auto;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--teal-soft);color:var(--navy)}
    .question{display:flex;align-items:center;justify-content:space-between;gap:18px;margin-bottom:14px;padding:15px 17px;border:1px solid #8dc5ca;border-radius:14px;background:var(--teal-soft)}.question h2{margin:0;font-size:clamp(1.05rem,2vw,1.35rem)}.question p{margin:2px 0 0;color:#365765;font-size:.84rem}.trial-tag{flex:0 0 auto;padding:6px 10px;border:1px solid #5a9ca4;border-radius:999px;background:#fff;color:#245761;font-size:.72rem;font-weight:900}
    .workspace{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(330px,.72fr);gap:14px;align-items:start}.card{min-width:0;border:1px solid var(--line);border-radius:15px;background:var(--card);box-shadow:0 10px 30px rgba(18,43,79,.08);overflow:hidden}.map-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px}.map-head h2{margin:0;font-size:1.08rem}.map-head p{margin:2px 0 0;color:var(--muted);font-size:.78rem}.map-tools{display:grid;gap:7px;flex:0 0 auto}.time-buttons{display:flex;gap:6px}.time-buttons button,.road-toggle{min-height:44px;padding:7px 10px;border:1px solid #aab9c4;border-radius:9px;background:#fff;color:var(--ink);font-weight:900;cursor:pointer}.time-buttons button{min-width:56px}.time-buttons button[aria-pressed="true"],.road-toggle[aria-pressed="true"]{border-color:var(--navy);background:var(--navy);color:#fff}.road-toggle{width:100%}
    .map-frame{position:relative}#map{width:100%;height:min(65vh,650px);min-height:500px;background:#dfe9ed}.map-fallback{display:grid;place-items:center;height:100%;padding:30px;text-align:center;color:#6d2f00;background:#fff4df;font-weight:800}.legend{position:absolute;z-index:500;left:12px;bottom:12px;display:grid;gap:4px;padding:7px 9px;border:1px solid rgba(9,73,122,.18);border-radius:8px;background:rgba(255,255,255,.95);color:#25425e;font-size:.68rem;box-shadow:0 2px 8px rgba(20,42,80,.14);pointer-events:none}.legend span{display:flex;align-items:center;gap:6px}.legend [hidden]{display:none}.swatch{display:inline-block;width:27px;border-radius:4px}.area{height:14px;border:2px solid var(--green);background:rgba(117,170,135,.42)}.road{height:2px;background:#315f4b}.bridge{height:4px;background:repeating-linear-gradient(90deg,#8a5b22 0 6px,transparent 6px 10px);border:1px solid #8a5b22}.facility-swatch{width:11px;height:11px;border:2px solid #fff;border-radius:50%;box-shadow:0 0 0 1px #40556a}.facility-public{background:#6648a3}.facility-medical{background:#b13f3f}.facility-childcare{background:#b56600}.map-alt{margin:0;padding:10px 15px;border-top:1px solid var(--line);color:var(--muted);font-size:.79rem}
    .decision{display:grid;gap:12px}.answer{margin-bottom:14px;padding:16px;border-top:7px solid var(--amber)}.answer .label{margin:0;color:var(--amber);font-size:.73rem;font-weight:900;letter-spacing:.06em}.answer h2{margin:2px 0 5px;font-size:1.35rem;line-height:1.35}.answer p{margin:0;color:#455c6d;font-size:.88rem}.evidence-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.state{padding:5px 8px;border-radius:999px;font-size:.7rem;font-weight:900}.known{background:#ddf1e6;color:#145a3b}.unknown{background:var(--amber-soft);color:#644700}
    .controls{padding:15px}.step-block+.step-block{margin-top:15px;padding-top:14px;border-top:1px solid var(--line)}.step-title{display:flex;align-items:center;gap:8px;margin:0 0 7px;font-size:.88rem;font-weight:900}.step-title b{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--navy);color:#fff;font-size:.73rem}.stop-select{width:100%;min-height:48px;padding:9px 36px 9px 11px;border:2px solid #7893a5;border-radius:10px;background:#fff;color:var(--ink);font-weight:900;cursor:pointer}.stop-help,.helper{display:block;margin-top:5px;color:var(--muted);font-size:.76rem}.needs{display:grid;grid-template-columns:1fr 1fr;gap:7px}.needs button{min-height:48px;padding:8px;border:1px solid #aab9c4;border-radius:9px;background:#fff;color:var(--ink);font-weight:800;cursor:pointer}.needs button[aria-pressed="true"]{border:2px solid var(--teal);background:var(--teal-soft);color:#124c55}.provisional{margin:8px 0 0;padding:8px 9px;border-radius:8px;background:#fff7e4;color:#684b12;font-size:.74rem}
    .stop-card{padding:15px;border-top:7px solid var(--teal)}.stop-card .eyebrow-small,.facilities .eyebrow-small{margin:0;color:var(--teal);font-size:.7rem;font-weight:900}.stop-card h2{margin:1px 0 2px;font-size:1.3rem}.stop-card-time{margin:0;color:var(--muted);font-size:.76rem}.facilities{padding:15px}.facilities h2{margin:1px 0 4px;font-size:1rem}.facility-summary{margin:7px 0 0;color:#334f62;font-size:.82rem;font-weight:800}.facility-counts{display:flex;flex-wrap:wrap;gap:5px;margin:9px 0 0;padding:0;list-style:none}.facility-counts li{padding:4px 7px;border-radius:999px;background:#eef3f6;color:#324b5d;font-size:.7rem;font-weight:900}.facility-zero{margin:9px 0 0;padding:10px;border-radius:9px;background:#fff2cf;color:#664700;font-size:.8rem;font-weight:900}.facility-list{display:grid;gap:5px;max-height:280px;margin:9px 0 0;padding:0;overflow:auto;list-style:none}.facility-list[hidden],.facility-zero[hidden]{display:none}.facility-list li{margin:0}.facility-list button{display:grid;grid-template-columns:12px 1fr;gap:7px;align-items:start;width:100%;min-height:44px;padding:7px 8px;border:1px solid #dbe4e8;border-radius:8px;background:#f8fafb;color:var(--ink);text-align:left;cursor:pointer;scroll-margin:8px}.facility-list button:hover{border-color:#8aa3b2;background:#eef5f7}.facility-list button[aria-current="true"]{border:3px solid var(--navy);background:#e7f2f7}.facility-list i{width:10px;height:10px;margin-top:5px;border-radius:50%}.facility-list strong{display:block}.facility-list small{display:block;color:var(--muted);font-size:.68rem}.facility-selection{margin:8px 0 0;padding:7px 8px;border-left:3px solid var(--teal);background:#eef8f8;color:#28515a;font-size:.72rem}.facility-note{margin:9px 0 0;padding-top:8px;border-top:1px solid var(--line);color:var(--muted);font-size:.72rem}.leaflet-tooltip.stop-label{border:2px solid var(--navy);border-radius:7px;background:#fff;color:var(--navy);font-weight:900;box-shadow:0 2px 8px rgba(18,43,79,.18)}.leaflet-interactive[role="button"]:focus-visible{outline:3px solid #ffb900;outline-offset:3px}
    .checklist{padding:15px}.checklist h2{margin:0 0 9px;font-size:1rem}.checklist ul{display:grid;gap:7px;margin:0;padding:0;list-style:none}.checklist li{display:grid;grid-template-columns:76px 1fr;gap:8px;padding:9px;border-radius:9px;background:#f3f6f8;font-size:.78rem}.checklist strong{color:#215b43}.checklist .not-yet{color:#715516}.next-needed{margin:10px 0 0;padding:10px;border-left:4px solid var(--orange);background:#fff7ef;color:#6a3517;font-size:.8rem}details{margin-top:11px;border-top:1px solid var(--line);padding-top:8px;color:var(--muted);font-size:.75rem}summary{display:flex;align-items:center;min-height:44px;cursor:pointer;color:var(--navy);font-weight:900}details p{margin:4px 0}.source{overflow-wrap:anywhere}footer{padding:17px;text-align:center;color:var(--muted);font-size:.71rem}.leaflet-control-attribution{font-size:10px}.leaflet-popup-content{font-family:inherit;line-height:1.5}
    @media(max-width:900px){.workspace{grid-template-columns:1fr}.decision{grid-template-columns:1fr 1fr}.checklist{grid-column:auto}#map{height:58vh;min-height:460px}}@media(max-width:650px){header{padding:17px 14px}main{padding:10px}.flow{grid-template-columns:1fr 1fr}.flow li{min-height:44px}.question{display:block}.trial-tag{display:inline-block;margin-top:8px}.map-head{display:block}.map-tools{margin-top:10px}.time-buttons{display:grid;grid-template-columns:repeat(3,1fr)}.time-buttons button{width:100%}.decision{grid-template-columns:1fr}#map{height:53vh;min-height:400px}.needs{grid-template-columns:1fr}.legend{max-width:83%}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{scroll-behavior:auto!important;transition:none!important;animation:none!important}}
  </style>
</head>
<body>
  <a class="skip" href="#resident-check">確認画面へ移動</a>
  <header><p class="eyebrow">作品①｜住民向け確認体験のローカル試作</p><h1>このバス停から、車なしで暮らせそう？</h1><p class="lead">徒歩時間内に届く範囲と、まだ分からない生活条件を分けて、住民が次に何を確かめればよいかを示します。</p></header>
  <main id="resident-check">
    <ol class="flow" aria-label="確認の流れ"><li><b>1</b>バス停を見る</li><li><b>2</b>歩く時間を選ぶ</li><li><b>3</b>施設を見る</li><li><b>4</b>今の答えを見る</li></ol>
    <section class="question" aria-labelledby="question-title"><div><h2 id="question-title">将来、車に乗れなくなっても、この場所で生活を続けられるか</h2><p>3つのバス停を切り替え、道路到達の試験用表示面と、その内側にある保存済み公式施設を地図と一覧で確認します。</p></div><span class="trial-tag" id="trial-tag">3停留所・公式3施設データで表示試験中</span></section>
    <section class="card answer" aria-live="polite"><p class="label">いまの答え</p><h2 id="answer-title">まだ判断できません</h2><p id="answer-text">道路計算から作った徒歩範囲と保存済み施設の位置は確認できますが、必要な用事を実際に済ませられるか、坂や安全性、帰り方は未確認です。</p><div class="evidence-row"><span class="state known">確認済み：道路到達</span><span class="state known">確認済み：保存済み施設位置</span><span class="state unknown">未確認：入口・営業時間</span><span class="state unknown">未確認：坂・安全</span><span class="state unknown">未確認：帰りの便</span></div></section>
    <div class="workspace">
      <article class="card" aria-labelledby="map-title"><div class="map-head"><div><h2 id="map-title">バス停から時間内に歩いて届く範囲</h2><p>5分・10分・15分で届く道路が変わる計算は前の線表示と同じです。保存済み施設のうち、表示面内にある座標を点で重ねます。</p></div><div class="map-tools"><div class="time-buttons" aria-label="歩く時間を選ぶ"><button type="button" data-minutes="5" aria-pressed="false">5分</button><button type="button" data-minutes="10" aria-pressed="true">10分</button><button type="button" data-minutes="15" aria-pressed="false">15分</button></div><button class="road-toggle" id="road-toggle" type="button" aria-pressed="false">詳しい道を表示</button></div></div><div class="map-frame"><div id="map" role="region" aria-label="岩国駅バス停から10分以内に歩いて届く範囲と保存済み施設の地図"></div><div class="legend" aria-hidden="true"><span><i class="swatch area"></i>時間内に届く範囲の目安</span><span><i class="facility-swatch facility-public"></i>公共施設</span><span><i class="facility-swatch facility-medical"></i>医療機関</span><span><i class="facility-swatch facility-childcare"></i>子育て施設</span><span id="road-legend" hidden><i class="swatch road"></i>計算に使った道路</span><span id="bridge-legend" hidden><i class="swatch bridge"></i>橋として登録された道</span></div></div><p class="map-alt" id="map-alt">文字での説明：岩国駅バス停から、保存済みの道路計算をもとにした10分以内の範囲と、その内側にある保存済み施設を表示しています。</p></article>
      <aside class="decision" aria-label="住民が確認する内容">
        <section class="card stop-card" aria-labelledby="stop-card-title"><p class="eyebrow-small">バス停カルテ（試験表示）</p><h2 id="stop-card-title">岩国駅</h2><p class="stop-card-time" id="stop-card-time">10分以内の生活インフラ候補</p><p class="facility-summary" id="facility-summary" aria-live="polite">施設を確認しています。</p><ul class="facility-counts" id="facility-counts" aria-label="施設分類別の件数"></ul><p class="facility-zero" id="facility-zero" hidden>この条件で範囲内に該当する保存済み施設は0件です。</p></section>
        <section class="card controls"><div class="step-block"><label class="step-title" for="stop-select"><b>1</b>バス停を選ぶ</label><select class="stop-select" id="stop-select">__STOP_OPTIONS__</select><span class="stop-help">保存範囲から選んだ3つの乗降場所です。最終対象地域や優先停留所ではありません。</span></div><div class="step-block"><h2 class="step-title"><b>2</b>歩く時間</h2><span class="helper" id="time-summary">岩国駅から10分以内で確認中</span></div><div class="step-block"><h2 class="step-title">確かめたい用事（任意の仮例）</h2><div class="needs" aria-label="確かめたい用事の仮例"><button type="button" data-need="shopping" aria-pressed="false">買い物をしたい</button><button type="button" data-need="medical" aria-pressed="false">通院・薬を済ませたい</button><button type="button" data-need="procedure" aria-pressed="false">手続き・相談をしたい</button><button type="button" data-need="undecided" aria-pressed="false">まだ決めていない</button></div><p class="provisional">用事の仮例と、保存済み公式3データセットの分類は別です。生活施設の優先順位や最終分類ではありません。</p></div></section>
        <section class="card facilities" aria-labelledby="facility-title"><p class="eyebrow-small">詳しく見る｜保存済み公式データ</p><h2 id="facility-title"><span id="facility-context">岩国駅・10分</span>の範囲内施設</h2><ul class="facility-list" id="facility-list" aria-label="範囲内の保存済み施設一覧"></ul><p class="facility-selection" id="facility-selection" aria-live="polite">施設名か地図上の点を選ぶと、地図を動かさずに一覧と施設情報を連動します。</p><p class="facility-note">施設座標が試験用表示面の内側にあるかだけを確認しています。入口、営業時間、利用条件や、用事を済ませて帰れることは判定していません。</p></section>
        <section class="card checklist"><h2>判断に使った事実</h2><ul><li><strong>確認できた</strong><span>バス停の位置、時間内にたどれる道路、その表示面内にある保存済み公式施設の座標</span></li><li><strong class="not-yet">まだ未確認</strong><span>選んだ用事を実際に済ませられるか、入口、営業時間、坂、歩道、横断安全性</span></li><li><strong class="not-yet">まだ未確認</strong><span>必要な時間に行き、用事を終えて帰れる便があるか</span></li></ul><p class="next-needed" id="next-needed">次に必要：施設の表示結果と、まだ不足している利用条件を分けて確認します。</p><details><summary>この試作で決めていないこと</summary><p>保存済みの公共施設・医療機関・子育て施設は表示方法を試す3データセットであり、生活施設の定義や優先順位ではありません。最初の対象地域、正式な徒歩条件、完全行程を組み込む段階も未決です。80m/分は正式条件ではありません。面を作る40mの仮幅も表示試験用で、徒歩条件ではありません。</p><p class="source" id="source-record"></p></details></section>
      </aside>
    </div>
  </main>
  <footer>生成日 __BUILD_DATE__｜住民向けの確認順序を試すローカル試作｜公開用ではありません</footer>
  <script src="__LEAFLET_JS_URL__" integrity="__LEAFLET_JS_INTEGRITY__" crossorigin="" defer></script>
  <script type="application/json" id="prototype-data">__PAYLOAD__</script>
  <script>
  "use strict";
  window.addEventListener("DOMContentLoaded",function(){
    const payload=JSON.parse(document.getElementById("prototype-data").textContent);const records=payload.stops;const facilityById=new Map(payload.facility_records.map(function(item){return [item.facility_id,item];}));const facilityCategories=payload.metadata.facility_categories;let selectedRecord=records.find(function(item){return item.stop.stop_id===payload.metadata.default_stop_id;})||records[0];const mapNode=document.getElementById("map");const mapTitle=document.getElementById("map-title");const altNode=document.getElementById("map-alt");const stopSelect=document.getElementById("stop-select");const timeSummary=document.getElementById("time-summary");const answerTitle=document.getElementById("answer-title");const answerText=document.getElementById("answer-text");const nextNeeded=document.getElementById("next-needed");const roadToggle=document.getElementById("road-toggle");const roadLegend=document.getElementById("road-legend");const bridgeLegend=document.getElementById("bridge-legend");const stopCardTitle=document.getElementById("stop-card-title");const stopCardTime=document.getElementById("stop-card-time");const facilityContext=document.getElementById("facility-context");const facilitySummary=document.getElementById("facility-summary");const facilityCounts=document.getElementById("facility-counts");const facilityList=document.getElementById("facility-list");const facilityZero=document.getElementById("facility-zero");const facilitySelection=document.getElementById("facility-selection");document.getElementById("source-record").textContent="保存GTFS：__GTFS_PATH__（SHA-256 __GTFS_SHA256__）｜保存OSM：__OSM_PATH__（SHA-256 __OSM_SHA256__）｜保存公式施設：__FACILITY_PATH__（SHA-256 __FACILITY_SHA256__、304件）｜3停留所の道路到達・表示面・施設内外判定は生成時に作成";
    const needs={shopping:{label:"買い物",gap:"店の入口、営業時間、必要な品物を買えるか、荷物を持って帰れるか"},medical:{label:"通院・薬",gap:"診療時間、薬局、待ち時間、診察後に帰れる交通"},procedure:{label:"手続き・相談",gap:"その窓口で用事が完了するか、受付時間、用事後に帰れる交通"},undecided:{label:"生活全体",gap:"本人が日常で欠かせない用事と、その用事を行って帰る条件"}};
    document.querySelector(".needs").addEventListener("click",function(event){const button=event.target.closest("[data-need]");if(!button){return;}document.querySelectorAll("[data-need]").forEach(function(candidate){candidate.setAttribute("aria-pressed",String(candidate===button));});const selected=needs[button.dataset.need];answerTitle.textContent=selected.label+"については、まだ判断できません";answerText.textContent="道路計算から作った徒歩範囲と保存済み施設の位置は確認できますが、"+selected.gap+"が未確認です。";nextNeeded.textContent="次に必要："+selected.gap+"を、直接データまたは確認可能な方法で確かめます。";});
    if(!window.L){mapNode.innerHTML='<div class="map-fallback">地図を読み込めませんでした。ネット接続を確認してください。</div>';mapNode.setAttribute("role","alert");return;}
    const initialStop=selectedRecord.stop;const map=L.map("map",{center:[initialStop.stop_lat,initialStop.stop_lon],zoom:15,minZoom:5,maxZoom:18,scrollWheelZoom:false});const tiles=L.tileLayer("__OSM_TILE_URL__",{minZoom:5,maxZoom:19,attribution:'__OSM_ATTRIBUTION__'}).addTo(map);tiles.on("tileerror",function(){mapNode.setAttribute("aria-label","背景地図の一部を読み込めませんでした。時間内に届く範囲を表示");});
    let selectedMinutes=10;let areaLayer=null;let roadLayer=null;let facilityLayer=null;let selectedFacilityId=null;const stopLayer=L.layerGroup().addTo(map);const stopMarkerById=new Map();const facilityMarkerById=new Map();records.forEach(function(record){const stop=record.stop;const marker=L.circleMarker([stop.stop_lat,stop.stop_lon],{radius:11,color:"#ffffff",weight:3,fillColor:"#607b8c",fillOpacity:.95}).addTo(stopLayer);marker.bindTooltip(stop.stop_name,{direction:"top",offset:[0,-12],className:"stop-label"});marker.on("click",function(){showStop(stop.stop_id);});stopMarkerById.set(stop.stop_id,marker);const element=marker.getElement();if(element){element.setAttribute("role","button");element.setAttribute("tabindex","0");element.setAttribute("aria-label",stop.stop_name+"バス停を選択");element.addEventListener("keydown",function(event){if(event.key==="Enter"||event.key===" "){event.preventDefault();showStop(stop.stop_id);}});}});
    function roadFeatures(minutes){return selectedRecord.road_payload.features.filter(function(feature){return feature.properties.kind==="reachable_road"&&feature.properties.minutes===minutes;});}
    function drawRoads(){if(roadLayer){map.removeLayer(roadLayer);roadLayer=null;}if(roadToggle.getAttribute("aria-pressed")!=="true"){roadLegend.hidden=true;bridgeLegend.hidden=true;return;}roadLayer=L.geoJSON({type:"FeatureCollection",features:roadFeatures(selectedMinutes)},{style:function(feature){return feature.properties.is_bridge?{color:"#8a5b22",weight:2.4,opacity:.75,dashArray:"7 5"}:{color:"#315f4b",weight:1.4,opacity:.48};},interactive:false}).addTo(map);roadLegend.hidden=false;bridgeLegend.hidden=false;}
    function drawFacilities(){if(facilityLayer){map.removeLayer(facilityLayer);}facilityLayer=L.layerGroup().addTo(map);facilityMarkerById.clear();selectedFacilityId=null;const summary=selectedRecord.facility_reachability.by_minutes[String(selectedMinutes)];const facilities=summary.facility_ids.map(function(facilityId){return facilityById.get(facilityId);}).filter(Boolean);stopCardTitle.textContent=selectedRecord.stop.stop_name;stopCardTime.textContent=selectedMinutes+"分以内の生活インフラ候補";facilityContext.textContent=selectedRecord.stop.stop_name+"・"+selectedMinutes+"分";facilitySummary.textContent="表示面内の保存済み公式施設："+facilities.length+"件";facilitySelection.textContent="施設名か地図上の点を選ぶと、地図を動かさずに一覧と施設情報を連動します。";facilityCounts.replaceChildren();facilityCategories.forEach(function(category){const item=document.createElement("li");item.textContent=category.label+" "+summary.category_counts[category.key]+"件";facilityCounts.appendChild(item);});facilityList.replaceChildren();facilities.forEach(function(facility){const category=facilityCategories.find(function(item){return item.key===facility.common_category;});const marker=L.circleMarker([facility.latitude,facility.longitude],{radius:6,color:"#ffffff",weight:2,fillColor:category.color,fillOpacity:.95});const popup=document.createElement("div");const name=document.createElement("strong");name.textContent=facility.facility_name;const detail=document.createElement("div");detail.textContent=category.label+"｜原本分類："+facility.source_category;popup.append(name,detail);marker.bindPopup(popup,{autoPan:false}).addTo(facilityLayer);marker.on("click",function(){focusFacility(facility.facility_id);});facilityMarkerById.set(facility.facility_id,marker);const listItem=document.createElement("li");const button=document.createElement("button");button.type="button";button.dataset.facilityId=facility.facility_id;button.setAttribute("aria-current","false");button.setAttribute("aria-label",facility.facility_name+"を地図で表示。"+category.label+"、原本分類 "+facility.source_category);const dot=document.createElement("i");dot.style.backgroundColor=category.color;dot.setAttribute("aria-hidden","true");const text=document.createElement("span");const listName=document.createElement("strong");listName.textContent=facility.facility_name;const listDetail=document.createElement("small");listDetail.textContent=category.label+"｜原本分類："+facility.source_category;text.append(listName,listDetail);button.append(dot,text);listItem.appendChild(button);facilityList.appendChild(listItem);});facilityZero.hidden=facilities.length!==0;facilityList.hidden=facilities.length===0;return facilities.length;}
    function focusFacility(facilityId){const facility=facilityById.get(facilityId);const marker=facilityMarkerById.get(facilityId);if(!facility||!marker){return;}if(selectedFacilityId){const previousFacility=facilityById.get(selectedFacilityId);const previousMarker=facilityMarkerById.get(selectedFacilityId);if(previousFacility&&previousMarker){const previousCategory=facilityCategories.find(function(item){return item.key===previousFacility.common_category;});previousMarker.setRadius(6);previousMarker.setStyle({color:"#ffffff",weight:2,fillColor:previousCategory.color,fillOpacity:.95});}}selectedFacilityId=facilityId;marker.setRadius(10);marker.setStyle({color:"#ffb900",weight:4,fillOpacity:1});marker.bringToFront();marker.openPopup();let selectedButton=null;facilityList.querySelectorAll("[data-facility-id]").forEach(function(button){const selected=button.dataset.facilityId===facilityId;button.setAttribute("aria-current",String(selected));if(selected){selectedButton=button;}});if(selectedButton){selectedButton.scrollIntoView({block:"nearest",inline:"nearest"});}facilitySelection.textContent=facility.facility_name+"を地図上と一覧で強調し、施設情報を表示しました。";}
    function updateStopMarkers(){records.forEach(function(record){const stop=record.stop;const marker=stopMarkerById.get(stop.stop_id);const selected=stop.stop_id===selectedRecord.stop.stop_id;marker.setRadius(selected?14:11);marker.setStyle(selected?{color:"#ffb900",weight:4,fillColor:"#07386d",fillOpacity:1}:{color:"#ffffff",weight:3,fillColor:"#607b8c",fillOpacity:.95});const element=marker.getElement();if(element){element.setAttribute("aria-pressed",String(selected));}marker.closeTooltip();marker.bringToFront();if(selected){marker.openTooltip();}});const selectedMarker=stopMarkerById.get(selectedRecord.stop.stop_id);if(selectedMarker){selectedMarker.bringToFront();}}
    function showMinutes(minutes){selectedMinutes=minutes;if(areaLayer){map.removeLayer(areaLayer);}const stop=selectedRecord.stop;const feature=selectedRecord.area_payload.features.find(function(item){return item.properties.minutes===minutes;});areaLayer=L.geoJSON(feature,{style:{color:"#2f694d",weight:2,opacity:.9,fillColor:"#75aa87",fillOpacity:.30,lineJoin:"round"},interactive:false}).addTo(map);drawRoads();const facilityCount=drawFacilities();updateStopMarkers();const viewBounds=areaLayer.getBounds();records.forEach(function(record){viewBounds.extend([record.stop.stop_lat,record.stop.stop_lon]);});if(viewBounds.isValid()){map.fitBounds(viewBounds,{padding:[28,28],maxZoom:16,animate:false});}document.querySelectorAll("[data-minutes]").forEach(function(button){button.setAttribute("aria-pressed",String(Number(button.dataset.minutes)===minutes));});mapTitle.textContent=stop.stop_name+"バス停から時間内に歩いて届く範囲";timeSummary.textContent=stop.stop_name+"から"+minutes+"分以内で確認中";altNode.textContent="文字での説明："+stop.stop_name+"バス停から、保存済みの道路計算をもとにした"+minutes+"分以内の範囲と、その内側にある保存済み施設"+facilityCount+"件を表示しています。地図上の3停留所は選択できます。";mapNode.setAttribute("aria-label",stop.stop_name+"バス停から"+minutes+"分以内に歩いて届く範囲と保存済み施設"+facilityCount+"件の地図。3停留所を選択できます");}
    function showStop(stopId){const nextRecord=records.find(function(item){return item.stop.stop_id===stopId;});if(!nextRecord){return;}selectedRecord=nextRecord;stopSelect.value=selectedRecord.stop.stop_id;showMinutes(selectedMinutes);}
    stopSelect.addEventListener("change",function(){showStop(stopSelect.value);});document.querySelector(".time-buttons").addEventListener("click",function(event){const button=event.target.closest("[data-minutes]");if(button){showMinutes(Number(button.dataset.minutes));}});facilityList.addEventListener("click",function(event){const button=event.target.closest("[data-facility-id]");if(button){focusFacility(button.dataset.facilityId);}});roadToggle.addEventListener("click",function(){const next=roadToggle.getAttribute("aria-pressed")!=="true";roadToggle.setAttribute("aria-pressed",String(next));roadToggle.textContent=next?"詳しい道を隠す":"詳しい道を表示";drawRoads();});showStop(payload.metadata.default_stop_id);
  });
  </script>
</body>
</html>
'''


def render_html(
    payload: dict[str, Any],
    gtfs_sha256: str,
    osm_sha256: str,
) -> str:
    embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    stop_options = "".join(
        '<option value="{stop_id}"{selected}>{stop_name}</option>'.format(
            stop_id=html.escape(item["stop"]["stop_id"], quote=True),
            stop_name=html.escape(item["stop"]["stop_name"]),
            selected=" selected" if item["stop"]["stop_id"] == DEFAULT_STOP_ID else "",
        )
        for item in payload["stops"]
    )
    return (
        HTML_TEMPLATE
        .replace("__LEAFLET_CSS_URL__", LEAFLET_CSS_URL)
        .replace("__LEAFLET_CSS_INTEGRITY__", LEAFLET_CSS_INTEGRITY)
        .replace("__LEAFLET_JS_URL__", LEAFLET_JS_URL)
        .replace("__LEAFLET_JS_INTEGRITY__", LEAFLET_JS_INTEGRITY)
        .replace("__OSM_TILE_URL__", OSM_TILE_URL)
        .replace("__OSM_ATTRIBUTION__", OSM_ATTRIBUTION)
        .replace("__BUILD_DATE__", BUILD_DATE)
        .replace("__STOP_OPTIONS__", stop_options)
        .replace("__GTFS_PATH__", GTFS_INPUT.relative_to(ROOT).as_posix())
        .replace("__GTFS_SHA256__", gtfs_sha256)
        .replace("__OSM_PATH__", OSM_INPUT.relative_to(ROOT).as_posix())
        .replace("__OSM_SHA256__", osm_sha256)
        .replace("__FACILITY_PATH__", payload["metadata"]["facility_source"]["path"])
        .replace("__FACILITY_SHA256__", payload["metadata"]["facility_source"]["sha256"])
        .replace("__PAYLOAD__", embedded)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gtfs-input", type=Path, default=GTFS_INPUT)
    parser.add_argument("--osm-input", type=Path, default=OSM_INPUT)
    parser.add_argument("--facility-input", type=Path, default=FACILITY_INPUT)
    parser.add_argument("--output", type=Path, default=HTML_OUTPUT)
    args = parser.parse_args()
    payload, gtfs_sha256, osm_sha256 = load_prototype_payloads(
        args.gtfs_input,
        args.osm_input,
        args.facility_input,
    )
    html_bytes = render_html(payload, gtfs_sha256, osm_sha256).encode("utf-8")
    args.output.write_bytes(html_bytes)
    print(f"WROTE {args.output} bytes={len(html_bytes)} sha256={hashlib.sha256(html_bytes).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
