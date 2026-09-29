"""Games channel: the game commands only in one channel (card: Plugins -> GamesChannel).

With the card switched on and a channel filled in, the commands on the card's list (quiz, hangman, stem, ...) only run in
that channel; elsewhere they stay silent, or answer with a short pointer to the games channel when that is switched on
(at most once per 30 minutes per channel). Direct messages always work. XP keeps counting in every channel: the bot
still records every message, only the game commands are held back. Lookups such as xp, dx, badge and topu are not games
and work everywhere (unless you put them on the list).

Hooks (local_patches/patch_games_channel.py): BaseCommand.is_channel_allowed asks games_verdict(); the command manager
calls send_pointer() when a game command was held back.

Config (config.ini):

    [GamesChannel]
    enabled = false
    channel = #games
    commands = quiz,hangman,poll,peiling,checkin,karma,voorspel
    pointer = false
"""
from __future__ import annotations

import time
from typing import Any, Optional

SECTION = "GamesChannel"
DEFAULT_COMMANDS = ["quiz", "hangman", "poll", "peiling", "checkin", "karma", "voorspel", "farm"]
POINTER_EVERY_S = 1800
_last_pointer: dict = {}   # channel -> when the last pointer went out


def _norm(channel: Optional[str]) -> str:
    return (channel or "").strip().lower()


def settings(bot: Any) -> Optional[dict]:
    """{channel, commands, pointer} when the card is on and has a channel, else None."""
    cfg = bot.config
    if not cfg.has_section(SECTION) or not cfg.getboolean(SECTION, "enabled", fallback=False):
        return None
    channel = _norm(cfg.get(SECTION, "channel", fallback=""))
    if not channel:
        return None
    raw = cfg.get(SECTION, "commands", fallback=",".join(DEFAULT_COMMANDS))
    commands = {c.strip().lower() for c in str(raw).split(",") if c.strip()}
    return {"channel": channel, "commands": commands, "pointer": cfg.getboolean(SECTION, "pointer", fallback=False)}


def games_verdict(command: Any, message: Any) -> Optional[bool]:
    """None when the games channel does not apply to this command/message; else whether it may run here."""
    try:
        s = settings(command.bot)
    except Exception:  # noqa: BLE001 - never block commands because of a bad setting
        return None
    if s is None or getattr(message, "is_dm", False):
        return None
    if str(getattr(command, "name", "") or "").lower() not in s["commands"]:
        return None
    return _norm(getattr(message, "channel", "")) == s["channel"]


def held_back(command: Any, message: Any) -> bool:
    return games_verdict(command, message) is False


async def send_pointer(bot: Any, message: Any, now: Optional[float] = None) -> bool:
    """'Games are played in #games' in the channel where a game command was held back; at most every 30 minutes."""
    s = settings(bot)
    if s is None or not s["pointer"]:
        return False
    now = time.time() if now is None else now
    channel = _norm(getattr(message, "channel", ""))
    last = _last_pointer.get(channel)
    if last is not None and now - last < POINTER_EVERY_S:
        return False
    _last_pointer[channel] = now
    translator = getattr(bot, "translator", None)
    text = (translator.translate("commands.games.pointer", channel=s["channel"]) if translator
            else f"Games are played in {s['channel']}")
    return bool(await bot.command_manager.send_channel_message(message.channel, text))
