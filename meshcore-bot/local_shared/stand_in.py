"""Stand-in ([StandIn]): the bot stands in for an old bot that is switched off.

Why: people still write "@[SaarMesh-Bot] /path" out of habit after the old bot went off. Upstream ignores a command
that mentions someone else, so nobody answered. Now the bot answers in its place:

- once per person per `repeat_hours` it says so in the channel ("@[Ve] The SaarMesh-Bot is on holiday, I'm standing
  in for it"), at most once per `channel_cooldown_minutes` per channel;
- with `answer = true` (default) the mention of the old name is turned into a mention of this bot, so the command in
  the message ("/path") is then handled as if it had been sent to this bot (normal rules: prefix, channels, hint
  channels, answer arbitration). The note goes out first, the answer after it;
- never for other bots or the bot itself, never in DMs; nothing when the message also mentions this bot already;
- in a hint channel (no commands there) no note: the channel hint answers the command attempt as usual.

Config (config.ini, card StandIn on the Plugins page):

    [StandIn]
    enabled = true
    names = SaarMesh-Bot          ; old bot names, comma-separated, as in @[...] (case does not matter)
    message =                     ; empty = standard text in the bot's language; {sender} = the name, {old} = old name
    answer = true
    repeat_hours = 12
    channel_cooldown_minutes = 2
    skip_bots = true
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Optional

SECTION = "StandIn"
NOTIFIED_KEY = "standin.notified"     # bot_metadata: {name (lower case): unix time of the note}
SETTINGS_TTL_SECONDS = 30
MAX_REMEMBERED = 2000
MAX_WAIT_S = 15

DEFAULT_TEXTS = {
    "de": "@[{sender}] Der {old} macht Urlaub, ich bin seine Vertretung \U0001F3D6\uFE0F",
    "en": "@[{sender}] {old} is on holiday, I'm standing in for it \U0001F3D6\uFE0F",
    "nl": "@[{sender}] {old} is op vakantie, ik ben de vervanger \U0001F3D6\uFE0F",
    "fr": "@[{sender}] {old} est en vacances, je le remplace \U0001F3D6\uFE0F",
    "da": "@[{sender}] {old} holder ferie, jeg er vikar \U0001F3D6\uFE0F",
}

_MENTION = re.compile(r"@\[([^\]]+)\]")


def _norm(name: str) -> str:
    return (name or "").strip().lower()


def _split(value: str) -> list:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


class StandIn:
    def __init__(self, bot: Any):
        self.bot = bot
        self._settings_at = -SETTINGS_TTL_SECONDS - 1.0
        self._last_channel: dict = {}
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
        self.names = {_norm(n) for n in _split(get("names", "SaarMesh-Bot"))}
        lang = (cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en") or "en"
        self.message = get("message", "").strip() or DEFAULT_TEXTS.get(lang.strip().lower()[:2], DEFAULT_TEXTS["en"])
        self.answer = cfg.getboolean(SECTION, "answer", fallback=True) if has else True
        self.repeat_seconds = num("repeat_hours", 12, 0, 24 * 365) * 3600
        self.channel_cooldown = num("channel_cooldown_minutes", 2, 0, 1440) * 60
        self.skip_bots = cfg.getboolean(SECTION, "skip_bots", fallback=True) if has else True

    def _refresh_settings(self) -> None:
        if time.monotonic() - self._settings_at > SETTINGS_TTL_SECONDS:
            try:
                self._load_settings()
            except Exception:  # noqa: BLE001 - keep the last good settings
                self._settings_at = time.monotonic()

    # ---- who already got the note (bot database) ----
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
        cutoff = when - max(self.repeat_seconds, 3600)
        for key in [k for k, t in notified.items() if t < cutoff]:
            del notified[key]
        if len(notified) > MAX_REMEMBERED:
            for key, _ in sorted(notified.items(), key=lambda kv: kv[1])[: len(notified) - MAX_REMEMBERED]:
                del notified[key]
        try:
            self.bot.db_manager.set_metadata(NOTIFIED_KEY, json.dumps(notified, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            self.bot.logger.warning("StandIn: could not save who got the note: %s", e)

    def recently_notified(self, name: str, now: Optional[float] = None) -> bool:
        if not self.repeat_seconds:
            return False
        now = time.time() if now is None else now
        return now - self._load_notified().get(_norm(name), 0.0) < self.repeat_seconds

    # ---- the check ----
    def old_mention(self, message: Any) -> Optional[str]:
        """The old bot name (as written) when a channel message mentions it and not this bot; else None."""
        self._refresh_settings()
        if not self.enabled or getattr(message, "is_dm", False) or not self.names:
            return None
        content = getattr(message, "content", "") or ""
        mentions = _MENTION.findall(content)
        if not mentions:
            return None
        own = self._own_names()
        if any(_norm(m) in own for m in mentions):
            return None
        for m in mentions:
            if _norm(m) in self.names:
                return m
        return None

    def _own_names(self) -> set:
        """This bot's names: the one in config.ini and the radio's own (they normally match: "Name|🤖")."""
        names = {_norm(self.bot.config.get("Bot", "bot_name", fallback=""))}
        try:
            info = getattr(getattr(self.bot, "meshcore", None), "self_info", None)
            name = info.get("name") if isinstance(info, dict) else None
            if isinstance(name, str):
                names.add(_norm(name))
        except Exception:  # noqa: BLE001
            pass
        names.discard("")
        return names

    def _is_other_bot(self, message: Any) -> bool:
        try:
            from .channel_hint import get_channel_hint
            return bool(get_channel_hint(self.bot).is_other_bot(message))
        except Exception:  # noqa: BLE001
            return False

    def _is_hint_channel(self, message: Any) -> bool:
        try:
            from .channel_hint import get_channel_hint
            return bool(get_channel_hint(self.bot).is_hint_channel(message))
        except Exception:  # noqa: BLE001
            return False

    async def handle(self, message: Any) -> str:
        """Called for every channel message before commands are matched. Returns what happened:
        'none' (not for the old bot), 'note' (note sent), 'quiet' (no note this time) - with 'answer' the message is
        rewritten in the last two cases so the command in it runs as if sent to this bot."""
        old = self.old_mention(message)
        if old is None:
            return "none"
        sender = (getattr(message, "sender_id", "") or "").strip()
        own_name = self.bot.config.get("Bot", "bot_name", fallback="")
        if not sender or _norm(sender) in self._own_names() or _norm(sender) in self.names:
            return "none"
        if self.skip_bots and self._is_other_bot(message):
            return "none"

        result = "quiet"
        now = time.time()
        channel = _norm(getattr(message, "channel", "") or "")
        if (not self._is_hint_channel(message) and not self.recently_notified(sender, now)
                and not (self.channel_cooldown and now - self._last_channel.get(channel, 0.0) < self.channel_cooldown)):
            self._last_channel[channel] = now
            self._remember(_norm(sender), now)
            text = self.message.replace("{sender}", sender).replace("{old}", old)
            kwargs = {"skip_user_rate_limit": True}
            scope = getattr(message, "reply_scope", None)
            if scope is not None:
                kwargs["scope"] = scope
            try:
                ok = bool(await self.bot.command_manager.send_channel_message(message.channel, text, **kwargs))
            except Exception as e:  # noqa: BLE001
                self.bot.logger.warning("StandIn: note in %s failed: %s", message.channel, e)
                ok = False
            if ok:
                result = "note"
                self.bot.logger.info("StandIn: %s wrote to %s in %s, note sent", sender, old, message.channel)

        if self.answer and own_name:
            message.content = message.content.replace(f"@[{old}]", f"@[{own_name}]")
            if result == "note":
                await self._wait_for_rate_limit()
        return result

    async def _wait_for_rate_limit(self) -> None:
        """The note counts in the bot's global send limit (rate_limit_seconds) even though it skips the check itself,
        so the answer right after it would be dropped ("Rate limited. Wait 2.0 seconds", 26-10-2026). Wait until the
        limit allows the next message (at most MAX_WAIT_S)."""
        try:
            wait = float(self.bot.rate_limiter.time_until_next() or 0)
        except Exception:  # noqa: BLE001
            return
        if wait > 0:
            await asyncio.sleep(min(wait + 0.3, MAX_WAIT_S))


def get_stand_in(bot: Any) -> StandIn:
    """One shared instance per bot, created on first use."""
    s = bot.__dict__.get("_stand_in") if hasattr(bot, "__dict__") else None
    if s is None:
        s = StandIn(bot)
        bot._stand_in = s
    return s
