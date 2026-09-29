"""Bot network: bots running this add-on share what their radio hears, over the internet (MQTT), without airtime and
without a distance limit (card: Plugins -> BotNetwork, off by default: every owner chooses).

Each bot connects to the network's MQTT server (fixed in bot_network_service.py: mqtt.vipje.nl, TLS) and publishes, retained,
under <topic>/<bot id>/<kind> (see bot_network_service.py for the schedule):

    H  hello: add-on version                                              (daily)
    I  info: radio settings (frequency, SF, BW, CR), firmware and model of the radio, the radio node's key prefix,
       optional region                                                    (weekly, and at the start)
    S  status, last 24 h: nodes heard (people/repeaters/rooms), new today, people who wrote, channel messages,
       commands answered, most hops today, uptime of the bot, night mode; and from the radio itself: noise floor,
       last RSSI/SNR, transmit and receive airtime (% of its uptime), battery, packet counters (hourly)
    N  neighbours: repeaters the radio hears directly (zero-hop discovery), key prefix + SNR (daily, when found)
    K  hashtag channels in use around the bot (channel radar)             (daily, when changed)
    B  names the owner marked as bots                                     (daily, when changed)

Over the internet anyone can publish under any name, so every message is signed with this bot's own Ed25519 key (made
once, kept in the bot's database). A message with a wrong signature, or in any other form, is ignored; a name stays
bound to the key it first came with, so nobody can pretend to be a bot that is already known. What goes over the broker
is no secret (numbers, bot names, hashtag channel names): never messages, keys or private channels.

This bot's own messages come back from the broker too: they are kept as "self" (only when signed with its own key), so
the Bot network page can show this bot next to the others, but they never count as another bot or as a source of names.

Trust: channel and bot names from others are only used (Channel radar, bot recognition) when they come from a bot on the
card's trusted list, or from at least two bots.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

SECTION = "BotNetwork"
CACHE_S = 60
_cache: dict = {"at": 0.0, "bots": set(), "channels": set()}

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS botnet_peers (
        name TEXT PRIMARY KEY, version TEXT, radio TEXT, region TEXT, status TEXT,
        first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL, last_hello INTEGER, last_status INTEGER, messages INTEGER NOT NULL DEFAULT 0,
        via TEXT, pubkey TEXT)""",
    """CREATE TABLE IF NOT EXISTS botnet_names (
        kind TEXT NOT NULL, value TEXT NOT NULL, from_name TEXT NOT NULL, ts INTEGER NOT NULL,
        PRIMARY KEY (kind, value, from_name))""",
    """CREATE TABLE IF NOT EXISTS botnet_links (
        from_name TEXT NOT NULL, neighbor TEXT NOT NULL, snr REAL, best_snr REAL, seen INTEGER, ts INTEGER NOT NULL,
        PRIMARY KEY (from_name, neighbor))""",
    # every status message (S), for the charts on the Bot network page; kept HISTORY_DAYS days
    """CREATE TABLE IF NOT EXISTS botnet_status_log (
        name TEXT NOT NULL, ts INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY (name, ts))""",
    "CREATE INDEX IF NOT EXISTS idx_botnet_status_log_ts ON botnet_status_log (ts)",
]
HISTORY_DAYS = 31
MAX_POINTS = 400


def ensure_tables(db: Any) -> None:
    with db.connection() as conn:
        for statement in SCHEMA:
            conn.execute(statement)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(botnet_peers)").fetchall()}
        for col in ("via", "pubkey", "info"):   # via/pubkey added in 2.21.0 (internet), info in 2.22.0
            if col not in cols:
                conn.execute(f"ALTER TABLE botnet_peers ADD COLUMN {col} TEXT")
        conn.commit()


def _norm(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def enabled(bot: Any) -> bool:
    cfg = bot.config
    return cfg.has_section(SECTION) and cfg.getboolean(SECTION, "enabled", fallback=False)


def trusted(bot: Any) -> set:
    raw = bot.config.get(SECTION, "trusted", fallback="") if bot.config.has_section(SECTION) else ""
    return {_norm(n) for n in str(raw).split(",") if n.strip()}


# ---------------------------------------------------------------------------------------------------- what we send
def hello_fields(bot: Any, version: str) -> dict:
    return {"v": version}


def info_fields(bot: Any) -> dict:
    info = getattr(getattr(bot, "meshcore", None), "self_info", None) or {}
    info = info if isinstance(info, dict) else {}
    region = (bot.config.get(SECTION, "region", fallback="") or "").strip().replace(" ", "")[:12]
    return {"f": info.get("radio_freq"), "sf": info.get("radio_sf"), "bw": info.get("radio_bw"), "r": region}


def status_fields(bot: Any, now: Optional[float] = None, started_at: Optional[float] = None) -> dict:
    now = time.time() if now is None else now
    day_ago = int(now - 86400)
    out: dict = {}
    try:
        from .mesh_community import day_start_ts, local_day, table_exists
        from .night_mode import is_night
        today_start = day_start_ts(bot, local_day(bot, now))
        with bot.db_manager.connection() as conn:
            if table_exists(conn, "complete_contact_tracking"):
                roles = dict(conn.execute("SELECT LOWER(role), COUNT(DISTINCT public_key) FROM complete_contact_tracking "
                                          "WHERE last_heard >= datetime('now', '-1 day') GROUP BY LOWER(role)").fetchall())
                out["n"] = f"{roles.get('companion', 0)}/{roles.get('repeater', 0)}/{roles.get('roomserver', 0)}"
                out["new"] = conn.execute("SELECT COUNT(*) FROM complete_contact_tracking WHERE first_heard >= datetime('now', 'start of day')").fetchone()[0]
            if table_exists(conn, "message_stats"):
                out["p"] = conn.execute("SELECT COUNT(DISTINCT sender_id) FROM message_stats WHERE timestamp >= ? AND is_dm = 0", (day_ago,)).fetchone()[0]
                out["m"] = conn.execute("SELECT COUNT(*) FROM message_stats WHERE timestamp >= ? AND is_dm = 0", (day_ago,)).fetchone()[0]
                out["dx"] = conn.execute("SELECT MAX(hops) FROM message_stats WHERE timestamp >= ? AND hops IS NOT NULL",
                                         (today_start,)).fetchone()[0] or 0
            if table_exists(conn, "command_stats"):
                out["c"] = conn.execute("SELECT COUNT(*) FROM command_stats WHERE timestamp >= ?", (day_ago,)).fetchone()[0]
        if started_at:
            out["up"] = int(now - started_at)
        out["nm"] = 1 if is_night(bot, now) else 0
    except Exception:  # noqa: BLE001 - send what we have
        pass
    return out


def radar_channels(bot: Any) -> list:
    """Hashtag channels the radar recognised in the last 7 days (at least 2 messages); never private channels."""
    try:
        from .channel_radar import summary
        rows = summary(bot)["channels"]
    except Exception:  # noqa: BLE001
        return []
    return [r["label"][1:] for r in sorted(rows, key=lambda r: -r["week"]) if r["label"].startswith("#") and r["week"] >= 2]


def marked_bots(bot: Any) -> list:
    try:
        raw = bot.db_manager.get_metadata("bots.marked")
        return [str(n) for n in (json.loads(raw) if raw else [])]
    except Exception:  # noqa: BLE001
        return []


# ---------------------------------------------------------------------------------------------------- what we hear
def store(bot: Any, sender: str, kind: str, data: Any, now: Optional[float] = None, via: str = "internet",
          pubkey: str = "", sent_at: Optional[int] = None) -> bool:
    """Keep what another bot reported (via "self": this bot's own message). A name belongs to the key it first came with:
    the same name with another key is refused (someone pretending to be that bot). False = refused. sent_at = the time in
    the message, so a retained status that arrives again is not logged twice."""
    now = int(time.time() if now is None else now)
    if via == "self" and kind in ("K", "B"):
        return True   # our own channel and bot names are no evidence from "another" bot
    ensure_tables(bot.db_manager)
    with bot.db_manager.connection() as conn:
        row = conn.execute("SELECT pubkey FROM botnet_peers WHERE name = ?", (sender,)).fetchone()
        if pubkey and row and row[0] and row[0] != pubkey:
            return False
        conn.execute("""INSERT INTO botnet_peers (name, first_seen, last_seen, messages, via, pubkey) VALUES (?,?,?,1,?,?)
                        ON CONFLICT(name) DO UPDATE SET last_seen = excluded.last_seen, messages = messages + 1,
                        via = CASE WHEN botnet_peers.via IS NULL OR botnet_peers.via = excluded.via THEN excluded.via ELSE 'both' END,
                        pubkey = COALESCE(botnet_peers.pubkey, excluded.pubkey)""",
                     (sender, now, now, via, pubkey or None))
        if kind == "H":
            conn.execute("UPDATE botnet_peers SET version = ?, last_hello = ? WHERE name = ?", (str(data.get("v", ""))[:20], now, sender))
        elif kind == "I":
            radio = "/".join(str(data.get(k, "")) for k in ("f", "sf", "bw", "cr") if data.get(k) not in (None, "")) if data.get("f") else ""
            extra = {k: str(v)[:40] for k, v in dict(data).items() if re.fullmatch(r"[a-z]{1,4}", str(k)) and k not in ("f", "sf", "bw", "cr", "r")}
            conn.execute("UPDATE botnet_peers SET radio = ?, region = ?, info = ? WHERE name = ?",
                         (radio[:40], str(data.get("r", ""))[:12], json.dumps(extra), sender))
        elif kind == "N":
            conn.execute("DELETE FROM botnet_links WHERE from_name = ?", (sender,))   # the newest list replaces the old one
            for item in list(data)[:64]:
                if not isinstance(item, dict) or not re.fullmatch(r"[0-9a-f]{8,64}", str(item.get("k", "")).lower()):
                    continue
                def num(v):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None
                seen = num(item.get("t"))
                conn.execute("INSERT OR REPLACE INTO botnet_links (from_name, neighbor, snr, best_snr, seen, ts) VALUES (?,?,?,?,?,?)",
                             (sender, str(item["k"]).lower()[:12], num(item.get("s")), num(item.get("b")), int(seen) if seen else None, now))
        elif kind == "S":
            clean = {k: str(v)[:20] for k, v in dict(data).items() if re.fullmatch(r"[a-z]{1,4}", str(k))}
            conn.execute("UPDATE botnet_peers SET status = ?, last_status = ? WHERE name = ?", (json.dumps(clean), now, sender))
            conn.execute("INSERT OR IGNORE INTO botnet_status_log (name, ts, data) VALUES (?,?,?)",
                         (sender, int(sent_at or now), json.dumps(clean)))
            conn.execute("DELETE FROM botnet_status_log WHERE ts < ?", (now - HISTORY_DAYS * 86400,))
        else:
            what = "channel" if kind == "K" else "bot"
            for value in list(data)[:100]:
                value = _norm(str(value)).lstrip("#")[:40]
                if value:
                    conn.execute("INSERT OR REPLACE INTO botnet_names (kind, value, from_name, ts) VALUES (?,?,?,?)",
                                 (what, value, sender, now))
        conn.commit()
    _cache["at"] = 0.0
    return True


# ---------------------------------------------------------------------------------------------------- signing
KEY_META = "botnet.signing_key"


def signing_key(bot: Any):
    from nacl.signing import SigningKey
    raw = bot.db_manager.get_metadata(KEY_META)
    if raw:
        return SigningKey(bytes.fromhex(raw))
    key = SigningKey.generate()
    bot.db_manager.set_metadata(KEY_META, key.encode().hex())
    return key


def bot_id(pubkey_hex: str) -> str:
    return pubkey_hex[:12]


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def mqtt_message(bot: Any, sender: str, kind: str, data: Any, now: Optional[float] = None) -> tuple:
    """(topic suffix, payload bytes) for one signed message: <bot id>/<kind>."""
    key = signing_key(bot)
    pk = key.verify_key.encode().hex()
    body = {"k": kind, "n": sender, "t": int(time.time() if now is None else now), "d": data, "pk": pk}
    body["sig"] = key.sign(_canonical(body)).signature.hex()
    return f"{bot_id(pk)}/{kind}", _canonical(body)


def receive_mqtt(bot: Any, payload: bytes, own_name: str = "", now: Optional[float] = None) -> Optional[str]:
    """Check and store one message from the broker. Returns the sender's name when kept, else None."""
    try:
        from nacl.signing import VerifyKey
        body = json.loads(payload.decode("utf-8"))
        sig = bytes.fromhex(body.pop("sig"))
        VerifyKey(bytes.fromhex(body["pk"])).verify(_canonical(body), sig)
    except Exception:  # noqa: BLE001 - not ours, not signed, or signed by someone else
        return None
    kind, sender, data = body.get("k"), str(body.get("n") or "").strip()[:40], body.get("d")
    if kind not in ("H", "I", "S", "K", "B", "N") or not sender:
        return None
    if (kind in ("H", "I", "S") and not isinstance(data, dict)) or (kind in ("K", "B", "N") and not isinstance(data, list)):
        return None
    if now is None and abs(time.time() - int(body.get("t") or 0)) > 30 * 86400:
        return None   # very old retained message
    sent_at = int(body.get("t") or 0) or None
    if own_name and _norm(sender) == _norm(own_name):
        # our own message back from the broker: kept as "self" when it is really ours, never returned as another bot
        if body["pk"] == signing_key(bot).verify_key.encode().hex():
            store(bot, sender, kind, data, now, via="self", pubkey=body["pk"], sent_at=sent_at)
        return None
    return sender if store(bot, sender, kind, data, now, via="internet", pubkey=body["pk"], sent_at=sent_at) else None


def _load(bot: Any) -> None:
    now = time.monotonic()
    if now - _cache["at"] < CACHE_S:
        return
    _cache["at"] = now
    bots, channels = set(), set()
    try:
        trust = trusted(bot)
        with bot.db_manager.connection() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='botnet_peers'").fetchone():
                bots |= {_norm(n) for (n,) in conn.execute("SELECT name FROM botnet_peers WHERE COALESCE(via, '') != 'self'").fetchall()}
                for kind, value, sources in conn.execute("SELECT kind, value, GROUP_CONCAT(from_name, '\n') FROM botnet_names GROUP BY kind, value"):
                    names = {_norm(s) for s in (sources or "").split("\n")}
                    if len(names) >= 2 or names & trust:
                        (bots if kind == "bot" else channels).add(value)
    except Exception:  # noqa: BLE001
        pass
    _cache["bots"], _cache["channels"] = bots, channels


def is_network_bot(bot: Any, name: str) -> bool:
    """A name that spoke on the network channel, or that trusted bots (or at least two bots) report as a bot."""
    if not enabled(bot):
        return False
    _load(bot)
    return _norm(name) in _cache["bots"]


def network_channels(bot: Any) -> list:
    """Hashtag channel names reported by trusted bots or by at least two bots (for the Channel radar)."""
    if not enabled(bot):
        return []
    _load(bot)
    return sorted(_cache["channels"])


def summary(bot: Any, now: Optional[float] = None) -> dict:
    """What the Bot network page shows: every bot (this one marked "self"), totals, who hears which repeater, shared names."""
    now = int(time.time() if now is None else now)
    out: dict = {"enabled": enabled(bot), "generated_at": now, "peers": [], "totals": {}, "channels": [], "bots": [], "heard": []}
    if not out["enabled"]:
        return out
    ensure_tables(bot.db_manager)
    trust = trusted(bot)
    with bot.db_manager.connection() as conn:
        links: dict = {}
        for frm, nb, snr, best, seen in conn.execute("SELECT from_name, neighbor, snr, best_snr, seen FROM botnet_links ORDER BY snr DESC"):
            links.setdefault(frm, []).append({"key": nb, "snr": snr, "best_snr": best, "seen": seen})
        try:
            from .repeater_page import contact_info
            names = contact_info(conn, [n["key"] for lst in links.values() for n in lst])
        except Exception:  # noqa: BLE001 - names are a nicety
            names = {}
        for lst in links.values():
            for n in lst:
                c = names.get(n["key"], {})
                n["name"], n["place"] = c.get("name", ""), c.get("place", "")
        for name, version, radio, region, status, first, last, hello, stat, msgs, via, pk, info in conn.execute(
                "SELECT name, version, radio, region, status, first_seen, last_seen, last_hello, last_status, messages, via, pubkey, info "
                "FROM botnet_peers ORDER BY via = 'self' DESC, last_seen DESC").fetchall():
            out["peers"].append({"name": name, "version": version or "", "radio": radio or "", "region": region or "",
                                 "via": via or "radio", "self": via == "self", "id": bot_id(pk) if pk else "",
                                 "info": json.loads(info) if info else {}, "neighbors": links.get(name, []),
                                 "status": json.loads(status) if status else {}, "first_seen": first, "last_seen": last,
                                 "last_hello": hello, "last_status": stat, "messages": msgs, "trusted": _norm(name) in trust})
        for kind, value, n in conn.execute("SELECT kind, value, COUNT(DISTINCT from_name) FROM botnet_names GROUP BY kind, value ORDER BY 3 DESC, 2"):
            (out["channels"] if kind == "channel" else out["bots"]).append({"name": value, "reported_by": n})
    heard: dict = {}
    for p in out["peers"]:
        for n in p["neighbors"]:
            h = heard.setdefault(n["key"], {"key": n["key"], "name": n["name"], "place": n["place"], "by": []})
            h["by"].append({"bot": p["name"], "snr": n["snr"], "seen": n["seen"]})
    out["heard"] = sorted(heard.values(), key=lambda h: (-len(h["by"]), -max((b["snr"] or -99) for b in h["by"])))
    fresh = [p["status"] for p in out["peers"] if p["last_status"] and now - p["last_status"] < 2 * 86400]
    for key in ("p", "m", "c", "new"):
        out["totals"][key] = sum(int(s.get(key, 0) or 0) for s in fresh if str(s.get(key, "")).isdigit())
    out["totals"]["bots"] = sum(1 for p in out["peers"] if not p["self"])
    out["totals"]["online"] = sum(1 for p in out["peers"] if now - (p["last_seen"] or 0) < 2 * 3600)
    return out


HISTORY_FIELDS = ("nf", "txa", "rxa", "m", "p", "c")


def _number(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def history(bot: Any, days: Any = 7, now: Optional[float] = None) -> dict:
    """Status numbers of every bot over 1, 7 or 30 days, for the charts: {bots: [{name, self, t: [...], nf: [...], ...}]}."""
    now = int(time.time() if now is None else now)
    days = int(days) if str(days) in ("1", "7", "30") else 7
    out: dict = {"enabled": enabled(bot), "generated_at": now, "days": days, "bots": []}
    if not out["enabled"]:
        return out
    ensure_tables(bot.db_manager)
    with bot.db_manager.connection() as conn:
        mine = {n for (n,) in conn.execute("SELECT name FROM botnet_peers WHERE via = 'self'")}
        rows = conn.execute("SELECT name, ts, data FROM botnet_status_log WHERE ts >= ? ORDER BY name, ts",
                            (now - days * 86400,)).fetchall()
    per: dict = {}
    for name, ts, data in rows:
        per.setdefault(name, []).append((ts, data))
    for name, items in sorted(per.items(), key=lambda kv: (kv[0] not in mine, kv[0].lower())):
        if len(items) > MAX_POINTS:
            step = len(items) / MAX_POINTS
            items = [items[int(i * step)] for i in range(MAX_POINTS - 1)] + [items[-1]]
        series: dict = {"name": name, "self": name in mine, "t": []}
        for key in HISTORY_FIELDS:
            series[key] = []
        for ts, data in items:
            try:
                d = json.loads(data)
            except ValueError:
                continue
            series["t"].append(ts)
            for key in HISTORY_FIELDS:
                series[key].append(_number(d.get(key)))
        out["bots"].append(series)
    return out
