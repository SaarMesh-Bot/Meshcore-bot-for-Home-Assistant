"""First-start wizard (dashboard: Settings -> Setup): the few choices a new owner has to make, on one page.

1. Channels: which channels on the radio the bot answers in (the add-on option Bot > Channels, written through the
   Supervisor), and which busy public channel only gets a pointer (ChannelHint) and a welcome (greeter).
2. Command groups: games, Germany lookups, weather and space, fun, Formula 1 - each on or off at once.
3. Extras: games channel, night mode, bot network, repeater watch, Home Assistant sensors.

A new installation shows a banner on every dashboard page until the wizard is finished ([Setup] done = false, seeded by
generate_config.py only for a new installation). Everything the wizard writes is also on the cards, and the wizard can
be run again at any time.
"""
from __future__ import annotations

from typing import Any, Optional

GROUPS = {
    "games": ["dx", "xp", "badge", "karma", "checkin", "voorspel", "peiling", "poll", "quiz", "hangman", "farm", "dice",
              "roll", "magic8", "prikbord"],
    "nlbe": ["noodnummers", "aed", "warnung", "pegel", "odl", "laadpaal", "feestdag"],
    "weather": ["wx", "vorhersage", "rain", "aqi", "sun", "moon", "aurora", "solar", "hfcond", "solarforecast", "satpass", "alert", "airplanes"],
    "fun": ["weetje", "quote", "joke", "dadjoke", "morse", "hacker", "catfact", "sports"],
    "f1": ["f1"],
}
# services that follow a command group
GROUP_SERVICES = {"f1": ["F1"]}
# extras: card section -> key in the wizard
FEATURES = {"night": "NightMode", "botnet": "BotNetwork", "repeaterwatch": "RepeaterWatch", "hasensors": "HASensors"}


def _split(raw: Any) -> list:
    return [n.strip() for n in str(raw or "").strip("[]").replace("'", "").split(",") if n.strip()]


def _on(config: Any, section: str) -> bool:
    return config.has_section(section) and config.getboolean(section, "enabled", fallback=False)


def is_done(config: Any) -> bool:
    return not config.has_section("Setup") or config.getboolean("Setup", "done", fallback=True)


def state(plugins: list, config: Any, radio: list) -> dict:
    """What the wizard shows: the current choices. plugins = the Plugins page's list ({name, kind, section, enabled})."""
    by_name = {p["name"]: p for p in plugins if p.get("kind") == "command"}
    groups = {}
    for g, names in GROUPS.items():
        present = [by_name[n] for n in names if n in by_name]
        groups[g] = {"on": bool(present) and sum(1 for p in present if p["enabled"]) * 2 >= len(present),
                     "commands": [p["name"] for p in present]}
    bot_channels = _split(config.get("Channels", "monitor_channels", fallback="")) if config.has_section("Channels") else []
    hint = _split(config.get("ChannelHint", "channels", fallback="")) if _on(config, "ChannelHint") else []
    games = (config.get("GamesChannel", "channel", fallback="") or "").strip() if _on(config, "GamesChannel") else ""
    return {
        "done": is_done(config),
        "radio_channels": radio,
        "bot_channels": bot_channels,
        "public": hint[0] if hint else "",
        "greeter": _on(config, "Greeter_Command"),
        "groups": groups,
        "games_channel": games,
        "features": {k: _on(config, section) for k, section in FEATURES.items()},
    }


def plan(data: dict, plugins: list, config: Any) -> tuple:
    """(updates {section: {key: value}}, new bot channels or None, restart needed) for the wizard's answers."""
    by_name = {p["name"]: p for p in plugins if p.get("kind") == "command"}
    updates: dict = {}
    restart = False

    def put(section: str, key: str, value: str) -> None:
        updates.setdefault(section, {})[key] = value

    for g, names in GROUPS.items():
        if g not in (data.get("groups") or {}):
            continue
        on = bool(data["groups"][g])
        for n in names:
            if n in by_name:
                put(by_name[n]["section"], "enabled", "true" if on else "false")
        for section in GROUP_SERVICES.get(g, []):
            if _on(config, section) != on:
                restart = True
            put(section, "enabled", "true" if on else "false")

    channels: Optional[list] = None
    if "bot_channels" in data:
        channels = [c for c in dict.fromkeys(str(c).strip() for c in data["bot_channels"]) if c]
    games = str(data.get("games_channel") or "").strip()
    if "games_channel" in data:
        if games:
            if not games.startswith("#"):
                games = "#" + games
            put("GamesChannel", "enabled", "true")
            put("GamesChannel", "channel", games.lower())
            if channels is not None and games.lower() not in [c.lower() for c in channels]:
                channels.append(games.lower())   # the bot must listen there too (AutoChannels makes it on the radio)
        else:
            put("GamesChannel", "enabled", "false")
        if _on(config, "GamesChannel") != bool(games):
            restart = True

    if "public" in data:
        public = str(data.get("public") or "").strip()
        where = [c for c in (channels or []) if c.startswith("#")]
        if public:
            put("ChannelHint", "enabled", "true")
            put("ChannelHint", "channels", public)
            if where:
                put("ChannelHint", "where", ",".join(where))
            if channels is not None:
                channels = [c for c in channels if c.lower() != public.lower()]   # a hint channel runs no commands
        else:
            put("ChannelHint", "enabled", "false")
        if _on(config, "ChannelHint") != bool(public):
            restart = True
        if "greeter" in data:
            put("Greeter_Command", "enabled", "true" if data["greeter"] and public else "false")
            if data["greeter"] and public:
                put("Greeter_Command", "channels", public)

    for key, section in FEATURES.items():
        if key in (data.get("features") or {}):
            on = bool(data["features"][key])
            if _on(config, section) != on:
                restart = True
            put(section, "enabled", "true" if on else "false")

    put("Setup", "done", "true")
    if channels is not None:
        old = _split(config.get("Channels", "monitor_channels", fallback="")) if config.has_section("Channels") else []
        if [c.lower() for c in old] == [c.lower() for c in channels]:
            channels = None
        else:
            restart = True
    return updates, channels, restart
