"""Water levels (Pegel) in Germany for the mesh: PEGELONLINE (federal waterways, WSV) and the Saarland's
Hochwassermeldedienst (HMD) for the smaller rivers. Ported from the SaarMesh bot (saarmesh.de).

Stations are set on the Pegel card as ``alias=source:id:label`` separated by ';', e.g.
``saar=po:26400220:Saar (Sankt Arnual); nied=hmd:W1102220:Nied (Niedaltdorf)``. Sources:
- ``po``  PEGELONLINE, id = the station number (https://www.pegelonline.wsv.de/gast/start). Current value from the
  station's W time series; the 3-hour trend is the median of the last values against the first (raw 15-minute values
  of the Saar jump by a few cm, a plain first/last difference would show a trend that is not there).
- ``hmd`` Saarland HMD text series (iframe01.saarland.de/extern/wasser/daten/{id}.txt: a title line, then
  ``date;time;value`` hourly for a week), id like W1102220. -9999 (no value yet) and other impossible values are
  skipped. Every known host is read and the newest series wins.

The Pegel alarm (PegelAlarm card) compares one station against thresholds ``cm:label`` (default: the Saar at Sankt
Arnual with the official Hochwassermeldehöhen and the A620 mark) and reports only a rise to a higher stage, and an
all-clear once the level is HYSTERESIS_CM below the lowest threshold.

Nothing here talks to the network or the radio.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Optional

PO_STATION = ("https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/{number}.json"
              "?includeTimeseries=true&includeCurrentMeasurement=true")
PO_HISTORY = "https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/{number}/W/measurements.json?start=PT{hours}H"

DEFAULT_STATIONS = ("saar=po:26400220:Saar (Sankt Arnual); blies=hmd:W1013120:Blies (Alsfassen); "
                    "nied=hmd:W1102220:Nied (Niedaltdorf)")
DEFAULT_THRESHOLDS = ("280:Meldehöhe 1, 320:Warnstufe 1, 350:Meldehöhe 2, 380:A620-Sperrung wahrscheinlich, "
                      "400:Meldehöhe 3, 750:Meldehöhe 4")
HYSTERESIS_CM = 10


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", (s or "").strip().lower())


def parse_stations(text: str) -> dict:
    """{alias: {source, id, label}} from 'alias=source:id:label; ...'. Bad entries are skipped."""
    out = {}
    for part in (text or "").replace("\n", ";").split(";"):
        if "=" not in part:
            continue
        alias, _, rest = part.partition("=")
        bits = [b.strip() for b in rest.split(":", 2)]
        if len(bits) < 2 or not norm(alias):
            continue
        source = bits[0].lower()
        source = {"pegelonline": "po", "saarland_hmd": "hmd"}.get(source, source)
        if source not in ("po", "hmd") or not bits[1]:
            continue
        out[norm(alias)] = {"source": source, "id": bits[1], "label": bits[2] if len(bits) > 2 and bits[2] else alias.strip()}
    return out


def parse_thresholds(text: str) -> list:
    """[(cm, label)] ascending from '280:Meldehöhe 1, 320:...'."""
    out = []
    for part in (text or "").split(","):
        cm, _, label = part.partition(":")
        try:
            out.append((int(float(cm.strip())), label.strip() or f"{cm.strip()} cm"))
        except ValueError:
            continue
    return sorted(out)


def stage(value_cm: float, thresholds: list) -> int:
    """0 = below all, n = the n-th threshold (1-based) reached."""
    return sum(1 for cm, _ in thresholds if value_cm >= cm)


# ---------------------------------------------------------------- PEGELONLINE
def po_current(station: Any, tz: tzinfo) -> Optional[dict]:
    """{value_cm, time, name} from a station answer (includeTimeseries + includeCurrentMeasurement); only the W
    (water level) series counts, never Q (discharge)."""
    if not isinstance(station, dict):
        return None
    for ts in station.get("timeseries") or []:
        if not isinstance(ts, dict) or (ts.get("shortname") or "").strip().upper() != "W":
            continue
        cur = ts.get("currentMeasurement") or {}
        try:
            v = float(cur.get("value"))
        except (TypeError, ValueError):
            return None
        if (ts.get("unit") or "cm").lower() in ("m", "meter"):
            v *= 100
        t = _iso(cur.get("timestamp"), tz)
        return {"value_cm": v, "time": t, "name": station.get("longname") or station.get("shortname") or ""}
    return None


def _iso(value: Any, tz: tzinfo) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(tz)
    except (TypeError, ValueError):
        return None


def po_trend(history: Any) -> Optional[float]:
    """Change in cm over the history (median of the last n values minus median of the first n)."""
    vals = []
    for m in history if isinstance(history, list) else []:
        try:
            vals.append(float(m.get("value")))
        except (TypeError, ValueError, AttributeError):
            continue
    if len(vals) < 2:
        return None
    n = max(1, min(4, len(vals) // 3))

    def med(xs):
        xs = sorted(xs)
        k = len(xs)
        return xs[k // 2] if k % 2 else (xs[k // 2 - 1] + xs[k // 2]) / 2

    return med(vals[-n:]) - med(vals[:n])


# ---------------------------------------------------------------- Saarland HMD
def hmd_urls(station: str) -> list:
    n = re.sub(r"\D+", "", station or "")
    # iframe01 first: umweltserver.saarland.de still answers, but with a series that ended in June 2017 (seen 10/2026).
    return [f"https://iframe01.saarland.de/extern/wasser/daten/{n}.txt",
            f"https://umweltserver.saarland.de/extern/wasser/daten/{n}.txt"] if n else []


def parse_hmd(text: str, tz: tzinfo) -> list:
    """[(datetime, cm)] sorted by time; lines 'DD.MM.YYYY;HH:MM;value' (or space-separated, or ISO date)."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 3:
            parts = line.split()
        if len(parts) < 3:
            continue
        d, t, v = parts[0], parts[1], parts[2]
        try:
            if "." in d:
                day, mon, year = d.split(".")
            else:
                year, mon, day = d.split("-")
            hh, mm = t.split(":")[:2]
            dt = datetime(int(year), int(mon), int(day), int(hh), int(mm), tzinfo=tz)
            val = float(v.replace(",", "."))
        except ValueError:
            continue
        if val <= -1000:
            continue
        out.append((dt, val))
    out.sort(key=lambda x: x[0])
    return out


def hmd_current(series: list) -> Optional[dict]:
    """{value_cm, time, trend_cm} - trend over 3 hours, None when the series is shorter."""
    if not series:
        return None
    now_dt, now_cm = series[-1]
    target = now_dt - timedelta(hours=3)
    prev = next((cm for dt, cm in reversed(series) if dt <= target), None)
    return {"value_cm": now_cm, "time": now_dt, "trend_cm": (now_cm - prev) if prev is not None else None}


# ---------------------------------------------------------------- longer spans (pegel trend)
MAX_DAYS = {"po": 30, "hmd": 7}   # PEGELONLINE keeps 30 days, the HMD text series one week


def po_series(history: Any, tz: tzinfo) -> list:
    """[(datetime, cm)] sorted, from a PEGELONLINE measurements answer."""
    out = []
    for m in history if isinstance(history, list) else []:
        try:
            v = float(m.get("value"))
        except (TypeError, ValueError, AttributeError):
            continue
        t = _iso(m.get("timestamp"), tz)
        if t is not None:
            out.append((t, v))
    out.sort(key=lambda x: x[0])
    return out


def span(series: list, days: int) -> Optional[dict]:
    """{now, then, diff, min, max, avg, then_time, now_time} over the last `days` days of a series, None when it has
    fewer than two values in that window."""
    if not series:
        return None
    end = series[-1][0]
    window = [(t, v) for t, v in series if t >= end - timedelta(days=days)]
    if len(window) < 2:
        return None
    vals = [v for _, v in window]
    return {"now": window[-1][1], "then": window[0][1], "diff": window[-1][1] - window[0][1],
            "min": min(vals), "max": max(vals), "avg": sum(vals) / len(vals),
            "then_time": window[0][0], "now_time": window[-1][0]}


def span_arrow(diff: float) -> str:
    return "↗️" if diff > 5 else ("↘️" if diff < -5 else "→")


def parse_days(token: str) -> Optional[int]:
    """'7d', '7t', '7' -> 7; anything else None."""
    m = re.fullmatch(r"(\d{1,2})\s*[dt]?", (token or "").strip().lower())
    return int(m.group(1)) if m else None


def next_threshold(value_cm: float, thresholds: list) -> Optional[tuple]:
    return next(((cm, label) for cm, label in thresholds if value_cm < cm), None)


# ---------------------------------------------------------------- wording
def trend_text(delta: Optional[float]) -> str:
    """' (↗️ +12 cm/3h)', ' (→ 0 cm/3h)' or ''."""
    if not isinstance(delta, (int, float)):
        return ""
    if abs(delta) < 0.5:
        return " (→ 0 cm/3h)"
    return f" ({'↗️' if delta > 0 else '↘️'} {'+' if delta > 0 else ''}{delta:.0f} cm/3h)"


def metres(cm: float, decimal: str = ",") -> str:
    return f"{cm / 100:.2f}".replace(".", decimal)


def fresh(time: Optional[datetime], now: datetime, max_hours: int = 6) -> bool:
    return time is None or now - time <= timedelta(hours=max_hours)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
