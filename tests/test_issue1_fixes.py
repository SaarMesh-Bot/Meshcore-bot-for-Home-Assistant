"""GitHub issue #1, second report: the Plugins switch saves at once, airplanes falls back to the radio's own position,
and path numbers its parts and can show fewer hops. Runs in the simulated build tree: test_issue1_fixes.py <tree>.
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


# ---------------------------------------------------------------- Plugins page: the switch saves at once
page = open(os.path.join(TREE, "modules/web_viewer/templates/plugins.html")).read()
i = page.index("toggle.addEventListener('change'")
check("this.save(plugin, toggle, inputs, saveBtn, status" in page[i:i + 400], "schakelaar op de Plugins-pagina slaat meteen op")

check('id="restart-banner"' in page and "this.showRestart(" in page and "/api/addon/restart" in page,
      "Plugins-pagina: balk met 'Restart now' als een wijziging een herstart nodig heeft")
app_src = open(os.path.join(TREE, "modules/web_viewer/app.py")).read()
check("'/api/addon/restart'" in app_src and "addons/self/restart" in app_src, "route die de add-on via de Supervisor herstart")

# ---------------------------------------------------------------- airplanes: the radio's position as fallback
Air = imp("modules.commands.airplanes_command").AirplanesCommand
tr = imp("modules.i18n").Translator("en", "translations/", "local/translations")


def air(bot_section, self_info):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = bot_section
    cmd = Air.__new__(Air)
    cmd.bot = types.SimpleNamespace(config=cfg, meshcore=types.SimpleNamespace(self_info=self_info))
    cmd.logger = logging.getLogger("air")
    return cmd._get_bot_location()


check(air({"bot_name": "X"}, {"adv_lat": 50.936, "adv_lon": 5.956}) == (50.936, 5.956), "airplanes zonder vaste plek: positie van de radio")
check(air({"bot_latitude": "51.1", "bot_longitude": "4.2"}, {"adv_lat": 50.9, "adv_lon": 5.9}) == (51.1, 4.2), "vaste plek (opties) gaat voor")
check(air({"bot_name": "X"}, {"adv_lat": 0.0, "adv_lon": 0.0}) is None, "radio zonder positie (0,0): geen plek")
check(air({"bot_name": "X"}, {}) is None, "niets bekend: geen plek (uitleg zoals voorheen)")

# ---------------------------------------------------------------- path: numbered parts, max hops shown
Path = imp("modules.commands.path_command").PathCommand
check(any(f["key"] == "max_hops_shown" for f in Path.settings_schema), "path-kaart heeft 'Max hops shown'")


def path_run(lines, max_hops=None, max_len=130):
    cfg = configparser.ConfigParser()
    cfg["Path_Command"] = {} if max_hops is None else {"max_hops_shown": str(max_hops)}
    cmd = Path.__new__(Path)
    cmd.bot = types.SimpleNamespace(config=cfg, translator=tr)
    cmd.logger = logging.getLogger("path")
    cmd.translate = lambda key, **kw: tr.translate(key, **kw)
    cmd.get_max_message_length = lambda m: max_len
    out = []

    async def send_response(message, content, **kw):
        out.append(content)
        return True

    async def prefix(message):
        return "@Piet "
    cmd.send_response = send_response
    cmd._format_path_reply_prefix = prefix
    real_sleep = asyncio.sleep

    async def no_sleep(_s):
        await real_sleep(0)
    imp("modules.commands.path_command").asyncio.sleep = no_sleep
    asyncio.run(cmd._send_path_response(types.SimpleNamespace(), "\n".join(lines)))
    imp("modules.commands.path_command").asyncio.sleep = real_sleep
    return out


hops = [f"{h:02x}: Repeater nummer {h} in een plaats" for h in range(1, 10)]
out = path_run(hops)
check(len(out) >= 2 and all(o.endswith(f"({n}/{len(out)})") for n, o in enumerate(out, 1)), f"lange route: delen genummerd ({[o[-6:] for o in out]})")
check(out[0].startswith("@Piet ") and all(len(o.encode()) <= 130 for o in out), "begroeting alleen in het eerste deel, elk deel past")
check(sum(o.count("Repeater nummer") for o in out) == 9, "geen hop kwijt")
out = path_run(hops, max_hops=3)
check(len(out) == 1 and out[0].count("Repeater nummer") == 3 and "+6 more hops" in out[0], f"max 3 hops: één bericht met '+6 more hops' ({out})")
out = path_run(hops[:2], max_hops=7)
check(len(out) == 1 and "(1/" not in out[0], "korte route: één bericht, geen nummer")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
