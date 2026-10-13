"""Greeter card "Send the greeting as": DM (default) to the contact with the sender's name, else the channel or nothing
as the card says; a DM to the bot itself is never redirected. Runs in the simulated build tree."""
import asyncio
import configparser
import contextlib
import logging
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.CRITICAL)
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


from modules.models import MeshMessage  # noqa: E402
from modules.commands.greeter_command import GreeterCommand  # noqa: E402


class DBM:
    def __init__(self, path):
        self.db_path = path

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.db_path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        return None

    def set_metadata(self, k, v):
        pass


def greet(extra, known=("Jean",)):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg["Bot"] = {"bot_name": "Mesh|HA|🤖"}
    cfg["Greeter_Command"] = dict({"enabled": "true", "rollout_days": "0", "channels": "Publiek",
                                   "greeting_message": "Welkom op de mesh, @[{sender}]! |", "include_mesh_info": "true",
                                   "mesh_info_format": "Mesh info: {total_contacts} contacten"}, **extra)
    bot = MagicMock()
    bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("g"), DBM(tempfile.mktemp())
    dms, chan = [], []

    async def send_dm(recipient, text, **kw):
        if recipient not in known:
            return False
        dms.append((recipient, text))
        return True
    bot.command_manager.send_dm = send_dm
    g = GreeterCommand(bot)

    async def info():
        return {"total_contacts": 900, "repeaters": 120, "companions": 700, "recent_activity_24h": 150}
    g._get_mesh_info = info

    async def chunked(message, parts, **kw):
        chan.extend(parts)
        return True
    g.send_response_chunked = chunked
    g.get_max_message_length = lambda m: 130
    return g, dms, chan


def run(g, name="Jean", is_dm=False):
    return asyncio.run(g._send_greeting(MeshMessage(content="hoi", sender_id=name, channel=None if is_dm else "Publiek", is_dm=is_dm)))


g, dms, chan = greet({})
ok = run(g)
check(ok and dms and dms[0][0] == "Jean" and dms[0][1].startswith("Welkom op de mesh, @[Jean]!") and not chan,
      f"standaard: begroeting als DM ({dms}, kanaal {chan})")
g, dms, chan = greet({}, known=())
run(g, "Onbekend")
check(not dms and chan and chan[0].startswith("Welkom op de mesh, @[Onbekend]!"), "geen contact: toch in het kanaal (standaard)")
g, dms, chan = greet({"dm_fallback": "none"}, known=())
check(run(g, "Onbekend") is False and not dms and not chan, "geen contact + 'niets sturen': niets verstuurd")
g, dms, chan = greet({"greet_via": "channel"})
run(g)
check(chan and not dms, "kaart op kanaal: zoals vroeger in het kanaal")
src = open("modules/commands/greeter_command.py").read()
check('"key": "greet_via"' in src and '"key": "dm_fallback"' in src, "twee keuzes op de Greeter-kaart")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
