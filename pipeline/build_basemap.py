#!/usr/bin/env python3
"""One-off: cut Natural Earth 1:50m country borders down to the map area.

  python pipeline/build_basemap.py ne_50m_admin_0_countries.geojson ne_50m_lakes.geojson
writes data/basemap.json  ({"countries": [{"name", "label": [lon, lat], "rings": [[[lon, lat], ...]]}], "lakes": [...]})
Natural Earth is public domain.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from grid import LON_MIN, LON_MAX, LAT_MIN, LAT_MAX  # noqa: E402

PAD = 400.0  # whole world: flight paths run far outside the analysis box
TOL = 0.06  # simplification tolerance in degrees


def dp(pts, tol):
    """Douglas-Peucker line simplification."""
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = (dx * dx + dy * dy) ** 0.5 or 1e-12
    best, idx = 0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]
        d = abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm
        if d > best:
            best, idx = d, i
    if best <= tol:
        return [pts[0], pts[-1]]
    return dp(pts[: idx + 1], tol)[:-1] + dp(pts[idx:], tol)


def rings_of(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        for ring in poly[:1]:  # outer rings only
            yield ring


def near(ring):
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return not (max(xs) < LON_MIN - PAD or min(xs) > LON_MAX + PAD or
                max(ys) < LAT_MIN - PAD or min(ys) > LAT_MAX + PAD)


def cut(path, with_names):
    out = []
    for f in json.load(open(path))["features"]:
        rings = []
        for ring in rings_of(f["geometry"]):
            if not near(ring):
                continue
            # closed ring: split at the point farthest from the start, simplify both halves
            x0, y0 = ring[0]
            k = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
            s = dp(ring[: k + 1], TOL)[:-1] + dp(ring[k:], TOL)
            if len(s) >= 4 and (len(s) >= 6 or max(abs(a[0]-b[0]) + abs(a[1]-b[1]) for a in s for b in s[:1]) > 0.3):
                rings.append([[round(x, 2), round(y, 2)] for x, y in s])
        if rings:
            p = f["properties"]
            item = {"rings": rings}
            if with_names:
                item["name"] = p.get("NAME_EN") or p.get("NAME")
                item["label"] = [round(p.get("LABEL_X", 0), 2), round(p.get("LABEL_Y", 0), 2)]
                item["rank"] = p.get("LABELRANK", 5)
            out.append(item)
    return out


if __name__ == "__main__":
    countries = cut(sys.argv[1], True)
    lakes = cut(sys.argv[2], False) if len(sys.argv) > 2 else []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "data", "basemap.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"countries": countries, "lakes": lakes}, fh, separators=(",", ":"))
    print(f"{len(countries)} countries, {len(lakes)} lakes -> {path} ({os.path.getsize(path)//1024} KB)")
