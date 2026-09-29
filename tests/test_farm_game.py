"""Kwekerij (farm command, modules/farm_game.py): start, sow, harvest, seeds, levels, processing, selling, bank, upgrades,
giving, the top, events, crops switched off on the card, DM-only play, and every reply within 130 bytes.

Runs in the simulated build tree: test_farm_game.py <tree>.
"""
import asyncio
import configparser
import contextlib
import importlib
import logging
import os
import random
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


G = imp("modules.farm_game")
FarmCommand = imp("modules.commands.farm_command").FarmCommand
MeshMessage = imp("modules.models").MeshMessage
Translator = imp("modules.i18n").Translator


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


tr = Translator("nl", "translations/", "local/translations")
t = tr.translate
long_texts = []


def say(texts):
    for x in texts:
        if len(x.encode()) > 130:
            long_texts.append(x)
    return texts


class NoEvents(random.Random):
    """A random generator that never rolls an event or a seed (random() is always high)."""
    def random(self):
        return 0.99


db = DB()
g = G.FarmGame(db, rng=NoEvents(1))
A, B = "aa" * 32, "bb" * 32
T0 = 1_800_000_000

# ---------------------------------------------------------------- start
r = say(g.start(A, "Alice", t, now=T0))
check(r[0].startswith("Welkom, boer Alice! 4 velden en 200 munten"), f"start: 4 velden, 200 munten ({r})")
check(say(g.start(A, "Alice", t, now=T0))[0].startswith("Je hebt al een kwekerij"), "tweede keer start: al een kwekerij")
check(say(g.status(B, "Bob", t, now=T0))[0].startswith("Je hebt nog geen kwekerij"), "zonder kwekerij: hoe je begint")

# ---------------------------------------------------------------- shop and sowing
r = say(g.shop(A, t))
check(r[0].startswith("Zaad (munten, groeitijd): tomaat 20 1u") and "L2: aardbei" in " ".join(r), f"winkel: alleen level 1 + wat er komt ({r})")
check("Onbekend" in say(g.sow(A, "Alice", "banaan", None, t, now=T0))[0] or "ken ik niet" in g.sow(A, "Alice", "banaan", None, t, now=T0)[0], "onbekend gewas")
check("vanaf level 2" in say(g.sow(A, "Alice", "aardbei", None, t, now=T0))[0], "aardbei pas vanaf level 2")
r = say(g.sow(A, "Alice", "tomaten", 2, t, now=T0))
check(r[0].startswith("Gezaaid: 2 tomaat (0 eigen zaad), rijp over 1:00 u. Nog 160 munten"), f"zaaien (meervoud werkt), 2 x 20 munten ({r})")
r = say(g.sow(A, "Alice", "tomato", None, t, now=T0))
check(r[0].startswith("Gezaaid: 2 tomaat") and "120 munten" in r[0], f"zaaien zonder aantal = alle lege velden, Engelse naam werkt ({r})")
check("Geen leeg veld" in say(g.sow(A, "Alice", "tomaat", 1, t, now=T0))[0], "alle velden vol")

# ---------------------------------------------------------------- harvest
r = say(g.harvest(A, "Alice", t, now=T0 + 600))
check(r[0].startswith("Nog niets rijp, het eerste over 50 min"), f"te vroeg oogsten ({r})")
r = say(g.status(A, "Alice", t, now=T0 + 600))
check(r == ["L1 (0/50 xp), 120 munten, bank 0 | 4 tomaat 50 min"], f"stand: gelijke gewassen samen ({r})")
r = say(g.harvest(A, "Alice", t, now=T0 + 3600))
check(r[0].startswith("Geoogst: ") and "tomaat (+8 xp)" in r[0], f"oogst van 4 velden: 8 xp ({r})")
items = g._items_for_test(A) if hasattr(g, "_items_for_test") else None
with db.connection() as c:
    tomatoes = c.execute("SELECT qty FROM farm_items WHERE pubkey=? AND item='tomaat'", (A,)).fetchone()[0]
    left = c.execute("SELECT MIN(left) FROM farm_fields WHERE pubkey=?", (A,)).fetchone()[0]
check(8 <= tomatoes <= 16 and left == 9, f"4 velden x 2-4 tomaten in de schuur, planten nog 9 oogsten ({tomatoes}, {left})")
check(say(g.status(A, "Alice", t, now=T0 + 3600))[0].endswith("4 tomaat 1:00 u"), "na het oogsten groeit hij weer")
check(G.left_text(3 * 86400, t) == "3 dagen" and G.left_text(90, t) == "2 min", "tijd: minuten, uren of dagen")

# ---------------------------------------------------------------- level up, a plant that is spent
seen = []
for i in range(2, 11):
    seen += say(g.harvest(A, "Alice", t, now=T0 + 3600 * i))
check(sum("Level 2! Nieuw: aardbei" in x for x in seen) == 1, f"level omhoog meldt één keer het nieuwe gewas ({[x for x in seen if 'Level' in x]})")
check(any("plant(en) op, veld weer leeg" in x for x in seen), "na de laatste oogst: plant op")
with db.connection() as c:
    xp = c.execute("SELECT xp FROM farm_players WHERE pubkey=?", (A,)).fetchone()[0]
    empty = c.execute("SELECT COUNT(*) FROM farm_fields WHERE pubkey=? AND crop IS NULL", (A,)).fetchone()[0]
check(xp == 80 and G.level_of(xp) == 2 and empty == 4, f"na 10 oogsten: 80 xp, level 2, planten op en velden leeg ({xp}, {empty})")
check([G.level_of(x) for x in (0, 49, 50, 18000, 99999)] == [1, 1, 2, 10, 10], "levels 1 tot 10")

# ---------------------------------------------------------------- barn, processing, selling
r = say(g.barn(A, t))
check(r[0].startswith("Schuur: ") and "tomaat" in r[0], f"schuur ({r})")
r = say(g.process(A, "Alice", "soep", 2, t, now=T0 + 40000))
check(r[0].startswith("In de werkplaats: 2 tomatensoep, klaar over 1:00 u"), f"verwerken: 2x soep = 8 tomaten ({r})")
check("werkplaats is vol" in say(g.process(A, "Alice", "soep", 1, t, now=T0 + 40001))[0], "werkplaats vol (1 tegelijk)")
check("vanaf level" in say(g.process(A, "Alice", "wijn", 1, t, now=T0 + 40001))[0], "wijn pas met druiven (level 5)")
r = say(g.status(A, "Alice", t, now=T0 + 40000 + 3600))
check(any("Klaar in de werkplaats: 2 tomatensoep" in x for x in r), f"klaar product komt vanzelf in de schuur ({r})")
before = g.top()[0][2]
r = say(g.sell(A, "Alice", "soep", None, t, now=T0 + 44000))
check(r[0].startswith("Verkocht: 2 tomatensoep voor 40 munten"), f"verkopen van een product ({r})")
r = say(g.sell(A, "Alice", "alles", None, t, now=T0 + 44000))
check(r[0].startswith("Verkocht: ") and g.top()[0][2] > before + 40, f"alles verkopen ({r})")
check("heb je niet" in say(g.sell(A, "Alice", "jam", None, t, now=T0 + 44000))[0], "iets verkopen wat je niet hebt")

# ---------------------------------------------------------------- bank with interest, events
coins = g.top()[0][2]
r = say(g.bank(A, "Alice", "in", "100", t, now=T0 + 50000))
check(r[0].startswith("Gestort. Bank 100"), f"storten ({r})")
r = say(g.bank(A, "Alice", "", "", t, now=T0 + 50000 + 3 * 86400))
check(r[0].startswith("Bank: 103 munten (1% rente per dag"), f"rente: 3 dagen 1% ({r})")
check("Welk bedrag" in say(g.bank(A, "Alice", "out", "99999", t, now=T0 + 50000))[0], "meer opnemen dan er staat")
r = say(g.bank(A, "Alice", "out", "alles", t, now=T0 + 50000 + 3 * 86400))
check(r[0].startswith("Opgenomen. Bank 0"), f"alles opnemen ({r})")

# ---------------------------------------------------------------- upgrades and giving
with db.connection() as c:
    c.execute("UPDATE farm_players SET coins = 5000 WHERE pubkey=?", (A,)); c.commit()
r = say(g.upgrade(A, "Alice", "", t, now=T0 + 400000))
check(r[0].startswith("Upgrades (5000 munten): veld 400 (4/12)") and "werkplaats 2000 (1/3)" in " ".join(r), f"upgradelijst ({r})")
r = say(g.upgrade(A, "Alice", "veld", t, now=T0 + 400000))
check(r[0] == "Gekocht: een extra veld. Nog 4600 munten.", f"veld kopen ({r})")
r = say(g.upgrade(A, "Alice", "greenhouse", t, now=T0 + 400000))
check(r[0].startswith("Gekocht: een betere kas"), "kas kopen (Engels woord)")
g.sow(A, "Alice", "tomaat", 1, t, now=T0 + 400000)
check(G.grow_seconds("tomaat", 1) == 3240, "kas: 10% sneller")
g.start(B, "Bob", t, now=T0)
r = say(g.give(A, "Alice", "bob", "100", t, now=T0 + 400000))
check(r[0].startswith("100 munten naar Bob"), f"geven aan een andere boer ({r})")
check("Geen boer" in say(g.give(A, "Alice", "Niemand", "5", t, now=T0))[0] and "weinig zin" in g.give(A, "Alice", "alice", "5", t, now=T0)[0],
      "geven aan onbekende of jezelf")
top = g.top()
check(top[0][0] == "Alice" and top[1][0] == "Bob" and top[1][2] == 300, f"top: rijkste eerst ({top})")

# ---------------------------------------------------------------- events and seeds (a generator that always rolls them)
class Always(random.Random):
    def random(self):
        return 0.0


g2 = G.FarmGame(db, rng=Always(3))
C = "cc" * 32
g2.start(C, "Cor", t, now=T0)
g2.sow(C, "Cor", "tomaat", None, t, now=T0)
r = say(g2.harvest(C, "Cor", t, now=T0 + 3600))
check("Zaadje gevonden" in r[0], f"zaadjes vinden bij het oogsten ({r})")
r = say(g2.sow(C, "Cor", "tomaat", 1, t, now=T0 + 3600)) if False else None
check(any(k in (say(g2.harvest(C, "Cor", t, now=T0 + 7200))[0]) for k in ("Topoogst", "Storm", "Zakkenroller", "Controle")),
      "gebeurtenissen komen voor")
with db.connection() as c:
    seeds = c.execute("SELECT qty FROM farm_items WHERE pubkey=? AND item='seed:tomaat'", (C,)).fetchone()
check(seeds and seeds[0] > 0, f"gevonden zaad in de schuur ({seeds})")

# ---------------------------------------------------------------- crops switched off on the card
g3 = G.FarmGame(db, crops_off={"wiet"}, rng=NoEvents(2))
with db.connection() as c:
    c.execute("UPDATE farm_players SET xp = 600 WHERE pubkey=?", (B,)); c.commit()
check("staat uit" in say(g3.sow(B, "Bob", "weed", 1, t, now=T0))[0], "wiet uitgezet op de kaart")
check("wiet" not in " ".join(say(g3.shop(B, t))), "uitgezet gewas niet in de winkel")
check("joint" not in " ".join(say(g3.process(B, "Bob", "", None, t, now=T0))), "en zijn product ook niet")
check("wiet" in " ".join(say(G.FarmGame(db).shop(B, t))), "zonder die keuze: wiet wel in de winkel (level 4)")

# ---------------------------------------------------------------- the command: DM only, top in a channel, bots
def make_bot(card=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Test|🤖"}
    if card:
        cfg["Farm_Command"] = card
    return types.SimpleNamespace(config=cfg, logger=logging.getLogger("farm"), db_manager=db, translator=tr,
                                 command_manager=types.SimpleNamespace(monitor_channels=["#games"]))


async def run(text, is_dm=True, pubkey=A, name="Alice", card=None):
    cmd = FarmCommand(make_bot(card))
    out = []

    async def send_response(message, content, **kw):
        out.append(content)
        return True

    async def send_response_chunked(message, chunks, **kw):
        out.extend(chunks)
        return True
    cmd.send_response, cmd.send_response_chunked = send_response, send_response_chunked
    await cmd.execute(MeshMessage(content=text, sender_id=name, sender_pubkey=pubkey, is_dm=is_dm, channel=None if is_dm else "#games"))
    return say(out)


async def commands():
    r = await run("farm oogst", is_dm=False, pubkey=None)
    check(r[0].startswith("De kwekerij speel je via een DM"), f"in een kanaal: via DM ({r})")
    r = await run("farm top", is_dm=False, pubkey=None)
    check(r[0].startswith("Kwekerij top: 1 Alice L2"), f"farm top in een kanaal ({r})")
    r = await run("farm")
    check(r[0].startswith("L2 ("), f"farm = je stand ({r})")
    r = await run("farm stort 10")
    check(r[0].startswith("Gestort. Bank 10"), f"farm stort ({r})")
    r = await run("farm bank haal 10")
    check(r[0].startswith("Opgenomen. Bank 0"), f"farm bank haal ({r})")
    r = await run("farm onzin")
    check(r[0].startswith("Kwekerij: farm, start"), "onbekend onderdeel: uitleg")
    r = await run("farm geef bob")
    check(r[0].startswith("Geven: farm geef"), "geven zonder bedrag: uitleg")
    r = await run("farm zaai")
    check(r[0].startswith("Zaaien: farm zaai"), "zaaien zonder gewas: uitleg")
    r = await run("farm start", pubkey="dd" * 32, name="EchoBot")
    check("bot" in r[0].lower() and "doen niet mee" in r[0], f"bots doen niet mee ({r})")
    r = await run("farm winkel", pubkey=B, name="Bob", card={"crops_off": "wiet"})
    check("wiet" not in " ".join(r), "kaart: wiet uit")
    check(FarmCommand(make_bot()).get_help_text().startswith("farm = kwekerij via DM"), "help farm")

asyncio.run(commands())
check(not long_texts, f"elk antwoord past in 130 bytes {[(len(x.encode()), x) for x in long_texts[:3]]}")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
