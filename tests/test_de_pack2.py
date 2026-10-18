"""DE pack, part 2: the odl command's data (BfS ODL network: fresh stations only, highest first, search by name or
postcode), feestdag with countries and regions from the card (regional holidays only for the regions on the card,
NL/BE behaviour unchanged without regions), and the per-country commands in generate_config (NL-only commands off
on a German installation and the other way round, a card that switched one on is kept)."""
import configparser
import copy
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TREE = sys.argv[1]
os.chdir(TREE)
sys.path.insert(0, TREE)
TESTS = pathlib.Path(__file__).resolve().parent
GEN = str(TESTS.parent / "meshcore-bot" / "generate_config.py")
OPTS = json.load(open(TESTS / "fixtures" / "options_sample.json"))

from modules import de_odl as O  # noqa: E402

fails = []


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        fails.append(m)


# ---------------------------------------------------------------- odl
NOW = datetime(2026, 10, 18, 2, 0, tzinfo=timezone.utc)


def feat(name, plz, value, end, status=1):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [6.56, 49.6]},
            "properties": {"id": "DEZ1", "kenn": "0723", "plz": plz, "name": name, "site_status": status,
                           "end_measure": end, "value": value, "unit": "µSv/h", "duration": "1h"}}


DATA = {"type": "FeatureCollection", "features": [
    feat("Saarburg", "54439", 0.113, "2026-10-18T01:00:00Z"),
    feat("Saarbrücken-Burbach", "66115", 0.091, "2026-10-18T01:00:00Z"),
    feat("Homburg", "66424", 0.142, "2026-10-18T01:00:00Z"),
    feat("Merzig", "66663", 0.088, "2026-10-17T18:00:00Z"),          # stale
    feat("Wadern", "66687", None, "2026-10-18T01:00:00Z"),           # no value
    feat("Losheim", "66679", 0.5, "2026-10-18T01:00:00Z", status=2),  # not in operation
]}
sts = O.stations(DATA, NOW, ZoneInfo("Europe/Berlin"))
check([s["name"] for s in sts] == ["Homburg", "Saarburg", "Saarbrücken-Burbach"], f"nur frische, in Betrieb, höchste zuerst: {sts}")
check(sts[0]["time"].strftime("%H:%M") == "03:00", "Zeit in Ortszeit")
s = O.summary(sts)
check(s["count"] == 3 and abs(s["median"] - 0.113) < 1e-9 and s["max_name"] == "Homburg", f"Zusammenfassung: {s}")
check([x["name"] for x in O.find(sts, "saarb")] == ["Saarburg", "Saarbrücken-Burbach"] and O.find(sts, "664")[0]["name"] == "Homburg",
      "Suche nach Name und PLZ")
check(O.usv(0.1134) == "0,113", "µSv/h mit Komma")
check(O.parse_bbox("49.1, 6.3, 49.65, 7.45") == "49.1,6.3,49.65,7.45" and O.parse_bbox("kaputt") == O.DEFAULT_BBOX
      and O.parse_bbox("50,7,49,6") == O.DEFAULT_BBOX, "Box gelesen, Unsinn -> Standard")
check(O.stations({"error": "x"}, NOW) == [] and O.summary([]) is None, "kaputte Antwort: leer")
url = O.WFS.format(bbox=O.DEFAULT_BBOX)
check("odlinfo_odl_1h_latest" in url and "bbox=49.10,6.30,49.65,7.45," in url, "WFS-Adresse")

# ---------------------------------------------------------------- feestdag
from modules.commands.feestdag_command import FeestdagCommand  # noqa: E402

DE = [{"date": "2026-11-01", "localName": "Allerheiligen", "global": False, "counties": ["DE-BW", "DE-SL"]},
      {"date": "2026-10-31", "localName": "Reformationstag", "global": False, "counties": ["DE-SN"]},
      {"date": "2026-10-03", "localName": "Tag der Deutschen Einheit", "global": True, "counties": None}]
FR = [{"date": "2026-11-01", "localName": "Toussaint", "global": True, "counties": None}]
by = {"DE": DE, "FR": FR}
on = FeestdagCommand._holidays_on
check(on(by, date(2026, 11, 1), {"DE-SL"}) == [("DE", "Allerheiligen"), ("FR", "Toussaint")], "Allerheiligen gilt im Saarland")
check(on(by, date(2026, 10, 31), {"DE-SL"}) == [], "Reformationstag nicht im Saarland")
check(on(by, date(2026, 10, 3), {"DE-SL"}) == [("DE", "Tag der Deutschen Einheit")], "bundesweit immer")
check(on(by, date(2026, 10, 31)) == [("DE", "Reformationstag")], "ohne Regionen wie bisher: alle")


# ---------------------------------------------------------------- generate_config per country
def gen(opts, d):
    with open(f"{d}/options.json", "w") as f:
        json.dump(opts, f)
    r = subprocess.run([sys.executable, GEN, f"{d}/options.json", f"{d}/config.ini", d], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    c = configparser.ConfigParser(interpolation=None, strict=False)
    c.optionxform = str
    c.read(f"{d}/config.ini", encoding="utf-8")
    return c


def enabled(c, sec):
    return c.get(sec, "enabled", fallback="(none)")


nl = copy.deepcopy(OPTS)
nl.setdefault("weather", {})["default_country"] = "NL"
with tempfile.TemporaryDirectory() as d:
    c = gen(nl, d)
    check(enabled(c, "Pegel_Command") == "false" and enabled(c, "Warnung_Command") == "false"
          and enabled(c, "Odl_Command") == "false", "NL: pegel/warnung/odl aus")
    check(not c.has_option("Feestdag_Command", "countries"), "NL: feestdag wie bisher (NL/BE)")

de = copy.deepcopy(OPTS)
de.setdefault("weather", {})["default_country"] = "DE"
with tempfile.TemporaryDirectory() as d:
    c = gen(de, d)
    check(enabled(c, "Pegel_Command") == "(none)" and enabled(c, "Odl_Command") == "(none)", "DE: DE-Befehle an (Standard)")
    check(c.get("Feestdag_Command", "countries", fallback="") == "DE", "DE: Feiertage DE")
    check(c.get("Odl_Command", "bbox", fallback="") == "49.1,6.3,49.65,7.45", "odl-Karte mit Standard-Box")
    # the card switches odl off and sets SaarLorLux holidays: a restart keeps both
    c.set("Odl_Command", "enabled", "false")
    c.set("Feestdag_Command", "countries", "DE,FR,LU")
    c.set("Feestdag_Command", "regions", "DE-SL")
    with open(f"{d}/config.ini", "w", encoding="utf-8") as f:
        c.write(f)
    c2 = gen(de, d)
    check(enabled(c2, "Odl_Command") == "false", "auf der Karte ausgeschaltet: bleibt nach Neustart aus")
    check(c2.get("Feestdag_Command", "countries") == "DE,FR,LU" and c2.get("Feestdag_Command", "regions") == "DE-SL",
          "Feiertags-Länder und -Regionen von der Karte bleiben")

# extra_config also wins in a section the cards own (Webhook), added after the first start
with tempfile.TemporaryDirectory() as d:
    o = copy.deepcopy(de)
    gen(o, d)
    o.setdefault("advanced", {})["extra_config"] = ["Webhook.enabled = true", "Webhook.secret_token = abc"]
    c = gen(o, d)
    check(c.get("Webhook", "enabled") == "true" and c.get("Webhook", "secret_token") == "abc",
          "extra_config setzt Webhook auch nach dem ersten Start")
    o["advanced"]["extra_config"] = []
    c.set("Webhook", "port", "9000")
    with open(f"{d}/config.ini", "w", encoding="utf-8") as f:
        c.write(f)
    c = gen(o, d)
    check(c.get("Webhook", "port") == "9000", "ohne extra_config bleibt der Kartenwert")

# the NL-only commands and services are gone from the fork
ADDON = TESTS.parent / "meshcore-bot"
left = [n for n in ("beving", "buien", "energieprijs", "file", "kenteken", "ov", "p2000", "storing", "tanken", "waterstand",
                    "weerwaarschuwing", "wegwerk", "straling") if (ADDON / "local_commands" / f"{n}_command.py").exists()]
left += [n for n in ("p2000_service", "nl_alert_service") if (ADDON / "local_service_plugins" / f"{n}.py").exists()]
check(not left, f"NL-Befehle/Dienste entfernt ({left})")
import importlib.util as _iu  # noqa: E402
for name in ("weetjes", "quotes", "hangman_words"):
    spec = _iu.spec_from_file_location(name, ADDON / "local_shared" / "local_data" / f"{name}.py")
    mod = _iu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = getattr(mod, {"weetjes": "WEETJES", "quotes": "QUOTES", "hangman_words": "HANGMAN_WORDS"}[name])
    text = json.dumps(data, ensure_ascii=False).lower()
    check(not any(w in text for w in (" het ", " een ", "weetje:", "spreekwoord", "nederland ")), f"{name}: kein Niederländisch mehr")
from modules.local_data.weetjes import WEETJES as _W  # noqa: E402
check(all(len(w.encode()) <= 125 for w in _W), "weetjes: jede Zeile passt in eine Nachricht")
from modules.local_data.hangman_words import HANGMAN_WORDS as _H  # noqa: E402
check(all(w.isascii() and w.isalpha() and w.islower() for ws in _H.values() for w in ws), "hangman: nur a-z (ae/oe/ue/ss)")

print(f"\n{len(fails)} Fehler")
sys.exit(1 if fails else 0)
