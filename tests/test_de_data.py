"""German data (DE pack): DWD + NINA warnings (wording, state/district filter, NINA's DWD copies dropped, splitting,
no repeats, nothing old after a start, all-clear only for what was posted), the water levels (PEGELONLINE W series,
robust trend, Saarland HMD text with -9999, stale data marked) and the Pegel alarm (only rises, all-clear with
hysteresis, survives a restart). Real-shaped answers, no network."""
import asyncio
import configparser
import contextlib
import logging
import os
import pathlib
import sqlite3
import sys
import tempfile
import types
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TREE = sys.argv[1]
os.chdir(TREE)
sys.path.insert(0, TREE)
FIX = pathlib.Path(__file__).resolve().parent / "fixtures"

from modules import de_pegel as P  # noqa: E402
from modules import de_warn as W  # noqa: E402
from modules.service_plugins import de_warn_service as DS  # noqa: E402
from modules.service_plugins import pegel_alarm_service as PS  # noqa: E402

fails = []


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        fails.append(m)


TZ = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 10, 18, 14, 0, tzinfo=TZ)
ms = lambda dt: int(dt.timestamp() * 1000)

# ---------------------------------------------------------------- wording
check(W.compact_phenom("Amtliche WARNUNG vor STARKEM GEWITTER") == "Gewitter (stark)", "DWD-Schlagzeile kompakt")
check(W.compact_phenom("Amtliche UNWETTERWARNUNG vor ORKANBÖEN") == "Orkanböen", "Orkanböen")
check(W.short_region("Landkreis Saarlouis") == "Saarlouis" and W.short_region("Regionalverband Saarbrücken") == "Saarbrücken",
      "Kreis-Präfixe weg")
check(W.nina_phenom("Rauchentwicklung nach Brand in Dillingen", "Fire") == "Rauch", "NINA: Rauch vor Brand")
check(W.when(NOW + timedelta(hours=4), NOW + timedelta(hours=6), NOW) == "18:00–20:00", "Zeitfenster heute ohne Datum")
check(W.when(NOW - timedelta(hours=1), NOW + timedelta(hours=2), NOW) == "bis 16:00", "läuft schon: 'bis'")
check(W.when(NOW + timedelta(hours=12), NOW + timedelta(hours=20), NOW) == "19.10. 02:00–10:00", "morgen mit Datum")
check(W.level_icon(4) == "🟥" and W.level_icon(3) == "🟧" and W.level_icon(2) == "🟨" and W.level_icon(50) == "🟧"
      and W.level_icon(51) == "🟥", "Stufen-Symbole, auch Hitze 50/51")

# ---------------------------------------------------------------- DWD
def dwd_w(state, region, level, headline, start, end):
    return {"state": {"SL": "Saarland", "RP": "Rheinland-Pfalz", "BW": "Baden-Württemberg"}[state], "type": 2,
            "level": level, "start": ms(start), "end": ms(end), "regionName": region, "event": headline.split()[-1],
            "headline": headline, "stateShort": state, "description": "x", "instruction": "y"}


DWD = {"time": ms(NOW), "warnings": {
    "110044000": [dwd_w("SL", "Kreis Saarlouis", 3, "Amtliche WARNUNG vor STARKEM GEWITTER", NOW + timedelta(hours=4), NOW + timedelta(hours=6))],
    "110041000": [dwd_w("SL", "Regionalverband Saarbrücken", 2, "Amtliche WARNUNG vor STURMBÖEN", NOW - timedelta(hours=1), NOW + timedelta(hours=2)),
                  dwd_w("SL", "Regionalverband Saarbrücken", 1, "Amtliche WARNUNG vor FROST", NOW, NOW + timedelta(hours=8))],
    "107235000": [dwd_w("RP", "Kreis Trier-Saarburg und Stadt Trier", 3, "Amtliche WARNUNG vor DAUERREGEN", NOW, NOW + timedelta(hours=8))],
    "108326000": [dwd_w("BW", "Schwarzwald-Baar-Kreis", 3, "Amtliche WARNUNG vor DAUERREGEN", NOW, NOW + timedelta(hours=8))],
    "110045000": [dwd_w("SL", "Saarpfalz-Kreis", 2, "Amtliche WARNUNG vor GLÄTTE", NOW - timedelta(hours=5), NOW - timedelta(hours=1))],
}}
jsonp = "warnWetter.loadWarnings(" + __import__("json").dumps(DWD) + ");"
data = W.parse_dwd_payload(jsonp)
check(data is not None and len(data["warnings"]) == 5, "JSONP-Hülle des DWD gelesen")
items = W.dwd_items(data, ["SL"], NOW, 2)
texts = [i["text"] for i in items]
check(texts == ["🟧 Saarlouis · Gewitter (stark) · 18:00–20:00", "🟨 Saarbrücken · Sturmböen · bis 16:00"],
      f"nur Saarland, ab Stufe 2, abgelaufene weg, stärkste zuerst: {texts}")
check(not any("Trier" in t for t in texts), "Trier-Saarburg (RP) nicht mehr per Freitext reingezogen")
check(len(W.dwd_items(data, ["SL", "RP"], NOW, 2)) == 3, "zwei Bundesländer")
check(len(W.dwd_items(data, ["SL"], NOW, 1)) == 3, "Stufe 1 bringt Frost dazu")
check(W.parse_dwd_payload("<html>Wartung</html>") is None, "kaputte Antwort: None statt Absturz")

# ---------------------------------------------------------------- NINA
def card(cid, headline, sev, msg="Alert", provider="MOWAS", cat_en="", onset=None, expires=None):
    d = {"headline": headline, "provider": provider, "severity": sev, "urgency": "Immediate", "msgType": msg}
    if onset:
        d["onset"] = onset.isoformat()
    if expires:
        d["expires"] = expires.isoformat()
    return {"id": cid, "payload": {"version": 1, "type": "ALERT", "id": cid, "hash": cid, "data": d},
            "i18nTitle": {"de": headline, "en": cat_en}, "sent": NOW.isoformat()}


NINA = [
    card("mow.1", "Rauchentwicklung nach Brand in Dillingen - Landkreis Saarlouis", "Minor", cat_en="Fire"),
    card("mow.2", "1. AKTUALISIERUNG: Bakteriologische Beeinträchtigung des Trinkwassers - Chlorung - Biringen", "Minor",
         cat_en="Contaminated drinking water"),
    card("dwd.1", "Amtliche WARNUNG vor STARKEM GEWITTER", "Severe", provider="DWD", cat_en="Thunderstorm"),
    card("mow.3", "Entwarnung: Gefahrstoffaustritt in Saarlouis", "Minor", msg="Cancel", cat_en="Hazmat"),
    card("mow.4", "Bombenentschärfung in Saarlouis-Innenstadt - Saarland", "Severe", expires=NOW + timedelta(hours=3)),
]
tokens = W.settings(configparser.ConfigParser())["tokens"]
warns, cancels = W.nina_items(NINA, "Saarlouis", NOW, tokens)
wt = [w["text"] for w in warns]
check(any(t.startswith("🟩 Saarlouis · Rauch") for t in wt), f"Rauch trotz 'Minor' gepostet: {wt}")
check(not any("Trinkwasser" in t for t in wt), "harmlose 'Minor'-Meldung (Chlorung) nicht")
check(any(t.startswith("🟧 Saarland ·") and t.endswith("· bis 17:00") for t in wt), f"landesweit am Schlagzeilen-Suffix erkannt: {wt}")
check(len(cancels) == 1 and cancels[0][0].startswith("nina::saarlouis::gefahrstoff::"), f"Entwarnung erkannt: {cancels}")
warns2, _ = W.nina_items([dict(NINA[0], id="mow.1-001", sent=(NOW + timedelta(minutes=5)).isoformat())], "Saarlouis", NOW, tokens)
check(warns2[0]["key"] == warns[0]["key"], "Update mit neuer ID: gleicher Schlüssel (kein Doppelpost)")
dwd_like = [{"key": "nina::saarlouis::gewitter (stark)::x", "text": "🟧 Saarlouis · Gewitter (stark)", "region": "saarlouis",
             "phenom": "gewitter (stark)", "is_dwd": True}]
check(len(W.merge(W.dwd_items(data, ["SL"], NOW, 2), dwd_like)) == 2, "NINA-Kopie einer DWD-Warnung fällt weg")
check(W.normalize_ars("10044") == "100440000000" and W.normalize_ars("x") == "", "ARS auf 12 Stellen")
d = W.parse_districts("10041, 10044=Saarlouis-Test, 07235, kaputt")
check(d == {"10041": "Regionalverband Saarbrücken", "10044": "Saarlouis-Test", "07235": "Kreis 07235"}, f"Kreise gelesen: {d}")

lines = [f"🟧 Kreis {i} · Gewitter (stark) · 18:00–20:00" for i in range(6)]
parts = W.split_lines("🚨 Warnung (6)", lines, 130)
check(all(len(p.encode()) <= 130 for p in parts) and sum(p.count("\n") + 1 for p in parts) == 7, f"gepackt ≤130 Bytes: {parts}")
check(W.split_lines("", ["ä" * 200], 130)[0].endswith("…"), "zu lange Zeile gekürzt")

# ---------------------------------------------------------------- Pegel
st = P.parse_stations(P.DEFAULT_STATIONS + "; kaputt; x=ftp:1:y")
check(list(st) == ["saar", "blies", "nied"] and st["nied"] == {"source": "hmd", "id": "W1102220", "label": "Nied (Niedaltdorf)"},
      f"Stationen gelesen: {st}")
check(P.parse_stations("Saar=pegelonline:26400220:Saar")["saar"]["source"] == "po", "alte Quellnamen gehen auch")
PO = {"number": "26400220", "shortname": "Sankt Arnual", "longname": "SANKT ARNUAL", "timeseries": [
    {"shortname": "Q", "unit": "m³/s", "currentMeasurement": {"timestamp": "2026-10-18T13:45:00+02:00", "value": 7.8}},
    {"shortname": "W", "unit": "cm", "currentMeasurement": {"timestamp": "2026-10-18T13:45:00+02:00", "value": 352.0}}]}
cur = P.po_current(PO, TZ)
check(cur["value_cm"] == 352.0 and cur["time"].hour == 13, "nur die W-Reihe (nicht Abfluss Q)")
hist = [{"value": v} for v in (340, 345, 338, 342, 344, 346, 349, 360, 351, 353, 352, 354)]
tr = P.po_trend(hist)
check(8 <= tr <= 12, f"Trend robust gegen Ausreißer (Median): {tr}")
check(P.trend_text(tr).startswith(" (↗️ +") and P.trend_text(0.2) == " (→ 0 cm/3h)" and P.trend_text(None) == "", "Trendtext")
check(P.metres(352) == "3,52", "Meter mit Komma")
series = P.parse_hmd((FIX / "hmd_blies.txt").read_text(), TZ)
hc = P.hmd_current(series)
check(hc["value_cm"] == 23 and hc["time"] == datetime(2026, 10, 18, 0, 0, tzinfo=TZ), "HMD: Titelzeile und -9999 übersprungen")
check(hc["trend_cm"] == 23 - 5, f"HMD-Trend 3 h: {hc['trend_cm']}")
check(not P.fresh(hc["time"], NOW) and P.fresh(hc["time"], datetime(2026, 10, 18, 2, 0, tzinfo=TZ)), "veraltet nach 6 h")
check(P.hmd_urls("W1102220")[0].startswith("https://iframe01."), "HMD: aktueller Host zuerst (umweltserver steht auf 2017)")
th = P.parse_thresholds(P.DEFAULT_THRESHOLDS)
check([c for c, _ in th] == [280, 320, 350, 380, 400, 750] and P.stage(352, th) == 3 and P.stage(100, th) == 0, "Stufen")


# ---------------------------------------------------------------- services
class DB:
    def __init__(self):
        self.path = tempfile.mktemp()
        with self.c() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
            c.commit()

    @contextlib.contextmanager
    def c(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        with self.c() as c:
            r = c.execute("SELECT value FROM bot_metadata WHERE key=?", (k,)).fetchone()
            return r[0] if r else None

    def set_metadata(self, k, v):
        with self.c() as c:
            c.execute("INSERT OR REPLACE INTO bot_metadata VALUES (?,?)", (k, v))
            c.commit()


class CM:
    def __init__(self):
        self.sent = []

    async def send_channel_message(self, ch, text, **kw):
        self.sent.append((ch, text))
        return True


def make_bot(db=None, **sections):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"timezone": "Europe/Berlin"}
    cfg["Localization"] = {"language": "de"}
    for name, vals in sections.items():
        cfg[name] = vals
    from modules.i18n import Translator
    tr = Translator("de", "translations/", "local/translations")
    return types.SimpleNamespace(config=cfg, logger=logging.getLogger("t"), db_manager=db or DB(), command_manager=CM(),
                                 connected=True, translator=tr, get_translator=lambda lang: tr)


async def main():
    DS.GAP_S = PS.GAP_S = 0
    ts = NOW.timestamp()
    bot = make_bot(DEWarn={"enabled": "true", "channel": "#Warnings"})
    s = DS.DEWarnService(bot)
    check(s.channels == ["#warnings"] and s.s["states"] == ["SL"] and len(s.s["districts"]) == 6, "Karte: Standard Saarland")
    dwd = W.dwd_items(data, ["SL"], NOW, 2)
    n = await s.tick(now=ts, fetched=(dwd, warns, [], True))
    check(n == 0 and bot.command_manager.sent == [], "erste Runde: nichts posten, nur merken")
    new_dwd = dwd + [{"key": "dwd::neunkirchen::orkanböen::", "text": "🟥 Neunkirchen · Orkanböen · bis 18:00", "level": 4,
                      "region": "neunkirchen", "phenom": "orkanböen", "end": None}]
    n = await s.tick(now=ts + 300, fetched=(new_dwd, warns, [], True))
    sent = bot.command_manager.sent
    check(n == 1 and sent == [("#warnings", "🚨 Warnung (1)\n🟥 Neunkirchen · Orkanböen · bis 18:00")], f"nur die neue gepostet: {sent}")
    n = await s.tick(now=ts + 600, fetched=(new_dwd, warns, [], True))
    check(n == 0 and len(sent) == 1, "nächste Runde: nichts doppelt")
    n = await s.tick(now=ts + 900, fetched=(None, warns, [], True))
    n += await s.tick(now=ts + 1200, fetched=(new_dwd, warns, [], True))
    check(n == 0 and len(sent) == 1, "DWD kurz weg und wieder da: nichts doppelt")
    # an all-clear for something posted
    gas = {"key": "nina::saarlouis::gefahrstoff::abc", "text": "🟧 Saarlouis · Gefahrstoff", "sev": "severe",
           "region": "saarlouis", "phenom": "gefahrstoff", "is_dwd": False}
    await s.tick(now=ts + 1500, fetched=(new_dwd, warns + [gas], [], True))
    check(sent[-1][1].endswith("🟧 Saarlouis · Gefahrstoff"), "Gefahrstoff gepostet")
    n = await s.tick(now=ts + 1800, fetched=(new_dwd, warns, [("nina::saarlouis::gefahrstoff::", "Saarlouis · Gefahrstoff")], True))
    check(n == 1 and sent[-1][1] == "✅ Entwarnung: Saarlouis · Gefahrstoff", f"Entwarnung: {sent[-1]}")
    n = await s.tick(now=ts + 2100, fetched=(new_dwd, warns, [("nina::saarlouis::gefahrstoff::", "Saarlouis · Gefahrstoff")], True))
    check(n == 0, "Entwarnung nur einmal")
    n = await s.tick(now=ts + 2400, fetched=(new_dwd, warns, [("nina::homburg::brand::", "Homburg · Brand")], True))
    check(n == 0, "keine Entwarnung für etwas, das nie gepostet wurde")
    s2 = DS.DEWarnService(make_bot(db=bot.db_manager, DEWarn={"enabled": "true"}))
    n = await s2.tick(now=ts + 2700, fetched=(new_dwd, warns, [], True))
    check(n == 0, "nach Neustart: Bekanntes nicht neu")
    # pointer channels (SaarMesh fork 1.5.1-sm.8): one line after a post with new warnings, at most once an hour
    bp = make_bot(DEWarn={"enabled": "true", "pointer_channels": "Public, #saarland, #warnings"})
    sp = DS.DEWarnService(bp)
    check(sp.pointer_channels == ["Public", "#saarland"], f"Hinweis-Kanäle (ohne den Warnkanal selbst): {sp.pointer_channels}")
    await sp.tick(now=ts, fetched=(dwd, warns, [], True))
    await sp.tick(now=ts + 300, fetched=(new_dwd, warns, [], True))
    ps = bp.command_manager.sent
    check([c for c, _ in ps] == ["#warnings", "Public", "#saarland"] and ps[1][1] == "⚠️ Warnungen aktiv im Saarland. Infos im #warnings",
          f"Hinweis nach neuer Warnung: {ps}")
    await sp.tick(now=ts + 600, fetched=(new_dwd, warns + [gas], [], True))
    check([c for c, _ in ps][3:] == ["#warnings"], "innerhalb einer Stunde kein zweiter Hinweis")
    gas2 = dict(gas, key="nina::homburg::brand::x", text="🟧 Homburg · Brand")
    await sp.tick(now=ts + 4000, fetched=(new_dwd, warns + [gas, gas2], [], True))
    check([c for c, _ in ps][4:] == ["#warnings", "Public", "#saarland"], f"nach einer Stunde wieder: {[c for c, _ in ps]}")
    bq = make_bot(DEWarn={"enabled": "true"})
    check(DS.DEWarnService(bq).pointer_channels == [], "ohne Einstellung kein Hinweis")

    # Pegel alarm
    pb = make_bot(PegelAlarm={"enabled": "true", "channel": "#warnings"})
    p = PS.PegelAlarmService(pb)
    check(p.station["id"] == "26400220" and len(p.thresholds) == 6, "Pegel-Alarm: Standard Sankt Arnual")
    r = lambda cm, trend=4.0: {"value_cm": cm, "time": NOW, "trend_cm": trend}
    check(await p.tick(now=ts, reading=r(250)) == 0, "unter allen Stufen: nichts")
    await p.tick(now=ts, reading=r(352, 12))
    ps = pb.command_manager.sent
    check(ps and ps[-1][1] == "⚠️ Pegel Saar (Sankt Arnual): 3,52 m (↗️ +12 cm/3h) · Stufe 3/6: Meldehöhe 2"
          and len(ps[-1][1].encode()) <= 130, f"Stufe 3 gemeldet, kurz: {ps}")
    check(await p.tick(now=ts, reading=r(330, -5)) == 0, "Rückgang um eine Stufe: nichts")
    check(await p.tick(now=ts, reading=r(355)) == 0, "wieder Stufe 3: nicht nochmal")
    await p.tick(now=ts, reading=r(385))
    check("Stufe 4/6: A620-Sperrung wahrscheinlich" in ps[-1][1] and ps[-1][1].startswith("🚨"), f"Stufe 4: {ps[-1]}")
    p2 = PS.PegelAlarmService(make_bot(db=pb.db_manager, PegelAlarm={"enabled": "true"}))
    check(await p2.tick(now=ts, reading=r(386)) == 0, "Stufe übersteht Neustart")
    check(await p.tick(now=ts, reading=r(275)) == 0, "knapp unter der ersten Schwelle: noch keine Entwarnung")
    n = await p.tick(now=ts, reading=r(265, -20))
    check(n == 1 and ps[-1][1].startswith("✅ Entwarnung Pegel Saar"), f"Entwarnung mit Abstand: {ps[-1]}")
    check(await p.tick(now=ts, reading={"value_cm": 900, "time": NOW - timedelta(hours=8), "trend_cm": None}) == 0,
          "veralteter Messwert löst nichts aus")

asyncio.run(main())
print(f"\n{len(fails)} Fehler")
sys.exit(1 if fails else 0)
