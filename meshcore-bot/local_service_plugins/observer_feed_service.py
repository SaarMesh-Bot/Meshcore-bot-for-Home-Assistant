#!/usr/bin/env python3
"""ObserverFeed: listens to MeshCore observers on an MQTT broker (card: Plugins -> ObserverFeed, off by default) and
keeps their numbers for the dashboard (Radar -> Observers) and the Channel radar. See modules/observers.py.

Observers publish in the common format meshcore/{IATA}/{PUBLIC_KEY}/packets and .../status (meshcoretomqtt, LetsMesh,
the meshcore-ha observer setting). Put in the broker your observers use (the same one meshcore-ha listens to);
nothing is published and nothing is sent over the radio.
"""
import asyncio
import ssl
import time
from typing import Any, Optional

from .base_service import BaseServicePlugin

CLEANUP_EVERY_S = 3600


class ObserverFeedService(BaseServicePlugin):
    config_section = "ObserverFeed"
    name = "observerfeed"
    description = "Listens to MeshCore observers on an MQTT broker (meshcore/+/+/packets and status) for the dashboard and the radar"

    settings_schema = [
        {"key": "host", "label": "Broker", "type": "str", "default": "",
         "help": "Host name or IP of the MQTT broker your observers publish to (the one meshcore-ha listens to)."},
        {"key": "port", "label": "Port", "type": "int", "default": 1883, "min": 1, "max": 65535,
         "help": "1883 without TLS, 8883 with TLS."},
        {"key": "tls", "label": "TLS", "type": "bool", "default": False},
        {"key": "username", "label": "User name", "type": "str", "default": ""},
        {"key": "password", "label": "Password", "type": "password", "default": ""},
        {"key": "topic", "label": "Topic", "type": "str", "default": "meshcore/#",
         "help": "The observers' topics: meshcore/{IATA}/{PUBLIC_KEY}/packets and .../status. meshcore/# takes all of them; "
                 "meshcore/AMS/# only one region."},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        has = cfg.has_section("ObserverFeed")

        def get(key, fallback=""):
            return (cfg.get("ObserverFeed", key, fallback=fallback) if has else fallback) or fallback
        self.host = get("host").strip()
        try:
            self.port = int(get("port", "1883"))
        except ValueError:
            self.port = 1883
        self.tls = cfg.getboolean("ObserverFeed", "tls", fallback=False) if has else False
        self.username, self.password = get("username").strip(), get("password")
        self.topic = get("topic", "meshcore/#").strip() or "meshcore/#"
        self._client = None
        self._task: Optional[asyncio.Task] = None
        self.connected = False
        self.received = 0

    async def start(self) -> None:
        self._running = True
        cfg = self.bot.config
        if not (cfg.has_section("ObserverFeed") and cfg.getboolean("ObserverFeed", "enabled", fallback=False)):
            return
        if not self.host:
            self.logger.warning("ObserverFeed: geen broker ingevuld op de kaart")
            return
        await self._connect()
        self._task = asyncio.get_running_loop().create_task(self._loop())

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
        from .. import observers
        while self._running:
            await asyncio.sleep(CLEANUP_EVERY_S)
            try:
                await asyncio.to_thread(observers.cleanup, self.bot.db_manager)
            except Exception as e:  # noqa: BLE001
                self.logger.debug("ObserverFeed: opruimen mislukt: %s", e)

    def _on_connect(self, client: Any, _userdata: Any, _flags: Any, rc: Any, *_: Any) -> None:
        ok = (not rc.is_failure) if hasattr(rc, "is_failure") else (getattr(rc, "value", rc) == 0)
        self.connected = bool(ok)
        if ok:
            client.subscribe(self.topic, qos=0)
            self.logger.info("ObserverFeed: verbonden met %s, luistert naar %s", self.host, self.topic)
        else:
            self.logger.warning("ObserverFeed: broker %s weigert de verbinding (%s)", self.host, rc)

    def _on_disconnect(self, *_: Any) -> None:
        self.connected = False

    def _on_message(self, _client: Any, _userdata: Any, msg: Any) -> None:
        from .. import observers
        try:
            if observers.handle(self.bot.db_manager, msg.topic, msg.payload):
                self.received += 1
        except Exception as e:  # noqa: BLE001
            self.logger.debug("ObserverFeed: bericht overgeslagen: %s", e)

    async def _connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.logger.warning("ObserverFeed: paho-mqtt ontbreekt")
            return
        try:
            client_id = f"mcbot-observers-{int(time.time()) % 100000}"
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
            except AttributeError:   # paho-mqtt 1.x
                client = mqtt.Client(client_id=client_id)
            client.on_connect, client.on_message, client.on_disconnect = self._on_connect, self._on_message, self._on_disconnect
            client.reconnect_delay_set(min_delay=5, max_delay=300)
            if self.tls:
                client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
            if self.username:
                client.username_pw_set(self.username, self.password)
            await asyncio.get_running_loop().run_in_executor(None, lambda: client.connect_async(self.host, self.port, keepalive=60))
            client.loop_start()
            self._client = client
        except Exception as e:  # noqa: BLE001
            self.logger.warning("ObserverFeed: verbinden met %s mislukt: %s", self.host, e)
