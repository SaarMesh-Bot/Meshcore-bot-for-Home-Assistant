"""HashHint: a 1-byte path hash in a watched channel gets one tip per person (DM, else channel or nothing), 2/3 bytes
and unknown sizes get none, bots and the bot itself are skipped, the channel cooldown, max_hops, the memory across a
restart, the texts fit, and the hook sits in the patched message handler. Runs in the simulated build tree."""
import asyncio
import configparser
import logging
import os
import sys
import time
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


from modules.models import MeshMessage  # noqa: E402
from modules import hash_hint as hh  # noqa: E402


class Meta:
    def __init__(self):
        self.d = {}

    def get_metadata(self, k):
        return self.d.get(k)

    def set_metadata(self, k, v):
        self.d[k] = v


def make(extra=None, known=("Jean",), meta=None, lang="de"):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg["Bot"] = {"bot_name": "Saarlodri"}
    cfg["Localization"] = {"language": lang}
    cfg["HashHint"] = dict({"enabled": "true", "channels": "Public", "delay_seconds": "0"}, **(extra or {}))
    bot = MagicMock()
    bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("hh"), meta or Meta()
    dms, chan = [], []

    async def send_dm(recipient, text, **kw):
        if recipient not in known:
            return False
        dms.append((recipient, text))
        return True

    async def send_channel_message(channel, text, **kw):
        chan.append((channel, text))
        return True
    bot.command_manager.send_dm = send_dm
    bot.command_manager.send_channel_message = send_channel_message
    bot._channel_hint = MagicMock()
    bot._channel_hint.is_other_bot = lambda m: "bot" in (m.sender_id or "").lower()
    return hh.HashHint(bot), dms, chan, bot


def msg(name="Jean", plb=0x02, channel="Public", is_dm=False):
    m = MeshMessage(content="hallo", sender_id=name, channel=None if is_dm else channel, is_dm=is_dm)
    m.routing_info = None if plb is None else {"path_len_byte": plb, "bytes_per_hop": (plb >> 6) + 1}
    return m


async def drain(h):
    while h._tasks:
        await asyncio.gather(*list(h._tasks))


def run(h, *messages):
    async def go():
        for m in messages:
            h.observe(m)
        await drain(h)
    asyncio.run(go())


# --- reading the size ---
check(hh.sender_bytes_per_hop(msg(plb=0x03)) == 1, "path_len 0x03 = 1 byte, 3 hops")
check(hh.sender_bytes_per_hop(msg(plb=0x42)) == 2, "path_len 0x42 = 2 bytes")
check(hh.sender_bytes_per_hop(msg(plb=0x81)) == 3, "path_len 0x81 = 3 bytes")
check(hh.sender_bytes_per_hop(msg(plb=0x40)) == 2, "2 bytes also at 0 hops")
check(hh.sender_bytes_per_hop(msg(plb=None)) is None, "no matched packet = unknown")
m = msg(); m.routing_info = {"bytes_per_hop": 1}
check(hh.sender_bytes_per_hop(m) is None, "bytes_per_hop alone (may be a default) is not trusted")

# --- DM to a known contact, once ---
h, dms, chan, bot = make()
run(h, msg(), msg())
check(len(dms) == 1 and not chan, "1-byte sender gets one DM, the second message nothing")
check("1-Byte" in dms[0][1] and "Jean" in dms[0][1], "German DM text with the name")
run(h, msg(plb=0x41, name="Anna"), msg(plb=0x81, name="Bert"), msg(plb=None, name="Carl"))
check(len(dms) == 1 and not chan, "2 bytes, 3 bytes and unknown size: no tip")
run(h, msg(channel="#saarland", name="Dora"))
check(len(dms) == 1 and not chan, "channel that is not watched: no tip")
run(h, msg(name="Saarlodri"), msg(name="Echobot"))
check(len(dms) == 1 and not chan, "the bot itself and other bots: no tip")
run(h, msg(is_dm=True))
check(len(dms) == 1, "direct messages are never checked")

# --- fallback channel, cooldown ---
h, dms, chan, bot = make(known=())
run(h, msg(name="Emil"), msg(name="Fritz"))
check(len(chan) == 1 and chan[0][0] == "Public" and "@[Emil]" in chan[0][1], "no DM possible: tip in the channel")
check(not h.recently_notified("Fritz"), "channel cooldown skips Fritz without marking him")
h._last_channel.clear()
run(h, msg(name="Fritz"))
check(len(chan) == 2, "after the cooldown Fritz gets his tip")

h, dms, chan, bot = make({"dm_fallback": "none"}, known=())
run(h, msg(name="Gina"), msg(name="Gina"))
check(not chan and not dms and h.recently_notified("Gina"), "fallback none: nothing sent, not retried")

h, dms, chan, bot = make({"via": "channel"})
run(h, msg())
check(len(chan) == 1 and not dms, "via channel: tip in the channel even for a known contact")

# --- max hops ---
h, dms, chan, bot = make({"max_hops": "2"})
run(h, msg(plb=0x05))
check(not dms, "5 hops with max_hops 2: no tip")
run(h, msg(plb=0x01))
check(len(dms) == 1, "1 hop with max_hops 2: tip")

# --- off ---
h, dms, chan, bot = make({"enabled": "false"})
run(h, msg())
check(not dms and not chan, "card off: nothing")

# --- memory across a restart, repeat_days ---
meta = Meta()
h, dms, chan, bot = make(meta=meta)
run(h, msg())
h2, dms2, chan2, bot2 = make(meta=meta)
run(h2, msg())
check(len(dms) == 1 and not dms2, "after a restart the same person gets no second tip")
old = {"jean": time.time() - 31 * 86400}
import json  # noqa: E402
meta.d[hh.NOTIFIED_KEY] = json.dumps(old)
h3, dms3, chan3, bot3 = make(meta=meta)
run(h3, msg())
check(len(dms3) == 1, "after 30 days the tip may come again")

# --- texts fit ---
for lang, (dm, ch) in hh.DEFAULT_TEXTS.items():
    name = "A" * 20
    check(len(dm.replace("{sender}", name).encode()) <= 158, f"{lang}: DM text fits 158 bytes with a 20-char name")
    check(len(ch.replace("{sender}", name).encode()) <= 125, f"{lang}: channel text fits about 125 bytes")

# --- the hook in the patched handler ---
src = open("modules/message_handler.py", encoding="utf-8").read()
check("get_hash_hint(self.bot).observe(message)" in src, "hook in message_handler.process_message")

if fails:
    print(f"{len(fails)} fouten")
    sys.exit(1)
