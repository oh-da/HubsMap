#!/usr/bin/env python3
"""Build one polyline (GeoJSON LineString) per ``LINE_ID`` from a nodes CSV.

The input CSV has one row per node with columns ``node, LINE_ID, X, Y`` (plus a
``geometry`` WKT POINT and a leading index column). Coordinates are in Israel
TM Grid (ITM, EPSG:2039). This script:

  1. groups the points by ``LINE_ID``;
  2. orders each group's points into a connected open polyline (the CSV is
     sorted by node id, *not* path order, so we order geometrically);
  3. reprojects ITM -> WGS84 lon/lat to match the dashboard's GeoJSON layers;
  4. writes a single FeatureCollection with one LineString per ``LINE_ID``.

Usage:
    python3 scripts/lines_to_geojson.py INPUT.csv [--out layers/lines.geojson]
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
    ap.add_argument("--out", default="layers/lines.geojson", help="output GeoJSON path")
    ap.add_argument("--name", default="lines", help="FeatureCollection name")
    args = ap.parse_args()

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
        features.append({
            "type": "Feature",
            "properties": {
                "LINE_ID": line_id,
                "num_points": len(ordered),
                "length_m": round(length_m, 1),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    fc = {"type": "FeatureCollection", "name": args.name, "features": features}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(features)} polylines to {out}")


if __name__ == "__main__":
    main()
