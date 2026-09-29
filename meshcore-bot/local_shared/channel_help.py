"""Help in a channel with its own commands: `help` in #f1 shows only the f1 help.

A command whose card lists channels of its own (Plugins -> f1 -> Channels = #f1) works in that channel even though the
channel is not one of the bot's normal command channels. `help` itself does not work there, so upstream stayed silent
and the channel hint pointed people elsewhere. Now `help` (with or without a word after it) in such a channel answers
with the help of exactly the commands that work there. Channels without commands of their own are unchanged.
"""

from typing import Any

from .help_filter import display_name, is_public_command


def channel_help_text(command_manager: Any, message: Any) -> str:
    """The help of the commands this channel has of its own, or '' when it has none."""
    if getattr(message, "is_dm", True) or not getattr(message, "channel", None):
        return ""
    channel = message.channel.lower().strip()
    texts = []
    for name, cmd in command_manager.commands.items():
        allowed = getattr(cmd, "allowed_channels", None)
        if not allowed:   # None = the normal command channels, [] = DM only
            continue
        if channel not in {c.lower().strip() for c in allowed}:
            continue
        try:
            if not is_public_command(name, cmd) or not cmd.is_channel_allowed(message):
                continue
            text = (cmd.get_help_text() or "").strip()
            word = display_name(name, cmd)
            if text and not text.lower().startswith(word.lower()):
                text = f"{getattr(cmd, 'usage', '') or word}: {text}"   # say which word to type
        except Exception:   # one broken command must not break help
            continue
        if text and text not in texts:
            texts.append(text)
    return " | ".join(texts)
