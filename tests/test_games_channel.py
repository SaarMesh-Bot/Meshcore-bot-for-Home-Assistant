"""Games channel (modules/games_channel.py + patch_games_channel.py): game commands only in one channel.

Runs in the simulated build tree: test_games_channel.py <tree>.
"""
import asyncio
import configparser
import importlib
import logging
import os
import sys
import types
from unittest.mock import MagicMock

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.ERROR)

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def imp(name):
    for _ in range(40):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name.split(".")[0] == "modules":
                raise
            sys.modules[e.name] = MagicMock()
            sys.modules.setdefault(e.name.split(".")[0], MagicMock())
    raise SystemExit("te veel ontbrekende modules")


G = imp("modules.games_channel")
Translator = imp("modules.i18n").Translator
MeshMessage = imp("modules.models").MeshMessage
Quiz = imp("modules.commands.quiz_command").QuizCommand
Karma = imp("modules.commands.karma_command").KarmaCommand
Xp = imp("modules.commands.xp_command").XpCommand
Service = imp("modules.service_plugins.games_channel_service").GamesChannelService
sent = []


def make_bot(card=None, lang="nl"):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
    cfg["Localization"] = {"language": lang}
    if card is not None:
        cfg["GamesChannel"] = card
    bot = types.SimpleNamespace(config=cfg, logger=logging.getLogger("games"), db_manager=MagicMock(), services={},
                                translator=Translator(lang, "translations/", "local/translations"), connected=True)

    async def send_channel_message(channel, text, **kw):
        sent.append((channel, text))
        return True
    bot.command_manager = types.SimpleNamespace(monitor_channels=["#bot", "#test", "#games"], commands={},
                                                send_channel_message=send_channel_message)
    return bot


def msg(channel=None, dm=False, text="quiz"):
    return MeshMessage(content=text, sender_id="Piet", channel=None if dm else channel, is_dm=dm)


ON = {"enabled": "true", "channel": "#Games", "commands": "quiz, hangman, poll, peiling, checkin, karma, voorspel", "pointer": "false"}

# ---------------------------------------------------------------- off: nothing changes
for card, why in ((None, "geen kaart"), ({"enabled": "false", "channel": "#games"}, "kaart uit"), ({"enabled": "true", "channel": ""}, "geen kanaal")):
    b = make_bot(card)
    check(Quiz(b).is_channel_allowed(msg("#bot")) and Quiz(b).is_channel_allowed(msg("#games")), f"{why}: quiz werkt overal zoals vroeger")

# ---------------------------------------------------------------- on
b = make_bot(ON)
q, k, x = Quiz(b), Karma(b), Xp(b)
check(q.is_channel_allowed(msg("#games")) and q.is_channel_allowed(msg("#GAMES")), "quiz werkt in het spellenkanaal (hoofdletters maken niet uit)")
check(not q.is_channel_allowed(msg("#bot")) and not k.is_channel_allowed(msg("#test")), "quiz en karma zijn stil in andere kanalen")
check(q.is_channel_allowed(msg(dm=True)) and k.is_channel_allowed(msg(dm=True)), "DM's werken altijd")
check(x.is_channel_allowed(msg("#bot")) and x.is_channel_allowed(msg("#games")), "xp staat niet op de lijst: werkt overal")
check(not x.is_channel_allowed(msg("#nergens")), "een kanaal waar de bot niet luistert blijft dicht voor gewone commando's")
check(G.held_back(q, msg("#bot")) and not G.held_back(q, msg("#games")) and not G.held_back(x, msg("#bot")), "held_back: alleen een spel buiten het spellenkanaal")

# ---------------------------------------------------------------- pointer
sent.clear()
check(asyncio.run(G.send_pointer(b, msg("#bot"))) is False and sent == [], "verwijzing staat standaard uit: stil")
bp = make_bot(dict(ON, pointer="true"))
G._last_pointer.clear()
ok1 = asyncio.run(G.send_pointer(bp, msg("#bot"), now=1000.0))
ok2 = asyncio.run(G.send_pointer(bp, msg("#bot"), now=1000.0 + 600))
ok3 = asyncio.run(G.send_pointer(bp, msg("#test"), now=1000.0 + 600))
ok4 = asyncio.run(G.send_pointer(bp, msg("#bot"), now=1000.0 + 1801))
check(ok1 and not ok2 and ok3 and ok4, "verwijzing hooguit één keer per 30 minuten per kanaal")
check(sent[0] == ("#bot", "Spellen spelen we in #games"), f"verwijzing in de taal van de bot ({sent[0]})")
G._last_pointer.clear(); sent.clear()
asyncio.run(G.send_pointer(make_bot(dict(ON, pointer="true"), lang="en"), msg("#bot"), now=5.0))
check(sent == [("#bot", "Games are played in #games")], f"en: {sent}")

# ---------------------------------------------------------------- card
keys = [f["key"] for f in Service.settings_schema]
check(keys == ["channel", "commands", "pointer"] and Service.config_section == "GamesChannel", f"kaart GamesChannel ({keys})")
check([f["default"] for f in Service.settings_schema] == ["", G.DEFAULT_COMMANDS, False], "standaard: geen kanaal, geen verwijzing")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
