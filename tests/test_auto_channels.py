"""AutoChannels (modules/channel_autocreate.py): missing hashtag channels are made in the first slot the radio really
reports empty; never private channels, never on a timeout (busy radio), never twice, and a channel the scan missed is
recognised instead of made again. Runs in the simulated build tree: test_auto_channels.py <tree>.
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


A = imp("modules.channel_autocreate")


class Radio:
    """The radio's real slots; `slow` slots do not answer (busy radio), slots past `size` give an error."""
    def __init__(self, slots, size=16, slow=()):
        self.slots, self.size, self.slow, self.asked = dict(slots), size, set(slow), []

    async def get_channel(self, idx):
        self.asked.append(idx)
        if idx in self.slow:
            await asyncio.sleep(10)
        if idx >= self.size:
            return types.SimpleNamespace(type="EventType.ERROR", payload={"reason": "out of range"})
        return types.SimpleNamespace(type="EventType.CHANNEL_INFO", payload={"channel_idx": idx, "channel_name": self.slots.get(idx, "")})


class CM:
    """The bot's channel cache, as the (maybe incomplete) scan left it."""
    def __init__(self, radio, cache):
        self.radio, self.max_channels, self.added = radio, 40, []
        self._channels_cache = {i: {"channel_name": n} for i, n in cache.items()}

    def get_channel_number(self, name):
        for i, c in self._channels_cache.items():
            if c["channel_name"].lower() == name.lower():
                return i
        return None

    async def add_hashtag_channel(self, idx, name):
        self.radio.slots[idx] = name
        self._channels_cache[idx] = {"channel_name": name}
        self.added.append((idx, name))
        return True


def bot(radio, cache, monitor="#test,#bot,Vip Bot", games=None, f1=False):
    cfg = configparser.ConfigParser()
    cfg["Channels"] = {"monitor_channels": monitor}
    if games is not None:
        cfg["GamesChannel"] = {"enabled": "true", "channel": games}
    if f1:
        cfg["F1"] = {"enabled": "true", "channel": "#f1"}
    return types.SimpleNamespace(config=cfg, channel_manager=CM(radio, cache), meshcore=types.SimpleNamespace(commands=radio))


log = logging.getLogger("t")
A.FETCH_TIMEOUT_S = 0.2

b = bot(Radio({0: "Public", 1: "#bot"}), {0: "Public", 1: "#bot"}, games="#games", f1=True)
check(A.wanted_channels(b) == ["#test", "#bot", "#games", "#f1"], f"gewenste kanalen: alleen hashtags, zonder dubbelen ({A.wanted_channels(b)})")
made = asyncio.run(A.ensure_channels(b, log))
check(made == ["#test", "#games", "#f1"] and b.channel_manager.added == [(2, "#test"), (3, "#games"), (4, "#f1")],
      f"ontbrekende kanalen in de eerste lege slots ({b.channel_manager.added})")
check(asyncio.run(A.ensure_channels(b, log)) == [] , "tweede keer: niets meer te doen")
r = b.meshcore.commands
before = len(r.asked)
asyncio.run(A.ensure_channels(b, log))
check(len(r.asked) == before, "niets ontbreekt: geen enkele vraag aan de radio")

# a channel asked for on the radar page ('Add to radio') is made too, the same safe way
meta = {"radar.add_to_radio": '["#bemesh"]'}
b2 = bot(Radio({0: "Public", 1: "#bot", 2: "#test"}), {0: "Public", 1: "#bot", 2: "#test"})
b2.db_manager = types.SimpleNamespace(get_metadata=lambda k: meta.get(k), set_metadata=lambda k, v: meta.__setitem__(k, v))
check(A.wanted_channels(b2) == ["#test", "#bot", "#bemesh"], f"verzoek van de radarpagina hoort bij de gewenste kanalen ({A.wanted_channels(b2)})")
check(asyncio.run(A.ensure_channels(b2, log)) == ["#bemesh"] and b2.channel_manager.added == [(3, "#bemesh")], "en wordt in een leeg slot gezet")

# the scan missed a channel (timeout counted as empty): recognised, not made twice
b = bot(Radio({0: "Public", 1: "#bot", 2: "#test"}), {0: "Public", 1: "#bot"})
check(asyncio.run(A.ensure_channels(b, log)) == [] and b.channel_manager.added == [], "kanaal dat de scan miste: niet nog eens aangemaakt")

# the radio does not answer about a slot: nothing is made
b = bot(Radio({0: "Public", 1: "#bot"}, slow={2}), {0: "Public", 1: "#bot"})
check(asyncio.run(A.ensure_channels(b, log)) == [] and b.channel_manager.added == [], "radio antwoordt niet: niets aangemaakt (later opnieuw)")

# a used slot the scan did not know is skipped, never overwritten
b = bot(Radio({0: "Public", 1: "#bot", 2: "Prive"}), {0: "Public", 1: "#bot"})
asyncio.run(A.ensure_channels(b, log))
check(b.channel_manager.added == [(3, "#test")] and b.meshcore.commands.slots[2] == "Prive", "bezet slot (privékanaal) nooit overschreven")

# private channel names are never made; a full radio stops cleanly
b = bot(Radio({0: "Public", 1: "#bot"}), {0: "Public", 1: "#bot"}, monitor="Geheim,#bot")
check(asyncio.run(A.ensure_channels(b, log)) == [], "privékanaal (zonder #) wordt nooit aangemaakt")
b = bot(Radio({0: "Public", 1: "#bot"}, size=2), {0: "Public", 1: "#bot"})
check(asyncio.run(A.ensure_channels(b, log)) == [] and b.channel_manager.added == [], "radio vol: niets, en geen fout")
off = bot(Radio({}), {}, games="#games")
off.config["GamesChannel"]["enabled"] = "false"
check("#games" not in A.wanted_channels(off), "spellenkaart uit: #games niet gevraagd")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
