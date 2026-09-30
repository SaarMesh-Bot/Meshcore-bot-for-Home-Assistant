"""The radio's own statistics, read with local commands (no airtime): noise floor, last RSSI/SNR, transmit and receive
airtime as % of the radio's uptime, battery and packet counters. Used by the bot network (status) and the HA sensors."""
from __future__ import annotations

import asyncio
from typing import Any


async def _command(bot: Any, name: str) -> dict:
    commands = getattr(getattr(bot, "meshcore", None), "commands", None)
    fn = getattr(commands, name, None)
    if fn is None:
        return {}
    try:
        result = await asyncio.wait_for(fn(), timeout=10)
        payload = getattr(result, "payload", None)
        return payload if isinstance(payload, dict) and "error" not in str(getattr(result, "type", "")).lower() else {}
    except Exception:  # noqa: BLE001 - an older firmware without the command: just leave it out
        return {}


async def radio_stats(bot: Any) -> dict:
    """{nf, rssi, snr, bat, rup, err, rcv, snt, ftx, dtx, frx, drx, txa, rxa}; missing values are left out."""
    core, radio, packets = await _command(bot, "get_stats_core"), await _command(bot, "get_stats_radio"), await _command(bot, "get_stats_packets")
    out: dict = {}
    up = core.get("uptime_secs") or 0
    for key, src in (("nf", radio.get("noise_floor")), ("rssi", radio.get("last_rssi")), ("snr", radio.get("last_snr")),
                     ("bat", core.get("battery_mv")), ("rup", up or None), ("err", core.get("errors")),
                     ("rcv", packets.get("recv")), ("snt", packets.get("sent")), ("ftx", packets.get("flood_tx")),
                     ("dtx", packets.get("direct_tx")), ("frx", packets.get("flood_rx")), ("drx", packets.get("direct_rx"))):
        if src is not None:
            out[key] = src
    if up and radio.get("tx_air_secs") is not None:
        out["txa"] = round(100.0 * radio["tx_air_secs"] / up, 2)
    if up and radio.get("rx_air_secs") is not None:
        out["rxa"] = round(100.0 * radio["rx_air_secs"] / up, 2)
    return out
