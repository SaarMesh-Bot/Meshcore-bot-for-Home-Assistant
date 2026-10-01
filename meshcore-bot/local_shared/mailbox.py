"""Mailbox ("post"): a message for someone who is not around. The bot keeps it and sends it by DM as soon as it hears
that person again (a message in a channel or to the bot, or an advert).

Table `mailbox` in the bot's database. Limits: MAX_TEXT characters, MAX_PENDING waiting messages per sender and
MAX_PER_RECIPIENT per recipient, KEEP_DAYS days; then the message expires. The recipient is found by name (a channel
message carries only a name); the DM needs that person on the radio's contact list, otherwise the bot keeps trying
until the message expires. The command is local_commands/post_command.py, the delivery local_service_plugins/
mailbox_service.py.
"""
from __future__ import annotations

import time
from typing import Any, Optional

MAX_TEXT = 100
MAX_PENDING = 3
MAX_PER_RECIPIENT = 10
KEEP_DAYS = 7

SCHEMA = """CREATE TABLE IF NOT EXISTS mailbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT, to_name TEXT NOT NULL, from_name TEXT NOT NULL, from_key TEXT,
    text TEXT NOT NULL, via TEXT, created INTEGER NOT NULL, delivered INTEGER, expired INTEGER)"""


def ensure(conn: Any) -> None:
    conn.execute(SCHEMA)


def _pending(conn: Any, now: float) -> str:
    return f"delivered IS NULL AND expired IS NULL AND created >= {int(now - KEEP_DAYS * 86400)}"


def add(db: Any, from_name: str, from_key: Optional[str], to_name: str, text: str, via: str,
        now: Optional[float] = None) -> tuple:
    """('ok', id) or (reason, None): 'empty', 'self', 'too_many', 'full'."""
    now = time.time() if now is None else now
    to_name, text = (to_name or "").strip()[:40], (text or "").strip()[:MAX_TEXT]
    if not to_name or not text:
        return "empty", None
    if to_name.lower() == (from_name or "").strip().lower():
        return "self", None
    with db.connection() as conn:
        ensure(conn)
        who = "from_key = ?" if from_key else "LOWER(from_name) = LOWER(?)"
        mine = conn.execute(f"SELECT COUNT(*) FROM mailbox WHERE {who} AND {_pending(conn, now)}",
                            (from_key or from_name,)).fetchone()[0]
        if mine >= MAX_PENDING:
            return "too_many", None
        theirs = conn.execute(f"SELECT COUNT(*) FROM mailbox WHERE LOWER(to_name) = LOWER(?) AND {_pending(conn, now)}",
                              (to_name,)).fetchone()[0]
        if theirs >= MAX_PER_RECIPIENT:
            return "full", None
        cur = conn.execute("INSERT INTO mailbox (to_name, from_name, from_key, text, via, created) VALUES (?,?,?,?,?,?)",
                           (to_name, (from_name or "?")[:40], from_key, text, via, int(now)))
        conn.commit()
        return "ok", cur.lastrowid


def waiting_from(db: Any, from_name: str, from_key: Optional[str], now: Optional[float] = None) -> list:
    """[(to_name, created)] of the sender's messages that are still waiting."""
    now = time.time() if now is None else now
    with db.connection() as conn:
        ensure(conn)
        who = "from_key = ?" if from_key else "LOWER(from_name) = LOWER(?)"
        return conn.execute(f"SELECT to_name, created FROM mailbox WHERE {who} AND {_pending(conn, now)} ORDER BY created",
                            (from_key or from_name,)).fetchall()


def _heard_since(conn: Any, name: str) -> int:
    """Last time the bot heard this name: a message (message_stats) or an advert (complete_contact_tracking)."""
    best = 0
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "message_stats" in tables:
        row = conn.execute("SELECT MAX(timestamp) FROM message_stats WHERE LOWER(sender_id) = LOWER(?)", (name,)).fetchone()
        best = max(best, int(row[0] or 0))
    if "complete_contact_tracking" in tables:
        row = conn.execute("SELECT MAX(CAST(strftime('%s', last_heard) AS INTEGER)) FROM complete_contact_tracking "
                           "WHERE LOWER(name) = LOWER(?) AND LOWER(role) != 'repeater'", (name,)).fetchone()
        best = max(best, int(row[0] or 0))
    return best


def due(db: Any, now: Optional[float] = None) -> list:
    """Messages whose recipient was heard after the message was left: [{id, to_name, from_name, text, via, created}].
    Expires what is older than KEEP_DAYS on the way."""
    now = time.time() if now is None else now
    out = []
    with db.connection() as conn:
        ensure(conn)
        conn.execute("UPDATE mailbox SET expired = ? WHERE delivered IS NULL AND expired IS NULL AND created < ?",
                     (int(now), int(now - KEEP_DAYS * 86400)))
        rows = conn.execute(f"SELECT id, to_name, from_name, text, via, created FROM mailbox WHERE {_pending(conn, now)} "
                            "ORDER BY created").fetchall()
        heard: dict = {}
        for mid, to_name, from_name, text, via, created in rows:
            key = to_name.lower()
            if key not in heard:
                heard[key] = _heard_since(conn, to_name)
            if heard[key] > created:
                out.append({"id": mid, "to_name": to_name, "from_name": from_name, "text": text, "via": via, "created": created})
        conn.commit()
    return out


def delivered(db: Any, mid: int, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    with db.connection() as conn:
        conn.execute("UPDATE mailbox SET delivered = ? WHERE id = ?", (int(now), int(mid)))
        conn.commit()


def ago(created: int, translate, now: Optional[float] = None) -> str:
    now = time.time() if now is None else now
    s = max(0, int(now - created))
    if s < 3600:
        return translate("commands.post.ago_min", n=max(1, s // 60))
    if s < 86400:
        return translate("commands.post.ago_h", n=s // 3600)
    return translate("commands.post.ago_d", n=s // 86400)


def split_recipient(args: str) -> tuple:
    """'@[Dirk Jan] hoi' / '"Dirk Jan" hoi' / 'Bob hoi' -> (name, text)."""
    a = (args or "").strip()
    if a.startswith("@[") and "]" in a:
        name, _, rest = a[2:].partition("]")
        return name.strip(), rest.strip()
    if a[:1] in ('"', "'") and a[0] in a[1:]:
        name, _, rest = a[1:].partition(a[0])
        return name.strip(), rest.strip()
    name, _, rest = a.partition(" ")
    return name.strip().lstrip("@"), rest.strip()


def overview(db: Any, now: Optional[float] = None) -> dict:
    """The dashboard's Mailbox page: every message of the last 30 days with its status. The text of a message left
    by DM is private and not shown (left in a channel it was public already)."""
    now = time.time() if now is None else now
    out = []
    with db.connection() as conn:
        ensure(conn)
        for mid, to_name, from_name, text, via, created, delivered_ts, expired in conn.execute(
                "SELECT id, to_name, from_name, text, via, created, delivered, expired FROM mailbox WHERE created >= ? "
                "ORDER BY created DESC LIMIT 500", (int(now - 30 * 86400),)):
            if delivered_ts:
                status = "delivered"
            elif expired or created < now - KEEP_DAYS * 86400:
                status = "expired"
            else:
                status = "waiting"
            private = (via or "") == "DM"
            out.append({"id": mid, "to": to_name, "from": from_name, "via": via or "?", "created": created,
                        "delivered": delivered_ts, "status": status, "private": private,
                        "text": None if private else text,
                        "expires": created + KEEP_DAYS * 86400 if status == "waiting" else None})
    counts = {s: sum(1 for m in out if m["status"] == s) for s in ("waiting", "delivered", "expired")}
    return {"messages": out, "counts": counts,
            "limits": {"keep_days": KEEP_DAYS, "max_pending": MAX_PENDING, "max_per_recipient": MAX_PER_RECIPIENT, "max_text": MAX_TEXT}}


def remove(db: Any, mid: int) -> bool:
    """Take a message out (dashboard); it will not be delivered."""
    with db.connection() as conn:
        ensure(conn)
        n = conn.execute("DELETE FROM mailbox WHERE id = ?", (int(mid),)).rowcount
        conn.commit()
    return n > 0
