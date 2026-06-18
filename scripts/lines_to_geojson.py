#!/usr/bin/env python3
"""Build one polyline (GeoJSON LineString) per ``LINE_ID`` from a nodes CSV.

The input CSV has one row per node with columns ``node, LINE_ID, X, Y`` (plus a
``geometry`` WKT POINT and a leading index column). Coordinates are in Israel
TM Grid (ITM, EPSG:2039). This script:

  1. groups the points by ``LINE_ID``;
  2. orders each group's points into a connected open polyline (the CSV is
     sorted by node id, *not* path order, so we order geometrically);
  3. reprojects ITM -> WGS84 lon/lat to match the dashboard's GeoJSON layers;
  4. optionally joins a "planned mode" CSV (columns ``Line_ModelName,
     Mode_Planned, Line_Name, Line_Description, Area``) so every feature carries
     a ``Mode`` (and ``Line_Name`` / ``Area``) property you can filter on;
  5. writes a single FeatureCollection with one LineString per ``LINE_ID``.

Usage:
    python3 scripts/lines_to_geojson.py INPUT.csv [--modes MODES.csv] \\
        [--out layers/lines.geojson]
"""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer

# Israel TM Grid (EPSG:2039) -> WGS84 lon/lat (EPSG:4326).
_TF = Transformer.from_crs("EPSG:2039", "EPSG:4326", always_xy=True)

# A handful of LINE_IDs in the nodes file don't match the planned-mode file
# verbatim: BluRT1/2 are a spelling of BlueRT1/2, and LRT9 / LRT10 appear there
# only as their per-direction variants (LRT91/LRT92, LRT101/LRT102). All four
# resolve to a single, unambiguous mode, so we alias them explicitly.
_LINE_ID_ALIASES = {
    "BluRT1": "BlueRT1",
    "BluRT2": "BlueRT2",
    "LRT9": "LRT91",
    "LRT10": "LRT101",
}


def load_modes(path):
    """Map LINE_ID -> {Mode, Line_Name, Area} from the planned-mode CSV.

    The file is Windows-1255 (Hebrew), so we decode it as cp1255 to keep the
    Hebrew ``Line_Name`` readable (Mode/Area are ASCII either way).
    """
    info = {}
    with open(path, encoding="cp1255", newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header: Line_ModelName,Mode_Planned,Line_Name,...,Area
        for row in reader:
            if len(row) < 2 or not row[0]:
                continue
            info[row[0]] = {
                "Mode": row[1].strip(),
                "Line_Name": row[2] if len(row) > 2 else "",
                "Area": row[4] if len(row) > 4 else "",
            }
    return info


def mode_for(line_id, modes):
    """Look up a line's mode info, falling back to the alias table."""
    if line_id in modes:
        return modes[line_id]
    alias = _LINE_ID_ALIASES.get(line_id)
    if alias and alias in modes:
        return modes[alias]
    return None


def order_points(pts):
    """Order points into a connected open polyline via nearest-neighbour.

    Transit corridors are essentially linear, so we find a true endpoint first
    (run NN from an arbitrary point; the far end it reaches is an endpoint),
    then run NN again from that endpoint to get a clean, non-zig-zag path.
    """
    if len(pts) <= 2:
        return pts

    def nn_path(start_idx, points):
        remaining = points[:]
        path = [remaining.pop(start_idx)]
        while remaining:
            lx, ly = path[-1]
            j = min(range(len(remaining)),
                    key=lambda k: (remaining[k][0] - lx) ** 2 + (remaining[k][1] - ly) ** 2)
            path.append(remaining.pop(j))
        return path

    endpoint = nn_path(0, pts)[-1]            # a real end of the corridor
    start = pts.index(endpoint)
    return nn_path(start, pts)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="input nodes/lines CSV")
    ap.add_argument("--modes", help="planned-mode CSV to join (Line_ModelName,Mode_Planned,...)")
    ap.add_argument("--out", default="layers/lines.geojson", help="output GeoJSON path")
    ap.add_argument("--name", default="lines", help="FeatureCollection name")
    args = ap.parse_args()

    modes = load_modes(args.modes) if args.modes else {}

    groups = defaultdict(list)
    # The file is Windows-1255 (Hebrew) encoded; latin-1 reads the numeric
    # columns we need without choking on the garbled index header.
    with open(args.csv, encoding="latin-1", newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            if len(row) < 5 or not row[2]:
                continue
            line_id = row[2]
            try:
                x, y = float(row[3]), float(row[4])
            except ValueError:
                continue
            groups[line_id].append((x, y))

    features = []
    unmatched = []
    for line_id in sorted(groups):
        # de-duplicate identical coordinates while preserving first-seen order
        seen = set()
        uniq = []
        for p in groups[line_id]:
            if p not in seen:
                seen.add(p)
                uniq.append(p)

        if len(uniq) < 2:
            # a single distinct point can't form a polyline; skip it
            continue

        ordered = order_points(uniq)
        coords = [[round(lon, 6), round(lat, 6)]
                  for lon, lat in (_TF.transform(x, y) for x, y in ordered)]

        length_m = sum(
            math.dist(ordered[i], ordered[i + 1]) for i in range(len(ordered) - 1)
        )
        props = {
            "LINE_ID": line_id,
            "num_points": len(ordered),
            "length_m": round(length_m, 1),
        }
        if modes:
            info = mode_for(line_id, modes)
            if info is None:
                unmatched.append(line_id)
                props["Mode"] = "Unknown"
            else:
                props["Mode"] = info["Mode"]
                props["Line_Name"] = info["Line_Name"]
                props["Area"] = info["Area"]
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    fc = {"type": "FeatureCollection", "name": args.name, "features": features}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(features)} polylines to {out}")
    if modes and unmatched:
        print(f"WARNING: {len(unmatched)} line(s) had no mode match: "
              f"{', '.join(sorted(unmatched))}")


if __name__ == "__main__":
    main()
