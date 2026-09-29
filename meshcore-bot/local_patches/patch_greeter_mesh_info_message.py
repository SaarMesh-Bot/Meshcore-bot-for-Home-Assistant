#!/usr/bin/env python3
"""Source patch: a greeting that ends in "|" sends the mesh info as its own message.

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

Upstream always glues the mesh info ("Mesh info: 3779 contacts, ...") onto the last part of the greeting. With a
two-line welcome that easily passes the ~130 byte budget of one mesh message. A trailing "|" was dropped as an empty
part; now it means "mesh info as a separate message" (leading newlines/spaces of the format are then left out).
Without the trailing "|" nothing changes.

A "|" means "may start a new message here", not "always": parts that fit together in one mesh message (at most 130
bytes, less if the bot name leaves less room) are sent as one message, one line each. Only what does not fit goes on.
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


GREETER = "modules/commands/greeter_command.py"

patch(
    GREETER,
    """        # Parse multi-part greetings (pipe-separated)
        if '|' in greeting_template:""",
    """        # A greeting that ends in "|" sends the mesh info as its own message
        mesh_info_own_message = greeting_template.rstrip().endswith('|')

        # Parse multi-part greetings (pipe-separated)
        if '|' in greeting_template:""",
)

patch(
    GREETER,
    """                # Append mesh info to the last greeting part
                if formatted_parts:
                    formatted_parts[-1] += mesh_info_text
                else:
                    formatted_parts.append(mesh_info_text)""",
    """                # Append mesh info to the last greeting part (greeting ends in "|": its own message)
                if formatted_parts and not mesh_info_own_message:
                    formatted_parts[-1] += mesh_info_text
                elif mesh_info_text.strip():
                    formatted_parts.append(mesh_info_text.strip())""",
)

patch(
    GREETER,
    """         "help": "Default greeting. {sender} = user; separate multi-part messages with |."},""",
    """         "help": "Default greeting. {sender} = user; \\\\n = new line; separate multi-part messages with |. "
                 "End with | to give the mesh info its own part. Parts that fit together still go out as one message."},""",
)

patch(
    GREETER,
    """            # Send all greeting parts (rate-limit spacing handled by send_response_chunked)
            success = await self.send_response_chunked(message, greeting_parts)""",
    """            # "|" = may start a new message: parts that fit together go out as one message, one line each
            try:
                _limit = min(130, self.get_max_message_length(message))
            except Exception:
                _limit = 130
            _merged = []
            for _part in greeting_parts:
                if _merged and len((_merged[-1] + "\\n" + _part).encode("utf-8")) <= _limit:
                    _merged[-1] += "\\n" + _part
                else:
                    _merged.append(_part)
            greeting_parts = _merged

            # Send all greeting parts (rate-limit spacing handled by send_response_chunked)
            success = await self.send_response_chunked(message, greeting_parts)""",
)
