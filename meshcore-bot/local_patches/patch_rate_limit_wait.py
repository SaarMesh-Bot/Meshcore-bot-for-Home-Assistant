#!/usr/bin/env python3
"""Source patch: a command reply waits for the send limit instead of being dropped.

Upstream drops a reply when the global send limit (rate_limit_seconds) or the per-user limit is not yet free:
"Rate limited. Wait 1.1 seconds" and nothing is sent. On 18-11-2026 "Moin" and "Pegel Saar" came 20 s apart in
#saarland; the greeting reply went out (after tx delay) 2 s before the pegel command arrived, so the pegel reply was
silently dropped. Now the reply waits until the limit is free (at most MAX_WAIT seconds) and is then sent. Only when
the wait would be longer (real flooding) is it still dropped.
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
    """        if not skip_user_rate_limit:
            if not self.bot.rate_limiter.can_send():
                wait_time = self.bot.rate_limiter.time_until_next()
                if wait_time > 0.1:
                    return False, f"Rate limited. Wait {wait_time:.1f} seconds"
                return False, ""
            # Per-user rate limit when enabled and key present.
            # Admin ACL controls command authorization only; it does not bypass send rate limits.
            if getattr(self.bot, 'per_user_rate_limit_enabled', False) and rate_limit_key:
                per_user = getattr(self.bot, 'per_user_rate_limiter', None)
                if per_user and not per_user.can_send(rate_limit_key):
                    wait_time = per_user.time_until_next(rate_limit_key)
                    if wait_time > 0.1:
                        return False, f"Rate limited. Wait {wait_time:.1f} seconds"
                    return False, \"\"""",
    """        if not skip_user_rate_limit:
            # (add-on) wait for the limit instead of dropping the reply (at most 15 s; longer = flooding, dropped)
            import asyncio as _asyncio
            _max_wait = 15.0
            if not self.bot.rate_limiter.can_send():
                wait_time = self.bot.rate_limiter.time_until_next()
                if wait_time > _max_wait:
                    return False, f"Rate limited. Wait {wait_time:.1f} seconds"
                self.logger.info(f"Rate limit: reply waits {wait_time:.1f} s")
                await _asyncio.sleep(max(wait_time, 0) + 0.2)
            # Per-user rate limit when enabled and key present.
            # Admin ACL controls command authorization only; it does not bypass send rate limits.
            if getattr(self.bot, 'per_user_rate_limit_enabled', False) and rate_limit_key:
                per_user = getattr(self.bot, 'per_user_rate_limiter', None)
                if per_user and not per_user.can_send(rate_limit_key):
                    wait_time = per_user.time_until_next(rate_limit_key)
                    if wait_time > _max_wait:
                        return False, f"Rate limited. Wait {wait_time:.1f} seconds"
                    self.logger.info(f"Per-user rate limit: reply waits {wait_time:.1f} s")
                    await _asyncio.sleep(max(wait_time, 0) + 0.2)""",
)
