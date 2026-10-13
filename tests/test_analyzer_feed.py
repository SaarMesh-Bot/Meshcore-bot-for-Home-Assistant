"""AnalyzerFeed: observers of chosen regions from the public EU Meshcore Analyzer API (no network: a fake session),
stored like MQTT observers; packets only once, only new ones, region row for nodes heard."""
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
AF = imp("modules.service_plugins.analyzer_feed_service")
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


import asyncio
from datetime import datetime, timezone
now = time.time()
iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")
db = DB()

check(O.regions_from(" mst, lgg ,x, MST;ams") == ["MST", "LGG", "AMS"], "regio's: hoofdletters, dubbels en onzin eruit")
check(len(O.region_key("MST")) == 16 and O.region_key("mst") == O.region_key("MST"), "vaste sleutel per regio")

A, B = "1f" * 32, "2e" * 32
OBSERVERS = [
    {"id": A.upper(), "name": "Testberg Observer", "iata": "MST", "model": "Heltec V3", "firmware": "1.15.0", "radio": "869.6,62.5,7,5",
     "first_seen": iso(now - 86400 * 9), "last_seen": iso(now - 60), "packets_hour": 480},
    {"id": B.upper(), "name": "Oude Hub", "iata": "MST", "last_seen": iso(now - 7200), "packets_hour": 0},
    {"id": "33" * 32, "name": "Andere regio", "iata": "AMS", "last_seen": iso(now), "packets_hour": 10},
]
rep_key = bytes(range(32))
app = bytes([0x02 | 0x10 | 0x80]) + struct.pack("<ii", 50856000, 5697000) + b"NL-TST-RPTR"
advert = raw_packet(4, [0xa1], rep_key + struct.pack("<I", int(now)) + bytes(64) + app)
key = R.key_for_name("limburg")
gbody = os.urandom(24)
ch = hashlib.sha256(key).digest()[0]
grp = raw_packet(5, [0x11], bytes([ch]) + hmac.new(key + bytes(16), gbody, hashlib.sha256).digest()[:2] + gbody)
PACKETS = [   # newest first, like the API
    {"hash": "h3", "raw_hex": grp, "timestamp": iso(now - 30)},
    {"hash": "h2", "raw_hex": advert, "timestamp": iso(now - 60)},
    {"hash": "h1", "raw_hex": advert, "timestamp": iso(now - 90)},
]


class Resp:
    def __init__(self, data): self.data = data
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    def raise_for_status(self): pass
    async def json(self, content_type=None): return self.data


class Session:
    def __init__(self): self.calls = []
    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        if url.endswith("/api/observers"):
            return Resp(OBSERVERS)                     # the API returns more than asked: the service filters on iata
        since = (params or {}).get("since", "")
        return Resp({"packets": [p for p in PACKETS if p["timestamp"] >= since], "total": None})


cfg = configparser.ConfigParser()
cfg["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
cfg["AnalyzerFeed"] = {"enabled": "true", "regions": "mst", "url": "http://evil.example", "packets": "true"}
bot = types.SimpleNamespace(config=cfg, db_manager=db, logger=logging.getLogger("a"))
svc = AF.AnalyzerFeedService(bot)
check(svc.regions == ["MST"] and svc.url == "https://meshcore-analyzer.eu", "kaart gelezen; geen https = standaardadres")
sess = Session()
n = asyncio.run(svc.read_observers(sess))
check(n == 2 and sess.calls[0] == ("https://meshcore-analyzer.eu/api/observers", {"region": "MST"}), f"observers van MST opgehaald ({n})")
got = asyncio.run(svc.read_new_packets(sess, now=now))
check(got == 3, f"drie nieuwe pakketten opgeslagen ({got})")
check(sess.calls[-1][1]["since"] <= iso(now - 590), "eerste keer: alleen de laatste 10 minuten")
again = asyncio.run(svc.read_new_packets(sess, now=now + 60))
check(again == 0 and sess.calls[-1][1]["since"] == PACKETS[0]["timestamp"], "volgende keer: vanaf het laatste pakket, niets dubbel")

s = O.summary(db, 1, now=now)
obs = {o["name"]: o for o in s["observers"]}
check(obs["Testberg Observer"]["status"] == "online" and obs["Testberg Observer"]["packets"] == 480 and obs["Testberg Observer"]["model"] == "Heltec V3",
      f"observer met status, model en pakketten per uur ({obs.get('Testberg Observer')})")
check(obs["Oude Hub"]["status"] == "offline", "observer zonder recent bericht: offline")
check("Andere regio" not in obs, "andere regio niet opgeslagen")
reg = obs.get("MST · EU Analyzer")
check(reg and reg["packets"] == 3 and reg["adverts"] == 2 and reg["group_msgs"] == 1 and reg["nodes"] == 1, f"regioregel: pakketten, adverts, groepsberichten, nodes ({reg})")
heard = O.summary(db, 1, key=O.region_key("MST"), now=now)["heard"]
check(heard and heard[0]["name"] == "NL-TST-RPTR", f"node gehoord in de regio ({heard})")
cfg2 = configparser.ConfigParser(); cfg2["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
rbot = types.SimpleNamespace(config=cfg2, db_manager=db, logger=logging.getLogger("r"))
CRS.ChannelRadarService(rbot).scan(now + 20)
lim = [c for c in R.summary(rbot, now + 20)["channels"] if c["label"] == "#limburg"]
check(lim and lim[0]["month"] == 1, f"groepsbericht uit de regio telt op de Kanaalradar ({lim})")
cfg["AnalyzerFeed"]["regions"] = ""
check(AF.AnalyzerFeedService(bot).regions == [], "zonder regio's: niets te doen")

# ---------------------------------------------------------------- names for unnamed neighbours (resolve)
AN = imp("modules.analyzer_names")
RPG = imp("modules.repeater_page")
dbn = DB()
with dbn.connection() as c:
    c.execute("CREATE TABLE ha_repeater_neighbors (id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL, repeater_key TEXT NOT NULL, "
              "neighbor_prefix TEXT NOT NULL, neighbor_name TEXT, snr REAL, secs_ago INTEGER, stats_key TEXT)")
    c.execute("CREATE TABLE repeater_telemetry (id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL, repeater_key TEXT NOT NULL, "
              "repeater_name TEXT, battery_mv INTEGER, battery_pct REAL, temperature REAL, ch1_voltage REAL, uptime_s INTEGER, airtime_s INTEGER, "
              "airtime_util REAL, nb_recv INTEGER, nb_sent INTEGER, noise_floor REAL, last_rssi REAL, last_snr REAL, neighbor_count INTEGER, "
              "stats_key TEXT, source TEXT NOT NULL DEFAULT 'ha')")
    RK = "ab" * 32
    c.execute("INSERT INTO repeater_telemetry (recorded_at, repeater_key, repeater_name, battery_mv) VALUES (?,?,?,?)", (int(now), RK, "Mijn RPT", 4000))
    for pfx, nm in (("1a2b3c", ""), ("4d5e6f", "Bekende"), ("7a7a7a", ""), ("c5", "")):
        c.execute("INSERT INTO ha_repeater_neighbors (recorded_at, repeater_key, neighbor_prefix, neighbor_name, snr, secs_ago) VALUES (?,?,?,?,?,?)",
                  (int(now), RK, pfx, nm, 5.0, 60))
    c.commit()
with dbn.connection() as c:
    todo = AN.wanted(c, now)
check(todo == ["1a2b3c", "7a7a7a"] or sorted(todo) == ["1a2b3c", "7a7a7a"], f"alleen naamloze buren van 6+ tekens ({todo})")


class ResolveSession(Session):
    def get(self, url, params=None):
        self.calls.append((url, dict(params or {})))
        p = (params or {}).get("prefix", "")
        if p == "1a2b3c":
            return Resp({"prefix": p, "count": 1, "candidates": [{"id": "1a2b3c" + "00" * 29, "name": "NL TST RP09", "role": "Repeater"}]})
        return Resp({"prefix": p, "count": 3, "candidates": [{"id": p + "01"}, {"id": p + "02"}, {"id": p + "03"}]})


cfgn = configparser.ConfigParser()
cfgn["AnalyzerFeed"] = {"enabled": "true", "regions": "", "url": "https://cornmeister.nl"}
svcn = AF.AnalyzerFeedService(types.SimpleNamespace(config=cfgn, db_manager=dbn, logger=logging.getLogger("n")))
check(svcn.lookup_names and svcn.url == "https://cornmeister.nl" and svcn.regions == [], "namen opzoeken staat standaard aan, ook zonder regio's; eigen adres (cornmeister.nl)")
rs = ResolveSession()
got = asyncio.run(svcn.look_up_names(rs, now=now))
check(got == 1 and rs.calls[0][0] == "https://cornmeister.nl/api/nodes/resolve", f"één eenduidige naam gevonden ({got}, {rs.calls})")
again = asyncio.run(svcn.look_up_names(rs, now=now + 60))
check(again == 0 and len(rs.calls) == 2, "niet opnieuw gevraagd binnen een week (ook niet de onduidelijke)")
s_rp = RPG.summary(dbn, RK, "7", now_ts=now)
nb = {n["prefix"]: n for n in s_rp["neighbors"]}
check(nb["1a2b3c"]["name"] == "NL TST RP09" and nb["1a2b3c"]["from_analyzer"] and nb["4d5e6f"]["name"] == "Bekende" and not nb["4d5e6f"]["from_analyzer"]
      and nb["7a7a7a"]["name"] == "", f"Repeater-pagina: naam uit de analyzer met label, meshcore-ha-naam wint ({nb})")
with dbn.connection() as c:
    for i in range(30):
        c.execute("INSERT INTO ha_repeater_neighbors (recorded_at, repeater_key, neighbor_prefix, neighbor_name, snr, secs_ago) VALUES (?,?,?,?,?,?)",
                  (int(now), RK, f"9{i:05x}", "", 1.0, 60))
    c.commit()
rs2 = ResolveSession()
asyncio.run(svcn.look_up_names(rs2, now=now + 120))
check(len(rs2.calls) <= AN.MAX_PER_HOUR - 2, f"hooguit {AN.MAX_PER_HOUR} per uur ({len(rs2.calls)} + 2 eerder)")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
