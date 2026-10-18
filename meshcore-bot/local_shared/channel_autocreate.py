"""Missing hashtag channels are made on the radio (card: Plugins -> AutoChannels, on by default).

The bot only hears and answers in channels that are on its radio. Hashtag channels (#test, #games, #f1, ...) need no
key to share: the firmware derives it from the name. So when a hashtag channel the bot is set to use is missing on the
radio, this puts it in the first free slot, once, and the bot uses it at once.

Which channels: the hashtag names in Bot > Channels to listen on ([Channels] monitor_channels), the games channel
(GamesChannel card) and the F1 channel (F1 card), each only when its card is on. Private channels (no #) are never made:
they need their own key. Nothing is ever removed or overwritten.

Safe against a busy radio: upstream's channel scan counts a timeout as an empty slot, so a missing channel may just be
one the radio did not report in time. Before making anything, every slot that is not known is asked again, and only
a slot the radio really reports as empty is used; when the radio does not answer, nothing is made and the next check
tries again.
"""
from __future__ import annotations

import asyncio
from typing import Any

FETCH_TIMEOUT_S = 6.0


def _names(raw: str) -> list:
    return [n.strip() for n in str(raw or "").replace(";", ",").split(",") if n.strip()]


def _on(cfg: Any, section: str) -> bool:
    return cfg.has_section(section) and cfg.getboolean(section, "enabled", fallback=False)


def wanted_channels(bot: Any) -> list:
    """The hashtag channels the bot is set to use, lower case, in order, without doubles."""
    cfg = bot.config
    names = _names(cfg.get("Channels", "monitor_channels", fallback="")) if cfg.has_section("Channels") else []
    if _on(cfg, "GamesChannel"):
        names += _names(cfg.get("GamesChannel", "channel", fallback=""))
    if _on(cfg, "F1"):
        names += _names(cfg.get("F1", "channel", fallback="#f1"))
    try:   # channels asked for on the radar page ('Add to radio')
        from .channel_radar import add_to_radio_requests
        names += add_to_radio_requests(bot.db_manager)
    except Exception:  # noqa: BLE001
        pass
    out = []
    for n in names:
        n = n.lower()
        if n.startswith("#") and len(n) > 1 and n not in out:
            out.append(n)
    return out


def _norm(name: str) -> str:
    return str(name or "").strip().lower()


async def _ask(bot: Any, idx: int):
    """(answered, name) for one slot: answered False = timeout or no answer (radio busy)."""
    try:
        res = await asyncio.wait_for(bot.meshcore.commands.get_channel(idx), timeout=FETCH_TIMEOUT_S)
    except Exception:  # noqa: BLE001 - timeout or connection trouble: do not guess
        return False, None
    kind = str(getattr(res, "type", "")).lower()
    if "error" in kind:
        return True, None          # beyond the radio's last slot
    payload = getattr(res, "payload", None) or {}
    return True, str(payload.get("channel_name") or "").strip()


async def ensure_channels(bot: Any, logger: Any) -> list:
    """Make the wanted hashtag channels that are missing. Returns the names made."""
    cm = getattr(bot, "channel_manager", None)
    commands = getattr(getattr(bot, "meshcore", None), "commands", None)
    if cm is None or commands is None or not hasattr(commands, "get_channel"):
        return []
    missing = [n for n in wanted_channels(bot) if cm.get_channel_number(n) is None]
    if not missing:
        return []
    made = []
    for idx in range(1, cm.max_channels):
        if not missing:
            break
        if idx in cm._channels_cache:
            continue
        answered, name = await _ask(bot, idx)
        if not answered:
            logger.info("Kanalen: de radio antwoordde niet over slot %s, niets aangemaakt (volgende keer opnieuw)", idx)
            return made
        if name is None:
            break                  # no more slots on this radio
        if name:
            # the scan had missed this one: it is there after all
            if _norm(name) in missing:
                missing.remove(_norm(name))
            continue
        target = missing.pop(0)
        if await cm.add_hashtag_channel(idx, target):
            logger.info("Kanalen: %s ontbrak op de radio, aangemaakt in slot %s", target, idx)
            made.append(target)
        else:
            logger.warning("Kanalen: %s aanmaken in slot %s mislukt", target, idx)
            return made
    if missing:
        logger.warning("Kanalen: geen vrij slot meer op de radio voor %s", ", ".join(missing))
    return made
