#!/usr/bin/env python3
"""Source patch: the path command numbers its parts and can show fewer hops.

A long path reply is split into several messages, 3 s apart. Over the mesh they often arrive out of order, or only the
last one arrives (GitHub issue #1). Now:
- every part ends with (1/2), (2/2), ... so the reader sees the order and whether one is missing;
- the path card has "Max hops shown" (0 = all): a longer path shows the first hops and "+N more".
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



FILE = "modules/commands/path_command.py"

patch(
    FILE,
    """        {"key": "graph_multi_hop_max_hops",""",
    """        {"key": "max_hops_shown", "label": "Max hops shown", "type": "int", "default": 0, "min": 0, "max": 64,
         "help": "Show at most this many hops of a long path, then '+N more' (0 = all). Fewer hops = fewer messages."},
        {"key": "graph_multi_hop_max_hops",""",
)

# Replace the splitting loop of _send_path_response: first make the parts, then send them numbered.
p = ROOT / FILE
text = p.read_text()
start = r"""        lines = response.split('\n')
        current_message = ""
        message_count = 0
"""
end = """    async def _extract_path_from_recent_messages("""
if text.count(start) != 1 or text.count(end) != 1:
    sys.exit(f"PATCH FAILED - path splitting loop not found once in {FILE} (upstream code likely changed)")
i, j = text.index(start), text.index(end)
new = r"""        lines = response.split('\n')
        # (add-on) at most "Max hops shown" hops, then how many more
        try:
            max_hops = int(self.bot.config.get('Path_Command', 'max_hops_shown', fallback='0') or 0)
        except ValueError:
            max_hops = 0
        if max_hops > 0 and len(lines) > max_hops:
            lines = lines[:max_hops] + [self.translate('commands.path.more_hops', n=len(lines) - max_hops)]
        if len(lines) != len(response.split('\n')) and self._count_byte_length('\n'.join(lines)) + prefix_len <= max_length:
            await self.send_response(message, prefix + '\n'.join(lines))
            return
        # (add-on) parts of whole lines, each ending with (1/2), (2/2), ... (room kept for that tag)
        tag_room = 8
        parts, current = [], ""
        for line in lines:
            budget = (first_segment_max if not parts else max_length) - tag_room
            candidate = f"{current}\n{line}" if current else line
            if current and self._count_byte_length(candidate) > budget:
                parts.append(current)
                current = line
            else:
                current = candidate
        if current:
            parts.append(current)
        total = len(parts)
        for n, part in enumerate(parts, 1):
            out = f"{part} ({n}/{total})"
            if n == 1 and prefix:
                out = prefix + out
            await self.send_response(message, out, skip_user_rate_limit=(n > 1))
            if n < total:
                await asyncio.sleep(3.0)

"""
p.write_text(text[:i] + new + text[j:])
print(f"Patched {FILE} (numbered parts)")
