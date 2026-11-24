#!/usr/bin/env python3
"""Add the marked differences of the agency GeoPackage to the two network comparison pages.

``MT_Network_*.gpkg`` carries a point layer ``mot_differences``: places where the two networks
differ, each with its kind (``type``: hub / line), who is to correct it (``to_correct``), the
``reason`` and a ``note``. This script draws those points on the comparison pages as one more
set with its own checkbox: the ``line`` points on ``network_comparison_routes.html`` and the
``hub`` points on ``network_comparison_hubs.html``.

    pip install geopandas
    python3 scripts/add_mot_differences.py --gpkg compare/MT_Network_12-11-2026.gpkg

The pages are generated elsewhere (``hubs compare-network`` of the HubPrioritizing project), so
nothing in them is rewritten: one marked block is inserted before ``</body>``. Running the script
again replaces that block, so it is safe to repeat, also after the pages are regenerated.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

LAYER = "mot_differences"
START = "<!-- mot-differences:start (scripts/add_mot_differences.py) -->"
END = "<!-- mot-differences:end -->"
PAGES = {"line": "network_comparison_routes.html", "hub": "network_comparison_hubs.html"}

BLOCK = r"""<style>
.md-icon { background: none; border: 0; }
.md-icon svg { display: block; overflow: visible; filter: drop-shadow(0 1px 2px rgba(0,0,0,.4)); }
.md-sym { justify-self: center; width: 22px; height: 16px; background: #f2f2f0; border-radius: 3px; }
</style>
<script type="application/json" id="mot-differences-data">__DATA__</script>
<script>
// Marked differences: the points of the layer mot_differences, as one more set per "to correct".
(function () {
  'use strict';
  var page = window.hubsPage, panel = document.getElementById('panel');
  if (!page || !page.map || !panel || typeof L === 'undefined') return;
  var DATA = JSON.parse(document.getElementById('mot-differences-data').textContent);
  if (!DATA.points.length) return;
  var esc = function (t) { return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]; }); };
  var INK = '#1c1b18', PAPER = '#ffffff';
  // A diamond, so it cannot be mistaken for a hub (circle) or a line; the fill tells who corrects.
  var LOOK = {Team: {fill: INK, stroke: PAPER, width: 1.6}, MOT: {fill: PAPER, stroke: INK, width: 2.4}};
  var look = function (who) { return LOOK[who] || {fill: '#8a877c', stroke: PAPER, width: 1.6}; };
  var diamond = function (who, size) {
    var k = look(who), h = size / 2, r = h - 2;
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '" aria-hidden="true"><path d="M' + h + ' ' + (h - r) + ' L' + (h + r) + ' ' + h + ' L' + h + ' ' + (h + r) + ' L' + (h - r) + ' ' + h + ' Z" fill="' + k.fill + '" stroke="' + k.stroke + '" stroke-width="' + k.width + '" stroke-linejoin="round"/></svg>';
  };
  var who = [];
  DATA.points.forEach(function (p) { if (who.indexOf(p.to_correct) < 0) who.push(p.to_correct); });
  who.sort(function (a, b) { return (a === 'Team' ? 0 : a === 'MOT' ? 1 : 2) - (b === 'Team' ? 0 : b === 'MOT' ? 1 : 2) || a.localeCompare(b); });

  var lists = panel.querySelectorAll('ul.sets'), last = lists[lists.length - 1];
  var head = document.createElement('p'), list = document.createElement('ul');
  head.className = 'eyebrow'; head.textContent = 'Marked differences';
  list.className = 'sets';
  last.parentNode.insertBefore(list, last.nextSibling);
  last.parentNode.insertBefore(head, list);

  var groups = {};
  who.forEach(function (w) {
    var pts = DATA.points.filter(function (p) { return p.to_correct === w; });
    var group = groups[w] = L.layerGroup().addTo(page.map);
    pts.forEach(function (p) {
      var title = (p.kind === 'hub' ? 'Hub' : p.kind === 'line' ? 'Line' : esc(p.kind)) + ' difference';
      var rows = [['to correct', esc(w)], ['reason', esc(p.reason)], ['note', p.note ? '<bdi>' + esc(p.note) + '</bdi>' : ''], ['from', '<bdi>' + esc(DATA.source) + '</bdi>, layer ' + esc(DATA.layer)]];
      var m = L.marker([p.lat, p.lng], {icon: L.divIcon({className: 'md-icon', html: diamond(w, 22), iconSize: [22, 22], iconAnchor: [11, 11], popupAnchor: [0, -10]}),
        title: title + ', to correct: ' + w, alt: title, riseOnHover: true});
      m.bindTooltip(esc(title) + ' · to correct: ' + esc(w) + (p.reason ? ' · ' + esc(p.reason) : ''), {direction: 'top', offset: [0, -9]});
      m.bindPopup('<div class="pp" dir="auto"><h2>' + esc(title) + '</h2><dl class="kv">' + rows.filter(function (r) { return r[1]; }).map(function (r) { return '<dt>' + r[0] + '</dt><dd>' + r[1] + '</dd>'; }).join('') + '</dl></div>', {maxWidth: 320});
      group.addLayer(m);
    });
    var reasons = [];
    pts.forEach(function (p) { if (p.reason && reasons.indexOf(p.reason) < 0) reasons.push(p.reason); });
    var li = document.createElement('li');
    li.innerHTML = '<label><input type="checkbox" checked><span class="md-sym">' + diamond(w, 16).replace('<svg ', '<svg style="display:block;margin:0 auto" ') + '</span>'
      + '<span class="lbl">To correct: ' + esc(w) + '<small>' + esc(DATA.kind_label) + ' marked in the file' + (reasons.length ? ' · ' + esc(reasons.join(', ')) : '') + '</small></span><span class="cnt">' + pts.length + '</span></label>';
    li.querySelector('input').addEventListener('change', function (e) { if (e.target.checked) group.addTo(page.map); else page.map.removeLayer(group); });
    list.appendChild(li);
  });
  page.motDifferences = {groups: groups, points: DATA.points};
})();
</script>"""


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def read_points(gpkg: Path) -> list[dict]:
    layer = gpd.read_file(gpkg, layer=LAYER)
    layer = layer[layer.geometry.notna() & ~layer.geometry.is_empty].to_crs(4326)
    return [
        {
            "kind": _text(row["type"]).lower(),
            "to_correct": _text(row["to_correct"]) or "not stated",
            "reason": _text(row["reason"]),
            "note": _text(row["note"]),
            "lat": round(geom.y, 6),
            "lng": round(geom.x, 6),
        }
        for (_, row), geom in zip(layer.iterrows(), layer.geometry)
    ]


def inject(page: Path, data: dict) -> None:
    html = page.read_text(encoding="utf-8")
    html = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", html, flags=re.S)
    if html.count("</body>") != 1:
        raise SystemExit(f"{page}: expected exactly one </body>")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    block = f"{START}\n{BLOCK.replace('__DATA__', payload)}\n{END}\n"
    page.write_text(html.replace("</body>", block + "</body>"), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--gpkg", required=True, type=Path, help=f"the agency network (layer `{LAYER}`)")
    parser.add_argument("--dir", type=Path, default=None, help="folder of the two comparison pages (default: the folder of --gpkg)")
    args = parser.parse_args()

    points = read_points(args.gpkg)
    folder = args.dir or args.gpkg.parent
    labels = {"line": "line differences", "hub": "hub differences"}
    for kind, name in PAGES.items():
        chosen = [p for p in points if p["kind"] == kind]
        inject(folder / name, {"source": args.gpkg.name, "layer": LAYER, "kind_label": labels[kind], "points": chosen})
        print(f"{name}: {len(chosen)} {kind} point(s)")
    other = [p for p in points if p["kind"] not in PAGES]
    if other:
        print(f"not drawn: {len(other)} point(s) of another kind: {sorted({p['kind'] for p in other})}")


if __name__ == "__main__":
    main()
