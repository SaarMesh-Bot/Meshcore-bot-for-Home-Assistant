"""The ping reply: Pong with what the bot knows about how the message reached it.

    Pong @[Jan]! 3 hops via NL-ABC-Repeater · SNR 6.5 dB · RSSI -92 dBm · 1.2s onderweg · 07:01

Every part is left out when it is unknown (no SNR, a sender clock that is off, a repeater prefix several repeaters
share). "via" names the last repeater on the path, the one the bot heard the message from, looked up in the bot's
contacts; only an unambiguous match (one repeater or room server with that key prefix) is used. A [Keywords] ping
in the config still wins over all of this (patch_ping_default.py).
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

SEP = " · "


def last_hop(message: Any) -> str:
    """Key prefix (hex) of the last repeater on the path, '' when direct or unknown."""
    ri = getattr(message, "routing_info", None) or {}
    nodes = ri.get("path_nodes") or []
    if nodes:
        return str(nodes[-1]).lower()
    path = str(getattr(message, "path", "") or "").split(" via ROUTE_TYPE_")[0]
    path = re.sub(r"\s*\([^)]*\)", "", path).strip()
    if not path or "direct" in path.lower():
        return ""
    last = path.split(",")[-1].strip().lower()
    return last if re.fullmatch(r"[0-9a-f]{2,}", last or "") else ""


def repeater_name(conn: Any, prefix: str) -> str:
    """The name of the one repeater/room server whose key starts with prefix, '' when none or several."""
    if not prefix or conn is None:
        return ""
    try:
        rows = conn.execute("SELECT DISTINCT name FROM complete_contact_tracking WHERE lower(public_key) LIKE ? "
                            "AND LOWER(role) IN ('repeater', 'roomserver') AND COALESCE(name, '') != ''",
                            (prefix.lower() + "%",)).fetchall()
    except Exception:  # noqa: BLE001 - no table yet
        return ""
    return str(rows[0][0])[:30] if len(rows) == 1 else ""


def _num(v: Any) -> Optional[str]:
    if v is None or v == "" or str(v).lower() == "unknown":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return str(int(f)) if f == int(f) else f"{f:.1f}"


def info(t: Callable[..., str], hops: Optional[int], via: str, snr: Any, rssi: Any, elapsed: str, time: str) -> str:
    """The part after "Pong!": hops (and via), SNR, RSSI, travel time, bot time; unknown parts left out."""
    parts = []
    if hops is not None:
        h = t("commands.ping.direct") if hops == 0 else (t("commands.ping.hop_one") if hops == 1 else t("commands.ping.hops", n=hops))
        if via and hops > 0:
            h += " " + t("commands.ping.via", name=via)
        parts.append(h)
    s, r = _num(snr), _num(rssi)
    if s is not None:
        parts.append(f"SNR {s} dB")
    if r is not None:
        parts.append(f"RSSI {r} dBm")
    if elapsed and re.fullmatch(r"[\d.]+m?s", elapsed):
        parts.append(t("commands.ping.travel", elapsed=elapsed))
    if time and time != "Unknown":
        parts.append(time)
    return SEP.join(parts)


def reply(cmd: Any, message: Any) -> str:
    """The full ping reply for a command object (BaseCommand) and the message."""
    from .utils import message_hop_count
    hops = message_hop_count(message)
    via = ""
    if hops:
        try:
            with cmd.bot.db_manager.connection() as conn:
                via = repeater_name(conn, last_hop(message))
        except Exception:  # noqa: BLE001
            via = ""
    try:
        elapsed = cmd.format_elapsed(message)
    except Exception:  # noqa: BLE001
        elapsed = ""
    time = cmd.format_timestamp(message)
    time = time[:5] if re.fullmatch(r"\d\d:\d\d:\d\d", time or "") else time
    text = info(cmd.translate, hops, via, getattr(message, "snr", None), getattr(message, "rssi", None), elapsed, time)
    return cmd.translate("commands.ping.response_full", sender=getattr(message, "sender_id", None) or "?", info=text).rstrip(" ·")
