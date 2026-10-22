#!/usr/bin/env python3
"""Source patch (SaarMesh fork): upstream replies that were English on a bot set to German.

Found 2026-10-22 by running every command offline against the patched tree with language = de:
- 'help <command>': upstream commands with a hardcoded English help text. A translation key
  help_override.<command name> (only in our de.json) now wins over the command's own text.
- sun / moon / satpass: labels (SunSet, Rise, Daylight, ...), English weekdays and months and 12-hour clock;
  solar: Sunspots, X-Ray Flux, ...; hfcond: Good/Fair/Poor. German labels when [Localization] language is de.
- rain: 'Kein rain erwartet' (the asked word was put in as is), 'No snow, but ...', the German alias 'schnee'
  counted as rain; place names from the reverse geocoder came back in English ('Germany').
- aqi: the category (Good, Moderate, ...) through commands.aqi.category_names.
- dadjoke, joke, magic8: English texts from icanhazdadjoke, JokeAPI and a built-in list. On German, our own lists
  (modules/de_content.py, local_data/unterhaltung_de.py).
- cmd ('Available commands:', '(N more)'), version ('Bot version'), trace, multitest: translation keys.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


# ------------------------------------------------------------------------------------------------ help <command>
patch(
    "modules/commands/help_command.py",
    """        if command:
            # Pass message context to get_help_text if the method supports it
            if hasattr(command, 'get_help_text') and callable(command.get_help_text):""",
    """        if command:
            # (SaarMesh fork) a translated help text for a command whose own text is fixed English
            override = self.translate_get_value(f"help_override.{getattr(command, 'name', '')}")
            if isinstance(override, str) and override.strip():
                help_text = override
            # Pass message context to get_help_text if the method supports it
            elif hasattr(command, 'get_help_text') and callable(command.get_help_text):""",
)

# ------------------------------------------------------------------------------------------------ sun, moon, solar, hf
patch(
    "modules/solar_conditions.py",
    """def get_config_value(section: str, key: str, fallback: Any) -> Any:""",
    """# (SaarMesh fork) German labels, weekdays and band conditions when the bot speaks German.
_DE_LABELS = {
    "SunSet": "Untergang", "SunRise": "Aufgang", "Rise": "Aufgang", "Set": "Untergang", "Daylight": "Tageslicht",
    "Remaining": "Noch hell", "Azimuth": "Azimut", "Altitude": "Höhe", "MoonRise": "Aufgang", "Phase": "Phase",
    "FullMoon": "Vollmond", "NewMoon": "Neumond", "Sunspots": "Sonnenflecken", "X-Ray Flux": "Röntgenfluss",
    "Solar Flux": "Solarflux", "Signal Noise": "Rauschen", "Good": "gut", "Fair": "mäßig", "Poor": "schlecht",
    "Error fetching data": "Daten gerade nicht abrufbar",
}
_DE_DAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
_DE_MONTHS = ("Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez")


def _de() -> bool:
    return str(get_config_value("Localization", "language", "en")).strip().lower().startswith("de")


def _lbl(text: str) -> str:
    return _DE_LABELS.get(text, text) if _de() else text


def get_config_value(section: str, key: str, fallback: Any) -> Any:""",
)
patch(
    "modules/solar_conditions.py",
    """        return "\\n".join(f"{period[0]}{name}={condition}" for period, name, condition in rows)""",
    """        if _de():
            return "\\n".join(f"{'T' if period[0] == 'd' else 'N'}{name}={_lbl(condition)}" for period, name, condition in rows)
        return "\\n".join(f"{period[0]}{name}={condition}" for period, name, condition in rows)""",
)
patch(
    "modules/solar_conditions.py",
    """        return "\\n".join(f"{label}: {_element_text(data, tag)}" for label, tag in fields)""",
    """        return "\\n".join(f"{_lbl(label)}: {_element_text(data, tag)}" for label, tag in fields)""",
)
patch(
    "modules/solar_conditions.py",
    """    if include_month:
        pattern = "%a %b %d %H:%M" if use_24_hour else "%a %b %d %I:%M%p"
    else:
        pattern = "%a %d %H:%M" if use_24_hour else "%a %d %I:%M%p"
    return _local_datetime(value).strftime(pattern)""",
    """    if _de():
        local = _local_datetime(value)
        if include_month:   # four words, like upstream's "Sun Sep 07 11:08AM" (moon_command picks words 2-4)
            return f"{_DE_DAYS[local.weekday()]} {local.day}. {_DE_MONTHS[local.month - 1]} {local:%H:%M}"
        return f"{_DE_DAYS[local.weekday()]} {local:%H:%M}"
    if include_month:
        pattern = "%a %b %d %H:%M" if use_24_hour else "%a %b %d %I:%M%p"
    else:
        pattern = "%a %d %H:%M" if use_24_hour else "%a %d %I:%M%p"
    return _local_datetime(value).strftime(pattern)""",
)
patch(
    "modules/solar_conditions.py",
    """            lines = [
                f"SunSet: {_format_event(sunset)}",
                f"Rise: {_format_event(sunrise)}",
                f"Daylight: {daylight_hours}h {daylight_minutes}m",
                f"Remaining: {remaining_hours}h {remaining_minutes}m",
                f"Azimuth: {azimuth:.2f}°",
                f"Altitude: {altitude:.2f}°",
            ]
        else:
            lines = [
                f"SunRise: {_format_event(sunrise)}",
                f"Set: {_format_event(next_sunset)}",
                f"Daylight: {daylight_hours}h {daylight_minutes}m",
                f"Azimuth: {azimuth:.2f}°",
            ]""",
    """            lines = [
                f"{_lbl('SunSet')}: {_format_event(sunset)}",
                f"{_lbl('Rise')}: {_format_event(sunrise)}",
                f"{_lbl('Daylight')}: {daylight_hours}h {daylight_minutes}m",
                f"{_lbl('Remaining')}: {remaining_hours}h {remaining_minutes}m",
                f"{_lbl('Azimuth')}: {azimuth:.0f}°" if _de() else f"Azimuth: {azimuth:.2f}°",
                f"{_lbl('Altitude')}: {altitude:.0f}°" if _de() else f"Altitude: {altitude:.2f}°",
            ]
        else:
            lines = [
                f"{_lbl('SunRise')}: {_format_event(sunrise)}",
                f"{_lbl('Set')}: {_format_event(next_sunset)}",
                f"{_lbl('Daylight')}: {daylight_hours}h {daylight_minutes}m",
                f"{_lbl('Azimuth')}: {azimuth:.0f}°" if _de() else f"Azimuth: {azimuth:.2f}°",
            ]""",
)
patch(
    "modules/solar_conditions.py",
    """    except Exception:
        logger.exception("Solar: Error calculating Sun conditions")
        return ERROR_FETCHING_DATA""",
    """    except Exception:
        logger.exception("Solar: Error calculating Sun conditions")
        return _lbl(ERROR_FETCHING_DATA)""",
)
patch(
    "modules/solar_conditions.py",
    """def _unix_local(timestamp: int | float) -> str:
    use_24_hour = get_config_value("Solar_Config", "use_zulu_time", DEFAULT_ZULU_TIME)""",
    """def _unix_local(timestamp: int | float) -> str:
    if _de():
        local = datetime.fromtimestamp(timestamp)
        return f"{_DE_DAYS[local.weekday()]} {local:%d.%m. %H:%M}"
    use_24_hour = get_config_value("Solar_Config", "use_zulu_time", DEFAULT_ZULU_TIME)""",
)

# ------------------------------------------------------------------------------------------------ place names
patch(
    "modules/location.py",
    """        result = geolocator.reverse(f"{lat}, {lon}", timeout=timeout, language="en")""",
    """        try:
            _lang = (bot.config.get("Localization", "language", fallback="en") or "en").strip().lower()[:2]
        except Exception:  # noqa: BLE001
            _lang = "en"
        result = geolocator.reverse(f"{lat}, {lon}", timeout=timeout, language=_lang or "en")""",
)

# ------------------------------------------------------------------------------------------------ rain
patch(
    "modules/commands/rain_command.py",
    """        mode = parts[0].lower() if parts else "rain"
""",
    """        mode = parts[0].lower() if parts else "rain"
        if mode == "schnee":   # (SaarMesh fork) German alias of snow
            mode = "snow"
""",
)
patch(
    "modules/commands/rain_command.py",
    """                "commands.rain.clear", precip=asked_word or "rain",""",
    """                "commands.rain.clear", precip=self._ptype(asked_word or "rain"),""",
)
patch(
    "modules/commands/rain_command.py",
    """            ptype = f"No {asked_word}, but {self._ptype(result.bucket).lower()}\"""",
    """            ptype = self.translate("commands.rain.mismatch", asked=self._ptype(asked_word),
                                   actual=self._ptype(result.bucket).lower())""",
)

# ------------------------------------------------------------------------------------------------ aqi
patch(
    "modules/commands/aqi_command.py",
    """    def get_aqi_category(self, aqi: float) -> str:
        \"\"\"Get category name for US AQI value.""",
    """    def get_aqi_category(self, aqi: float) -> str:
        \"\"\"(SaarMesh fork) the category name in the bot's language (commands.aqi.category_names).\"\"\"
        name = self._aqi_category_en(aqi)
        names = self.translate_get_value("commands.aqi.category_names")
        return names.get(name, name) if isinstance(names, dict) else name

    def _aqi_category_en(self, aqi: float) -> str:
        \"\"\"Get category name for US AQI value.""",
)

# ------------------------------------------------------------------------------------------------ fun commands
patch(
    "modules/commands/magic8_command.py",
    """        answer = magic8()
""",
    """        answer = magic8()
        from .. import de_content   # (SaarMesh fork) German answers on a German bot
        answer = de_content.pick(self, "orakel") or answer
""",
)
patch(
    "modules/commands/dadjoke_command.py",
    """            # Get dad joke from API with length handling
            joke_data = await self.get_dad_joke_with_length_handling()""",
    """            # (SaarMesh fork) a German Flachwitz from our own list on a German bot
            from .. import de_content
            limit = self.get_max_message_length(message)
            german = de_content.pick(self, "flachwitz", fits=lambda t: len(f"🥸 {t}".encode("utf-8")) <= limit)
            if german:
                await self.send_response(message, f"🥸 {german}")
                return True

            # Get dad joke from API with length handling
            joke_data = await self.get_dad_joke_with_length_handling()""",
)
patch(
    "modules/commands/joke_command.py",
    """        content = message.content.strip()

        # Parse the command to extract category""",
    """        content = message.content.strip()

        # (SaarMesh fork) a German joke from our own list on a German bot (no categories)
        from .. import de_content
        limit = self.get_max_message_length(message)
        german = de_content.pick(self, "witz", fits=lambda t: len(f"🎭 {t}".encode("utf-8")) <= limit)
        if german:
            self.record_execution(message.sender_id)
            await self.send_response(message, f"🎭 {german}")
            return True

        # Parse the command to extract category""",
)

# ------------------------------------------------------------------------------------------------ cmd, version, trace, multitest
patch(
    "modules/commands/cmd_command.py",
    """        prefix = "Available commands: \"""",
    """        prefix = self.translate("commands.cmd.prefix")""",
)
patch(
    "modules/commands/cmd_command.py",
    """                    suffix = f" ({remaining_count} more)\"""",
    """                    suffix = self.translate("commands.cmd.more", n=remaining_count)""",
)
patch(
    "modules/commands/version_command.py",
    """        response = f"@[{sender}] Bot version: {version_value}\"""",
    """        response = self.translate("commands.version.reply", sender=sender, version=version_value)""",
)
patch(
    "modules/commands/trace_command.py",
    """            return f"{sender_str}Trace failed: {result.error_message or 'unknown'}\"""",
    """            return sender_str + self.translate("commands.trace.failed", error=result.error_message or "?")""",
)
patch(
    "modules/commands/trace_command.py",
    """                    "Trace/tracer need a path (e.g. trace 01,7a,55) or a message that has a path.",""",
    """                    self.translate("commands.trace.need_path"),""",
)
patch(
    "modules/commands/trace_command.py",
    """            await self.send_response(message, "Not connected to radio.")""",
    """            await self.send_response(message, self.translate("commands.trace.not_connected"))""",
)
patch(
    "modules/commands/trace_command.py",
    """            await self.send_response(message, "Trace not available (firmware/connection).")""",
    """            await self.send_response(message, self.translate("commands.trace.not_available"))""",
)
patch(
    "modules/commands/multitest_command.py",
    """                response = "Error: Could not find packet data for this message. Please try again.\"""",
    """                response = self.translate("commands.multitest.no_packet")""",
)

# ------------------------------------------------------------------------------------------------ cmd names, aurora time
patch(
    "modules/commands/cmd_command.py",
    """        command_names = prioritized + sorted(remaining)
""",
    """        command_names = prioritized + sorted(remaining)
        # (SaarMesh fork) the word actually typed (German on a German bot), as in help lists
        from ..help_filter import display_name
        _cmds = self.bot.command_manager.commands
        command_names = list(dict.fromkeys(display_name(n, _cmds[n]) if n in _cmds else n for n in command_names))
""",
)
patch(
    "modules/commands/aurora_command.py",
    """        local = dt_utc.astimezone(tz)
        return local.strftime("%b %d %I:%M%p")""",
    """        local = dt_utc.astimezone(tz)
        if str(self.bot.config.get("Localization", "language", fallback="en")).lower().startswith("de"):
            return local.strftime("%d.%m. %H:%M")   # (SaarMesh fork) German date and 24-hour clock
        return local.strftime("%b %d %I:%M%p")""",
)
patch(
    "modules/commands/aurora_command.py",
    """        if use_zulu or iana_str == "UTC":
            return dt_utc.strftime("%b %d ") + f"{dt_utc.hour:02d}Z\"""",
    """        if (use_zulu and not str(self.bot.config.get("Localization", "language", fallback="en")).lower().startswith("de")) \\
                or iana_str == "UTC":
            return dt_utc.strftime("%b %d ") + f"{dt_utc.hour:02d}Z\"""",
)

# 'help <command>' as answered by the command manager (the path a channel message takes)
patch(
    "modules/command_manager.py",
    """        if command:
            try:
                help_text = command.get_help_text(message)
            except TypeError:
                help_text = command.get_help_text()
            if hasattr(self.bot, 'translator'):""",
    """        if command:
            try:
                help_text = command.get_help_text(message)
            except TypeError:
                help_text = command.get_help_text()
            # (SaarMesh fork) a translated help text for a command whose own text is fixed English
            _help_cmd = self.commands.get('help')
            if _help_cmd is not None and hasattr(_help_cmd, 'translate_get_value'):
                _override = _help_cmd.translate_get_value(f"help_override.{getattr(command, 'name', '')}")
                if isinstance(_override, str) and _override.strip():
                    help_text = _override
            if hasattr(self.bot, 'translator'):""",
)
