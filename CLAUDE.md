# CLAUDE.md: Middle East Airspace Watch

## What this is
A public static website that draws **one line per civil flight** crossing the Middle East
(Egypt → Pakistan, Yemen → Caucasus), start to finish, over the last ~90 days. It refreshes
daily. Goal: see which airspace airlines avoid and how routes shift after regional events
(Houthi launches from Yemen, Iran/Israel strikes, airspace closures). The project began as
"flights to/from Doha", so the DOH filter matters.

- Live site: https://jeanturban.github.io/middle-east-airspace-watch/
- Owner: Jean-Alexandre (new to GitHub: explain git/GitHub steps in plain words and do them yourself where possible).
- Demo preview (synthetic data): https://claude.ai/artifact/LesXPA9iqtxpYQQms5V12Q
- A local copy also exists on his Mac: ~/Documents/Claude Projects/middle-east-airspace-watch (older first version).

## Data source
adsb.lol `globe_history` (https://github.com/adsblol/globe_history_2026): ODbL 1.0, free, one
GitHub release per day with the previous day's traces of every aircraft, ~3.6 GB as a split tar
(`.tar.aa` + `.tar.ab`). `PREFERRED_RELEASES.txt` in that repo lists the download URLs per day.
Trace format: https://github.com/wiedehopf/readsb/blob/dev/README-json.md#trace-jsons
(points `[dt, lat, lon, alt|"ground", gs, track, flags, ...]`; `flags & 2` = new leg; `dbFlags & 1` = military).

**Caveat to keep in the UI:** coverage relies on volunteer receivers and is thin over Iran, Iraq
and the Saudi interior. An empty area can mean "avoided" or "unobserved". Compare periods.

## Layout
```
pipeline/grid.py          analysis box 25–65°E, 10–42°N, 0.1° grid (400×320)
pipeline/process_day.py   stdin tar stream → out/days/<date>.json (density) + out/lines/<date>.s0-3.bin (paths)
pipeline/airports.py      airport list for origin/dest tagging. APPEND-ONLY (indices are stored in data)
pipeline/update.py        `plan` (missing days as JSON for the Actions matrix) / `manifest` (+ prunes line files >180 days)
pipeline/build_basemap.py Natural Earth 1:50m → data/basemap.json (whole world, simplified)
pipeline/make_demo_data.py synthetic data, manifest demo=true (banner in UI). Never commit its output
site/index.html           the whole viewer: one file, no build step, no external libs
data/                     committed by the workflow: manifest.json, days/*.json, lines/*.bin, basemap.json, events.json
.github/workflows/update.yml  daily 09:17 UTC + manual dispatch (input `days`, default 90)
```

## Pipeline details
- A leg is kept if any airborne point is inside the box. Its **entire** path is stored (worldwide),
  Douglas-Peucker simplified at 0.03°, coords as int16 lat*100/lon*100.
- Gaps > 20 min or > 300 km between reports → gap flag 1 (drawn faint). |Δlon| > 180 → flag 2 (not drawn).
- Origin/dest = airport within 40 km of the leg's first/last point if below 10,000 ft.
- Each day is shuffled into 4 shards so the viewer can load a random sample for long ranges.
- Density grid: each leg adds +1 to every 0.1° cell it crosses (≥1,000 ft), once per leg.
- Binary shard layout is documented in the `process_day.py` docstring and parsed by `parseShard()` in the viewer. Change both together.
- Real numbers (Oct 28 2026): ~79k traces/day, ~3,700 aircraft / ~8,100 legs in box, ~128k path points,
  ~650 KB of line files/day. Processing ≈ 2–3 min/day on a GitHub runner.

## Workflow
`plan` → `process` (matrix, one job per day, max-parallel 8, streams `curl aa ab | process_day.py`)
→ `publish` (copies artifacts into data/, `update.py manifest`, `git pull --rebase`, push, deploy to Pages).
A day counts as done when both `data/days/<d>.json` and `data/lines/<d>.s0.bin` exist.
GitHub Pages source = "GitHub Actions" (already set).

## Viewer (site/index.html)
- Three stacked canvases: `#base` (2D: water, land, borders, heatmap), `#gl` (WebGL2 line strips,
  additive blending, primitive restart, `flat` varying for gap flag), `#top` (labels, airports, events, analysis box).
- Equirectangular projection with cos(28°) x-scaling; zoom 0.2–16 (zoom out to world).
- Modes: Flight paths (default) / Heatmap / Compare periods (baseline vs recent, red = fewer flights).
- Controls: range presets, drag-select on daily-totals timeline, airport filter, brightness, ▶ Play weekly.
- `MAX_LINES = 150000`: above it, fewer shards per day are loaded (random sample, stated in the UI).
- `manifest.bundle` (optional) lets a host that can't serve .bin (the claude.ai artifact preview) use one base64 JSON.
- Colors from a validated palette: sequential blue, diverging red/blue with gray midpoint, dark surface #1a1a19.

## Testing
- Pipeline: build a tiny tar of `traces/xx/trace_full_<hex>.json` (gzip JSON), `split` it, pipe through `process_day.py`.
- Viewer: `python3 pipeline/make_demo_data.py --days 14` into a scratch copy (NOT the repo's data/),
  serve with `python3 -m http.server`, screenshot with Playwright/Chrome (`--use-angle=swiftshader --enable-unsafe-swiftshader` for WebGL2).

## Status (2026-11-08)
- First real backfill with flight lines running: workflow run 42457890600 (89 days, ~50 min).
  An earlier cancelled run committed density-only files for ~18 days; they are reprocessed automatically.
- data/events.json is empty.

## Next steps (agreed or proposed)
1. Verify the backfill and live site (all days have shards, lines render, DOH filter works).
2. Aesthetics pass on real data: the user wants to tweak the look. Ask what they like; tune line alpha/color.
3. Research and add key events from the last ~3 months to data/events.json (date, lat, lon, type, title,
   source URL). Sourced facts only; stay neutral.
4. Ideas: hover a line → callsign/route (needs callsign in shards), filter by airline, altitude band filter, mobile layout.

## Conventions
- Commit as the user; end commit messages with the Co-Authored-By line Claude Code adds.
- Don't commit synthetic demo data or the raw tar downloads (.gitignore covers `downloads/`, `*.tar.*`).
- Keep the site dependency-free (single HTML file) unless there's a strong reason.
