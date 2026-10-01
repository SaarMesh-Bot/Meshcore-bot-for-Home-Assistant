#!/usr/bin/env python3
"""Source patch: trace works on long paths, answers to "tracert", and says why it failed in the sender's language.

Found 2026-09-30 in #bot: "trace" from someone 5 hops away failed every time ("No trace response within timeout (path:
da,69,04,68,37,68,04,69,da)"). Without Trace_Command keys in config.ini the runner waited 1 s + 0.5 s per hop, 5.5 s
for that 9-hop round trip, and then sent the trace a second time. Over LoRa every hop takes its airtime plus a
retransmit delay, so a round trip of 9 hops needs well over 5.5 s. Now:
- the defaults match the card (1.5 s per hop, base 2 s); a value on the card still wins;
- "tracert" (as people type it from other bots) is a keyword of trace;
- a timeout answers with commands.trace.timeout (hops, seconds, path, and a tip to try a shorter path).
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
    "modules/trace_runner.py",
    """    per_hop = bot.config.getfloat("Trace_Command", "timeout_per_hop_seconds", fallback=0.5)
    base = bot.config.getfloat("Trace_Command", "timeout_base_seconds", fallback=1.0)""",
    """    # (add-on) defaults as on the card: 0.5 s per hop was too short for real LoRa hops (airtime + retransmit delay)
    per_hop = bot.config.getfloat("Trace_Command", "timeout_per_hop_seconds", fallback=1.5)
    base = bot.config.getfloat("Trace_Command", "timeout_base_seconds", fallback=2.0)""",
)

patch(
    "modules/commands/trace_command.py",
    """    keywords = ["trace", "tracer"]""",
    """    keywords = ["trace", "tracer", "tracert"]   # (add-on) tracert: as people type it from other bots""",
)

patch(
    "modules/commands/trace_command.py",
    """        sender_str = f"@[{message.sender_id}] "
        if not result.success:
            return f"{sender_str}Trace failed: {result.error_message or 'unknown'}\"""",
    """        sender_str = f"@[{message.sender_id}] "
        if not result.success and "No trace response" in (result.error_message or ""):
            # (add-on) a timeout: say how long and over how many hops, and that a shorter path works more often
            path = getattr(self, "_last_path", None) or []
            from ..trace_runner import _get_timeout_seconds
            return sender_str + self.translate("commands.trace.timeout", hops=len(path), seconds=round(_get_timeout_seconds(self.bot, path)),
                                               path=",".join(path), short=",".join(path[:2]) or "01,7a")
        if not result.success:
            return f"{sender_str}Trace failed: {result.error_message or 'unknown'}\"""",
)

patch(
    "modules/commands/trace_command.py",
    """        result = await run_trace(
            self.bot,
            path=path_nodes,""",
    """        self._last_path = list(path_nodes)   # (add-on) for the timeout text
        result = await run_trace(
            self.bot,
            path=path_nodes,""",
)
