"""German warnings on the mesh: DWD weather warnings and NINA (BBK) civil-protection warnings, compact enough for LoRa.

Ported from the SaarMesh bot (saarmesh.de), where this has run in #warnings since 2025.

Sources
- DWD: https://www.dwd.de/DWD/warnungen/warnapp/json/warnings.json - JSONP (``warnWetter.loadWarnings({...});``) with
  every active warning per warn cell. Each warning has ``level`` (1-4, heat 50/51), ``start``/``end`` (ms), ``regionName``,
  ``stateShort`` (e.g. SL, RP), ``headline``. Filtered on the federal state(s) on the card (``states``, default SL).
- NINA: https://warnung.bund.de/api31/dashboard/{ARS12}.json - the warnings for one district (Kreis), keyed on its
  12-digit Amtlicher Regionalschlüssel. The fields sit under ``payload.data`` (older answers: flat). Cancellations
  (``msgType`` Cancel / headline "Entwarnung") are returned separately so the service can post an all-clear.

One warning becomes one line: ``🟧 Saarlouis · Gewitter (stark) · 18:10–19:30``. Updates of the same warning (new id,
new "sent") keep the same key, so they are not posted again. NINA mirrors DWD weather warnings 1:1; those duplicates
are dropped when DWD already has the same region and phenomenon.

Nothing here talks to the network or the radio; the DEWarn service and the ``warnung`` command do.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Iterable, Optional

DWD_URL = "https://www.dwd.de/DWD/warnungen/warnapp/json/warnings.json"
NINA_URL = "https://warnung.bund.de/api31/dashboard/{ars}.json"
MAX_BYTES = 130

# The districts of the Saarland (5-digit ARS prefix) - the default for the NINA card.
SAARLAND_ARS = {
    "10041": "Regionalverband Saarbrücken",
    "10042": "Merzig-Wadern",
    "10043": "Neunkirchen",
    "10044": "Saarlouis",
    "10045": "Saarpfalz-Kreis",
    "10046": "St. Wendel",
}
STATE_NAMES = {
    "BW": "baden-württemberg", "BY": "bayern", "BE": "berlin", "BB": "brandenburg", "HB": "bremen", "HH": "hamburg",
    "HE": "hessen", "MV": "mecklenburg-vorpommern", "NI": "niedersachsen", "NW": "nordrhein-westfalen",
    "RP": "rheinland-pfalz", "SL": "saarland", "SN": "sachsen", "ST": "sachsen-anhalt", "SH": "schleswig-holstein",
    "TH": "thüringen",
}


# ---------------------------------------------------------------- compact wording
_INTENS = [("extrem", "extrem"), ("schwer", "schwer"), ("stark", "stark"), ("markant", "markant"),
           ("mäßig", "mäßig"), ("maessig", "mäßig"), ("leicht", "leicht")]
# first match wins, so the more specific stem comes first
_PHENOM = [
    ("gewitter", "Gewitter"),
    ("orkanbö", "Orkanböen"), ("orkanboe", "Orkanböen"), ("orkan", "Orkan"),
    ("sturmbö", "Sturmböen"), ("sturmboe", "Sturmböen"), ("windbö", "Windböen"), ("windboe", "Windböen"),
    ("sturm", "Sturm"), ("bö", "Böen"), ("boe", "Böen"),
    ("starkregen", "Starkregen"), ("dauerregen", "Dauerregen"), ("regen", "Regen"),
    ("glatteis", "Glatteis"), ("glätte", "Glätte"), ("glaette", "Glätte"), ("tauwetter", "Tauwetter"),
    ("schneefall", "Schneefall"), ("schneever", "Schneeverwehung"), ("schnee", "Schnee"),
    ("frost", "Frost"), ("hitze", "Hitze"), ("uv", "UV-Gefahr"), ("nebel", "Nebel"), ("hagel", "Hagel"),
    ("hochwasser", "Hochwasser"), ("überschwemm", "Überschwemmung"),
    ("brand", "Brand"), ("feuer", "Feuer"), ("rauch", "Rauch"),
    ("gefahrstoff", "Gefahrstoff"), ("gefahrgut", "Gefahrgut"), ("chemi", "Chemie-Gefahr"),
    ("störfall", "Störfall"), ("stoerfall", "Störfall"),
    ("strom", "Stromausfall"), ("blackout", "Stromausfall"), ("trinkwasser", "Trinkwasser"), ("wasser", "Wasser"),
]
_NINA_CAT = [("odour", "Geruch"), ("odor", "Geruch"), ("forest fire", "Waldbrand"), ("flood", "Hochwasser"),
             ("hazmat", "Gefahrstoff"), ("chemical", "Gefahrstoff"), ("hazard", "Gefahrstoff"),
             ("health", "Gesundheit"), ("power", "Stromausfall"), ("blackout", "Stromausfall"),
             ("drinking water", "Trinkwasser"), ("fire", "Brand")]
# NINA warnings with severity "minor" that still go out: authorities rate smoke from a fire as minor even when the
# text says "leave the area now".
_MINOR_PUSH = ("brand", "feuer", "waldbrand", "flächenbrand", "flaechenbrand", "rauch", "fire", "gefahrstoff",
               "gefahrgut", "chemi", "chemical", "störfall", "stoerfall", "austritt", "kontamin", "explos", "abc-",
               "geruch", "belästig")


def short_region(name: Optional[str], fallback: str = "") -> str:
    """'Landkreis Saarlouis' -> 'Saarlouis'."""
    n = " ".join((name or "").split())
    for pref in ("Regionalverband ", "Landkreis ", "Landeshauptstadt ", "Kreis ", "Stadt "):
        if n.startswith(pref):
            n = n[len(pref):]
            break
    return n or fallback


def compact_phenom(headline: Optional[str]) -> str:
    """'Amtliche WARNUNG vor STARKEM GEWITTER' -> 'Gewitter (stark)'; unknown -> the cleaned-up headline."""
    h = " ".join((headline or "").split())
    if not h:
        return "Warnung"
    low = h.lower()
    intens = next((lbl for stem, lbl in _INTENS if stem in low), "")
    phenom = next((lbl for stem, lbl in _PHENOM if stem in low), "")
    if phenom:
        return f"{phenom} ({intens})" if intens else phenom
    core = re.sub(r"^(amtliche|offizielle|vorläufige|vorlaeufige)\s+", "", h, flags=re.I)
    core = re.sub(r"^(unwetter|hitze|frost|glätte|glaette)?\s*(warnung|warning|vorabinformation|vorinfo|meldung)\s*"
                  r"(vor|before|of|für|fuer)?\s*", "", core, count=1, flags=re.I)
    core = core.strip(" :–-·") or h
    return core[:1].upper() + core[1:]


def nina_region(headline: Optional[str], fallback: str, region_tokens: Iterable[str] = ()) -> str:
    """The region from the headline's suffix ('... - Landkreis Neunkirchen', '... - Saarland') when it names one of
    ours, else the district of the feed. Keeps state-wide MoWaS warnings from being pinned on one district."""
    tokens = [t.lower() for t in region_tokens]
    segs = [p.strip() for p in re.split(r"\s[-–—]\s", headline or "") if p.strip()]
    for seg in reversed(segs[1:]):
        low = seg.lower()
        if any(t in low for t in tokens):
            return short_region(seg, fallback)
    return short_region(fallback, fallback)


def nina_phenom(headline: Optional[str], category: Optional[str]) -> str:
    """Smoke and smell first (that is what people notice), then the structured category, then the headline."""
    h, c = (headline or "").lower(), (category or "").lower()
    if "rauch" in h:
        return "Rauch"
    if "geruch" in h or "odour" in c or "odor" in c:
        return "Geruch"
    if "waldbrand" in h or "forest fire" in c:
        return "Waldbrand"
    for key, lbl in _NINA_CAT:
        if key in c:
            return lbl
    return compact_phenom(headline)


def level_icon(level: Any) -> str:
    try:
        lvl = int(level)
    except (TypeError, ValueError):
        return "🟩"
    if lvl == 51 or lvl >= 4 and lvl < 50:
        return "🟥"
    if lvl in (50, 3):
        return "🟧"
    return "🟨" if lvl == 2 else "🟩"


def severity(sev: Any) -> str:
    """NINA severity -> minor/moderate/severe/extreme."""
    if isinstance(sev, (int, float)):
        return ("minor", "minor", "moderate", "severe", "extreme")[max(0, min(4, int(sev)))]
    s = str(sev or "").lower()
    if "extreme" in s:
        return "extreme"
    if "severe" in s or "hoch" in s:
        return "severe"
    if "moderate" in s or "mäßig" in s:
        return "moderate"
    return "minor"


SEV_ICON = {"extreme": "🟥", "severe": "🟧", "moderate": "🟨", "minor": "🟩"}


def to_dt(value: Any, tz: tzinfo) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            v = float(value)
            v = v / 1000 if v > 10_000_000_000 else v
            return datetime.fromtimestamp(v, tz=timezone.utc).astimezone(tz)
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).astimezone(tz)
    except (ValueError, OverflowError, OSError):
        return None


def when(start: Optional[datetime], end: Optional[datetime], now: datetime) -> str:
    """'18:10–19:30' today, '17.10. 18:10–18.10. 06:00' across days, 'bis 06:00' / 'ab 18.10. 06:00'."""
    today = now.strftime("%d.%m.")

    def fmt(d: datetime) -> str:
        s = d.strftime("%d.%m. %H:%M")
        return s[len(today) + 1:] if s.startswith(today) else s

    if start and end:
        if start <= now:
            return f"bis {fmt(end)}"
        if start.date() == end.date():
            return f"{fmt(start)}–{end.strftime('%H:%M')}"
        return f"{fmt(start)}–{fmt(end)}"
    if end:
        return f"bis {fmt(end)}"
    if start and start > now:
        return f"ab {fmt(start)}"
    return ""


# ---------------------------------------------------------------- DWD
def parse_dwd_payload(text: str) -> Optional[dict]:
    """The JSON inside the JSONP wrapper (or plain JSON)."""
    raw = (text or "").strip()
    m = re.search(r"warnWetter\.loadWarnings\((.*)\);?\s*$", raw, re.S)
    try:
        if m:
            return json.loads(m.group(1))
        if raw.startswith("{"):
            return json.loads(raw)
    except ValueError:
        return None
    return None


def dwd_items(data: Any, states: Iterable[str], now: datetime, min_level: int = 2, ahead_hours: int = 12) -> list:
    """[{key, text, level, region, phenom}] for the federal states given (codes like SL), strongest first.
    Warnings that ended, or start more than ahead_hours from now, are skipped."""
    if not isinstance(data, dict):
        return []
    codes = {s.strip().upper() for s in states if s.strip()}
    names = {STATE_NAMES.get(c, c.lower()) for c in codes}
    warns = data.get("warnings")
    flat: list = []
    if isinstance(warns, dict):
        for cell, arr in warns.items():
            for w in arr if isinstance(arr, list) else []:
                if isinstance(w, dict):
                    flat.append((cell, w))
    elif isinstance(warns, list):
        flat = [("", w) for w in warns if isinstance(w, dict)]
    tz = now.tzinfo or timezone.utc
    out, seen = [], set()
    for cell, w in flat:
        try:
            lvl = int(w.get("level") or 0)
        except (TypeError, ValueError):
            lvl = 0
        if lvl < min_level:
            continue
        short = str(w.get("stateShort") or "").upper().strip()
        state = str(w.get("state") or "").lower().strip()
        if codes and not (short in codes or (not short and state in names)):
            continue
        start, end = to_dt(w.get("start"), tz), to_dt(w.get("end"), tz)
        if end and end <= now:
            continue
        if start and start > now + timedelta(hours=ahead_hours):
            continue
        headline = w.get("headline") or w.get("event") or "DWD-Warnung"
        region = short_region(w.get("regionName"), "?")
        phenom = compact_phenom(headline)
        # One key per region + phenomenon + start: the DWD re-issues warnings with a new id when they are extended.
        key = "dwd::" + "::".join((region.lower(), phenom.lower(), start.isoformat() if start else ""))
        if key in seen:
            continue
        seen.add(key)
        span = when(start, end, now)
        text = f"{level_icon(lvl)} {region} · {phenom}" + (f" · {span}" if span else "")
        out.append({"key": key, "text": text, "level": lvl, "region": region.lower(), "phenom": phenom.lower(),
                    "end": end.timestamp() if end else None})
    out.sort(key=lambda i: (-(i["level"] if i["level"] < 50 else i["level"] - 47), i["text"]))
    return out


# ---------------------------------------------------------------- NINA
def normalize_ars(ars: str) -> str:
    s = "".join(ch for ch in str(ars) if ch.isdigit())
    if len(s) == 12:
        return s
    if 5 <= len(s) < 12:
        return s.ljust(12, "0")
    return ""


def _pick(*vals) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _first_sentence(text: str) -> str:
    t = (text or "").strip().replace("\r", " ")
    for sep in (". ", "\n", "; "):
        if sep in t:
            return t.split(sep, 1)[0].strip()
    return t


def nina_items(data: Any, area_name: str, now: datetime, region_tokens: Iterable[str] = ()) -> tuple:
    """(warnings, cancels) for one district's dashboard answer.
    warnings: [{key, text, sev, region, phenom, is_dwd}]; cancels: [(key_prefix, label)]."""
    tz = now.tzinfo or timezone.utc
    cards = data if isinstance(data, list) else ((data or {}).get("cards") or (data or {}).get("warnings") or [])
    out, cancels, seen = [], [], set()
    for c in cards if isinstance(cards, list) else []:
        if not isinstance(c, dict):
            continue
        p = c.get("payload") if isinstance(c.get("payload"), dict) else {}
        pd = p.get("data") if isinstance(p.get("data"), dict) else {}
        i18n = c.get("i18nTitle") if isinstance(c.get("i18nTitle"), dict) else {}
        headline = _pick(pd.get("headline"), p.get("headline"), p.get("event"), c.get("title"), i18n.get("de"), "Warnung")
        cat = _pick(pd.get("category"), c.get("category"), p.get("category"), i18n.get("en"))
        msg_type = str(pd.get("msgType") or p.get("type") or c.get("type") or "").lower()
        region = nina_region(headline, area_name, region_tokens)
        segs = [x.strip() for x in re.split(r"\s[-–—]\s", headline) if x.strip()]
        phenom = nina_phenom(segs[0] if segs else headline, cat or i18n.get("en"))
        prefix = "nina::" + region.lower().replace(":", "") + "::" + phenom.lower().replace(":", "") + "::"
        if msg_type == "cancel" or headline.lower().startswith("entwarnung"):
            cancels.append((prefix, f"{region} · {phenom}"))
            continue
        sev = severity(pd.get("severity") or p.get("severity") or c.get("severity"))
        if sev == "minor" and not any(k in " ".join((headline, cat, i18n.get("en") or "")).lower() for k in _MINOR_PUSH):
            continue
        desc = _pick(pd.get("description"), pd.get("instruction"), pd.get("headline"), c.get("body"), headline)
        provider = _pick(pd.get("provider"), c.get("provider"), p.get("provider"), "NINA")
        start = to_dt(_pick(pd.get("onset"), pd.get("effective")), tz)
        end = to_dt(_pick(pd.get("expires"), pd.get("end")), tz)
        if end and end <= now:
            continue
        # Content signature instead of id/sent: an update with a new id and the same content is not posted again.
        sig = hashlib.md5("|".join((sev, headline.strip().lower(), _first_sentence(desc).lower())).encode()).hexdigest()[:12]
        key = prefix + sig
        if key in seen:
            continue
        seen.add(key)
        span = when(start, end, now)
        text = f"{SEV_ICON[sev]} {region} · {phenom}" + (f" · {span}" if span else "")
        out.append({"key": key, "text": text, "sev": sev, "region": region.lower(), "phenom": phenom.lower(),
                    "is_dwd": provider.upper().startswith("DWD")})
    return out, cancels


def merge(dwd: list, nina: list, max_dwd: int = 6, max_nina: int = 8) -> list:
    """DWD first, then NINA without the DWD weather warnings NINA mirrors. Each item once (by key)."""
    out, keys = [], set()
    sigs = {(d["region"], d["phenom"]) for d in dwd[:max_dwd]}
    for d in dwd[:max_dwd]:
        if d["key"] not in keys:
            keys.add(d["key"])
            out.append(d)
    for n in nina[:max_nina]:
        if n["key"] in keys or (n.get("is_dwd") and (n["region"], n["phenom"]) in sigs):
            continue
        keys.add(n["key"])
        out.append(n)
    return out


# ---------------------------------------------------------------- settings (card DEWarn)
DEFAULTS = {"channel": "#warnings", "states": "SL", "districts": ",".join(SAARLAND_ARS), "min_level": "2",
            "max_dwd": "6", "all_clear": "true", "poll_seconds": "300"}


def parse_districts(text: str) -> dict:
    """{ars5: name} from '10041, 10044=Saarlouis, 07235'. Names of the Saarland's districts are known."""
    out = {}
    for part in (text or "").replace(";", ",").split(","):
        code, _, name = part.partition("=")
        digits = "".join(ch for ch in code if ch.isdigit())
        if len(digits) < 5:
            continue
        ars5 = digits[:5]
        out[ars5] = name.strip() or SAARLAND_ARS.get(ars5) or f"Kreis {ars5}"
    return out


def settings(cfg: Any, section: str = "DEWarn") -> dict:
    has = cfg.has_section(section)

    def get(key):
        return ((cfg.get(section, key, fallback=DEFAULTS[key]) if has else DEFAULTS[key]) or DEFAULTS[key]).strip()

    def num(key, lo, hi):
        try:
            return max(lo, min(hi, int(get(key))))
        except ValueError:
            return int(DEFAULTS[key])

    states = [s.strip().upper() for s in get("states").replace(";", ",").split(",") if s.strip()]
    districts = parse_districts(get("districts"))
    tokens = set()
    for name in districts.values():
        tokens.update(w for w in re.split(r"[\s\-/]+", short_region(name).lower()) if len(w) > 3)
    tokens.update(STATE_NAMES.get(s, s.lower()) for s in states)
    if "SL" in states:
        tokens.update(("saarbrücken", "saarbruecken", "regionalverband", "homburg", "völklingen", "voelklingen",
                       "st. wendel", "st.wendel"))
    channels = []
    for n in get("channel").replace(";", ",").split(","):
        n = n.strip()
        n = n.lower() if n.startswith("#") else n
        if n and n not in channels:
            channels.append(n)
    return {"channels": channels or [DEFAULTS["channel"]], "states": states, "districts": districts,
            "tokens": sorted(tokens), "min_level": num("min_level", 1, 4), "max_dwd": num("max_dwd", 1, 20),
            "all_clear": get("all_clear").lower() in ("1", "true", "yes", "on"),
            "poll_seconds": num("poll_seconds", 120, 1800)}


# ---------------------------------------------------------------- splitting
def split_lines(header: str, lines: list, max_bytes: int = MAX_BYTES) -> list:
    """Header + one line per warning, packed into as few messages of max_bytes as fit. A line that is too long on its
    own is cut with '…'."""
    def fit(s: str) -> str:
        if len(s.encode()) <= max_bytes:
            return s
        while s and len((s + "…").encode()) > max_bytes:
            s = s[:-1]
        return s.rstrip() + "…"

    msgs, cur = [], fit(header) if header else ""
    for line in lines:
        line = fit(line)
        cand = f"{cur}\n{line}" if cur else line
        if len(cand.encode()) <= max_bytes:
            cur = cand
        else:
            if cur:
                msgs.append(cur)
            cur = line
    if cur:
        msgs.append(cur)
    return msgs
