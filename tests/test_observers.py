"""MQTT observers (modules/observers.py): packets and status in the common observer format, adverts decoded, group
messages counted by the Channel radar once (also when the own radio heard them). Runs in the simulated build tree."""
import contextlib
import hashlib
import hmac
import importlib
import json
import logging
import os
import sqlite3
import struct
import sys
import tempfile
import time
import types
import configparser
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


O = imp("modules.observers")
R = imp("modules.channel_radar")
CRS = imp("modules.service_plugins.channel_radar_service")
U = imp("modules.utils")


class DB:
    def __init__(self):
        self.path = tempfile.mktemp()
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
            c.execute("CREATE TABLE packet_stream (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, data TEXT, type TEXT)")
            c.commit()

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        with self.connection() as c:
            r = c.execute("SELECT value FROM bot_metadata WHERE key=?", (k,)).fetchone()
            return r[0] if r else None

    def set_metadata(self, k, v):
        with self.connection() as c:
            c.execute("INSERT OR REPLACE INTO bot_metadata VALUES (?,?)", (k, v)); c.commit()


def raw_packet(ptype, path, payload, route=1):
    return (bytes([(ptype << 2) | route, len(path)]) + bytes(path) + payload).hex()


now = time.time()
db = DB()
OBS = "ab" * 32
topic = f"meshcore/AMS/{OBS.upper()}"
check(O.handle(db, "something/else", b"{}") is None, "ander topic: genegeerd")
check(O.handle(db, topic + "/status", json.dumps({"status": "online", "origin": "Hub-Noord", "model": "Heltec V3",
                                                    "firmware_version": "v1.9.1", "radio": "869.618,62.5,8,8"}).encode(), now) == "status",
      "status van een observer")

# an advert of a repeater, with position and name
rep_key = bytes(range(32))
app = bytes([0x02 | 0x10 | 0x80]) + struct.pack("<ii", 50936200, 5956400) + b"NL-HRL-RPTR"
advert = rep_key + struct.pack("<I", int(now)) + bytes(64) + app
pkt = raw_packet(4, [0xc5, 0x98], advert)
dec = O.decode_raw(pkt)
check(dec["type"] == "ADVERT" and dec["path"] == ["c5", "98"] and dec["hops"] == 2 and dec["route"] == "FLOOD", f"pakket ontleed ({dec['type']}, {dec['path']})")
adv = O.parse_advert(dec["payload"])
check(adv == {"key": rep_key.hex(), "type": "repeater", "name": "NL-HRL-RPTR", "lat": 50.9362, "lon": 5.9564}, f"advert: naam, type, positie ({adv})")
for i in range(3):
    O.handle(db, topic + "/packets", json.dumps({"origin": "Hub-Noord", "raw": pkt, "SNR": "8.5", "RSSI": "-90"}).encode(), now + i)

# a group message on #limburg, heard by the observer AND by the bot's own radio: counted once by the radar
key = R.key_for_name("limburg")
body = os.urandom(24)
ch = hashlib.sha256(key).digest()[0]
mac = hmac.new(key + bytes(16), body, hashlib.sha256).digest()[:2]
grp = raw_packet(5, [0x11], bytes([ch]) + mac + body)
with db.connection() as c:     # the own radio heard it first (same packet hash as the bot computes)
    c.execute("INSERT INTO packet_stream (timestamp, data, type) VALUES (?,?, 'packet')",
              (now, json.dumps({"payload_type_name": "GRP_TXT", "payload_hex": (bytes([ch]) + mac + body).hex(),
                                "packet_hash": U.calculate_packet_hash(grp)})))
    c.commit()
O.handle(db, topic + "/packets", json.dumps({"origin": "Hub-Noord", "raw": grp, "SNR": 2, "RSSI": -110}).encode(), now + 5)
O.handle(db, topic + "/packets", b"not json", now + 6)

s = O.summary(db, 1, now=now + 10)
o = s["observers"][0]
check(o["name"] == "Hub-Noord" and o["iata"] == "AMS" and o["status"] == "online" and o["model"] == "Heltec V3" and o["firmware"] == "v1.9.1",
      f"observer met status, model en firmware ({o})")
check(o["packets"] == 4 and o["adverts"] == 3 and o["group_msgs"] == 1 and o["nodes"] == 1, f"tellers ({o['packets']}, {o['adverts']}, {o['group_msgs']}, {o['nodes']})")
check(s["heard"][0]["name"] == "NL-HRL-RPTR" and s["heard"][0]["count"] == 3 and s["heard"][0]["hops"] == 2, f"node gehoord via adverts ({s['heard']})")
check(sum(s["series"]["packets"]) == 4 and "full_key" not in o, "reeks per uur, geen volledige sleutel naar de browser")

cfg = configparser.ConfigParser(); cfg["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
bot = types.SimpleNamespace(config=cfg, db_manager=db, logger=logging.getLogger("r"))
svc = CRS.ChannelRadarService(bot)
svc.scan(now + 20)
lim = [c for c in R.summary(bot, now + 20)["channels"] if c["label"] == "#limburg"]
check(lim and lim[0]["month"] == 1, f"radar telt het groepsbericht één keer (radio + observer) ({lim})")
O.cleanup(db, now + 40 * 86400)
check(O.summary(db, 30, now=now + 40 * 86400)["observers"][0]["packets"] == 0, "na 30 dagen opgeruimd")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
