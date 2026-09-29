#!/usr/bin/env python3
"""Source patch: night mode (see modules/night_mode.py; card Plugins -> NightMode).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

The bot sends some messages on its own: scheduled messages, feed items and whatever Home Assistant posts through the
webhook. At night those can be kept quiet. One check is added right where each of them leaves:

1. scheduler._send_scheduled_message_async(): a scheduled message due at night is skipped (logged).
2. feed_manager._process_message_queue_inner(): at night the queued feed items are marked handled instead of sent,
   so they do not all come out in the morning (logged).
3. webhook_service: at night (only when switched on for the webhook) the request is answered 200 with
   {"skipped": "night mode"} and nothing is sent.
Replies to people are never touched.
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
    '''        """Send a scheduled message (async implementation)"""
''',
    '''        """Send a scheduled message (async implementation)"""
        from modules.night_mode import quiet as _night_quiet
        if _night_quiet(self.bot, "scheduled"):
            self.logger.info("Nachtstand: gepland bericht voor %s overgeslagen", channel)
            return
''',
)

patch(
    "modules/feed_manager.py",
    '''                messages = cursor.fetchall()

            if not messages:
                return
''',
    '''                messages = cursor.fetchall()

            if not messages:
                return

            from modules.night_mode import quiet as _night_quiet
            if _night_quiet(self.bot, "feeds"):
                # Night: handled without sending, so the night's items do not all go out in the morning.
                with self.bot.db_manager.connection() as conn:
                    conn.executemany("UPDATE feed_message_queue SET sent_at = CURRENT_TIMESTAMP WHERE id = ?",
                                     [(m['id'],) for m in messages])
                    conn.commit()
                self.logger.info("Nachtstand: %d feedbericht(en) overgeslagen", len(messages))
                return
''',
)

patch(
    "modules/service_plugins/webhook_service.py",
    '''        # --- Dispatch ---
''',
    '''        # --- Night mode (Plugins -> NightMode, only when switched on for the webhook) ---
        from modules.night_mode import quiet as _night_quiet
        if _night_quiet(self.bot, "webhook"):
            self.logger.info("Nachtstand: webhookbericht niet verstuurd")
            return aio_web.Response(status=200, content_type="application/json", text='{"skipped": "night mode"}')

        # --- Dispatch ---
''',
)
