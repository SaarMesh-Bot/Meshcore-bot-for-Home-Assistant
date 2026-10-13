#!/usr/bin/env python3
"""Source patch: the greeting as a direct message instead of in the channel (Greeter card, "Send the greeting as").

Wish 2026-10-04: a greeting in a busy public channel is noise for everyone else; a DM reaches only the new person.
Default since 2.51.7 is "dm". A channel message carries only the sender's name, not their key, so the DM goes to the
contact on the radio with that name (as the dm, farm and post commands do); the new person must also have the bot as
a contact to read it. When the DM cannot be sent (name not in the radio's contacts) the card decides: greet in the
channel after all (default) or send nothing. The person is marked as greeted either way, so a failed DM is never retried
on every message.
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


F = "modules/commands/greeter_command.py"

patch(
    F,
    """        {"key": "auto_backfill", "label": "Auto-backfill greeted users", "type": "bool",""",
    """        {"key": "greet_via", "label": "Send the greeting as", "type": "enum", "default": "dm",
         "options": [{"value": "dm", "label": "A direct message to the new person"},
                     {"value": "channel", "label": "A message in the channel"}],
         "help": "A DM reaches only the new person and keeps the channel quiet. It needs the person in the radio's contacts (and the bot in theirs to read it)."},
        {"key": "dm_fallback", "label": "When the DM cannot be sent", "type": "enum", "default": "channel",
         "options": [{"value": "channel", "label": "Greet in the channel after all"},
                     {"value": "none", "label": "Send nothing"}],
         "help": "Only with 'Send the greeting as' = DM. The person counts as greeted either way, so the bot never tries again."},
        {"key": "auto_backfill", "label": "Auto-backfill greeted users", "type": "bool",""",
)

patch(
    F,
    """            success = await self.send_response_chunked(message, greeting_parts)
""",
    """            # (add-on) as a DM to the new person when the card says so (patch_greeter_dm.py)
            success = None
            if not getattr(message, 'is_dm', False) and self._greet_option('greet_via', 'dm') == 'dm':
                success = await self._greet_by_dm(message, greeting_parts)
                if not success:
                    if self._greet_option('dm_fallback', 'channel') == 'none':
                        self.logger.info(f"Greeter: no DM possible to {message.sender_id}, nothing sent (card: send nothing)")
                        return False
                    self.logger.info(f"Greeter: no DM possible to {message.sender_id}, greeting in the channel instead")
                    success = None
            if success is None:
                success = await self.send_response_chunked(message, greeting_parts)
""",
)

patch(
    F,
    """    async def _send_greeting(self, message: MeshMessage) -> bool:""",
    """    def _greet_option(self, key: str, default: str) -> str:
        try:
            value = self.get_config_value('Greeter_Command', key, fallback=default) or default
        except Exception:  # noqa: BLE001 - no config: the default
            value = default
        return str(value).strip().lower()

    async def _greet_by_dm(self, message: MeshMessage, parts: list) -> bool:
        \"\"\"The greeting as DM(s) to the contact with the sender's name (or key); False when that is not possible.\"\"\"
        recipient = getattr(message, 'sender_pubkey', None) or (message.sender_id or '').strip()
        if not recipient or not parts:
            return False
        try:
            for i, part in enumerate(parts):
                ok = await self.bot.command_manager.send_dm(recipient, part, skip_user_rate_limit=True)
                if not ok:
                    return i > 0          # a first part that failed = no DM at all; a later one = partly sent
        except Exception as e:  # noqa: BLE001
            self.logger.debug(f"Greeter: DM to {message.sender_id} failed: {e}")
            return False
        self.logger.info(f"Greeter: greeted {message.sender_id} by DM ({len(parts)} part(s))")
        return True

    async def _send_greeting(self, message: MeshMessage) -> bool:""",
)
