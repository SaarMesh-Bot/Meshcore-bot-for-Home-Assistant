"""Night mode: keep the messages the bot sends on its own quiet at night (card: Plugins -> NightMode).

Checked right before such a message would go out (patched in by local_patches/patch_night_mode.py):
- scheduled messages (dashboard Schedule page): a message due at night is skipped;
- feeds: feed items queued at night are skipped (marked handled, so they do not all come out in the morning);
- the incoming webhook (Home Assistant -> mesh): only when switched on for it; the webhook then answers 200 with
  {"skipped": "night mode"}.
Answers to people (commands, DMs, the greeter, the channel hint) are never affected: someone who asks at night still
gets an answer. The settings are read on every check, so a change on the card applies at once.

Config (config.ini):

    [NightMode]
    enabled = false
    start = 23:00          ; local time (Bot -> Time zone), may run past midnight
    end = 07:00
    scheduled = true       ; scheduled messages
    feeds = true
    webhook = false
"""
from __future__ import annotations

import re
from typing import Any, Optional

SECTION = "NightMode"
KINDS = {"scheduled": True, "feeds": True, "webhook": False}   # default per kind


def _minutes(text: str, fallback: int) -> int:
    m = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", str(text or ""))
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return fallback
    return int(m.group(1)) * 60 + int(m.group(2))


def window(bot: Any) -> Optional[tuple]:
    """(start, end) in minutes after midnight when night mode is on, else None."""
    cfg = bot.config
    if not cfg.has_section(SECTION) or not cfg.getboolean(SECTION, "enabled", fallback=False):
        return None
    start = _minutes(cfg.get(SECTION, "start", fallback="23:00"), 23 * 60)
    end = _minutes(cfg.get(SECTION, "end", fallback="07:00"), 7 * 60)
    return None if start == end else (start, end)


def is_night(bot: Any, now_ts: Optional[float] = None) -> bool:
    span = window(bot)
    if span is None:
        return False
    from .mesh_community import local_now
    now = local_now(bot, now_ts)
    minute = now.hour * 60 + now.minute
    start, end = span
    return start <= minute < end if start < end else (minute >= start or minute < end)


def quiet(bot: Any, kind: str, now_ts: Optional[float] = None) -> bool:
    """True when a message of this kind (scheduled, feeds, webhook) must not be sent now."""
    try:
        if kind not in KINDS or not bot.config.getboolean(SECTION, kind, fallback=KINDS[kind]):
            return False
        return is_night(bot, now_ts)
    except Exception:  # noqa: BLE001 - never block sending because of a bad setting
        return False
