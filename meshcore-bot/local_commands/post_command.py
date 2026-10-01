#!/usr/bin/env python3
"""
'post' command for the MeshCore Bot: the mailbox (see modules/mailbox.py). Leave a message for someone who is not
around; the bot sends it by DM as soon as it hears that person again.

  post <name> <text>         leave a message (names with spaces: post @[Dirk Jan] text)
  post                       your messages that are still waiting
"""

from typing import Any

from .. import mailbox
from ..mesh_community import is_bot_name
from ..models import MeshMessage
from .base_command import BaseCommand


class PostCommand(BaseCommand):
    """Mailbox: a message for someone who is not around, delivered by DM when the bot hears them again."""

    name = "post"
    keywords = ["post", "brief", "mail", "courrier"]
    description = "Mailbox: leave a message for someone; the bot sends it by DM as soon as it hears them again (7 days)"
    category = "general"

    short_description = "Leave a message for someone (mailbox)"
    usage = "post <name> <text>"
    examples = ["post Bob ik ben er zaterdag", "post @[Dirk Jan] bel je me?", "post"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.post_enabled = self.get_config_value("Post_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.post_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.post.help")

    async def execute(self, message: MeshMessage) -> bool:
        try:
            _trigger, rest = self.split_trigger_and_args(message.content)
            sender = (message.sender_id or "").strip()
            key = (message.sender_pubkey or "").lower() if message.is_dm else None
            if not (rest or "").strip():
                waiting = mailbox.waiting_from(self.bot.db_manager, sender, key)
                if not waiting:
                    return await self.send_response(message, self.translate("commands.post.none_waiting"))
                items = ", ".join(f"{n} ({mailbox.ago(c, self.translate)})" for n, c in waiting)
                return await self.send_response(message, self.translate("commands.post.waiting", items=items))
            to_name, text = mailbox.split_recipient(rest)
            if not to_name or not text:
                return await self.send_response(message, self.translate("commands.post.usage"))
            if is_bot_name(self.bot, to_name):
                return await self.send_response(message, self.translate("commands.post.no_bots"))
            via = "DM" if message.is_dm else (message.channel or "?")
            result, _mid = mailbox.add(self.bot.db_manager, sender, key, to_name, text, via)
            if result != "ok":
                return await self.send_response(message, self.translate(f"commands.post.refused.{result}", name=to_name[:30],
                                                                        n=mailbox.MAX_PENDING, days=mailbox.KEEP_DAYS))
            return await self.send_response(message, self.translate("commands.post.saved", name=to_name[:30],
                                                                    days=mailbox.KEEP_DAYS))
        except Exception as e:
            self.logger.error(f"Error executing post command: {e}", exc_info=True)
            return await self.send_response(message, self.translate("commands.post.error"))
