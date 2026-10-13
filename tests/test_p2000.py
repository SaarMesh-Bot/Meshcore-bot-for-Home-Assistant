"""P2000 (card P2000 + command p2000): only priority-1 messages are posted (fresh ones, at most N an hour, nothing on
the first round), a daily count at 12:00 once, the command gives the latest / a place / urgent / today, only in the
card's channel and by DM. No network: API answers are made up here. Runs in the simulated build tree."""
import asyncio
import configparser
import contextlib
import logging
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.CRITICAL)
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


from modules import p2000 as P  # noqa: E402
from modules.i18n import Translator  # noqa: E402
from modules.models import MeshMessage  # noqa: E402
from modules.service_plugins.p2000_service import P2000Service  # noqa: E402
from modules.commands.p2000_command import P2000Command  # noqa: E402

TZ = ZoneInfo("Europe/Amsterdam")


def ts(d, hm):
    h, m = hm.split(":")
    return datetime(2026, 10, d, int(h), int(m), tzinfo=TZ).timestamp()


def melding(mid, d, hm, dienst, prio1, tekst, plaats=""):
    return {"id": str(mid), "tekstmelding": tekst, "melding": tekst, "dienst": dienst, "dienstid": "2", "regioid": "21",
            "plaats": plaats, "datum": f"{d:02d}-10", "tijd": hm, "prio1": "1" if prio1 else "0"}


class DBM:
    def __init__(self):
        self.path = tempfile.mktemp()
        self.meta = {}

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        return self.meta.get(k)

    def set_metadata(self, k, v):
        self.meta[k] = v


cfg = configparser.ConfigParser(interpolation=None)
cfg["Bot"] = {"bot_name": "Mesh|HA|🤖", "timezone": "Europe/Amsterdam"}
cfg["Localization"] = {"language": "nl"}
cfg["P2000"] = {"enabled": "true", "regions": "21", "channel": "#p2000-zl", "max_per_hour": "2"}
bot = MagicMock()
bot.config, bot.logger, bot.db_manager, bot.connected = cfg, logging.getLogger("p"), DBM(), True
bot.get_translator = lambda lang: Translator(lang, "translations/", "local/translations")
bot.translator = bot.get_translator("nl")
posts = []


async def send_channel_message(channel, text, **kw):
    posts.append((channel, text))
    return True
bot.command_manager.send_channel_message = send_channel_message
svc = P2000Service(bot)
check(svc.regions == ["21"] and svc.channel == "#p2000-zl", "kaart: regio en kanaal gelezen")

# ---- parse
items = P.parse({"meldingen": [melding(5, 12, "21:23 - 21:24", "Brandweer", True, "Brandweer met spoed naar Dorpsstraat, Geleen, voor een onderzoek", "6161GE  Geleen")]},
                datetime.fromtimestamp(ts(12, "22:00"), TZ))
check(items and items[0]["plaats"] == "Geleen" and items[0]["tijd"] == "21:23" and items[0]["prio1"]
      and items[0]["ts"] == int(ts(12, "21:23")), f"parse: plaats zonder postcode, tijd, prio 1 ({items})")

# ---- first round stores only
first = {"meldingen": [melding(1, 12, "20:00", "Brandweer", True, "Brandweer met spoed naar Dorpsstraat, Geleen, voor een onderzoek", "Geleen"),
                       melding(2, 12, "20:05", "Politie", False, "Bel OC GMS 100002")]}
asyncio.run(svc.tick(now=ts(12, "20:10"), data=first))
check(posts == [], "eerste ronde: alleen opslaan, niets posten")

# ---- new messages: only fresh priority 1, at most 2 an hour
second = {"meldingen": first["meldingen"] + [
    melding(3, 12, "20:20", "Ambulance", True, "A1 Heerlen rit: 100001", "Heerlen"),
    melding(4, 12, "20:21", "Politie", False, "P 2 Aanrijding Sittard", "Sittard"),
    melding(6, 12, "19:00", "Politie", True, "P 1 oud bericht", "Kerkrade"),
    melding(7, 12, "20:22", "Politie", True, "P 1 Achtervolging Maastricht", "Maastricht"),
    melding(8, 12, "20:23", "Brandweer", True, "Brandweer met spoed naar Kerkstraat, Stein, voor een gebouwbrand", "Stein")]}
asyncio.run(svc.tick(now=ts(12, "20:25"), data=second))
texts = [t for _, t in posts]
check(len(posts) == 2 and all(c == "#p2000-zl" for c, _ in posts), f"alleen prio 1 en hooguit 2 per uur ({texts})")
check(texts and texts[0] == "20:20 Ambulance: A1 Heerlen rit: 100001", f"ambulance met dienst ervoor ({texts[:1]})")
check(not any("oud bericht" in t or "Aanrijding" in t for t in texts), "geen oude prio 1, geen prio 2")
check(all(len(t.encode()) <= 130 for t in texts), "elk bericht past (130 bytes)")

# ---- daily count at 12:00, once
posts.clear()
asyncio.run(svc.tick(now=ts(13, "11:58"), data={"meldingen": []}))
check(posts == [], "voor 12:00 geen telling")
asyncio.run(svc.tick(now=ts(13, "12:01"), data={"meldingen": []}))
check(len(posts) == 1 and posts[0][1].startswith("P2000 24 u: brandweer 2 (2 spoed), ambulance 1 (1 A1), politie 4 (2 P1)"),
      f"telling om 12:00 ({posts})")
asyncio.run(svc.tick(now=ts(13, "12:05"), data={"meldingen": []}))
check(len(posts) == 1, "telling maar een keer per dag")


# ---- the command
def ask(text, is_dm=False, channel="#p2000-zl", now=ts(12, "20:30")):
    cmd = P2000Command(bot)
    m = MeshMessage(content=text, sender_id="Piet", channel=None if is_dm else channel, is_dm=is_dm)
    return cmd, cmd.answer(m, now=now)


cmd, r = ask("p2000")
check(r == ["20:23 Brandweer met spoed naar Kerkstraat, Stein, voor een gebouwbrand"], f"p2000: laatste ({r})")
_, r = ask("p2000 3")
check(len(r) == 3, "p2000 3: drie meldingen")
_, r = ask("p2000 heerlen")
check(r == ["20:20 Ambulance: A1 Heerlen rit: 100001"], f"p2000 <plaats> ({r})")
_, r = ask("p2000 nergensdorp")
check(r == ["Geen P2000-melding gevonden voor nergensdorp."], f"onbekende plaats ({r})")
_, r = ask("p2000 spoed")
check(r and "Kerkstraat" in r[0], "p2000 spoed: laatste prio 1")
_, r = ask("p2000 vandaag")
check(r and r[0].startswith("P2000 24 u: brandweer"), "p2000 vandaag: de telling")
_, r = ask("p2000", now=ts(14, "09:00"))
check(r and r[0].startswith("12-10 20:23"), f"ouder dan een dag: met datum ({r})")
check(cmd.is_channel_allowed(MeshMessage(content="p2000", sender_id="P", channel="#p2000-zl", is_dm=False))
      and cmd.is_channel_allowed(MeshMessage(content="p2000", sender_id="P", channel=None, is_dm=True))
      and not cmd.is_channel_allowed(MeshMessage(content="p2000", sender_id="P", channel="#limburg", is_dm=False)),
      "alleen in het kaartkanaal en via DM")
cfg["P2000"]["enabled"] = "false"
check(not P2000Command(bot).can_execute(MeshMessage(content="p2000", sender_id="P", channel=None, is_dm=True)),
      "kaart uit: commando uit")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
