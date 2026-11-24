#!/usr/bin/env python3
"""Build a standalone map of the routes in the planning agency's network GeoPackage.

Reads the ``lines`` layer of ``MT_Network_*.gpkg`` (EPSG:2039) and writes one self-contained
HTML page: every route drawn in the colour of its mode, with its name as a label on the map.

    pip install geopandas openpyxl
    python3 scripts/build_network_routes_map.py \
        --gpkg compare/MT_Network_12-11-2026.gpkg \
        --meta compare/MT_Network_MetaData.xlsx \
        --out compare/mt_network_routes.html \
        --csv compare/mt_network_lines.csv

A *route* is ``(type, line_id)``; the existing rail segments all share ``line_id = 0``, so for
them the feature ``name`` completes the key. This is the same definition the network comparison
uses, so the route count matches the comparison pages. The label of a route is its ``line_name``
when the file has one, otherwise its ``name``.

``--csv`` also writes the list of routes as a table (one row per route). The file has no origin
or destination of a line, so the table has none: its stops carry street names only, and those
identify both ends of a line for about one route in six.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import LineString, MultiLineString

# Mode -> how it is drawn. Colours are the validated categorical set (all pairs, light surface);
# Rail fast shares the rail hue (darker step, dashed, drawn above Rail, whose tracks it reuses).
MODES = [
    {"type": "Rail", "label": "Rail", "color": "#2a78d6", "weight": 3.5, "dash": None},
    {"type": "Rail fast", "label": "Fast rail", "color": "#0d366b", "weight": 3.5, "dash": "9 7"},
    {"type": "Metro", "label": "Metro", "color": "#e87ba4", "weight": 4.5, "dash": None},
    {"type": "LRT", "label": "LRT", "color": "#008300", "weight": 3, "dash": None},
    {"type": "BRT", "label": "BRT", "color": "#eda100", "weight": 3, "dash": None},
    {"type": "FUNI", "label": "Funicular / cable", "color": "#1baf7a", "weight": 3.5, "dash": "4 5"},
]
OTHER_MODE = {"color": "#52514e", "weight": 3, "dash": "4 4"}  # a type not listed above
GENERIC_LINE_NAMES = {"fast rail"}  # a line_name shared by many routes: the line_id is appended
ANCHOR_FRACTIONS = (0.5, 0.35, 0.65, 0.2, 0.8)  # label positions tried along the longest part
SIMPLIFY_M = 2.0
RAIL_ASSIGN_M = 250.0  # a stop with line_id 0 belongs to the nearest line_id 0 feature this close
CSV_COLUMNS = [
    "mode", "mode_he", "line_id", "line_name", "name", "year_open", "year_close", "plan", "source",
    "length_km", "stops",
]


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _year(value) -> int | None:
    number = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(number) else int(number)


def read_labels(meta: Path | None) -> dict[str, dict[str, str]]:
    """Hebrew labels of the ``type`` and ``source_plan`` codes (keys lower-cased)."""
    labels: dict[str, dict[str, str]] = {"type": {}, "source_plan": {}}
    if meta is None:
        return labels
    sheet = pd.read_excel(meta, header=0)
    for field, code_col, label_col in (("type", 0, 1), ("source_plan", 8, 9)):
        for code, label in zip(sheet.iloc[:, code_col], sheet.iloc[:, label_col]):
            if _text(code) and _text(label):
                labels[field][_text(code).lower()] = _text(label)
    return labels


def route_key(row) -> str:
    key = f"{row['type']}:{row['line_id']}"
    return f"{key}:{_text(row['name'])}" if row["line_id"] == 0 else key


def route_label(rows: pd.DataFrame) -> str:
    rows = rows.sort_values("_len", ascending=False)
    line_names = list(dict.fromkeys(n for n in map(_text, rows["line_name"]) if n))
    if line_names:
        label = " / ".join(line_names)
        return f"{label} {rows['line_id'].iloc[0]}" if label in GENERIC_LINE_NAMES else label
    names = [n for n in map(_text, rows["name"]) if n]
    return names[0] if names else f"{rows['type'].iloc[0]} {rows['line_id'].iloc[0]}"


def _parts(geom) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, LineString)]


def read_stops(gpkg: Path, lines: gpd.GeoDataFrame) -> pd.DataFrame:
    """The ``stations`` layer with the route key of every stop (column ``_key``).

    A stop belongs to the route of its ``type`` and ``line_id``. The existing rail has
    ``line_id = 0`` on every segment, so such a stop goes to the nearest ``line_id = 0`` feature
    of its type within ``RAIL_ASSIGN_M`` (the rule of the network comparison); farther stops
    belong to no route.
    """
    stops = gpd.read_file(gpkg, layer="stations")
    stops = stops[stops.geometry.notna() & ~stops.geometry.is_empty].reset_index(drop=True)
    stops["line_id"] = pd.to_numeric(stops["line_id"], errors="coerce").fillna(-1).astype(int)
    stops["type"] = stops["type"].map(_text)
    stops["_key"] = [f"{t}:{i}" if i != 0 else None for t, i in zip(stops["type"], stops["line_id"])]
    unnumbered = lines[lines["line_id"] == 0][["type", "_key", "geometry"]]
    for mode, segments in unnumbered.groupby("type"):
        mine = stops[(stops["type"] == mode) & (stops["line_id"] == 0)]
        if mine.empty:
            continue
        near = gpd.sjoin_nearest(mine[["geometry"]], segments[["_key", "geometry"]],
                                 max_distance=RAIL_ASSIGN_M, how="inner")
        near = near.sort_values("index_right")
        near = near[~near.index.duplicated(keep="first")]
        stops.loc[near.index, "_key"] = near["_key"]
    return stops[stops["_key"].notna() & stops["_key"].isin(set(lines["_key"]))]


def build_table(data: dict, stops: pd.DataFrame) -> pd.DataFrame:
    """One row per route, in the order of the mode list, then by line number and name."""
    mode = {m["type"]: (i, m) for i, m in enumerate(data["modes"])}
    n_stops = stops.groupby("_key").size()
    rows = []
    for route in data["routes"]:
        rows.append({
            "_order": (mode[route["type"]][0], route["line_id"], route["label"]),
            "mode": route["type"],
            "mode_he": mode[route["type"]][1]["he"],
            "line_id": route["line_id"] if route["line_id"] > 0 else "",
            "line_name": " / ".join(route["line_names"]),
            "name": " / ".join(route["names"]),
            "year_open": route["opens"] if route["opens"] is not None else "",
            "year_close": route["closes"] if route["closes"] is not None else "",
            "plan": " / ".join(route["plans"]),
            "source": " / ".join(route["sources"]),
            "length_km": route["km"],
            "stops": int(n_stops.get(route["key"], 0)),
        })
    rows.sort(key=lambda r: r["_order"])
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def read_lines(gpkg: Path) -> gpd.GeoDataFrame:
    lines = gpd.read_file(gpkg, layer="lines")
    lines = lines[lines.geometry.notna() & ~lines.geometry.is_empty].reset_index(drop=True)
    lines["line_id"] = pd.to_numeric(lines["line_id"], errors="coerce").fillna(-1).astype(int)
    lines["type"] = lines["type"].map(_text)
    lines["_len"] = lines.geometry.length
    lines["_key"] = [route_key(r) for _, r in lines.iterrows()]
    return lines


def build_data(lines: gpd.GeoDataFrame, source: str, meta: Path | None) -> dict:
    labels = read_labels(meta)
    wgs = lines.geometry.simplify(SIMPLIFY_M).set_crs(lines.crs).to_crs(4326)

    routes, features = [], []
    for key, rows in lines.groupby("_key", sort=True):
        merged = shapely.line_merge(shapely.unary_union(list(rows.geometry)))
        longest = max(_parts(merged), key=lambda g: g.length)
        anchors = gpd.GeoSeries(
            [longest.interpolate(f, normalized=True) for f in ANCHOR_FRACTIONS], crs=lines.crs
        ).to_crs(4326)
        opens = [y for y in map(_year, rows["year_operation"]) if y is not None]
        closes = [_year(v) for v in rows["year_cancel"]]
        plans = list(dict.fromkeys(p for p in map(_text, rows["source_plan"]) if p))
        routes.append({
            "key": key,
            "type": rows["type"].iloc[0],
            "line_id": int(rows["line_id"].iloc[0]),
            "label": route_label(rows),
            "names": list(dict.fromkeys(n for n in map(_text, rows["name"]) if n)),
            "line_names": list(dict.fromkeys(n for n in map(_text, rows["line_name"]) if n)),
            "opens": min(opens) if opens else None,
            "closes": max(c for c in closes if c is not None) if all(c is not None for c in closes) else None,
            "plans": [labels["source_plan"].get(p.lower(), p) for p in plans],
            "sources": list(dict.fromkeys(s for s in map(_text, rows["source_name"]) if s)),
            "km": round(float(merged.length) / 1000, 1),
            "anchors": [[round(p.y, 5), round(p.x, 5)] for p in anchors],
        })
        for idx, row in rows.iterrows():
            features.append({
                "key": key,
                "opens": _year(row["year_operation"]),
                "closes": _year(row["year_cancel"]),
                "paths": [[[round(y, 5), round(x, 5)] for x, y in part.coords] for part in _parts(wgs[idx])],
            })

    known = {m["type"] for m in MODES}
    modes = [dict(m, he=labels["type"].get(m["type"].lower(), "")) for m in MODES]
    for extra in sorted(set(lines["type"]) - known):
        modes.append(dict(OTHER_MODE, type=extra, label=extra or "(no type)", he=labels["type"].get(extra.lower(), "")))
    present = set(lines["type"])
    years = sorted({f["opens"] for f in features if f["opens"] is not None})
    return {
        "source": source,
        "modes": [m for m in modes if m["type"] in present],
        "routes": routes,
        "features": features,
        "years": years,
    }


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>מנהל התכנון network: transit lines by mode</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700&display=swap">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
:root { color-scheme: light; --bg: #f4f3ef; --panel: #fffefb; --panel-border: #dcd9d0; --ink: #1c1b18; --ink-2: #5b5950; --ink-3: #8a877c; --map-bg: #e9e9e9; --shadow: 0 4px 18px rgba(30,28,20,.16); --accent: #2a78d6; --focus: #2a78d6; --label-bg: rgba(255,254,251,.94); --label-ink: #1c1b18; --label-border: rgba(28,27,24,.18); }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark; --bg: #17171a; --panel: #212125; --panel-border: #3a3a40; --ink: #f2f1ea; --ink-2: #c3c2b7; --ink-3: #8b8a82; --shadow: 0 4px 18px rgba(0,0,0,.5); --accent: #3987e5; --focus: #3987e5; } }
:root[data-theme="dark"] { color-scheme: dark; --bg: #17171a; --panel: #212125; --panel-border: #3a3a40; --ink: #f2f1ea; --ink-2: #c3c2b7; --ink-3: #8b8a82; --shadow: 0 4px 18px rgba(0,0,0,.5); --accent: #3987e5; --focus: #3987e5; }

html, body { height: 100%; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.4 "Heebo", "Segoe UI", system-ui, sans-serif; }
#map { position: absolute; inset: 0; background: var(--map-bg); }
.leaflet-container { background: var(--map-bg); font: inherit; }
.osm-gray { filter: grayscale(1) brightness(1.06) contrast(0.88); }
.leaflet-bar { box-shadow: var(--shadow); border: 1px solid var(--panel-border); }
.leaflet-bar a { background: var(--panel); color: var(--ink); border-bottom-color: var(--panel-border); }
.leaflet-bar a:hover, .leaflet-bar a:focus-visible { background: var(--bg); }
.leaflet-control-attribution { background: color-mix(in srgb, var(--panel) 85%, transparent); color: var(--ink-3); font-size: 11px; }
.leaflet-control-attribution a { color: var(--ink-2); }
.leaflet-popup-content-wrapper, .leaflet-popup-tip { background: var(--panel); color: var(--ink); box-shadow: var(--shadow); }
.leaflet-popup-content-wrapper { border-radius: 8px; border: 1px solid var(--panel-border); }
.leaflet-popup-content { margin: 12px 14px; font-size: 13px; min-width: 220px; }
.leaflet-container a.leaflet-popup-close-button { color: var(--ink-3); }
.leaflet-container :focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.panel { position: absolute; z-index: 1000; top: calc(12px + env(safe-area-inset-top, 0px)); left: 12px; width: 336px; max-width: calc(100% - 24px); max-height: calc(100% - 24px); overflow: auto;
  background: var(--panel); border: 1px solid var(--panel-border); border-radius: 10px; box-shadow: var(--shadow); padding: 14px 16px 12px; box-sizing: border-box; }
.panel h1 { margin: 0; font-size: 17px; font-weight: 700; letter-spacing: -.01em; text-wrap: balance; }
.panel .sub { margin: 2px 0 0; color: var(--ink-2); font-size: 12.5px; }
.panel bdi { white-space: nowrap; }
.eyebrow { margin: 14px 0 6px; font-size: 11px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--ink-3); }
.sets { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.sets label { display: grid; grid-template-columns: 18px 30px 1fr auto; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 6px; cursor: pointer; }
.sets label:hover { background: var(--bg); }
.sets input { margin: 0; width: 15px; height: 15px; accent-color: var(--accent); }
.sets input:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.sets .lbl { font-weight: 500; line-height: 1.2; }
.sets .lbl small { display: block; font-weight: 400; color: var(--ink-3); font-size: 11.5px; }
.sets .cnt { color: var(--ink-2); font-variant-numeric: tabular-nums; font-size: 13px; text-align: right; }
.sym { justify-self: center; width: 28px; height: 14px; background: #f2f2f0; border-radius: 3px; }
.pick { display: grid; grid-template-columns: 1fr auto; gap: 6px; margin-top: 6px; }
.pick.one { grid-template-columns: 1fr; }
.pick.two { grid-template-columns: 1fr 1fr; }
.pick select { font: inherit; font-size: 12.5px; padding: 5px 6px; border-radius: 6px; border: 1px solid var(--panel-border); background: var(--bg); color: var(--ink); min-width: 0; }
.pick select:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
.actions button { flex: 1 1 auto; white-space: nowrap; font: inherit; font-size: 12.5px; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--panel-border); background: var(--bg); color: var(--ink); cursor: pointer; }
.actions button:hover { border-color: var(--ink-3); }
.actions button:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
.note { margin: 10px 0 0; font-size: 11.5px; color: var(--ink-3); }
.bm-note { color: var(--ink-2); }
.bm-note:empty { display: none; }
.pp h2 { margin: 0 0 4px; font-size: 14px; font-weight: 700; line-height: 1.25; }
.pp .mode { display: flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--ink-2); }
.pp .kv { display: grid; grid-template-columns: auto 1fr; gap: 2px 8px; font-size: 12.5px; margin: 8px 0 0; }
.pp .kv dt { color: var(--ink-3); } .pp .kv dd { margin: 0; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.pp button { font: inherit; font-size: 12px; margin-top: 8px; padding: 4px 8px; border-radius: 6px; border: 1px solid var(--panel-border); background: var(--bg); color: var(--ink); cursor: pointer; }
.dot { flex: none; width: 9px; height: 9px; border-radius: 50%; box-shadow: 0 0 0 1px rgba(28,27,24,.25); }
.leaflet-names-pane { z-index: 620; pointer-events: none; }
.rt-label { position: absolute; left: 0; top: 0; display: flex; align-items: center; gap: 5px; white-space: nowrap; padding: 1px 7px 1px 5px; border-radius: 99px;
  background: var(--label-bg); color: var(--label-ink); border: 1px solid var(--label-border); font-size: 11.5px; font-weight: 500; line-height: 1.35; visibility: hidden; will-change: transform; }
.rt-label .dot { width: 8px; height: 8px; }
.names-off .rt-label, .zooming .rt-label { visibility: hidden !important; }
@media (max-width: 560px) {
  .panel { top: auto; bottom: calc(12px + env(safe-area-inset-bottom, 0px)); left: 12px; right: 12px; width: auto; max-height: 50%; }
  .leaflet-top.leaflet-right { top: env(safe-area-inset-top, 0px); }
}
@media (prefers-reduced-motion: reduce) { .leaflet-zoom-anim .leaflet-zoom-animated, .leaflet-fade-anim .leaflet-popup { transition: none; } }
</style>
</head>
<body>
<div id="map" role="application" aria-label="Map of the transit lines of מנהל התכנון, coloured by mode"></div>

<section class="panel" id="panel" aria-label="Modes and legend">
  <h1><bdi>מנהל התכנון</bdi> network: transit lines by mode</h1>
  <p class="sub" id="sub"></p>
  <p class="eyebrow">Filter</p>
  <div class="pick two">
    <select id="pick-mode" aria-label="Mode"><option value="">all modes</option><option value="*" hidden>several modes</option></select>
    <select id="pick-year" aria-label="Opening year"><option value="">all years</option></select>
  </div>
  <p class="eyebrow">Mode</p>
  <ul class="sets" id="modes"></ul>
  <ul class="sets" style="margin-top:6px">
    <li><label><input type="checkbox" id="set-names" checked>
      <svg class="sym" viewBox="0 0 28 14" aria-hidden="true" style="background:none"><rect x="1.5" y="2.5" width="25" height="9" rx="4.5" fill="var(--panel)" stroke="var(--ink-3)"/><line x1="7" y1="7" x2="21" y2="7" stroke="var(--ink-2)" stroke-width="1.5"/></svg>
      <span class="lbl">Line names<small>as many as fit without overlapping; zoom in for more</small></span><span class="cnt"></span></label></li>
  </ul>
  <p class="eyebrow">Find a line</p>
  <div class="pick one"><select id="pick-line" aria-label="Line"></select></div>
  <div class="actions">
    <button type="button" id="btn-fit">Zoom to all</button>
    <button type="button" id="btn-tlv">Tel Aviv</button>
    <button type="button" id="btn-hfa">Haifa</button>
    <button type="button" id="btn-jlm">Jerusalem</button>
    <button type="button" id="btn-bsh">Be'er Sheva</button>
  </div>
  <p class="eyebrow">Basemap</p>
  <div class="pick one"><select id="basemap" aria-label="Basemap"></select></div>
  <p class="note bm-note" id="basemap-note" role="status" aria-live="polite"></p>
  <p class="note">A line is one mode and line number; the existing rail network has no line numbers, so it is split by the segment names of the file. Names come from the file as they are.</p>
  <p class="note">Picking a year shows every line that opens by that year, including lines that close later on; the popup of a line gives its years.</p>
</section>

<script type="application/json" id="page-data">__DATA__</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
var HUBS_BASEMAPS = [{"id":"carto","name":"CARTO light","url":"https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png","options":{"subdomains":"abcd","maxZoom":20,"attribution":"&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors &copy; <a href=\"https://carto.com/attributions\">CARTO</a>"}},{"id":"esri","name":"Esri light gray","url":"https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}","options":{"maxNativeZoom":16,"maxZoom":19,"attribution":"Tiles &copy; Esri"}},{"id":"osm","name":"OpenStreetMap (light gray)","url":"https://tile.openstreetmap.org/{z}/{x}/{y}.png","options":{"maxZoom":19,"className":"osm-gray","attribution":"&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors"}},{"id":"none","name":"No basemap","url":null,"options":{}}];

// Basemaps in order; when the first tiles of the active one all fail before any loads, the
// next one is tried and a short notice in the panel says so. A basemap the user picks is
// never replaced. (Same behaviour as the two network comparison pages.)
function hubsBasemap(map, select, note) {
  var list = HUBS_BASEMAPS, active = null, current = -1, auto = true;
  list.forEach(function (b, i) {
    var o = document.createElement('option'); o.value = String(i); o.textContent = b.name; select.appendChild(o);
  });
  var none = list.length - 1;
  function use(i) {
    if (active) { map.removeLayer(active); active = null; }
    current = i; select.value = String(i);
    map.getContainer().setAttribute('data-basemap', list[i].id);
    var b = list[i];
    if (!b.url) return;
    var layer = L.tileLayer(b.url, b.options), loaded = 0, failed = 0, done = false;
    function fail() {
      if (done || layer !== active) return;
      done = true;
      setTimeout(switchAway, 0);
    }
    function switchAway() {
      if (layer !== active) return;
      if (!auto) { note.textContent = 'Basemap tiles from ' + b.name + ' did not load (blocked or offline).'; return; }
      var next = i + 1;
      if (next < none) {
        use(next);
        note.textContent = 'Basemap tiles from ' + b.name + ' did not load (blocked or offline); switched to ' + list[next].name + '.';
      } else {
        use(none);
        note.textContent = 'No basemap tiles could be loaded; the lines still draw on the gray background.';
      }
    }
    layer.on('tileload', function () { if (layer !== active) return; loaded++; auto = false; });
    layer.on('tileerror', function () { if (layer !== active) return; failed++; if (!loaded && failed >= 6) fail(); });
    layer.on('load', function () { if (layer === active && !loaded && failed) fail(); });
    active = layer;
    layer.addTo(map);
  }
  select.addEventListener('change', function () { auto = false; note.textContent = ''; use(Number(select.value)); });
  var requested = new URLSearchParams(window.location.search).get('basemap');
  if (requested !== null && /^[0-9]+$/.test(requested) && Number(requested) < list.length) {
    select.value = requested;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  } else {
    use(0);
  }
  return {current: function () { return list[current].id; }};
}

(function () {
  'use strict';
  const DATA = JSON.parse(document.getElementById('page-data').textContent);
  const $ = id => document.getElementById(id);
  const esc = t => String(t ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const bdi = t => '<bdi>' + esc(t) + '</bdi>';
  const has = v => v != null && v !== '';
  const panel = $('panel');
  if (typeof L === 'undefined') {
    $('basemap-note').textContent = 'The map could not be drawn: Leaflet did not load from cdnjs (offline?).';
    return;
  }
  const MODE = {}, ROUTE = {};
  DATA.modes.forEach(m => { MODE[m.type] = Object.assign({routes: [], on: true}, m); });
  DATA.routes.forEach(r => { ROUTE[r.key] = Object.assign({layers: [], casings: [], feats: []}, r); MODE[r.type].routes.push(r.key); });
  const modeText = m => m.label + (m.he ? ' · ' + m.he : '');
  $('sub').innerHTML = DATA.routes.length + ' lines from ' + bdi(DATA.source) + ' · coloured by mode · click a line for its details';

  const map = L.map('map', {zoomControl: false, renderer: L.canvas({tolerance: 6, padding: .3})});
  L.control.zoom({position: 'topright'}).addTo(map);
  map.attributionControl.setPrefix('');
  const ISRAEL = [[29.4, 34.2], [33.4, 35.9]];
  map.fitBounds(ISRAEL);
  const basemap = hubsBasemap(map, $('basemap'), $('basemap-note'));
  const bounds = L.latLngBounds([]);

  // Lines: a white casing below every line keeps crossing and parallel lines apart; modes are
  // drawn in list order, so Fast rail (dashed) stays readable on the rail tracks it shares.
  const state = {year: null, pick: null};
  const casingGroup = L.layerGroup().addTo(map), lineGroup = L.layerGroup().addTo(map);
  const order = {}; DATA.modes.forEach((m, i) => { order[m.type] = i; });
  const FEATS = [];
  DATA.features.slice().sort((a, b) => order[ROUTE[a.key].type] - order[ROUTE[b.key].type]).forEach(f => {
    const r = ROUTE[f.key], m = MODE[r.type];
    const casing = L.polyline(f.paths, {color: '#ffffff', weight: m.weight + 2.5, opacity: .85, interactive: false});
    const line = L.polyline(f.paths, {color: m.color, weight: m.weight, opacity: .95, dashArray: m.dash, lineCap: m.dash ? 'butt' : 'round'});
    line.bindTooltip(() => bdi(r.label) + ' · ' + esc(m.label), {sticky: true});
    line.bindPopup(() => popup(r), {maxWidth: 340});
    const feat = {f: f, r: r, line: line, casing: casing, shown: false};
    r.feats.push(feat); FEATS.push(feat);
    bounds.extend(line.getBounds());
    r.bounds = (r.bounds || L.latLngBounds([])).extend(line.getBounds());
  });
  const inYear = f => state.year == null || f.opens == null || f.opens <= state.year;  // opened by that year
  const years = r => has(r.opens) ? (has(r.closes) ? r.opens + ' to ' + r.closes : 'from ' + r.opens) : '';
  function popup(r) {
    const m = MODE[r.type];
    const rows = [['line number', r.line_id > 0 ? r.line_id : ''], ['line name', r.line_names.map(bdi).join(', ')],
      ['name in the file', r.names.map(bdi).join(', ')], ['years', esc(years(r))], ['plan', r.plans.map(bdi).join(', ')],
      ['source', r.sources.map(bdi).join(', ')], ['length', r.km.toLocaleString('en') + ' km']];
    return '<div class="pp" dir="auto"><h2>' + bdi(r.label) + '</h2><div class="mode"><span class="dot" style="background:' + m.color + '"></span>' + esc(modeText(m)) + '</div>'
      + '<dl class="kv">' + rows.filter(x => has(x[1])).map(x => '<dt>' + esc(x[0]) + '</dt><dd>' + x[1] + '</dd>').join('') + '</dl>'
      + '<button type="button" data-zoom="' + esc(r.key) + '">Zoom to line</button></div>';
  }
  let drawnPick = null;
  function refresh() {  // which features are drawn, in mode order, and how strongly
    let changed = false;
    Object.values(ROUTE).forEach(r => { r.visible = false; });
    FEATS.forEach(x => {
      const show = MODE[x.r.type].on && inYear(x.f);
      if (show !== x.shown) { x.shown = show; changed = true; }
      if (show) x.r.visible = true;
    });
    if (state.pick != null && !ROUTE[state.pick].visible) state.pick = null;
    if (changed) fillLines();
    sel.value = state.pick || '';
    if (changed || drawnPick !== state.pick) {  // a canvas draws in the order layers were added: casings, then lines
      drawnPick = state.pick;
      casingGroup.clearLayers(); lineGroup.clearLayers();
      const shown = FEATS.filter(x => x.shown);
      shown.forEach(x => casingGroup.addLayer(x.casing));
      shown.forEach(x => lineGroup.addLayer(x.line));
    }
    FEATS.forEach(x => {
      if (!x.shown) return;
      const dim = state.pick != null && state.pick !== x.r.key;
      x.line.setStyle({opacity: dim ? .12 : .95});
      x.casing.setStyle({opacity: dim ? 0 : .85});
    });
    if (state.pick != null) FEATS.forEach(x => { if (x.shown && x.r.key === state.pick) { x.casing.bringToFront(); x.line.bringToFront(); } });
    DATA.modes.forEach(m => { $('cnt-' + m.type).textContent = MODE[m.type].routes.filter(k => ROUTE[k].feats.some(x => inYear(x.f))).length; });
    placeLabels();
  }

  // Legend rows: one per mode, with the line symbol the map uses.
  DATA.modes.forEach(m => {
    const li = document.createElement('li');
    li.innerHTML = '<label><input type="checkbox" checked><svg class="sym" viewBox="0 0 28 14" aria-hidden="true"><line x1="2" y1="7" x2="26" y2="7" stroke="' + m.color
      + '" stroke-width="' + m.weight + '"' + (m.dash ? ' stroke-dasharray="' + m.dash + '"' : ' stroke-linecap="round"') + '/></svg>'
      + '<span class="lbl">' + esc(m.label) + (m.he ? '<small>' + bdi(m.he) + '</small>' : '') + '</span><span class="cnt" id="cnt-' + esc(m.type) + '"></span></label>';
    const box = li.querySelector('input');
    MODE[m.type].box = box;
    box.addEventListener('change', e => { MODE[m.type].on = e.target.checked; syncMode(); refresh(); });
    $('modes').appendChild(li);
  });

  // Mode filter: one mode or all of them; the checkboxes above allow any other combination.
  const selMode = $('pick-mode');
  DATA.modes.forEach(m => { const o = document.createElement('option'); o.value = m.type; o.textContent = modeText(m); selMode.appendChild(o); });
  function syncMode() {
    const on = DATA.modes.filter(m => MODE[m.type].on);
    selMode.value = on.length === DATA.modes.length ? '' : on.length === 1 ? on[0].type : '*';
  }
  selMode.addEventListener('change', () => {
    DATA.modes.forEach(m => { MODE[m.type].on = selMode.value === '' || selMode.value === m.type; MODE[m.type].box.checked = MODE[m.type].on; });
    refresh();
  });

  // Name labels: one per line, placed where it does not cover another label or the panel.
  const pane = map.createPane('names');
  const labels = DATA.routes.map(r => {
    const el = document.createElement('div');
    el.className = 'rt-label'; el.dir = 'auto';
    el.innerHTML = '<span class="dot" style="background:' + MODE[r.type].color + '"></span>' + esc(r.label);
    pane.appendChild(el);
    return {r: ROUTE[r.key], el: el, w: 0, h: 0, named: r.line_names.length > 0};
  }).sort((a, b) => (b.named - a.named) || (b.r.km - a.r.km));
  function measure() { labels.forEach(l => { l.w = l.el.offsetWidth; l.h = l.el.offsetHeight; }); }
  const hit = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
  function placeLabels() {
    const size = map.getSize(), taken = [], pr = panel.getBoundingClientRect(), mr = map.getContainer().getBoundingClientRect();
    taken.push([pr.left - mr.left - 4, pr.top - mr.top - 4, pr.right - mr.left + 4, pr.bottom - mr.top + 4]);
    labels.forEach(l => {
      const r = l.r;
      let placed = false;
      if (r.visible && (state.pick == null || state.pick === r.key) && r.bounds) {
        const a = map.latLngToContainerPoint(r.bounds.getNorthWest()), b = map.latLngToContainerPoint(r.bounds.getSouthEast());
        if (Math.hypot(b.x - a.x, b.y - a.y) >= 46 || state.pick === r.key) {
          for (const c of r.anchors) {
            const p = map.latLngToContainerPoint(c);
            const box = [p.x - l.w / 2 - 3, p.y - l.h / 2 - 3, p.x + l.w / 2 + 3, p.y + l.h / 2 + 3];
            if (box[0] < 0 || box[1] < 0 || box[2] > size.x || box[3] > size.y || taken.some(t => hit(t, box))) continue;
            const q = map.latLngToLayerPoint(c);
            l.el.style.transform = 'translate(' + Math.round(q.x - l.w / 2) + 'px,' + Math.round(q.y - l.h / 2) + 'px)';
            taken.push(box); placed = true;
            break;
          }
        }
      }
      l.el.style.visibility = placed ? 'visible' : 'hidden';
    });
  }
  map.on('zoomstart', () => pane.classList.add('zooming'));
  map.on('zoomend', () => pane.classList.remove('zooming'));
  map.on('moveend zoomend resize', placeLabels);
  $('set-names').addEventListener('change', e => pane.classList.toggle('names-off', !e.target.checked));

  // Find a line: the lines that pass the filters, grouped by mode. And the year filter.
  const sel = $('pick-line'), selYear = $('pick-year');
  function fillLines() {
    sel.textContent = '';
    const all = document.createElement('option'); all.value = '';
    sel.appendChild(all);
    let n = 0;
    DATA.modes.forEach(m => {
      const shown = MODE[m.type].routes.map(k => ROUTE[k]).filter(r => r.visible).sort((a, b) => a.label.localeCompare(b.label, 'en', {numeric: true}));
      if (!shown.length) return;
      const g = document.createElement('optgroup'); g.label = modeText(m);
      shown.forEach(r => {
        const o = document.createElement('option'); o.value = r.key;
        o.textContent = r.label + (r.line_id > 0 && !r.label.includes(String(r.line_id)) ? ' (' + r.line_id + ')' : '');
        g.appendChild(o);
      });
      sel.appendChild(g); n += shown.length;
    });
    all.textContent = n === DATA.routes.length ? 'all ' + n + ' lines' : 'all ' + n + ' lines shown';
  }
  DATA.years.forEach(y => { const o = document.createElement('option'); o.value = y; o.textContent = 'up to ' + y; selYear.appendChild(o); });
  // Fit padding that keeps the fitted area clear of the panel when it sits beside the map.
  const clear = pad => window.innerWidth > 560 ? {paddingTopLeft: [panel.offsetWidth + 12 + pad, pad], paddingBottomRight: [pad, pad]} : {padding: [pad, pad]};
  function zoomTo(key) {
    const r = ROUTE[key];
    if (r && r.bounds && r.bounds.isValid()) map.fitBounds(r.bounds, Object.assign(clear(40), {maxZoom: 15}));
  }
  function pick(key, zoom) {
    state.pick = key || null;
    refresh();
    if (state.pick && zoom) zoomTo(state.pick);
  }
  sel.addEventListener('change', () => pick(sel.value, true));
  selYear.addEventListener('change', () => {
    state.year = selYear.value ? Number(selYear.value) : null;
    refresh();
  });
  map.on('popupopen', e => {
    const b = e.popup.getElement() && e.popup.getElement().querySelector('button[data-zoom]');
    if (b) b.addEventListener('click', () => pick(b.dataset.zoom, true));
  });
  const fitAll = () => bounds.isValid() ? map.fitBounds(bounds, clear(30)) : map.fitBounds(ISRAEL);
  $('btn-fit').addEventListener('click', () => { pick(null); fitAll(); });
  [['btn-tlv', [32.08, 34.82]], ['btn-hfa', [32.80, 35.02]], ['btn-jlm', [31.78, 35.21]],
   ['btn-bsh', [31.25, 34.79]]].forEach(c => $(c[0]).addEventListener('click', () => map.setView(c[1], 12)));
  L.DomEvent.disableClickPropagation(panel);
  L.DomEvent.disableScrollPropagation(panel);

  fitAll();
  measure();
  refresh();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => { measure(); placeLabels(); });
  window.hubsPage = {map: map, routes: ROUTE, modes: MODE, basemap: basemap, pick: pick, placeLabels: placeLabels};
})();</script>

</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gpkg", required=True, type=Path, help="the agency network (layer `lines`)")
    parser.add_argument("--meta", type=Path, default=None, help="optional MT_Network_MetaData.xlsx (Hebrew labels)")
    parser.add_argument("--out", required=True, type=Path, help="HTML file to write")
    parser.add_argument("--csv", type=Path, default=None, help="optional CSV file to write: one row per route")
    args = parser.parse_args()

    lines = read_lines(args.gpkg)
    data = build_data(lines, args.gpkg.name, args.meta)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    args.out.write_text(PAGE.replace("__DATA__", payload), encoding="utf-8")
    per_mode = pd.Series([r["type"] for r in data["routes"]]).value_counts()
    print(f"wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB): {len(data['routes'])} routes, "
          f"{len(data['features'])} line features")
    print("  " + ", ".join(f"{m['type']} {int(per_mode.get(m['type'], 0))}" for m in data["modes"]))
    if args.csv is not None:
        table = build_table(data, read_stops(args.gpkg, lines))
        table.to_csv(args.csv, index=False, encoding="utf-8-sig")  # the BOM lets Excel read the Hebrew
        print(f"wrote {args.csv}: {len(table)} routes")


if __name__ == "__main__":
    main()
