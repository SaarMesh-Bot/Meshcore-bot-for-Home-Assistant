#!/usr/bin/env python3
"""Source patch: the interval advert survives a restart.

Upstream keeps the time of the last interval advert only in memory and starts counting again at every start, so with
advert_interval_hours = 12 and a restart (update, reload) in between, the bot hardly ever adverts. Now the time is kept
in bot_metadata ("advert.last_interval"): after a restart the bot adverts as soon as the interval since the last one
has passed (at the earliest 5 minutes after the start, so a restart loop cannot flood the mesh).
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
    "modules/scheduler.py",
    """            # Check if enough time has passed since last advert
            if not hasattr(self.bot, 'last_advert_time') or self.bot.last_advert_time is None:
                # First time, set the timer
                self.bot.last_advert_time = current_time
                return
""",
    """            # Check if enough time has passed since last advert
            if not hasattr(self.bot, 'last_advert_time') or self.bot.last_advert_time is None:
                # (add-on) First time after a start: continue from the last interval advert kept in the database,
                # so a restart does not reset the count; at the earliest 5 minutes after the start.
                stored = None
                try:
                    stored = float(self.bot.db_manager.get_metadata('advert.last_interval') or 0) or None
                except Exception:
                    stored = None
                if stored:
                    self.bot.last_advert_time = max(stored, current_time - advert_interval_hours * 3600 + 300)
                else:
                    self.bot.last_advert_time = current_time
                return
""",
)

patch(
    "modules/scheduler.py",
    """                self.send_interval_advert()
                self.bot.last_advert_time = current_time
""",
    """                self.send_interval_advert()
                self.bot.last_advert_time = current_time
                try:   # (add-on) kept for the next start, see above
                    self.bot.db_manager.set_metadata('advert.last_interval', str(int(current_time)))
                except Exception:
                    pass
""",
)
