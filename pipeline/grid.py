"""Shared grid definition. Keep in sync with GRID in site/index.html (it is also
written into data/manifest.json, which the viewer reads)."""

LON_MIN, LON_MAX = 25.0, 65.0   # Egypt/Turkey in the west -> Pakistan border in the east
LAT_MIN, LAT_MAX = 10.0, 42.0   # Yemen/Horn of Africa -> Caucasus/Caspian
# Bump when process_day.py output changes meaning: `update.py plan` then reprocesses every day
# whose data/days/<date>.json carries an older "v". 2 = gaps over 5 min / 100 km between reports.
PIPELINE_VERSION = 2

RES = 0.1                       # degrees per cell (~11 km)

W = round((LON_MAX - LON_MIN) / RES)   # 400 columns
H = round((LAT_MAX - LAT_MIN) / RES)   # 320 rows


def cell(lat, lon):
    """Return (col, row) for a position; row 0 is the northern edge."""
    col = int((lon - LON_MIN) / RES)
    row = int((LAT_MAX - lat) / RES)
    return col, row


def in_box(lat, lon, pad=0.0):
    return (LAT_MIN - pad) <= lat <= (LAT_MAX + pad) and (LON_MIN - pad) <= lon <= (LON_MAX + pad)


def spec():
    return {"lon_min": LON_MIN, "lon_max": LON_MAX, "lat_min": LAT_MIN,
            "lat_max": LAT_MAX, "res": RES, "w": W, "h": H}
