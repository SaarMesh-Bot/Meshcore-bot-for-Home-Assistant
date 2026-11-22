"""Watchlist: a watched sender in a channel gets one DM per cooldown (to the configured key, added as a contact when
missing), Home Assistant is told every time, other senders, DMs, other channels and the bot itself are left alone,
the cooldown survives a restart, the default text fits, and the hook sits in the patched message handler.
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
from modules import watchlist as wl  # noqa: E402

KEY = "7cf26cbf9c9743f831dd91d7ea3f017e75ab771d6eebe19fe37bbcd47b7f3fa7"


class Meta:
    def __init__(self):
        self.d = {}

    def get_metadata(self, k):
        return self.d.get(k)

    def set_metadata(self, k, v):
        self.d[k] = v


def make(extra=None, meta=None, contacts=None):
    cfg = configparser.ConfigParser(interpolation=None)
    cfg["Bot"] = {"bot_name": "Saarlodri"}
    cfg["Watchlist"] = dict({"enabled": "true", "targets": f"Führerhauptquartier={KEY}, Troll",
                             "delay_seconds": "0"}, **(extra or {}))
    bot = MagicMock()
    bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("wl"), meta or Meta()
    known = dict(contacts or {})
    dms, added, notes = [], [], []

    async def send_dm(recipient, text, **kw):
        if recipient not in known and recipient not in {c.get("adv_name") for c in known.values()}:
            return False
        dms.append((recipient, text))
        return True

    async def add_contact(contact):
        added.append(contact)
        known[contact["public_key"]] = contact
        return MagicMock(type="OK")

    async def get_contacts(*a, **kw):
        return None
    bot.command_manager.send_dm = send_dm
    bot.meshcore.get_contact_by_key_prefix = lambda p: known.get(p)
    bot.meshcore.commands.add_contact = add_contact
    bot.meshcore.commands.get_contacts = get_contacts
    w = wl.Watchlist(bot)

    async def fake_notify(message, dm_result, tpl):
        notes.append((message.sender_id, dm_result))
    w._ha_notify = fake_notify
    return w, dms, added, notes


def msg(name="Führerhauptquartier", channel="Public", is_dm=False, content="hallo"):
    return MeshMessage(content=content, sender_id=name, channel=None if is_dm else channel, is_dm=is_dm)


async def drain(w):
    while w._tasks:
        await asyncio.gather(*list(w._tasks))


def run(w, *messages):
    async def go():
        for m in messages:
            w.observe(m)
            await drain(w)
    asyncio.run(go())


# --- the watched sender: contact added, DM to the key, HA told ---
w, dms, added, notes = make()
run(w, msg())
check(len(added) == 1 and added[0]["public_key"] == KEY, "unknown key is added as a contact")
check(len(dms) == 1 and dms[0][0] == KEY and dms[0][1] == wl.DEFAULT_DM, "DM goes to the key with the default text")
check(notes == [("Führerhauptquartier", "gesendet")], "HA is told, with the DM result")

# --- a second message: no second DM, HA told again ---
run(w, msg(content="nochmal"))
check(len(dms) == 1, "cooldown: no second DM")
check(len(notes) == 2 and notes[1][1].startswith("keine"), "HA told again, DM skipped")

# --- name matches case-insensitively as part of the sender name ---
w, dms, added, notes = make()
run(w, msg(name="führerhauptquartier 2"))
check(len(dms) == 1, "name matches case-insensitively as part of the sender name")

# --- known contact: not added again ---
w, dms, added, notes = make(contacts={KEY: {"public_key": KEY, "adv_name": "Führerhauptquartier"}})
run(w, msg())
check(not added and len(dms) == 1, "known contact is not added again")

# --- target without key and not a contact: no DM, HA told ---
w, dms, added, notes = make()
run(w, msg(name="Troll"))
check(not dms and not added and notes and notes[0][1].startswith("nicht"), "no key, no contact: no DM, HA still told")

# --- left alone: other senders, DMs, other channels, the bot itself ---
w, dms, added, notes = make({"channels": "Public"})
run(w, msg(name="Jean"), msg(is_dm=True), msg(channel="#saarland"), msg(name="Saarlodri"))
check(not dms and not notes, "other senders, DMs, other channels and the bot itself are left alone")

# --- disabled ---
w, dms, added, notes = make({"enabled": "false"})
run(w, msg())
check(not dms and not notes, "disabled: nothing happens")

# --- cooldown survives a restart, and expires ---
meta = Meta()
w, dms, *_ = make(meta=meta)
run(w, msg())
w2, dms2, *_ = make(meta=meta)
run(w2, msg())
check(len(dms) == 1 and not dms2, "after a restart no second DM within the cooldown")
meta.d[wl.DM_KEY] = json.dumps({"führerhauptquartier": time.time() - 25 * 3600})
w3, dms3, *_ = make(meta=meta)
run(w3, msg())
check(len(dms3) == 1, "after 24 h a DM may go out again")

# --- texts fit ---
check(len(wl.DEFAULT_DM.encode()) <= 158, "default DM text fits 158 bytes")
for tpl in wl.DEFAULT_TEMPLATES:
    check(len(tpl["text"].encode()) <= 158 and (bool(tpl["text"]) == tpl["dm"]), f"template {tpl['id']}: text fits, DM only with a text")

# --- templates per target ---
check(wl.parse_targets(f"A={KEY}=spam, B==ton, C")
      == [("a", "A", KEY, "spam"), ("b", "B", "", "ton"), ("c", "C", "", "")], "targets with key and template")
w, dms, added, notes = make({"targets": f"Führerhauptquartier={KEY}=spam"})


async def observe_and_drain(w, m):
    target = w.observe(m)
    await drain(w)
    return target
target = asyncio.run(observe_and_drain(w, msg()))
check(target is not None and w.ignores_commands(target), "template spam: commands ignored")
check(len(dms) == 1 and dms[0][1].startswith("Hallo, du sendest sehr viele"), "template spam: its DM text")
w, dms, added, notes = make({"targets": f"Führerhauptquartier={KEY}=beobachten"})
run(w, msg())
check(not dms and notes and notes[0][1] == "keine (Baustein ohne DM)", "template beobachten: no DM, HA still told")
w, dms, added, notes = make()
check(not w.ignores_commands(w.match(msg())) and not w.ignores_commands(None), "standard template name: commands answered")
w, dms, added, notes = make({"targets": f"Führerhauptquartier={KEY}=gibtsnicht", "default_template": "ton"})
run(w, msg())
check(len(dms) == 1 and "respektvollen Ton" in dms[0][1], "unknown template: the default template")

# --- own templates from config, '%' stored as \u0025 ---
own = '[{"id": "x", "label": "Eigen", "text": "100\\u0025 daneben, {sender}", "dm": true, "ignore": true}]'
w, dms, added, notes = make({"templates": own, "targets": f"Führerhauptquartier={KEY}"})
run(w, msg())
check(len(dms) == 1 and dms[0][1] == "100% daneben, Führerhauptquartier" and w.ignores_commands(w.match(msg())),
      "own templates from config (with % and {sender})")
w, *_ = make({"templates": "kaputt"})
check([t["id"] for t in w.templates] == [t["id"] for t in wl.DEFAULT_TEMPLATES], "broken templates: the defaults")

# --- the old single text (1.5.1-sm.24) is still used ---
w, dms, *_ = make({"message_dm": "Alter Text"})
run(w, msg())
check(dms and dms[0][1] == "Alter Text", "old message_dm: text of the default template")

# --- the hook in the patched handler ---
src = open("modules/message_handler.py", encoding="utf-8").read()
check("_wl.ignores_commands(_wl.observe(message))" in src, "hook in message_handler.process_message")
hook = src.index("_wl.ignores_commands(_wl.observe(message))")
check(src.index("if _wl_mute:", hook) < src.index("check_keywords(message)", hook), "muted senders stop before any command")

if fails:
    print(f"{len(fails)} fouten")
    sys.exit(1)
