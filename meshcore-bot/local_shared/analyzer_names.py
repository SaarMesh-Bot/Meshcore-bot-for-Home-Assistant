"""Names for nodes the bot only knows by a key prefix, looked up at the public EU Meshcore Analyzer.

The neighbour lists meshcore-ha gives (Repeater page, `rptr buren`) carry a 6-hex key prefix; when neither meshcore-ha
nor the bot's own Contacts know the name, the AnalyzerFeed service (card AnalyzerFeed, option "Look up unknown names")
asks the analyzer: /api/nodes/resolve?prefix=a1b2c3 gives the nodes whose key starts with it. Only an unambiguous answer
(exactly one node) is used. Each prefix is asked at most once per RECHECK_S, and at most MAX_PER_HOUR per hour, to
be kind to a free service. Prefixes shorter than 6 hex (1-2 bytes, as in paths) are never asked: hundreds of nodes
share them.

    analyzer_names   prefix, name, role, public_key, looked_at (name '' = not found / not unique)
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

RECHECK_S = 7 * 86400
MAX_PER_HOUR = 20
MIN_HEX = 6
LOOKBACK_S = 7 * 86400


def ensure(conn: Any) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS analyzer_names (
        prefix TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', role TEXT, public_key TEXT, looked_at INTEGER NOT NULL)""")


def _table(conn: Any, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def wanted(conn: Any, now: Optional[float] = None, limit: int = MAX_PER_HOUR) -> list:
    """Neighbour prefixes (last week) without a name from meshcore-ha or the Contacts, not asked recently."""
    now = time.time() if now is None else now
    ensure(conn)
    if not _table(conn, "ha_repeater_neighbors"):
        return []
    rows = conn.execute("SELECT DISTINCT lower(neighbor_prefix) FROM ha_repeater_neighbors WHERE recorded_at >= ? "
                        "AND COALESCE(neighbor_name, '') = ''", (int(now - LOOKBACK_S),)).fetchall()
    have_contacts = _table(conn, "complete_contact_tracking")
    out = []
    for (p,) in rows:
        p = str(p or "")
        if len(p) < MIN_HEX or not re.fullmatch(r"[0-9a-f]+", p):
            continue
        last = conn.execute("SELECT looked_at FROM analyzer_names WHERE prefix = ?", (p,)).fetchone()
        if last and now - last[0] < RECHECK_S:
            continue
        if have_contacts and conn.execute("SELECT 1 FROM complete_contact_tracking WHERE lower(public_key) LIKE ? "
                                          "AND COALESCE(name, '') != '' LIMIT 1", (p + "%",)).fetchone():
            continue
        out.append(p)
        if len(out) >= limit:
            break
    return out


def store(conn: Any, prefix: str, answer: Any, now: Optional[float] = None) -> str:
    """Keep the analyzer's answer for one prefix; returns the name ('' when not found or not unique)."""
    now = time.time() if now is None else now
    ensure(conn)
    name = role = key = ""
    cands = (answer or {}).get("candidates") or [] if isinstance(answer, dict) else []
    if len(cands) == 1 and isinstance(cands[0], dict):
        c = cands[0]
        name = str(c.get("name") or "")[:40]
        role = str(c.get("role") or "")[:20]
        key = str(c.get("id") or "").lower()[:64]
        if key and not key.startswith(prefix.lower()):
            name = role = key = ""
    conn.execute("INSERT INTO analyzer_names (prefix, name, role, public_key, looked_at) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(prefix) DO UPDATE SET name = excluded.name, role = excluded.role, public_key = excluded.public_key, "
                 "looked_at = excluded.looked_at", (prefix.lower(), name, role, key, int(now)))
    conn.commit()
    return name


def names_for(conn: Any, prefixes: list) -> dict:
    """{prefix: name} for the prefixes the analyzer could name."""
    if not prefixes or not _table(conn, "analyzer_names"):
        return {}
    out = {}
    for p in prefixes:
        row = conn.execute("SELECT name FROM analyzer_names WHERE prefix = ? AND name != ''", (str(p).lower(),)).fetchone()
        if row:
            out[str(p).lower()] = row[0]
    return out


def asked_this_hour(conn: Any, now: Optional[float] = None) -> int:
    now = time.time() if now is None else now
    ensure(conn)
    return conn.execute("SELECT COUNT(*) FROM analyzer_names WHERE looked_at >= ?", (int(now - 3600),)).fetchone()[0]
