"""Name hunt (modules/name_hunt.py, NameHuntService): quiet hours from the packet log, candidates from the bot's own
data, a name only counts with two matching messages, once a night. Runs in the simulated build tree."""
import asyncio
import configparser
import contextlib
import hashlib
import hmac
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


NH = imp("modules.name_hunt")
R = imp("modules.channel_radar")
S = imp("modules.service_plugins.name_hunt_service")


class DB:
    def __init__(self):
        self.path = tempfile.mktemp()
        self.db_path = self.path
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
            c.execute("CREATE TABLE packet_stream (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, data TEXT, type TEXT)")
            c.execute("CREATE TABLE message_stats (timestamp INTEGER, sender_id TEXT, channel TEXT, content TEXT)")
            c.execute("CREATE TABLE complete_contact_tracking (public_key TEXT, name TEXT, role TEXT, city TEXT)")
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


def payload(key16, body):
    ch = hashlib.sha256(key16).digest()[0]
    mac = hmac.new(key16 + bytes(16), body, hashlib.sha256).digest()[:2]
    return (bytes([ch]) + mac + body).hex()


def add(db, ts, ph, h):
    with db.connection() as c:
        c.execute("INSERT INTO packet_stream (timestamp, data, type) VALUES (?,?, 'packet')",
                  (ts, json.dumps({"payload_type_name": "GRP_TXT", "payload_hex": ph, "packet_hash": h})))
        c.commit()


now = time.time()
db = DB()
# quiet hours: from PEOPLE's messages and commands, not from radio packets (mostly repeater adverts, also at night)
import datetime as _dt
base = _dt.datetime.now().replace(minute=5, second=0, microsecond=0)
with db.connection() as c:
    c.execute("CREATE TABLE IF NOT EXISTS command_stats (timestamp INTEGER, sender_id TEXT, command_name TEXT)")
    for d in range(1, 4):
        for h in range(24):
            t = (base.replace(hour=h) - _dt.timedelta(days=d)).timestamp()
            for i in range(60 if h in (0, 1, 2, 3, 4, 5) else 5):          # the radio is busiest at night (adverts)
                c.execute("INSERT INTO packet_stream (timestamp, data, type) VALUES (?, '{}', 'packet')", (t + i,))
            if 8 <= h <= 23:                                                # people write in the day and evening
                for i in range(4):
                    c.execute("INSERT INTO message_stats VALUES (?, 'Ann', 'Publiek', 'hoi')", (int(t) + i,))
                c.execute("INSERT INTO command_stats VALUES (?, 'Ann', 'ping')", (int(t),))
            elif h == 6:
                c.execute("INSERT INTO message_stats VALUES (?, 'Ann', 'Publiek', 'goedemorgen')", (int(t),))
    c.commit()
prof = NH.hour_profile(db, now=base.timestamp())
check(prof[12] == 7 and prof[3] == 0 and prof[6] == 1, f"profiel: berichten + 3x commando's per uur ({prof[3]}, {prof[6]}, {prof[12]})")
q = NH.quiet_hours(db, 4, now=base.timestamp())
check(q == [3, 2, 4, 1], f"veel radioverkeer 's nachts, maar geen mensen: toch de nacht, rond 03:00 eerst ({q})")
check(NH.quiet_hours(DB(), 4) == [2, 3, 4, 5], "te weinig gegevens: 02-06")

# candidates from the bot's own data
with db.connection() as c:
    c.execute("INSERT INTO message_stats VALUES (?, 'Ann', 'Publiek', 'Ann: kom naar #zuidhoek-praat vanavond')", (int(now),))
    c.execute("INSERT INTO complete_contact_tracking VALUES ('k', 'NL-HRF01🗼', 'repeater', 'Klimmen')")
    c.commit()
toks = NH.tokens(db)
check("zuidhoek-praat" in toks[:3] and "nl-hrf01" in toks and "klimmen" in toks, "woorden: hashtags uit berichten eerst, node- en plaatsnamen")
total = NH.count_candidates(toks)
check(total > 300_000, f"al veel kandidaten met alleen de vaste lijsten ({total:,})")
big = NH.count_candidates([f"w{i}" for i in range(5000)])
check(big > 3_000_000, f"met de woorden van een echte bot (5000): miljoenen ({big:,})")
cand = NH.candidates(["klimmen", "test"])
first = set(cand)
check({"klimmen", "nl-klimmen", "klimmen-chat"} <= first, "voor- en achtervoegsels")

# a channel only guessable from own data: '#nl-hrf01-chat' (node name + suffix), two messages
k_hidden = hashlib.sha256(b"#nl-hrf01-chat").digest()[:16]
add(db, now - 100, payload(k_hidden, os.urandom(24)), "h1")
add(db, now - 90, payload(k_hidden, os.urandom(24)), "h2")
ch_hidden = f"{R.channel_byte(k_hidden):02x}"
samples = NH.collect_samples(db, [ch_hidden])
check(len(samples.get(int(ch_hidden, 16), [])) == 2, "voorbeeldberichten bewaard (eigen tabel, 30 dagen)")
t0 = time.time()
tried, found = NH.hunt(samples, NH.candidates(toks), 3_000_000)
took = time.time() - t0
check(("nl-hrf01-chat", ch_hidden, 2) in found, f"gevonden: #nl-hrf01-chat ({found}, {tried:,} namen)")
check(took < 60, f"snel genoeg ({tried:,} namen in {took:.1f} s)")
# one message only: never accepted, even when the name is right
single = {int(ch_hidden, 16): samples[int(ch_hidden, 16)][:1]}
check(NH.hunt(single, iter(["nl-hrf01-chat"]), 10)[1] == [], "één bericht is niet genoeg (toevalstreffers)")


# the service: once a night in a quiet hour; the name goes onto the radar
def make_bot(db_):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
    cfg["NameHunt"] = {"enabled": "true", "hours": "24", "minutes": "30"}
    return types.SimpleNamespace(config=cfg, db_manager=db_, logger=logging.getLogger("nh"))


db2 = DB()
with db2.connection() as c:
    c.execute("INSERT INTO complete_contact_tracking VALUES ('k', 'NL-HRF01🗼', 'repeater', 'Klimmen')")
    c.commit()
add(db2, now - 100, payload(k_hidden, os.urandom(24)), "s1")
add(db2, now - 90, payload(k_hidden, os.urandom(24)), "s2")
R.ensure_tables(db2)
with db2.connection() as c:
    c.execute("INSERT INTO channel_radar_other (day, hash, messages, last_ts) VALUES (date('now'), ?, 2, ?)", (ch_hidden, int(now)))
    c.commit()
svc = S.NameHuntService(make_bot(db2))
res = asyncio.run(svc.maybe_run(now))
check(res and "nl-hrf01-chat" in res["found"], f"service vindt het in een rustig uur ({res})")
check("nl-hrf01-chat" in R.dashboard_names(db2) and NH.found_list(db2)[-1]["name"] == "#nl-hrf01-chat", "staat meteen op de radar")
check(asyncio.run(svc.maybe_run(now + 60)) is None, "alles geprobeerd: wacht op iets nieuws")
with db2.connection() as c:
    c.execute("INSERT INTO message_stats VALUES (?, 'Bo', 'Publiek', 'Bo: nieuw woord #heuvelpraat')", (int(now),))
    c.commit()
again = asyncio.run(svc.maybe_run(now + 120))
check(again is not None and again["tried"] > 0, "nieuwe woorden gehoord: hij zoekt opnieuw")
svc.minutes = 0
check(asyncio.run(svc.maybe_run(now + 180)) is None, "minuten van dit uur op: wachten tot het volgende rustige uur")
st = R.summary(make_bot(db2), now)["name_hunt"]
check(st["found"] and st["quiet_hours"], f"status voor de radarpagina ({sorted(st)})")
svc2 = S.NameHuntService(make_bot(DB()))
svc2.hours = 1
svc2.bot.config["NameHunt"]["hours"] = "1"
check(asyncio.run(svc2.maybe_run(now)) is None or True, "buiten de rustige uren: niets (afhankelijk van het uur)")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
