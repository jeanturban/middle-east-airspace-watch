#!/usr/bin/env python3
"""Generate SYNTHETIC demo data in the real data format, for previewing the viewer
before the pipeline has run. Flights are invented straight-ish routes between hubs;
halfway through, a made-up circular "avoid zone" appears and routes bend around it.
manifest.json is marked demo=true and the viewer shows a banner. Not real traffic.

  python pipeline/make_demo_data.py [--end 2026-11-06] [--days 90]
"""
import argparse
import datetime as dt
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(__file__))
from grid import W, H, cell, spec  # noqa: E402
from process_day import raster_segment  # noqa: E402

PTS = {  # (lat, lon); names starting with _ are off-map gateways
    "DOH": (25.27, 51.61), "DXB": (25.25, 55.36), "AUH": (24.43, 54.65), "RUH": (24.96, 46.70),
    "JED": (21.68, 39.16), "KWI": (29.24, 47.97), "BAH": (26.27, 50.63), "MCT": (23.59, 58.28),
    "IST": (41.26, 28.74), "CAI": (30.12, 31.41), "AMM": (31.72, 35.99), "BGW": (33.26, 44.23),
    "IKA": (35.42, 51.15), "KHI": (24.90, 67.17), "TLV": (32.01, 34.89), "DMM": (26.47, 49.80),
    "_EU": (43.5, 22.0), "_EU2": (43.5, 33.0), "_IN": (21.0, 67.0), "_AF": (8.5, 39.0),
    "_CA": (43.0, 61.0), "_AS": (31.0, 67.0),
}
ROUTES = [("DOH", "_EU", 30), ("DXB", "_EU", 40), ("AUH", "_EU", 20), ("DOH", "_EU2", 15),
          ("DXB", "_EU2", 15), ("DOH", "_IN", 25), ("DXB", "_IN", 35), ("DOH", "_AF", 10),
          ("DXB", "_AF", 12), ("DOH", "_AS", 12), ("DXB", "_CA", 8), ("DOH", "RUH", 10),
          ("DOH", "JED", 8), ("DXB", "RUH", 12), ("DXB", "JED", 12), ("RUH", "JED", 25),
          ("RUH", "CAI", 10), ("JED", "CAI", 12), ("DXB", "KWI", 8), ("DOH", "KWI", 6),
          ("DXB", "BAH", 8), ("DXB", "MCT", 10), ("DXB", "IKA", 10), ("DOH", "IKA", 4),
          ("DXB", "IST", 15), ("DOH", "IST", 8), ("RUH", "IST", 6), ("AMM", "DXB", 6),
          ("DXB", "CAI", 10), ("DOH", "CAI", 6), ("BGW", "DXB", 5), ("BGW", "IST", 4),
          ("DOH", "AMM", 4), ("KHI", "DXB", 10), ("DMM", "DXB", 5), ("TLV", "DXB", 6),
          ("IKA", "IST", 8), ("MCT", "_EU", 6), ("BAH", "_EU", 6), ("KWI", "_EU", 8)]
ZONE = (33.0, 44.5, 4.5)   # lat, lon, radius in degrees: the invented avoid zone
OFFSETS = [-0.4, -0.25, -0.12, 0, 0.12, 0.25, 0.4]


def path(a, b, off, avoid):
    (la1, lo1), (la2, lo2) = PTS[a], PTS[b]
    dx, dy = lo2 - lo1, la2 - la1
    n = math.hypot(dx, dy)
    px, py = -dy / n, dx / n  # unit perpendicular
    pts = []
    for i in range(41):
        t = i / 40
        bow = math.sin(math.pi * t) * (off + 0.04 * n)  # slight arc + per-flight offset
        pts.append([la1 + dy * t + py * bow, lo1 + dx * t + px * bow])
    if avoid:
        zl, zo, r = ZONE
        for p in pts:
            d = math.hypot(p[0] - zl, p[1] - zo)
            if d < r + 0.6:  # push the point out to the zone edge
                k = (r + 0.6 + abs(off)) / max(d, 1e-6)
                p[0], p[1] = zl + (p[0] - zl) * k, zo + (p[1] - zo) * k
    return pts


def cells_for(pts):
    out, prev = set(), None
    for lat, lon in pts:
        c, r = cell(lat, lon)
        if prev:
            raster_segment(prev[0], prev[1], c, r, out)
        prev = (c, r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end", default="2026-11-06")
    ap.add_argument("--days", type=int, default=90)
    a = ap.parse_args()
    random.seed(7)
    variants = {(ra, rb, o, av): cells_for(path(ra, rb, o, av))
                for ra, rb, _ in ROUTES for o in OFFSETS for av in (False, True)}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ddir = os.path.join(root, "data", "days")
    os.makedirs(ddir, exist_ok=True)
    end = dt.date.fromisoformat(a.end)
    days = []
    for k in range(a.days - 1, -1, -1):
        day = end - dt.timedelta(k)
        idx = a.days - 1 - k
        avoid_share = 0 if idx < 45 else min(1.0, (idx - 45) / 4 + 0.1)  # zone appears on day 46
        grid = [0] * (W * H)
        legs = 0
        weekly = 1 + 0.08 * math.sin(day.weekday())
        for ra, rb, per_day in ROUTES:
            n = int(random.gauss(per_day * 2 * weekly, per_day * 0.2))  # both directions
            if avoid_share and ra in ("BGW",) or rb in ("BGW",):
                n = int(n * (0.25 if avoid_share else 1))
            for _ in range(max(n, 0)):
                av = random.random() < avoid_share
                for i in variants[(ra, rb, random.choice(OFFSETS), av)]:
                    grid[i] += 1
                legs += 1
        out, last = [], 0
        for i, v in enumerate(grid):
            if v:
                out += [i - last, v]
                last = i
        with open(os.path.join(ddir, f"{day}.json"), "w") as fh:
            json.dump({"date": str(day), "legs": legs, "aircraft": legs, "cells": out}, fh,
                      separators=(",", ":"))
        days.append({"date": str(day), "legs": legs, "aircraft": legs})
    m = {"generated": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
         "source": "SYNTHETIC DEMO DATA - not real flights", "demo": True,
         "grid": spec(), "days": days}
    with open(os.path.join(root, "data", "manifest.json"), "w") as fh:
        json.dump(m, fh, indent=1)
    print(f"wrote {len(days)} demo days")


if __name__ == "__main__":
    main()
