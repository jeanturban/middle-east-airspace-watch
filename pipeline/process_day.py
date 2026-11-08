#!/usr/bin/env python3
"""Turn one day of adsb.lol globe_history into a flight-density grid.

Reads the day's tar archive as a STREAM on stdin (nothing is extracted to disk):

    curl -sL URL.tar.aa URL.tar.ab | python pipeline/process_day.py 2026-11-06 data/days

For every aircraft trace inside the tar (traces/xx/trace_full_<hex>.json, gzip JSON,
format: https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons):
  * skip aircraft flagged military in the adsb.lol database (dbFlags & 1)
  * split the trace into flight legs (flag bit 2 = new leg)
  * keep airborne points inside the Middle East box
  * draw straight segments between consecutive points, but only across short
    gaps (<= MAX_GAP_S and <= MAX_GAP_KM) so coverage holes are not bridged with
    invented lines
  * each leg adds +1 to every grid cell it touches (once per leg)

Output: <outdir>/<date>.json
  {"date", "legs", "aircraft", "points", "cells": [d0, c0, d1, c1, ...]}
  where cells is sparse, delta-encoded: cell index = running sum of d, value = c.
"""
import gzip
import json
import math
import os
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(__file__))
from grid import W, H, RES, cell, in_box  # noqa: E402

try:
    import orjson
    loads = orjson.loads
except ImportError:  # works without it, just slower
    loads = json.loads

MAX_GAP_S = 20 * 60     # bridge position gaps up to 20 minutes...
MAX_GAP_KM = 300        # ...and up to 300 km
MIN_ALT_FT = 1000       # ignore ground/taxi and very low points


def km(lat1, lon1, lat2, lon2):
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371 * math.hypot(x, y)


def raster_segment(c0, r0, c1, r1, out):
    """Add all cells on the line between two cells (Bresenham) to the set `out`."""
    dc, dr = abs(c1 - c0), -abs(r1 - r0)
    sc, sr = (1 if c0 < c1 else -1), (1 if r0 < r1 else -1)
    err = dc + dr
    while True:
        if 0 <= c0 < W and 0 <= r0 < H:
            out.add(r0 * W + c0)
        if c0 == c1 and r0 == r1:
            return
        e2 = 2 * err
        if e2 >= dr:
            err += dr
            c0 += sc
        if e2 <= dc:
            err += dc
            r0 += sr


def legs_cells(trace):
    """Yield one set of grid cells per flight leg."""
    cells, prev = set(), None
    for p in trace:
        t, lat, lon, alt = p[0], p[1], p[2], p[3]
        flags = p[6] if len(p) > 6 and isinstance(p[6], int) else 0
        if flags & 2 and cells:          # new leg starts here
            yield cells
            cells, prev = set(), None
        airborne = isinstance(alt, (int, float)) and alt >= MIN_ALT_FT
        if lat is None or lon is None or not airborne or not in_box(lat, lon, pad=1.0):
            prev = None
            continue
        c, r = cell(lat, lon)
        if prev is not None:
            pt, plat, plon, pc, pr = prev
            if t - pt <= MAX_GAP_S and km(plat, plon, lat, lon) <= MAX_GAP_KM:
                raster_segment(pc, pr, c, r, cells)
        if 0 <= c < W and 0 <= r < H:
            cells.add(r * W + c)
        prev = (t, lat, lon, c, r)
    if cells:
        yield cells


def process(stream, date, outdir):
    grid = [0] * (W * H)
    n_legs = n_aircraft = n_points = n_files = 0
    t0 = time.time()
    with tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            name = member.name
            if not member.isfile() or "/traces/" not in "/" + name or "trace_full_" not in name:
                continue
            n_files += 1
            f = tar.extractfile(member)
            if f is None:
                continue
            raw = f.read()
            try:
                data = loads(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
            except Exception:
                continue
            if (data.get("dbFlags") or 0) & 1:      # military
                continue
            trace = data.get("trace") or []
            hit = False
            for cells in legs_cells(trace):
                hit = True
                n_legs += 1
                for i in cells:
                    grid[i] += 1
            if hit:
                n_aircraft += 1
                n_points += len(trace)
            if n_files % 20000 == 0:
                print(f"  {n_files} traces read, {n_aircraft} aircraft in box, "
                      f"{time.time() - t0:.0f}s", file=sys.stderr)

    out, last = [], 0
    for i, v in enumerate(grid):
        if v:
            out += [i - last, v]
            last = i
    os.makedirs(outdir, exist_ok=True)
    result = {"date": date, "legs": n_legs, "aircraft": n_aircraft,
              "points": n_points, "traces_read": n_files, "cells": out}
    path = os.path.join(outdir, f"{date}.json")
    with open(path, "w") as fh:
        json.dump(result, fh, separators=(",", ":"))
    print(f"{date}: {n_files} traces, {n_aircraft} aircraft / {n_legs} legs in box, "
          f"{len(out) // 2} cells -> {path} ({time.time() - t0:.0f}s)", file=sys.stderr)
    if n_files == 0:
        sys.exit("no trace files found in the archive")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    process(sys.stdin.buffer, sys.argv[1], sys.argv[2])
