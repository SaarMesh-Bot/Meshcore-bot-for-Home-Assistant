#!/usr/bin/env python3
"""Source patch: the greeter's delayed greeting was never sent.

With a "dead air" delay (the greeter waits a few seconds so a person can greet first), upstream marks the newcomer as
greeted right away and schedules the greeting; after the delay it checks has_been_greeted() and finds its own mark, so
it skipped every greeting silently (debug only). Found 2026-10-01: 12 greetings scheduled in a day, none sent, while
the names did land on the greeted list. Now the delayed greeting ignores a mark made when it was scheduled (or later
by this same greeting); a mark that was there before still stops it, and so do a human greeting and paused channel
responses, as before. A skipped greeting is logged at info level.
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
    "modules/commands/greeter_command.py",
    """            # Check if we should still greet (user might have been greeted by another process)
            if self.has_been_greeted(message.sender_id, message.channel):
                self.logger.debug(f"User {message.sender_id} already greeted on {message.channel} - skipping")
                if key in self.pending_greetings:
                    del self.pending_greetings[key]
                return""",
    """            # Check if we should still greet (user might have been greeted by another process).
            # (add-on) execute() marks the user as greeted before it schedules this greeting, so that mark is ours:
            # only a mark made before this greeting was scheduled means someone else greeted first.
            if self.has_been_greeted(message.sender_id, message.channel) and self._greeted_before(message, scheduled_at):
                self.logger.info(f"User {message.sender_id} already greeted on {message.channel} before - skipping")
                if key in self.pending_greetings:
                    del self.pending_greetings[key]
                return""",
)

patch(
    "modules/commands/greeter_command.py",
    """        key = (message.sender_id, message.channel)
        original_timestamp = message.timestamp or int(time.time())
""",
    """        key = (message.sender_id, message.channel)
        original_timestamp = message.timestamp or int(time.time())
        scheduled_at = time.time()
""",
)

patch(
    "modules/commands/greeter_command.py",
    """    async def _send_delayed_greeting(self, message: MeshMessage) -> None:""",
    """    def _greeted_before(self, message: MeshMessage, scheduled_at: float) -> bool:
        \"\"\"(add-on) True when the greeted mark is older than this delayed greeting (with 30 s margin for the mark that
        execute() wrote just before scheduling it). Unknown = False (better to greet than to miss it).\"\"\"
        try:
            with self.bot.db_manager.connection() as conn:
                if self.per_channel_greetings:
                    row = conn.execute("SELECT CAST(strftime('%s', greeted_at) AS INTEGER) FROM greeted_users "
                                       "WHERE sender_id = ? AND channel = ?", (message.sender_id, message.channel)).fetchone()
                else:
                    row = conn.execute("SELECT CAST(strftime('%s', greeted_at) AS INTEGER) FROM greeted_users "
                                       "WHERE sender_id = ? AND channel IS NULL", (message.sender_id,)).fetchone()
            return bool(row and row[0] and row[0] < scheduled_at - 30)
        except Exception as e:
            self.logger.debug(f"Greeter: could not read the greeted time ({e}); greeting anyway")
            return False

    async def _send_delayed_greeting(self, message: MeshMessage) -> None:""",
)
