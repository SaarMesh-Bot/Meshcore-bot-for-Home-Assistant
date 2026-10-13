"""Data for the dashboard's Repeater page (templates/repeater.html, GET /api/repeater).

Everything comes from the tables the HARepeater service fills (see service_plugins/ha_repeater_service.py):
repeater_telemetry (one row per status reply of a repeater, read from meshcore-ha) and ha_repeater_neighbors. This
module only reads. Units as stored: battery in mV, temperature in °C, noise floor / RSSI in dBm, SNR in dB, airtime
utilisation in %, uptime in seconds.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional

PERIODS = {"1": 1, "7": 7, "30": 30}
MAX_POINTS = 600   # per chart; longer periods are thinned out evenly (the newest point is always kept)
SERIES = ("battery_mv", "battery_pct", "temperature", "noise_floor", "airtime_util", "last_rssi", "last_snr", "neighbor_count", "uptime_s")


def _table_exists(conn: Any, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def contact_info(conn: Any, prefixes: list) -> dict:
    """{prefix: {name, place, lat, lon}} from the bot's own contact list (complete_contact_tracking), by key prefix; the
    most recently heard node wins when several keys start with the same prefix. Columns the table lacks are left empty."""
    out: dict = {}
    if not prefixes or not _table_exists(conn, "complete_contact_tracking"):
        return out
    cols = {r[1] for r in conn.execute("PRAGMA table_info(complete_contact_tracking)").fetchall()}
    want = [c for c in ("name", "city", "state", "country", "latitude", "longitude") if c in cols]
    order = "last_heard DESC" if "last_heard" in cols else "rowid DESC"
    for prefix in {str(p).lower() for p in prefixes if p and len(str(p)) >= 4}:
        row = conn.execute(f"SELECT {', '.join(want)} FROM complete_contact_tracking WHERE lower(public_key) LIKE ? "
                           f"ORDER BY {order} LIMIT 1", (prefix + "%",)).fetchone()
        if not row:
            continue
        d = dict(zip(want, row))
        place = next((d.get(k) for k in ("city", "state", "country") if d.get(k)), "") or ""
        lat, lon = d.get("latitude"), d.get("longitude")
        has_pos = lat not in (None, 0, 0.0) and lon not in (None, 0, 0.0)
        out[prefix] = {"name": d.get("name") or "", "place": place, "lat": lat if has_pos else None, "lon": lon if has_pos else None}
    return out


def contact_names(conn: Any, prefixes: list) -> dict:
    """{prefix: name} for neighbours meshcore-ha gives no name (see contact_info)."""
    return {p: i["name"] for p, i in contact_info(conn, prefixes).items() if i["name"]}


def km_between(a: tuple, b: tuple) -> Optional[float]:
    """Great-circle distance in km between two (lat, lon), or None when one is unknown."""
    if None in a or None in b:
        return None
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * 6371.0 * math.asin(math.sqrt(h)), 1)


def _thin(rows: list, limit: int = MAX_POINTS) -> list:
    if len(rows) <= limit:
        return rows
    step = len(rows) / float(limit)
    picked = [rows[int(i * step)] for i in range(limit - 1)]
    return picked + [rows[-1]]


def summary(db: Any, key: Optional[str] = None, days: str = "7", now_ts: Optional[float] = None,
            allowed: Optional[set] = None) -> dict:
    """{repeaters: [...], selected, days, latest, series: {...}, neighbors: [...]} for one repeater (default: the one
    heard from last). allowed: the repeater keys a dashboard viewer may see (None = all)."""
    now_ts = time.time() if now_ts is None else now_ts
    span = PERIODS.get(str(days), 7)
    out: dict = {"generated_at": int(now_ts), "days": span, "repeaters": [], "selected": None, "latest": None,
                 "series": {"t": [], **{k: [] for k in SERIES}}, "neighbors": [], "neighbors_at": None}
    with db.connection() as conn:
        if not _table_exists(conn, "repeater_telemetry"):
            return out
        reps = conn.execute(
            """SELECT t.repeater_key, t.repeater_name, t.recorded_at, c.n FROM repeater_telemetry t
               JOIN (SELECT repeater_key, MAX(id) AS last_id, COUNT(*) AS n FROM repeater_telemetry GROUP BY repeater_key) c
                 ON t.id = c.last_id
               ORDER BY t.recorded_at DESC""").fetchall()
        if allowed is not None:
            ok = {a.lower() for a in allowed}
            reps = [r for r in reps if str(r[0]).lower() in ok or any(str(r[0]).lower().startswith(a) for a in ok)]
        out["repeaters"] = [{"key": k, "name": n or k[:10], "last_ts": int(ts), "readings": int(c)} for k, n, ts, c in reps]
        if not reps:
            return out
        keys = {r["key"] for r in out["repeaters"]}
        selected = key if key in keys else out["repeaters"][0]["key"]
        out["selected"] = selected
        cols = ", ".join(SERIES)
        rows = conn.execute(f"SELECT recorded_at, {cols} FROM repeater_telemetry WHERE repeater_key = ? AND recorded_at >= ? ORDER BY recorded_at",
                            (selected, int(now_ts - span * 86400))).fetchall()
        last = conn.execute(f"SELECT recorded_at, repeater_name, {cols} FROM repeater_telemetry WHERE repeater_key = ? ORDER BY id DESC LIMIT 1",
                            (selected,)).fetchone()
        out["latest"] = {"ts": int(last[0]), "name": last[1], **dict(zip(SERIES, last[2:]))}
        for row in _thin(rows):
            out["series"]["t"].append(int(row[0]))
            for name, value in zip(SERIES, row[1:]):
                out["series"][name].append(value)
        # (2.46) other telemetry channels (ch2_current, ch2_voltage, ...): latest values and a series per channel
        cols_t = {r[1] for r in conn.execute("PRAGMA table_info(repeater_telemetry)")}
        out["telemetry"], out["telemetry_series"], out["telemetry_units"] = {}, {}, {}
        if "telemetry" in cols_t:
            trows = conn.execute("SELECT recorded_at, telemetry FROM repeater_telemetry WHERE repeater_key = ? AND recorded_at >= ? "
                                 "AND telemetry IS NOT NULL ORDER BY recorded_at", (selected, int(now_ts - span * 86400))).fetchall()
            lastt = conn.execute("SELECT telemetry FROM repeater_telemetry WHERE repeater_key = ? AND telemetry IS NOT NULL "
                                 "ORDER BY id DESC LIMIT 1", (selected,)).fetchone()
            if lastt:
                try:
                    data = json.loads(lastt[0])
                    out["telemetry"] = data.get("values") or {}
                    out["telemetry_units"] = data.get("units") or {}
                except ValueError:
                    pass
            series: dict = {}
            for ts, raw in _thin(trows):
                try:
                    values = (json.loads(raw) or {}).get("values") or {}
                except ValueError:
                    continue
                for name, value in values.items():
                    series.setdefault(name, {"t": [], "v": []})
                    series[name]["t"].append(int(ts))
                    series[name]["v"].append(value)
            out["telemetry_series"] = series
        if _table_exists(conn, "ha_repeater_neighbors"):
            at = conn.execute("SELECT MAX(recorded_at) FROM ha_repeater_neighbors WHERE repeater_key = ?", (selected,)).fetchone()[0]
            if at:
                out["neighbors_at"] = int(at)
                rows_nb = conn.execute(
                    """SELECT neighbor_prefix, neighbor_name, snr, secs_ago FROM ha_repeater_neighbors
                       WHERE repeater_key = ? AND recorded_at = ? ORDER BY snr DESC""", (selected, at)).fetchall()
                info = contact_info(conn, [p for p, _n, _s, _a in rows_nb] + [selected])
                try:   # names the AnalyzerFeed looked up at the EU Meshcore Analyzer (modules/analyzer_names.py)
                    from .analyzer_names import names_for
                    looked = names_for(conn, [p for p, n, _s, _a in rows_nb if not n])
                except Exception:  # noqa: BLE001
                    looked = {}
                home = info.get(selected.lower(), {})
                here = (home.get("lat"), home.get("lon"))
                out["neighbors"] = []
                for p, n, s, a in rows_nb:
                    c = info.get(str(p).lower(), {})
                    an = "" if (n or c.get("name")) else looked.get(str(p).lower(), "")
                    out["neighbors"].append({
                        "prefix": p, "name": n or c.get("name", "") or an, "from_contacts": not n and bool(c.get("name")),
                        "from_analyzer": bool(an),
                        "place": c.get("place", ""), "km": km_between(here, (c.get("lat"), c.get("lon"))),
                        "snr": s, "secs_ago": a})
    return out
