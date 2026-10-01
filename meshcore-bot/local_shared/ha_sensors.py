"""The bot's numbers as Home Assistant sensors (card: Plugins -> HASensors, on by default).

Every few minutes the bot writes a handful of sensor states through Home Assistant's REST API (the add-on has
homeassistant_api), the same way as the heartbeat: people and messages in the last 24 hours, commands answered, nodes
heard by kind, new nodes today, most hops today, direct neighbours, the radio's noise floor and airtime, map uploads
and the Farming Idle's richest farmer. They can go on a Home Assistant dashboard and into automations. Nothing is sent over
the radio; the radio numbers come from local commands.

States written this way live in Home Assistant until it restarts; the bot writes them again within minutes.
"""
from __future__ import annotations

import time
from typing import Any, Optional

PREFIX = "sensor.meshcore_bot_"


def _count(unit: str, value: Any, name: str, icon: str, **attrs) -> dict:
    return {"state": value, "attributes": {"friendly_name": name, "icon": icon, "unit_of_measurement": unit,
                                          "state_class": "measurement", **attrs}}


def collect(bot: Any, radio: Optional[dict] = None, now: Optional[float] = None) -> dict:
    """{object id: {state, attributes}} for every sensor that has a value; `radio` = modules.radio_stats output."""
    now = time.time() if now is None else now
    out: dict = {}
    try:
        from .bot_network import status_fields
        s = status_fields(bot, now)
    except Exception:  # noqa: BLE001
        s = {}
    if "n" in s:
        people, repeaters, rooms = (int(x) for x in str(s["n"]).split("/"))
        out["people_heard"] = _count("people", people, "MeshCore people heard (24 h)", "mdi:account-group")
        out["repeaters_heard"] = _count("repeaters", repeaters, "MeshCore repeaters heard (24 h)", "mdi:radio-tower")
        out["rooms_heard"] = _count("rooms", rooms, "MeshCore room servers heard (24 h)", "mdi:forum")
    if "new" in s:
        out["new_nodes_today"] = _count("nodes", s["new"], "MeshCore new nodes today", "mdi:new-box")
    if "p" in s:
        out["people_wrote"] = _count("people", s["p"], "MeshCore people who wrote (24 h)", "mdi:account-voice")
    if "m" in s:
        out["channel_messages"] = _count("messages", s["m"], "MeshCore channel messages (24 h)", "mdi:message-text")
    if "c" in s:
        out["commands_answered"] = _count("commands", s["c"], "MeshCore commands answered (24 h)", "mdi:robot")
    if "dx" in s:
        out["most_hops_today"] = _count("hops", s["dx"], "MeshCore most hops today", "mdi:map-marker-distance")
    try:
        with bot.db_manager.connection() as conn:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_links'").fetchone():
                n = conn.execute("SELECT COUNT(DISTINCT neighbor_public_key) FROM neighbor_links "
                                 "WHERE last_seen >= datetime('now', '-7 day')").fetchone()[0]
                out["direct_neighbours"] = _count("repeaters", n, "MeshCore direct neighbours (7 days)", "mdi:access-point")
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='farm_players'").fetchone():
                players = conn.execute("SELECT COUNT(*) FROM farm_players").fetchone()[0]
                top = conn.execute("SELECT name, coins + bank FROM farm_players ORDER BY coins + bank DESC LIMIT 1").fetchone()
                out["farm_players"] = _count("players", players, "MeshCore Farming Idle players", "mdi:sprout")
                if top:
                    out["farm_richest"] = {"state": top[0] or "?", "attributes": {
                        "friendly_name": "MeshCore Farming Idle richest farmer", "icon": "mdi:trophy", "coins": top[1]}}
    except Exception:  # noqa: BLE001 - a missing table only leaves that sensor out
        pass
    try:
        from .map_upload_stats import totals
        m = totals(bot.db_manager, 1, now)
        if m is not None:
            out["map_uploads_today"] = _count("nodes", m["sent"], "MeshCore map uploads today", "mdi:map-marker-up",
                                              new=m["new"], already_known=m["duplicate"], failed=m["failed"])
    except Exception:  # noqa: BLE001
        pass
    r = radio or {}
    if r.get("nf") is not None:
        out["noise_floor"] = {"state": r["nf"], "attributes": {"friendly_name": "MeshCore radio noise floor", "icon": "mdi:waveform",
                                                              "unit_of_measurement": "dBm", "device_class": "signal_strength",
                                                              "state_class": "measurement"}}
    if r.get("txa") is not None:
        out["airtime_tx"] = _count("%", r["txa"], "MeshCore radio transmit airtime", "mdi:upload-network")
    if r.get("rxa") is not None:
        out["airtime_rx"] = _count("%", r["rxa"], "MeshCore radio receive airtime", "mdi:download-network")
    return out
