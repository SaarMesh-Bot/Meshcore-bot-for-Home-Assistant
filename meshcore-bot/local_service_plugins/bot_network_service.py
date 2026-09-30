#!/usr/bin/env python3
"""Bot network: shares this bot's hello, info, status, channel and bot lists with other bots of this add-on over the
internet (MQTT) - no airtime, any distance (card: Plugins -> BotNetwork, off by default; see modules/bot_network.py for
the messages, the signatures and the trust rules).

One connection to the network's own MQTT server (fixed in the code: mqtt.vipje.nl, TLS on 8883, run by the add-on's
maintainer; the shared login only gives access to the network's topic). Every message is signed with this bot's own
key and published retained under <topic>/<bot id>/<kind>, so a bot that joins sees the latest state of every other bot
at once. Messages from other bots come in on the same connection. Who is who is decided by those signatures, never by
the shared login.

Schedule (hours adjustable on the card): hello (version) every 24 h, info (radio settings, region) every week, status
every hour, channel and bot lists every 24 h and only when changed; each kind also goes out a few minutes after the
start, with a random extra wait so bots do not all publish at the same moment. What could not be sent (no connection)
stays due and goes out once the broker is back.
"""
import asyncio
import hashlib
import json
import os
import random
import ssl
import time
from typing import Any, Optional

from ..bot_network import (SECTION, bot_id, enabled, ensure_tables, hello_fields, info_fields, marked_bots, mqtt_message,
                           radar_channels, receive_mqtt, signing_key, status_fields)
from ..mesh_community import own_name
from ..night_mode import is_night
from .base_service import BaseServicePlugin

CHECK_EVERY_S = 60
STATE_KEY = "botnet.state"
KINDS = ("H", "I", "S", "K", "B", "N")
EVERY_H = {"H": 24, "I": 168, "S": 1, "K": 24, "B": 24, "N": 24}   # hours, the defaults of the card
FIRST = {"H": 180, "I": 300, "S": 600, "K": 900, "B": 1200, "N": 1500}   # seconds after the start
DISCOVER_FIRST_S = 1200   # the first neighbour discovery 20 minutes after the start (it transmits once)
JITTER_S = 300
# The network's server. Fixed on purpose (no card fields): every bot must meet on the same server. The password is
# public (it is in this open-source code) and only opens the topic below; see bot_network.py for why that is safe.
BROKER = {"host": "mqtt.vipje.nl", "port": 8883, "tls": True, "username": "mcbot", "password": "mcbot-cgL9PuyQmEb7spctqNlb",
          "topic": "meshcore-bot-ha/botnet/v1"}


class BotNetworkService(BaseServicePlugin):
    config_section = SECTION
    name = "botnetwork"
    description = "Shares what this bot's radio hears with other bots of this add-on, over the internet (MQTT, no airtime)"

    settings_schema = [
        {"key": "region", "label": "Region (optional)", "type": "str", "default": "",
         "help": "A short code sent with the info, for example NL-LI. Empty = no region."},
        {"key": "trusted", "label": "Trusted bots", "type": "list", "default": [],
         "help": ("Names of bots whose channel and bot lists are used at once. From other bots a name is only used when at "
                  "least two bots report it.")},
        {"key": "share_status", "label": "Share status", "type": "bool", "default": True,
         "help": "Nodes heard, new nodes, people who wrote, messages, commands answered, most hops today, uptime."},
        {"key": "share_channels", "label": "Share channel names", "type": "bool", "default": True,
         "help": "Hashtag channels the Channel radar recognised in the last 7 days. Never private channels."},
        {"key": "share_bots", "label": "Share bot names", "type": "bool", "default": True,
         "help": "The names you marked as bots (Bots page or botlist)."},
        {"key": "hello_hours", "label": "Hello (version) every", "type": "int", "default": 24, "min": 1, "max": 720, "unit": "h",
         "help": "Hours between two hellos."},
        {"key": "info_hours", "label": "Radio settings and region every", "type": "int", "default": 168, "min": 1, "max": 720,
         "unit": "h", "help": "They rarely change: once a week (168 h) is plenty. Also sent once after every start."},
        {"key": "status_hours", "label": "Status every", "type": "int", "default": 1, "min": 1, "max": 168, "unit": "h",
         "help": "Hours between two status messages."},
        {"key": "lists_hours", "label": "Channel and bot names at most every", "type": "int", "default": 24, "min": 1, "max": 720,
         "unit": "h", "help": "Only sent when the list changed since last time."},
        {"key": "find_neighbours", "label": "Find and share neighbours", "type": "bool", "default": False,
         "help": ("Ask which repeaters hear this radio directly (zero-hop discovery), store them (like PacketCapture does) and "
                  "share them. Costs one short transmission per round. Off by default.")},
        {"key": "neighbours_hours", "label": "Neighbours every", "type": "int", "default": 24, "min": 6, "max": 168, "unit": "h",
         "help": "Hours between two neighbour discoveries (at least 6). Never in night mode."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        has = cfg.has_section(SECTION)

        def get(key, fallback=""):
            return (cfg.get(SECTION, key, fallback=fallback) if has else fallback) or fallback

        def getbool(key, fallback):
            return cfg.getboolean(SECTION, key, fallback=fallback) if has else fallback

        def getint(key, fallback, lo, hi):
            try:
                return max(lo, min(hi, int(get(key, str(fallback)))))
            except ValueError:
                return fallback
        self.find_neighbours = getbool("find_neighbours", False)
        self.share = {"H": True, "I": True, "S": getbool("share_status", True), "K": getbool("share_channels", True),
                      "B": getbool("share_bots", True), "N": self.find_neighbours}
        lists = getint("lists_hours", EVERY_H["K"], 1, 720)
        self.every = {"H": getint("hello_hours", EVERY_H["H"], 1, 720) * 3600, "I": getint("info_hours", EVERY_H["I"], 1, 720) * 3600,
                      "S": getint("status_hours", EVERY_H["S"], 1, 168) * 3600, "K": lists * 3600, "B": lists * 3600,
                      "N": getint("neighbours_hours", EVERY_H["N"], 6, 168) * 3600}
        self.neighbours_every = self.every["N"]
        self._firmware: Optional[dict] = None
        self._discovering = False
        self.broker = dict(BROKER)
        self.version = os.environ.get("ADDON_VERSION", "") or "?"
        self.started_at = time.time()
        self._due: dict = {}
        self._task: Optional[asyncio.Task] = None
        self._client = None
        self.mqtt_connected = False

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._running = True
        if not enabled(self.bot):
            return
        ensure_tables(self.bot.db_manager)
        now = time.time()
        self._due = {k: now + FIRST[k] + random.uniform(0, JITTER_S) for k in KINDS}
        await self._connect()
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("Botnetwerk: gestart (%s, %s)", self.broker["host"], self.broker["topic"])

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                self.logger.warning(f"Botnetwerk: fout: {e}")
            await asyncio.sleep(CHECK_EVERY_S)

    # ------------------------------------------------------------------ internet
    def _on_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        try:
            receive_mqtt(self.bot, msg.payload, own_name(self.bot))
        except Exception as e:  # noqa: BLE001
            self.logger.debug("Botnetwerk: bericht van de broker overgeslagen: %s", e)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, rc: Any, *_: Any) -> None:
        ok = (not rc.is_failure) if hasattr(rc, "is_failure") else (getattr(rc, "value", rc) == 0)
        self.mqtt_connected = bool(ok)
        if ok:
            client.subscribe(f"{self.broker['topic']}/+/+", qos=0)
            self.logger.info("Botnetwerk: verbonden met %s", self.broker["host"])
        else:
            self.logger.warning("Botnetwerk: broker %s weigert de verbinding (%s)", self.broker["host"], rc)

    def _on_disconnect(self, *_: Any) -> None:
        self.mqtt_connected = False

    async def _connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.logger.warning("Botnetwerk: paho-mqtt ontbreekt, geen internet-transport")
            return
        try:
            # A fixed name per bot (its id), so the broker lists every bot as its own client.
            client_id = f"mcbot-{bot_id(signing_key(self.bot).verify_key.encode().hex())}"
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
            except AttributeError:   # paho-mqtt 1.x
                client = mqtt.Client(client_id=client_id)
            client.on_connect, client.on_message, client.on_disconnect = self._on_connect, self._on_message, self._on_disconnect
            client.reconnect_delay_set(min_delay=5, max_delay=300)
            if self.broker["tls"]:
                client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            if self.broker["username"]:
                client.username_pw_set(self.broker["username"], self.broker["password"])
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: client.connect_async(self.broker["host"], self.broker["port"], keepalive=120))
            client.loop_start()
            self._client = client
        except Exception as e:  # noqa: BLE001
            self.logger.warning("Botnetwerk: verbinden met %s mislukt: %s", self.broker["host"], e)

    def _publish(self, kind: str, data: Any, now: float) -> bool:
        if self._client is None or not self.mqtt_connected:
            return False
        suffix, payload = mqtt_message(self.bot, own_name(self.bot), kind, data, now)
        info = self._client.publish(f"{self.broker['topic']}/{suffix}", payload, qos=0, retain=True)
        return getattr(info, "rc", 0) == 0

    # ------------------------------------------------------------------ the radio itself (no airtime: local commands)
    def _self_pubkey(self) -> str:
        info = getattr(getattr(self.bot, "meshcore", None), "self_info", None) or {}
        key = info.get("public_key", "") if isinstance(info, dict) else getattr(info, "public_key", "")
        return (key.hex() if isinstance(key, (bytes, bytearray)) else str(key or "")).lower()

    async def _command(self, name: str) -> dict:
        commands = getattr(getattr(self.bot, "meshcore", None), "commands", None)
        fn = getattr(commands, name, None)
        if fn is None:
            return {}
        try:
            result = await asyncio.wait_for(fn(), timeout=10)
            payload = getattr(result, "payload", None)
            return payload if isinstance(payload, dict) and "error" not in str(getattr(result, "type", "")).lower() else {}
        except Exception:  # noqa: BLE001 - an older firmware without the command: just leave it out
            return {}

    async def radio_stats(self) -> dict:
        """Noise floor, last RSSI/SNR, airtime (% of the radio's uptime), battery and packet counters (modules/radio_stats.py)."""
        from ..radio_stats import radio_stats
        return await radio_stats(self.bot)

    async def firmware(self) -> dict:
        if self._firmware is None:
            q = await self._command("send_device_query")
            fw = {}
            if q:
                version = str(q.get("ver") or q.get("fw ver") or "")
                fw = {"fw": version.lstrip("v")[:20] if version else "", "mdl": str(q.get("model") or "")[:40],
                      "fwd": str(q.get("fw_build") or "")[:20]}
            self._firmware = {k: v for k, v in fw.items() if v}
        return dict(self._firmware)

    # ------------------------------------------------------------------ neighbours (zero-hop discovery)
    def neighbours(self, now: Optional[float] = None) -> list:
        """What the radio's own neighbour table holds (neighbor_links), newest first, last 7 days."""
        me = self._self_pubkey()
        if not me:
            return []
        try:
            with self.bot.db_manager.connection() as conn:
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='neighbor_links'").fetchone():
                    return []
                rows = conn.execute("""SELECT neighbor_public_key, last_snr, best_snr, last_seen FROM neighbor_links
                                       WHERE self_public_key = ? ORDER BY last_seen DESC LIMIT 64""", (me,)).fetchall()
        except Exception:  # noqa: BLE001
            return []
        from datetime import datetime
        now = time.time() if now is None else now
        out = []
        for key, snr, best, seen in rows:
            try:
                ts = int(datetime.fromisoformat(str(seen).replace("Z", "+00:00")).timestamp())
            except ValueError:
                ts = None
            if ts is not None and now - ts > 7 * 86400:
                continue
            out.append({"k": str(key).lower()[:12], "s": snr, "b": best, "t": ts})
        return out

    async def discover(self, now: Optional[float] = None) -> Optional[int]:
        """One zero-hop discovery round (one transmission), stored in neighbor_links. Number found, or None."""
        me = self._self_pubkey()
        mc = getattr(self.bot, "meshcore", None)
        if not me or mc is None or self._discovering:
            return None
        self._discovering = True
        try:
            from ..neighbors_discovery import NeighborsConfig, discover_neighbors, record_neighbors
            entries = await discover_neighbors(mc, NeighborsConfig(collect_scopes=False), me, self.logger)
            if entries is None:
                self.logger.info("Botnetwerk: buren zoeken lukte niet (radio antwoordde niet)")
                return None
            record_neighbors(self.bot.db_manager, me, entries, self.logger)
            self.logger.info("Botnetwerk: %d buur/buren gevonden", len(entries))
            return len(entries)
        except Exception as e:  # noqa: BLE001
            self.logger.info("Botnetwerk: buren zoeken mislukt: %s", e)
            return None
        finally:
            self._discovering = False

    # ------------------------------------------------------------------ what to send
    async def data(self, kind: str, now: Optional[float] = None) -> Any:
        if kind == "H":
            return hello_fields(self.bot, self.version)
        if kind == "I":
            info = {k: v for k, v in info_fields(self.bot).items() if v not in (None, "")}
            radio = getattr(getattr(self.bot, "meshcore", None), "self_info", None) or {}
            if isinstance(radio, dict) and radio.get("radio_cr"):
                info["cr"] = radio["radio_cr"]
            me = self._self_pubkey()
            if me:
                info["node"] = me[:12]
            info.update(await self.firmware())
            return info
        if kind == "S":
            return {**status_fields(self.bot, now, self.started_at), **await self.radio_stats()}
        if kind == "N":
            return self.neighbours(now)
        return radar_channels(self.bot) if kind == "K" else marked_bots(self.bot)

    def _state(self) -> dict:
        try:
            return json.loads(self.bot.db_manager.get_metadata(STATE_KEY) or "{}")
        except (ValueError, TypeError):
            return {}

    async def tick(self, now: Optional[float] = None) -> list:
        """Publish what is due. Returns the kinds published (for tests)."""
        now = time.time() if now is None else now
        if not enabled(self.bot):
            return []
        state = self._state()
        sent = []
        if self.find_neighbours and not is_night(self.bot, now) and getattr(self.bot, "connected", False):
            last = float(state.get("nb_attempt") or 0)
            first_ok = now - self.started_at >= DISCOVER_FIRST_S
            if first_ok and now - last >= self.neighbours_every:
                state["nb_attempt"] = now   # charge the transmission, not the result
                self.bot.db_manager.set_metadata(STATE_KEY, json.dumps(state))
                if await self.discover(now) is not None:
                    self._due["N"] = min(self._due.get("N", now), now)   # share the fresh list at once
        for kind in KINDS:
            if not self.share.get(kind) or now < self._due.get(kind, now + 1):
                continue
            d = await self.data(kind, now)
            digest = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:12]
            if kind in ("K", "B", "N") and (not d or state.get(f"net_{kind}") == digest):
                self._due[kind] = now + self.every[kind]
                continue
            if self._publish(kind, d, now):
                self._due[kind] = now + self.every[kind] + random.uniform(0, JITTER_S)
                state[f"net_{kind}"] = digest
                sent.append(kind)
        self.bot.db_manager.set_metadata(STATE_KEY, json.dumps(state))
        return sent
