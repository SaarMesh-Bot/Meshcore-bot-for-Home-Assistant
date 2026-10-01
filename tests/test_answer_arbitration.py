"""Bot network: only the closest bot answers (modules/answer_arbitration.py, kind "C" in bot_network.py).
Runs in the simulated build tree: test_answer_arbitration.py <tree>."""
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


A = imp("modules.answer_arbitration")
N = imp("modules.bot_network")
MeshMessage = imp("modules.models").MeshMessage
A.WAIT_S = 0.05


class DB:
    def __init__(self):
        self.path = tempfile.mktemp()
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
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


def make_bot(name, card=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": name}
    cfg["BotNetwork"] = card or {"enabled": "true"}
    return types.SimpleNamespace(config=cfg, db_manager=DB(), logger=logging.getLogger(name), services={})


# ---- ranking
m = A.message_id("#bot", "Carol", "Test")
check(m == A.message_id("#BOT", "Carol", " test "), "zelfde bericht = zelfde id (hoofdletters, spaties)")
A.add_claim(m, "other1", 3, 5.0)
check(A.winner(m, "me", 2, -8.0)[0] is True, "minder hops wint, ook met slechter signaal")
check(A.winner(m, "me", 4, 12.0)[:2] == (False, "other1"), "meer hops: de ander antwoordt")
check(A.winner(m, "me", 3, 6.0)[0] is True and A.winner(m, "me", 3, 4.0)[0] is False, "gelijke hops: beste signaal")
check(A.winner(m, "me", None, None)[0] is False, "onbekende hops tellen als ver")
check(A.winner(m, "me", 4, 12.0, now=time.time() + 60)[0] is True, "claims van langer geleden tellen niet (ander bericht)")

# ---- should_answer: the fall-backs
bot = make_bot("Vip|HA|🤖")
msg = MeshMessage(content="ping", sender_id="Carol", channel="#bot", is_dm=False, hops=4, snr=3.0)
check(asyncio.run(A.should_answer(bot, msg, "ping")) is True, "geen botnetwerk-service: gewoon antwoorden")


class Svc:
    def __init__(self, connected=True):
        self.mqtt_connected = connected
        self.claims = []

    def own_id(self):
        return "me"

    def publish_claim(self, mid, hops, snr):
        self.claims.append((mid, hops, snr))
        return True
svc = Svc(); bot.services = {"botnetwork": svc}
check(asyncio.run(A.should_answer(bot, msg, "ping")) is True and not svc.claims, "geen andere bot online: meteen antwoorden, geen claim")
N.ensure_tables(bot.db_manager)
with bot.db_manager.connection() as c:
    c.execute("INSERT INTO botnet_peers (name, first_seen, last_seen, messages, via, pubkey) VALUES ('Ander|🤖', 1, ?, 1, 'internet', 'x')",
              (int(time.time()),)); c.commit()
check(asyncio.run(A.should_answer(bot, msg, "quiz")) is True and not svc.claims, "spel (niet op de lijst): geen afspraak")
check(asyncio.run(A.should_answer(bot, MeshMessage(content="ping", sender_id="Carol", is_dm=True), "ping")) is True, "DM: altijd zelf")
m2 = A.message_id("#bot", "Carol", "ping")


async def race(other_hops, other_snr):
    task = asyncio.create_task(A.should_answer(bot, msg, "ping"))
    await asyncio.sleep(0.01)
    A.add_claim(m2, "other2", other_hops, other_snr)
    return await task
check(asyncio.run(race(2, 1.0)) is False and svc.claims[-1] == (m2, 4, 3.0), "andere bot dichterbij (2 hops): stil, eigen claim verstuurd")
A._claims.clear()
check(asyncio.run(race(6, 9.0)) is True, "andere bot verder weg: zelf antwoorden")
A._claims.clear()
svc.mqtt_connected = False
check(asyncio.run(A.should_answer(bot, msg, "ping")) is True, "broker weg: gewoon antwoorden")
svc.mqtt_connected = True
off = make_bot("X", {"enabled": "true", "answer_once": "false"}); off.services = {"botnetwork": svc}
check(asyncio.run(A.should_answer(off, msg, "ping")) is True, "kaart: uit")

# ---- a claim over MQTT: signed, only from a known bot with the same key
other = make_bot("Ander|🤖")
suffix, payload = N.mqtt_message(other, "Ander|🤖", "C", {"m": "abc", "h": 1, "s": 5.0})
A._claims.clear()
N.receive_mqtt(bot, payload, "Vip|HA|🤖")
check("abc" not in A._claims, "onbekende sleutel voor die naam: claim genegeerd")
pk = N.signing_key(other).verify_key.encode().hex()
with bot.db_manager.connection() as c:
    c.execute("UPDATE botnet_peers SET pubkey = ? WHERE name = 'Ander|🤖'", (pk,)); c.commit()
N.receive_mqtt(bot, payload, "Vip|HA|🤖")
check(A._claims.get("abc", [None])[0][:3] == (N.bot_id(pk), 1, 5.0), "bekende bot: claim telt")
with bot.db_manager.connection() as c:
    n = c.execute("SELECT messages FROM botnet_peers WHERE name = 'Ander|🤖'").fetchone()[0]
check(n == 1, "claims worden niet opgeslagen als bericht")
_s, own = N.mqtt_message(bot, "Vip|HA|🤖", "C", {"m": "zelf", "h": 0, "s": 1.0})
N.receive_mqtt(bot, own, "Vip|HA|🤖")
check("zelf" not in A._claims, "eigen claim terug van de broker: genegeerd")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
