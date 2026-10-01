"""Mailbox ('post'): leave a message, the bot DMs it when it hears the recipient again (a message or an advert after
the message was left), 7 days, limits. Runs in the simulated build tree: test_mailbox.py <tree>."""
import asyncio
import configparser
import contextlib
import importlib
import logging
import os
import sqlite3
import sys
import tempfile
import time
import types
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


M = imp("modules.mailbox")
PostCommand = imp("modules.commands.post_command").PostCommand
MS = imp("modules.service_plugins.mailbox_service")
MeshMessage = imp("modules.models").MeshMessage
tr = imp("modules.i18n").Translator("nl", "translations/", "local/translations")


class DB:
    def __init__(self):
        self.path = tempfile.mktemp()
        with self.connection() as c:
            c.execute("CREATE TABLE message_stats (timestamp INTEGER, sender_id TEXT)")
            c.execute("CREATE TABLE complete_contact_tracking (public_key TEXT, name TEXT, role TEXT, last_heard TIMESTAMP)")
            c.commit()

    @contextlib.contextmanager
    def connection(self):
        c = sqlite3.connect(self.path)
        try:
            yield c
        finally:
            c.close()


db = DB()
check(M.split_recipient("@[Dirk Jan] bel je me?") == ("Dirk Jan", "bel je me?") and M.split_recipient("Bob hoi daar") == ("Bob", "hoi daar")
      and M.split_recipient('"Dirk Jan" hoi') == ("Dirk Jan", "hoi"), "naam en tekst uit elkaar, ook met spaties")
T0 = time.time() - 3600
check(M.add(db, "Carol", None, "Bob", "tot zaterdag", "#bot", now=T0)[0] == "ok", "bericht bewaard")
check(M.add(db, "Carol", None, "carol", "x", "#bot", now=T0)[0] == "self", "niet aan jezelf")
M.add(db, "Carol", None, "Ann", "a", "#bot", now=T0); M.add(db, "Carol", None, "Eve", "e", "#bot", now=T0)
check(M.add(db, "Carol", None, "Dan", "d", "#bot", now=T0)[0] == "too_many", "hooguit 3 wachtende per afzender")
check([n for n, _ in M.waiting_from(db, "Carol", None)] == ["Bob", "Ann", "Eve"], "wat nog wacht")
check(M.due(db) == [], "niemand gehoord: niets te bezorgen")
with db.connection() as c:
    c.execute("INSERT INTO message_stats VALUES (?, 'Bob')", (int(T0) - 10,)); c.commit()
check(M.due(db) == [], "gehoord vóór het bericht telt niet")
with db.connection() as c:
    c.execute("INSERT INTO message_stats VALUES (?, 'bob')", (int(T0) + 60,))
    c.execute("INSERT INTO complete_contact_tracking VALUES ('a1', 'Ann', 'companion', datetime('now'))"); c.commit()
d = M.due(db)
check(sorted(m["to_name"] for m in d) == ["Ann", "Bob"], f"Bob schreef iets, Ann stuurde een advert ({[m['to_name'] for m in d]})")

# the service: DM when the recipient is on the radio (exactly one contact with that name)
sent = []


async def send_dm(key, text, **kw):
    sent.append((key, text))
    return True
cfg = configparser.ConfigParser(); cfg["Mailbox"] = {"enabled": "true"}; cfg["Bot"] = {"bot_name": "Test|🤖"}
bot = types.SimpleNamespace(config=cfg, db_manager=db, translator=tr, logger=logging.getLogger("m"), connected=True,
                            command_manager=types.SimpleNamespace(send_dm=send_dm),
                            meshcore=types.SimpleNamespace(contacts={"bb" * 32: {"public_key": "bb" * 32, "adv_name": "Bob"}}))
svc = MS.MailboxService(bot)
n = asyncio.run(svc.deliver())
check(n == 1 and sent[0][0] == "bb" * 32 and sent[0][1] == "📬 Post van Carol (1 u geleden): tot zaterdag", f"bezorgd per DM ({sent})")
check(asyncio.run(svc.deliver()) == 0 and len(sent) == 1, "één keer; Ann staat niet op de radio: wacht nog")
check([n for n, _ in M.waiting_from(db, "Carol", None)] == ["Ann", "Eve"], "Bob is weg uit de wachtlijst")
M.add(db, "Zed", None, "Old", "oud", "#bot", now=time.time() - 8 * 86400)
M.due(db)
with db.connection() as c:
    check(c.execute("SELECT expired IS NOT NULL FROM mailbox WHERE to_name='Old'").fetchone()[0] == 1, "na 7 dagen verlopen")


async def cmd(text, dm=False, name="Frank"):
    b = types.SimpleNamespace(config=cfg, db_manager=db, translator=tr, logger=logging.getLogger("p"),
                              command_manager=types.SimpleNamespace(monitor_channels=["#bot"]))
    c = PostCommand(b)
    out = []

    async def send(message, content, **kw):
        out.append(content)
        return True
    c.send_response = send
    await c.execute(MeshMessage(content=text, sender_id=name, sender_pubkey=("ff" * 32) if dm else None, is_dm=dm,
                                channel=None if dm else "#bot"))
    return out
r = asyncio.run(cmd("post @[Dirk Jan] bel je me?"))
check(r == ["Bewaard voor Dirk Jan. Ik stuur het per DM zodra ik Dirk Jan hoor (7 dagen geldig)."], f"post in een kanaal ({r})")
r = asyncio.run(cmd("post"))
check(r[0].startswith("Wacht nog: Dirk Jan ("), f"post zonder tekst: wat wacht ({r})")
r = asyncio.run(cmd("post Bob"))
check(r[0].startswith("Zo: post <naam> <tekst>"), "zonder tekst: uitleg")
r = asyncio.run(cmd("post Echo|🤖 hoi"))
check(r == ["Post voor een bot gaat niet."], "niet naar bots")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
