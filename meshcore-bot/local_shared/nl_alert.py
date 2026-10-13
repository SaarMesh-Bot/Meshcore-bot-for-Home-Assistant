"""NL-Alert on the mesh: the government's public warnings (cell broadcast) and the monthly siren test, posted in a channel.

Source: the public NL-Alert feed (api.public-warning.app, the endpoint the NL-Alert app uses). Each alert has an id, the
text (Dutch, often followed by "*** Dutch Public Warning System." and the English text), start/stop time and the area
as one or more polygons ("lat,lon lat,lon ..."). The NLAlert service (card NLAlert) polls it and posts new alerts for
the chosen provinces (looked up once per alert from the middle of its area, via OpenStreetMap) and/or within a radius
of the bot. Only the Dutch part is posted, split over at most MAX_PARTS messages of MAX_BYTES. A re-send of the same
text within REPEAT_WINDOW_S (the authorities often extend an alert with a new id) is not posted again. Alerts that were
already in the feed when the service started are never posted (no flood of old warnings after a restart).

Siren test (WAS): every first Monday of the month at 12:00, not on a public holiday (New Year, Easter Monday, King's Day,
4 and 5 May, Whit Monday), until the sirens stop on 2028-01-01. In June and December NL-Alert sends its own test message
at the same time; the post says so.

Nothing here talks to the network or the radio; the service does.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

FEED_URL = "https://api.public-warning.app/api/v1/providers/nl-alert/alerts"
MAX_BYTES = 130
MAX_PARTS = 3
REPEAT_WINDOW_S = 12 * 3600
FRESH_S = 3 * 3600          # an alert that started longer ago than this is not posted any more
SIREN_END = date(2028, 1, 1)


# ---------------------------------------------------------------- feed
def _ts(value: Any) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _polygon(text: Any) -> list:
    pts = []
    for pair in str(text or "").split():
        try:
            lat, lon = pair.split(",")
            pts.append((float(lat), float(lon)))
        except ValueError:
            continue
    return pts


def parse_feed(data: Any) -> list:
    """[{id, text, start, stop, areas: [[(lat, lon), ...], ...]}] from the feed's JSON, newest first as given."""
    items = data.get("data", []) if isinstance(data, dict) else (data or [])
    out = []
    for it in items:
        if not isinstance(it, dict) or not it.get("id") or not it.get("message"):
            continue
        areas = it.get("area") or []
        if isinstance(areas, str):
            areas = [areas]
        out.append({"id": str(it["id"]), "text": dutch_text(it["message"]), "start": _ts(it.get("start_at")),
                    "stop": _ts(it.get("stop_at")), "areas": [p for p in (_polygon(a) for a in areas) if p]})
    return out


def dutch_text(message: str) -> str:
    """The Dutch part: everything before '***' (the English version follows it), whitespace tidied."""
    return " ".join(str(message).split("***")[0].split())


# ---------------------------------------------------------------- where
def centre(points: list) -> tuple:
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def km(a: tuple, b: tuple) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def near(alert: dict, here: Optional[tuple], radius_km: float) -> bool:
    """Any point of the area (or its middle) within radius_km of the bot."""
    if not here or radius_km <= 0:
        return False
    for poly in alert["areas"]:
        if km(centre(poly), here) <= radius_km or any(km(p, here) <= radius_km for p in poly[::4]):
            return True
    return False


def wanted(alert: dict, provinces: list, radius_km: float, here: Optional[tuple], province_of: Callable) -> bool:
    """Whether to post this alert. No provinces and no radius = the whole country.
    province_of((lat, lon)) -> province name or None (looked up by the caller, may be cached)."""
    if not alert["areas"]:
        return not provinces and radius_km <= 0
    if not provinces and radius_km <= 0:
        return True
    if near(alert, here, radius_km):
        return True
    if provinces:
        want = {p.strip().lower() for p in provinces if p.strip()}
        for poly in alert["areas"]:
            name = province_of(centre(poly))
            if name and name.strip().lower() in want:
                return True
    return False


# ---------------------------------------------------------------- what to post
def text_key(text: str) -> str:
    return hashlib.sha1(text.lower().encode("utf-8")).hexdigest()[:16]


def split(text: str, prefix: str, limit: int = MAX_BYTES, parts: int = MAX_PARTS) -> list:
    """The text in at most `parts` messages of at most `limit` bytes, each starting with prefix (and n/m when split)."""
    def fits(s: str) -> bool:
        return len(s.encode("utf-8")) <= limit

    whole = f"{prefix}: {text}"
    if fits(whole):
        return [whole]
    for total in range(2, parts + 1):
        words, out, cur = text.split(), [], ""
        for w in words:
            head = f"{prefix} {len(out) + 1}/{total}: "
            cand = (cur + " " + w) if cur else w
            if fits(head + cand):
                cur = cand
            else:
                out.append(head + cur)
                cur = w
        out.append(f"{prefix} {len(out) + 1}/{total}: " + cur)
        if len(out) <= total and all(fits(o) for o in out):
            return out
    # still too long: the first parts, the last one cut with an ellipsis
    out = split(text, prefix, limit, parts + 20)[:parts]
    last = out[-1]
    while not fits(last + "…"):
        last = last[:-1]
    out[-1] = last.rstrip() + "…"
    return [re.sub(r" \d+/\d+:", f" {i + 1}/{parts}:", o, count=1) for i, o in enumerate(out)]


def new_alerts(alerts: list, seen: set, sent: dict, now: float, first_run: bool) -> list:
    """Alerts to consider posting: not seen before, not expired, recent, and not the same text as one posted recently.
    On the first run everything is only remembered (returns [])."""
    if first_run:
        return []
    out = []
    for a in alerts:
        if a["id"] in seen:
            continue
        if a["stop"] and a["stop"] < now:
            continue
        if a["start"] and now - a["start"] > FRESH_S:
            continue
        if now - sent.get(text_key(a["text"]), 0) < REPEAT_WINDOW_S:
            continue
        out.append(a)
    return list(reversed(out))     # oldest first


# ---------------------------------------------------------------- siren test
def easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def holidays(year: int) -> set:
    e = easter(year)
    kings = date(year, 4, 27) if date(year, 4, 27).weekday() != 6 else date(year, 4, 26)
    return {date(year, 1, 1), e + timedelta(days=1), kings, date(year, 5, 4), date(year, 5, 5), e + timedelta(days=50)}


def siren_test_day(d: date) -> bool:
    """First Monday of the month, not a holiday, before the sirens stop."""
    return d < SIREN_END and d.weekday() == 0 and d.day <= 7 and d not in holidays(d.year)


def siren_due(local: datetime, posted_month: str) -> Optional[str]:
    """'with_test' (June/December: NL-Alert test message too), 'plain', or None. Due from 12:00 to 12:15 local time,
    once per month."""
    if not siren_test_day(local.date()) or posted_month == local.strftime("%Y-%m"):
        return None
    if not (12 * 60 <= local.hour * 60 + local.minute < 12 * 60 + 15):
        return None
    return "with_test" if local.month in (6, 12) else "plain"
