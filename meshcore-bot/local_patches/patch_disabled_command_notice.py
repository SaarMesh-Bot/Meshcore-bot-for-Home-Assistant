#!/usr/bin/env python3
"""Source patch: a command that is switched off stays silent.

Until 2.51.4 this patch made the bot answer "Sorry, '<command>' staat momenteel uit - er wordt aan gewerkt!" (always
in Dutch) when someone used a command switched off on the Plugins page. Users would rather have no answer at all
(issue #1, 2026-10-06): a switched-off command now behaves as if it does not exist. Also for the commands that would
still speak up on their own (stats: "Stats command is disabled"; DM-only ones: "can only be used in DMs"). The
trigger is not claimed, so another command with the same word (an alias) can still answer.

Off = the command's own flag (`self.<name>_enabled`, every toggleable plugin has one) or `enabled = false` in its
[Xxx_Command] section.
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


patch(
    "modules/command_manager.py",
    """            if command.should_execute(message):
                # Only execute commands that don't have a response format (they handle their own responses)""",
    """            if command.should_execute(message):
                # (add-on) switched off on the Plugins page: stay silent, as if the command did not exist
                try:
                    _off = getattr(command, f"{command.name}_enabled", True) is False
                    if not _off:
                        _sec = command._derive_config_section_name()
                        _off = (self.bot.config.has_section(_sec)
                                and not self.bot.config.getboolean(_sec, "enabled", fallback=True))
                except Exception:  # noqa: BLE001
                    _off = False
                if _off:
                    self.logger.debug(f"Command '{command_name}' is switched off; staying silent")
                    continue
                # Only execute commands that don't have a response format (they handle their own responses)""",
)
