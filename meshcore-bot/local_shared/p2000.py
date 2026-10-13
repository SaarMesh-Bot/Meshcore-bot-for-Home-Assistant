"""P2000 on the mesh, with as little airtime as possible (card: Plugins -> P2000; command `p2000`).

Source: the public AlarmeringDroid API that Home Assistant's p2000_nl integration also uses
(https://beta.alarmeringdroid.nl/api2/find/{"regios":["21"]} -> the latest 30 messages of the chosen regions). Every
message has `dienst` (Brandweer / Ambulance / Politie / ...), `prio1` ("1" for P1, A1, "met spoed") and its text.

The bot keeps the messages of the last days in its own database (table p2000) and:
- posts only the priority-1 messages in the card's channel (at most a few an hour);
- answers `p2000` (latest message, `p2000 3`, `p2000 <place>`, `p2000 spoed`, `p2000 vandaag`) in that channel or by DM;
- once a day (default 12:00) posts how often the fire brigade, ambulance and police were called out in the last 24 h.

Before (2026-10) a Home Assistant automation posted every message in #p2000-zl: about 30 a day, the biggest part of the
bot's airtime, and the reason for complaints about needless traffic.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Optional

API_URL = "https://beta.alarmeringdroid.nl/api2/find/"
KEEP_S = 8 * 86400
MAX_BYTES = 130
FRESH_S = 30 * 60          # a priority-1 message older than this is not posted any more (after a restart, a gap)
SERVICES = ("brandweer", "ambulance", "politie")

_POSTCODE = re.compile(r"^\s*\d{4}\s?[A-Za-z]{2}\s+")
_TIME = re.compile(r"(\d{1,2}):(\d{2})")


def ensure(conn: Any) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS p2000 (
        id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, dienst TEXT, prio1 INTEGER NOT NULL DEFAULT 0,
        plaats TEXT, tekst TEXT NOT NULL, regio TEXT, posted INTEGER NOT NULL DEFAULT 0, datum TEXT, tijd TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_p2000_ts ON p2000(ts)")


def _ts(datum: str, tijd: str, now: datetime) -> Optional[int]:
    """'12-10' + '21:23' (or '21:23 - 21:24') in the bot's time zone -> epoch; the year is the one that fits best."""
    try:
        day, month = (int(x) for x in str(datum).split("-")[:2])
        m = _TIME.search(str(tijd or ""))
        hour, minute = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        dt = now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)
    except (ValueError, TypeError, AttributeError):
        return None
    if dt - now > timedelta(days=1):          # "31-12" seen on 1 January
        dt = dt.replace(year=dt.year - 1)
    return int(dt.timestamp())


def parse(data: Any, now: datetime) -> list:
    """The API answer -> [{id, ts, dienst, prio1, plaats, tekst, regio, tijd}], oldest first."""
    items = (data or {}).get("meldingen") if isinstance(data, dict) else data
    out = []
    for m in items or []:
        if not isinstance(m, dict):
            continue
        try:
            mid = int(m.get("id"))
        except (TypeError, ValueError):
            continue
        text = " ".join(str(m.get("tekstmelding") or m.get("melding") or "").split())
        ts = _ts(m.get("datum"), m.get("tijd"), now)
        if not text or ts is None:
            continue
        place = _POSTCODE.sub("", str(m.get("plaats") or "")).strip()
        hhmm = _TIME.search(str(m.get("tijd") or ""))
        out.append({"id": mid, "ts": ts, "dienst": str(m.get("dienst") or "").strip(),
                    "prio1": str(m.get("prio1") or "0").strip() == "1", "plaats": place[:40], "tekst": text[:200],
                    "regio": str(m.get("regioid") or ""), "tijd": hhmm.group(0) if hhmm else "",
                    "datum": str(m.get("datum") or "")[:5]})
    out.sort(key=lambda x: (x["ts"], x["id"]))
    return out


def store(conn: Any, items: Iterable[dict], now: Optional[float] = None) -> list:
    """Save new messages; returns the ones that were not known yet. Also forgets messages older than KEEP_S."""
    now = time.time() if now is None else now
    ensure(conn)
    new = []
    for m in items:
        cur = conn.execute("INSERT OR IGNORE INTO p2000 (id, ts, dienst, prio1, plaats, tekst, regio, datum, tijd) "
                           "VALUES (?,?,?,?,?,?,?,?,?)",
                           (m["id"], m["ts"], m["dienst"], 1 if m["prio1"] else 0, m["plaats"], m["tekst"], m["regio"],
                            m.get("datum", ""), m.get("tijd", "")))
        if cur.rowcount:
            new.append(m)
    conn.execute("DELETE FROM p2000 WHERE ts < ?", (int(now - KEEP_S),))
    conn.commit()
    return new


def mark_posted(conn: Any, mid: int) -> None:
    conn.execute("UPDATE p2000 SET posted = 1 WHERE id = ?", (mid,))
    conn.commit()


def posted_since(conn: Any, since: float) -> int:
    ensure(conn)
    return conn.execute("SELECT COUNT(*) FROM p2000 WHERE posted = 1 AND ts >= ?", (int(since),)).fetchone()[0]


def fit(text: str, max_bytes: int = MAX_BYTES) -> str:
    if len(text.encode("utf-8")) <= max_bytes:
        return text
    while text and len((text + "…").encode("utf-8")) > max_bytes:
        text = text[:-1]
    return text.rstrip(" ,.;:") + "…"


def line(m: dict, with_date: bool = False) -> str:
    """'21:23 Brandweer met spoed naar Dorpsstraat, Geleen, voor een onderzoek' (the service only when the text lacks it)."""
    text = m["tekst"]
    service = m.get("dienst") or ""
    if service and service.lower() not in ("onbekend", "") and not text.lower().startswith(service.lower()[:4]):
        text = f"{service}: {text}"
    when = m.get("tijd") or ""
    if with_date and m.get("datum"):
        when = f"{m['datum']} {when}".strip()
    return fit(f"{when} {text}".strip())


def _row(r: tuple) -> dict:
    return {"id": r[0], "ts": r[1], "dienst": r[2] or "", "prio1": bool(r[3]), "plaats": r[4] or "", "tekst": r[5],
            "datum": r[6] or "", "tijd": r[7] or ""}


def latest(conn: Any, n: int = 1, place: str = "", prio1: bool = False) -> list:
    """The newest n messages (newest first), optionally only a place (or a word in the text) or only priority 1."""
    ensure(conn)
    sql = "SELECT id, ts, dienst, prio1, plaats, tekst, datum, tijd FROM p2000 WHERE 1=1"
    args: list = []
    if place:
        sql += " AND (lower(plaats) LIKE ? OR lower(tekst) LIKE ?)"
        args += [f"%{place.lower()}%"] * 2
    if prio1:
        sql += " AND prio1 = 1"
    sql += " ORDER BY ts DESC, id DESC LIMIT ?"
    args.append(max(1, min(n, 3)))
    return [_row(r) for r in conn.execute(sql, args).fetchall()]


def counts(conn: Any, since: float, until: float) -> dict:
    """{'brandweer': (all, prio1), 'ambulance': (...), 'politie': (...)} between two moments."""
    ensure(conn)
    out = {s: (0, 0) for s in SERVICES}
    for service, total, urgent in conn.execute(
            "SELECT lower(dienst), COUNT(*), SUM(prio1) FROM p2000 WHERE ts >= ? AND ts < ? GROUP BY lower(dienst)",
            (int(since), int(until))).fetchall():
        if service in out:
            out[service] = (int(total), int(urgent or 0))
    return out


def summary_text(c: dict, translate: Callable[..., str]) -> str:
    return fit(translate("services.p2000.summary",
                         fire=c["brandweer"][0], fire_p1=c["brandweer"][1],
                         ambu=c["ambulance"][0], ambu_p1=c["ambulance"][1],
                         police=c["politie"][0], police_p1=c["politie"][1]))


def summary_due(local: datetime, at: str, done_day: str) -> bool:
    """True from the set time (HH:MM, local) until 30 minutes later, once a day."""
    m = _TIME.fullmatch(str(at or "").strip())
    if not m or done_day == local.strftime("%Y-%m-%d"):
        return False
    start = int(m.group(1)) * 60 + int(m.group(2))
    minute = local.hour * 60 + local.minute
    return start <= minute < start + 30
