"""DE pack, part 3 (parity with the old SaarMesh bot): vorhersage (arguments, Open-Meteo rows, one line per step),
pegel trend / alarm helpers, the commands' keyword parsing, and generate_config (prefix "/" by default, the SaarMesh
keywords and how the option overrides them)."""
import asyncio
import configparser
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TREE = sys.argv[1]
os.chdir(TREE)
sys.path.insert(0, TREE)
TESTS = pathlib.Path(__file__).resolve().parent
GEN = str(TESTS.parent / "meshcore-bot" / "generate_config.py")
OPTS = json.load(open(TESTS / "fixtures" / "options_sample.json"))

from modules import de_forecast as F  # noqa: E402
from modules import de_pegel as P  # noqa: E402

fails = []


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        fails.append(m)


BER = ZoneInfo("Europe/Berlin")

# ---------------------------------------------------------------- vorhersage
check(F.parse_args("") == (6, None), "ohne Argumente: 6 h, eigener Standort")
check(F.parse_args("12") == (12, None), "nur Stunden")
check(F.parse_args("66117") == (6, "66117"), "PLZ ist ein Ort, keine Stunden")
check(F.parse_args("66117 12") == (12, "66117") and F.parse_args("12 Trier") == (12, "Trier"), "Ort und Stunden in beliebiger Reihenfolge")
check(F.parse_args("Sankt Ingbert 24h") == (24, "Sankt Ingbert"), "Ort mit Leerzeichen, '24h'")
check(F.parse_args("99") == (48, None) and F.parse_args("0")[0] == 1, "Stunden begrenzt auf 1..48")
check(F.is_plz("66117") and not F.is_plz("6611") and not F.is_plz("Trier"), "PLZ erkannt")
check(F.plz_name("66333") == "Völklingen" and F.plz_name("10115") is None, "Saarland-PLZ benannt, andere nicht")
check(F.step_for(6) == 1 and F.step_for(12) == 2 and F.step_for(24) == 3 and F.step_for(48) == 6, "Schrittweite")
u = F.url(49.2401, 6.9969, 12, "Europe/Berlin")
check("latitude=49.2401" in u and "forecast_hours=13" in u and "weather_code" in u and "timezone=Europe/Berlin" in u, "Open-Meteo-Adresse")

NOW = datetime(2026, 10, 21, 14, 37, tzinfo=BER)
start = datetime(2026, 10, 21, 13, 0)
times = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(30)]
DATA = {"hourly": {"time": times, "temperature_2m": [10 + i * 0.5 for i in range(30)],
                   "weather_code": [61 if i == 3 else 3 for i in range(30)],
                   "precipitation": [0.4 if i in (3, 4) else 0.0 for i in range(30)]}}
r = F.rows(DATA, 6, NOW)
check(len(r) == 7 and r[0][0].hour == 14 and r[-1][0].hour == 20, f"6 h: ab der laufenden Stunde stündlich ({[x[0].hour for x in r]})")
r12 = F.rows(DATA, 12, NOW)
check([x[0].hour for x in r12] == [14, 16, 18, 20, 22, 0, 2], f"12 h: alle 2 h ({[x[0].hour for x in r12]})")
check(r12[0][3] == 0 and abs(r12[1][3] - 0.8) < 1e-9, f"Niederschlag der ausgelassenen Stunde wird mitgezählt ({[x[3] for x in r12[:2]]})")
check(len(F.rows(DATA, 48, NOW)) <= F.MAX_LINES, "höchstens 8 Zeilen")
check(F.rows({"error": True}, 6, NOW) == [] and F.rows(None, 6, NOW) == [], "kaputte Antwort: leer")
check(F.line(datetime(2026, 10, 21, 16, 0), 61, 11.6, 0.4) == "16:00 🌧️ 12° 0,4mm", f"Zeile mit Regen: {F.line(datetime(2026, 10, 21, 16, 0), 61, 11.6, 0.4)}")
check(F.line(datetime(2026, 10, 21, 3, 0), 0, -0.4, 0.0) == "03:00 ☀️ 0°", "keine -0°, kein Niederschlag")
check(F.line(datetime(2026, 10, 21, 3, 0), 73, -2, 1.2).endswith("❄1,2mm"), "Schnee markiert")

# ---------------------------------------------------------------- pegel trend / alarm
hist = [{"timestamp": (datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc) + timedelta(hours=i)).isoformat(),
         "value": 200 + (i % 24) - i * 0.2} for i in range(169)]
series = P.po_series(hist, BER)
check(len(series) == 169 and series[0][0] < series[-1][0] and series[0][0].tzinfo is not None, "PEGELONLINE-Reihe gelesen")
sp = P.span(series, 7)
check(sp and abs(sp["then"] - 200) < 1e-9 and sp["min"] <= sp["now"] <= sp["max"] and sp["diff"] < 0, f"7-Tage-Spanne: {sp and {k: round(v, 1) for k, v in sp.items() if isinstance(v, float)}}")
sp3 = P.span(series, 3)
check(sp3["then_time"] >= series[-1][0] - timedelta(days=3), "3-Tage-Fenster")
check(P.span(series[:1], 7) is None and P.span([], 7) is None, "zu wenig Werte: nichts")
check(P.span_arrow(12) == "↗️" and P.span_arrow(-12) == "↘️" and P.span_arrow(3) == "→", "Pfeile")
check(P.parse_days("7d") == 7 and P.parse_days("10t") == 10 and P.parse_days("3") == 3 and P.parse_days("saar") is None, "Tage lesen")
th = P.parse_thresholds(P.DEFAULT_THRESHOLDS)
check(P.next_threshold(250, th) == (280, "Meldehöhe 1") and P.next_threshold(330, th)[0] == 350 and P.next_threshold(800, th) is None, "nächste Schwelle")


# ---------------------------------------------------------------- commands (keyword parsing, no network)
try:
    from modules.commands import pegel_command, vorhersage_command, zeit_command, echo_command  # noqa: F401
    check(True, "neue Befehle importierbar")
except Exception as e:  # noqa: BLE001
    check(False, f"neue Befehle importierbar: {e}")

from modules.commands.pegel_command import PegelCommand  # noqa: E402
from modules.commands.vorhersage_command import VorhersageCommand  # noqa: E402
check({"pegeltrend", "pegel3d", "pegel7d", "pegel10d", "pegelalarm"} <= set(PegelCommand.keywords), "alte Pegel-Befehle als Schlüsselwörter")
check({"vorhersage", "forecast"} <= set(VorhersageCommand.keywords), "vorhersage/forecast")


async def run_pegel(text):
    """PegelCommand.execute with the network parts replaced, to see which mode a text picks."""
    cmd = PegelCommand.__new__(PegelCommand)
    from modules import de_pegel
    cmd.keywords = PegelCommand.keywords
    cmd.stations = de_pegel.parse_stations(de_pegel.DEFAULT_STATIONS)
    cmd.default = "saar"
    seen = {}

    async def trend(st, days, now):
        seen.update(mode="trend", station=st["label"], days=days)
        return "t"

    async def alarm():
        seen.update(mode="alarm")
        return "a"

    async def send(message, text):
        seen.setdefault("mode", "now")
        seen["text"] = text
        return True
    cmd._trend_text, cmd._alarm_text, cmd.send_response = trend, alarm, send
    cmd.translate = lambda key, **kw: key
    cmd.logger = type("L", (), {"error": staticmethod(print)})()
    cmd.bot = None

    class M:
        content = text
    import modules.mesh_community as mc
    mc_local = mc.local_now
    mc.local_now = lambda bot, ts=None: datetime(2026, 10, 21, 12, 0, tzinfo=BER)
    try:
        await cmd.execute(M())
    finally:
        mc.local_now = mc_local
    seen.pop("text", None) if seen.get("mode") != "now" else None
    return seen


def pg(text):
    return asyncio.run(run_pegel(text))


check(pg("pegeltrend") == {"mode": "trend", "station": "Saar (Sankt Arnual)", "days": 7}, f"pegeltrend: {pg('pegeltrend')}")
check(pg("pegel10d")["days"] == 10 and pg("pegel3d")["days"] == 3, "pegel3d / pegel10d")
check(pg("pegel trend nied 5d") == {"mode": "trend", "station": "Nied (Niedaltdorf)", "days": 5}, "pegel trend nied 5d")
check(pg("pegel nied 3d")["mode"] == "trend" and pg("pegel nied 3d")["days"] == 3, "pegel nied 3d")
check(pg("pegelalarm") == {"mode": "alarm"} and pg("pegel alarm") == {"mode": "alarm"}, "pegelalarm / pegel alarm")
check(pg("pegel ?").get("text") == "commands.pegel.list", "pegel ? bleibt die Liste")

# ---------------------------------------------------------------- generate_config
def gen(opts):
    with tempfile.TemporaryDirectory() as d:
        with open(f"{d}/options.json", "w") as f:
            json.dump(opts, f)
        r = subprocess.run([sys.executable, GEN, f"{d}/options.json", f"{d}/config.ini", d], capture_output=True, text=True)
        if r.returncode != 0:
            raise subprocess.CalledProcessError(r.returncode, "gen", stderr=r.stderr)
        c = configparser.ConfigParser(interpolation=None, strict=False)
        c.optionxform = str
        c.read(f"{d}/config.ini", encoding="utf-8")
        return c


import copy  # noqa: E402

try:
    o = copy.deepcopy(OPTS)
    o.setdefault("bot", {}).pop("command_prefix", None)
    o.setdefault("weather", {})["default_country"] = "DE"
    o.setdefault("advanced", {})["keywords"] = ["bier=Prost!", "1-byte="]
    c = gen(o)
    check(c.get("Bot", "command_prefix", fallback="") == "/" and c.get("Bot", "require_command_prefix") == "false",
          "Präfix / ohne Option, nicht Pflicht")
    kw = dict(c.items("Keywords"))
    check("regions" in kw and "info" in kw and "💙🖤" in kw, f"SaarMesh-Keywords da: {sorted(kw)}")
    check(kw.get("bier") == "Prost!" and "1-byte" not in kw, "Option ersetzt bzw. entfernt ein Keyword")
    o["bot"]["command_prefix"] = "-"
    check(not gen(o).has_option("Bot", "command_prefix"), "Präfix '-' = aus")
    o["bot"]["command_prefix"] = "!"
    check(gen(o).get("Bot", "command_prefix") == "!", "eigener Präfix bleibt")
    o["weather"]["default_country"] = "NL"
    o["advanced"]["keywords"] = []
    check(dict(gen(o).items("Keywords")) == {}, "keine SaarMesh-Keywords außerhalb DE")
except subprocess.CalledProcessError as e:
    check(False, f"generate_config: {e.stderr[-500:]}")

print(f"\n{len(fails)} fouten" if fails else "\nalles OK")
sys.exit(1 if fails else 0)
