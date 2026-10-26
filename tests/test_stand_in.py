"""StandIn: "@[SaarMesh-Bot] /path" in a channel gets the note "Der SaarMesh-Bot macht Urlaub, ich bin seine Vertretung"
once per person (repeat_hours, survives a restart), at most once per channel per cooldown, never in a hint channel,
never for other bots, the bot itself or DMs; the mention is turned into one of this bot so the command runs; a message
that also mentions this bot or other people only is left alone; the hook sits in the patched message handler.
Runs in the simulated build tree."""
import asyncio
import configparser
import json
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
from modules import stand_in as si  # noqa: E402


class Meta:
    def __init__(self):
        self.d = {}

    def get_metadata(self, k):
        return self.d.get(k)

    def set_metadata(self, k, v):
        self.d[k] = v


def make(extra=None, meta=None, lang="de", hint_channels=()):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg["Bot"] = {"bot_name": "Saarlodri|\U0001F916"}
    cfg["Localization"] = {"language": lang}
    cfg["StandIn"] = dict({"enabled": "true", "names": "SaarMesh-Bot"}, **(extra or {}))
    bot = MagicMock()
    bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("si"), meta or Meta()
    bot.meshcore.self_info = {"name": "Saarlodri|\U0001F916"}
    sent = []

    async def send_channel_message(channel, text, **kw):
        sent.append((channel, text, kw.get("scope")))
        return True
    bot.command_manager.send_channel_message = send_channel_message
    bot.rate_limiter.time_until_next = lambda: 0.0
    bot._channel_hint = MagicMock()
    bot._channel_hint.is_other_bot = lambda m: "bot" in (m.sender_id or "").lower()
    bot._channel_hint.is_hint_channel = lambda m: (m.channel or "").lower() in hint_channels
    return si.StandIn(bot), sent


def msg(text="@[SaarMesh-Bot] /path", name="Ve", channel="#saarland", is_dm=False, scope=None):
    m = MeshMessage(content=text, sender_id=name, channel=None if is_dm else channel, is_dm=is_dm)
    m.reply_scope = scope
    return m


def handle(s, m):
    return asyncio.run(s.handle(m))


# --- the note and the rewritten command ---
s, sent = make()
m = msg(scope="#saarlorlux")
check(handle(s, m) == "note", "mention of the old bot: note sent")
check(len(sent) == 1 and sent[0][1].startswith("@[Ve] Der SaarMesh-Bot macht Urlaub, ich bin seine Vertretung"),
      f"German text with the sender's name: {sent[:1]}")
check(sent[0][0] == "#saarland" and sent[0][2] == "#saarlorlux", "in the same channel, with the incoming scope")
check(m.content == "@[Saarlodri|\U0001F916] /path", f"mention turned into this bot: {m.content!r}")

# same person again: no second note, but still answered
m2 = msg(text="@[saarmesh-bot] /path")
check(handle(s, m2) == "quiet" and len(sent) == 1, "same person shortly after: no second note (case does not matter)")
check(m2.content == "@[Saarlodri|\U0001F916] /path", "...but the command is still handed to this bot")

# channel cooldown: another person right after in the same channel gets no note
m3 = msg(name="Jean")
check(handle(s, m3) == "quiet" and len(sent) == 1, "channel cooldown: second person right after, no note")
s._last_channel.clear()
check(handle(s, msg(name="Jean")) == "note" and len(sent) == 2, "after the cooldown the next person gets the note")

# --- after the note the bot waits for its global send limit, so the answer is not dropped ---
s, sent = make()
waits = []
s.bot.rate_limiter.time_until_next = lambda: 0.4
_sleep = asyncio.sleep


async def fake_sleep(sec):
    waits.append(sec)
    await _sleep(0)
si.asyncio.sleep = fake_sleep
handle(s, msg())
check(waits and 0.4 <= waits[0] <= si.MAX_WAIT_S, f"waits for the send limit after the note: {waits}")
waits.clear()
handle(s, msg())
check(not waits, "no note (same person): no wait")
s, sent = make({"answer": "false"})
s.bot.rate_limiter.time_until_next = lambda: 0.4
handle(s, msg())
check(not waits, "answer off: no wait")
si.asyncio.sleep = _sleep

# --- left alone ---
s, sent = make()
check(handle(s, msg(text="/path")) == "none" and not sent, "no mention: nothing")
check(handle(s, msg(text="@[Peter] hallo")) == "none" and not sent, "someone else mentioned: nothing")
mm = msg(text="@[SaarMesh-Bot] @[Saarlodri|\U0001F916] /path")
check(handle(s, mm) == "none" and not sent and mm.content == "@[SaarMesh-Bot] @[Saarlodri|\U0001F916] /path",
      "this bot mentioned too: nothing, message unchanged")
check(handle(s, msg(is_dm=True)) == "none" and not sent, "DM: nothing")
check(handle(s, msg(name="Other-Bot")) == "none" and not sent, "another bot: nothing")
check(handle(s, msg(name="Saarlodri|\U0001F916")) == "none" and not sent, "the bot itself: nothing")
s, sent = make({"enabled": "false"})
check(handle(s, msg()) == "none" and not sent, "card off: nothing")

# hint channel: no note (the channel hint answers), mention still rewritten
s, sent = make(hint_channels=("public",))
mh = msg(channel="Public")
check(handle(s, mh) == "quiet" and not sent and mh.content.startswith("@[Saarlodri|"), "hint channel: no note")

# answer = false: note only, message unchanged
s, sent = make({"answer": "false"})
ma = msg()
check(handle(s, ma) == "note" and ma.content == "@[SaarMesh-Bot] /path", "answer off: note, message unchanged")

# own text, other language
s, sent = make({"message": "{sender}: {old} ist weg"})
handle(s, msg())
check(sent and sent[0][1] == "Ve: SaarMesh-Bot ist weg", "own text with {sender} and {old}")
s, sent = make(lang="en")
handle(s, msg())
check(sent and "on holiday" in sent[0][1], "English bot: English text")

# --- memory across a restart, repeat_hours ---
meta = Meta()
s, sent = make(meta=meta)
handle(s, msg())
s2, sent2 = make(meta=meta)
handle(s2, msg())
check(len(sent) == 1 and not sent2, "after a restart no second note within repeat_hours")
meta.d[si.NOTIFIED_KEY] = json.dumps({"ve": time.time() - 13 * 3600})
s3, sent3 = make(meta=meta)
handle(s3, msg())
check(len(sent3) == 1, "after 12 hours the note may come again")

# --- texts fit ---
for lang, text in si.DEFAULT_TEXTS.items():
    t = text.replace("{sender}", "A" * 20).replace("{old}", "SaarMesh-Bot")
    check(len(t.encode()) <= 130, f"{lang}: note fits a channel message with a 20-char name ({len(t.encode())} bytes)")

# --- the hook in the patched handler ---
src = open("modules/message_handler.py", encoding="utf-8").read()
check("await get_stand_in(self.bot).handle(message)" in src, "hook in message_handler.process_message")
check(src.index("get_stand_in(self.bot)") < src.index("if not self.should_process_message(message):"),
      "hook runs before the command matching")

if fails:
    print(f"{len(fails)} Fehler")
    sys.exit(1)
