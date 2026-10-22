#!/usr/bin/env python3
"""CoreScopeTelemetry: battery and temperature of your repeaters to a CoreScope map over MQTT (card: Plugins ->
CoreScopeTelemetry, off by default).

meshcore-ha already asks the repeaters for their status over the radio and keeps the answer as Home Assistant sensors
(the same data the HARepeater card reads). This service reads those sensors (`GET /api/states` with the add-on's own
Supervisor token, no airtime) and publishes every NEW reading in the format CoreScope's ingestor understands:

    topic   meshcore/{REGION}/{public_key}/telemetry
    payload {"public_key": ..., "battery_mv": 4104, "temperature_c": 27.0, "source": "ha-bot", "ts": "...Z"}

`ts` is the time of the reading in Home Assistant, not the time of publishing, so a reading that is sent twice (after a
restart) is the same data point. Nothing goes over the radio and nothing is written to Home Assistant.
"""
import asyncio
import json
import os
import ssl
import time
from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

from .base_service import BaseServicePlugin

try:
    from ..ha_repeater_parser import parse_states, select
except ImportError:  # pragma: no cover - unit tests import the file directly
    from ha_repeater_parser import parse_states, select   # type: ignore[no-redef]

STATES_URL = "http://supervisor/core/api/states"
FIRST_READ_DELAY_S = 60
ERROR_LOG_INTERVAL_S = 6 * 3600


def build_payload(rep: dict, now: Optional[float] = None) -> Optional[tuple]:
    """(public_key, payload) for one parsed repeater, or None when there is nothing to send."""
    pk = str(rep.get("public_key") or "").lower()
    if len(pk) != 64:
        return None                      # CoreScope keys nodes by the full key; a prefix would create a ghost node
    payload: dict = {"public_key": pk, "source": "ha-bot"}
    if rep.get("battery_mv"):
        payload["battery_mv"] = int(rep["battery_mv"])
    if rep.get("temperature") is not None:
        payload["temperature_c"] = float(rep["temperature"])
    if len(payload) == 2:
        return None
    age = rep.get("stats_age_s")
    reading_at = (now if now is not None else time.time()) - (age or 0)
    payload["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(reading_at))
    return pk, payload


class CoreScopeTelemetryService(BaseServicePlugin):
    config_section = "CoreScopeTelemetry"
    name = "corescopetelemetry"
    description = "Battery and temperature of your repeaters (read from Home Assistant) to a CoreScope map over MQTT, no airtime"

    settings_schema = [
        {"key": "host", "label": "Broker", "type": "str", "default": "",
         "help": "Host name of the MQTT broker your CoreScope ingestor listens to."},
        {"key": "port", "label": "Port", "type": "int", "default": 8883, "min": 1, "max": 65535,
         "help": "1883 without TLS, 8883 with TLS."},
        {"key": "tls", "label": "TLS", "type": "bool", "default": True},
        {"key": "username", "label": "User name", "type": "str", "default": ""},
        {"key": "password", "label": "Password", "type": "password", "default": ""},
        {"key": "region", "label": "Region (IATA)", "type": "str", "default": "",
         "help": "The region part of the topic meshcore/{REGION}/{key}/telemetry, e.g. SCN."},
        {"key": "repeaters", "label": "Repeaters", "type": "list", "default": [], "pattern": "[0-9a-fA-F]{4,64}",
         "help": "Empty = every repeater meshcore-ha follows. Otherwise the first characters of their public keys."},
        {"key": "read_interval_minutes", "label": "Read Home Assistant every", "type": "int", "default": 10,
         "min": 1, "max": 120, "unit": "min",
         "help": "Costs no airtime. Only readings that are new since the last check are published."},
        {"key": "max_age_hours", "label": "Skip readings older than", "type": "int", "default": 6,
         "min": 1, "max": 72, "unit": "h",
         "help": "A repeater that stopped answering keeps its last value in Home Assistant; that value is not sent again."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        s = self.config_section
        has = cfg.has_section(s)

        def get(key, fallback=""):
            return (cfg.get(s, key, fallback=fallback) if has else fallback) or fallback

        def number(key, fallback, lo, hi):
            try:
                return max(lo, min(hi, int(get(key, str(fallback)))))
            except ValueError:
                return fallback
        self.enabled = cfg.getboolean(s, "enabled", fallback=False) if has else False
        self.host = get("host").strip()
        self.port = number("port", 8883, 1, 65535)
        self.tls = cfg.getboolean(s, "tls", fallback=True) if has else True
        self.username, self.password = get("username").strip(), get("password")
        self.region = get("region").strip().upper()
        self.wanted = [w.strip().lower() for w in get("repeaters").split(",") if w.strip()]
        self.interval = number("read_interval_minutes", 10, 1, 120) * 60
        self.max_age_s = number("max_age_hours", 6, 1, 72) * 3600
        self._client = None
        self._task: Optional[asyncio.Task] = None
        self._session = None
        self._sent: dict = {}              # public_key -> stats_key of the last published reading
        self._error_logged: dict = {}
        self.connected = False
        self.published = 0
        self.last_error = ""

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        self._running = True
        if not self.enabled:
            return
        if aiohttp is None:
            self.logger.warning("CoreScopeTelemetry: aiohttp fehlt, Dienst nicht gestartet")
            return
        if not (self.host and self.region):
            self.logger.warning("CoreScopeTelemetry: Broker oder Region fehlt auf der Karte")
            return
        await self._connect()
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25))
        self._task = asyncio.get_running_loop().create_task(self._loop())
        self.logger.info("CoreScopeTelemetry: gestartet (%s:%s, Region %s, alle %d min aus Home Assistant, keine Airtime)",
                         self.host, self.port, self.region, self.interval // 60)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._session is not None:
            await self._session.close()
            self._session = None
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    def _on_connect(self, _client: Any, _userdata: Any, _flags: Any, rc: Any, *_: Any) -> None:
        ok = (not rc.is_failure) if hasattr(rc, "is_failure") else (getattr(rc, "value", rc) == 0)
        self.connected = bool(ok)
        if ok:
            self.logger.info("CoreScopeTelemetry: verbunden mit %s", self.host)
        else:
            self._complain("connect", f"CoreScopeTelemetry: Broker {self.host} lehnt ab ({rc})")

    def _on_disconnect(self, *_: Any) -> None:
        self.connected = False

    async def _connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.logger.warning("CoreScopeTelemetry: paho-mqtt fehlt")
            return
        try:
            client_id = f"mcbot-telemetry-{int(time.time()) % 100000}"
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
            except AttributeError:   # paho-mqtt 1.x
                client = mqtt.Client(client_id=client_id)
            client.on_connect, client.on_disconnect = self._on_connect, self._on_disconnect
            client.reconnect_delay_set(min_delay=5, max_delay=300)
            if self.tls:
                client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            if self.username:
                client.username_pw_set(self.username, self.password)
            await asyncio.get_running_loop().run_in_executor(None, lambda: client.connect_async(self.host, self.port, keepalive=60))
            client.loop_start()
            self._client = client
        except Exception as e:  # noqa: BLE001
            self._complain("connect", f"CoreScopeTelemetry: Verbindung zu {self.host} fehlgeschlagen: {e}")

    async def _loop(self) -> None:
        await asyncio.sleep(FIRST_READ_DELAY_S)
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - never let one bad round stop the loop
                self._complain("loop", f"CoreScopeTelemetry: Runde fehlgeschlagen: {e}")
            await asyncio.sleep(self.interval)

    # ------------------------------------------------------------------ work
    def _complain(self, kind: str, text: str) -> None:
        self.last_error = text
        now = time.time()
        if now - self._error_logged.get(kind, 0.0) >= ERROR_LOG_INTERVAL_S:
            self._error_logged[kind] = now
            self.logger.warning(text)

    async def _fetch(self) -> Optional[list]:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        try:
            async with self._session.get(STATES_URL, headers={"Authorization": f"Bearer {token}"}) as resp:
                if resp.status != 200:
                    self._complain("http", f"CoreScopeTelemetry: Home Assistant antwortete HTTP {resp.status}")
                    return None
                return await resp.json(content_type=None)
        except Exception as e:  # noqa: BLE001
            self._complain("net", f"CoreScopeTelemetry: Home Assistant nicht erreichbar: {e}")
        return None

    def due(self, states: list, now: Optional[float] = None) -> list:
        """[(public_key, payload, stats_key)] for the readings that are new and not too old."""
        now = time.time() if now is None else now
        out = []
        for rep in select(parse_states(states), self.wanted):
            if rep.get("online") is False:
                continue
            age = rep.get("stats_age_s")
            if age is not None and age > self.max_age_s:
                continue
            built = build_payload(rep, now)
            if built is None:
                continue
            pk, payload = built
            key = rep.get("stats_key") or payload["ts"]
            if self._sent.get(pk) == key:
                continue
            out.append((pk, payload, key))
        return out

    async def run_once(self) -> int:
        if self._client is None or not self.connected:
            self._complain("offline", f"CoreScopeTelemetry: nicht mit {self.host} verbunden, Runde übersprungen")
            return 0
        states = await self._fetch()
        if states is None:
            return 0
        n = 0
        for pk, payload, key in self.due(states):
            topic = f"meshcore/{self.region}/{pk}/telemetry"
            info = self._client.publish(topic, json.dumps(payload), qos=1)
            if getattr(info, "rc", 0) == 0:
                self._sent[pk] = key
                n += 1
                self.logger.info("CoreScopeTelemetry: %s… %s mV %s °C", pk[:8], payload.get("battery_mv"), payload.get("temperature_c"))
        self.published += n
        self.last_error = ""
        return n
