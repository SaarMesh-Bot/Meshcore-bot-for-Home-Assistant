"""German content for the fun commands (SaarMesh fork).

The upstream dadjoke, joke and magic8 commands (and our quiz) answer with English texts from icanhazdadjoke, JokeAPI,
a built-in English list and OpenTDB. When the reply language is German (the bot's language, or the sender's with
AutoLanguage on), these helpers hand out lines from local_data/unterhaltung_de.py instead. Each list is played in a
shuffled order, so nothing repeats until the whole list has been used.
"""

import random
from typing import Any, Optional

from .local_data import unterhaltung_de as U

_LISTS = {"flachwitz": U.FLACHWITZE, "witz": U.WITZE, "orakel": U.ORAKEL, "quiz": U.QUIZ}
_queues: dict = {}


def reply_language(command: Any) -> str:
    """'de', 'en', ... : the language this command answers in right now."""
    tr = getattr(command, "response_translator", None) or getattr(getattr(command, "bot", None), "translator", None)
    lang = getattr(tr, "language", None)
    if not lang:
        try:
            lang = command.bot.config.get("Localization", "language", fallback="en")
        except Exception:  # noqa: BLE001
            lang = "en"
    return str(lang or "en").strip().lower()[:2]


def is_german(command: Any) -> bool:
    return reply_language(command) == "de"


def pick(command: Any, kind: str, fits: Optional[Any] = None) -> Optional[Any]:
    """The next item of list `kind` when the command answers in German, else None. `fits(item)` can skip items that
    do not fit the message (they stay in the list for a later, roomier message such as a DM)."""
    if not is_german(command):
        return None
    items = _LISTS[kind]
    queue = _queues.setdefault(kind, [])
    for _ in range(len(items) * 2):
        if not queue:
            queue.extend(random.sample(range(len(items)), len(items)))
        item = items[queue.pop()]
        if fits is None or fits(item):
            return item
    return None
