"""Farming Idle (was Kwekerij) (farm command, modules/farm_game.py): start, sow, harvest, seeds, levels, processing, selling, bank, upgrades,
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
check(say(g.start(A, "Alice", t, now=T0))[0].startswith("Je hebt al een boerderij"), "tweede keer start: al een kwekerij")
check(say(g.status(B, "Bob", t, now=T0))[0].startswith("Je hebt nog geen boerderij"), "zonder kwekerij: hoe je begint")

# ---------------------------------------------------------------- shop and sowing
r = say(g.shop(A, t))
check(r[0].startswith("Zaadwinkel (prijs, groeit, oogsten): tomaat 20 1u 10x") and "L2: aardbei" in " ".join(r)
      and r[-1].startswith("Info: farm winkel tomaat"), f"zaadwinkel: alleen level 1 + wat er komt + uitleg ({r})")
r = say(g.shop(A, t, "tomaat"))
check(r == ["tomaat (L1): zaad 20, groeit 1u, 2-4 per oogst, 10 oogsten per plant, verkoop 3. Maak: tomatensoep, pasta"], f"winkel tomaat: alles over het gewas ({r})")
check(say(g.shop(A, t, "aardbei", 2))[0].startswith("aardbei kun je zaaien vanaf level 2") or "level 2" in say(g.shop(A, t, "aardbei", 2))[0], "zaad boven je level: niet te koop")
check(say(g.shop(A, t, "xyz"))[0].startswith("'xyz'") or "xyz" in say(g.shop(A, t, "xyz"))[0], "onbekend gewas in de winkel")
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
check(r == ["L1 (0/50 xp), 120 munten, bank 0 | 4 tomaat 50 min (nog 10x)"], f"stand: gelijke gewassen samen, met oogsten over ({r})")
r = say(g.harvest(A, "Alice", t, now=T0 + 3600))
check(r[0].startswith("Geoogst: ") and "tomaat (+8 xp)" in r[0], f"oogst van 4 velden: 8 xp ({r})")
check("Groeit opnieuw (nog 9x)." in r[0], f"na de oogst: de speler hoort dat het veld opnieuw groeit ({r})")
items = g._items_for_test(A) if hasattr(g, "_items_for_test") else None
with db.connection() as c:
    tomatoes = c.execute("SELECT qty FROM farm_items WHERE pubkey=? AND item='tomaat'", (A,)).fetchone()[0]
    left = c.execute("SELECT MIN(left) FROM farm_fields WHERE pubkey=?", (A,)).fetchone()[0]
check(8 <= tomatoes <= 16 and left == 9, f"4 velden x 2-4 tomaten in de schuur, planten nog 9 oogsten ({tomatoes}, {left})")
check(say(g.status(A, "Alice", t, now=T0 + 3600))[0].endswith("4 tomaat 1:00 u (nog 9x)"), "na het oogsten groeit hij weer, nog 9x")
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

# ---------------------------------------------------------------- daily task (the same for everyone, amount by level)
D = "dd" * 32
gq = G.FarmGame(db, rng=NoEvents(4))
gq.start(D, "Dirk", t, now=T0)
r = say(gq.quest(D, "Dirk", t, now=T0))
check(r[0].startswith("Opdracht vandaag (voor iedereen): ") and "Beloning 100 munten, +8 xp" in r[0], f"dagopdracht, beloning past bij level 1 ({r})")
check(say(gq.quest(D, "Dirk", t, now=T0 + 600)) == r, "de hele dag dezelfde opdracht")
kinds = {G.FarmGame.task_of_day(T0 + i * 86400) for i in range(30)}
check(kinds == {"harvest", "process", "sell"}, f"opdracht wisselt per dag tussen oogsten, maken en verkopen ({kinds})")
with db.connection() as c:
    c.execute("UPDATE farm_quests SET kind='harvest', need=3 WHERE pubkey=?", (D,)); c.commit()
gq.sow(D, "Dirk", "tomaat", 4, t, now=T0)
r = say(gq.harvest(D, "Dirk", t, now=T0 + 3600))
check("Opdracht klaar: +100 munten, +8 xp!" in r[0], f"oogsten (elk gewas telt): opdracht voltooid, beloning uitbetaald ({r})")
check(say(gq.quest(D, "Dirk", t, now=T0 + 3700))[0].startswith("Je opdracht van vandaag is klaar"), "daarna: klaar voor vandaag")
r2 = say(gq.quest(D, "Dirk", t, now=T0 + 86400))
check(r2[0].startswith("Opdracht vandaag (voor iedereen): ") and "(0/" in r2[0], "de volgende dag een nieuwe opdracht")
with db.connection() as c:
    c.execute("UPDATE farm_quests SET kind='sell', need=10, progress=0, done=0 WHERE pubkey=? AND done=0", (D,)); c.commit()
r = say(gq.sell(D, "Dirk", "alles", None, t, now=T0 + 86400 + 60))
check("Opdracht klaar" in r[0], f"verkoop-opdracht telt de verkochte munten ({r})")
low, high = {"xp": 0, "pubkey": "x", "name": "x"}, {"xp": 18000, "pubkey": "y", "name": "y"}
with db.connection() as c:
    ql = gq._quest(c, low, T0 + 5 * 86400); qh = gq._quest(c, high, T0 + 5 * 86400)
check(ql["kind"] == qh["kind"] and qh["need"] > ql["need"] and qh["reward_coins"] > ql["reward_coins"], "zelfde opdracht voor iedereen, level 10 moet meer en krijgt meer")

# ---------------------------------------------------------------- Mesh RPG XP from farm tasks
MA = imp("modules.mesh_archive")
xb = types.SimpleNamespace(db_manager=db, config=configparser.ConfigParser(), logger=logging.getLogger("x"))
info = MA.xp_of(xb, "dirk")
check(info["farm_tasks"] == 2 and info["xp"] >= 10, f"Mesh RPG: 5 XP per voltooide dagopdracht ({info['farm_tasks']}, {info['xp']})")

# ---------------------------------------------------------------- seed shop: buy seeds for later, clear fields
S = "5a" * 32
g.start(S, "Sam", t, now=T0)
r = say(g.shop(S, t, "tomaat", 3, now=T0))
check(r == ["Gekocht: 3 zaad tomaat voor 60. In je schuur: 3. Nog 140 munten"], f"zaad kopen voor de schuur ({r})")
check(say(g.shop(S, t, "tomaat", 99, now=T0))[0].startswith("Te weinig munten") or "140" in say(g.shop(S, t, "tomaat", 99, now=T0))[0],
      "te veel zaad: te weinig munten")
r = say(g.sow(S, "Sam", "tomaat", 4, t, now=T0))
check(r[0].startswith("Gezaaid: 4 tomaat (3 eigen zaad)") and "Nog 120 munten" in r[0], f"zaaien gebruikt eerst het gekochte zaad ({r})")
check(say(g.sow(S, "Sam", "tomaat", 1, t, now=T0))[0].startswith("Geen leeg veld: een plant geeft meerdere oogsten"), "vol: uitleg + farm ruim")
check(say(g.clear(S, "", t))[0].startswith("Veld leegmaken: farm ruim"), "ruim zonder woord: uitleg")
check(say(g.clear(S, "2", t)) == ["1 veld(en) leeggemaakt. Zaai iets nieuws: farm zaai <gewas>"], "ruim veld 2")
check(say(g.clear(S, "2", t)) == ["Daar groeit niets. Zie farm"], "leeg veld nog eens ruimen")
check(say(g.clear(S, "tomaat", t))[0].startswith("3 veld(en) leeggemaakt"), "ruim alle tomaten")
check(say(g.status(S, "Sam", t, now=T0 + 60))[0].endswith("| 4 leeg"), "daarna 4 lege velden")

# ---------------------------------------------------------------- market
E = "ee" * 32
gq.start(E, "Eva", t, now=T0)
with db.connection() as c:
    c.execute("INSERT OR REPLACE INTO farm_items (pubkey, item, qty) VALUES (?, 'jam', 5)", (D,))
    c.execute("UPDATE farm_players SET coins = 1000 WHERE pubkey=?", (E,)); c.commit()
check(say(gq.market(t, now=T0))[0].startswith("De markt is leeg"), "lege markt: hoe je iets aanbiedt")
r = say(gq.offer(D, "Dirk", "jam", 3, 60, t, now=T0))
oid = int(r[0].split("#")[1].split()[0])
check(r[0].startswith(f"Aangeboden: #{oid} 3 jam à 60 munten, 3 dagen geldig."), f"aanbieden ({r})")
check("jam" in " ".join(say(gq.barn(D, t))) and "2 jam" in " ".join(say(gq.barn(D, t))), "aangeboden goederen gaan uit de schuur (2 over)")
check(say(gq.offer(D, "Dirk", "jam", 9, 60, t, now=T0))[0].startswith("Je hebt maar 2 jam"), "niet meer aanbieden dan je hebt")
check(say(gq.market(t, now=T0))[0].startswith(f"Markt: #{oid} 3 jam à 60 (Dirk)"), "de markt toont de aanbieding")
check(say(gq.buy(D, "Dirk", str(oid), t, now=T0))[0].startswith("Dat is je eigen aanbieding"), "eigen aanbieding kopen kan niet")
r = say(gq.buy(E, "Eva", f"#{oid}", t, now=T0))
check(r[0] == "Gekocht: 3 jam van Dirk voor 180 munten. Nog 820.", f"kopen ({r})")
news = say(gq.status(D, "Dirk", t, now=T0 + 60))
check(any(x.startswith("Verkocht op de markt: 3 jam aan Eva (+180)") for x in news), f"verkoper ziet de verkoop in zijn stand ({news})")
check(not any("Verkocht op de markt" in x for x in say(gq.status(D, "Dirk", t, now=T0 + 120))), "die melding maar één keer")
check(say(gq.buy(E, "Eva", str(oid), t, now=T0))[0].startswith(f"Aanbieding #{oid} bestaat niet"), "verkochte aanbieding is weg")
r = say(gq.offer(D, "Dirk", "jam", 2, 50, t, now=T0))
oid2 = int(r[0].split("#")[1].split()[0])
check(say(gq.withdraw(D, str(oid2), t))[0] == "Ingetrokken: 2 jam terug in je schuur.", "intrekken")
gq.offer(D, "Dirk", "jam", 1, 50, t, now=T0)
gq.market(t, now=T0 + 4 * 86400)
with db.connection() as c:
    left = c.execute("SELECT COUNT(*) FROM farm_market").fetchone()[0]
    jam = c.execute("SELECT qty FROM farm_items WHERE pubkey=? AND item='jam'", (D,)).fetchone()[0]
check(left == 0 and jam == 2, f"na 3 dagen: aanbieding verlopen, goederen terug ({left}, {jam})")
check(say(gq.offer(D, "Dirk", "jam", None, None, t))[0].startswith("Aanbieden: farm bied"), "aanbieden zonder aantal/prijs: uitleg")

# ---------------------------------------------------------------- the market buys (buy orders from the dashboard)
with db.connection() as c:
    c.execute("INSERT OR REPLACE INTO farm_items (pubkey, item, qty) VALUES (?, 'jam', 6)", (D,)); c.commit()
check(say(gq.deliver(D, "Dirk", "jam", None, t, now=T0))[0] == "De markt vraagt nu geen jam. Zie farm markt", "leveren zonder inkooporder")
try:
    gq.add_order("goud", 10, 5, 3, now=T0); bad = False
except ValueError:
    bad = True
check(bad, "inkooporder voor iets dat niet bestaat: geweigerd")
o_low = gq.add_order("jam", 40, 10, 3, now=T0)
o_high = gq.add_order("jam", 90, 4, 3, now=T0)
m = say(gq.market(t, now=T0))
check(m[0].startswith("Markt koopt: 4 jam à 90") and "6 jam à 40" not in m[0] and "10 jam à 40" in m[0], f"farm markt toont wat de markt koopt, hoogste prijs eerst ({m})")
with db.connection() as c:
    coins0 = c.execute("SELECT coins FROM farm_players WHERE pubkey=?", (D,)).fetchone()[0]
r = say(gq.deliver(D, "Dirk", "jam", 5, t, now=T0))
check(r[0].startswith(f"Geleverd: 5 jam voor 400 munten. Je hebt nu {coins0 + 400}."), f"leveren: eerst de beste prijs (4x90 + 1x40) ({r})")
with db.connection() as c:
    filled = dict(c.execute("SELECT id, filled FROM farm_orders").fetchall())
    jam = c.execute("SELECT qty FROM farm_items WHERE pubkey=? AND item='jam'", (D,)).fetchone()[0]
check(filled[o_high] == 4 and filled[o_low] == 1 and jam == 1, f"orders bijgewerkt, jam uit de schuur ({filled}, {jam})")
check(not any("à 90" in x for x in say(gq.market(t, now=T0))), "volle order staat niet meer in de markt")
check(say(gq.deliver(D, "Dirk", "tomaat", None, t, now=T0))[0].startswith("De markt vraagt nu geen"), "ander item: geen order")
check(say(gq.deliver(D, "Dirk", "xyz", None, t, now=T0))[0].startswith("Leveren aan de markt: farm lever"), "onbekend item: uitleg")
check(say(gq.deliver(D, "Dirk", "jam", None, t, now=T0 + 4 * 86400))[0].startswith("De markt vraagt nu geen jam"), "verlopen order: weg")
ov = gq.overview(now=T0)
dirk = next(p for p in ov["players"] if p["name"] == "Dirk")
check(ov["task"] in ("harvest", "process", "sell") and "jam" in ov["items"] and ov["items"]["tomaat"]["kind"] == "crop",
      "overzicht: taak van de dag en de lijst met items")
check(dirk["barn"].get("jam") == 1 and "pubkey" not in dirk and "key" not in dirk and isinstance(dirk["fields"], list),
      f"overzicht per speler zonder sleutel ({sorted(dirk)})")
check(all(f["crop"] for p in ov["players"] for f in p["fields"]), "lege velden niet in het overzicht")
check({o["id"] for o in ov["orders"]} == {o_low, o_high} and not next(o for o in ov["orders"] if o["id"] == o_high)["open"],
      "overzicht: orders met open/vol")
check(gq.delete_order(o_low) and not gq.delete_order(o_low), "order verwijderen (één keer)")

# ---------------------------------------------------------------- seasons (calendar month, points = farm XP gained)
import datetime as _sdt
sdb = DB()
sg = G.FarmGame(sdb)
t_sep = _sdt.datetime(2026, 9, 10, 12).timestamp()
t_oct = _sdt.datetime(2026, 10, 1, 7).timestamp()
for k, n in (("11" * 32, "Anna"), ("22" * 32, "Bas"), ("33" * 32, "Cor"), ("44" * 32, "Dee")):
    sg.start(k, n, t, now=t_sep)
sg.season_roll(now=t_sep)
with sdb.connection() as c:
    for k, xp in (("11" * 32, 300), ("22" * 32, 120), ("33" * 32, 40)):
        c.execute("UPDATE farm_players SET xp = xp + ? WHERE pubkey = ?", (xp, k))
    c.commit()
r = say(sg.season("22" * 32, t, now=t_sep))
check(r[0].startswith("Seizoen (nog 20 d): 1 Anna 300 | 2 Bas 120 | 3 Cor 40") and r[-1].startswith("Jij: plek 2, 120 punten"),
      f"farm seizoen: top en eigen plek ({r})")
closed = sg.season_roll(now=t_oct)
check(closed and closed["season"] == "2026-09" and [x[:3] for x in closed["results"]] == [(1, "Anna", 300), (2, "Bas", 120), (3, "Cor", 40)],
      f"einde seizoen: uitslag ({closed})")
with sdb.connection() as c:
    anna = c.execute("SELECT coins FROM farm_players WHERE name='Anna'").fetchone()[0]
    dee = c.execute("SELECT coins FROM farm_players WHERE name='Dee'").fetchone()[0]
check(anna == 200 + 1000 and dee == 200, f"beloning voor de top 3 ({anna}, {dee})")
check(sg.season_roll(now=t_oct + 60) is None, "één keer afgesloten")
post = sg.season_announcement("2026-09", t)
check(post == "🏆 Farming Idle, seizoen september: 1 Anna 300 (+1000), 2 Bas 120 (+500), 3 Cor 40 (+250). Nieuw seizoen, iedereen begint op 0!"
      and len(post.encode()) <= 130, f"bekendmaking ({post})")
r = say(sg.season("11" * 32, t, now=t_oct + 120))
check("nog niemand punten" in r[0] and r[-1].startswith("Jij: plek 1, 0 punten"), f"nieuw seizoen: iedereen op 0 ({r})")
ov = sg.overview(now=t_oct + 120)
check(ov["season"]["name"] == "2026-10" and ov["season"]["past"][0]["name"] == "Anna", "dashboard: seizoen en vorige winnaars")

# season settings (dashboard): off, a week, other rewards
check(sg.season_settings() == {"enabled": True, "length": "month", "rewards": [1000, 500, 250], "start": "", "end": ""}, "standaardinstellingen")
sg.save_season_settings(False, "month", [1000, 500, 250])
check(say(sg.season("11" * 32, t, now=t_oct + 200)) == ["Seizoenen staan uit op deze bot."] and sg.season_roll(now=t_oct + 200) is None, "uit: niets")
sg.save_season_settings(True, "week", [300, 200, 100])
w_mon = _sdt.datetime(2026, 10, 5, 9).timestamp()            # Monday of week 41
sg.season_roll(now=w_mon)
with sdb.connection() as c:
    c.execute("UPDATE farm_players SET xp = xp + 50 WHERE name = 'Dee'"); c.commit()
r = say(sg.season("44" * 32, t, now=w_mon + 3600))
check(r[0].startswith("Seizoen (nog 6 d): 1 Dee 50"), f"week: nog 6 dagen, Dee voor ({r})")
closed = sg.season_roll(now=w_mon + 7 * 86400)
check(closed and closed["season"] == "2026-W41" and closed["results"][0][1:] == ("Dee", 50, 300), f"week afgesloten, beloning 300 ({closed})")
check(sg.season_announcement("2026-W41", t).startswith("🏆 Farming Idle, seizoen week 41: 1 Dee 50 (+300)"), "bekendmaking noemt de week")
check(sg.last_closed_season() == "2026-W41", "laatst afgesloten seizoen")
# a chosen period: planned, running, ended
t_now = _sdt.datetime(2026, 10, 20, 9).timestamp()
for bad, why in ((("", "2026-11-01"), "zonder begin"), (("2026-11-10", "2026-11-01"), "eind voor begin"),
                 (("2026-09-01", "2026-09-30"), "eind in het verleden"), (("2026-11-01", "2028-01-01"), "langer dan een jaar")):
    try:
        sg.save_season_settings(True, "custom", [10, 5, 1], bad[0], bad[1], now=t_now); ok = False
    except ValueError:
        ok = True
    check(ok, f"eigen periode geweigerd: {why}")
sg.save_season_settings(True, "custom", [700, 300, 100], "2026-10-25", "2026-11-08", now=t_now)
check(say(sg.season("44" * 32, t, now=t_now)) == ["Het volgende seizoen begint op 25 oktober."], "gepland: wanneer het begint")
t_in = _sdt.datetime(2026, 10, 26, 9).timestamp()
sg.season_roll(now=t_in)
with sdb.connection() as c:
    c.execute("UPDATE farm_players SET xp = xp + 25 WHERE name = 'Cor'"); c.commit()
r = say(sg.season("33" * 32, t, now=t_in))
check(r[0].startswith("Seizoen (nog 13 d): 1 Cor 25"), f"loopt: 13 dagen tot en met 8 november ({r})")
closed = sg.season_roll(now=_sdt.datetime(2026, 11, 9, 7).timestamp())
check(closed and closed["season"] == "2026-10-25_2026-11-08" and closed["results"][0][1:] == ("Cor", 25, 700), f"na de einddatum afgesloten ({closed})")
check(sg.season_announcement("2026-10-25_2026-11-08", t).startswith("🏆 Farming Idle, seizoen 25 oktober t/m 8 november: 1 Cor 25 (+700)"),
      "bekendmaking noemt de periode")
check(say(sg.season("33" * 32, t, now=_sdt.datetime(2026, 11, 10, 7).timestamp()))[0].startswith("Er loopt nu geen seizoen"), "daarna: geen seizoen")
ov = sg.overview(now=_sdt.datetime(2026, 11, 10, 7).timestamp())
check(ov["season"]["running"] is False and ov["season"]["past"][0]["season"] == "2026-10-25 – 2026-11-08", "dashboard: niets bezig, periode bij de winnaars")

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
    check(r[0] == "Farming Idle speel je in een privébericht, niet in een kanaal. Open een DM met Test|🤖 en stuur daar: farm start",
          f"in een kanaal: zegt dat je een DM met de bot moet openen, met de naam ({r})")
    r = await run("farm top", is_dm=False, pubkey=None)
    check(r[0].startswith("Farming Idle top: 1 Alice L2"), f"farm top in een kanaal ({r})")
    r = await run("farm")
    check(r[0].startswith("L2 ("), f"farm = je stand ({r})")
    r = await run("farm stort 10")
    check(r[0].startswith("Gestort. Bank 10"), f"farm stort ({r})")
    r = await run("farm bank haal 10")
    check(r[0].startswith("Opgenomen. Bank 0"), f"farm bank haal ({r})")
    r = await run("farm onzin")
    check(r[0].startswith("Farming Idle: start"), "onbekend onderdeel: uitleg")
    r = await run("farm geef bob")
    check(r[0].startswith("Geven: farm geef"), "geven zonder bedrag: uitleg")
    r = await run("farm zaai")
    check(r[0].startswith("Zaaien: farm zaai"), "zaaien zonder gewas: uitleg")
    r = await run("farm markt", is_dm=False, pubkey=None)
    check(r[0].startswith("De markt is leeg") or r[0].startswith("Markt:"), "farm markt werkt ook in een kanaal")
    r = await run("farm opdracht")
    check(r[0].startswith("Opdracht vandaag") or r[0].startswith("Je opdracht"), "farm opdracht via DM")
    r = await run("farm bied tomaat 2 5")
    check(r[0].startswith("Aangeboden:") or r[0].startswith("Je hebt maar"), f"farm bied via DM ({r})")
    r = await run("farm start", pubkey="ff" * 32, name="EchoBot")
    check("bot" in r[0].lower() and "doen niet mee" in r[0], f"bots doen niet mee ({r})")
    r = await run("farm zaad tomaat 1", pubkey=B, name="Bob")
    check(r[0].startswith("Gekocht: 1 zaad tomaat voor 20"), f"farm zaad tomaat 1 via DM ({r})")
    r = await run("farm winkel pompoen", pubkey=B, name="Bob")
    check(r[0].startswith("pompoen (L3): zaad 150"), f"farm winkel pompoen: info ({r})")
    r = await run("farm ruim", pubkey=B, name="Bob")
    check(r[0].startswith("Veld leegmaken"), f"farm ruim zonder woord ({r})")
    # farm in a channel: the bot opens a DM with that person (one contact with that name), once a day
    dms = []

    async def send_dm(key, text, **kw):
        dms.append((key, text))
        return True
    CK = "c0" * 32
    ib = make_bot()
    ib.meshcore = types.SimpleNamespace(contacts={CK: {"public_key": CK, "adv_name": "Carol"},
                                                  "d1" * 32: {"public_key": "d1" * 32, "adv_name": "Dubbel"},
                                                  "d2" * 32: {"public_key": "d2" * 32, "adv_name": "Dubbel"}})
    ib.command_manager.send_dm = send_dm
    icmd = FarmCommand(ib)
    iout = []

    async def isend(message, content, **kw):
        iout.append(content)
        return True
    icmd.send_response = isend
    await icmd.execute(MeshMessage(content="farm", sender_id="Carol", is_dm=False, channel="#games"))
    check(dms == [(CK, "Hoi Carol! Hier speel je Farming Idle. Stuur in deze DM: farm start")]
          and iout == ["@[Carol] Ik heb je een DM gestuurd, speel daar verder."], f"farm in een kanaal: DM naar Carol + korte melding ({dms}, {iout})")
    await icmd.execute(MeshMessage(content="farm start", sender_id="Carol", is_dm=False, channel="#games"))
    check(len(dms) == 1 and iout[-1].startswith("Farming Idle speel je in een privébericht"), "tweede keer dezelfde dag: geen DM meer, wel de uitleg")
    await icmd.execute(MeshMessage(content="farm", sender_id="Dubbel", is_dm=False, channel="#games"))
    check(len(dms) == 1 and iout[-1].startswith("Farming Idle speel je in een privébericht"), "twee contacten met die naam: geen DM")
    await icmd.execute(MeshMessage(content="farm", sender_id="Onbekend", is_dm=False, channel="#games"))
    check(len(dms) == 1, "onbekende naam: geen DM")
    await icmd.execute(MeshMessage(content="farm", sender_id="Echo|🤖", is_dm=False, channel="#games"))
    check(len(dms) == 1, "bots krijgen geen DM")
    gq_order = G.FarmGame(db).add_order("tomaat", 5, 3, 1)
    r = await run("farm lever tomaat 2", pubkey=B, name="Bob")
    check(r[0].startswith("Geleverd: 2 tomaat voor 10 munten") or r[0].startswith("Je hebt maar"), f"farm lever via DM ({r})")
    G.FarmGame(db).delete_order(gq_order)
    r = await run("farm winkel", pubkey=B, name="Bob", card={"crops_off": "wiet"})
    check("wiet" not in " ".join(r), "kaart: wiet uit")
    check(FarmCommand(make_bot()).get_help_text().startswith("farm = Farming Idle via DM"), "help farm")

asyncio.run(commands())

# ---------------------------------------------------------------- FarmDaily: the task of the day in the games channel
FD = imp("modules.service_plugins.farm_daily_service")
G.FarmGame(db).save_season_settings(False, "month", [1000, 500, 250])   # the plain FarmDaily tests below: no season posts
sent = []


class CM:
    async def send_channel_message(self, channel, text, **kw):
        sent.append((channel, text))
        return True


def daily_bot(card, games=True):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
    cfg["FarmDaily"] = card
    if games:
        cfg["GamesChannel"] = {"enabled": "true", "channel": "#games"}
    return types.SimpleNamespace(config=cfg, db_manager=db, translator=tr, logger=logging.getLogger("fd"), connected=True,
                                 command_manager=CM())


import datetime as _dt
from zoneinfo import ZoneInfo
morning = _dt.datetime(2026, 10, 5, 5, 59, tzinfo=ZoneInfo("Europe/Amsterdam")).timestamp()
fd = FD.FarmDailyService(daily_bot({"enabled": "true", "time": "06:00", "channel": ""}))
check(asyncio.run(fd.tick(morning)) is False and not sent, "voor 06:00: nog niets")
check(asyncio.run(fd.tick(morning + 120)) is True and sent[-1][0] == "#games" and sent[-1][1].startswith("🌱 Farming Idle, opdracht van vandaag"),
      f"om 06:00 in het spellenkanaal ({sent})")
check(asyncio.run(fd.tick(morning + 3600)) is False and len(sent) == 1, "één keer per dag")
check(asyncio.run(fd.tick(morning + 86400 + 120)) is True and len(sent) == 2, "de volgende ochtend weer")
none = FD.FarmDailyService(daily_bot({"enabled": "true", "time": "06:00", "channel": ""}, games=False))
db.set_metadata("farm.daily_posted", "")
check(none.due(morning + 2 * 86400 + 120) is None, "geen spellenkanaal en geen kanaal op de kaart: niets")
own = FD.FarmDailyService(daily_bot({"enabled": "true", "time": "06:00", "channel": "#boerderij"}))
check(own.channel() == "#boerderij", "eigen kanaal op de kaart gaat voor")
nb = daily_bot({"enabled": "true", "time": "06:00", "channel": ""})
nb.config["NightMode"] = {"enabled": "true", "start": "23:00", "end": "07:00"}
check(FD.FarmDailyService(nb).due(morning + 3 * 86400 + 120) is None, "nachtstand tot 07:00: wacht tot de nacht voorbij is")
empty_db = type(db)()
eb = daily_bot({"enabled": "true", "time": "06:00", "channel": ""}); eb.db_manager = empty_db
e_fd = FD.FarmDailyService(eb)
d0 = e_fd.due(morning + 120)
check(d0 and d0[1] == "🌱 Farming Idle: begin vandaag je eigen boerderij! Open een DM (privébericht) met Test|🤖 en stuur daar: farm start", f"nog niemand speelt: 's ochtends een uitnodiging ({d0})")
sent.clear(); e_fd.bot.command_manager = CM()
asyncio.run(e_fd.tick(morning + 120))
check(e_fd.due(morning + 8 * 3600 + 120) is None, "dan om 14:00 geen tweede uitnodiging dezelfde dag")

# season results in the games channel on the first morning of a new month, before the task
sdb2 = DB()
sg2 = G.FarmGame(sdb2)
sg2.start("55" * 32, "Eef", t, now=t_sep)
sg2.season_roll(now=t_sep)
with sdb2.connection() as c:
    c.execute("UPDATE farm_players SET xp = xp + 70"); c.commit()
sd_bot = daily_bot({"enabled": "true", "time": "06:00", "invite_time": "", "channel": ""}); sd_bot.db_manager = sdb2
sfd = FD.FarmDailyService(sd_bot)
due1 = sfd.due(_sdt.datetime(2026, 10, 1, 6, 5, tzinfo=ZoneInfo("Europe/Amsterdam")).timestamp())
check(due1 and due1[0] == "farm.season_announced:2026-09" and due1[1].startswith("🏆 Farming Idle, seizoen september: 1 Eef 70 (+1000)"), f"06:00 op de 1e: eerst de uitslag ({due1})")
sent.clear(); sfd.bot.command_manager = CM()
asyncio.run(sfd.tick(_sdt.datetime(2026, 10, 1, 6, 5, tzinfo=ZoneInfo("Europe/Amsterdam")).timestamp()))
due2 = sfd.due(_sdt.datetime(2026, 10, 1, 6, 6, tzinfo=ZoneInfo("Europe/Amsterdam")).timestamp())
check(len(sent) == 1 and due2 and due2[0] == "farm.daily_posted", f"daarna de gewone ochtendopdracht ({due2})")

# with players: task at 06:00, invitation at 14:00
pl = FD.FarmDailyService(daily_bot({"enabled": "true", "time": "06:00", "invite_time": "14:00", "channel": ""}))
db.set_metadata("farm.daily_posted", ""); db.set_metadata("farm.invite_posted", "")
sent.clear()
day5 = morning + 5 * 86400
asyncio.run(pl.tick(day5 + 120))
check(len(sent) == 1 and sent[0][1].startswith("🌱 Farming Idle, opdracht van vandaag"), f"06:00: de opdracht ({sent})")
check(asyncio.run(pl.tick(day5 + 4 * 3600)) is False, "10:00: niets")
asyncio.run(pl.tick(day5 + 8 * 3600 + 120))
check(len(sent) == 2 and sent[1][1].startswith("🌱 Farming Idle: begin vandaag je eigen boerderij!"), f"14:00: uitnodiging om mee te doen, ook met spelers ({sent})")
check(asyncio.run(pl.tick(day5 + 9 * 3600)) is False and len(sent) == 2, "één uitnodiging per dag")
off = FD.FarmDailyService(daily_bot({"enabled": "true", "time": "06:00", "invite_time": "", "channel": ""}))
check(off.invite_minute is None, "uitnodiging leeg op de kaart: uit")
# 12:00: what the market buys, only with an open order
ob = FD.FarmDailyService(daily_bot({"enabled": "true", "time": "06:00", "invite_time": "", "orders_time": "12:00", "channel": ""}))
day9 = morning + 9 * 86400
db.set_metadata("farm.daily_posted", ""); db.set_metadata("farm.orders_posted", "")
sent.clear()
asyncio.run(ob.tick(day9 + 120))
check(ob.due(day9 + 6 * 3600 + 120) is None, "12:00 zonder open inkooporder: niets")
fgo = G.FarmGame(db)
ids = [fgo.add_order("jam", 80, 20, 3, now=day9), fgo.add_order("wijn", 300, 5, 3, now=day9)]
for i in range(8):
    ids.append(fgo.add_order("tomaat", 5 + i, 100, 3, now=day9))
check(ob.due(day9 + 5 * 3600) is None, "11:00: nog niet")
sent.clear()
check(asyncio.run(ob.tick(day9 + 6 * 3600 + 120)) is True and sent and sent[0][0] == "#games", f"12:00: inkooporders in het spellenkanaal ({sent})")
txt = sent[0][1] if sent else ""
check(txt.startswith("🛒 Farming Idle, de markt koopt: 5 wijn à 300, 20 jam à 80") and "farm lever" in txt and len(txt.encode()) <= 130,
      f"hoogste prijs eerst, past in 130 bytes ({len(txt.encode())}: {txt})")
check(asyncio.run(ob.tick(day9 + 7 * 3600)) is False and len(sent) == 1, "één keer per dag")
check(FD.FarmDailyService(daily_bot({"enabled": "true", "orders_time": "", "channel": ""})).orders_minute is None, "leeg op de kaart: uit")
for i in ids:
    fgo.delete_order(i)
check(not long_texts, f"elk antwoord past in 130 bytes {[(len(x.encode()), x) for x in long_texts[:3]]}")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
