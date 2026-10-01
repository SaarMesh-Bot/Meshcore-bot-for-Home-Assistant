"""HASensors (modules/ha_sensors.py, ha_sensors_service.py): the bot's numbers as Home Assistant sensors.
Runs in the simulated build tree: test_ha_sensors.py <tree>.
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
import time
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


S = imp("modules.ha_sensors")
Svc = imp("modules.service_plugins.ha_sensors_service")


class DB:
    def __init__(self):
        self.path = tempfile.mktemp()
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
            c.execute("CREATE TABLE complete_contact_tracking (public_key TEXT, name TEXT, role TEXT, last_heard TIMESTAMP, first_heard TIMESTAMP)")
            c.execute("CREATE TABLE message_stats (timestamp INTEGER, sender_id TEXT, channel TEXT, is_dm INTEGER, hops INTEGER)")
            c.execute("CREATE TABLE command_stats (timestamp INTEGER, command_name TEXT)")
            c.execute("CREATE TABLE neighbor_links (neighbor_public_key TEXT, last_seen TIMESTAMP)")
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


db = DB()
now = time.time()
with db.connection() as c:
    for i, role in enumerate(["companion", "companion", "repeater", "repeater", "repeater", "roomserver"]):
        c.execute("INSERT INTO complete_contact_tracking VALUES (?,?,?,datetime('now','-1 hour'),datetime('now','-2 day'))", (f"k{i}", f"n{i}", role))
    c.execute("INSERT INTO complete_contact_tracking VALUES ('new1','Nieuw','companion',datetime('now'),datetime('now'))")
    for i in range(5):
        c.execute("INSERT INTO message_stats VALUES (?,?,?,0,?)", (int(now) - 60 * i, "Piet" if i % 2 else "Klaas", "#test", 3 + i))
    c.execute("INSERT INTO command_stats VALUES (?, 'test')", (int(now) - 30,))
    c.execute("INSERT INTO neighbor_links VALUES ('aa', datetime('now','-1 hour'))")
    c.execute("INSERT INTO neighbor_links VALUES ('bb', datetime('now','-9 day'))")
    c.commit()
cfg = configparser.ConfigParser()
cfg["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
cfg["HASensors"] = {"enabled": "true", "interval_minutes": "5"}
bot = types.SimpleNamespace(config=cfg, db_manager=db, logger=logging.getLogger("t"), connected=True)

s = S.collect(bot, {"nf": -108, "txa": 0.22, "rxa": 7.9}, now)
check(s["people_heard"]["state"] == 3 and s["repeaters_heard"]["state"] == 3 and s["rooms_heard"]["state"] == 1,
      f"gehoorde nodes per soort ({s['people_heard']['state']}/{s['repeaters_heard']['state']}/{s['rooms_heard']['state']})")
check(s["people_wrote"]["state"] == 2 and s["channel_messages"]["state"] == 5 and s["commands_answered"]["state"] == 1,
      "schrijvers, kanaalberichten, commando's (24 uur)")
check(s["new_nodes_today"]["state"] == 1 and s["most_hops_today"]["state"] == 7, "nieuw vandaag en meeste hops")
check(s["direct_neighbours"]["state"] == 1, "directe buren van de laatste 7 dagen")
check(s["noise_floor"]["state"] == -108 and s["noise_floor"]["attributes"]["unit_of_measurement"] == "dBm" and s["airtime_rx"]["state"] == 7.9,
      "radio: ruisvloer en zendtijd")
check(all(v["attributes"].get("friendly_name", "").startswith("MeshCore") for v in s.values()), "elke sensor heeft een leesbare naam")
check("farm_players" not in s and "map_uploads_today" not in s, "geen Farming Idle of kaartuploads: die sensoren weggelaten")
imp("modules.map_upload_stats").record(db, "sent", now)
with db.connection() as c:
    c.execute("CREATE TABLE farm_players (name TEXT, coins INTEGER, bank INTEGER)")
    c.execute("INSERT INTO farm_players VALUES ('Alice', 500, 100), ('Bob', 50, 0)"); c.commit()
s = S.collect(bot, {}, now)
check(s["farm_players"]["state"] == 2 and s["farm_richest"]["state"] == "Alice" and s["farm_richest"]["attributes"]["coins"] == 600,
      "Farming Idle: aantal spelers en de rijkste")
check(s["map_uploads_today"]["state"] == 1 and "noise_floor" not in s, "kaartuploads; zonder radiocijfers geen ruisvloer")

# the service: every sensor posted to /core/api/states/sensor.meshcore_bot_<name> with the token
posted = []


class Resp:
    status = 201
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False


class Session:
    def post(self, url, json=None, headers=None):
        posted.append((url, json["state"], headers["Authorization"]))
        return Resp()


os.environ["SUPERVISOR_TOKEN"] = "tok"
svc = Svc.HASensorsService(bot)
svc._session = Session()
bot.meshcore = types.SimpleNamespace(commands=types.SimpleNamespace())
n = asyncio.run(svc.write())
check(n == len(posted) and n >= 10 and all(u.startswith("http://supervisor/core/api/states/sensor.meshcore_bot_") and a == "Bearer tok" for u, _s, a in posted),
      f"service schrijft elke sensor naar Home Assistant ({n})")
check(svc.interval == 300, "standaard elke 5 minuten")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
