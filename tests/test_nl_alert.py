"""NL-Alert in a channel: feed parsing, province/radius filter, splitting (≤130 bytes), no repeats, nothing old after a
start, and the monthly siren test (first Monday 12:00, holidays skipped, June/December with the NL-Alert test)."""
import asyncio
import configparser
import contextlib
import json
import os
import sqlite3
import sys
import tempfile
import types
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

TREE = sys.argv[1]
os.chdir(TREE)
sys.path.insert(0, TREE)

from modules import nl_alert as N  # noqa: E402
from modules.service_plugins.nl_alert_service import NLAlertService  # noqa: E402

fails = []


def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c:
        fails.append(m)


def poly(lat, lon, d=0.01):
    return f"{lat - d},{lon - d} {lat - d},{lon + d} {lat + d},{lon + d} {lat + d},{lon - d}"


NOW = 1790900000.0
iso = lambda ts: datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
LONG = ("Gevaarlijke stof vrijgekomen in Bonksel, Asten. Ga naar binnen! Sluit ramen en deuren. Zet ventilatie uit. "
        "https://brabantalert.nl/ *** Dutch Public Warning System. Dangerous substance released. Go inside!")
FEED = {"data": [
    {"id": "lim1", "message": "Brand met veel rook in Sittard. Blijf uit de rook! Sluit ramen en deuren. *** Dutch Public Warning System. Fire.",
     "type": "alert", "start_at": iso(NOW - 120), "stop_at": iso(NOW + 3600), "area": [poly(51.0, 5.87)]},
    {"id": "bra1", "message": LONG, "type": "alert", "start_at": iso(NOW - 300), "stop_at": iso(NOW + 3600),
     "area": [poly(51.41, 5.75)]},
]}

# ---------------------------------------------------------------- module
alerts = N.parse_feed(FEED)
check([a["id"] for a in alerts] == ["lim1", "bra1"] and alerts[0]["text"].endswith("Sluit ramen en deuren."), "feed gelezen, alleen de Nederlandse tekst")
check(len(alerts[0]["areas"][0]) == 4 and alerts[0]["stop"] > alerts[0]["start"], "gebied en tijden gelezen")
parts = N.split(alerts[1]["text"], "NL-Alert")
check(all(len(p.encode()) <= 130 for p in parts) and parts[0].startswith("NL-Alert 1/") and len(parts) <= 3, f"gesplitst ≤130 bytes: {parts}")
check(N.split("Kort bericht.", "NL-Alert") == ["NL-Alert: Kort bericht."], "kort bericht in één keer")
huge = N.split("woord " * 200, "NL-Alert")
check(len(huge) == 3 and huge[-1].endswith("…") and all(len(p.encode()) <= 130 for p in huge), "te lang: 3 delen, laatste afgekapt")
prov = {(51.0, 5.87): "Limburg", (51.41, 5.75): "Noord-Brabant"}
of = lambda p: prov.get((round(p[0], 2), round(p[1], 2)))
check(N.wanted(alerts[0], ["Limburg"], 0, None, of) and not N.wanted(alerts[1], ["Limburg"], 0, None, of), "provincie Limburg: Sittard wel, Asten niet")
check(N.wanted(alerts[1], ["Limburg"], 20, (51.45, 5.80), of), "straal rond de bot neemt ook Asten mee")
check(N.wanted(alerts[1], [], 0, None, of), "geen provincie en geen straal = heel Nederland")
check(N.new_alerts(alerts, set(), {}, NOW, first_run=True) == [], "eerste start: niets posten (alleen onthouden)")
check([a["id"] for a in N.new_alerts(alerts, set(), {}, NOW, False)] == ["bra1", "lim1"], "nieuwe meldingen, oudste eerst")
check(N.new_alerts(alerts, {"lim1", "bra1"}, {}, NOW, False) == [], "al gezien: niet opnieuw")
check([a["id"] for a in N.new_alerts(alerts, set(), {N.text_key(alerts[0]["text"]): NOW - 3600}, NOW, False)] == ["bra1"],
      "zelfde tekst met nieuwe id (verlenging) binnen 12 uur: niet opnieuw")
check(N.new_alerts(alerts, set(), {}, NOW + 7200, False) == [], "verlopen melding wordt niet gepost")

# siren test calendar
days26 = [date(2026, m, d) for m in range(1, 13) for d in range(1, 8) if N.siren_test_day(date(2026, m, d))]
check(date(2026, 4, 6) not in days26 and date(2026, 5, 4) not in days26, "2e paasdag (6-4-2026) en 4 mei: geen test")
check(date(2026, 6, 1) in days26 and date(2026, 10, 5) in days26 and len(days26) == 10, f"2026: 10 testdagen ({len(days26)})")
check(not N.siren_test_day(date(2028, 1, 3)), "na 1-1-2028 geen sirenes meer")
check(N.siren_due(datetime(2026, 10, 5, 12, 0), "") == "plain", "5 oktober 12:00: sirenetest")
check(N.siren_due(datetime(2026, 12, 7, 12, 3), "") == "with_test", "december: ook het NL-Alert-controlebericht")
check(N.siren_due(datetime(2026, 10, 5, 11, 59), "") is None and N.siren_due(datetime(2026, 10, 5, 12, 20), "") is None, "alleen tussen 12:00 en 12:15")
check(N.siren_due(datetime(2026, 10, 5, 12, 5), "2026-10") is None, "maar één keer per maand")
check(N.siren_due(datetime(2026, 10, 12, 12, 0), "") is None, "tweede maandag: niets")


# ---------------------------------------------------------------- service
class DB:
    def __init__(self, path):
        self.path = path
        with self.connection() as c:
            c.execute("CREATE TABLE bot_metadata (key TEXT PRIMARY KEY, value TEXT)"); c.commit()

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        with self.connection() as c:
            r = c.execute("SELECT value FROM bot_metadata WHERE key=?", (k,)).fetchone()
            return r[0] if r else None

    def set_metadata(self, k, v):
        with self.connection() as c:
            c.execute("INSERT OR REPLACE INTO bot_metadata VALUES (?,?)", (k, v)); c.commit()


class CM:
    def __init__(self): self.sent = []
    async def send_channel_message(self, ch, text, **kw):
        self.sent.append((ch, text)); return True


def make(**card):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_latitude": "50.94", "bot_longitude": "5.96", "timezone": "Europe/Amsterdam"}
    cfg["Localization"] = {"language": "nl"}
    cfg["NLAlert"] = {"enabled": "true", "channel": "#NLAlert", "provinces": "Limburg", "radius_km": "0", "siren_test": "true", **card}
    from modules.i18n import Translator
    tr = Translator("nl", "translations/", "local/translations")
    import logging
    bot = types.SimpleNamespace(config=cfg, logger=logging.getLogger("t"), db_manager=DB(tempfile.mktemp()), command_manager=CM(),
                                connected=True, translator=tr, get_translator=lambda lang: tr)
    s = NLAlertService(bot)
    async def fake_province(p):
        return of(p)
    s.province_of = fake_province
    return s, bot


async def main():
    import modules.nl_alert as NA
    NA.GAP_S = 0
    s, bot = make()
    check(s.channel == "#nlalert" and s.provinces == ["Limburg"], "kaart gelezen (kanaal in kleine letters)")
    october_noon = datetime(2026, 10, 5, 12, 1, tzinfo=ZoneInfo("Europe/Amsterdam")).timestamp()   # a siren test day: checked below, not here
    n = await s.tick(now=NOW, data=FEED)
    check(n == 0 and bot.command_manager.sent == [], "eerste ronde na de start: niets gepost")
    feed2 = {"data": [{"id": "lim2", "message": "Gevaarlijke stof in Maastricht. Ga naar binnen! Sluit ramen en deuren.",
                       "type": "alert", "start_at": iso(NOW), "stop_at": iso(NOW + 3600), "area": [poly(51.0, 5.87)]},
                      {"id": "bra2", "message": "Brand in Asten. Blijf uit de rook!", "type": "alert", "start_at": iso(NOW),
                       "stop_at": iso(NOW + 3600), "area": [poly(51.41, 5.75)]}] + FEED["data"]}
    import modules.service_plugins.nl_alert_service as SM
    SM.GAP_S = 0
    n = await s.tick(now=NOW + 60, data=feed2)
    sent = bot.command_manager.sent
    check(n == 1 and sent == [("#nlalert", "NL-Alert: Gevaarlijke stof in Maastricht. Ga naar binnen! Sluit ramen en deuren.")],
          f"nieuwe melding in Limburg gepost, Asten niet: {sent}")
    n = await s.tick(now=NOW + 120, data=feed2)
    check(n == 0 and len(sent) == 1, "volgende ronde: niets dubbel")
    s2, bot2 = make()
    bot2.db_manager = bot.db_manager
    s2 = NLAlertService(bot2); s2.province_of = s.province_of
    n = await s2.tick(now=NOW + 180, data=feed2)
    check(n == 0, "na een herstart: wat al gezien was komt niet opnieuw")
    # siren test
    s3, bot3 = make()
    await s3.tick(now=october_noon, data={"data": []})
    check(bot3.command_manager.sent and bot3.command_manager.sent[0][1].startswith("Sirenetest:")
          and len(bot3.command_manager.sent[0][1].encode()) <= 130, f"sirenetest gepost: {bot3.command_manager.sent}")
    await s3.tick(now=october_noon + 120, data={"data": []})
    check(len(bot3.command_manager.sent) == 1, "sirenetest maar één keer")
    s5, bot5 = make(channel="#NLAlert, #limburg")
    check(s5.channels == ["#nlalert", "#limburg"], f"meerdere kanalen ({s5.channels})")
    await s5.tick(now=october_noon, data={"data": []})
    check([c for c, _ in bot5.command_manager.sent] == ["#nlalert", "#limburg"], "sirenetest in beide kanalen")
    s4, bot4 = make(siren_test="false")
    await s4.tick(now=october_noon, data={"data": []})
    check(bot4.command_manager.sent == [], "sirenetest uit op de kaart: niets")

asyncio.run(main())
print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
