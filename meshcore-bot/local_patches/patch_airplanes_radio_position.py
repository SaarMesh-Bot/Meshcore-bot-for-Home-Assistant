#!/usr/bin/env python3
"""Source patch: airplanes (and 'airplanes here') use the radio's own advertised position when the add-on has no
fixed position.

Upstream only looks at [Bot] bot_latitude/bot_longitude, which this add-on writes only when the options Latitude and
Longitude are both filled in. Without them every airplanes question answered "no location" (GitHub issue #1), while a
normal install had the position in config.ini. The radio usually advertises its position, so that is the fallback
(0,0 = not set, ignored). Runs after patch_airplanes_metric.py.
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
    "modules/commands/airplanes_command.py",
    """            lat = self.bot.config.getfloat('Bot', 'bot_latitude', fallback=None)
            lon = self.bot.config.getfloat('Bot', 'bot_longitude', fallback=None)
""",
    """            lat = self.bot.config.getfloat('Bot', 'bot_latitude', fallback=None)
            lon = self.bot.config.getfloat('Bot', 'bot_longitude', fallback=None)
            if lat is None or lon is None:
                # (add-on) no fixed position: the position the radio itself advertises
                info = getattr(getattr(self.bot, 'meshcore', None), 'self_info', None) or {}
                a_lat, a_lon = info.get('adv_lat'), info.get('adv_lon')
                if a_lat not in (None, 0, 0.0) and a_lon not in (None, 0, 0.0):
                    lat, lon = float(a_lat), float(a_lon)
""",
)
