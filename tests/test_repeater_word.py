"""The word "repeater" at the start of a channel message is ordinary chat, not a command (25-10-2026: "Repeater update
auf 1.18" in #saarland got "Invalid prefix format. Expected 2, 4, or 6 hex characters"). Upstream's translations list
"repeater" as a keyword of the prefix lookup; our overlay drops it, and the DM-only repeater command stays out of
channels. prefix/lookup still work, and "repeater" still reaches the repeater command in a DM."""
import asyncio
import configparser
import contextlib
import json
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
ADDON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "meshcore-bot")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.CRITICAL)
for _ in range(60):
    try:
        from modules.command_manager import CommandManager
        from modules.models import MeshMessage
        from modules.i18n import Translator
        break
    except ModuleNotFoundError as e:
        sys.modules[e.name] = MagicMock()
        sys.modules.setdefault(e.name.split(".")[0], MagicMock())


class DB:
    def __init__(self, d):
        self.path = os.path.join(d, "bot.db")

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        yield c
        c.close()

    def __getattr__(self, k):
        return MagicMock()


for lang in ("de", "en", "nl", "fr"):
    d = tempfile.mkdtemp()
    opts = json.load(open(os.path.join(FIXTURES, "options_sample.json")))
    opts.setdefault("bot", {})["language"] = lang
    opts["bot"]["channels"] = ["saarland", "test"]
    json.dump(opts, open(f"{d}/options.json", "w"))
    subprocess.run([sys.executable, os.path.join(ADDON, "generate_config.py"), f"{d}/options.json",
                    f"{d}/config.ini", d], check=True, capture_output=True)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(f"{d}/config.ini")
    check(cfg.get("Repeater_Command", "channels", fallback=None) == "",
          f"[{lang}] Repeater_Command channels leer = nur DM")

    bot = MagicMock()
    bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("t"), DB(d)
    bot.translator = Translator(lang, "translations/", "local/translations")
    cm = CommandManager(bot)
    bot.command_manager = cm
    sent = []

    async def send_response(message, content, *a, **k):
        sent.append(content)
        return True
    cm.send_response = send_response

    async def say(text, dm=False):
        m = MeshMessage(content=text, sender_id="13PG666-Mobil", channel=None if dm else "#saarland", is_dm=dm,
                        hops=4, snr=5.0, path="41a985")
        sent.clear()
        sent.extend(r for _, r in cm.check_keywords(m) if r)
        await cm.execute_commands(m)
        return list(sent), m

    pc = cm.commands.get("prefix")
    check(pc is not None and "repeater" not in [k.lower() for k in pc.keywords],
          f"[{lang}] prefix hat kein Stichwort 'repeater' ({pc.keywords if pc else None})")
    check(pc is not None and {"prefix", "lookup"} <= set(pc.keywords), f"[{lang}] prefix/lookup bleiben")
    for text in ("Repeater update auf 1.18", "repeater ist wieder online", "Repeaters sind alle da", "rp down?"):
        r, _ = asyncio.run(say(text))
        check(r == [], f"[{lang}] Kanal: {text!r} bleibt ohne Antwort ({r})")
    rc = cm.commands.get("repeater")
    if rc is not None:
        _, m = asyncio.run(say("repeater list", dm=True))
        check(rc.should_execute(m) and rc.is_channel_allowed(m), f"[{lang}] DM: 'repeater' erreicht weiter den Befehl")

print(f"\n{len(fails)} Fehler")
sys.exit(1 if fails else 0)
