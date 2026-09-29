#!/usr/bin/env python3
"""Source patch: the greeter's rollout runs once, not again every week.

Upstream (v1.1.0) auto-starts a new rollout at every start when the last one ended more than a day ago, and also when it
finds an expired rollout. With the default rollout_days = 7 that means: one week of greeting, then a new week of only
marking people (no greetings), again and again - and ending the rollout by hand only helps until the next start a day
later. Seen 2026-09-29: rollout 2 had started on its own (26-09 21:05) after the first had ended.

The rollout is meant for the first start only (so the regulars are not all greeted at once). Now a new rollout starts
automatically only when there never was one; an expired one is marked completed without starting another. Starting a
rollout by hand (dashboard) keeps working.
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


GR = "modules/commands/greeter_command.py"

patch(
    GR,
    """                            self.logger.warning(f"Found expired rollout (ID: {rollout_id}) - marking as completed and starting new one")
                            cursor.execute('''
                                UPDATE greeter_rollout
                                SET rollout_completed = 1
                                WHERE id = ?
                            ''', (rollout_id,))
                            conn.commit()
                            self.logger.info(f"Auto-starting greeter rollout for {self.rollout_days} days")
                            self.start_rollout(backfill_first=self.auto_backfill)""",
    """                            # (add-on) a rollout runs once: mark it completed, never start another one by itself
                            self.logger.info(f"Greeter rollout {rollout_id} has ended - marking it completed (no new rollout)")
                            cursor.execute('''
                                UPDATE greeter_rollout
                                SET rollout_completed = 1
                                WHERE id = ?
                            ''', (rollout_id,))
                            conn.commit()""",
)

patch(
    GR,
    """                        recent_rollout = cursor.fetchone()

                        if recent_rollout:""",
    """                        recent_rollout = cursor.fetchone()

                        if recent_rollout:
                            # (add-on) there has been a rollout already: it runs once, not every week
                            self.logger.info(f"Greeter rollout already done (ID: {recent_rollout[0]}) - greeting new people, no new rollout")
                            return
                        if recent_rollout:""",
)
