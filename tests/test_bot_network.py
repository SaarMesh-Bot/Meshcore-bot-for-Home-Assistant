"""Bot network over the internet (modules/bot_network.py, bot_network_service.py): signed messages, a name bound to its
key, the trust rules, the status numbers from the bot's own tables and the publish schedule.

Runs in the simulated build tree: test_bot_network.py <tree>.
"""
import asyncio
import configparser
import contextlib
import importlib
import json
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


N = imp("modules.bot_network")
Service = imp("modules.service_plugins.bot_network_service").BotNetworkService


class DB:
    def __init__(self, path=None):
        self.path = path or tempfile.mktemp()
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
            c.execute("CREATE TABLE complete_contact_tracking (public_key TEXT, name TEXT, role TEXT, last_heard TIMESTAMP, first_heard TIMESTAMP)")
            c.execute("CREATE TABLE message_stats (timestamp INTEGER, sender_id TEXT, channel TEXT, is_dm INTEGER, hops INTEGER)")
            c.execute("CREATE TABLE command_stats (timestamp INTEGER, command_name TEXT)")
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


def make_bot(card=None, db=None, name="Test|🤖"):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": name, "timezone": "Europe/Amsterdam"}
    if card is not None:
        cfg["BotNetwork"] = card
    bot = types.SimpleNamespace(config=cfg, logger=logging.getLogger("net"), db_manager=db or DB(), connected=True)
    bot.meshcore = types.SimpleNamespace(self_info={"radio_freq": 869.618, "radio_sf": 8, "radio_bw": 62.5})
    return bot


ON = {"enabled": "true", "region": "NL-LI"}
now = time.time()

# ---------------------------------------------------------------- signed messages
me = make_bot(ON)
far = make_bot(ON, name="Engeland|🤖")
suffix, payload = N.mqtt_message(far, "Engeland|🤖", "S", {"p": 5, "m": 40, "n": "30/8/1", "new": 2, "c": 7}, now=now)
check(suffix.endswith("/S") and len(suffix.split("/")[0]) == 12, f"onderwerp <bot-id>/<soort> ({suffix})")
check(N.receive_mqtt(me, payload, "Test|🤖") == "Engeland|🤖", "ondertekend bericht van een bot ver weg: opgeslagen")
_s, info = N.mqtt_message(far, "Engeland|🤖", "I", {"f": 869.525, "sf": 11, "bw": 250, "r": "UK-LON"}, now=now)
_s, hello = N.mqtt_message(far, "Engeland|🤖", "H", {"v": "1.1.0"}, now=now)
N.receive_mqtt(me, info, "Test|🤖"); N.receive_mqtt(me, hello, "Test|🤖")
peer = {p["name"]: p for p in N.summary(me)["peers"]}["Engeland|🤖"]
check(peer["via"] == "internet" and peer["status"]["p"] == "5" and peer["region"] == "UK-LON" and peer["radio"] == "869.525/11/250"
      and peer["version"] == "1.1.0" and len(peer["id"]) == 12, "status, info en hallo opgeslagen, met bot-id")
check(N.receive_mqtt(me, payload.replace(b'"p":5', b'"p":9'), "Test|🤖") is None, "veranderd onderweg (handtekening klopt niet): genegeerd")
check(N.receive_mqtt(me, b"hallo", "Test|🤖") is None and N.receive_mqtt(me, b'{"k":"S"}', "Test|🤖") is None, "onzin of niet ondertekend: genegeerd")
_s, bad_kind = N.mqtt_message(far, "Engeland|🤖", "X", {"a": 1}, now=now)
_s, bad_shape = N.mqtt_message(far, "Engeland|🤖", "K", {"niet": "lijst"}, now=now)
check(N.receive_mqtt(me, bad_kind, "Test|🤖") is None and N.receive_mqtt(me, bad_shape, "Test|🤖") is None, "onbekende soort of verkeerde vorm: genegeerd")
imposter = make_bot(ON, name="Nep")
_s, fake = N.mqtt_message(imposter, "Engeland|🤖", "H", {"v": "6.6.6"}, now=now)
check(N.receive_mqtt(me, fake, "Test|🤖") is None and {p["name"]: p for p in N.summary(me)["peers"]}["Engeland|🤖"]["version"] == "1.1.0",
      "zelfde naam met een andere sleutel (iemand doet zich voor als die bot): geweigerd")
_s, own = N.mqtt_message(me, "Test|🤖", "H", {"v": "1"}, now=now)
check(N.receive_mqtt(me, own, "Test|🤖") is None, "eigen bericht terug van de broker: niet als andere bot teruggegeven")
selfp = {p["name"]: p for p in N.summary(me)["peers"]}.get("Test|🤖")
check(selfp is not None and selfp["self"] and not N.is_network_bot(me, "Test|🤖"),
      "eigen bericht bewaard als 'deze bot' (voor de pagina), telt niet als andere bot")
_s, own_fake = N.mqtt_message(imposter, "Test|🤖", "H", {"v": "6.6.6"}, now=now)
N.receive_mqtt(me, own_fake, "Test|🤖")
check({p["name"]: p for p in N.summary(me)["peers"]}["Test|🤖"]["version"] == "1", "iemand anders met onze naam: niet bewaard")
_s, old = N.mqtt_message(far, "Engeland|🤖", "H", {"v": "0.1"}, now=now - 40 * 86400)
check(N.receive_mqtt(me, old, "Test|🤖") is None, "heel oud bewaard bericht (40 dagen): genegeerd")
check(N.signing_key(me).encode() == N.signing_key(me).encode(), "de sleutel van de bot blijft dezelfde (bewaard in de database)")

# ---------------------------------------------------------------- trust
beta = make_bot(ON, name="Beta")
N.receive_mqtt(me, N.mqtt_message(far, "Engeland|🤖", "K", ["nrw", "london"], now=now)[1], "Test|🤖")
N.receive_mqtt(me, N.mqtt_message(far, "Engeland|🤖", "B", ["echobot"], now=now)[1], "Test|🤖")
N._cache["at"] = 0.0
check(N.network_channels(me) == [] and not N.is_network_bot(me, "echobot"), "namen van één onbekende bot: nog niet gebruikt")
check(N.is_network_bot(me, "engeland|🤖") and not N.is_network_bot(me, "Piet"), "wie een geldig bericht stuurt, telt als bot; een mens niet")
N.receive_mqtt(me, N.mqtt_message(beta, "Beta", "K", ["nrw"], now=now)[1], "Test|🤖")
N._cache["at"] = 0.0
check(N.network_channels(me) == ["nrw"], "zelfde kanaal van twee bots: gebruikt (Kanaalradar)")
trusting = make_bot(dict(ON, trusted="Engeland|🤖"), db=me.db_manager)
N._cache["at"] = 0.0
check(N.network_channels(trusting) == ["london", "nrw"] and N.is_network_bot(trusting, "EchoBot"), "van een vertrouwde bot: meteen gebruikt")
N._cache["at"] = 0.0
check(N.network_channels(make_bot(None, db=me.db_manager)) == [] and not N.is_network_bot(make_bot(None, db=me.db_manager), "Engeland|🤖"),
      "netwerk uit: niets uit het netwerk gebruikt")
N._cache["at"] = 0.0
N.receive_mqtt(me, N.mqtt_message(beta, "Beta", "S", {"p": 7, "m": 90, "c": 3, "new": 1}, now=now)[1], "Test|🤖")
tot = N.summary(me, now=now + 60)["totals"]
check(tot == {"p": 12, "m": 130, "c": 10, "new": 3, "bots": 2, "online": 3}, f"totalen over het netwerk, deze bot niet als andere bot ({tot})")

# ---------------------------------------------------------------- an old 2.20.0 table gets the new columns
db_old = DB()
with db_old.connection() as c:
    c.execute("""CREATE TABLE botnet_peers (name TEXT PRIMARY KEY, version TEXT, radio TEXT, region TEXT, status TEXT,
                 first_seen INTEGER NOT NULL, last_seen INTEGER NOT NULL, last_hello INTEGER, last_status INTEGER, messages INTEGER NOT NULL DEFAULT 0)""")
    c.execute("INSERT INTO botnet_peers (name, first_seen, last_seen) VALUES ('Oud', 1, 1)")
    c.commit()
N.ensure_tables(db_old)
with db_old.connection() as c:
    cols = {r[1] for r in c.execute("PRAGMA table_info(botnet_peers)").fetchall()}
    kept = c.execute("SELECT COUNT(*) FROM botnet_peers").fetchone()[0]
check({"via", "pubkey"} <= cols and kept == 1, "tabel van 2.20.0 krijgt de nieuwe kolommen erbij, oude rijen blijven")

# ---------------------------------------------------------------- status numbers
db = DB()
with db.connection() as c:
    c.executemany("INSERT INTO complete_contact_tracking VALUES (?,?,?,datetime('now','-1 hour'),?)",
                  [("a1", "Piet", "companion", "2020-01-01"), ("a2", "Kees", "companion", "2020-01-01"),
                   ("r1", "Rep", "repeater", "2020-01-01"), ("x1", "Room", "roomserver", "2020-01-01")])
    c.execute("INSERT INTO complete_contact_tracking VALUES ('n1', 'Nieuw', 'companion', datetime('now'), datetime('now'))")
    c.execute("INSERT INTO complete_contact_tracking VALUES ('o1', 'Oud', 'companion', datetime('now','-3 days'), '2020-01-01')")
    c.executemany("INSERT INTO message_stats VALUES (?,?,?,?,?)",
                  [(int(now) - 60, "Piet", "#bot", 0, 3), (int(now) - 120, "Piet", "#bot", 0, 7), (int(now) - 180, "Kees", "#test", 0, 2),
                   (int(now) - 200, "Kees", None, 1, 1), (int(now) - 90000, "Oud", "#bot", 0, 20)])
    c.executemany("INSERT INTO command_stats VALUES (?,?)", [(int(now) - 60, "test"), (int(now) - 90, "ping"), (int(now) - 90000, "wx")])
    c.commit()
sb = make_bot(ON, db)
f = N.status_fields(sb, now, started_at=now - 3600)
check(f["n"] == "3/1/1" and f["new"] == 1, f"gezien in 24 u (mensen/repeaters/rooms) en nieuw vandaag ({f})")
check(f["p"] == 2 and f["m"] == 3 and f["c"] == 2 and f["up"] == 3600, "gesproken, berichten (zonder DM's), commando's, uptime")
check(N.info_fields(sb) == {"f": 869.618, "sf": 8, "bw": 62.5, "r": "NL-LI"}, "info: radio-instellingen en regio")

# ---------------------------------------------------------------- the service: publish schedule
published = []


class FakeClient:
    def publish(self, topic, payload, qos=0, retain=False):
        published.append((topic, retain, json.loads(payload)))
        return types.SimpleNamespace(rc=0)


svc = Service(sb)
svc._client, svc.mqtt_connected = FakeClient(), True
svc._due = {k: now + 100 for k in ("H", "I", "S", "K", "B")}
check(asyncio.run(svc.tick(now)) == [], "vlak na de start: nog niets (willekeurige wachttijd)")
got = asyncio.run(svc.tick(now + 200))
check(got == ["H", "I", "S"], f"daarna hallo, info en status; lege lijsten niet ({got})")
check(all(t.startswith("meshcore-bot-ha/botnet/v1/") and r for t, r, _p in published), f"retained op het onderwerp van de kaart ({published[0][0]})")
check(published[0][2]["n"] == "Test|🤖" and "sig" in published[0][2], "met de botnaam en een handtekening")
check(svc.every == {"H": 86400, "I": 604800, "S": 3600, "K": 86400, "B": 86400, "N": 86400}, f"ritme: hallo dagelijks, info wekelijks, status elk uur, buren dagelijks ({svc.every})")
check(asyncio.run(svc.tick(now + 260)) == [], "niet opnieuw tot de volgende ronde")
svc.mqtt_connected = False
svc._due = {k: 0 for k in svc._due}
check(asyncio.run(svc.tick(now + 300)) == [] and svc._due["H"] == 0, "geen verbinding: niets, en het blijft aan de beurt")
check(Service(make_bot(dict(ON, status_hours="3"))).every["S"] == 10800, "ritme instelbaar op de kaart")
vast = Service(make_bot(dict(ON, broker="mqtt.example.org", port="1883", tls="false", topic="/eigen/net/"))).broker
check(vast["host"] == "mqtt.vipje.nl" and vast["port"] == 8883 and vast["tls"] is True and vast["username"] == "mcbot"
      and vast["topic"] == "meshcore-bot-ha/botnet/v1", "de netwerkserver staat vast in de code (kaartwaarden voor een andere server tellen niet)")
check(asyncio.run(Service(make_bot(None)).tick(now)) == [], "kaart uit: niets")
import inspect
check("mcbot-{bot_id(" in inspect.getsource(Service._connect), "vaste verbindingsnaam per bot (mcbot-<bot-id>), zodat de broker elke bot apart toont")
keys = [x["key"] for x in Service.settings_schema]
check(keys[:2] == ["region", "trusted"] and not {"broker", "port", "tls", "username", "password", "topic", "channel", "transport"} & set(keys),
      f"kaart: geen serverinstellingen en geen radiokanaal ({keys[:4]})")

# ---------------------------------------------------------------- the radio itself: stats, firmware, neighbours
class Ev:
    def __init__(self, payload, type_="STATS"):
        self.payload, self.type = payload, type_


class FakeCommands:
    def __init__(self):
        self.calls = []

    async def get_stats_core(self):
        return Ev({"battery_mv": 4100, "uptime_secs": 10000, "errors": 0, "queue_len": 0})

    async def get_stats_radio(self):
        return Ev({"noise_floor": -108, "last_rssi": -92, "last_snr": 7.25, "tx_air_secs": 150, "rx_air_secs": 900})

    async def get_stats_packets(self):
        return Ev({"recv": 5000, "sent": 300, "flood_tx": 200, "direct_tx": 100, "flood_rx": 4000, "direct_rx": 1000})

    async def send_device_query(self):
        self.calls.append("query")
        return Ev({"fw ver": 8, "ver": "v1.11.0", "model": "Heltec V3", "fw_build": "01-Sep-2026"})


MY_KEY = "ab" * 32
rb = make_bot(dict(ON, find_neighbours="true", neighbours_hours="24"))
rb.meshcore = types.SimpleNamespace(self_info={"radio_freq": 869.618, "radio_sf": 8, "radio_bw": 62.5, "radio_cr": 8, "public_key": MY_KEY},
                                    commands=FakeCommands())
rs = Service(rb)
st = asyncio.run(rs.radio_stats())
check(st["nf"] == -108 and st["rssi"] == -92 and st["snr"] == 7.25 and st["txa"] == 1.5 and st["rxa"] == 9.0 and st["bat"] == 4100
      and st["rcv"] == 5000 and st["ftx"] == 200, f"radio: ruisvloer, RSSI/SNR, airtime in % van de uptime, batterij, pakkettellers ({st})")
info = asyncio.run(rs.data("I"))
check(info["fw"] == "1.11.0" and info["mdl"] == "Heltec V3" and info["node"] == MY_KEY[:12] and info["cr"] == 8 and info["f"] == 869.618,
      f"info: firmware, model, node-sleutel, CR ({info})")
asyncio.run(rs.data("I"))
check(rb.meshcore.commands.calls == ["query"], "firmware wordt één keer gevraagd en onthouden")
status = asyncio.run(rs.data("S"))
check("nf" in status and "p" in status, "status bevat de bot- en de radiocijfers")
empty = Service(make_bot(ON))
check(asyncio.run(empty.radio_stats()) == {} and asyncio.run(empty.firmware()) == {}, "radio zonder die commando's: velden weggelaten, geen fout")

with rb.db_manager.connection() as c:
    c.execute("""CREATE TABLE neighbor_links (id INTEGER PRIMARY KEY AUTOINCREMENT, self_public_key TEXT NOT NULL, neighbor_public_key TEXT NOT NULL,
                 first_seen TIMESTAMP, last_seen TIMESTAMP, observation_count INTEGER, snr_sum REAL, snr_count INTEGER, best_snr REAL, last_snr REAL,
                 last_status TEXT, scopes TEXT)""")
    c.execute("""CREATE TABLE neighbor_observations (id INTEGER PRIMARY KEY AUTOINCREMENT, observed_at TIMESTAMP, self_public_key TEXT,
                 neighbor_public_key TEXT, snr REAL, heard_secs_ago INTEGER, scopes TEXT, status TEXT)""")
    c.execute("CREATE UNIQUE INDEX nl_pair ON neighbor_links (self_public_key, neighbor_public_key)")
    from datetime import datetime, timezone, timedelta
    iso = lambda d: (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()
    c.executemany("INSERT INTO neighbor_links (self_public_key, neighbor_public_key, last_seen, best_snr, last_snr) VALUES (?,?,?,?,?)",
                  [(MY_KEY, "1f2e3d4c5b6a" + "0" * 52, iso(0), 11.0, 10.0), (MY_KEY, "29d447007f28" + "0" * 52, iso(1), -2.0, -3.0),
                   (MY_KEY, "aaaaaaaaaaaa" + "0" * 52, iso(10), 1.0, 1.0), ("cd" * 32, "bbbbbbbbbbbb" + "0" * 52, iso(0), 5.0, 5.0)])
    c.commit()
nb = rs.neighbours()
check([n["k"] for n in nb] == ["1f2e3d4c5b6a", "29d447007f28"] and nb[0]["s"] == 10.0 and nb[0]["b"] == 11.0,
      f"buren van deze radio, laatste 7 dagen, nieuwste eerst ({nb})")

import modules.neighbors_discovery as ND
found = []


async def fake_discover(mc, cfg, key, logger, **kw):
    found.append((key, cfg.collect_scopes))
    return [ND.NeighborEntry(pubkey="dd" * 32, snr=6.5, heard_at=time.time())]
real_discover, ND.discover_neighbors = ND.discover_neighbors, fake_discover
rb.connected = True
rs.started_at = time.time() - 3600
rs._client, rs.mqtt_connected = FakeClient(), True
rs._due = {k: time.time() + 9999 for k in ("H", "I", "S", "K", "B", "N")}
published.clear()
got = asyncio.run(rs.tick())
check(found == [(MY_KEY, False)] and got == ["N"], f"buren zoeken (zonder scopes), opslaan en meteen delen ({found}, {got})")
sentN = [p for t, r, p in published if t.endswith("/N")][0]["d"]
check(any(n["k"] == ("dd" * 6) for n in sentN), "de nieuw gevonden buur zit in het gedeelde bericht")
check(asyncio.run(rs.tick()) == [] and len(found) == 1, "niet opnieuw zoeken binnen het interval (ook na een herstart: bewaard)")
night = make_bot(dict(ON, find_neighbours="true"), rb.db_manager)
night.config["NightMode"] = {"enabled": "true", "start": "00:00", "end": "23:59"}
night.meshcore = rb.meshcore
rn = Service(night); rn.started_at = time.time() - 3600; rn._due = {k: time.time() + 9999 for k in ("H", "I", "S", "K", "B", "N")}
rb.db_manager.set_metadata("botnet.state", "{}")
asyncio.run(rn.tick())
check(len(found) == 1, "nachtstand: geen buren zoeken (het zendt)")
off_nb = Service(make_bot(ON)); off_nb.started_at = 0
check(off_nb.find_neighbours is False and off_nb.share["N"] is False, "buren zoeken staat standaard uit")
ND.discover_neighbors = real_discover

# receiving neighbours and info from another bot
nb_msg = N.mqtt_message(far, "Engeland|🤖", "N", [{"k": "1f2e3d4c5b6a", "s": 9.5, "b": 11, "t": int(now)}, {"k": "NIETHEX!", "s": 1}], now=now)[1]
check(N.receive_mqtt(me, nb_msg, "Test|🤖") == "Engeland|🤖", "buren van een andere bot ontvangen")
_s, i2 = N.mqtt_message(far, "Engeland|🤖", "I", {"f": 869.525, "sf": 11, "bw": 250, "cr": 5, "r": "UK-LON", "fw": "1.11.0", "mdl": "RAK4631", "node": "0123456789ab"}, now=now)
N.receive_mqtt(me, i2, "Test|🤖")
peer = {p["name"]: p for p in N.summary(me)["peers"]}["Engeland|🤖"]
check([n["key"] for n in peer["neighbors"]] == ["1f2e3d4c5b6a"] and peer["neighbors"][0]["snr"] == 9.5, f"buren opgeslagen, onzin-sleutel weggelaten ({peer['neighbors']})")
check(peer["info"] == {"fw": "1.11.0", "mdl": "RAK4631", "node": "0123456789ab"} and peer["radio"] == "869.525/11/250/5",
      f"firmware, model, node en CR opgeslagen ({peer['info']}, {peer['radio']})")
N.receive_mqtt(me, N.mqtt_message(far, "Engeland|🤖", "N", [{"k": "29d447007f28", "s": 1}], now=now)[1], "Test|🤖")
peer = {p["name"]: p for p in N.summary(me)["peers"]}["Engeland|🤖"]
check([n["key"] for n in peer["neighbors"]] == ["29d447007f28"], "nieuwe burenlijst vervangt de oude")

# ---------------------------------------------------------------- Bot network page: history and who hears whom
N.receive_mqtt(me, N.mqtt_message(me, "Test|🤖", "N", [{"k": "29d447007f28", "s": 4.5}], now=now)[1], "Test|🤖")
heard = {h["key"]: h for h in N.summary(me)["heard"]}
check(sorted(b["bot"] for b in heard["29d447007f28"]["by"]) == ["Engeland|🤖", "Test|🤖"] and heard["29d447007f28"] == N.summary(me)["heard"][0],
      "wie hoort welke repeater: door twee bots gehoord staat bovenaan")
for i, nf in enumerate((-110, -108, -105)):
    msg = N.mqtt_message(far, "Engeland|🤖", "S", {"nf": nf, "rxa": 1.5, "m": 10 + i}, now=now - (3 - i) * 3600)[1]
    N.receive_mqtt(me, msg, "Test|🤖")
    N.receive_mqtt(me, msg, "Test|🤖")   # a retained message that comes again
N.receive_mqtt(me, N.mqtt_message(me, "Test|🤖", "S", {"nf": -100}, now=now)[1], "Test|🤖")
h = N.history(me, "1")
series = {b["name"]: b for b in h["bots"]}
check(series["Engeland|🤖"]["nf"][-4:] == [-110.0, -108.0, -105.0, None] and len(series["Engeland|🤖"]["t"]) == len(set(series["Engeland|🤖"]["t"])),
      f"statusgeschiedenis per bot, zelfde bericht niet dubbel ({series['Engeland|🤖']['nf']})")
check(h["bots"][0]["name"] == "Test|🤖" and h["bots"][0]["self"] and N.history(me, "99")["days"] == 7, "eigen bot eerst; onbekende periode wordt 7 dagen")
with me.db_manager.connection() as c:
    c.execute("INSERT INTO botnet_status_log (name, ts, data) VALUES ('Oud', ?, '{}')", (int(time.time()) - 40 * 86400,))
    c.commit()
N.receive_mqtt(me, N.mqtt_message(far, "Engeland|🤖", "S", {"nf": -99}, now=now + 5)[1], "Test|🤖")
with me.db_manager.connection() as c:
    left = c.execute("SELECT COUNT(*) FROM botnet_status_log WHERE name = 'Oud'").fetchone()[0]
check(left == 0, "geschiedenis ouder dan 31 dagen wordt opgeruimd")
check(N.history(make_bot(None, db=me.db_manager))["bots"] == [] and N.summary(make_bot(None, db=me.db_manager))["heard"] == [],
      "netwerk uit: geen geschiedenis of buren op de pagina")

# ---------------------------------------------------------------- install count (anonymous, card InstallCount)
IC = imp("modules.service_plugins.install_count_service")
sent_count = []
def counted(bot_):
    svc = IC.InstallCountService(bot_)
    svc.version = "2.24.0"
    svc._send = lambda topic, payload: sent_count.append((topic, json.loads(payload))) or True
    return svc
cb = make_bot(ON)
cb.config["InstallCount"] = {"enabled": "true"}
cs = counted(cb); cs._due = 0
asyncio.run(cs.tick())
topic, body = sent_count[-1]
iid = topic.rsplit("/", 1)[-1]
check(topic.startswith("meshcore-bot-ha/count/v1/") and len(iid) == 16 and all(ch in "0123456789abcdef" for ch in iid),
      f"telling: willekeurig nummer van 16 tekens ({topic})")
check(set(body) == {"v", "d"} and body["v"] == "2.24.0", f"telling: alleen versie en datum, niets anders ({body})")
pk_hex = N.signing_key(cb).verify_key.encode().hex()
check(iid not in pk_hex and "Test" not in topic + json.dumps(body), "telling: niet afgeleid van de sleutel of de botnaam")
check(asyncio.run(cs.tick()) is False and len(sent_count) == 1, "telling: hooguit één keer per dag (ook na een herstart: bewaard)")
cs2 = counted(cb); cs2._due = 0
cb.db_manager.set_metadata("count.last_day", "2000-01-01")
asyncio.run(cs2.tick())
check(len(sent_count) == 2 and sent_count[-1][0] == topic, "telling: volgende dag weer, met hetzelfde nummer")
off = make_bot(ON); off.config["InstallCount"] = {"enabled": "false"}
co = counted(off); co._due = 0
check(asyncio.run(co.tick()) is False and len(sent_count) == 2, "telling uit: niets verstuurd")
none = make_bot(ON); cn = counted(none); cn._due = 0
check(asyncio.run(cn.tick()) is False and len(sent_count) == 2, "zonder kaart: niets verstuurd")
late = counted(cb); late._due = time.time() + 999
cb.db_manager.set_metadata("count.last_day", "2000-01-01")
check(asyncio.run(late.tick()) is False, "telling: niet voor de wachttijd na de start")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
