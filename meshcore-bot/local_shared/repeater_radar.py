"""Repeater radar (dashboard: Radar -> Repeater radar): every repeater the bot heard in the last 24 hours, 7 or 30 days,
from its own tables - nothing is sent.

Per repeater: name, key prefix, place and distance to the bot, last heard, SNR and hops of the last advert, adverts in
the period, whether the bot's radio hears it directly (zero-hop neighbour, from neighbour discovery), how many bots of
the bot network hear it directly, and how many other repeaters in the list start with the same key byte (a path of
1-byte hops cannot tell those apart).

The bot's own position: [Bot] bot_latitude/bot_longitude, else the position the radio advertises (stored by the
AutoChannels service in bot_metadata "radio.position").
"""
from __future__ import annotations

import calendar
import json
import math
import time
from typing import Any, Optional

PERIODS = {"1": 1, "7": 7, "30": 30}
MAX_ROWS = 600
NEAR_KM = 50      # a shared prefix only counts between repeaters that can both be in the bot's paths
NEAR_HOPS = 2     # (both within NEAR_KM of the bot, or, without a position, both heard within NEAR_HOPS hops)


def _table_exists(conn: Any, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def km_between(a: tuple, b: tuple) -> Optional[float]:
    if None in a or None in b:
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def bot_position(config: Any, db: Any) -> Optional[tuple]:
    try:
        lat = config.getfloat("Bot", "bot_latitude", fallback=None)
        lon = config.getfloat("Bot", "bot_longitude", fallback=None)
        if lat is not None and lon is not None:
            return (lat, lon)
    except Exception:  # noqa: BLE001
        pass
    try:
        raw = db.get_metadata("radio.position")
        if raw:
            pos = json.loads(raw)
            if pos.get("lat") and pos.get("lon"):
                return (float(pos["lat"]), float(pos["lon"]))
    except Exception:  # noqa: BLE001
        pass
    return None


def _good(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f == 0.0 else f


def summary(db: Any, config: Any, days: str = "1", now: Optional[float] = None) -> dict:
    now = time.time() if now is None else now
    d = PERIODS.get(str(days), 1)
    out: dict = {"generated_at": int(now), "days": d, "repeaters": [], "totals": {}, "has_position": False}
    here = bot_position(config, db)
    out["has_position"] = here is not None
    with db.connection() as conn:
        if not _table_exists(conn, "complete_contact_tracking"):
            return out
        rows = conn.execute(
            "SELECT public_key, name, latitude, longitude, city, last_heard, snr, hop_count, first_heard, "
            "CAST(strftime('%s', last_heard) AS INTEGER) FROM complete_contact_tracking "
            "WHERE LOWER(role) = 'repeater' AND last_heard >= datetime('now', ?) ORDER BY last_heard DESC LIMIT ?",
            (f"-{d} day", MAX_ROWS)).fetchall()
        adverts: dict = {}
        if _table_exists(conn, "daily_stats"):
            for key, n in conn.execute("SELECT public_key, SUM(advert_count) FROM daily_stats WHERE date >= date('now', ?) "
                                       "GROUP BY public_key", (f"-{d - 1} day",)):
                adverts[key] = n
        direct: dict = {}
        if _table_exists(conn, "neighbor_links"):
            for key, last_snr, best, seen, count in conn.execute(
                    "SELECT neighbor_public_key, last_snr, best_snr, CAST(strftime('%s', last_seen) AS INTEGER), observation_count "
                    "FROM neighbor_links WHERE last_seen >= datetime('now', '-7 day')"):
                direct[str(key).lower()[:12]] = {"snr": last_snr, "best": best, "seen": seen, "count": count}
        heard_by: dict = {}
        if _table_exists(conn, "botnet_links"):
            for nb, bot_name, snr in conn.execute(
                    "SELECT neighbor, from_name, snr FROM botnet_links "
                    "WHERE COALESCE((SELECT via FROM botnet_peers WHERE name = from_name), '') != 'self'"):
                heard_by.setdefault(str(nb).lower(), []).append({"bot": bot_name, "snr": snr})
    week_ago = now - 7 * 86400
    for key, name, lat, lon, city, _last, snr, hops, first, last_ts in rows:
        k = str(key).lower()
        pos = (_good(lat), _good(lon))
        dist = km_between(here, pos) if here and None not in pos else None
        nb = direct.get(k[:12])
        try:
            first_ts = calendar.timegm(time.strptime(str(first)[:19], "%Y-%m-%d %H:%M:%S")) if first else None   # stored in UTC
        except ValueError:
            first_ts = None
        out["repeaters"].append({
            "name": name or "?", "key": k[:12], "prefix": k[:2], "place": city or "",
            "lat": pos[0], "lon": pos[1], "km": round(dist, 1) if dist is not None else None,
            "last_heard": last_ts, "snr": snr, "hops": hops, "adverts": adverts.get(key, 0),
            "direct": nb is not None, "direct_snr": (nb or {}).get("snr"), "direct_best": (nb or {}).get("best"),
            "direct_seen": (nb or {}).get("seen"), "direct_count": (nb or {}).get("count"),
            "bots": len(heard_by.get(k[:12], [])), "bot_list": heard_by.get(k[:12], []),
            "first_heard": int(first_ts) if first_ts else None,
            "new": bool(first_ts and first_ts >= week_ago),
        })
    reps = out["repeaters"]

    # Same prefix: a path of 1-byte hops (d5,b0,...) cannot tell two repeaters with the same first key byte apart, but
    # that only matters when both could be in the bot's paths. With ~300 repeaters heard and 256 possible bytes almost
    # every repeater shares its byte with one somewhere far away (2026-09-30: 187 of 287), which says nothing.
    def near(r):
        if r["km"] is not None:
            return r["km"] <= NEAR_KM
        return r["hops"] is not None and r["hops"] <= NEAR_HOPS
    near_by_byte: dict = {}
    for r in reps:
        if near(r):
            near_by_byte.setdefault(r["prefix"], []).append(r["key"])
    for r in reps:
        group = near_by_byte.get(r["prefix"], [])
        r["near"] = near(r)
        r["same_prefix"] = (len(group) - 1) if r["near"] and r["key"] in group else 0
    # smaller answers (the dashboard may be used over RDP or a slow link): rounded numbers, no empty fields
    for r in reps:
        for f in ("lat", "lon"):
            if r[f] is not None:
                r[f] = round(r[f], 4)
        for f in [f for f, v in r.items() if v in (None, "", [], False, 0) and f not in ("name", "key", "prefix", "direct", "near", "km", "last_heard")]:
            del r[f]
    out["totals"] = {
        "heard": len(reps),
        "direct": sum(1 for r in reps if r["direct"]),
        "new": sum(1 for r in reps if r.get("new")),
        "shared_prefix": sum(1 for r in reps if r.get("same_prefix", 0) > 0),
        "near_km": NEAR_KM,
        # only neighbour discovery says reliably that the radio hears a repeater directly (hop_count 0 in the contact
        # table can come from the contact list, not from the advert itself: seen 2026-09-30, 104 km "0 hops")
        "farthest_km": max((r["km"] for r in reps if r["km"] is not None and r["direct"]), default=None),
    }
    return out
