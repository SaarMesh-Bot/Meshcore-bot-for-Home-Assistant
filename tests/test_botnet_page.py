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
radar_src = open(os.path.join(TREE, "modules", "web_viewer", "templates", "radar.html")).read()
check("innerHTML" not in radar_src and "insertAdjacentHTML" not in radar_src, "radar: namen alleen als tekst")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
