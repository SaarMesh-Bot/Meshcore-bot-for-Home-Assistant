#!/usr/bin/env python3
"""Source patch: only the closest bot of the bot network answers (see modules/answer_arbitration.py).

Just before a command runs for a channel message, the bot asks the bot network whether another bot of this add-on
heard the same command closer to the person (fewest hops, then best signal). If so, this bot stays silent. Only for the
commands on the BotNetwork card; without the broker, or with no other network bot online, nothing changes.
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
    """                try:
                    # Record execution time for cooldown tracking
                    if hasattr(command, '_record_execution') and callable(command._record_execution):""",
    """                # (add-on) bot network: when another bot of this add-on heard this command closer, it answers
                if not message.is_dm:
                    try:
                        from modules.answer_arbitration import should_answer
                        if not await should_answer(self.bot, message, command_name):
                            return
                    except Exception as e:
                        self.logger.debug(f"Botnetwerk: wie-antwoordt-controle overgeslagen: {e}")

                try:
                    # Record execution time for cooldown tracking
                    if hasattr(command, '_record_execution') and callable(command._record_execution):""",
)
