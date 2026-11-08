#!/usr/bin/env python3
"""Turn one day of adsb.lol globe_history into (1) full flight paths and (2) a density grid.

Reads the day's tar archive as a STREAM on stdin (nothing is extracted to disk):

    curl -sL URL.tar.aa URL.tar.ab | python pipeline/process_day.py 2026-11-06 out

For every aircraft trace inside the tar (traces/xx/trace_full_<hex>.json, gzip JSON,
format: https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons):
  * skip aircraft flagged military in the adsb.lol database (dbFlags & 1)
  * split the trace into flight legs (flag bit 2 = new leg), airborne points only
  * keep legs that pass through the Middle East box (pipeline/grid.py)

Outputs
  out/days/<date>.json        density grid: each leg adds +1 to every 0.1° cell it crosses
                              {"date", "legs", "aircraft", "points", "cells": [d0,c0,d1,c1,...]}
  out/lines/<date>.s<k>.bin   the FULL path of every such leg, worldwide, start to finish,
                              split into SHARDS random shards so the viewer can load a sample.
                              Binary layout (little-endian), each block padded to 4 bytes:
                                uint32 version(=1), nLegs, nPts, reserved
                                uint16 legLen[nLegs]       points per leg
                                uint8  orig[nLegs], dest[nLegs]   index+1 into airports.py (0 = unknown)
                                int16  pts[nPts*2]         lat*100, lon*100 pairs
                                uint8  gap[nPts]           segment ENDING at this point:
                                                           0 = observed, 1 = coverage gap (no reports;
                                                           drawn faint), 2 = do not draw (hard break)
"""
import gzip
import json
import math
import os
import random
import struct
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(__file__))
from grid import W, H, cell, in_box  # noqa: E402
from airports import AIRPORTS  # noqa: E402

try:
    import orjson
    loads = orjson.loads
except ImportError:  # works without it, just slower
    loads = json.loads

MAX_GAP_S = 20 * 60     # positions further apart than this (or MAX_GAP_KM) are a coverage gap
MAX_GAP_KM = 300
MIN_ALT_FT = 1000       # density grid ignores very low points
SIMPLIFY_DEG = 0.03     # path simplification tolerance (~3 km)
SHARDS = 4
AIRPORT_KM = 40         # leg start/end within this distance (and low) -> tagged with that airport
AIRPORT_ALT_FT = 10000


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


def split_legs(trace):
    """Yield legs as lists of airborne (t, lat, lon, alt) points."""
    leg = []
    for p in trace:
        flags = p[6] if len(p) > 6 and isinstance(p[6], int) else 0
        if flags & 2 and leg:
            yield leg
            leg = []
        lat, lon, alt = p[1], p[2], p[3]
        if lat is None or lon is None or not isinstance(alt, (int, float)):
            continue  # on the ground or no position
        leg.append((p[0], lat, lon, alt))
    if leg:
        yield leg


def leg_cells(leg):
    """Grid cells crossed by a leg inside the box (density layer)."""
    cells, prev = set(), None
    for t, lat, lon, alt in leg:
        if alt < MIN_ALT_FT or not in_box(lat, lon, pad=1.0):
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
    return cells


def dp_keep(pts, tol):
    """Douglas-Peucker on (lat, lon): return indices to keep (iterative)."""
    n = len(pts)
    if n < 3:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        (y1, x1), (y2, x2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            y, x = pts[i]
            d = (abs(dy * x - dx * y + x2 * y1 - y2 * x1) / norm) if norm > 1e-9 else math.hypot(x - x1, y - y1)
            if d > best:
                best, idx = d, i
        if best > tol and idx > 0:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [i for i in range(n) if keep[i]]


def leg_path(leg):
    """Simplified full path: list of (lat, lon, gapflag). Runs between gaps are simplified separately."""
    runs, run = [], [0]
    for i in range(1, len(leg)):
        t0, la0, lo0, _ = leg[i - 1]
        t1, la1, lo1, _ = leg[i]
        if abs(lo1 - lo0) > 180:
            flag = 2
        elif t1 - t0 > MAX_GAP_S or km(la0, lo0, la1, lo1) > MAX_GAP_KM:
            flag = 1
        else:
            run.append(i)
            continue
        runs.append((run, flag))
        run = [i]
    runs.append((run, None))
    out, pending = [], 0
    for run, next_flag in runs:
        pts = [(leg[i][1], leg[i][2]) for i in run]
        for j, k in enumerate(dp_keep(pts, SIMPLIFY_DEG)):
            out.append((pts[k][0], pts[k][1], pending if j == 0 else 0))
        pending = next_flag or 0
    return out


def airport_at(t_lat, t_lon, alt):
    if alt > AIRPORT_ALT_FT:
        return 0
    best, code = AIRPORT_KM, 0
    for i, (_, la, lo) in enumerate(AIRPORTS):
        if abs(la - t_lat) < 1 and abs(lo - t_lon) < 1.2:
            d = km(t_lat, t_lon, la, lo)
            if d < best:
                best, code = d, i + 1
    return code


def pack_shard(legs):
    """legs: list of (orig, dest, path). Returns bytes in the layout described in the docstring."""
    pad = lambda b: b + b"\0" * (-len(b) % 4)  # noqa: E731
    n_pts = sum(len(p) for _, _, p in legs)
    lens = [len(p) for _, _, p in legs]
    coords, gaps = [], bytearray()
    for _, _, path in legs:
        for lat, lon, g in path:
            coords += [round(lat * 100), round(lon * 100)]
            gaps.append(g)
    return (struct.pack("<4I", 1, len(legs), n_pts, 0)
            + pad(struct.pack(f"<{len(lens)}H", *lens))
            + pad(bytes(o for o, _, _ in legs) + bytes(d for _, d, _ in legs))
            + pad(struct.pack(f"<{len(coords)}h", *coords))
            + pad(bytes(gaps)))


def process(stream, date, outdir):
    grid = [0] * (W * H)
    lines = []
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
            hit = False
            for leg in split_legs(data.get("trace") or []):
                if not any(in_box(la, lo) for _, la, lo, _ in leg):
                    continue
                hit = True
                n_legs += 1
                n_points += len(leg)
                for i in leg_cells(leg):
                    grid[i] += 1
                path = leg_path(leg)
                if len(path) >= 2:
                    lines.append((airport_at(*leg[0][1:4]), airport_at(*leg[-1][1:4]), path))
            if hit:
                n_aircraft += 1
            if n_files % 20000 == 0:
                print(f"  {n_files} traces read, {n_aircraft} aircraft in box, "
                      f"{time.time() - t0:.0f}s", file=sys.stderr)
    if n_files == 0:
        sys.exit("no trace files found in the archive")

    # density grid
    out, last = [], 0
    for i, v in enumerate(grid):
        if v:
            out += [i - last, v]
            last = i
    os.makedirs(os.path.join(outdir, "days"), exist_ok=True)
    with open(os.path.join(outdir, "days", f"{date}.json"), "w") as fh:
        json.dump({"date": date, "legs": n_legs, "aircraft": n_aircraft, "points": n_points,
                   "traces_read": n_files, "cells": out}, fh, separators=(",", ":"))

    # full paths, randomly sharded
    os.makedirs(os.path.join(outdir, "lines"), exist_ok=True)
    random.Random(date).shuffle(lines)
    size = 0
    for k in range(SHARDS):
        b = pack_shard(lines[k::SHARDS])
        size += len(b)
        with open(os.path.join(outdir, "lines", f"{date}.s{k}.bin"), "wb") as fh:
            fh.write(b)
    kept = sum(len(p) for _, _, p in lines)
    print(f"{date}: {n_files} traces, {n_aircraft} aircraft / {n_legs} legs in box, "
          f"{len(out) // 2} cells, {len(lines)} paths / {kept} pts ({size // 1024} KB) "
          f"({time.time() - t0:.0f}s)", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    process(sys.stdin.buffer, sys.argv[1], sys.argv[2])
