"""Bot network page on the real patched v1.1.0 viewer: menu item only while the card is on, page, /api/botnet and
/api/botnet/history, and the Bots page only links to it."""
import configparser
import os
import sys
import tempfile
import time

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

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
