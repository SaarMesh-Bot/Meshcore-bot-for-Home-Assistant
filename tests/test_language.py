"""English by default (GitHub issue #1): card texts in English, help texts and replies in the chosen language, ping with a
pointer to test, the standard hint texts per language, and bytes per hop in the test reply.

Runs in the simulated build tree: test_language.py <tree>.
"""
import ast
import asyncio
import configparser
import importlib
import logging
import os
import pathlib
import re
import sys
import types
from unittest.mock import MagicMock

HERE = pathlib.Path(__file__).resolve().parent
ADDON = HERE.parent / "meshcore-bot"
TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
logging.basicConfig(level=logging.ERROR)

fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def import_with_stubs(name):
    for _ in range(40):
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name.split(".")[0] == "modules":
                raise
            sys.modules[e.name] = MagicMock()
            sys.modules.setdefault(e.name.split(".")[0], MagicMock())
    raise SystemExit("te veel ontbrekende modules")


DUTCH = re.compile(r"\b(de|het|een|van|je|jouw|nabij|plaats|voor|bij|met|naam|ooit|dagen|uur|stemming|commando's?|opschonen|toont|"
                   r"actuele|dichtstbijzijnde|landelijk|berichten|repeaters? van)\b", re.I)

# ---------------------------------------------------------------- card texts (static)
cards, helps = {}, {}
for f in sorted((ADDON / "local_commands").glob("*.py")):
    src = f.read_text()
    for cls in [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)]:
        vals = {n.targets[0].id: n.value.value for n in cls.body
                if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}
        if "name" not in vals:
            continue
        cards[vals["name"]] = (vals.get("description", ""), vals.get("short_description", ""), f.stem, cls.name)
        fn = next((n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "get_help_text"), None)
        helps[vals["name"]] = ast.get_source_segment(src, fn) if fn else ""
dutch_cards = {n: d for n, (d, s, _f, _c) in cards.items() if DUTCH.search(d) or DUTCH.search(s)}
check(len(cards) >= 40 and not dutch_cards, f"kaartteksten van alle {len(cards)} eigen commando's in het Engels ({dutch_cards})")
untranslated = [n for n, h in helps.items() if "self.translate(" not in h]
check(not untranslated, f"elke eigen help-tekst gaat via translate ({untranslated})")

# ---------------------------------------------------------------- help texts per language
i18n = import_with_stubs("modules.i18n")
Translator = i18n.Translator


def make_bot(lang, sections=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Test|🤖", "timezone": "Europe/Amsterdam"}
    cfg["Localization"] = {"language": lang}
    for k, v in (sections or {}).items():
        cfg[k] = v
    bot = types.SimpleNamespace(config=cfg, logger=logging.getLogger("lang"), db_manager=MagicMock(), services={},
                                translator=Translator(lang, "translations/", "local/translations"), connected=True)
    bot.get_translator = lambda l: Translator(l, "translations/", "local/translations")
    bot.command_manager = types.SimpleNamespace(monitor_channels=["#test"], commands={})
    return bot


loaded = {}
for name, (_d, _s, stem, cls_name) in cards.items():
    try:
        mod = import_with_stubs(f"modules.commands.{stem}")
        loaded[name] = getattr(mod, cls_name)
    except Exception as e:  # noqa: BLE001
        check(False, f"{stem} laden: {e}")
for lang in ("en", "nl", "de", "fr", "da"):
    bot = make_bot(lang)
    bad, dutch = [], []
    for name, cls in loaded.items():
        try:
            text = cls(bot).get_help_text()
        except Exception as e:  # noqa: BLE001
            bad.append(f"{name}: {e}")
            continue
        if not text or text.startswith("commands."):
            bad.append(name)
        elif lang == "en" and DUTCH.search(text):
            dutch.append(name)
    check(not bad, f"help <commando> ({lang}): elke tekst bestaat ({bad})")
    if lang == "en":
        check(not dutch, f"help <commando> (en): geen Nederlands ({dutch})")

# ---------------------------------------------------------------- ping, help sample, own help text
ping_mod = import_with_stubs("modules.commands.ping_command")
for lang, want in (("en", "Pong! More info: type test"), ("nl", "Pong! Meer info: typ test"), ("de", "Pong! Mehr Infos: tippe test"),
                   ("fr", "Pong ! Plus d'infos : tapez test"), ("da", "Pong! Mere info: skriv test")):
    check(make_bot(lang).translator.translate("commands.ping.response") == want, f"ping ({lang}): {want}")
# the command itself (found 2026-09-30: without a ping keyword it sent nothing, the text above was never used)
pc = ping_mod.PingCommand(make_bot("nl"))
# since 2.51.2 the reply without a keyword is built in execute (modules/ping_info.py, test_ping_info.py)
check(pc.get_response_format() is None and "ping_info import reply" in open("modules/commands/ping_command.py").read(),
      "ping zonder keyword antwoordt echt (uitgebreid antwoord via ping_info)")
pk = ping_mod.PingCommand(make_bot("nl", {"Keywords": {"ping": '"Pong van mij!"'}}))
check(pk.get_response_format() == "Pong van mij!", "een eigen ping-keyword gaat voor")

cm_mod = import_with_stubs("modules.command_manager")
help_mod = import_with_stubs("modules.commands.help_command")
models = import_with_stubs("modules.models")
msg = models.MeshMessage(content="help", sender_id="Piet", channel="#test")
for lang, tail in (("en", "helpall=all"), ("nl", "helpall=alles"), ("de", "helpall=alle"), ("fr", "helpall=tout"), ("da", "helpall=alle")):
    b = make_bot(lang)
    hc = help_mod.HelpCommand(b)
    fake = types.SimpleNamespace(bot=b, commands={"help": hc, **{n: c(b) for n, c in list(loaded.items())[:5]}})
    text = cm_mod.CommandManager.get_general_help(fake, msg)
    check(text.startswith("Help: ") and text.endswith(tail), f"help zonder link ({lang}) eindigt op '{tail}': {text!r}")
b = make_bot("en", {"Help_Command": {"text": "Ask me anything, {sender}!", "list_url": "https://example.org/x"}})
fake = types.SimpleNamespace(bot=b, commands={"help": help_mod.HelpCommand(b)},
                             format_keyword_response=lambda t, m: t.replace("{sender}", m.sender_id))
check(cm_mod.CommandManager.get_general_help(fake, msg) == "Ask me anything, Piet!", "eigen help-tekst op de kaart wint (ook boven de link)")
check(any(f["key"] == "text" for f in help_mod.HelpCommand.settings_schema), "help-kaart heeft het veld 'Own help text'")
URL = "https://github.com/vipje/Meshcore-bot-for-Home-Assistant/blob/main/COMMANDS.md"
for lang, want in (("nl", URL), ("en", URL.replace("COMMANDS.md", "COMMANDS.en.md")), ("de", URL.replace("COMMANDS.md", "COMMANDS.en.md"))):
    b = make_bot(lang, {"Help_Command": {"list_url": URL}})
    fake = types.SimpleNamespace(bot=b, commands={"help": help_mod.HelpCommand(b)})
    text = cm_mod.CommandManager.get_general_help(fake, msg)
    check(want + " " in text and ("COMMANDS.en.md" in text) == (lang != "nl"), f"help-link in de taal van de schrijver ({lang}): {text!r}")
b = make_bot("en", {"Help_Command": {"list_url": "https://example.org/mylist"}})
text = cm_mod.CommandManager.get_general_help(types.SimpleNamespace(bot=b, commands={"help": help_mod.HelpCommand(b)}), msg)
check("https://example.org/mylist " in text, "een eigen link blijft zoals hij is")

# ---------------------------------------------------------------- standard hint texts per language
ch = import_with_stubs("modules.channel_hint")
for lang, word in (("en", "Happy to help"), ("nl", "We helpen"), ("de", "Gerne helfen"), ("fr", "Avec plaisir"), ("da", "Vi hjælper"), ("es", "Happy to help")):
    cfg = configparser.ConfigParser(); cfg["Localization"] = {"language": lang}
    check(ch.default_texts(cfg)[0].startswith(word), f"standaard verwijstekst ({lang}) begint met '{word}'")

# ---------------------------------------------------------------- bytes per hop in test
utils = import_with_stubs("modules.utils")
b = make_bot("en")
for bph, want_ci, want_ph in ((2, " | 2B/hop | ", "2"), (3, " | 3B/hop | ", "3"), (None, " | 1B/hop | ", "1"), (4, " | 1B/hop | ", "1")):
    m = models.MeshMessage(content="test", sender_id="Piet", channel="#test", path="4a,c2 (2 hops)", snr=7.5, rssi=-90,
                           routing_info={"bytes_per_hop": bph} if bph else None)
    out = utils.format_keyword_response_with_placeholders("{connection_info} ## {bytes_per_hop}", m, b)
    ci, ph = out.split(" ## ")
    ok = (want_ci in ci) if want_ci else ("B/hop" not in ci)
    check(ok and ph == want_ph and ci.startswith("4a,c2 (2 hops)"), f"test: bytes per hop {bph} -> {out!r}")

# bytes per hop read from the path when routing_info lacks it (the channel message of 2026-09-29)
for path, want in (("456b,6367,8e7c,29d4,c5f9 (5 hops)", " | 2B/hop | "), ("4a,c2 (2 hops)", " | 1B/hop | "),
                   ("a1b2c3,d4e5f6 (2 hops)", " | 3B/hop | "), ("Direct", None), ("4a,c2c2 (2 hops)", None)):
    m = models.MeshMessage(content="test", sender_id="Vipje", channel="#test", path=path, snr=10.25, rssi=-91, routing_info=None)
    out = utils.format_keyword_response_with_placeholders("{connection_info}", m, b)
    ok = (want in out) if want else ("B/hop" not in out)
    check(ok, f"test zonder routing_info, uit het pad: {path} -> {out!r}")

# the real `test` command builds its reply in base_command.py, not via the keyword route (live reply of 2026-09-29 03:56
# had no B/hop): the same result there, for the reply the user saw
test_mod = import_with_stubs("modules.commands.test_command")
tc = test_mod.TestCommand(b)
for path, ri, want in (("d5,b0,de,a9,c5 (5 hops)", None, "d5,b0,de,a9,c5 (5 hops) | 1B/hop | SNR: 11.25 dB"),
                       ("456b,6367 (2 hops)", None, "456b,6367 (2 hops) | 2B/hop | SNR"),
                       ("4a,c2 (2 hops)", {"bytes_per_hop": 3, "path_length": 2, "path_nodes": ["4a", "c2"]}, "4a,c2 (2 hops) | 3B/hop | "), ("Direct", None, None)):
    m = models.MeshMessage(content="test", sender_id="FOXtrott", channel="#test", path=path, snr=11.25, rssi=-91, routing_info=ri)
    ci = tc.build_enhanced_connection_info(m)
    ok = (want in ci) if want else ("B/hop" not in ci)
    check(ok, f"test-commando (base_command): {path} -> {ci!r}")
    check(tc.get_standard_placeholder_fields(m)["bytes_per_hop"] == (want.split("B/hop")[0][-1] if want else "?"),
          f"{{bytes_per_hop}} in commando-sjablonen: {path}")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
