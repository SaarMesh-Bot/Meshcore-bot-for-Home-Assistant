"""ping without a [Keywords] ping: Pong with hops, the repeater it came via, SNR, RSSI, travel time and bot time;
unknown parts left out; a keyword still wins."""
import importlib
import logging
import os
import sqlite3
import sys
import time
import types
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


P = imp("modules.ping_info")
Translator = imp("modules.i18n").Translator
nl = Translator("nl", "translations/", "local/translations")
en = Translator("en", "translations/", "local/translations")
de = Translator("de", "translations/", "local/translations")

src = open("modules/commands/ping_command.py").read()
check("from ..ping_info import reply" in src and "if self.get_response_format():" in src, "patch: zonder keyword het uitgebreide antwoord")

conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE complete_contact_tracking (public_key TEXT, name TEXT, role TEXT)")
conn.executemany("INSERT INTO complete_contact_tracking VALUES (?,?,?)", [
    ("5f" + "0" * 62, "Repeater Zuid", "repeater"), ("a1" + "1" * 62, "Rep A", "repeater"),
    ("a1" + "2" * 62, "Rep B", "repeater"), ("7c" + "3" * 62, "Jan", "companion")])
check(P.repeater_name(conn, "5f") == "Repeater Zuid", "unieke repeater-prefix: naam")
check(P.repeater_name(conn, "a1") == "", "twee repeaters met die prefix: geen naam")
check(P.repeater_name(conn, "7c") == "", "companion telt niet als repeater")
check(P.repeater_name(None, "5f") == "" and P.repeater_name(sqlite3.connect(":memory:"), "5f") == "", "geen db/tabel: leeg")

M = types.SimpleNamespace
check(P.last_hop(M(routing_info={"path_nodes": ["01", "5F"]}, path="")) == "5f", "laatste hop uit routing_info")
check(P.last_hop(M(routing_info=None, path="01,5f (2 hops)")) == "5f", "laatste hop uit padtekst")
check(P.last_hop(M(routing_info=None, path="a1b2 via ROUTE_TYPE_FLOOD")) == "a1b2", "een multibyte hop")
check(P.last_hop(M(routing_info=None, path="Direct")) == "", "direct: geen hop")

t = nl.translate
s = P.info(t, 3, "Repeater Zuid", 6.5, -92, "1.2s", "07:01")
check(s == "3 hops via Repeater Zuid · SNR 6.5 dB · RSSI -92 dBm · 1.2s onderweg · 07:01", f"nl volledig: {s}")
s = P.info(t, 0, "", "Unknown", None, "Klok gelijkzetten", "07:01")
check(s == "direct · 07:01", f"onbekende delen weg: {s}")
check(P.info(t, 1, "", 5.0, -100.0, "850ms", "") == "1 hop · SNR 5 dB · RSSI -100 dBm · 850ms onderweg", "1 hop, hele getallen")
check(P.info(t, None, "x", None, None, "", "") == "", "niets bekend: leeg")
check(P.info(en.translate, 2, "R", 1, -90, "2s", "") == "2 hops via R · SNR 1 dB · RSSI -90 dBm · 2s in transit", "en")
check(P.info(de.translate, 2, "R", None, None, "", "") == "2 Hops über R", "de")


class Cmd:
    def __init__(self, tr, db_conn):
        self.translate = tr.translate
        self.bot = M(db_manager=M(connection=lambda: _Ctx(db_conn)))

    def format_elapsed(self, m):
        return "1.2s"

    def format_timestamp(self, m):
        return "07:01:33"


class _Ctx:
    def __init__(self, c):
        self.c = c

    def __enter__(self):
        return self.c

    def __exit__(self, *a):
        return False


msg = M(sender_id="Jan", routing_info={"path_length": 3, "path_nodes": ["01", "a1", "5f"]}, path="", snr=6.5, rssi=-92,
        hops=3, timestamp=time.time())
r = P.reply(Cmd(nl, conn), msg)
check(r == "Pong @[Jan]! 3 hops via Repeater Zuid · SNR 6.5 dB · RSSI -92 dBm · 1.2s onderweg · 07:01", f"reply nl: {r}")
check(len(r.encode()) <= 130, f"past in een kanaalbericht ({len(r.encode())} bytes)")
d = M(sender_id="Jan", routing_info={"path_length": 0, "path_nodes": []}, path="Direct", snr=None, rssi=None, hops=0, timestamp=None)
r = P.reply(Cmd(nl, conn), d)
check(r.startswith("Pong @[Jan]! direct"), f"direct bericht: {r}")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
