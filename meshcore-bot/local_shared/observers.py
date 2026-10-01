"""MQTT observers: packets that other MeshCore radios ("observers", often hubs with repeaters behind them) publish to an
MQTT broker, in the common observer format (meshcoretomqtt / LetsMesh):

    meshcore/{IATA}/{PUBLIC_KEY}/packets   one JSON per packet heard: raw hex, SNR, RSSI, direction, ...
    meshcore/{IATA}/{PUBLIC_KEY}/status    one JSON per observer: online/offline, name, model, firmware, radio

The ObserverFeed service (card ObserverFeed) subscribes to them; this module only parses and stores, so it can be tested
without a broker. What is kept (the bot's own database):

    observer_nodes   per observer: name, IATA, status, model, firmware, radio, first/last seen
    observer_hourly  per observer and hour: packets, adverts, group messages, other, RSSI/SNR sums
    observer_heard   per observer: the nodes whose adverts it heard (name, type, position, count, last seen)

Group messages (GRP_TXT) also go into the bot's packet log, tagged as coming from an observer, so the Channel radar
counts them too; the packet hash is the bot's own (calculate_packet_hash), so a message heard by the radio and by an
observer counts once. Nothing is sent over the radio, and message texts are never decrypted.
"""
from __future__ import annotations

import json
import re
import struct
import time
from typing import Any, Optional

PAYLOAD_TYPES = {0: "REQ", 1: "RESPONSE", 2: "TXT_MSG", 3: "ACK", 4: "ADVERT", 5: "GRP_TXT", 6: "GRP_DATA", 7: "ANON_REQ",
                 8: "PATH", 9: "TRACE", 10: "MULTIPART", 11: "CONTROL", 15: "RAW_CUSTOM"}
ROUTE_TYPES = {0: "TRANSPORT_FLOOD", 1: "FLOOD", 2: "DIRECT", 3: "TRANSPORT_DIRECT"}
NODE_TYPES = {1: "companion", 2: "repeater", 3: "roomserver", 4: "sensor"}
KEEP_DAYS = 30
TOPIC = re.compile(r"^(?P<prefix>.+?)/(?P<iata>[^/]+)/(?P<key>[0-9A-Fa-f]{16,64})/(?P<kind>packets|status)$")

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS observer_nodes (
        key TEXT PRIMARY KEY, name TEXT, iata TEXT, status TEXT, model TEXT, firmware TEXT, radio TEXT,
        first_seen INTEGER, last_seen INTEGER, last_status INTEGER)""",
    """CREATE TABLE IF NOT EXISTS observer_hourly (
        key TEXT NOT NULL, hour INTEGER NOT NULL, packets INTEGER NOT NULL DEFAULT 0, adverts INTEGER NOT NULL DEFAULT 0,
        group_msgs INTEGER NOT NULL DEFAULT 0, other INTEGER NOT NULL DEFAULT 0, rssi_sum REAL NOT NULL DEFAULT 0,
        snr_sum REAL NOT NULL DEFAULT 0, sig_n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (key, hour))""",
    """CREATE TABLE IF NOT EXISTS observer_heard (
        key TEXT NOT NULL, node TEXT NOT NULL, name TEXT, type TEXT, lat REAL, lon REAL, count INTEGER NOT NULL DEFAULT 0,
        last_seen INTEGER, last_snr REAL, hops INTEGER, PRIMARY KEY (key, node))""",
]


def ensure(conn: Any) -> None:
    for s in SCHEMA:
        conn.execute(s)


# ------------------------------------------------------------------------------------------------ decoding
def decode_raw(raw_hex: str) -> Optional[dict]:
    """{route, type, path [hex per hop], hops, payload (bytes)} of a raw MeshCore packet, or None when not valid."""
    try:
        data = bytes.fromhex(str(raw_hex or "").strip())
    except ValueError:
        return None
    if len(data) < 2:
        return None
    header = data[0]
    if (header >> 6) & 0x03 != 0:            # only payload version 1
        return None
    route = header & 0x03
    offset = 1 + (4 if route in (0, 3) else 0)
    if len(data) <= offset:
        return None
    plen = data[offset]
    offset += 1
    per_hop = (plen >> 6) + 1
    hops = plen & 63
    if per_hop == 4 or hops * per_hop > 64 or len(data) < offset + hops * per_hop:
        return None
    path_bytes = data[offset:offset + hops * per_hop]
    payload = data[offset + hops * per_hop:]
    path = [path_bytes[i:i + per_hop].hex() for i in range(0, len(path_bytes), per_hop)]
    ptype = (header >> 2) & 0x0F
    return {"route": ROUTE_TYPES.get(route, str(route)), "type": PAYLOAD_TYPES.get(ptype, f"TYPE{ptype}"), "type_n": ptype,
            "path": path, "hops": hops, "payload": payload}


def parse_advert(payload: bytes) -> Optional[dict]:
    """{key, type, name, lat, lon} of an ADVERT payload (key 32, timestamp 4, signature 64, app data)."""
    if len(payload) < 101:
        return None
    key = payload[:32].hex()
    app = payload[100:]
    flags = app[0]
    pos = 1
    lat = lon = None
    if flags & 0x10 and len(app) >= pos + 8:
        la, lo = struct.unpack("<ii", app[pos:pos + 8])
        lat, lon = la / 1e6, lo / 1e6
        pos += 8
    if flags & 0x20:
        pos += 2
    if flags & 0x40:
        pos += 2
    name = ""
    if flags & 0x80 and len(app) > pos:
        name = app[pos:].split(b"\x00")[0].decode("utf-8", "replace").strip()[:40]
    return {"key": key, "type": NODE_TYPES.get(flags & 0x0F, "unknown"), "name": name,
            "lat": lat if lat not in (None, 0.0) else None, "lon": lon if lon not in (None, 0.0) else None}


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def packet_hash(raw_hex: str) -> str:
    try:
        from .utils import calculate_packet_hash
        return calculate_packet_hash(raw_hex)
    except Exception:  # noqa: BLE001 - outside the bot (tests): a stable stand-in
        import hashlib
        return hashlib.sha256(bytes.fromhex(raw_hex)).hexdigest()[:16].upper()


# ------------------------------------------------------------------------------------------------ storing
def handle(db: Any, topic: str, payload: bytes, now: Optional[float] = None) -> Optional[str]:
    """Store one MQTT message. Returns what it was ('packet', 'status') or None when it is not an observer message."""
    m = TOPIC.match(str(topic or ""))
    if not m:
        return None
    try:
        body = json.loads(payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict):
        return None
    now = time.time() if now is None else now
    key = m.group("key").lower()
    iata = m.group("iata").upper()[:8]
    name = str(body.get("origin") or body.get("name") or "")[:40]
    with db.connection() as conn:
        ensure(conn)
        conn.execute("INSERT INTO observer_nodes (key, name, iata, first_seen, last_seen) VALUES (?,?,?,?,?) "
                     "ON CONFLICT(key) DO UPDATE SET last_seen = excluded.last_seen, iata = excluded.iata, "
                     "name = COALESCE(NULLIF(excluded.name, ''), observer_nodes.name)", (key, name, iata, int(now), int(now)))
        if m.group("kind") == "status":
            radio = body.get("radio")
            conn.execute("UPDATE observer_nodes SET status = ?, model = COALESCE(?, model), firmware = COALESCE(?, firmware), "
                         "radio = COALESCE(?, radio), last_status = ? WHERE key = ?",
                         (str(body.get("status") or "")[:20] or None, (str(body["model"])[:40] if body.get("model") else None),
                          (str(body.get("firmware_version") or body.get("firmware") or "")[:40] or None),
                          (str(radio)[:60] if radio else None), int(now), key))
            conn.commit()
            return "status"
        raw = str(body.get("raw") or body.get("raw_hex") or "")
        pkt = decode_raw(raw) if raw else None
        hour = int(now // 3600) * 3600
        rssi, snr = _num(body.get("RSSI", body.get("rssi"))), _num(body.get("SNR", body.get("snr")))
        kind = (pkt or {}).get("type")
        conn.execute(
            "INSERT INTO observer_hourly (key, hour, packets, adverts, group_msgs, other, rssi_sum, snr_sum, sig_n) "
            "VALUES (?,?,1,?,?,?,?,?,?) ON CONFLICT(key, hour) DO UPDATE SET packets = packets + 1, "
            "adverts = adverts + excluded.adverts, group_msgs = group_msgs + excluded.group_msgs, other = other + excluded.other, "
            "rssi_sum = rssi_sum + excluded.rssi_sum, snr_sum = snr_sum + excluded.snr_sum, sig_n = sig_n + excluded.sig_n",
            (key, hour, int(kind == "ADVERT"), int(kind == "GRP_TXT"), int(kind not in ("ADVERT", "GRP_TXT")),
             rssi or 0.0, snr or 0.0, int(rssi is not None and snr is not None)))
        if pkt and kind == "ADVERT":
            adv = parse_advert(pkt["payload"])
            if adv:
                conn.execute(
                    "INSERT INTO observer_heard (key, node, name, type, lat, lon, count, last_seen, last_snr, hops) "
                    "VALUES (?,?,?,?,?,?,1,?,?,?) ON CONFLICT(key, node) DO UPDATE SET count = count + 1, "
                    "name = COALESCE(NULLIF(excluded.name, ''), observer_heard.name), type = excluded.type, "
                    "lat = COALESCE(excluded.lat, observer_heard.lat), lon = COALESCE(excluded.lon, observer_heard.lon), "
                    "last_seen = excluded.last_seen, last_snr = excluded.last_snr, hops = excluded.hops",
                    (key, adv["key"], adv["name"], adv["type"], adv["lat"], adv["lon"], int(now), snr, pkt["hops"]))
        if pkt and kind == "GRP_TXT" and conn.execute("SELECT 1 FROM sqlite_master WHERE name='packet_stream'").fetchone():
            # for the Channel radar: same row shape as the bot's own packets, tagged with the observer
            conn.execute("INSERT INTO packet_stream (timestamp, data, type) VALUES (?,?, 'packet')",
                         (now, json.dumps({"payload_type_name": "GRP_TXT", "payload_hex": pkt["payload"].hex(),
                                           "packet_hash": packet_hash(raw), "via_observer": key})))
        conn.commit()
    return "packet"


def cleanup(db: Any, now: Optional[float] = None) -> None:
    now = time.time() if now is None else now
    with db.connection() as conn:
        ensure(conn)
        conn.execute("DELETE FROM observer_hourly WHERE hour < ?", (int(now - KEEP_DAYS * 86400),))
        conn.execute("DELETE FROM observer_heard WHERE last_seen < ?", (int(now - KEEP_DAYS * 86400),))
        conn.commit()


# ------------------------------------------------------------------------------------------------ the dashboard
def summary(db: Any, days: int = 1, key: Optional[str] = None, now: Optional[float] = None) -> dict:
    """Observers with their numbers over `days`, and for `key` (or the busiest) the hourly series and the nodes heard."""
    now = time.time() if now is None else now
    days = max(1, min(KEEP_DAYS, int(days)))
    since = int(now - days * 86400)
    with db.connection() as conn:
        ensure(conn)
        obs = []
        for k, name, iata, status, model, fw, radio, first, last in conn.execute(
                "SELECT key, name, iata, status, model, firmware, radio, first_seen, last_seen FROM observer_nodes ORDER BY last_seen DESC"):
            row = conn.execute("SELECT COALESCE(SUM(packets),0), COALESCE(SUM(adverts),0), COALESCE(SUM(group_msgs),0), "
                               "COALESCE(SUM(rssi_sum),0), COALESCE(SUM(snr_sum),0), COALESCE(SUM(sig_n),0) FROM observer_hourly "
                               "WHERE key = ? AND hour >= ?", (k, since)).fetchone()
            heard = conn.execute("SELECT COUNT(*) FROM observer_heard WHERE key = ? AND last_seen >= ?", (k, since)).fetchone()[0]
            obs.append({"key": k[:12], "full_key": k, "name": name or k[:8], "iata": iata, "status": status, "model": model,
                        "firmware": fw, "radio": radio, "first_seen": first, "last_seen": last, "packets": row[0],
                        "adverts": row[1], "group_msgs": row[2], "rssi": round(row[3] / row[5], 1) if row[5] else None,
                        "snr": round(row[4] / row[5], 1) if row[5] else None, "nodes": heard})
        sel = next((o for o in obs if key and o["full_key"].startswith(key.lower())), None) or (max(obs, key=lambda o: o["packets"]) if obs else None)
        series, heard_list = {"t": [], "packets": [], "adverts": [], "group_msgs": []}, []
        if sel:
            for hour, p, a, g in conn.execute("SELECT hour, packets, adverts, group_msgs FROM observer_hourly WHERE key = ? "
                                              "AND hour >= ? ORDER BY hour", (sel["full_key"], since)):
                series["t"].append(hour)
                series["packets"].append(p)
                series["adverts"].append(a)
                series["group_msgs"].append(g)
            heard_list = [{"node": n[:12], "name": nm or n[:8], "type": tp, "count": c, "last_seen": ls, "snr": snr, "hops": hp,
                           "lat": la, "lon": lo}
                          for n, nm, tp, c, ls, snr, hp, la, lo in conn.execute(
                              "SELECT node, name, type, count, last_seen, last_snr, hops, lat, lon FROM observer_heard WHERE key = ? "
                              "AND last_seen >= ? ORDER BY count DESC LIMIT 300", (sel["full_key"], since))]
    for o in obs:
        o.pop("full_key", None)
    return {"generated_at": int(now), "days": days, "observers": obs, "selected": sel["key"] if sel else None,
            "series": series, "heard": heard_list}
