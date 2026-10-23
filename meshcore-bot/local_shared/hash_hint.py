"""Path hash hint ([HashHint]): someone who sends with a 1-byte path hash in a watched channel gets a short tip
that 2 (or 3) bytes per hop is better.

Why: since firmware 1.14 a companion can send channel and direct messages with 1, 2 or 3 bytes per repeater in the
path (MeshCore FAQ 3.9). With 1 byte many repeaters share the same id, so routes and tools (map, analyzer, `path`)
cannot tell them apart. The size is chosen by whoever sends the message (app: Settings -> Experimental Settings);
repeaters on 1.14+ forward every size.

How the bot knows: the packet's path_len byte (high 2 bits = bytes per hop - 1, low 6 bits = hop count), taken from
the RF packet the message handler matched to the channel message (message.routing_info["path_len_byte"]). The size
bits are set by the sender even at 0 hops. A message without a matched RF packet is left alone (size unknown).

What it does, sparingly:
- once per person per `repeat_days` (kept in the bot's database, survives restarts);
- after `delay_seconds` (plus a little random), so the tip does not collide with the repeats of their own message;
- as a DM to the contact with the sender's name (`via = dm`, default); when no DM is possible (name not among the
  radio's contacts) `dm_fallback` decides: the tip in the channel after all (default) or nothing;
- in the channel at most once per `channel_cooldown_minutes`;
- never to the bot itself or to other bots (same recognition as the channel hint), optionally only within
  `max_hops` hops (0 = any distance).

Config (config.ini, set on the HashHint card of the Plugins page):

    [HashHint]
    enabled = true
    channels = Public
    via = dm                      ; dm | channel
    dm_fallback = channel         ; channel | none
    message_dm =                  ; empty = standard text in the bot's language; {sender} = the name
    message_channel =
    repeat_days = 30
    channel_cooldown_minutes = 10
    delay_seconds = 20
    max_hops = 0
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Optional

SECTION = "HashHint"
NOTIFIED_KEY = "hashhint.notified"   # bot_metadata: {name (lower case): unix time of the tip}
SETTINGS_TTL_SECONDS = 30
MAX_REMEMBERED = 3000
DELAY_JITTER_SECONDS = 10

# (DM text, channel text) per language of the bot. DM <= 158 bytes, channel text short enough for "Name: " + scope.
DEFAULT_TEXTS = {
    "de": ("Hi {sender}! Deine Nachricht kam mit 1-Byte-Pfad-Hash. Mit 2 Byte sind Wege im Mesh eindeutig: "
           "App > Einstellungen > Experimental Settings. Danke!",
           "@[{sender}] Tipp: Du sendest mit 1-Byte-Pfad-Hash. 2 Byte ist besser: App > Einstellungen > Experimental Settings"),
    "en": ("Hi {sender}! Your message used a 1-byte path hash. With 2 bytes routes in the mesh are unique: "
           "app > Settings > Experimental Settings. Thanks!",
           "@[{sender}] Tip: you send with a 1-byte path hash. 2 bytes is better: app > Settings > Experimental Settings"),
    "nl": ("Hoi {sender}! Je bericht had een 1-byte pad-hash. Met 2 bytes zijn routes in de mesh uniek: "
           "app > Instellingen > Experimental Settings. Bedankt!",
           "@[{sender}] Tip: je zendt met 1-byte pad-hash. 2 bytes is beter: app > Instellingen > Experimental Settings"),
    "fr": ("Salut {sender} ! Ton message avait un hash de chemin de 1 octet. 2 octets, c'est mieux : "
           "app > Réglages > Experimental Settings. Merci !",
           "@[{sender}] Astuce : hash de chemin 1 octet. 2 octets, c'est mieux : app > Réglages > Experimental Settings"),
}


def _split(value: str) -> list:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def sender_bytes_per_hop(message: Any) -> Optional[int]:
    """1, 2 or 3: the path hash size the sender chose, from the raw path_len byte of the matched RF packet.
    None when the bot has no packet for this message (then nothing is known)."""
    ri = getattr(message, "routing_info", None)
    if not isinstance(ri, dict):
        return None
    raw = ri.get("path_len_byte")
    if raw is None or isinstance(raw, bool):
        return None
    try:
        size = (int(raw) >> 6) + 1
    except (TypeError, ValueError):
        return None
    return size if size in (1, 2, 3) else None


def _hops(message: Any) -> Optional[int]:
    ri = getattr(message, "routing_info", None)
    if isinstance(ri, dict) and ri.get("path_len_byte") is not None:
        try:
            return int(ri["path_len_byte"]) & 63
        except (TypeError, ValueError):
            pass
    hops = getattr(message, "hops", None)
    return hops if isinstance(hops, int) and 0 <= hops < 64 else None


class HashHint:
    def __init__(self, bot: Any):
        self.bot = bot
        self._settings_at = -SETTINGS_TTL_SECONDS - 1.0
        self._last_channel: dict = {}     # channel -> when the last tip went out there
        self._pending: set = set()        # names with a tip on its way
        self._tasks: set = set()
        self._notified: Optional[dict] = None
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
        self.channels = {_norm(c) for c in _split(get("channels", "Public"))}
        self.via = (get("via", "dm") or "dm").strip().lower()
        self.dm_fallback = (get("dm_fallback", "channel") or "channel").strip().lower()
        lang = (cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en") or "en"
        dm_default, channel_default = DEFAULT_TEXTS.get(lang.strip().lower()[:2], DEFAULT_TEXTS["en"])
        self.message_dm = get("message_dm", "").strip() or dm_default
        self.message_channel = get("message_channel", "").strip() or channel_default
        self.repeat_days = num("repeat_days", 30, 1, 3650)
        self.channel_cooldown = num("channel_cooldown_minutes", 10, 0, 1440) * 60
        self.delay_seconds = num("delay_seconds", 20, 0, 600)
        self.max_hops = num("max_hops", 0, 0, 63)
        self.skip_bots = cfg.getboolean(SECTION, "skip_bots", fallback=True) if has else True

    def _refresh_settings(self) -> None:
        if time.monotonic() - self._settings_at > SETTINGS_TTL_SECONDS:
            try:
                self._load_settings()
            except Exception:  # noqa: BLE001 - keep the last good settings
                self._settings_at = time.monotonic()

    # ---- who already got a tip (bot database) ----
    def _load_notified(self) -> dict:
        if self._notified is None:
            try:
                raw = self.bot.db_manager.get_metadata(NOTIFIED_KEY)
                data = json.loads(raw) if raw else {}
                self._notified = {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}
            except Exception:  # noqa: BLE001
                self._notified = {}
        return self._notified

    def _remember(self, name: str, when: float) -> None:
        notified = self._load_notified()
        notified[name] = when
        cutoff = when - self.repeat_days * 86400
        for key in [k for k, t in notified.items() if t < cutoff]:
            del notified[key]
        if len(notified) > MAX_REMEMBERED:
            for key, _ in sorted(notified.items(), key=lambda kv: kv[1])[: len(notified) - MAX_REMEMBERED]:
                del notified[key]
        try:
            self.bot.db_manager.set_metadata(NOTIFIED_KEY, json.dumps(notified, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            self.bot.logger.warning("HashHint: could not save who got a tip: %s", e)

    def recently_notified(self, name: str, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return now - self._load_notified().get(_norm(name), 0.0) < self.repeat_days * 86400

    # ---- the check, for every channel message ----
    def wants_tip(self, message: Any) -> bool:
        self._refresh_settings()
        if not self.enabled or getattr(message, "is_dm", False):
            return False
        channel = _norm(getattr(message, "channel", "") or "")
        sender = (getattr(message, "sender_id", "") or "").strip()
        if not channel or channel not in self.channels or not sender:
            return False
        if sender_bytes_per_hop(message) != 1:
            return False
        own = self.bot.config.get("Bot", "bot_name", fallback="")
        if _norm(sender) == _norm(own) or _norm(sender) in self._pending:
            return False
        if self.max_hops:
            hops = _hops(message)
            if hops is None or hops > self.max_hops:
                return False
        if self.recently_notified(sender):
            return False
        if self.skip_bots:
            try:
                from .channel_hint import get_channel_hint
                if get_channel_hint(self.bot).is_other_bot(message):
                    return False
            except Exception:  # noqa: BLE001
                pass
        return True

    def observe(self, message: Any) -> bool:
        """Called for every channel message. Schedules a tip in the background; True when one was scheduled."""
        if not self.wants_tip(message):
            return False
        name = _norm(message.sender_id)
        self._pending.add(name)
        task = asyncio.ensure_future(self._tip_later(message))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _tip_later(self, message: Any) -> None:
        name = _norm(message.sender_id)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds + random.uniform(0, DELAY_JITTER_SECONDS))
            await self.send_tip(message)
        except Exception as e:  # noqa: BLE001
            self.bot.logger.warning("HashHint: tip to %s failed: %s", message.sender_id, e)
        finally:
            self._pending.discard(name)

    async def send_tip(self, message: Any) -> str:
        """Send the tip now. Returns 'dm', 'channel', 'skipped' (channel cooldown or fallback none) or 'failed'.
        The person counts as having had the tip in every case except 'skipped' by channel cooldown, so a DM that
        cannot be delivered is not retried on every message."""
        sender = (message.sender_id or "").strip()
        now = time.time()
        if self.recently_notified(sender, now):
            return "skipped"
        if self.via == "dm":
            recipient = getattr(message, "sender_pubkey", None) or sender
            ok = False
            try:
                ok = bool(await self.bot.command_manager.send_dm(
                    recipient, self.message_dm.replace("{sender}", sender), skip_user_rate_limit=True))
            except Exception as e:  # noqa: BLE001
                self.bot.logger.debug("HashHint: DM to %s failed: %s", sender, e)
            if ok:
                self._remember(_norm(sender), now)
                self.bot.logger.info("HashHint: %s sends with a 1-byte path hash, tip sent by DM", sender)
                return "dm"
            if self.dm_fallback == "none":
                self._remember(_norm(sender), now)
                self.bot.logger.info("HashHint: %s sends with a 1-byte path hash, no DM possible, nothing sent", sender)
                return "skipped"
        channel = _norm(message.channel)
        if self.channel_cooldown and now - self._last_channel.get(channel, 0.0) < self.channel_cooldown:
            return "skipped"   # someone else got a tip here a moment ago; this person gets one another time
        self._last_channel[channel] = now
        self._remember(_norm(sender), now)
        try:
            ok = bool(await self.bot.command_manager.send_channel_message(
                message.channel, self.message_channel.replace("{sender}", sender), skip_user_rate_limit=True))
        except Exception as e:  # noqa: BLE001
            self.bot.logger.warning("HashHint: tip in %s failed: %s", message.channel, e)
            ok = False
        if ok:
            self.bot.logger.info("HashHint: %s sends with a 1-byte path hash, tip sent in %s", sender, message.channel)
            return "channel"
        return "failed"


def get_hash_hint(bot: Any) -> HashHint:
    """One shared instance per bot, created on first use."""
    hint = bot.__dict__.get("_hash_hint") if hasattr(bot, "__dict__") else None
    if hint is None:
        hint = HashHint(bot)
        bot._hash_hint = hint
    return hint
