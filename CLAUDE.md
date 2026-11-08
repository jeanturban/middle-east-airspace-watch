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
pipeline/fetch.sh         download a day's split tar to disk, resuming + size-checking each part
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
- Gaps > 5 min or > 100 km between reports → gap flag 1 (hidden by default, "Show gaps" draws them thin/grey).
  |Δlon| > 180 → flag 2 (never drawn). Positions are never estimated by adsb.lol (ADS-B/MLAT/TIS-B only);
  straight stretches come from these joins. Measured Nov 5: in-box distance was 56% reports <1 min apart,
  15% 2–20 min joins, 29% >20 min joins.
- `PIPELINE_VERSION` (grid.py) is written into each day JSON as "v"; `plan` reprocesses days with an older v.
  Bump it whenever process_day.py output changes meaning.
- tar is read with `ignore_zeros=True` (the 2026-09-01 release has a damaged block; that day has ~5.9k legs).
- Origin/dest = airport within 40 km of the leg's first/last point if below 10,000 ft.
- Each day is shuffled into 4 shards so the viewer can load a random sample for long ranges.
- Density grid: each leg adds +1 to every 0.1° cell it crosses (≥1,000 ft, observed segments only), once per leg.
- Binary shard layout is documented in the `process_day.py` docstring and parsed by `parseShard()` in the viewer. Change both together.
- Real numbers (Oct 28 2026): ~79k traces/day, ~3,700 aircraft / ~8,100 legs in box, ~128k path points,
  ~650 KB of line files/day. Processing ≈ 2–3 min/day on a GitHub runner.

## Workflow
`plan` → `process` (matrix, one job per day, max-parallel 5)
(`fetch.sh` to disk, then `cat | process_day.py`; never stream curl straight in: a dropped
connection plus ignore_zeros silently saved partial days on Nov 8) → `publish` (copies artifacts into data/, `update.py manifest`, `git pull --rebase`, push, deploy to Pages).
A day counts as done when both `data/days/<d>.json` and `data/lines/<d>.s0.bin` exist.
GitHub Pages source = "GitHub Actions" (already set).

## Viewer (site/index.html)
- Three stacked canvases: `#base` (2D: water, land, borders, heatmap), `#gl` (WebGL2 lines), `#top`
  (labels, airports, events, analysis box).
- Lines, pass 1: line strips (primitive restart, `flat` gap varying) are counted per CSS pixel into an
  RGBA16F texture (R = observed, G = gaps). Pass 2 (full-screen): each pixel looks R_MAX px around and draws a
  solid line whose half-width = w·(0.45 + 0.3·log2(1 + flights/day)), colour dark→light blue with density,
  dimmed to 45% outside the analysis box. "Line width" slider scales w. Without EXT_color_buffer_float it falls
  back to premultiplied additive blending (no width encoding). Never go back to plain alpha blending at tiny
  alpha: the 8-bit canvas alpha rounds to 0 and the layer vanishes (that bug hid all lines until Nov 8).
- Equirectangular projection with cos(28°) x-scaling; zoom 0.2–16 (zoom out to world).
- Modes: Flight paths (default) / Heatmap / Compare periods (baseline vs recent, red = fewer flights).
- Controls: range presets, drag-select on daily-totals timeline, airport filter, line width, show gaps, ▶ Play weekly.
- `MAX_LINES = 150000`: above it, fewer shards per day are loaded (random sample, stated in the UI).
- `manifest.bundle` (optional) lets a host that can't serve .bin (the claude.ai artifact preview) use one base64 JSON.
- Colors from a validated palette: sequential blue, diverging red/blue with gray midpoint, dark surface #1a1a19.

## Testing
- Pipeline: build a tiny tar of `traces/xx/trace_full_<hex>.json` (gzip JSON), `split` it, pipe through `process_day.py`.
- Viewer: `python3 pipeline/make_demo_data.py --days 14` into a scratch copy (NOT the repo's data/),
  serve with `python3 -m http.server`, screenshot with Playwright/Chrome (`--use-angle=swiftshader --enable-unsafe-swiftshader` for WebGL2).

## Status (2026-11-08)
- Backfill done (Aug 10 – Nov 6). Run 42457890600 + a re-run for 2026-09-01.
- Fixed: lines invisible at high counts (8-bit alpha), damaged-tar early exit.
- Look agreed with the user: firm lines, thickness = density, less blown-out, gaps hidden by default.
- All 89 days (Aug 10 – Nov 6) are pipeline v2 with 4 shards (verified after run 42470754478).
  Legs/day median ~8,650; low but complete days: Sep 1 (5,927, damaged tar) and Aug 13 (6,931, full 74k traces).
  The 09:17 UTC schedule did not fire on Nov 8; trigger update.yml manually if a day is missing.
- data/events.json is empty.

## Next steps (agreed or proposed)
1. Verify the backfill and live site (all days have shards, lines render, DOH filter works).
2. Aesthetics: first pass done (see Status). Check with the user after they've seen v2 data live.
3. Research and add key events from the last ~3 months to data/events.json (date, lat, lon, type, title,
   source URL). Sourced facts only; stay neutral.
4. Ideas: hover a line → callsign/route (needs callsign in shards), filter by airline, altitude band filter, mobile layout.

## Conventions
- Commit as the user; end commit messages with the Co-Authored-By line Claude Code adds.
- Don't commit synthetic demo data or the raw tar downloads (.gitignore covers `downloads/`, `*.tar.*`).
- Keep the site dependency-free (single HTML file) unless there's a strong reason.
