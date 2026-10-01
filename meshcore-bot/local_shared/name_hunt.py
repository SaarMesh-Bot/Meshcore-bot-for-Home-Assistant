"""Name hunt: looks for the names of the unknown hashtag channels on the Channel radar, at quiet hours (service
local_service_plugins/name_hunt_service.py, card NameHunt).

A hashtag channel's key follows from its name, but not the other way round; so the hunt tries names. Candidates come
from what this bot hears itself, which is what is used around here: node and place names from the contacts, words and
#hashtags people type in channels, the radar's word lists, and combinations of those (prefixes, suffixes, numbers,
word pairs): millions of names. A candidate is only accepted when TWO stored messages of that channel byte match it
(channel byte and the 2-byte check code); with millions of tries one message alone would give chance hits.

The packet log is kept 3 days, so the hunt keeps up to SAMPLES_PER_BYTE messages per unknown channel byte itself
(table name_hunt_samples, 30 days). Progress is kept in bot_metadata, so a hunt continues the next night. Nothing is
sent, and messages are never decrypted.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from typing import Any, Iterable, Iterator, Optional

from .channel_radar import (DEFAULT_NAMES, GEN_PREFIXES, GEN_SUFFIXES, GEN_WORDS, PUBLIC_KEY, channel_byte, clean_name,
                            dashboard_names)

SAMPLES_PER_BYTE = 4
KEEP_SAMPLES_DAYS = 30
STATE_KEY = "namehunt.state"
FOUND_KEY = "namehunt.found"
MAX_TOKENS = 6000
PAIR_TOKENS = 250
NUMBERS = [str(i) for i in range(0, 100)] + [str(y) for y in range(2020, 2031)]
SEPARATORS = ("", "-", "_")

SCHEMA = """CREATE TABLE IF NOT EXISTS name_hunt_samples (
    ch TEXT NOT NULL, payload TEXT NOT NULL, ts INTEGER NOT NULL, PRIMARY KEY (ch, payload))"""

_WORD = re.compile(r"[a-z0-9][a-z0-9\-]{1,30}")


def _table(conn: Any, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


# ------------------------------------------------------------------------------------------------ the messages to match
def collect_samples(db: Any, unknown: Iterable[str], now: Optional[float] = None) -> dict:
    """Store up to SAMPLES_PER_BYTE packet payloads per unknown channel byte (from the 3-day packet log) and return
    {byte int: [payload bytes, ...]} for the bytes that have at least two."""
    now = time.time() if now is None else now
    want = {c.lower() for c in unknown}
    with db.connection() as conn:
        conn.execute(SCHEMA)
        conn.execute("DELETE FROM name_hunt_samples WHERE ts < ?", (int(now - KEEP_SAMPLES_DAYS * 86400),))
        have: dict = {}
        for ch, n in conn.execute("SELECT ch, COUNT(*) FROM name_hunt_samples GROUP BY ch"):
            have[ch] = n
        if want and _table(conn, "packet_stream"):
            for ts, data in conn.execute("SELECT timestamp, data FROM packet_stream WHERE type IN ('packet', 'routing') "
                                         "AND data LIKE '%GRP_TXT%' ORDER BY id DESC LIMIT 20000"):
                try:
                    p = json.loads(data)
                except ValueError:
                    continue
                payload = str(p.get("payload_hex") or "")
                if p.get("payload_type_name") != "GRP_TXT" or len(payload) < 10:
                    continue
                ch = payload[:2].lower()
                if ch not in want or have.get(ch, 0) >= SAMPLES_PER_BYTE:
                    continue
                cur = conn.execute("INSERT OR IGNORE INTO name_hunt_samples (ch, payload, ts) VALUES (?,?,?)",
                                   (ch, payload.lower(), int(ts)))
                if cur.rowcount:
                    have[ch] = have.get(ch, 0) + 1
        conn.commit()
        out: dict = {}
        for ch, payload in conn.execute("SELECT ch, payload FROM name_hunt_samples"):
            if ch in want:
                try:
                    out.setdefault(int(ch, 16), []).append(bytes.fromhex(payload))
                except ValueError:
                    continue
    return {b: v for b, v in out.items() if len(v) >= 2}


# ------------------------------------------------------------------------------------------------ candidate names
def _split(text: str) -> list:
    return _WORD.findall((text or "").lower())


def tokens(db: Any) -> list:
    """Words to build names from, most useful first: hashtags people typed, the radar's lists, node and place names,
    words from channel messages (most frequent first)."""
    hashtags: dict = {}
    words: dict = {}
    names: dict = {}
    with db.connection() as conn:
        if _table(conn, "message_stats"):
            for (content,) in conn.execute("SELECT content FROM message_stats WHERE timestamp >= ? AND content IS NOT NULL",
                                           (int(time.time() - 60 * 86400),)):
                text = str(content or "").lower()
                for tag in re.findall(r"#([a-z0-9][a-z0-9\-_]{0,30})", text):
                    hashtags[tag] = hashtags.get(tag, 0) + 1
                body = text.split(":", 1)[1] if ":" in text[:40] else text
                for w in _split(body):
                    if 3 <= len(w) <= 20:
                        words[w] = words.get(w, 0) + 1
        if _table(conn, "complete_contact_tracking"):
            cols = {r[1] for r in conn.execute("PRAGMA table_info(complete_contact_tracking)")}
            fields = [c for c in ("name", "city") if c in cols]
            for row in conn.execute(f"SELECT {', '.join(fields)} FROM complete_contact_tracking"):
                for value in row:
                    v = str(value or "").lower()
                    whole = re.sub(r"[^a-z0-9\-]+", "-", v).strip("-")
                    if 2 <= len(whole) <= 30:
                        names[whole] = names.get(whole, 0) + 1
                    for w in _split(v):
                        if 2 <= len(w) <= 20:
                            names[w] = names.get(w, 0) + 1
    ordered = (sorted(hashtags, key=lambda w: -hashtags[w]) + [w.lower() for w in DEFAULT_NAMES + GEN_WORDS]
               + sorted(names, key=lambda w: -names[w]) + sorted(words, key=lambda w: -words[w]))
    out, seen = [], set()
    for w in ordered:
        w = clean_name(w)
        if w and w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= MAX_TOKENS:
            break
    return out


def candidates(toks: list) -> Iterator[str]:
    """Every name to try, in a fixed order (so a hunt can continue where it stopped)."""
    for t in toks:
        yield t
    for t in toks:
        for p in GEN_PREFIXES:
            for s in GEN_SUFFIXES:
                if p or s:
                    yield f"{p}{t}{s}"
    for t in toks:
        for sep in SEPARATORS:
            for n in NUMBERS:
                yield f"{t}{sep}{n}"
    top = toks[:PAIR_TOKENS]
    for a in top:
        for b in top:
            if a != b:
                for sep in SEPARATORS:
                    yield f"{a}{sep}{b}"


def count_candidates(toks: list) -> int:
    n = len(toks)
    affix = len(GEN_PREFIXES) * len(GEN_SUFFIXES) - 1
    top = min(len(toks), PAIR_TOKENS)
    return n + n * affix + n * len(SEPARATORS) * len(NUMBERS) + top * (top - 1) * len(SEPARATORS)


def signature(toks: list, bytes_: Iterable[int]) -> str:
    return hashlib.sha256(("\n".join(toks) + "|" + ",".join(f"{b:02x}" for b in sorted(bytes_))).encode()).hexdigest()[:16]


def _matches(key: bytes, payloads: list) -> int:
    n = 0
    for raw in payloads:
        if len(raw) < 4:
            continue
        mac, ciphertext = raw[1:3], raw[3:]
        if hmac.compare_digest(hmac.new(key + bytes(16), ciphertext, hashlib.sha256).digest()[:2], mac):
            n += 1
    return n


def hunt(samples: dict, names: Iterator[str], max_count: int, should_stop=None) -> tuple:
    """Try up to `max_count` names. Returns (tried, [(name, channel byte hex, matching messages)]).
    `should_stop()` is asked every few thousand names (time budget)."""
    sha = hashlib.sha256
    found, tried = [], 0
    targets = set(samples)
    for name in names:
        if tried >= max_count:
            break
        tried += 1
        key = sha(("#" + name).encode("utf-8")).digest()[:16]
        b = sha(key).digest()[0]
        if b in targets and key != PUBLIC_KEY:
            hits = _matches(key, samples[b])
            if hits >= 2:
                found.append((name, f"{b:02x}", hits))
                targets.discard(b)
                if not targets:
                    break
        if should_stop is not None and tried % 5000 == 0 and should_stop():
            break
    return tried, found


# ------------------------------------------------------------------------------------------------ quiet hours
def hour_profile(db: Any, local_hour=None, now: Optional[float] = None) -> list:
    """How busy every local hour of the day is with PEOPLE: the average number of messages plus three times the commands
    per hour, over the days each hour is in the stats (message_stats / command_stats keep about 7 days). None for an
    hour without data. Radio packets are not used: most of them are repeater adverts, also at night, so by packets the
    afternoon looked quieter than the night (found 2026-10-01: 12, 13, 16, 18)."""
    import datetime as _dt
    now = time.time() if now is None else now
    current = int(now // 3600) * 3600
    buckets: dict = {}
    with db.connection() as conn:
        for table, weight in (("message_stats", 1), ("command_stats", 3)):
            if not _table(conn, table):
                continue
            for ts, n in conn.execute(f"SELECT CAST(timestamp / 3600 AS INTEGER) * 3600, COUNT(*) FROM {table} "
                                      "WHERE timestamp >= ? GROUP BY 1", (int(now - 8 * 86400),)):
                buckets[ts] = buckets.get(ts, 0) + n * weight
    if not buckets:
        return [None] * 24
    first, last = min(buckets), min(max(buckets), current - 3600)
    sums, seen = [0.0] * 24, [0] * 24
    t = first + 3600                      # whole hours only: the first and the current one are incomplete
    while t <= last:
        h = local_hour(t) if local_hour else _dt.datetime.fromtimestamp(t).hour
        sums[h] += buckets.get(t, 0)      # an hour without messages counts as 0 (quiet), not as missing
        seen[h] += 1
        t += 3600
    return [round(sums[h] / seen[h], 2) if seen[h] else None for h in range(24)]


def quiet_hours(db: Any, hours: int = 4, local_hour=None, now: Optional[float] = None, profile: Optional[list] = None) -> list:
    """The `hours` local hours in which people use the mesh and the bot least (hour_profile), quietest first;
    on a tie the hours closest to 03:00 first. Default 2-5 with less than two days of stats."""
    prof = profile if profile is not None else hour_profile(db, local_hour, now)
    known = [h for h in range(24) if prof[h] is not None]
    if len(known) < 24 or sum(prof[h] for h in known) < 20:
        return [(2 + i) % 24 for i in range(max(1, min(24, hours)))]    # from 02:00 on, as many hours as asked
    return sorted(known, key=lambda h: (prof[h], min(abs(h - 3), 24 - abs(h - 3)), h))[:hours]


def load_state(db: Any) -> dict:
    try:
        s = json.loads(db.get_metadata(STATE_KEY) or "{}")
        return s if isinstance(s, dict) else {}
    except ValueError:
        return {}


def save_state(db: Any, state: dict) -> None:
    db.set_metadata(STATE_KEY, json.dumps(state))


def found_list(db: Any) -> list:
    try:
        f = json.loads(db.get_metadata(FOUND_KEY) or "[]")
        return f if isinstance(f, list) else []
    except ValueError:
        return []


def add_found(db: Any, name: str, ch: str, hits: int, now: float) -> None:
    items = found_list(db) + [{"name": "#" + name, "byte": ch, "messages": hits, "ts": int(now)}]
    db.set_metadata(FOUND_KEY, json.dumps(items[-50:]))


def status(db: Any) -> dict:
    """For the Channel radar page."""
    s = load_state(db)
    return {"quiet_hours": s.get("quiet_hours", []), "profile": s.get("profile", []), "last_run": s.get("last_run"), "position": s.get("position", 0),
            "total": s.get("total", 0), "rounds": s.get("rounds", 0), "tried_total": s.get("tried_total", 0),
            "bytes": s.get("bytes", 0), "found": found_list(db)[-10:], "already_added": dashboard_names(db)}
