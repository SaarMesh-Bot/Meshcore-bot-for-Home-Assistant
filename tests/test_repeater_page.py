"""Repeater page on the real patched v1.1.0 viewer: menu item, page, /api/repeater (periods, choice, thinning, empty state)."""
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


work = tempfile.mkdtemp()
cfg = configparser.ConfigParser()
cfg["Bot"] = {"db_path": f"{work}/viewer.db", "bot_name": "Mesh|HA|🤖"}
cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": ""}
cfg["Channels"] = {"monitor_channels": "#test"}
with open(f"{work}/config.ini", "w") as f:
    cfg.write(f)

from modules.web_viewer.app import BotDataViewer  # noqa: E402
from modules import repeater_page as RP  # noqa: E402

viewer = BotDataViewer(config_path=f"{work}/config.ini")
app = viewer.app
app.config["TESTING"] = True
client = app.test_client()
H = {"X-Requested-With": "XMLHttpRequest"}

# ---------------------------------------------------------------- empty: no HARepeater data
r = client.get("/api/repeater", headers=H)
check(r.status_code == 200 and r.get_json()["repeaters"] == [] and r.get_json()["selected"] is None, "zonder gegevens: lege lijst, geen fout")
page = client.get("/repeater")
html = page.get_data(as_text=True)
check(page.status_code == 200 and 'href="/repeater"' in html and "Repeater" in html and "c-battery" in html, "pagina /repeater met menu-item en grafieken")
games = client.get("/games").get_data(as_text=True)
check(games.index('href="/radar"') < games.index('href="/repeater"'), "menu: Repeater staat na Channel radar")

# ---------------------------------------------------------------- data as the HARepeater service stores it
now = int(time.time())
with viewer.db_manager.connection() as conn:
    conn.execute("""CREATE TABLE repeater_telemetry (
        id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL, repeater_key TEXT NOT NULL,
        repeater_name TEXT, battery_mv INTEGER, battery_pct REAL, temperature REAL, ch1_voltage REAL,
        uptime_s INTEGER, airtime_s INTEGER, airtime_util REAL, nb_recv INTEGER, nb_sent INTEGER,
        noise_floor REAL, last_rssi REAL, last_snr REAL, neighbor_count INTEGER,
        stats_key TEXT, source TEXT NOT NULL DEFAULT 'ha')""")
    conn.execute("""CREATE TABLE ha_repeater_neighbors (
        id INTEGER PRIMARY KEY AUTOINCREMENT, recorded_at INTEGER NOT NULL, repeater_key TEXT NOT NULL,
        neighbor_prefix TEXT NOT NULL, neighbor_name TEXT, snr REAL, secs_ago INTEGER, stats_key TEXT)""")
    A, B = "a1" * 32, "b2" * 32
    # A: every 15 minutes for 40 days (3840 readings), temperature missing now and then
    for i in range(40 * 96):
        ts = now - (40 * 96 - i) * 900
        conn.execute("""INSERT INTO repeater_telemetry (recorded_at, repeater_key, repeater_name, battery_mv, battery_pct, temperature,
                        uptime_s, airtime_util, noise_floor, last_rssi, last_snr, neighbor_count, stats_key)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (ts, A, "Heuvel <b>RPTR</b>", 4000 + i % 100, 80.0, None if i % 10 == 0 else 21.5, i * 900, 2.5, -110, -90, 7.5, 3, f"s{i}"))
    # B: older, two readings
    for i, ts in enumerate((now - 3 * 86400, now - 2 * 86400)):
        conn.execute("INSERT INTO repeater_telemetry (recorded_at, repeater_key, repeater_name, battery_mv, stats_key) VALUES (?,?,?,?,?)",
                     (ts, B, "Dal", 3900, f"b{i}"))
    conn.executemany("INSERT INTO ha_repeater_neighbors (recorded_at, repeater_key, neighbor_prefix, neighbor_name, snr, secs_ago) VALUES (?,?,?,?,?,?)",
                     [(now - 3600, A, "ab", "Oud", 1.0, 60), (now - 900, A, "cd", "Buur 1", 9.5, 30), (now - 900, A, "ef", "Buur 2", 3.0, 300),
                      (now - 900, A, "8e7c70", "", None, None), (now - 900, A, "73c82e", "", None, None)])
    # the bot's own contact list knows 8e7c70... (twice: the most recently heard name wins); 73c82e is unknown
    cols = {r[1]: r for r in conn.execute("PRAGMA table_info(complete_contact_tracking)").fetchall()}
    def contact(key, name, heard, **extra):
        vals = {"public_key": key, "name": name, "role": "repeater", "last_heard": heard, **extra}
        for cname, (_, _, ctype, notnull, default, _) in cols.items():
            if cname in vals or cname == "id" or not notnull or default is not None:
                continue
            vals[cname] = 0 if "INT" in (ctype or "").upper() or "REAL" in (ctype or "").upper() else ""
        conn.execute(f"INSERT INTO complete_contact_tracking ({','.join(vals)}) VALUES ({','.join('?' * len(vals))})", list(vals.values()))
    contact("8E7C70" + "11" * 29, "Oude Naam", "2026-09-01 10:00:00")
    contact("8e7c70" + "22" * 29, "Heuvel-Noord RPTR", "2026-09-24 10:00:00", city="Heerlen", latitude=50.89, longitude=5.98)
    contact("cd" + "33" * 31, "Buur Eén", "2026-09-24 09:00:00", country="Belgium")
    contact(A, "Heuvel <b>RPTR</b>", "2026-09-24 11:00:00", latitude=50.85, longitude=5.69)
    conn.commit()

d = client.get("/api/repeater", headers=H).get_json()
check([r["name"] for r in d["repeaters"]] == ["Heuvel <b>RPTR</b>", "Dal"] and d["selected"] == A, "standaard de repeater die het laatst antwoordde")
check(d["days"] == 7 and 670 <= len(d["series"]["t"]) <= 673 or len(d["series"]["t"]) == RP.MAX_POINTS,
      f"7 dagen, zo nodig uitgedund ({len(d['series']['t'])} punten)")
check(len(d["series"]["t"]) <= RP.MAX_POINTS and d["series"]["t"][-1] == d["latest"]["ts"], "nooit meer dan MAX_POINTS, het nieuwste punt zit er altijd in")
check(all(len(v) == len(d["series"]["t"]) for v in d["series"].values()), "alle reeksen even lang als de tijdas")
check(None in d["series"]["temperature"], "ontbrekende waarden blijven leeg (geen verzonnen punten)")
check([n["name"] for n in d["neighbors"]][:2] == ["Buur 1", "Buur 2"] and len(d["neighbors"]) == 4, "buren: alleen de laatste lijst, beste SNR eerst")
nb = {n["prefix"]: n for n in d["neighbors"]}
check(nb["8e7c70"]["name"] == "Heuvel-Noord RPTR" and nb["8e7c70"]["from_contacts"] is True, f"buur zonder naam: naam uit Contacts, de laatst gehoorde ({nb['8e7c70']})")
check(nb["8e7c70"]["place"] == "Heerlen" and 20 <= nb["8e7c70"]["km"] <= 22, f"plaats en afstand tot de repeater ({nb['8e7c70']})")
check(nb["cd"]["place"] == "" and nb["cd"]["name"] == "Buur 1", "te kort sleutelbegin (2 tekens) wordt niet opgezocht: te onzeker; naam van meshcore-ha blijft")
with viewer.db_manager.connection() as conn:
    conn.execute("INSERT INTO ha_repeater_neighbors (recorded_at, repeater_key, neighbor_prefix, neighbor_name, snr, secs_ago) VALUES (?,?,?,?,?,?)",
                 (now - 900, A, "cd3333", "Grensbuur", 2.0, 60))
    conn.commit()
gb = {n["prefix"]: n for n in client.get("/api/repeater", headers=H).get_json()["neighbors"]}["cd3333"]
check(gb["place"] == "Belgium" and gb["km"] is None and gb["name"] == "Grensbuur" and gb["from_contacts"] is False,
      f"zonder coördinaten: alleen de plaats, geen afstand; naam van meshcore-ha blijft ({gb})")
check(nb["73c82e"]["place"] == "" and nb["73c82e"]["km"] is None, "onbekende buur: geen plaats, geen afstand")
check(nb["73c82e"]["name"] == "" and nb["73c82e"]["from_contacts"] is False and nb["cd"]["from_contacts"] is False, "onbekend blijft leeg; namen van meshcore-ha blijven zoals ze zijn")
d1 = client.get("/api/repeater?days=1", headers=H).get_json()
check(d1["days"] == 1 and 95 <= len(d1["series"]["t"]) <= 97, f"24 uur ({len(d1['series']['t'])} punten)")
d30 = client.get("/api/repeater?days=30", headers=H).get_json()
check(d30["days"] == 30 and len(d30["series"]["t"]) == RP.MAX_POINTS and min(d30["series"]["t"]) >= now - 30 * 86400 - 1, "30 dagen, uitgedund, niets ouder")
db_ = client.get(f"/api/repeater?key={B}&days=7", headers=H).get_json()
check(db_["selected"] == B and len(db_["series"]["t"]) == 2 and db_["neighbors"] == [], "andere repeater kiezen")
check(client.get("/api/repeater?key=onzin&days=99", headers=H).get_json()["selected"] == A, "onbekende sleutel of periode: terug naar de standaard")
own = open(os.path.join(TREE, "modules", "web_viewer", "templates", "repeater.html")).read()
check("textContent" in own and "innerHTML" not in own and "insertAdjacentHTML" not in own, "namen van de mesh alleen als tekst op de pagina")

# other telemetry channels (ch2 current/voltage for charging): stored as JSON by HARepeater, shown when present
import json as _json
with viewer.db_manager.connection() as conn:
    conn.execute("ALTER TABLE repeater_telemetry ADD COLUMN telemetry TEXT")
    for i, (cur, volt) in enumerate(((0.10, 12.9), (0.42, 13.2))):
        conn.execute("INSERT INTO repeater_telemetry (recorded_at, repeater_key, repeater_name, battery_mv, stats_key, telemetry) VALUES (?,?,?,?,?,?)",
                     (now - 600 + i * 300, A, "Heuvel", 4100, f"t{i}",
                      _json.dumps({"values": {"ch2_current": cur, "ch2_voltage": volt}, "units": {"ch2_current": "A", "ch2_voltage": "V"}})))
    conn.commit()
dt = client.get(f"/api/repeater?key={A}&days=1", headers=H).get_json()
check(dt["telemetry"] == {"ch2_current": 0.42, "ch2_voltage": 13.2} and dt["telemetry_units"]["ch2_current"] == "A",
      f"laatste ch2-stroom en -spanning met eenheid ({dt['telemetry']})")
check(dt["telemetry_series"]["ch2_current"]["v"] == [0.10, 0.42], "reeks per telemetriekanaal voor de grafiek")
check(client.get(f"/api/repeater?key={B}&days=7", headers=H).get_json()["telemetry"] == {}, "repeater zonder ch2: niets")
page = client.get("/repeater").get_data(as_text=True)
check('id="rp-tel-charts"' in page, "plek voor de telemetriegrafieken op de pagina")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
