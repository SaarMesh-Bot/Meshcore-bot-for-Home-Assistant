"""Watchlist ([Watchlist]): react when a watched sender writes in a channel.

Why: a node with an offensive name (21.11.2026 "Führerhauptquartier" in Public) should get a short, direct request
to change it, and the operator wants to know when it shows up again - without giving it a stage in the channel.

What it does:
- every channel message whose sender name matches a target is reported to Home Assistant (default
  telegram_bot.send_message): sender, channel, text, hops, and what happened with the DM;
- the sender gets one DM per `dm_cooldown_hours` (kept in the bot's database, survives restarts), after
  `delay_seconds`. A channel message carries no public key, so the DM goes to the key given with the target
  ("Name=publickey"); when that key is not among the radio's contacts yet, the bot adds it as a contact first.
  Without a key the DM only works when the name is already a contact. Never anything in the channel.

Config (config.ini, set on the Watchlist card of the Plugins page):

    [Watchlist]
    enabled = true
    targets = Führerhauptquartier=7cf26cbf...   ; comma-separated "name" or "name=public key"; the name matches
                                                 ; case-insensitively as part of the sender name
    channels =                                   ; empty = every channel
    message_dm = Hallo, bitte wähl einen anderen Node-Namen ...
    dm_cooldown_hours = 24
    delay_seconds = 15
    notify = true
    ha_notify_service = telegram_bot.send_message
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

SECTION = "Watchlist"
DM_KEY = "watchlist.dm_sent"   # bot_metadata: {target name (lower case): unix time of the last DM}
SETTINGS_TTL_SECONDS = 30
DELAY_JITTER_SECONDS = 5
DEFAULT_DM = ("Hallo, bitte wähl einen anderen Node-Namen, der jetzige ist hier im Netz nicht erwünscht. "
              "Danke! – SaarMesh")


def _split(value: str) -> list:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _norm(name: str) -> str:
    return (name or "").strip().casefold()


def _hops(message: Any) -> Optional[int]:
    ri = getattr(message, "routing_info", None)
    if isinstance(ri, dict) and ri.get("path_len_byte") is not None:
        try:
            return int(ri["path_len_byte"]) & 63
        except (TypeError, ValueError):
            pass
    hops = getattr(message, "hops", None)
    return hops if isinstance(hops, int) and 0 <= hops < 64 else None


class Watchlist:
    def __init__(self, bot: Any):
        self.bot = bot
        self._settings_at = -SETTINGS_TTL_SECONDS - 1.0
        self._pending: set = set()
        self._tasks: set = set()
        self._load_settings()

    # ---- settings (re-read every SETTINGS_TTL_SECONDS: a change on the card works without a restart) ----
    def _load_settings(self) -> None:
        self._settings_at = time.monotonic()
        cfg = self.bot.config
        has = cfg.has_section(SECTION)

        def get(key, fallback=""):
            return cfg.get(SECTION, key, fallback=fallback) if has else fallback

        def num(key, fallback, low, high):
            try:
                return max(low, min(high, int(float(get(key, str(fallback)) or fallback))))
            except ValueError:
                return fallback

        self.enabled = cfg.getboolean(SECTION, "enabled", fallback=False) if has else False
        targets = []
        for item in _split(get("targets", "")):
            name, _, key = item.partition("=")
            key = key.strip().lower()
            if _norm(name):
                targets.append((_norm(name), name.strip(), key if len(key) == 64 else ""))
        self.targets = targets
        self.channels = {_norm(c) for c in _split(get("channels", ""))}
        self.message_dm = get("message_dm", "").strip() or DEFAULT_DM
        self.dm_cooldown = num("dm_cooldown_hours", 24, 0, 24 * 365) * 3600
        self.delay_seconds = num("delay_seconds", 15, 0, 600)
        self.notify = cfg.getboolean(SECTION, "notify", fallback=True) if has else True
        self.ha_notify_service = (get("ha_notify_service", "telegram_bot.send_message") or "").strip()

    def _refresh_settings(self) -> None:
        if time.monotonic() - self._settings_at > SETTINGS_TTL_SECONDS:
            try:
                self._load_settings()
            except Exception:  # noqa: BLE001 - keep the last good settings
                self._settings_at = time.monotonic()

    # ---- when the last DM went out (bot database) ----
    def _dm_sent(self) -> dict:
        try:
            raw = self.bot.db_manager.get_metadata(DM_KEY)
            data = json.loads(raw) if raw else {}
            return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _remember_dm(self, target: str, when: float) -> None:
        data = self._dm_sent()
        data[target] = when
        try:
            self.bot.db_manager.set_metadata(DM_KEY, json.dumps(data, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            self.bot.logger.warning("Watchlist: could not save the DM time: %s", e)

    # ---- the check, for every channel message ----
    def match(self, message: Any):
        self._refresh_settings()
        if not self.enabled or not self.targets or getattr(message, "is_dm", False):
            return None
        sender = _norm(getattr(message, "sender_id", "") or "")
        if not sender or sender == _norm(self.bot.config.get("Bot", "bot_name", fallback="")):
            return None
        if self.channels and _norm(getattr(message, "channel", "") or "") not in self.channels:
            return None
        for target in self.targets:
            if target[0] in sender:
                return target
        return None

    def observe(self, message: Any) -> bool:
        """Called for every channel message. Works in the background; True when the sender is watched."""
        target = self.match(message)
        if target is None:
            return False
        task = asyncio.ensure_future(self._handle(message, target))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _handle(self, message: Any, target: tuple) -> None:
        key_name = target[0]
        dm_result = "keine (Abstand %d h)" % (self.dm_cooldown // 3600)
        try:
            now = time.time()
            due = now - self._dm_sent().get(key_name, 0.0) >= self.dm_cooldown and key_name not in self._pending
            if due:
                self._pending.add(key_name)
                try:
                    if self.delay_seconds:
                        await asyncio.sleep(self.delay_seconds + random.uniform(0, DELAY_JITTER_SECONDS))
                    dm_result = await self._send_dm(message, target)
                finally:
                    self._pending.discard(key_name)
        except Exception as e:  # noqa: BLE001
            dm_result = f"Fehler: {e}"
            self.bot.logger.warning("Watchlist: DM to %s failed: %s", getattr(message, "sender_id", "?"), e)
        if self.notify:
            await self._ha_notify(message, dm_result)

    async def _ensure_contact(self, pubkey: str, name: str) -> None:
        mc = self.bot.meshcore
        if mc.get_contact_by_key_prefix(pubkey):
            return
        contact = {
            "public_key": pubkey, "type": 1, "flags": 0,
            "out_path_len": -1, "out_path": "", "out_path_hash_mode": 0,
            "adv_name": name[:31], "last_advert": 0, "adv_lat": 0.0, "adv_lon": 0.0,
        }
        res = await mc.commands.add_contact(contact)
        self.bot.logger.info("Watchlist: added %s (%s...) as a contact: %s", name, pubkey[:8],
                             getattr(res, "type", None))
        try:
            await mc.commands.get_contacts()
        except Exception:  # noqa: BLE001
            pass

    async def _send_dm(self, message: Any, target: tuple) -> str:
        sender = (getattr(message, "sender_id", "") or "").strip()
        pubkey = (getattr(message, "sender_pubkey", None) or target[2] or "").strip().lower()
        recipient = sender
        if len(pubkey) == 64:
            try:
                await self._ensure_contact(pubkey, sender or target[1])
            except Exception as e:  # noqa: BLE001
                self.bot.logger.info("Watchlist: could not add the contact: %s", e)
            recipient = pubkey
        ok = bool(await self.bot.command_manager.send_dm(
            recipient, self.message_dm.replace("{sender}", sender), skip_user_rate_limit=True))
        if ok:
            self._remember_dm(target[0], time.time())
            self.bot.logger.info("Watchlist: DM sent to %s", sender)
            return "gesendet"
        self.bot.logger.info("Watchlist: DM to %s not possible", sender)
        return "nicht möglich (kein Kontakt)" if len(pubkey) != 64 else "fehlgeschlagen"

    async def _ha_notify(self, message: Any, dm_result: str) -> None:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not (aiohttp and token and "." in self.ha_notify_service):
            return
        hops = _hops(message)
        snr = getattr(message, "snr", None)
        lines = [
            f"Von: {getattr(message, 'sender_id', '?')}",
            f"Kanal: {getattr(message, 'channel', '?')}",
            f"Text: {getattr(message, 'content', '') or ''}",
        ]
        rf = " • ".join(x for x in (f"{hops} Hops" if hops is not None else "",
                                     f"SNR {snr}" if snr is not None else "") if x)
        if rf:
            lines.append(rf)
        lines.append(f"DM: {dm_result}")
        domain, service = self.ha_notify_service.split(".", 1)
        body = {"title": "👀 Watchlist", "message": "\n".join(lines)}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"http://supervisor/core/api/services/{domain}/{service}", json=body,
                                        headers={"Authorization": f"Bearer {token}"},
                                        timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status >= 300:
                        self.bot.logger.info("Watchlist: HA notify returned status %s", resp.status)
        except Exception as e:  # noqa: BLE001
            self.bot.logger.info("Watchlist: HA notify failed: %s", e)


def get_watchlist(bot: Any) -> Watchlist:
    """One shared instance per bot, created on first use."""
    wl = bot.__dict__.get("_watchlist") if hasattr(bot, "__dict__") else None
    if wl is None:
        wl = Watchlist(bot)
        bot._watchlist = wl
    return wl
