"""Problems at a glance (dashboard: Settings -> Problems).

Two sources:
- the bot's own WARNING and ERROR log lines, kept in the table `bot_problems` per day and per kind (numbers, names in
  quotes and hex keys are replaced, so "Contact list at 99.7% capacity (349/350)" and "... (348/350)" are one kind),
  14 days;
- commands the bot recognised but did not answer (packet_stream, type 'command', success false), with the input, the
  channel and the time.

The ProblemLog service installs the log handler (card ProblemLog, on). The web viewer only reads. Nothing is sent
over the radio.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from typing import Any, Optional

KEEP_DAYS = 14
MAX_EXAMPLE = 300
TABLE = """CREATE TABLE IF NOT EXISTS bot_problems (
    day TEXT NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL, example TEXT, count INTEGER NOT NULL DEFAULT 0,
    first_ts INTEGER, last_ts INTEGER, PRIMARY KEY (day, level, kind))"""

_HEX = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_QUOTED = re.compile(r"'[^']{1,80}'|\"[^\"]{1,80}\"")
_BRACKET = re.compile(r"\[[^\]]{1,200}\]")


def kind_of(message: str) -> str:
    """The message with the variable parts replaced, so repeats of the same problem count as one kind."""
    text = (message or "").strip().splitlines()[0] if (message or "").strip() else ""
    text = _HEX.sub("#", text)
    text = _QUOTED.sub("'…'", text)
    text = _BRACKET.sub("[…]", text)
    text = _NUM.sub("N", text)
    return text[:160]


class ProblemHandler(logging.Handler):
    """Writes WARNING and ERROR records into bot_problems (own short sqlite connection; never raises)."""

    def __init__(self, db_path: str):
        super().__init__(level=logging.WARNING)
        self.db_path = db_path
        self._lock = threading.Lock()
        self._ready = False
        self._busy = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._busy, "on", False):
            return
        self._busy.on = True
        try:
            message = record.getMessage()
            if message.startswith("Web viewer stderr:"):
                return   # request lines of the dashboard, not problems
            now = int(record.created)
            day = time.strftime("%Y-%m-%d", time.localtime(now))
            example = message.strip()[:MAX_EXAMPLE]
            if record.exc_info and record.exc_info[1] is not None:
                example = f"{example} ({type(record.exc_info[1]).__name__}: {record.exc_info[1]})"[:MAX_EXAMPLE]
            with self._lock:
                conn = sqlite3.connect(self.db_path, timeout=5)
                try:
                    if not self._ready:
                        conn.execute(TABLE)
                        conn.execute("DELETE FROM bot_problems WHERE day < date('now', ?)", (f"-{KEEP_DAYS} day",))
                        self._ready = True
                    conn.execute(
                        "INSERT INTO bot_problems (day, level, kind, example, count, first_ts, last_ts) VALUES (?,?,?,?,1,?,?) "
                        "ON CONFLICT(day, level, kind) DO UPDATE SET count = count + 1, example = excluded.example, "
                        "last_ts = excluded.last_ts",
                        (day, record.levelname, kind_of(message), example, now, now))
                    conn.commit()
                finally:
                    conn.close()
        except Exception:  # noqa: BLE001 - a log handler must never break the bot
            pass
        finally:
            self._busy.on = False


def install(logger: logging.Logger, db_path: str) -> Optional[ProblemHandler]:
    """Add the handler once (a reload does not add a second one)."""
    for h in logger.handlers:
        if isinstance(h, ProblemHandler) or type(h).__name__ == "ProblemHandler":
            return None
    handler = ProblemHandler(db_path)
    logger.addHandler(handler)
    return handler


DISMISSED = "CREATE TABLE IF NOT EXISTS problem_dismissed (key TEXT PRIMARY KEY, ts INTEGER)"


def command_key(c: dict) -> str:
    return f"c|{c.get('timestamp')}|{c.get('command')}|{c.get('user')}"


def dismiss(conn: Any, item: dict) -> bool:
    """'Done' on the dashboard. A warning/error kind: its rows are removed (it comes back when it happens again).
    An unanswered command: remembered as seen. Returns False for an unknown item."""
    conn.execute(DISMISSED)
    if item.get("type") == "problem":
        conn.execute(TABLE)
        n = conn.execute("DELETE FROM bot_problems WHERE level = ? AND kind = ?",
                         (str(item.get("level") or ""), str(item.get("kind") or ""))).rowcount
        conn.commit()
        return n > 0
    if item.get("type") == "command" and item.get("key"):
        conn.execute("INSERT OR REPLACE INTO problem_dismissed (key, ts) VALUES (?, ?)", (str(item["key"])[:200], int(time.time())))
        conn.execute("DELETE FROM problem_dismissed WHERE ts < ?", (int(time.time()) - 30 * 86400,))
        conn.commit()
        return True
    return False


def clear_all(conn: Any, now: Optional[float] = None) -> None:
    """'Clear all': every warning/error gone, every unanswered command up to now seen."""
    now = time.time() if now is None else now
    conn.execute(TABLE)
    conn.execute(DISMISSED)
    conn.execute("DELETE FROM bot_problems")
    conn.execute("INSERT OR REPLACE INTO problem_dismissed (key, ts) VALUES ('cleared_at', ?)", (int(now),))
    conn.commit()


def _table(conn: Any, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def summary(conn: Any, days: int = 1, now: Optional[float] = None) -> dict:
    """What the Problems page shows: log problems grouped per kind, and unanswered commands."""
    now = time.time() if now is None else now
    days = max(1, min(KEEP_DAYS, int(days)))
    since_day = time.strftime("%Y-%m-%d", time.localtime(now - (days - 1) * 86400))
    problems = []
    if _table(conn, "bot_problems"):
        for level, kind, example, count, first_ts, last_ts, n_days in conn.execute(
                "SELECT level, kind, MAX(example), SUM(count), MIN(first_ts), MAX(last_ts), COUNT(DISTINCT day) FROM bot_problems "
                "WHERE day >= ? GROUP BY level, kind ORDER BY (level = 'ERROR') DESC, SUM(count) DESC LIMIT 200", (since_day,)):
            problems.append({"level": level, "kind": kind, "example": example, "count": count, "first": first_ts,
                             "last": last_ts, "days": n_days})
    commands, unanswered, per_command = 0, [], {}
    seen, cleared_at = set(), 0
    if _table(conn, "problem_dismissed"):
        for k, ts in conn.execute("SELECT key, ts FROM problem_dismissed"):
            if k == "cleared_at":
                cleared_at = int(ts or 0)
            else:
                seen.add(k)
    if _table(conn, "packet_stream"):
        for (data,) in conn.execute("SELECT data FROM packet_stream WHERE type = 'command' AND timestamp > ? ORDER BY timestamp DESC "
                                    "LIMIT 5000", (now - days * 86400,)):
            try:
                c = json.loads(data)
            except (TypeError, ValueError):
                continue
            commands += 1
            name = str(c.get("command") or "?")
            stat = per_command.setdefault(name, {"command": name, "asked": 0, "unanswered": 0, "unconfirmed": 0})
            stat["asked"] += 1
            if c.get("success") is False and command_key(c) not in seen and not (cleared_at and float(c.get("timestamp") or 0) <= cleared_at):
                response = str(c.get("response") or "").strip()
                channel = c.get("channel") or "DM"
                # A DM reply that was sent but whose ACK never came back: the text went out, it may well have arrived
                # (long flood routes often lose the confirmation). Not the same as no answer at all.
                unconfirmed = channel == "DM" and bool(response) and response != "Command executed"
                stat["unconfirmed" if unconfirmed else "unanswered"] += 1
                if len(unanswered) < 100:
                    unanswered.append({"command": name, "input": str(c.get("user_input") or "")[:120],
                                       "user": str(c.get("user") or "")[:40], "channel": channel,
                                       "time": c.get("timestamp"), "response": response[:160],
                                       "kind": "unconfirmed" if unconfirmed else "unanswered", "key": command_key(c)})
    failing = sorted((s for s in per_command.values() if s["unanswered"] or s["unconfirmed"]),
                     key=lambda s: -(s["unanswered"] * 10 + s["unconfirmed"]))
    return {
        "days": days,
        "errors": sum(p["count"] for p in problems if p["level"] == "ERROR"),
        "warnings": sum(p["count"] for p in problems if p["level"] != "ERROR"),
        "commands": commands,
        "unanswered_total": sum(s["unanswered"] for s in per_command.values()),
        "unconfirmed_total": sum(s["unconfirmed"] for s in per_command.values()),
        "problems": problems,
        "unanswered": unanswered,
        "failing_commands": failing[:30],
    }
