"""A command switched off on the Plugins page stays silent (issue #1: the old notice was always Dutch), also stats and
DM-only commands that used to speak up on their own; it gets no channel hint either. A command that is on still answers."""
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


d = tempfile.mkdtemp()
opts = json.load(open(os.path.join(FIXTURES, "options_sample.json")))
opts.setdefault("bot", {})["language"] = "en"
opts["bot"]["channels"] = ["test", "bot"]
json.dump(opts, open(f"{d}/options.json", "w"))
subprocess.run([sys.executable, os.path.join(ADDON, "generate_config.py"), f"{d}/options.json", f"{d}/config.ini", d],
               check=True, capture_output=True)

os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.CRITICAL)
for _ in range(60):
    try:
        from modules.command_manager import CommandManager
        from modules.models import MeshMessage
        from modules.i18n import Translator
        from modules.channel_hint import ChannelHint
        break
    except ModuleNotFoundError as e:
        sys.modules[e.name] = MagicMock()
        sys.modules.setdefault(e.name.split(".")[0], MagicMock())

cfg = configparser.ConfigParser(interpolation=None)
cfg.read(f"{d}/config.ini")
for sec in ("Morse_Command", "Stats_Command", "Test_Command"):
    if not cfg.has_section(sec):
        cfg.add_section(sec)
    cfg[sec]["enabled"] = "false"


class DB:
    path = os.path.join(d, "bot.db")

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        yield c
        c.close()

    def __getattr__(self, k):
        return MagicMock()


bot = MagicMock()
bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("t"), DB()
bot.translator = Translator("en", "translations/", "local/translations")
cm = CommandManager(bot)
bot.command_manager = cm
sent = []


async def send_response(message, content, *a, **k):
    sent.append(content)
    return True
cm.send_response = send_response


async def say(text):
    m = MeshMessage(content=text, sender_id="Piet", channel="test", is_dm=False, hops=1, snr=5.0, path="5f")
    sent.clear()
    sent.extend(r for _, r in cm.check_keywords(m) if r)
    await cm.execute_commands(m)
    return list(sent)

check(asyncio.run(say("morse hello")) == [], "morse uit: geen antwoord (was: 'staat momenteel uit')")
check(asyncio.run(say("stats")) == [], "stats uit: geen 'Stats command is disabled'")
check(asyncio.run(say("test")) == [], "test uit: geen antwoord")
r = asyncio.run(say("ping"))
check(len(r) == 1 and r[0].startswith("Pong"), f"ping staat aan en antwoordt ({r})")
src = open("modules/command_manager.py").read()
check("staat momenteel uit" not in src, "de oude Nederlandse melding is weg")

hint = ChannelHint.__new__(ChannelHint)
hint.bot = bot
check(hint.command_hint_mode(cm.commands["test"]) == "off", "test uit: ook geen kanaalhint")
check(hint.command_hint_mode(cm.commands["ping"]) == "word", "ping aan: hint zoals ingesteld")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
