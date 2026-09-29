"""botlist-commando + greeter tegen de echte (gepatchte) upstream-code."""
import os
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
ADDON = str(_TESTS.parent / "meshcore-bot")      # the add-on being tested
FIXTURES = str(_TESTS / "fixtures")
import asyncio, configparser, logging, os, sys, tempfile, types

sys.path.insert(0, os.environ["SIM_TREE"])
logging.basicConfig(level=logging.WARNING)

from unittest.mock import MagicMock


def import_with_stubs(fn):
    """Ontbrekende externe pakketten (aiohttp, ...) vervangen door lege stand-ins."""
    for _ in range(40):
        try:
            return fn()
        except ModuleNotFoundError as e:
            top = e.name.split(".")[0]
            if top in ("modules",):
                raise
            sys.modules[e.name] = MagicMock(); sys.modules[top] = sys.modules.get(top, MagicMock())
    raise SystemExit("te veel ontbrekende modules")


def _imports():
    global ChannelHint, get_channel_hint, MARKED_KEY, NEVER_KEY, MeshMessage, BotlistCommand, Translator
    from modules.channel_hint import ChannelHint, get_channel_hint, MARKED_KEY, NEVER_KEY
    from modules.models import MeshMessage
    from modules.commands.botlist_command import BotlistCommand
    from modules.i18n import Translator


import_with_stubs(_imports)


def nl_translator():
    return Translator("nl", "translations/", "local/translations")

OWN = "Mesh|HA|🤖"


class DB:
    def __init__(self): self.store = {}
    def get_metadata(self, k): return self.store.get(k)
    def set_metadata(self, k, v): self.store[k] = v


def make_bot(db=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": OWN}
    cfg["Channels"] = {"monitor_channels": "#test"}
    cfg["ChannelHint"] = {"enabled": "true", "channels": "Publiek", "where": "#bot,#test"}
    replies = []
    bot = types.SimpleNamespace(config=cfg, logger=logging.getLogger("t"), db_manager=db or DB(), replies=replies, translator=nl_translator())
    return bot


# ---------- 1. ChannelHint: lijsten en volgorde van regels
bot = make_bot()
h = get_channel_hint(bot)
assert h.classify("DX1ABC-BOT") == (True, "woord bot in de naam")
assert h.classify("Alex")[0] is False
assert h.set_manual("Alex", True) is None
assert h.classify("Alex") == (True, "handmatig: bot")
assert h.set_manual("talbot", False) is None            # 'Talbot' zou als bot gelden (eindigt op bot)
assert h.classify("Talbot") == (False, "handmatig: geen bot")
assert h.set_manual("alex", False) is True              # verplaatst, hoofdletters maken niet uit
assert h.classify("Alex") == (False, "handmatig: geen bot")
assert h.set_manual("Alex", None) is False
assert h.classify("Alex")[0] is False and h.classify("DX1ABC-BOT")[0]
assert h.manual_lists() == ([], ["talbot"])
assert h.is_other_bot(types.SimpleNamespace(sender_id=OWN)) is False       # eigen naam nooit
try: h.set_manual("", True); raise SystemExit("lege naam had moeten falen")
except ValueError: pass
try: h.set_manual("x" * 41, True); raise SystemExit("lange naam had moeten falen")
except ValueError: pass
for i in range(300): h.set_manual(f"n{i}", True)
try: h.set_manual("een-te-veel", True); raise SystemExit("volle lijst had moeten falen")
except ValueError: pass
print("1 lijsten en regels: OK")

# ---------- 2. het commando
bot = make_bot()


async def run(text, sender_is_admin=True):
    cmd = BotlistCommand(bot)
    out = []
    async def send_response(message, content): out.append(content); return True
    cmd.send_response = send_response
    msg = MeshMessage(content=text, sender_id="Alex", is_dm=True)
    await cmd.execute(msg)
    return out[0]

async def commands():
    assert BotlistCommand(bot).requires_admin_access() is True
    print(" ", await run("botlist"))
    r = await run("botlist add Echo Bot 2");           print(" ", r); assert "Echo Bot 2 telt nu altijd als bot" in r
    r = await run("!botlist not Talbot");              print(" ", r); assert "Talbot telt nooit als bot" in r
    r = await run("botlist");                          print(" ", r); assert "Bots: Echo Bot 2" in r and "Nooit bot: Talbot" in r
    r = await run("botlist check Talbot");             print(" ", r); assert "geen bot (handmatig: geen bot)" in r
    r = await run("botlist check DX1ABC-BOT");          print(" ", r); assert "= bot (woord bot in de naam)" in r
    r = await run("botlist not Echo Bot 2");           print(" ", r); assert "verplaatst" in r
    r = await run("botlist del Echo Bot 2");           print(" ", r); assert "uit de lijst gehaald" in r
    r = await run("botlist del Echo Bot 2");           print(" ", r); assert "stond niet in de lijsten" in r
    r = await run("botlijst toevoegen Sam");           print(" ", r); assert "Sam telt nu altijd als bot" in r
    r = await run("botlist add");                      print(" ", r); assert "naam ontbreekt" in r
    r = await run("botlist foo");                      print(" ", r); assert "gebruik botlist" in r
    r = await run("botlist add " + "x" * 50);          print(" ", r); assert "te lang" in r
    # persistente opslag: nieuwe ChannelHint op dezelfde db ziet de lijsten
    bot2 = make_bot(bot.db_manager)
    assert ChannelHint(bot2).classify("Sam") == (True, "handmatig: bot")
    assert ChannelHint(bot2).classify("Talbot") == (False, "handmatig: geen bot")
asyncio.run(commands())
print("2 commando: OK")

# ---------- 3. greeter begroet geen bots
import inspect
import_with_stubs(lambda: globals().__setitem__('GreeterCommand', __import__('modules.commands.greeter_command', fromlist=['GreeterCommand']).GreeterCommand))
src = inspect.getsource(GreeterCommand.should_execute)
assert "Never greet another bot" in src

g = GreeterCommand.__new__(GreeterCommand)          # zonder database-init
g.bot = make_bot(); g.logger = logging.getLogger("g")
g.enabled = True
g.is_channel_allowed = lambda m: True
g._is_rollout_active = lambda: False
g.has_been_greeted = lambda s, c: False
mk = lambda name: types.SimpleNamespace(is_dm=False, channel="Publiek", sender_id=name)
assert g.should_execute(mk("Nieuwe Mens")) is True          # gewone nieuwkomer wordt begroet
assert g.should_execute(mk("DX1ABC-BOT")) is False          # woord bot
assert g.should_execute(mk("Mesh|🤖")) is False             # emoji
get_channel_hint(g.bot).set_manual("Nieuwe Mens", True)
assert g.should_execute(mk("Nieuwe Mens")) is False         # handmatig gemarkeerd
get_channel_hint(g.bot).set_manual("Nieuwe Mens", False)
assert g.should_execute(mk("Nieuwe Mens")) is True
get_channel_hint(g.bot).set_manual("Talbot", False)
assert g.should_execute(mk("Talbot")) is True               # uitzondering: wel begroeten
# kapotte hint mag de greeter niet stuk maken
g.bot = types.SimpleNamespace(config=None, logger=logging.getLogger("x"), db_manager=None)
assert g.should_execute(mk("Iemand")) is True
print("3 greeter: OK")

# ---------- 4. mesh info als eigen bericht (begroeting eindigt op "|")
def parts(greeting, fmt="\n\nMesh info: {total_contacts} contacten, {companions} companions", include=True):
    g.greeting_message = greeting; g.mesh_info_format = fmt; g.include_mesh_info = include
    g.per_channel_greetings = False; g.channel_greetings = {}
    g._get_greeting_for_channel = lambda c: greeting
    info = {"total_contacts": 3779, "repeaters": 2659, "companions": 1120, "recent_activity_24h": 211}
    return asyncio.run(g._format_greeting_parts("Jan", None, info))
twee = "Hallo @[{sender}], welkom!\nTesten? #test."
assert parts(twee + " |") == ["Hallo @[Jan], welkom!\nTesten? #test.", "Mesh info: 3779 contacten, 1120 companions"], parts(twee + " |")
assert parts(twee + "|") == ["Hallo @[Jan], welkom!\nTesten? #test.", "Mesh info: 3779 contacten, 1120 companions"]
# zonder "|" op het eind: zoals upstream, vastgeplakt aan het laatste deel
assert parts(twee) == ["Hallo @[Jan], welkom!\nTesten? #test.\n\nMesh info: 3779 contacten, 1120 companions"]
assert parts("A | B") == ["A", "B\n\nMesh info: 3779 contacten, 1120 companions"]
# mesh info uit: "|" op het eind geeft geen leeg bericht
assert parts(twee + " |", include=False) == ["Hallo @[Jan], welkom!\nTesten? #test."]
# lege opmaak: geen leeg extra bericht
assert parts(twee + " |", fmt="") == ["Hallo @[Jan], welkom!\nTesten? #test."]
print("4 greeter mesh info eigen bericht: OK")

# ---------- 5. "|" splitst alleen als het niet in één bericht past
def sent(greeting, fmt, max_len=147):
    out = []
    async def chunked(message, parts): out.extend(parts); return True
    g.send_response_chunked = chunked
    g.get_max_message_length = lambda m: max_len
    g.get_greeted_users_count = lambda: 0
    g.greeting_message = greeting; g.mesh_info_format = fmt; g.include_mesh_info = True
    g._get_greeting_for_channel = lambda c: greeting
    async def info(): return {"total_contacts": 3779, "repeaters": 2659, "companions": 1120, "recent_activity_24h": 211}
    g._get_mesh_info = info
    assert asyncio.run(g._send_greeting(mk("Jan"))) is True
    return out
lang = "Hallo @[{sender}], welkom op de mesh! 👋\nWil je de bot testen? Dat kan in #test. |"
mesh = "Mesh info: {total_contacts} contacten, {repeaters} repeaters, {companions} companions, {recent_activity_24h} actief in 24u"
r = sent(lang, mesh)                                     # 80 + 79 bytes: past niet samen -> 2 berichten
assert r == ["Hallo @[Jan], welkom op de mesh! 👋\nWil je de bot testen? Dat kan in #test.",
             "Mesh info: 3779 contacten, 2659 repeaters, 1120 companions, 211 actief in 24u"], r
r = sent("Hoi @[{sender}]! | Test in #test. |", "Mesh: {total_contacts} contacten")   # kort: alles in één bericht
assert r == ["Hoi @[Jan]!\nTest in #test.\nMesh: 3779 contacten"], r
assert all(len(x.encode()) <= 130 for x in sent(lang, mesh, max_len=500))   # nooit boven 130, ook bij een korte botnaam
r = sent("Hoi @[{sender}]! | Test in #test. |", "Mesh: {total_contacts} contacten", max_len=30)   # lange botnaam: minder ruimte
assert r == ["Hoi @[Jan]!\nTest in #test.", "Mesh: 3779 contacten"], r
print("5 greeter: delen samen als het past: OK")
print("ALLES OK")
