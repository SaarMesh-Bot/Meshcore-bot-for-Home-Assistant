"""Watchlist page on the real patched v1.1.0 viewer: menu item right after Mailbox, the page, /api/watchlist with
settings, targets, statistics and hits, reset of the cooldown, clearing the hits, saving through the plugin API, the
test note without a Supervisor, and mesh text only as text."""
import configparser
import json
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
from modules.models import MeshMessage  # noqa: E402
from modules import watchlist as wl  # noqa: E402

H = {"X-Requested-With": "XMLHttpRequest"}
KEY = "7cf26cbf9c9743f831dd91d7ea3f017e75ab771d6eebe19fe37bbcd47b7f3fa7"

work = tempfile.mkdtemp()
cfg = configparser.ConfigParser()
cfg["Bot"] = {"db_path": f"{work}/viewer.db", "bot_name": "Saarlodri"}
cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": ""}
cfg["Channels"] = {"monitor_channels": "Public"}
cfg["Watchlist"] = {"enabled": "true", "targets": f"Führerhauptquartier={KEY}, Troll", "dm_cooldown_hours": "24",
                    "corescope_url": "https://live.saarmesh.de/"}
with open(f"{work}/config.ini", "w", encoding="utf-8") as f:
    cfg.write(f)
v = BotDataViewer(config_path=f"{work}/config.ini")
v.app.config["TESTING"] = True
c = v.app.test_client()

# ---- menu and page ----
home = c.get("/mailbox").get_data(as_text=True)
check('href="/watchlist"' in home, "menu item Watchlist")
check(home.index('href="/mailbox"') < home.index('href="/watchlist"'), "menu: Watchlist right after Mailbox")
page = c.get("/watchlist")
html = page.get_data(as_text=True)
check(page.status_code == 200 and "wl-targets" in html and "wl-hits" in html and "wl-settings" in html,
      "page /watchlist with targets, hits and settings")
own = open(os.path.join(TREE, "modules", "web_viewer", "templates", "watchlist.html"), encoding="utf-8").read()
check("textContent" in own and "innerHTML" not in own and "insertAdjacentHTML" not in own, "mesh text only as text")

# ---- api: empty ----
d = c.get("/api/watchlist", headers=H).get_json()
check([t["name"] for t in d["targets"]] == ["Führerhauptquartier", "Troll"] and d["targets"][0]["key"] == KEY
      and d["targets"][1]["key"] == "", "targets with and without key")
check(d["settings"]["enabled"] and d["settings"]["corescope_url"] == "https://live.saarmesh.de"
      and d["settings"]["default_dm"] == wl.DEFAULT_DM, "settings (CoreScope address without trailing slash)")
check(d["hits"] == [] and d["counts"]["targets"] == 2 and d["counts"]["hits_7d"] == 0, "no hits yet")

# ---- hits as the bot records them ----
db = v.db_manager
now = time.time()
m = MeshMessage(content="Gruß aus Saarbrücken", sender_id="Führerhauptquartier", channel="Public")
m.routing_info = {"path_len_byte": 0x03}
wl.record_hit(db, "führerhauptquartier", m, "gesendet", now=now - 60)
db.set_metadata(wl.DM_KEY, json.dumps({"führerhauptquartier": now - 60}))
wl.record_hit(db, "führerhauptquartier", MeshMessage(content="nochmal", sender_id="Führerhauptquartier", channel="Public"),
              "keine (Abstand 24 h)", now=now - 30)
d = c.get("/api/watchlist", headers=H).get_json()
t = d["targets"][0]
check(t["msgs"] == 2 and t["dms"] == 1 and t["last_dm_result"] == "gesendet" and t["next_dm"]
      and abs(t["next_dm"] - (now - 60 + 86400)) < 2, f"statistics per target ({t})")
check([h["text"] for h in d["hits"]] == ["nochmal", "Gruß aus Saarbrücken"] and d["hits"][1]["hops"] == 3,
      "hit log, newest first, with hops")
check(d["counts"]["hits_7d"] == 2 and d["counts"]["dms"] == 1, "tiles: hits and DMs")

# ---- reset the cooldown, clear the hits ----
# (the viewer's X-Requested-With check is off under TESTING; it covers every POST to /api/ in real use)
r = c.post("/api/watchlist/reset", json={"target": "führerhauptquartier"}, headers=H).get_json()
d = c.get("/api/watchlist", headers=H).get_json()
check(r["reset"] and d["targets"][0]["next_dm"] is None and d["targets"][0]["dms"] == 1,
      "reset: next message gets a DM again, statistics stay")
c.post("/api/watchlist/clear-hits", headers=H)
d = c.get("/api/watchlist", headers=H).get_json()
check(d["hits"] == [] and d["targets"][0]["msgs"] == 2, "clear hits: list empty, statistics stay")

# ---- saving through the plugin API (as the page does) ----
r = c.post("/api/plugins/service/watchlist", headers=H, json={"section": "Watchlist", "enabled": True, "values": {
    "targets": f"Führerhauptquartier={KEY}", "channels": "", "message_dm": "Bitte Namen ändern, {sender}.",
    "dm_cooldown_hours": 48, "delay_seconds": 15, "notify": True, "ha_notify_service": "telegram_bot.send_message",
    "corescope_url": "https://live.saarmesh.de"}})
d = c.get("/api/watchlist", headers=H).get_json()
check(r.status_code == 200 and [t["name"] for t in d["targets"]] == ["Führerhauptquartier"]
      and d["settings"]["message_dm"] == "Bitte Namen ändern, {sender}." and d["settings"]["dm_cooldown_hours"] == 48,
      f"saved through the plugin API ({r.status_code})")

# ---- test note: no Supervisor here ----
os.environ.pop("SUPERVISOR_TOKEN", None)
r = c.post("/api/watchlist/test", headers=H)
check(r.status_code == 502 and "SUPERVISOR_TOKEN" in r.get_json()["detail"], "test note without Supervisor: clear error")

# ---- German texts for the page ----
de = json.load(open(os.path.join(TREE, "modules", "local_data", "ui_i18n.json"), encoding="utf-8"))["de"]
check(de.get("Watched senders") == "Beobachtete Absender" and de.get("with the next message"), "German texts for the page")

if fails:
    print(f"{len(fails)} fouten")
    sys.exit(1)
