"""Greeter with a dead-air delay (patch_greeter_delayed.py): the delayed greeting is really sent; someone greeted
before is still not greeted twice. Runs in the simulated build tree: test_greeter_delayed.py <tree>."""
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


from modules.commands.greeter_command import GreeterCommand  # noqa: E402
from modules.models import MeshMessage  # noqa: E402


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


def greeter(db):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Mesh|HA|🤖"}
    cfg["Channels"] = {"monitor_channels": "#test"}
    cfg["Greeter_Command"] = {"enabled": "true", "rollout_days": "0", "channels": "Publiek", "dead_air_delay_seconds": "1",
                              "defer_to_human_greeting": "false", "greeting": "Welkom {sender}!"}
    bot = MagicMock()
    bot.config, bot.logger, bot.db_manager = cfg, logging.getLogger("greeter"), db
    bot.channel_responses_enabled = True
    g = GreeterCommand(bot)
    g._is_rollout_active = lambda: False
    import modules.channel_hint as _ch
    _ch.get_channel_hint = lambda b: type("H", (), {"is_other_bot": lambda self, m: False})()   # a person, not a bot
    sent = []

    async def chunked(message, parts, **kw):
        sent.extend(parts)
        return True

    async def single(message, text, **kw):
        sent.append(text)
        return True
    g.send_response_chunked, g.send_response = chunked, single
    return g, sent


async def main():
    db = DBM(tempfile.mktemp())
    g, sent = greeter(db)
    msg = MeshMessage(content="Marco: Moin aus der Grafschaft", sender_id="Marco👋", channel="Publiek", is_dm=False)
    await g.execute(msg)
    check(g.has_been_greeted("Marco👋", "Publiek"), "op de lijst gezet (zoals in het log)")
    await asyncio.sleep(1.6)
    check(len(sent) >= 1, f"na de wachttijd: begroeting echt verstuurd ({sent})")
    sent.clear()
    await g.execute(MeshMessage(content="Marco: nog eens", sender_id="Marco👋", channel="Publiek", is_dm=False))
    await asyncio.sleep(1.6)
    check(sent == [], "tweede bericht van dezelfde persoon: niet nog eens begroet")
    # someone already on the list long ago: a scheduled greeting is still skipped
    with db.connection() as c:
        c.execute("UPDATE greeted_users SET greeted_at = datetime('now', '-2 days')")
        c.commit()
    task = asyncio.create_task(g._send_delayed_greeting(MeshMessage(content="x", sender_id="Marco👋", channel="Publiek", is_dm=False)))
    g.pending_greetings[("Marco👋", "Publiek")] = task
    await task
    check(sent == [], "eerder begroet (oude markering): niet nog eens")

asyncio.run(main())
print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
