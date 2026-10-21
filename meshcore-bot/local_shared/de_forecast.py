"""Short hourly forecast for the mesh ('vorhersage'), ported from the SaarMesh bot's /vorhersage and moved from
OpenWeather (needs a key) to Open-Meteo (no key).

  vorhersage                 the next 6 hours where the sender is (their advert position), else the bot's location
  vorhersage 12              the next 12 hours (1..48)
  vorhersage 66117           a postcode (Saarland postcodes are named, others are shown as the number)
  vorhersage Trier 12        a place and hours, in any order; the last 1-2 digit number is the hours

At most MAX_LINES lines: longer spans are shown in steps (12 h -> every 2 h, 24 h -> every 3 h). One line per step:
'HH:MM <emoji> <temp>°' plus the precipitation of that hour when there is any; the emoji carries the condition, so
no words (airtime).

Nothing here talks to the network or the radio (see de_fetch.open_meteo_hourly).
"""
from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Optional

OPEN_METEO = ("https://api.open-meteo.com/v1/forecast?latitude={lat:.4f}&longitude={lon:.4f}"
              "&hourly=temperature_2m,weather_code,precipitation&forecast_hours={hours}&timezone={tz}")
DEFAULT_HOURS = 6
MAX_HOURS = 48
MAX_LINES = 8

_PLZ = re.compile(r"^\d{5}$")

WMO_EMOJI = {
    0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️", 45: "🌫️", 48: "🌫️",
    51: "🌦️", 53: "🌦️", 55: "🌧️", 56: "🌧️", 57: "🌧️",
    61: "🌧️", 63: "🌧️", 65: "🌧️", 66: "🌧️", 67: "🌧️",
    71: "🌨️", 73: "🌨️", 75: "❄️", 77: "❄️", 80: "🌦️", 81: "🌧️", 82: "🌧️",
    85: "🌨️", 86: "❄️", 95: "⛈️", 96: "⛈️", 99: "⛈️",
}
SNOW = {71, 73, 75, 77, 85, 86}


def parse_args(text: str) -> tuple:
    """(hours, place or None) from the words after the keyword. The last token of 1-2 digits is the hours (clamped
    to 1..MAX_HOURS), everything else is the place; a 5-digit postcode is a place, not hours."""
    toks = (text or "").split()
    hours = DEFAULT_HOURS
    idx = None
    for i, t in enumerate(toks):
        t2 = t.lower().rstrip("h")
        if t2.isdigit() and len(t2) <= 2:
            idx = i
    if idx is not None:
        hours = max(1, min(MAX_HOURS, int(toks[idx].lower().rstrip("h"))))
        toks = toks[:idx] + toks[idx + 1:]
    place = " ".join(toks).strip(" ,") or None
    return hours, place


def is_plz(place: Optional[str]) -> bool:
    return bool(place and _PLZ.match(place.strip()))


def plz_name(plz: str) -> Optional[str]:
    try:
        from .local_data.plz_saarland import PLZ
    except ImportError:  # pragma: no cover - flat layout in tests
        from local_data.plz_saarland import PLZ  # type: ignore
    names = PLZ.get((plz or "").strip())
    return names[0] if names else None


def url(lat: float, lon: float, hours: int, tz: str = "Europe/Berlin") -> str:
    return OPEN_METEO.format(lat=lat, lon=lon, hours=max(1, min(MAX_HOURS, hours)) + 1, tz=tz or "auto")


def step_for(hours: int) -> int:
    return max(1, math.ceil(hours / MAX_LINES))


def rows(data: Any, hours: int, now: datetime) -> list:
    """[(datetime, code, temp, precip)] from an Open-Meteo hourly answer: from the current hour on, every
    step_for(hours) hours, at most MAX_LINES. Precipitation of a shown hour is summed with the hidden hours up to the
    next shown one, so a shower between two lines is not lost."""
    h = (data or {}).get("hourly") if isinstance(data, dict) else None
    if not isinstance(h, dict):
        return []
    times, temps = h.get("time") or [], h.get("temperature_2m") or []
    codes, precs = h.get("weather_code") or [], h.get("precipitation") or []
    hour0 = now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    pts = []
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(str(t))
        except ValueError:
            continue
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        if dt < hour0:
            continue
        pts.append((dt, _at(codes, i), _at(temps, i), _at(precs, i) or 0.0))
    pts = pts[:hours + 1]
    step = step_for(hours)
    out = []
    for k in range(0, len(pts), step):
        dt, code, temp, _ = pts[k]
        rain = sum((p[3] or 0.0) for p in pts[k:k + step])
        out.append((dt, code, temp, rain))
        if len(out) >= MAX_LINES:
            break
    return out


def _at(xs: list, i: int):
    try:
        v = xs[i]
    except (IndexError, TypeError):
        return None
    return v


def line(dt: datetime, code: Any, temp: Any, rain: float) -> str:
    try:
        c = int(code)
    except (TypeError, ValueError):
        c = -1
    emo = WMO_EMOJI.get(c, "🌡️")
    t = f"{int(round(float(temp)))}°" if isinstance(temp, (int, float)) else "?°"
    p = ""
    if rain and rain >= 0.1:
        p = f" {'❄' if c in SNOW else ''}{rain:.1f}mm".replace(".", ",")
    return f"{dt.strftime('%H:%M')} {emo} {t}{p}"
