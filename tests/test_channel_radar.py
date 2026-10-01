"""Channel radar (Kanaalradar) against the real patched code: recognising a hashtag channel by channel byte + MAC (never
decrypting), counting per day, the same message via several repeaters once, unknown channels, restart safety, the card
setting for extra names, and the dashboard summary."""
import configparser
import contextlib
import hashlib
import hmac
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
logging.basicConfig(level=logging.WARNING)


def import_with_stubs(fn):
    for _ in range(40):
        try:
            return fn()
        except ModuleNotFoundError as e:
            if e.name.split(".")[0] == "modules":
                raise
            sys.modules[e.name] = MagicMock()
            sys.modules.setdefault(e.name.split(".")[0], MagicMock())
    raise SystemExit("te veel ontbrekende modules")


def _imp():
    global R, ChannelRadarService
    from modules import channel_radar as R
    from modules.service_plugins.channel_radar_service import ChannelRadarService


import_with_stubs(_imp)

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


class DB:
    def __init__(self, path):
        self.path = path
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)")
            c.execute("CREATE TABLE packet_stream (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL NOT NULL, data TEXT NOT NULL, type TEXT NOT NULL)")
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
            c.execute("INSERT OR REPLACE INTO bot_metadata (key, value) VALUES (?,?)", (k, v))
            c.commit()


def group_payload(key16: bytes, body: bytes) -> str:
    """A GRP_TXT payload as the firmware makes it: channel byte + MAC over the (here: fake) ciphertext."""
    mac = hmac.new(key16 + bytes(16), body, hashlib.sha256).digest()[:2]
    return (bytes([R.channel_byte(key16)]) + mac + body).hex()


def add_packet(db, ts, payload_hex, packet_hash, kind="packet", ptype="GRP_TXT"):
    data = json.dumps({"payload_type_name": ptype, "payload_hex": payload_hex, "packet_hash": packet_hash})
    with db.connection() as c:
        c.execute("INSERT INTO packet_stream (timestamp, data, type) VALUES (?,?,?)", (ts, data, kind))
        c.commit()


def make_bot(db, extra=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "X", "timezone": "Europe/Amsterdam"}
    cfg["ChannelRadar"] = {"enabled": "true", **(extra or {})}
    return types.SimpleNamespace(config=cfg, logger=logging.getLogger("radar"), db_manager=db)


# ---------------------------------------------------------------- recognising
k_limburg = R.key_for_name("limburg")
check(k_limburg == hashlib.sha256(b"#limburg").digest()[:16] and R.key_for_name("#Limburg") == k_limburg, "sleutel = eerste 16 bytes SHA256('#naam'), hoofdletters en # maken niet uit")
check(R.key_for_name("f1").hex() == "bbf06f639e0e37fb2d2b9d6cc6c26c14", "sleutel van #f1 klopt met die op de radio")
table = R.build_table(R.DEFAULT_NAMES)
body = os.urandom(32)
check(R.identify(group_payload(k_limburg, body), table) == ("#limburg", f"{R.channel_byte(k_limburg):02x}"), "#limburg herkend via kenmerk + MAC")
check(R.identify(group_payload(R.PUBLIC_KEY, body), table)[0] == R.PUBLIC_LABEL, "het publieke kanaal herkend")
bad = bytearray(bytes.fromhex(group_payload(k_limburg, body)))
bad[1] ^= 0xFF
check(R.identify(bad.hex(), table) == (None, f"{bad[0]:02x}"), "verkeerde MAC = niet herkend (alleen het kenmerk is niet genoeg)")
secret = R.key_for_name("mijn-geheime-kanaal-xyz")
check(R.identify(group_payload(secret, body), table)[0] is None, "onbekend kanaal blijft onbekend")
check(R.identify("zz", table) == (None, None) and R.identify("0102", table) == (None, None), "rommel en te korte pakketten geven niets")
check(len(R.DEFAULT_NAMES) >= 200, f"ruime lijst met namen ({len(R.DEFAULT_NAMES)})")

# ---------------------------------------------------------------- the service
tmp = tempfile.mkdtemp()
db = DB(f"{tmp}/bot.db")
now = time.time()
add_packet(db, now - 3600, group_payload(k_limburg, body), "AAA1")
add_packet(db, now - 3500, group_payload(k_limburg, body), "AAA1", kind="routing")      # same message via another repeater
add_packet(db, now - 3000, group_payload(k_limburg, os.urandom(40)), "AAA2")
add_packet(db, now - 2000, group_payload(R.key_for_name("test"), os.urandom(24)), "BBB1")
add_packet(db, now - 1000, group_payload(secret, os.urandom(24)), "CCC1")
add_packet(db, now - 900, "00" * 20, "DDD1", ptype="ADVERT")                                # not a group message
svc = ChannelRadarService(make_bot(db))
n = svc.scan(now)
s = R.summary(make_bot(db), now)
rows = {c["label"]: c for c in s["channels"]}
check(n == 4 and rows["#limburg"]["today"] + 0 >= 0 and rows["#limburg"]["week"] == 2 and rows["#test"]["week"] == 1,
      f"service telt per kanaal, hetzelfde bericht via 2 repeaters 1 keer ({n}, {rows})")
check(len(s["unknown"]) == 1 and s["unknown"][0]["week"] == 1 and s["unknown"][0]["hash"] == f"{R.channel_byte(secret):02x}", "onbekend kanaal apart geteld op kenmerk")
check(svc.scan(now + 60) == 0, "een tweede ronde telt niets dubbel")
svc2 = ChannelRadarService(make_bot(db))
check(svc2.scan(now + 120) == 0 and db.get_metadata("radar.last_id") == "6", "na een herstart (nieuwe service, zelfde database) niets dubbel")
add_packet(db, now + 100, group_payload(k_limburg, os.urandom(16)), "AAA3")
check(svc2.scan(now + 180) == 1 and {c["label"]: c for c in R.summary(make_bot(db), now + 180)["channels"]}["#limburg"]["week"] == 3,
      "nieuw bericht na de herstart wordt wel geteld")

# ---------------------------------------------------------------- extra names on the card
db2 = DB(f"{tmp}/bot2.db")
add_packet(db2, now - 100, group_payload(secret, os.urandom(24)), "EEE1")
svc3 = ChannelRadarService(make_bot(db2, {"extra_names": "#mijn-geheime-kanaal-xyz, andere"}))
svc3.scan(now)
labels = [c["label"] for c in R.summary(make_bot(db2, {"extra_names": "#mijn-geheime-kanaal-xyz, andere"}), now)["channels"]]
check(labels == ["#mijn-geheime-kanaal-xyz"], f"een naam op de kaart wordt herkend ({labels})")
field = [f for f in ChannelRadarService.settings_schema if f["key"] == "extra_names"]
check(field and field[0]["type"] == "list", "kaart: veld 'Extra channel names to look for'")
check(json.dumps(R.summary(make_bot(db), now)).count("payload") == 0, "het overzicht bevat geen berichtinhoud of pakketdata")

# ---------------------------------------------------------------- generated names, and counting again when the list changes
gen = R.generated_names()
check(len(gen) > 20000 and "mesh-zl" in gen and "maastricht-chat" in gen, f"gegenereerde namen ({len(gen)}), o.a. mesh-zl en maastricht-chat")
db3 = DB(f"{tmp}/bot3.db")
k_gen = R.key_for_name("mesh-zl")
add_packet(db3, now - 500, group_payload(k_gen, os.urandom(20)), "GGG1")
svc5 = ChannelRadarService(make_bot(db3))
t0 = time.time(); svc5.scan(now); took = time.time() - t0
labels = [c["label"] for c in R.summary(make_bot(db3), now)["channels"]]
check(labels == [], f"een gegenereerde naam met 1 bericht staat nog niet op de lijst (kan toeval zijn) {labels}")
add_packet(db3, now - 400, group_payload(k_gen, os.urandom(20)), "GGG2")
svc5.scan(now + 60)
chans = R.summary(make_bot(db3), now + 60)["channels"]
check([(c["label"], c["month"], c["found"]) for c in chans] == [("#mesh-zl", 2, True)], f"vanaf 2 berichten wel, gemarkeerd als gevonden ({chans})")
check(took < 5, f"eerste ronde met alle namen blijft snel ({took:.2f} s)")
later = R.summary(make_bot(db3), now + 3 * 86400)["channels"]
check([c["found"] for c in later if c["label"] == "#mesh-zl"] == [False], f"'found' alleen de eerste dag (en de dag erna), daarna niet meer ({later})")
# a name added on the card counts from the start of the packet log, and nothing is counted twice
db4 = DB(f"{tmp}/bot4.db")
k_new = R.key_for_name("zeldzaam-kanaal-q")
add_packet(db4, now - 800, group_payload(k_new, os.urandom(20)), "HHH1")
add_packet(db4, now - 700, group_payload(k_limburg, os.urandom(20)), "HHH2")
ChannelRadarService(make_bot(db4)).scan(now)
before = {c["label"]: c["month"] for c in R.summary(make_bot(db4), now)["channels"]}
svc6 = ChannelRadarService(make_bot(db4, {"extra_names": "zeldzaam-kanaal-q"}))
svc6.scan(now + 60)
after = {c["label"]: c["month"] for c in R.summary(make_bot(db4, {"extra_names": "zeldzaam-kanaal-q"}), now + 60)["channels"]}
check(before == {"#limburg": 1} and after == {"#limburg": 1, "#zeldzaam-kanaal-q": 1},
      f"naam op de kaart erbij: het pakketlogboek wordt opnieuw geteld, niets dubbel ({before} -> {after})")

# channels on the radio: recognised with their own keys (private ones too), picked up while running, counted from the log
db5 = DB(f"{tmp}/bot5.db")
k_private = os.urandom(16)                      # a private channel: its key only lives on the radio
k_pub_tag = R.key_for_name("public")            # "#public" is on no list, like the user's channel 9
add_packet(db5, now - 900, group_payload(k_private, os.urandom(20)), "RRR1")
add_packet(db5, now - 800, group_payload(k_pub_tag, os.urandom(20)), "RRR2")
add_packet(db5, now - 700, group_payload(R.PUBLIC_KEY, os.urandom(20)), "RRR3")
svc7 = ChannelRadarService(make_bot(db5))
svc7.scan(now)
labels0 = {c["label"] for c in R.summary(make_bot(db5), now)["channels"]}
check("#public" not in labels0 and "Club Kanaal" not in labels0, f"zonder kanaallijst van de radio: #public en het privékanaal onbekend ({labels0})")
with db5.connection() as c:
    c.execute("CREATE TABLE channels (channel_idx INTEGER PRIMARY KEY, channel_name TEXT NOT NULL, channel_type TEXT, channel_key_hex TEXT)")
    c.executemany("INSERT INTO channels VALUES (?,?,?,?)", [(0, "Publiek", "custom", R.PUBLIC_KEY.hex()), (1, "Club Kanaal", "custom", k_private.hex()),
                                                           (9, "#Public", "hashtag", ""), (10, "Leeg", "custom", "zz")])
    c.commit()
check(R.radio_channels(db5) == [("Club Kanaal", k_private), ("#public", k_pub_tag)],
      f"kanalen van de radio: privé met eigen sleutel, hashtag uit de naam, publiek en kapotte sleutel overgeslagen ({R.radio_channels(db5)})")
svc7.scan(now + 60)                             # the same running service: picks up the new radio channels itself
chans = {c["label"]: c for c in R.summary(make_bot(db5), now + 60)["channels"]}
check(chans.get("#public", {}).get("month") == 1 and chans.get("Club Kanaal", {}).get("month") == 1 and chans[R.PUBLIC_LABEL]["month"] == 1,
      f"nieuwe kanalen op de radio: binnen een minuut herkend en vanaf het begin van het logboek geteld, niets dubbel ({chans})")
check(chans["#public"]["found"] is False and chans["Club Kanaal"]["found"] is False, "kanalen van de radio tellen als vaste namen (vanaf 1 bericht, geen 'gevonden')")
check(not [c for c in R.summary(make_bot(db5), now + 60)["unknown"] if c["month"]], "het privékanaal staat niet meer bij de onbekende")
before_sig = db5.get_metadata("radar.names")
svc7.scan(now + 120)
check(db5.get_metadata("radar.names") == before_sig, "zonder wijziging op de radio wordt er niet opnieuw geteld")
check(any("channels on your radio" in f["help"] for f in ChannelRadarService.settings_schema), "kaart legt uit dat radiokanalen vanzelf meedoen")

# open channels without #: a key shared openly, added on the card as Name=key
db7 = DB(f"{tmp}/bot7.db")
k_open = os.urandom(16)
add_packet(db7, now - 300, group_payload(k_open, os.urandom(20)), "OOO1")
card = {"known_keys": f"Regio Open={k_open.hex()}, kapot=zz, Kort=abcd"}
check(R.card_keys(make_bot(db7, card).config) == [("Regio Open", k_open)], "kaart: alleen geldige Naam=sleutel")
ChannelRadarService(make_bot(db7, card)).scan(now)
chans = {c["label"]: c for c in R.summary(make_bot(db7, card), now)["channels"]}
check(chans.get("Regio Open", {}).get("month") == 1 and chans["Regio Open"]["found"] is False, f"open kanaal met gedeelde sleutel herkend ({chans})")
check(any(f["key"] == "known_keys" for f in ChannelRadarService.settings_schema), "kaartveld voor bekende sleutels")

# the radar page: 'Name it' checks a name against the logged messages of that byte; 'Add to radio' queues a request
db8 = DB(f"{tmp}/bot8.db")
k_secret = R.key_for_name("geheimpje-xyz")
for i in range(3):
    add_packet(db8, now - 600 + i, group_payload(k_secret, os.urandom(20)), f"NNN{i}")
ch = f"{R.channel_byte(k_secret):02x}"
check(R.verify_name(db8, "#Geheimpje-XYZ", ch) == 3, "juiste naam: alle 3 berichten kloppen (hoofdletters en # maken niet uit)")
check(R.verify_name(db8, "iets-anders", ch) == 0, "verkeerde naam: 0")
check(R.verify_name(db8, "geheimpje-xyz", "00" if ch != "00" else "01") == 0, "ander kanaalbyte: 0")
check(R.clean_name("met spatie") == "" and R.clean_name("#Ok-1") == "ok-1", "alleen geldige hashtag-namen")
R.add_dashboard_name(db8, "geheimpje-xyz")
svc8 = ChannelRadarService(make_bot(db8))
svc8.scan(now)
chans = {c["label"]: c for c in R.summary(make_bot(db8), now)["channels"]}
check(chans.get("#geheimpje-xyz", {}).get("month") == 3 and R.summary(make_bot(db8), now)["added_names"] == ["#geheimpje-xyz"],
      f"benoemd op de pagina: meteen herkend, zonder herstart, terug in het logboek geteld ({chans})")
check(R.remove_dashboard_name(db8, "#geheimpje-xyz") and R.dashboard_names(db8) == [], "naam weer weghalen")
check(R.request_add_to_radio(db8, "#BeMesh") == "#bemesh" and R.add_to_radio_requests(db8) == ["#bemesh"], "verzoek 'op de radio zetten'")
try:
    R.request_add_to_radio(db8, "Club Kanaal"); bad = False
except ValueError:
    bad = True
check(bad, "alleen hashtag-kanalen kunnen zo op de radio")

# 'Add a channel' at the top of the radar page: a hashtag name, or a name with its own key; and the 'watching' line
db9 = DB(f"{tmp}/bot9.db")
k_club = os.urandom(16)
add_packet(db9, now - 300, group_payload(k_club, os.urandom(20)), "KKK1")
check(R.add_channel(db9, "#Stilte-hier") == "#stilte-hier", "hashtag-kanaal toevoegen met alleen de naam")
check(R.add_channel(db9, "Club Kanaal", k_club.hex()) == "Club Kanaal", "kanaal met eigen sleutel toevoegen")
check(R.add_channel(db9, "#test2", R.key_for_name("#test2").hex()) == "#test2", "hashtag met zijn eigen (afgeleide) sleutel: als naam bewaard")
for bad in (("Zonder Sleutel", ""), ("X", "123"), ("Y", "zz" * 16), ("Pub", R.PUBLIC_KEY.hex())):
    try:
        R.add_channel(db9, *bad); ok = False
    except ValueError:
        ok = True
    check(ok, f"geweigerd: {bad[0]}")
b9 = make_bot(db9, {"extra_names": "95033, alameda"})
ChannelRadarService(b9).scan(now)
sm = R.summary(b9, now)
chans = {c["label"]: c for c in sm["channels"]}
check(chans.get("Club Kanaal", {}).get("month") == 1 and chans["Club Kanaal"]["found"] is False, f"kanaal met sleutel meteen herkend ({chans})")
check([(w["label"], w["source"]) for w in sm["watching"]] == [("#95033", "card"), ("#alameda", "card"), ("#stilte-hier", "page"), ("#test2", "page")],
      f"tabblad 'nog niets gehoord': kaart en pagina, met herkomst ({sm['watching']})")
check(set(sm["added_names"]) == {"#stilte-hier", "#test2", "Club Kanaal"}, f"lijst 'toegevoegd' ({sm['added_names']})")
check(R.remove_channel(db9, "Club Kanaal") and R.dashboard_keys(db9) == [] and R.remove_channel(db9, "#stilte-hier"), "weer weghalen")

# a log that starts halfway yesterday: yesterday keeps the counts from before the log, only whole days are counted again
from modules.mesh_community import day_start_ts, local_day
from datetime import timedelta
db6 = DB(f"{tmp}/bot6.db")
b6 = make_bot(db6)
today = local_day(b6, now)
yday = today - timedelta(days=1)
noon_y = day_start_ts(b6, yday) + 12 * 3600
R.ensure_tables(db6)
with db6.connection() as c:
    c.execute("INSERT INTO channel_radar (day, label, messages, last_ts) VALUES (?, '#limburg', 5, ?)", (yday.isoformat(), noon_y + 60))
    c.execute("INSERT INTO channel_radar (day, label, messages, last_ts) VALUES (?, '#limburg', 2, ?)", (today.isoformat(), int(now) - 30))
    c.commit()
add_packet(db6, noon_y + 60, group_payload(k_limburg, os.urandom(20)), "PPP1")        # already in yesterday's 5
add_packet(db6, day_start_ts(b6, today) + 10, group_payload(k_limburg, os.urandom(20)), "PPP2")
add_packet(db6, int(now) - 30, group_payload(k_limburg, os.urandom(20)), "PPP3")
svc8 = ChannelRadarService(b6)
svc8.scan(now)
with db6.connection() as c:
    counts = dict(c.execute("SELECT day, messages FROM channel_radar WHERE label='#limburg'").fetchall())
check(counts == {yday.isoformat(): 5, today.isoformat(): 2},
      f"opnieuw tellen: de eerste, halve dag van het logboek houdt zijn telling, hele dagen worden opnieuw geteld ({counts})")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
