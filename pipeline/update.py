#!/usr/bin/env python3
"""Planning + manifest helper for the daily GitHub Actions run.

  python pipeline/update.py plan [--days 90] [--max 90]
      Print a JSON list of days that are published by adsb.lol but not yet in
      data/days/, newest first: [{"date": "2026-11-06", "urls": [".aa", ".ab"]}, ...]

  python pipeline/update.py manifest
      Rebuild data/manifest.json (list of available days + daily totals + grid spec).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from grid import spec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAYS_DIR = os.path.join(ROOT, "data", "days")
RELEASES = "https://raw.githubusercontent.com/adsblol/globe_history_{year}/main/PREFERRED_RELEASES.txt"
TAG = re.compile(r"/v(\d{4})\.(\d{2})\.(\d{2})-planes-readsb-")


def published(years):
    """date -> list of split-tar URLs, from adsb.lol's PREFERRED_RELEASES.txt."""
    out = {}
    for year in sorted(years):
        try:
            with urllib.request.urlopen(RELEASES.format(year=year), timeout=60) as r:
                text = r.read().decode()
        except Exception as e:  # e.g. next year's repo not created yet
            print(f"warning: could not read releases for {year}: {e}", file=sys.stderr)
            continue
        for line in text.splitlines():
            urls = [u.strip() for u in line.split(",") if u.strip()]
            m = TAG.search(urls[0]) if urls else None
            if m and "mlatonly" not in urls[0]:
                out.setdefault("-".join(m.groups()), urls)
    return out


def plan(days, max_n):
    today = dt.date.today()
    window = {str(today - dt.timedelta(d)) for d in range(1, days + 1)}
    have = {f[:-5] for f in os.listdir(DAYS_DIR)} if os.path.isdir(DAYS_DIR) else set()
    avail = published({int(d[:4]) for d in window})
    todo = sorted((d for d in window if d in avail and d not in have), reverse=True)[:max_n]
    print(json.dumps([{"date": d, "urls": avail[d]} for d in todo]))


def manifest():
    days = []
    for f in sorted(os.listdir(DAYS_DIR)):
        if f.endswith(".json"):
            with open(os.path.join(DAYS_DIR, f)) as fh:
                d = json.load(fh)
            days.append({"date": d["date"], "legs": d["legs"], "aircraft": d["aircraft"]})
    m = {"generated": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
         "source": "adsb.lol globe_history (ODbL 1.0)", "demo": False,
         "grid": spec(), "days": days}
    with open(os.path.join(ROOT, "data", "manifest.json"), "w") as fh:
        json.dump(m, fh, indent=1)
    print(f"manifest: {len(days)} days", file=sys.stderr)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["plan", "manifest"])
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--max", type=int, default=90)
    a = ap.parse_args()
    plan(a.days, a.max) if a.cmd == "plan" else manifest()
