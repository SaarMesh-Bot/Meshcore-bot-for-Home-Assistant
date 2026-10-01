"""Writes one dashboard page (as a viewer would get it, bot language from argv) plus the three /webui scripts, for webui_test.js."""
import configparser, json, os, sys, tempfile
TREE, OUT, LANG = sys.argv[1], sys.argv[2], sys.argv[3]
os.chdir(TREE); sys.path.insert(0, TREE)
work = tempfile.mkdtemp()
cfg = configparser.ConfigParser()
cfg["Bot"] = {"db_path": f"{work}/v.db", "bot_name": "Own|🤖"}
cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": ""}
cfg["Localization"] = {"language": LANG}
with open(f"{work}/config.ini", "w") as f: cfg.write(f)
from modules.web_viewer.app import BotDataViewer
v = BotDataViewer(config_path=f"{work}/config.ini"); v.app.config["TESTING"] = True
c = v.app.test_client()
json.dump({"html": c.get("/problems").get_data(as_text=True),
           "me": c.get("/webui/me.js").get_data(as_text=True),
           "i18n": c.get("/webui/i18n.js").get_data(as_text=True),
           "webui": c.get("/webui/webui.js").get_data(as_text=True)}, open(OUT, "w", encoding="utf-8"))
