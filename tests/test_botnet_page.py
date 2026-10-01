"""Bot network page on the real patched v1.1.0 viewer: menu item only while the card is on, page, /api/botnet and
/api/botnet/history, and the Bots page only links to it."""
import configparser
import os
import sys
import tempfile
import time
import types

TREE = sys.argv[1]
os.chdir(TREE)
sys.path.insert(0, TREE)

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


from modules.web_viewer.app import BotDataViewer  # noqa: E402

H = {"X-Requested-With": "XMLHttpRequest"}


def viewer(on):
    work = tempfile.mkdtemp()
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"db_path": f"{work}/viewer.db", "bot_name": "Mesh|HA|🤖"}
    cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": ""}
    cfg["Channels"] = {"monitor_channels": "#test"}
    if on is not None:
        cfg["BotNetwork"] = {"enabled": "true" if on else "false"}
    with open(f"{work}/config.ini", "w") as f:
        cfg.write(f)
    v = BotDataViewer(config_path=f"{work}/config.ini")
    v.app.config["TESTING"] = True
    return v, v.app.test_client()


# ---------------------------------------------------------------- off (and no card at all): no menu item
for state in (False, None):
    _v, c = viewer(state)
    home = c.get("/repeater").get_data(as_text=True)
    bots = c.get("/bots").get_data(as_text=True)
    check('href="/botnet"' not in home and 'href="/botnet"' not in bots, f"netwerk {'uit' if state is False else 'zonder kaart'}: geen tabblad, geen verwijzing")
    check(c.get("/api/botnet", headers=H).get_json()["enabled"] is False and c.get("/api/botnet/history", headers=H).get_json()["bots"] == [],
          "netwerk uit: de API zegt 'uit', geen gegevens")

# ---------------------------------------------------------------- on
v, c = viewer(True)
page = c.get("/botnet")
html = page.get_data(as_text=True)
check(page.status_code == 200 and "c-nf" in html and "bn-heard" in html, "pagina /botnet met grafieken en burentabel")
check(html.index('href="/repeater"') < html.index('href="/botnet"'), "menu: Bot network staat na Repeater")
bots = c.get("/bots").get_data(as_text=True)
check('href="/botnet"' in bots and "net-card" not in bots and "/api/botnet" not in bots, "Bots-pagina: alleen een verwijzing, het oude blok is weg")

now = int(time.time())
with v.db_manager.connection() as conn:
    from modules import bot_network as N
    N.ensure_tables(v.db_manager)
    conn.execute("INSERT INTO botnet_peers (name, first_seen, last_seen, via, status, last_status) VALUES ('Ver|🤖', ?, ?, 'internet', '{\"p\": \"4\"}', ?)",
                 (now - 99, now - 60, now - 60))
    conn.execute("INSERT INTO botnet_peers (name, first_seen, last_seen, via) VALUES ('Mesh|HA|🤖', ?, ?, 'self')", (now - 99, now - 60))
    for i in range(5):
        conn.execute("INSERT INTO botnet_status_log (name, ts, data) VALUES ('Ver|🤖', ?, ?)", (now - i * 3600, '{"nf": "-107", "m": "12"}'))
    conn.execute("INSERT INTO botnet_links (from_name, neighbor, snr, ts) VALUES ('Ver|🤖', '0a1b2c3d4e5f', 7.5, ?)", (now,))
    conn.commit()
d = c.get("/api/botnet", headers=H).get_json()
check([p["name"] for p in d["peers"]] == ["Mesh|HA|🤖", "Ver|🤖"] and d["peers"][0]["self"] and d["totals"]["bots"] == 1,
      f"eigen bot eerst en niet meegeteld als andere bot ({[p['name'] for p in d['peers']]})")
check(d["heard"][0]["key"] == "0a1b2c3d4e5f" and d["heard"][0]["by"][0]["bot"] == "Ver|🤖", "wie hoort welke repeater")
h = c.get("/api/botnet/history?days=1", headers=H).get_json()
check(h["days"] == 1 and h["bots"][0]["name"] == "Ver|🤖" and h["bots"][0]["nf"] == [-107.0] * 5, f"geschiedenis voor de grafieken ({h['bots']})")
own = open(os.path.join(TREE, "modules", "web_viewer", "templates", "botnet.html")).read()
check("textContent" in own and "innerHTML" not in own and "insertAdjacentHTML" not in own, "namen uit het netwerk alleen als tekst op de pagina")

# ---------------------------------------------------------------- restart button (Plugins page)
os.environ.pop("SUPERVISOR_TOKEN", None)
v.app.config["TESTING"] = False   # the X-Requested-With check is off in test mode
check(c.post("/api/addon/restart").status_code == 403, "herstarten zonder X-Requested-With: geweigerd")
v.app.config["TESTING"] = True
r = c.post("/api/addon/restart", headers=H)
check(r.status_code == 400 and "add-on" in r.get_json()["error"], "herstarten buiten Home Assistant: nette melding")
calls = []
import urllib.request as _ur
real_urlopen = _ur.urlopen
_ur.urlopen = lambda req, timeout=None: calls.append((req.full_url, req.get_method(), req.headers.get("Authorization"))) or types.SimpleNamespace(read=lambda: b"")
os.environ["SUPERVISOR_TOKEN"] = "tok"
r = c.post("/api/addon/restart", headers=H)
time.sleep(1.5)
_ur.urlopen = real_urlopen
os.environ.pop("SUPERVISOR_TOKEN", None)
check(r.get_json() == {"restarting": True} and calls == [("http://supervisor/addons/self/restart", "POST", "Bearer tok")],
      f"herstartknop: de Supervisor krijgt POST /addons/self/restart ({calls})")

# ---------------------------------------------------------------- Radar: two tabs, Repeater radar
html = c.get("/radar").get_data(as_text=True)
check('id="tab-channels"' in html and 'id="tab-repeaters"' in html and "Repeater radar" in html, "Radar-pagina: tabbladen Channel radar en Repeater radar")
now_s = int(time.time())
with v.db_manager.connection() as conn:
    conn.execute("""CREATE TABLE IF NOT EXISTS complete_contact_tracking (id INTEGER PRIMARY KEY, public_key TEXT, name TEXT, role TEXT,
                    first_heard TIMESTAMP, last_heard TIMESTAMP, latitude REAL, longitude REAL, city TEXT, snr REAL, hop_count INTEGER)""")
    conn.execute("CREATE TABLE IF NOT EXISTS daily_stats (date DATE, public_key TEXT, advert_count INTEGER)")
    conn.execute("""CREATE TABLE IF NOT EXISTS neighbor_links (self_public_key TEXT, neighbor_public_key TEXT, last_seen TIMESTAMP,
                    last_snr REAL, best_snr REAL)""")
    rows = [("aa11" + "0" * 60, "Heuvel RPT", 50.90, 5.95, "Heerlen", 9.5, 0, "-1 hour", "-30 day"),
            ("aa22" + "0" * 60, "Dal RPT", 50.80, 5.70, "Maastricht", -3.0, 2, "-2 hour", "-2 day"),
            ("bb33" + "0" * 60, "Oud RPT", 0, 0, None, 1.0, 1, "-3 day", "-60 day"),
            ("cc44" + "0" * 60, "Mens", 50.9, 5.9, "Heerlen", 1.0, 1, "-1 hour", "-9 day")]
    for key, name, lat, lon, city, snr, hops, last, first in rows:
        conn.execute("INSERT INTO complete_contact_tracking (public_key, name, role, first_heard, last_heard, latitude, longitude, city, snr, hop_count) "
                     "VALUES (?,?,?,datetime('now', ?),datetime('now', ?),?,?,?,?,?)",
                     (key, name, "companion" if name == "Mens" else "repeater", first, last, lat, lon, city, snr, hops))
    conn.execute("INSERT INTO daily_stats (date, public_key, advert_count) VALUES (date('now'), ?, 5)", (rows[0][0],))
    conn.execute("INSERT INTO neighbor_links (self_public_key, neighbor_public_key, last_seen, last_snr, best_snr) "
                 "VALUES ('me', ?, datetime('now', '-1 hour'), 8.25, 10)", (rows[0][0],))
    conn.execute("INSERT INTO botnet_links (from_name, neighbor, snr, ts) VALUES ('Ver|🤖', 'aa1100000000', 4.0, ?)", (now_s,))
    conn.execute("INSERT OR REPLACE INTO bot_metadata (key, value) VALUES ('radio.position', '{\"lat\": 50.936, \"lon\": 5.956}')")
    conn.commit()
rr = c.get("/api/radar/repeaters?days=1", headers=H).get_json()
names = [r["name"] for r in rr["repeaters"]]
check(names == ["Heuvel RPT", "Dal RPT"], f"24 uur: alleen repeaters, nieuwste eerst ({names})")
h1 = rr["repeaters"][0]
check(h1["direct"] and h1["direct_snr"] == 8.25 and h1["bots"] == 1 and h1["adverts"] == 5 and h1["same_prefix"] == 1,
      f"rechtstreeks, andere bots, adverts, zelfde prefix ({h1})")
check(h1["km"] is not None and 3 < h1["km"] < 6 and rr["has_position"], f"afstand vanaf de positie van de radio ({h1['km']})")
check(rr["repeaters"][1].get("new") and not h1.get("new") and rr["totals"]["new"] == 1, "nieuw = deze week voor het eerst gehoord")
check(h1["bot_list"] == [{"bot": "Ver|🤖", "snr": 4.0}] and h1["direct_best"] == 10 and h1["first_heard"] and h1["first_heard"] < now_s - 20 * 86400,
      f"details voor het venster: welke bots, beste SNR, eerst gehoord ({h1['bot_list']}, {h1['direct_best']})")
check("function details(r)" in html and 'id="rr-modal"' in html and "state.filter === 'shared'" in html, "klikbare tegels en rijen met detailvenster")
check(rr["totals"] == {"heard": 2, "direct": 1, "new": 1, "shared_prefix": 2, "farthest_km": h1["km"], "near_km": 50}, f"tegels ({rr['totals']})")
r7 = c.get("/api/radar/repeaters?days=7", headers=H).get_json()
old_rpt = [r for r in r7["repeaters"] if r["name"] == "Oud RPT"]
far = [r for r in r7["repeaters"] if r["name"] == "Dal RPT"][0]
check("place" in far and "bot_list" not in far and "snr" in far, "compact antwoord: lege velden weggelaten")
check(len(r7["repeaters"]) == 3 and old_rpt and old_rpt[0]["km"] is None, "7 dagen: ook de oudere, zonder plek geen afstand")
check(rr["map"] is None, "zonder MapUploader: geen kaarttegel")
from modules import map_upload_stats as _mus
_mus.record(v.db_manager, "sent"); _mus.record(v.db_manager, "new")
rm = c.get("/api/radar/repeaters?days=1", headers=H).get_json()["map"]
check(rm["today"] == {"sent": 1, "new": 1, "duplicate": 0, "failed": 0} and rm["week"]["sent"] == 1, f"kaarttegel: tellingen van vandaag en 7 dagen ({rm})")
radar_src = open(os.path.join(TREE, "modules", "web_viewer", "templates", "radar.html")).read()
check("innerHTML" not in radar_src and "insertAdjacentHTML" not in radar_src, "radar: namen alleen als tekst")

# ---------------------------------------------------------------- first-start wizard
os.environ.pop("SUPERVISOR_TOKEN", None)
work = tempfile.mkdtemp()
wcfg = configparser.ConfigParser()
wcfg["Bot"] = {"db_path": f"{work}/viewer.db", "bot_name": "Mesh|HA|🤖"}
wcfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": ""}
wcfg["Channels"] = {"monitor_channels": "#test"}
wcfg["Setup"] = {"done": "false"}
wcfg["Quiz_Command"] = {"enabled": "true"}
with open(f"{work}/config.ini", "w") as f:
    wcfg.write(f)
wv = BotDataViewer(config_path=f"{work}/config.ini")
wv.app.config["TESTING"] = True
wc = wv.app.test_client()
with wv.db_manager.connection() as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS channels (channel_idx INTEGER, channel_name TEXT, channel_key_hex TEXT)")
    conn.executemany("INSERT INTO channels (channel_idx, channel_name, channel_key_hex) VALUES (?,?,?)",
                     [(0, "Public", ""), (1, "#test", ""), (2, "#bot", ""), (3, "#games", "")])
    conn.commit()
home = wc.get("/radar").get_data(as_text=True)
check('href="/setup"' in home and "Start the setup" in home, "nieuwe installatie: melding 'Start the setup' en menu-item Setup")
check(wc.get("/setup").status_code == 200, "pagina /setup")
first = wc.get("/")
check(first.status_code == 302 and first.headers["Location"].endswith("/setup"), f"nieuwe installatie: de startpagina opent de wizard ({first.status_code})")
st = wc.get("/api/setup", headers=H).get_json()
check(st["radio_channels"] == ["Public", "#test", "#bot", "#games"] and st["bot_channels"] == ["#test"] and not st["done"],
      f"wizard leest de kanalen van de radio en de huidige keuzes ({st['radio_channels']}, {st['bot_channels']})")
check(st["groups"]["games"]["on"] and "quiz" in st["groups"]["games"]["commands"], "commandogroepen met hun huidige stand")
r = wc.post("/api/setup/apply", headers=H, json={
    "bot_channels": ["#test", "#bot"], "public": "Public", "greeter": True,
    "groups": {"games": True, "fun": False}, "games_channel": "#games",
    "features": {"night": True, "botnet": False, "repeaterwatch": True, "hasensors": True}}).get_json()
check(r["success"] and r["restart_required"] and r["channels_saved"] is False, f"opslaan; buiten HA: kanalen niet opgeslagen, dat wordt gemeld ({r})")
after = configparser.ConfigParser(interpolation=None, strict=False); after.read(f"{work}/config.ini")
check(after["Setup"]["done"] == "true" and after["ChannelHint"]["channels"] == "Public" and after["ChannelHint"]["where"] == "#test,#bot,#games",
      f"afgerond, verwijskanaal en waar commando's werken ({dict(after['ChannelHint'])})")
check(after["GamesChannel"]["channel"] == "#games" and after["Greeter_Command"]["channels"] == "Public" and after["NightMode"]["enabled"] == "true",
      "spellenkanaal, begroeter en nachtstand")
check(after["Joke_Command"]["enabled"] == "false" and after["Quiz_Command"]["enabled"] == "true", "groep 'fun' uit, 'games' aan")
home2 = wc.get("/radar").get_data(as_text=True)
check("Start the setup" not in home2 and 'href="/setup"' in home2, "na de wizard: geen melding meer, menu-item blijft")
check(wc.get("/").status_code == 200, "na de wizard: de startpagina is weer de gewone startpagina")
wsrc = open(os.path.join(TREE, "modules", "web_viewer", "templates", "setup.html")).read()
check("innerHTML" not in wsrc and "insertAdjacentHTML" not in wsrc, "wizard: kanaalnamen alleen als tekst")

# ---------------------------------------------------------------- Games -> Farming Idle tab (players, market, buy orders)
gv, gc = viewer(None)
from modules.farm_game import FarmGame  # noqa: E402
fg = FarmGame(gv.db_manager)
fg.start("aa" * 32, "Alice", lambda k, **kw: k)
fg.start("bb" * 32, "Echo|🤖", lambda k, **kw: k)
gpage = gc.get("/games").get_data(as_text=True)
check('id="tab-farm"' in gpage and "farm-players" in gpage and "order-form" in gpage, "Games-pagina: tabblad Farming Idle")
gsrc = open(os.path.join(TREE, "modules", "web_viewer", "templates", "games.html")).read()
check("innerHTML" not in gsrc and "insertAdjacentHTML" not in gsrc, "Farming Idle: spelersnamen alleen als tekst")
fo = gc.get("/api/games/farm", headers=H).get_json()
check([p["name"] for p in fo["players"]] == ["Alice"] and fo["players"][0]["fields_total"] == 4, f"spelers, bots weggelaten ({[p['name'] for p in fo['players']]})")
check("aa" * 6 not in str(fo), "geen publieke sleutels naar de browser")
r = gc.post("/api/games/farm/orders", headers=H, json={"item": "jam", "qty": 10, "price": 80, "days": 2})
oid = r.get_json().get("id")
check(r.status_code == 200 and oid, "inkooporder toevoegen")
check(gc.post("/api/games/farm/orders", headers=H, json={"item": "goud", "qty": 1, "price": 1}).status_code == 400, "onbekend item: 400")
check(gc.post("/api/games/farm/orders", headers=H, json={"item": "jam", "qty": 0, "price": 5}).status_code == 400, "aantal 0: 400")
fo = gc.get("/api/games/farm", headers=H).get_json()
check(fo["orders"][0]["item"] == "jam" and fo["orders"][0]["open"] and fo["orders"][0]["price"] == 80, "order staat in het overzicht")
gv.app.config["TESTING"] = False
check(gc.post("/api/games/farm/orders", json={"item": "jam", "qty": 1, "price": 5}).status_code == 403, "zonder X-Requested-With: geweigerd")
gv.app.config["TESTING"] = True
check(gc.post(f"/api/games/farm/orders/{oid}/delete", headers=H).get_json()["deleted"] is True, "order verwijderen")
check(gc.get("/api/games/farm", headers=H).get_json()["orders"] == [], "daarna geen orders")
r = gc.post("/api/games/farm/season", headers=H, json={"enabled": True, "length": "week", "rewards": [100, 50, 25]})
check(r.status_code == 200 and r.get_json()["length"] == "week", "seizoensinstellingen opslaan")
check(gc.get("/api/games/farm", headers=H).get_json()["season"]["settings"]["rewards"] == [100, 50, 25], "en terug in het overzicht")
check(gc.post("/api/games/farm/season", headers=H, json={"rewards": [1, 2]}).status_code == 400, "twee beloningen: 400")
check(gc.post("/api/games/farm/season", headers=H, json={"length": "custom", "rewards": [1, 2, 3], "start": "2099-01-10", "end": "2099-01-01"}).status_code == 400,
      "eigen periode: eind voor begin -> 400")
r = gc.post("/api/games/farm/season", headers=H, json={"length": "custom", "rewards": [1, 2, 3], "start": "2099-01-01", "end": "2099-01-31"})
check(r.status_code == 200 and r.get_json()["start"] == "2099-01-01", "eigen periode opslaan")
check('id="season-start"' in gc.get("/games").get_data(as_text=True), "datumvelden op het tabblad")
check('id="season-form"' in gc.get("/games").get_data(as_text=True), "seizoensblok op het tabblad")

# ---------------------------------------------------------------- Mailbox page
from modules import mailbox as _mb  # noqa: E402
_mb.add(gv.db_manager, "Carol", None, "Bob", "tot zaterdag", "#bot")
_mb.add(gv.db_manager, "Dirk", "ee" * 32, "Bob", "geheim", "DM")
mp = gc.get("/mailbox").get_data(as_text=True)
check('id="mb-body"' in mp and 'href="/mailbox"' in mp, "pagina Mailbox met menu-item")
mj = gc.get("/api/mailbox", headers=H).get_json()
texts = {m["from"]: m["text"] for m in mj["messages"]}
check(mj["counts"]["waiting"] == 2 and texts["Carol"] == "tot zaterdag" and texts["Dirk"] is None and "geheim" not in str(mj),
      "wachtende berichten; tekst van een DM-bericht niet naar de browser")
mid = next(m["id"] for m in mj["messages"] if m["from"] == "Carol")
check(gc.post(f"/api/mailbox/{mid}/delete", headers=H).get_json()["deleted"] is True and
      gc.get("/api/mailbox", headers=H).get_json()["counts"]["waiting"] == 1, "bericht weghalen")
msrc = open(os.path.join(TREE, "modules", "web_viewer", "templates", "mailbox.html")).read()
check("innerHTML" not in msrc and "insertAdjacentHTML" not in msrc, "Mailbox: teksten alleen als tekst")

# ---------------------------------------------------------------- ha card: one row per entity
hp = next(p for p in gc.get("/api/plugins", headers=H).get_json()["plugins"] if p["name"] == "ha")
check(any(rb["id"] == "entity" for rb in hp["repeating_blocks"]), "ha-kaart heeft regels per entiteit")
r = gc.post("/api/plugins/command/ha", headers=H, json={"repeating_blocks": {"entity": [
    {"enabled": True, "values": {"entity_id": "switch.feest_verlichting", "name": "feest", "switch": True}}]}})
check(r.status_code == 200, f"regel opslaan ({r.get_json()})")
hp = next(p for p in gc.get("/api/plugins", headers=H).get_json()["plugins"] if p["name"] == "ha")
blk = next(rb for rb in hp["repeating_blocks"] if rb["id"] == "entity")["blocks"]
check(blk and blk[0]["values"].get("entity_id") == "switch.feest_verlichting" and blk[0]["values"].get("name") == "feest",
      f"en weer gelezen ({blk})")

# ---------------------------------------------------------------- radar page: Name it / Add to radio
check(gc.post("/api/radar/name", headers=H, json={"hash": "ab", "name": "niets-hier"}).status_code == 400, "naam zonder passende berichten: 400")
r = gc.post("/api/radar/add_to_radio", headers=H, json={"name": "#bemesh"})
check(r.status_code == 200 and r.get_json()["queued"] == "#bemesh", "Add to radio: in de wachtrij")
check(gc.get("/api/radar", headers=H).get_json()["add_to_radio"] == ["#bemesh"], "de pagina ziet het verzoek")
check(gc.post("/api/radar/add_to_radio", headers=H, json={"name": "met spatie"}).status_code == 400, "geen hashtag-naam: 400")
r = gc.post("/api/radar/channel", headers=H, json={"name": "Club Kanaal", "key": "00112233445566778899aabbccddeeff"})
check(r.status_code == 200 and r.get_json()["added"] == "Club Kanaal", "kanaal met sleutel toevoegen via de pagina")
check(gc.post("/api/radar/channel", headers=H, json={"name": "Club", "key": "kort"}).status_code == 400, "foute sleutel: 400")
check("Club Kanaal" in [w["label"] for w in gc.get("/api/radar", headers=H).get_json()["watching"]], "staat bij 'nog niets gehoord'")
check('id="tab-watching"' in gc.get("/radar").get_data(as_text=True), "tabblad 'Not heard yet'")
check(gc.post("/api/radar/name/delete", headers=H, json={"name": "Club Kanaal"}).get_json()["deleted"] is True, "weer weghalen")
check('id="add-channel-form"' in gc.get("/radar").get_data(as_text=True), "formulier bovenaan de radarpagina")

# ---------------------------------------------------------------- Settings -> Problems
pp = gc.get("/problems").get_data(as_text=True)
check('id="pr-problems"' in pp and 'href="/problems"' in pp, "pagina Problems met menu-item")
pj = gc.get("/api/problems?days=7", headers=H).get_json()
check(pj.get("days") == 7 and "problems" in pj and "unanswered" in pj, f"/api/problems antwoordt ({sorted(pj)})")
check(gc.post("/api/problems/dismiss", headers=H, json={"type": "command", "key": "c|1|ping|x"}).get_json()["dismissed"] is True, "afvinken via de API")
check(gc.post("/api/problems/clear", headers=H).get_json()["cleared"] is True, "alles wissen via de API")
gv.app.config["TESTING"] = False
check(gc.post("/api/problems/clear").status_code == 403, "wissen zonder X-Requested-With: geweigerd")
gv.app.config["TESTING"] = True
psrc = open(os.path.join(TREE, "modules", "web_viewer", "templates", "problems.html")).read()
check("innerHTML" not in psrc and "insertAdjacentHTML" not in psrc, "Problems: logteksten alleen als tekst")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
