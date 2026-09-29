#!/usr/bin/env python3
"""
'whois' command for the MeshCore Bot.
Contact card for a known node: name, role, last seen, hops, location - looked
up from the bot's own 'complete_contact_tracking' table (populated from every
advert the bot has ever seen, not just repeaters).
"""

from datetime import datetime
from typing import Any, Optional

from ..models import MeshMessage
from .base_command import BaseCommand


class WhoisCommand(BaseCommand):
    """Looks up a known contact by (partial) name or public-key prefix."""

    name = "whois"
    keywords = ["whois"]
    description = "Contact card of a known node (usage: whois <name or key>)"
    category = "mesh"

    short_description = "Contact card of a known node"
    usage = "whois <naam of sleutel-prefix>"
    examples = ["whois Pluto", "whois a1b2c3"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.whois_enabled = self.get_config_value(
            "Whois_Command", "enabled", fallback=True, value_type="bool"
        )

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.whois_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.whois.help")

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _ago(self, dt: Optional[datetime]) -> str:
        if dt is None:
            return self.translate("commands.whois.unknown")
        delta = datetime.now() - dt
        seconds = int(delta.total_seconds())
        if seconds < 0:
            seconds = 0
        if seconds < 60:
            return self.translate("commands.whois.just_now")
        minutes = seconds // 60
        if minutes < 60:
            return self.translate("commands.whois.minutes_ago", n=minutes)
        hours = minutes // 60
        if hours < 24:
            return self.translate("commands.whois.hours_ago", n=hours)
        days = hours // 24
        return self.translate("commands.whois.days_ago", n=days)

    def _level(self, name: Optional[str]) -> str:
        """Mesh RPG level and title of a person (not of a bot, not without XP); empty when there is nothing to show."""
        try:
            from ..mesh_archive import xp_of
            from ..mesh_community import is_bot_name
            if not name or is_bot_name(self.bot, name):
                return ""
            info = xp_of(self.bot, name)
            if not info or not info.get("xp"):
                return ""
            return self.translate("commands.whois.level", level=info["level"], title=self.translate(f"commands.xp.title.{info['title']}"),
                                  xp=info["xp"])
        except Exception:  # noqa: BLE001 - the contact card works without the games
            return ""

    async def execute(self, message: MeshMessage) -> bool:
        try:
            content = message.content.strip()
            if content.lower().startswith("whois"):
                content = content[len("whois"):].strip()

            if not content:
                return await self.send_response(
                    message, self.translate("commands.whois.usage")
                )

            like_pattern = f"%{content}%"
            with self.bot.db_manager.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT name, public_key, role, device_type, last_heard,
                           hop_count, advert_count, city, state, country
                    FROM complete_contact_tracking
                    WHERE name LIKE ? OR public_key LIKE ?
                    ORDER BY last_heard DESC
                    LIMIT 3
                    """,
                    (like_pattern, like_pattern),
                )
                rows = cursor.fetchall()

            if not rows:
                return await self.send_response(
                    message, self.translate("commands.whois.not_found", query=content)
                )

            lines = []
            for row in rows:
                (name, public_key, role, device_type, last_heard,
                 hop_count, advert_count, city, state, country) = row

                short_key = (public_key or "")[:12]
                ago = self._ago(self._parse_timestamp(last_heard))

                bits = [f"{name or '?'} ({short_key})"]
                if role:
                    bits.append(role)
                if hop_count is not None:
                    hop_key = "commands.whois.hop" if hop_count == 1 else "commands.whois.hops"
                    bits.append(self.translate(hop_key, n=hop_count))
                bits.append(self.translate("commands.whois.last_seen", ago=ago))
                location_bits = [b for b in (city, state, country) if b]
                if location_bits:
                    bits.append(", ".join(location_bits))
                level = self._level(name)
                if level:
                    bits.append(level)

                lines.append(" | ".join(bits))

            response = "\n".join(lines)
            return await self.send_response(message, response)
        except Exception as e:
            self.logger.error(f"Error executing whois command: {e}")
            return await self.send_response(message, self.translate("commands.whois.error", error=str(e)))
