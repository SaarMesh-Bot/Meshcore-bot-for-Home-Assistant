#!/usr/bin/env python3
"""
'discover' command for the MeshCore Bot: the repeaters the bot's radio hears directly (0 hops), best signal first.

People type "discover" in #bot as they know it from the firmware's discover.neighbors. This command sends nothing over
the radio: it answers from what neighbour discovery (PacketCapture / BotNetwork card) already found in the last 7
days. A fresh scan by DM: neighbors (15 minutes cooldown).
"""

from typing import Any

from ..models import MeshMessage
from .base_command import BaseCommand

MAX_BYTES = 130
DAYS = 7


def direct_neighbours(db: Any, days: int = DAYS) -> list:
    """[(name, snr)] of the repeaters heard directly in the last `days` days, best last SNR first."""
    with db.connection() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "neighbor_links" not in tables:
            return []
        rows = conn.execute("SELECT neighbor_public_key, last_snr FROM neighbor_links WHERE last_seen >= datetime('now', ?)",
                            (f"-{int(days)} day",)).fetchall()
        names = {}
        if "complete_contact_tracking" in tables:
            for key, name in conn.execute("SELECT public_key, name FROM complete_contact_tracking WHERE name IS NOT NULL"):
                names[str(key).lower()[:12]] = name
    out = []
    for key, snr in rows:
        k = str(key).lower()
        out.append(((names.get(k[:12]) or k[:6]).strip(), snr))
    out.sort(key=lambda r: (r[1] is None, -(r[1] or 0)))
    return out


class DiscoverCommand(BaseCommand):
    """Direct neighbours of the bot's radio, from the neighbour-discovery data (no transmission)."""

    name = "discover"
    keywords = ["nachbarn", "discover", "buren", "voisins"]
    description = "The repeaters the bot's radio hears directly (0 hops), best signal first; sends nothing over the radio"
    category = "meshcore_info"

    short_description = "Repeaters the bot hears directly"
    usage = "discover"
    examples = ["discover"]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.discover_enabled = self.get_config_value("Discover_Command", "enabled", fallback=True, value_type="bool")

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.discover_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.discover.help")

    def answer(self) -> str:
        rows = direct_neighbours(self.bot.db_manager)
        if not rows:
            return self.translate("commands.discover.none")
        parts = [f"{name[:18]} {snr:+.0f}dB" if snr is not None else name[:18] for name, snr in rows]
        for n in range(len(parts), 0, -1):
            text = self.translate("commands.discover.result", n=len(rows), list=", ".join(parts[:n]) + ("…" if n < len(parts) else ""))
            if len(text.encode()) <= MAX_BYTES:
                return text
        return self.translate("commands.discover.result", n=len(rows), list=parts[0][:40])

    async def execute(self, message: MeshMessage) -> bool:
        try:
            return await self.send_response(message, self.answer())
        except Exception as e:
            self.logger.error(f"Error executing discover command: {e}")
            return await self.send_response(message, self.translate("commands.discover.none"))
