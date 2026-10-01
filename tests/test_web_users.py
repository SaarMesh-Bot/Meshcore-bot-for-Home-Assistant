"""Dashboard users on the real patched v1.1.0 viewer: admin/viewer accounts, server-side limits, repeaters per viewer,
login rate limit, the Users page, and the scripts that put the dashboard in the bot's language."""
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


def make(password="", lang="nl"):
    work = tempfile.mkdtemp()
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"db_path": f"{work}/viewer.db", "bot_name": "Test|🤖"}
    cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": password}
    cfg["Channels"] = {"monitor_channels": "#test"}
    cfg["Localization"] = {"language": lang}
    with open(f"{work}/config.ini", "w") as f:
        cfg.write(f)
    from modules.web_viewer.app import BotDataViewer
    v = BotDataViewer(config_path=f"{work}/config.ini")
    v.app.config["TESTING"] = False      # keep the X-Requested-With check on
    return v


from modules import web_users as WU  # noqa: E402

H = {"X-Requested-With": "XMLHttpRequest"}
A, B = "a1" * 32, "b2" * 32

# ---------------------------------------------------------------- module
h = WU.hash_password("geheim123")
check(h.startswith("pbkdf2_sha256$") and "geheim123" not in h, "wachtwoord als PBKDF2-hash, nooit leesbaar")
check(WU.check_password("geheim123", h) and not WU.check_password("geheim124", h), "hash controleert goed en fout")
check(WU.hash_password("x") != WU.hash_password("x"), "elke hash met eigen zout")
viewer_u = {"name": "v", "role": "viewer", "pages": ["repeater"], "repeaters": [], "groups": []}
check(WU.may_request(viewer_u, "GET", "/repeater") and WU.may_request(viewer_u, "GET", "/api/repeater"), "kijker: eigen pagina en API")
check(not WU.may_request(viewer_u, "POST", "/api/repeater"), "kijker: geen POST")
check(not WU.may_request(viewer_u, "GET", "/api/channels") and not WU.may_request(viewer_u, "GET", "/config"), "kijker: geen kanalen (sleutels) of config")
check(not WU.may_request(viewer_u, "GET", "/radar"), "kijker: geen pagina die niet is aangevinkt")
check(WU.may_request({"role": "admin"}, "POST", "/api/anything"), "admin mag alles")

# ---------------------------------------------------------------- open dashboard (no password, no accounts)
v = make("")
app = v.app
c = app.test_client()
r = c.get("/repeater")
html = r.get_data(as_text=True)
check(r.status_code == 200, "zonder wachtwoord en accounts: dashboard open zoals eerst")
check('/webui/me.js' in html and '/webui/i18n.js' in html and '/webui/webui.js' in html and
      html.index('/webui/webui.js') < html.index('</head>'), "elke pagina krijgt de drie scripts in <head>")
me = c.get("/webui/me.js").get_data(as_text=True)
check('"auth": false' in me and '"lang": "nl"' in me and '"role": "admin"' in me, f"me.js zonder login: {me}")
check('href="/users"' in html, "menu: Settings -> Users")
i18n = c.get("/webui/i18n.js")
check(i18n.status_code == 200 and i18n.get_data(as_text=True).startswith("window.WEBUI_I18N = {"), "i18n.js met de woordenlijst van de bottaal")
check(c.get("/webui/webui.js").status_code == 200 and "MutationObserver" in c.get("/webui/webui.js").get_data(as_text=True), "webui.js bestaat")
check(c.get("/users").status_code == 200, "Users-pagina bereikbaar (open dashboard)")

# repeater data
now = int(time.time())
with v.db_manager.connection() as conn:
    conn.execute("""CREATE TABLE repeater_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL, repeater_key TEXT NOT NULL,
        repeater_name TEXT, battery_mv INTEGER, battery_pct REAL, temperature REAL, ch1_voltage REAL,
        uptime_s INTEGER, airtime_s INTEGER, airtime_util REAL, nb_recv INTEGER, nb_sent INTEGER,
        noise_floor REAL, last_rssi REAL, last_snr REAL, neighbor_count INTEGER,
        stats_key TEXT, source TEXT NOT NULL DEFAULT 'ha')""")
    for key, name in ((A, "Rep A"), (B, "Rep B")):
        conn.execute("INSERT INTO repeater_telemetry (recorded_at, repeater_key, repeater_name, battery_mv) VALUES (?,?,?,?)",
                     (now - 60, key, name, 4000))
    conn.commit()

# first account must be an admin (no add-on password)
r = c.post("/api/users/save", json={"name": "Kijker", "password": "kijken123", "role": "viewer", "pages": ["repeater"]}, headers=H)
check(r.status_code == 400 and "admin" in r.get_json()["error"], "zonder add-on-wachtwoord eerst een admin-account")
r = c.post("/api/users/save", json={"name": "Baas", "password": "kort", "role": "admin"}, headers=H)
check(r.status_code == 400, "te kort wachtwoord geweigerd")
r = c.post("/api/users/save", json={"name": "admin", "password": "lang genoeg", "role": "admin"}, headers=H)
check(r.status_code == 400, "de naam 'admin' is voor het add-on-wachtwoord")
r = c.post("/api/users/save", json={"name": "Baas", "password": "baas12345", "role": "admin"})
check(r.status_code == 403, "POST zonder X-Requested-With geweigerd (CSRF)")
r = c.post("/api/users/save", json={"name": "Baas", "password": "baas12345", "role": "admin"}, headers=H)
check(r.status_code == 200 and r.get_json()["user"]["role"] == "admin", "admin-account aangemaakt")

# from now on a login is needed
c2 = app.test_client()
r = c2.get("/repeater")
check(r.status_code in (302, 303) and "/login" in r.headers["Location"], "met een account: inloggen nodig")
check(c2.get("/api/repeater", headers=H).status_code == 401, "API zonder login: 401")
check(c2.get("/webui/me.js").status_code == 200 and c2.get("/webui/i18n.js").status_code == 200, "scripts ook op de loginpagina")
login_html = c2.get("/login").get_data(as_text=True)
check('name="username"' in login_html and 'name="password"' in login_html, "loginformulier met naam en wachtwoord")

# admin logs in, makes a viewer and a group
r = c2.post("/login", data={"username": "baas", "password": "baas12345"})
check(r.status_code in (302, 303), "admin logt in (naam hoofdletterongevoelig)")
r = c2.post("/api/users/group", json={"name": "Club", "repeaters": [B]}, headers=H)
check(r.status_code == 200 and r.get_json()["group"]["repeaters"] == [B], "repeatergroep opgeslagen")
r = c2.post("/api/users/save", json={"name": "Kijker", "password": "kijken123", "role": "viewer",
                                     "pages": ["repeater", "games", "bogus"], "repeaters": [A]}, headers=H)
u = r.get_json().get("user") or {}
check(r.status_code == 200 and u.get("pages") == ["repeater", "games"], f"kijker opgeslagen, onbekende pagina weg: {u}")
lst = c2.get("/api/users", headers=H).get_json()
check([x["name"] for x in lst["users"]] == ["Baas", "Kijker"] and "pw_hash" not in json.dumps(lst), "lijst zonder wachtwoord-hashes")
check({r["key"] for r in lst["repeaters"]} == {A, B}, "repeaters om uit te kiezen")

# viewer
cv = app.test_client()
r = cv.post("/login", data={"username": "Kijker", "password": "kijken123"})
check(r.status_code in (302, 303) and r.headers["Location"].endswith("/repeater"), f"kijker landt op de eerste toegestane pagina: {r.headers.get('Location')}")
check(cv.get("/repeater").status_code == 200, "kijker: Repeater-pagina")
r = cv.get("/")
check(r.status_code in (302, 303) and r.headers["Location"].endswith("/repeater"), "kijker: dashboard niet aangevinkt -> naar Repeater")
d = cv.get("/api/repeater", headers=H).get_json()
check([x["key"] for x in d["repeaters"]] == [A] and d["selected"] == A, "kijker ziet alleen zijn repeater")
d = cv.get("/api/repeater?key=" + B, headers=H).get_json()
check(d["selected"] == A, "een andere repeater opvragen geeft hem niet")
check(cv.get("/api/channels", headers=H).status_code == 403, "kijker: /api/channels (sleutels) 403")
check(cv.get("/api/users", headers=H).status_code == 403, "kijker: accountlijst 403")
check(cv.post("/api/bots/set", json={}, headers=H).status_code == 403, "kijker: niets wijzigen (403)")
check(cv.post("/api/games/farm/season", json={}, headers=H).status_code == 403, "kijker: ook niet op een toegestane pagina")
r = cv.get("/config")
check(r.status_code in (302, 303) and r.headers["Location"].endswith("/repeater"), "kijker: config-pagina -> terug naar Repeater")
check(cv.get("/games").status_code == 200 and cv.get("/api/games", headers=H).status_code == 200, "kijker: tweede pagina (Games) mag")
me = cv.get("/webui/me.js").get_data(as_text=True)
check('"role": "viewer"' in me and '"/repeater"' in me and '"/games"' in me and '"user": "Kijker"' in me, f"me.js voor de kijker: {me}")

# group instead of single repeater: works at once for the logged-in viewer
c2.post("/api/users/save", json={"name": "Kijker", "role": "viewer", "pages": ["repeater"], "repeaters": [], "groups": ["Club"]}, headers=H)
d = cv.get("/api/repeater", headers=H).get_json()
check([x["key"] for x in d["repeaters"]] == [B], "groep: kijker ziet de repeaters van de groep (meteen)")
check(cv.get("/games").status_code in (302, 303), "pagina uitgevinkt: meteen dicht")

# deleted while logged in
r = c2.post("/api/users/delete", json={"name": "Kijker"}, headers=H)
check(r.status_code == 200, "kijker verwijderd")
check(cv.get("/api/repeater", headers=H).status_code == 401, "verwijderd account: volgende verzoek 401")

# last admin cannot go while other accounts remain and there is no add-on password
c2.post("/api/users/save", json={"name": "Lezer", "password": "lezen1234", "role": "viewer", "pages": ["repeater"]}, headers=H)
r = c2.post("/api/users/delete", json={"name": "Baas"}, headers=H)
check(r.status_code == 400, "laatste admin niet weg zolang er accounts zijn (geen add-on-wachtwoord)")
r = c2.post("/api/users/save", json={"name": "Baas", "role": "viewer", "pages": ["repeater"]}, headers=H)
check(r.status_code == 400, "laatste admin niet degraderen")

# Home Assistant sidebar: only from the Supervisor's address, never on the header alone
ING = {"X-Ingress-Path": "/api/hassio_ingress/TOKEN"}
ch = app.test_client()
r = ch.get("/repeater", headers=ING, environ_base={"REMOTE_ADDR": "172.30.32.2"})
check(r.status_code == 200, "zijbalk (Supervisor 172.30.32.2): geen tweede login")
check(ch.get("/api/users", headers={**H, **ING}, environ_base={"REMOTE_ADDR": "172.30.32.2"}).status_code == 200, "zijbalk = admin")
r = app.test_client().get("/repeater", headers=ING, environ_base={"REMOTE_ADDR": "203.0.113.5"})
check(r.status_code in (302, 303), "ingress-header van een ander adres: gewoon inloggen")
me = ch.get("/webui/me.js", headers=ING, environ_base={"REMOTE_ADDR": "172.30.32.2"}).get_data(as_text=True)
check('"ha": true' in me and '"role": "admin"' in me, "me.js in de zijbalk")

# rate limit
cb = app.test_client()
codes = [cb.post("/login", data={"username": "Baas", "password": f"fout{i}"}, environ_base={"REMOTE_ADDR": "203.0.113.9"}).status_code
         for i in range(WU.LOGIN_MAX_FAILS + 1)]
check(codes[-1] == 429, f"na {WU.LOGIN_MAX_FAILS} foute pogingen: 429 ({codes})")
r = cb.post("/login", data={"username": "Baas", "password": "baas12345"}, environ_base={"REMOTE_ADDR": "203.0.113.9"})
check(r.status_code == 429, "ook het goede wachtwoord even geblokkeerd voor dat adres")
r = cb.post("/login", data={"username": "Baas", "password": "baas12345"}, environ_base={"REMOTE_ADDR": "203.0.113.10"})
check(r.status_code in (302, 303), "een ander adres kan gewoon inloggen")

# logout
r = c2.get("/logout")
check(r.status_code in (302, 303) and c2.get("/api/repeater", headers=H).status_code == 401, "uitloggen wist de sessie")

# ---------------------------------------------------------------- with the add-on password
v2 = make("supergeheim", lang="en")
c3 = v2.app.test_client()
check(c3.post("/login", data={"password": "fout"}).status_code == 200, "fout add-on-wachtwoord: formulier met fout")
r = c3.post("/login", data={"password": "supergeheim"})
check(r.status_code in (302, 303) and c3.get("/users").status_code == 200, "add-on-wachtwoord zonder naam = admin (zoals eerst)")
r = c3.post("/login", data={"username": "admin", "password": "supergeheim"})
check(r.status_code in (302, 303), "of met de naam admin")
check('"lang": "en"' in c3.get("/webui/me.js").get_data(as_text=True), "taal volgt [Localization] language")
r = c3.post("/api/users/save", json={"name": "Lezer", "password": "lezen1234", "role": "viewer", "pages": ["radar"]}, headers=H)
check(r.status_code == 200, "met add-on-wachtwoord mag het eerste account een kijker zijn")

# the translation table itself
table = json.load(open(os.path.join(TREE, "modules/local_data/ui_i18n.json"), encoding="utf-8"))
check(set(table) >= {"nl", "de", "fr", "da"}, "woordenlijst voor nl, de, fr, da")
for lang, t in table.items():
    bad = [k for k, val in t.items() if k != "__patterns" and (not isinstance(val, str) or not val.strip())]
    check(not bad, f"{lang}: geen lege vertalingen ({bad[:5]})")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
