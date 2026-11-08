# Middle East Airspace Watch

Static website showing where civil flights go over the Middle East, and how that
changes over time. Updated daily from adsb.lol's open data (ODbL 1.0), with a 90-day backfill.

## How it works

```
adsb.lol globe_history (GitHub releases, ~3.6 GB/day, previous day)
   │  streamed, never extracted to disk
   ▼
pipeline/process_day.py  → data/days/YYYY-MM-DD.json   (flights per 0.1° cell, sparse)
pipeline/update.py       → data/manifest.json          (day list + daily totals)
   ▼
site/index.html          (static page: density map, compare mode, weekly playback, events)
```

* **Box:** 25–65°E, 10–42°N (Egypt → Pakistan border, Yemen → Caucasus). Change it in `pipeline/grid.py`.
* **Counting:** each flight leg adds 1 to every cell it crosses, once. Airborne points ≥1,000 ft only,
  military aircraft (adsb.lol `dbFlags & 1`) excluded. Gaps between position reports are bridged with a
  straight line only if ≤20 min and ≤300 km, so coverage holes are not filled with invented lines.
* **Compare mode:** relative change per cell between a baseline and a recent window, normalised per day.

## Run it

GitHub Actions (`.github/workflows/update.yml`) runs daily at 09:17 UTC:
`plan` finds days not yet processed (last 90 days) → `process` streams each day in parallel
(8 at a time) → `publish` commits the new files and deploys to GitHub Pages.

One-time setup on GitHub:
1. Settings → Pages → Source: **GitHub Actions**.
2. Settings → Actions → General → Workflow permissions: **Read and write**.
3. Actions → "Daily flight data update" → **Run workflow** to start the 90-day backfill.

Locally, for one day:
```
curl -sL <url>.tar.aa <url>.tar.ab | python3 pipeline/process_day.py 2026-11-06 data/days
python3 pipeline/update.py manifest
cd site && ln -s ../data data && python3 -m http.server
```
`pipeline/make_demo_data.py` writes **synthetic** data (flagged `demo: true`, banner in the UI) for previewing.

## Events

`data/events.json` holds dated events drawn on the map and timeline:
```json
{"events": [{"date": "2026-10-01", "lat": 15.3, "lon": 44.2, "type": "missile",
             "title": "Short description", "source": "https://..."}]}
```

## Caveats

* adsb.lol relies on volunteer receivers. Coverage is thin over parts of Iran, Iraq and the Saudi interior,
  so an empty area may simply be unobserved. Compare periods rather than reading absolute emptiness.
* A receiver going offline shows up as a drop in traffic. Check the daily totals bar before drawing conclusions.

Basemap: Natural Earth 1:50m (public domain).
