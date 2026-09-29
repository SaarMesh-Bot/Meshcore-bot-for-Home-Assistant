#!/usr/bin/env python3
"""Source patch: bytes per hop (1, 2 or 3) in the `test` reply (GitHub issue #1).

Runs once during the Docker build (see patch_webviewer.py for the shared mechanics).

MeshCore paths can use 1, 2 or 3 bytes per hop (multi-byte paths). The bot already knows it for a message heard over
RF (message.routing_info["bytes_per_hop"]), but no placeholder showed it. Both places that build {connection_info}
(utils.format_keyword_response_with_placeholders for keywords, base_command.build_enhanced_connection_info for the `test`
command and every command template) now use one helper, utils.addon_bytes_per_hop:
- {connection_info} gets it after the route ("4a,c2 (2 hops) | 2B/hop | SNR ... | RSSI ..."), so the standard `test`
  keyword shows it without changing its text. When routing_info does not carry it (channel messages often do not), it
  is read from the path itself: "456b,6367" = 4 hex characters per hop = 2 bytes. Nothing is added when it is unknown
  (a direct message without a path);
- a new placeholder {bytes_per_hop} ("2" or "?") for your own keyword texts.
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
    "modules/utils.py",
    """            connection_info = f"{routing_info} | {snr_info} | {rssi_info}"
            replacements['connection_info'] = connection_info
""",
    """            _bph = addon_bytes_per_hop(message, routing_info)
            replacements['bytes_per_hop'] = str(_bph) if _bph else "?"
            _bph_info = f" | {_bph}B/hop" if _bph else ""
            connection_info = f"{routing_info}{_bph_info} | {snr_info} | {rssi_info}"
            replacements['connection_info'] = connection_info
""",
)

# The helper both places use, at the end of utils.py.
_utils = ROOT / "modules/utils.py"
_utils.write_text(_utils.read_text().rstrip("\n") + '''


def addon_bytes_per_hop(message, path_display=""):
    """Bytes per hop (1, 2 or 3) of a message, or None (add-on, patch_test_bytes_per_hop.py): from routing_info when the
    bot knows it, else from the path shown ("456b,6367 (2 hops)" = 4 hex characters per hop = 2 bytes)."""
    import re as _re
    if str(path_display or "").strip().lower().startswith(("direct", "unknown")):
        return None   # no hops: bytes per hop says nothing
    ri = getattr(message, "routing_info", None) or {}
    bph = ri.get("bytes_per_hop") if isinstance(ri, dict) else None
    if bph in (1, 2, 3):
        return bph
    hops = [h for h in _re.split(r"[,\\s>]+", str(path_display or "").split("(")[0].strip()) if h]
    if hops and all(_re.fullmatch(r"[0-9a-fA-F]+", h) for h in hops) and len({len(h) for h in hops}) == 1 \\
            and len(hops[0]) in (2, 4, 6):
        return len(hops[0]) // 2
    return None
''')
print("Patched modules/utils.py (addon_bytes_per_hop)")

# The `test` command (and every command template) builds {connection_info} in base_command.py, not in utils.py.
patch(
    "modules/commands/base_command.py",
    """        connection_info = f"{path_part} | {snr_info} | {rssi_info}"
        return connection_info
""",
    """        from modules.utils import addon_bytes_per_hop
        _bph = addon_bytes_per_hop(message, path_part)
        _bph_info = f" | {_bph}B/hop" if _bph else ""
        connection_info = f"{path_part}{_bph_info} | {snr_info} | {rssi_info}"
        return connection_info
""",
)

patch(
    "modules/commands/base_command.py",
    """            'packet_hash': get_packet_hash_placeholder(message),
        }
""",
    """            'packet_hash': get_packet_hash_placeholder(message),
            'bytes_per_hop': str(self._addon_bph(message)),
        }

    def _addon_bph(self, message) -> str:
        from modules.utils import addon_bytes_per_hop
        return addon_bytes_per_hop(message, self.get_path_display_string(message)) or "?"
""",
)

patch(
    "modules/utils.py",
    """            replacements['connection_info'] = "Unknown"
""",
    """            replacements['connection_info'] = "Unknown"
            replacements['bytes_per_hop'] = "?"
""",
)
