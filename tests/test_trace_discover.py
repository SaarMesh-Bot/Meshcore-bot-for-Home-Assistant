"""trace (longer default timeout, "tracert", a clear timeout text) and discover (direct neighbours from the database,
nothing sent over the radio). Runs in the simulated build tree: test_trace_discover.py <tree>.
"""
import asyncio
import configparser
import contextlib
import importlib
import logging
import os
import sqlite3
import sys
import tempfile
import types
from unittest.mock import MagicMock

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.ERROR)
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def imp(name):
    for _ in range(40):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name.split(".")[0] == "modules":
                raise
            sys.modules[e.name] = MagicMock()
            sys.modules.setdefault(e.name.split(".")[0], MagicMock())
    raise SystemExit("te veel ontbrekende modules")


R = imp("modules.trace_runner")
TraceCommand = imp("modules.commands.trace_command").TraceCommand
D = imp("modules.commands.discover_command")
MeshMessage = imp("modules.models").MeshMessage
Translator = imp("modules.i18n").Translator
tr = Translator("nl", "translations/", "local/translations")


class DB:
    def __init__(self):
        self.path = tempfile.mktemp()

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()


def make_bot(db, card=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Test|🤖"}
    if card:
        cfg["Trace_Command"] = card
    return types.SimpleNamespace(config=cfg, logger=logging.getLogger("t"), db_manager=db, translator=tr,
                                 command_manager=types.SimpleNamespace(monitor_channels=["#bot"]))


db = DB()
bot = make_bot(db)
path9 = "da,69,04,68,37,68,04,69,da".split(",")
check(R._get_timeout_seconds(bot, path9) == 2 + 9 * 1.5, f"9 hops zonder instellingen: 15.5 s ({R._get_timeout_seconds(bot, path9)})")
check(R._get_timeout_seconds(make_bot(db, {"timeout_per_hop_seconds": "0.8"}), path9) == 2 + 9 * 0.8, "waarde op de kaart gaat voor")
tc = TraceCommand(bot)
check("tracert" in tc.keywords and "trace" in tc.keywords, "tracert is een trefwoord van trace")
tc._last_path = path9
msg = MeshMessage(content="trace", sender_id="🗼LA-963 🇵🇦", channel="#bot", is_dm=False)
text = tc._format_trace_result(msg, R.RunTraceResult(success=False, tag=1, error_message="No trace response within timeout (path: x)"))
check(text == "@[🗼LA-963 🇵🇦] Trace: geen antwoord na 16s over 9 hops (da,69,04,68,37,68,04,69,da). Korter lukt vaker: tracer da,69"
      and len(text.encode()) <= 130, f"time-out: duidelijke tekst met tip ({len(text.encode())}: {text})")
other = tc._format_trace_result(msg, R.RunTraceResult(success=False, tag=1, error_message="radio busy"))
check(other.endswith("Trace failed: radio busy"), "andere fouten blijven zoals ze waren")

# ---------------------------------------------------------------- discover
dc = D.DiscoverCommand(bot)
check(dc.answer().startswith("Nog geen directe buren bekend"), "zonder burenscan: uitleg")
with db.connection() as c:
    c.execute("CREATE TABLE neighbor_links (neighbor_public_key TEXT, last_seen TIMESTAMP, last_snr REAL)")
    c.execute("CREATE TABLE complete_contact_tracking (public_key TEXT, name TEXT)")
    rows = [("da11" + "0" * 60, 7.5, "0 day"), ("6922" + "0" * 60, -3.2, "0 day"), ("0433" + "0" * 60, 11.0, "1 day"),
            ("9944" + "0" * 60, 20.0, "10 day"), ("7755" + "0" * 60, None, "0 day")]
    for key, snr, age in rows:
        c.execute("INSERT INTO neighbor_links VALUES (?, datetime('now', ?), ?)", (key, "-" + age, snr))
    c.execute("INSERT INTO complete_contact_tracking VALUES (?, ?)", ("da11" + "0" * 60, "NL-Heerlen-Rptr"))
    c.execute("INSERT INTO complete_contact_tracking VALUES (?, ?)", ("0433" + "0" * 60, "BE-Voeren 🗼"))
    c.commit()
a = dc.answer()
check(a == "Direct gehoord (4): BE-Voeren 🗼 +11dB, NL-Heerlen-Rptr +8dB, 692200 -3dB, 775500", f"beste signaal eerst, ouder dan 7 dagen weg ({a})")
with db.connection() as c:
    for i in range(20):
        c.execute("INSERT INTO neighbor_links VALUES (?, datetime('now'), ?)", (f"{i:02x}ee" + "0" * 60, float(i)))
    c.commit()
a = dc.answer()
check(len(a.encode()) <= 130 and a.startswith("Direct gehoord (24):") and a.endswith("…"), f"veel buren: past in 130 bytes ({len(a.encode())}: {a})")
check("discover" in dc.keywords, "trefwoord discover")


async def run():
    out = []

    async def send_response(message, content, **kw):
        out.append(content)
        return True
    dc.send_response = send_response
    await dc.execute(MeshMessage(content="discover", sender_id="X", channel="#bot", is_dm=False))
    return out
check(asyncio.run(run())[0].startswith("Direct gehoord"), "discover in een kanaal antwoordt")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
