"""Who answers? When several bots of this add-on hear the same command in a channel, only the one closest to the
person who asked answers (fewest hops, then the best signal; the bot id breaks a tie). Saves airtime.

How: a bot that is about to answer a command from the card's list (information commands every bot answers the same,
never games that keep their own state) sends a short claim over the bot network (MQTT, kind "C", not retained):
the message's id, its hops and SNR. It then waits WAIT_S seconds for the claims of other bots and answers only when
its own claim is the best. Without a connection to the broker, or when no other network bot was online in the last
two hours, it answers at once, as before. A claim is only taken from a bot whose name and key the network already knows
(signed, like every bot-network message). Nothing of this goes over the radio.
"""
from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from typing import Any, Optional

WAIT_S = 2.0
WINDOW_S = 20        # claims further apart than this are about another message (someone asking again later)
KEEP_S = 120
DEFAULT_COMMANDS = ["test", "t", "ping", "path", "pad", "sig", "trace", "tracer", "tracert", "discover", "wx", "weer",
                    "help", "hello", "version", "stats", "sun", "moon", "aqi", "rain"]

_lock = threading.Lock()
_claims: dict = {}   # message id -> [(bot_id, hops, snr, received_at)]


def message_id(channel: Optional[str], sender: Optional[str], content: Optional[str]) -> str:
    raw = f"{(channel or '').strip().lower()}|{(sender or '').strip()}|{(content or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def add_claim(mid: str, bot: str, hops: Any, snr: Any, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    try:
        hops = int(hops) if hops is not None else None
    except (TypeError, ValueError):
        hops = None
    try:
        snr = float(snr) if snr is not None else None
    except (TypeError, ValueError):
        snr = None
    with _lock:
        for k in [k for k, v in _claims.items() if all(now - c[3] > KEEP_S for c in v)]:
            del _claims[k]
        _claims.setdefault(str(mid)[:16], []).append((str(bot)[:40], hops, snr, now))


def rank(hops: Optional[int], snr: Optional[float], bot: str) -> tuple:
    return (99 if hops is None else hops, -(-99.0 if snr is None else snr), bot)


def winner(mid: str, me: str, my_hops: Optional[int], my_snr: Optional[float], now: Optional[float] = None) -> tuple:
    """(i_answer, best_bot, best_hops) from the claims around now."""
    now = time.time() if now is None else now
    with _lock:
        others = [c for c in _claims.get(mid, []) if c[0] != me and abs(now - c[3]) <= WINDOW_S]
    best = (me, my_hops, my_snr)
    for bot, hops, snr, _t in others:
        if rank(hops, snr, bot) < rank(best[1], best[2], best[0]):
            best = (bot, hops, snr)
    return best[0] == me, best[0], best[1]


def _settings(bot: Any) -> tuple:
    cfg = bot.config
    if not cfg.has_section("BotNetwork") or not cfg.getboolean("BotNetwork", "enabled", fallback=False):
        return False, []
    on = cfg.getboolean("BotNetwork", "answer_once", fallback=True)
    raw = cfg.get("BotNetwork", "answer_commands", fallback="") or ""
    names = [n.strip().lower() for n in raw.strip("[]").replace("'", "").split(",") if n.strip()] or DEFAULT_COMMANDS
    return on, names


def _peers_online(bot: Any, now: float) -> bool:
    """Another bot of the network seen over the internet in the last two hours."""
    try:
        with bot.db_manager.connection() as conn:
            row = conn.execute("SELECT COUNT(*) FROM botnet_peers WHERE via != 'self' AND last_seen >= ?",
                               (int(now - 7200),)).fetchone()
        return bool(row and row[0])
    except Exception:  # noqa: BLE001 - no table yet
        return False


async def should_answer(bot: Any, message: Any, command_name: str, now: Optional[float] = None) -> bool:
    """False only when another network bot heard this command closer; True in every other case."""
    if getattr(message, "is_dm", False):
        return True
    on, names = _settings(bot)
    if not on or (command_name or "").lower() not in names:
        return True
    services = getattr(bot, "services", None) or {}
    svc = services.get("botnetwork") if isinstance(services, dict) else None
    if svc is None or not getattr(svc, "mqtt_connected", False) or not hasattr(svc, "publish_claim"):
        return True
    now = time.time() if now is None else now
    if not _peers_online(bot, now):
        return True
    mid = message_id(message.channel, message.sender_id, message.content)
    me = svc.own_id()
    hops, snr = getattr(message, "hops", None), getattr(message, "snr", None)
    add_claim(mid, me, hops, snr, now)
    if not svc.publish_claim(mid, hops, snr):
        return True
    await asyncio.sleep(WAIT_S)
    mine, best, best_hops = winner(mid, me, hops, snr)
    if not mine:
        bot.logger.info(f"Botnetwerk: {best} hoorde {message.sender_id} dichterbij ({best_hops} hops), ik antwoord niet op {command_name}")
    return mine
