"""Greeting and channel hint in the language of the sender (AutoLanguage on): detection limited to our five languages,
shared words ("hallo") keep the bot's language, the card's own text per language wins over the standard text, and
"of" in the channel list follows the language too. Runs in the simulated build tree."""
import asyncio
import configparser
import contextlib
import logging
import os
import sqlite3
import sys
import tempfile
from unittest.mock import MagicMock

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.CRITICAL)
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


from modules import sender_language as SL  # noqa: E402
from modules.i18n import Translator  # noqa: E402
from modules.models import MeshMessage  # noqa: E402
from modules.commands.greeter_command import GreeterCommand  # noqa: E402
import modules.channel_hint as CH  # noqa: E402

try:
    import langdetect  # noqa: F401
    HAVE_LANGDETECT = True
except ImportError:
    HAVE_LANGDETECT = False


def config(auto=True, lang="nl"):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg["Bot"] = {"bot_name": "Mesh|HA|🤖"}
    cfg["Localization"] = {"language": lang}
    cfg["AutoLanguage"] = {"enabled": "true" if auto else "false"}
    return cfg


# ------------------------------------------------------------------ detection
c = config()
check(SL.detect(c, "bonjour") == "fr", "bonjour -> fr")
check(SL.detect(c, "Goedenavond") is None, "Nederlands bij een Nederlandse bot: geen wissel")
check(SL.detect(c, "hallo") is None and SL.detect(c, "Hallo!") is None, "hallo (ook Duits) houdt Nederlands")
check(SL.detect(config(lang="en"), "hallo") == "de", "hallo bij een Engelse bot: Duits (zoals upstream)")
check(SL.detect(c, "test") is None and SL.detect(c, "ping") is None, "commandowoorden: geen wissel")
check(SL.detect(config(auto=False), "bonjour") is None, "AutoLanguage uit: nooit een wissel")
check(SL.detect(c, "hola") is None, "Spaans: geen eigen teksten, dus geen wissel")
if HAVE_LANGDETECT:
    check(SL.detect(c, "Bonne soirée et bonne nuit à tous") == "fr", "zin in het Frans -> fr")
    check(SL.detect(c, "Guten Abend zusammen, hört mich jemand?") == "de", "zin in het Duits -> de")
    check(SL.detect(c, "Goedenavond allemaal, wie hoort mij?") is None, "zin in het Nederlands: geen wissel")
else:
    print("skip langdetect-zinnen (langdetect niet geinstalleerd)")


# ------------------------------------------------------------------ channel hint
def hint_for(cfg, text, where=None):
    bot = MagicMock()
    bot.config = cfg
    h = CH.ChannelHint.__new__(CH.ChannelHint)
    h.bot = bot
    h._last_variant, h._last_channel, h._last_user, h._bot_seen, h._tasks = {}, {}, {}, {}, set()
    h._settings_at = 0
    h._load_settings()
    h.enabled, h.yield_seconds = True, 0
    out = []

    async def send_now(channel_name, t):
        out.append(t)
        return True
    h._send_now = send_now
    asyncio.run(h.send_hint(MeshMessage(content=text, sender_id="Jean", channel="Publiek", is_dm=False), where=where))
    return out[0] if out else None


c = config()
c["ChannelHint"] = {"enabled": "true", "channels": "Publiek", "where": "#bot,#test",
                    "message": "Voor commando's ben je welkom in {channels}"}
check(hint_for(c, "test") == "Voor commando's ben je welkom in #bot of #test", "commandowoord: eigen Nederlandse tekst")
t = hint_for(c, "bonjour")
check(t in [v.strip().replace("{channels}", "#bot ou #test") for v in CH.DEFAULT_TEXTS["fr"][0].split("||")],
      f"Frans: standaard Franse tekst met 'ou': {t}")
c["ChannelHint"]["message_fr"] = "Les commandes, c'est dans {channels}"
check(hint_for(c, "bonjour") == "Les commandes, c'est dans #bot ou #test", "Frans: eigen tekst van de kaart wint")
check(hint_for(c, "bonjour", where=["#bot"]) == CH.DEFAULT_TEXTS["fr"][1].replace("{channels}", "#bot"),
      "verkeerd kanaal: standaard Franse tekst")
e = config(lang="en")
e["ChannelHint"] = {"enabled": "true", "channels": "Publiek", "where": "#bot,#test"}
check(" or #test" in (hint_for(e, "test") or ""), "Engelse bot: 'or' in plaats van 'of'")


# ------------------------------------------------------------------ greeter
class DBM:
    def __init__(self, path):
        self.db_path = path

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.db_path)
        try:
            yield c
        finally:
            c.close()

    def get_metadata(self, k):
        return None

    def set_metadata(self, k, v):
        pass


def greet(cfg, text):
    cfg["Greeter_Command"] = dict({"enabled": "true", "rollout_days": "0", "channels": "Publiek",
                                   "greeting_message": "Welkom op de mesh, @[{sender}]! |", "include_mesh_info": "true",
                                   "mesh_info_format": "Mesh info: {total_contacts} contacten"},
                                  **(dict(cfg["Greeter_Command"]) if cfg.has_section("Greeter_Command") else {}))
    bot = MagicMock()
    bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("g"), DBM(tempfile.mktemp())
    bot.get_translator = lambda lang: Translator(lang, "translations/", "local/translations")
    g = GreeterCommand(bot)

    async def info():
        return {"total_contacts": 900, "repeaters": 120, "companions": 700, "recent_activity_24h": 150}
    g._get_mesh_info = info
    sent = []

    async def chunked(message, parts, **kw):
        sent.extend(parts)
        return True
    g.send_response_chunked = chunked
    g.get_max_message_length = lambda m: 130
    asyncio.run(g._send_greeting(MeshMessage(content=text, sender_id="Jean", channel="Publiek", is_dm=False)))
    return sent


s = greet(config(), "Goedenavond")
check(s and s[0].startswith("Welkom op de mesh, @[Jean]!") and "900 contacten" in s[-1], f"Nederlands: eigen tekst ({s})")
s = greet(config(), "bonjour")
check(s and s[0].startswith("Bienvenue sur le mesh, @[Jean] !") and "900 contacts" in s[-1] and "répéteurs" in s[-1],
      f"Frans: standaard Franse begroeting en mesh-info ({s})")
fr = config()
fr["Greeter_Command"] = {"greeting_message_fr": "Salut @[{sender}], bienvenue chez Vip !"}
s = greet(fr, "bonjour")
check(s and s[0].startswith("Salut @[Jean], bienvenue chez Vip !"), f"Frans: eigen tekst van de kaart wint ({s})")
s = greet(config(auto=False), "bonjour")
check(s and s[0].startswith("Welkom op de mesh"), "AutoLanguage uit: gewoon de eigen tekst")
s = greet(config(), "bonjour")
s2 = greet(config(), "Goedenavond")
check(s2 and s2[0].startswith("Welkom"), "na een Franse begroeting is de volgende weer Nederlands")
src = open("modules/commands/greeter_command.py").read()
check('"key": "greeting_message_fr"' in src, "kaartveld 'Greeting in French' op de Greeter-kaart")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
