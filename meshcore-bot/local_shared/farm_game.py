"""Farming Idle (the `farm` command): grow crops, harvest, process them in the workshop, sell, save in the bank, and level up
from 1 to 10. Played by direct message (the sender's key is the player, so nobody can play in your name); `farm top`
also works in a channel.

The numbers are tuned for the mesh: crops grow for hours, not minutes, so a player checks a few times a day and the
game costs little airtime. Every text goes through translate() (commands.farm.*); crop and product names are
commands.farm.crop.<id> / commands.farm.product.<id>.

Tables (in the bot's own database): farm_players, farm_fields, farm_items (produce, "seed:<crop>", products), farm_jobs
(the workshop).
"""
from __future__ import annotations

import math
import random
import time
from typing import Any, Callable, Optional

START_COINS = 200
START_FIELDS = 4
MAX_FIELDS = 12
MAX_KAS = 5          # greenhouse: -10% growing time per level
MAX_GROND = 5        # soil: +10% yield per level
MAX_WORKSHOP = 3     # jobs at the same time
SEED_CHANCE = 0.01   # per harvested unit: a free seed of that crop
BANK_RATE = 0.01     # per day
BANK_MAX_INTEREST = 500   # per day
EVENT_CHANCE = 0.08  # per harvest round
MAX_JOB_QTY = 5
MARKET_DAYS = 3      # an offer on the market lasts this long, then the goods go back to the seller's barn
MAX_OFFERS = 5       # per player
MAX_PRICE = 100000
SEASON_REWARDS = (1000, 500, 250)   # coins for places 1-3 at the end of a season (a calendar month)

# id: level, seed price, growing hours, units per harvest (min, max), harvests before the plant is spent, sell price, xp
CROPS = {
    "tomaat":     {"level": 1,  "seed": 20,   "hours": 1,  "units": (2, 4), "harvests": 10, "sell": 3,   "xp": 2},
    "aardbei":    {"level": 2,  "seed": 60,   "hours": 2,  "units": (3, 5), "harvests": 8,  "sell": 6,   "xp": 4},
    "pompoen":    {"level": 3,  "seed": 150,  "hours": 4,  "units": (1, 2), "harvests": 6,  "sell": 40,  "xp": 8},
    "wiet":       {"level": 4,  "seed": 300,  "hours": 6,  "units": (2, 3), "harvests": 5,  "sell": 50,  "xp": 12},
    "druif":      {"level": 5,  "seed": 500,  "hours": 8,  "units": (4, 6), "harvests": 8,  "sell": 45,  "xp": 16},
    "zonnebloem": {"level": 6,  "seed": 800,  "hours": 10, "units": (3, 5), "harvests": 6,  "sell": 95,  "xp": 20},
    "appel":      {"level": 7,  "seed": 1200, "hours": 12, "units": (5, 7), "harvests": 10, "sell": 100, "xp": 26},
    "hop":        {"level": 8,  "seed": 2000, "hours": 16, "units": (4, 6), "harvests": 8,  "sell": 210, "xp": 34},
    "koffie":     {"level": 9,  "seed": 3500, "hours": 20, "units": (3, 5), "harvests": 8,  "sell": 430, "xp": 42},
    "cacao":      {"level": 10, "seed": 6000, "hours": 24, "units": (3, 5), "harvests": 8,  "sell": 700, "xp": 50},
}
# id: crop, crop units needed, hours in the workshop, sell price, xp
PRODUCTS = {
    "soep":      {"crop": "tomaat",     "need": 4, "hours": 1,  "sell": 20,   "xp": 3},
    "pasta":     {"crop": "tomaat",     "need": 8, "hours": 3,  "sell": 45,   "xp": 6},
    "jam":       {"crop": "aardbei",    "need": 5, "hours": 2,  "sell": 50,   "xp": 6},
    "lantaarn":  {"crop": "pompoen",    "need": 1, "hours": 1,  "sell": 70,   "xp": 5},
    "joint":     {"crop": "wiet",       "need": 2, "hours": 1,  "sell": 170,  "xp": 10},
    "wijn":      {"crop": "druif",      "need": 6, "hours": 12, "sell": 480,  "xp": 20},
    "olie":      {"crop": "zonnebloem", "need": 3, "hours": 4,  "sell": 500,  "xp": 18},
    "taart":     {"crop": "appel",      "need": 4, "hours": 3,  "sell": 700,  "xp": 22},
    "bier":      {"crop": "hop",        "need": 3, "hours": 8,  "sell": 1100, "xp": 30},
    "espresso":  {"crop": "koffie",     "need": 2, "hours": 2,  "sell": 1500, "xp": 30},
    "chocolade": {"crop": "cacao",      "need": 2, "hours": 6,  "sell": 2400, "xp": 40},
}
# farm XP needed for level 1..10
LEVELS = [0, 50, 200, 500, 1100, 2200, 4000, 7000, 11500, 18000]

CROP_ALIASES = {
    "tomaat": ("tomaten", "tomato", "tomatoes", "tomate", "tomaten", "tomates"),
    "aardbei": ("aardbeien", "strawberry", "strawberries", "erdbeere", "erdbeeren", "fraise", "fraises"),
    "pompoen": ("pompoenen", "pumpkin", "pumpkins", "kürbis", "kurbis", "citrouille", "citrouilles"),
    "wiet": ("weed", "cannabis", "hennep", "hanf", "chanvre"),
    "druif": ("druiven", "grape", "grapes", "traube", "trauben", "raisin", "raisins"),
    "zonnebloem": ("zonnebloemen", "sunflower", "sunflowers", "sonnenblume", "sonnenblumen", "tournesol", "tournesols"),
    "appel": ("appels", "apple", "apples", "apfel", "äpfel", "pomme", "pommes"),
    "hop": ("hops", "hopfen", "houblon"),
    "koffie": ("coffee", "kaffee", "café", "cafe"),
    "cacao": ("cocoa", "kakao"),
}
PRODUCT_ALIASES = {
    "soep": ("tomatensoep", "soup", "suppe", "soupe"),
    "pasta": ("pastasaus", "nudeln", "pâtes", "pates"),
    "jam": ("confiture", "marmelade", "konfitüre"),
    "lantaarn": ("lantern", "jackolantern", "jack-o-lantern", "laterne", "lanterne"),
    "joint": ("joints",),
    "wijn": ("wine", "wein", "vin"),
    "olie": ("oil", "öl", "ol", "huile"),
    "taart": ("appeltaart", "pie", "kuchen", "tarte"),
    "bier": ("beer", "bière", "biere"),
    "espresso": ("expresso",),
    "chocolade": ("chocolate", "schokolade", "chocolat"),
}
UPGRADE_WORDS = {
    "veld": ("veld", "field", "feld", "champ"),
    "kas": ("kas", "greenhouse", "gewächshaus", "gewachshaus", "serre"),
    "grond": ("grond", "soil", "boden", "sol"),
    "werkplaats": ("werkplaats", "workshop", "werkstatt", "atelier"),
}

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS farm_players (
        pubkey TEXT PRIMARY KEY, name TEXT, coins INTEGER NOT NULL, bank INTEGER NOT NULL DEFAULT 0, bank_ts INTEGER,
        xp INTEGER NOT NULL DEFAULT 0, fields INTEGER NOT NULL, kas INTEGER NOT NULL DEFAULT 0, grond INTEGER NOT NULL DEFAULT 0,
        workshop INTEGER NOT NULL DEFAULT 1, created INTEGER, last_seen INTEGER)""",
    """CREATE TABLE IF NOT EXISTS farm_fields (
        pubkey TEXT NOT NULL, slot INTEGER NOT NULL, crop TEXT, planted INTEGER, left INTEGER,
        PRIMARY KEY (pubkey, slot))""",
    """CREATE TABLE IF NOT EXISTS farm_items (
        pubkey TEXT NOT NULL, item TEXT NOT NULL, qty INTEGER NOT NULL, PRIMARY KEY (pubkey, item))""",
    """CREATE TABLE IF NOT EXISTS farm_quests (
        pubkey TEXT NOT NULL, day TEXT NOT NULL, name TEXT, kind TEXT NOT NULL, item TEXT, need INTEGER NOT NULL,
        progress INTEGER NOT NULL DEFAULT 0, done INTEGER NOT NULL DEFAULT 0, reward_coins INTEGER NOT NULL,
        reward_xp INTEGER NOT NULL, PRIMARY KEY (pubkey, day))""",
    """CREATE TABLE IF NOT EXISTS farm_market (
        id INTEGER PRIMARY KEY AUTOINCREMENT, seller TEXT NOT NULL, seller_name TEXT, item TEXT NOT NULL,
        qty INTEGER NOT NULL, price INTEGER NOT NULL, created INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS farm_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, item TEXT NOT NULL, price INTEGER NOT NULL, qty INTEGER NOT NULL,
        filled INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL, expires INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS farm_season_base (
        season TEXT NOT NULL, pubkey TEXT NOT NULL, xp_start INTEGER NOT NULL, PRIMARY KEY (season, pubkey))""",
    """CREATE TABLE IF NOT EXISTS farm_season_results (
        season TEXT NOT NULL, rank INTEGER NOT NULL, pubkey TEXT NOT NULL, name TEXT, points INTEGER NOT NULL,
        reward INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (season, rank))""",
    """CREATE TABLE IF NOT EXISTS farm_market_sales (
        seller TEXT NOT NULL, text TEXT NOT NULL, ts INTEGER NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS farm_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, pubkey TEXT NOT NULL, product TEXT NOT NULL, qty INTEGER NOT NULL,
        ready INTEGER NOT NULL)""",
]


def level_of(xp: int) -> int:
    return max(i + 1 for i, need in enumerate(LEVELS) if xp >= need)


def next_level_xp(xp: int) -> Optional[int]:
    lvl = level_of(xp)
    return LEVELS[lvl] if lvl < len(LEVELS) else None


def field_price(fields: int) -> int:
    return 400 * 2 ** (fields - START_FIELDS)


def kas_price(k: int) -> int:
    return 1000 * 3 ** k


def grond_price(g: int) -> int:
    return 800 * 3 ** g


def workshop_price(w: int) -> int:
    return {1: 2000, 2: 10000}.get(w, 0)


def grow_seconds(crop: str, kas: int) -> int:
    return int(CROPS[crop]["hours"] * 3600 * (1 - 0.1 * kas))


def _match(word: str, table: dict) -> Optional[str]:
    w = (word or "").strip().lower()
    if not w:
        return None
    for key, aliases in table.items():
        if w == key or w in aliases:
            return key
    return None


def find_crop(word: str) -> Optional[str]:
    return _match(word, {k: CROP_ALIASES.get(k, ()) for k in CROPS})


def find_product(word: str) -> Optional[str]:
    return _match(word, {k: PRODUCT_ALIASES.get(k, ()) for k in PRODUCTS})


def find_upgrade(word: str) -> Optional[str]:
    return _match(word, UPGRADE_WORDS)


def _day(now: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(now))


SEASON_SETTINGS_KEY = "farm.season_settings"
SEASON_DEFAULTS = {"enabled": True, "length": "month", "rewards": list(SEASON_REWARDS), "start": "", "end": ""}
MAX_SEASON_DAYS = 366


def _date(text: str):
    import datetime as _dt
    try:
        return _dt.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


def season_of(now: float, length: str = "month", start: str = "", end: str = "") -> Optional[str]:
    """A season is a calendar month ('2026-10'), an ISO week ('2026-W40') or a chosen period
    ('2026-10-01_2026-11-15', start and end day included), local time. None: a chosen period that is not running."""
    import datetime as _dt
    if length == "custom":
        a, b, today = _date(start), _date(end), _dt.date.fromtimestamp(now)
        if a and b and a <= today <= b:
            return f"{a.isoformat()}_{b.isoformat()}"
        return None
    if length == "week":
        iso = _dt.date.fromtimestamp(now).isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return time.strftime("%Y-%m", time.localtime(now))


def season_start(season: str) -> float:
    import datetime as _dt
    if "_" in season:
        return time.mktime(_dt.date.fromisoformat(season.split("_")[0]).timetuple())
    if "-W" in season:
        year, week = season.split("-W")
        return time.mktime(_dt.date.fromisocalendar(int(year), int(week), 1).timetuple())
    return time.mktime(time.strptime(season + "-01", "%Y-%m-%d"))


def season_days_left(now: float, length: str = "month", end: str = "") -> int:
    import datetime as _dt
    if length == "custom":
        b = _date(end)
        if not b:
            return 0
        nxt = time.mktime((b + _dt.timedelta(days=1)).timetuple())
    elif length == "week":
        d = _dt.date.fromtimestamp(now)
        nxt = time.mktime((d + _dt.timedelta(days=7 - d.weekday())).timetuple())
    else:
        lt = time.localtime(now)
        nxt = time.mktime((lt.tm_year + (lt.tm_mon == 12), lt.tm_mon % 12 + 1, 1, 0, 0, 0, 0, 0, -1))
    return max(0, int((nxt - now) // 86400))


def left_text(seconds: float, translate: Callable) -> str:
    seconds = max(60, int(seconds))
    if seconds < 3600:
        return translate("commands.farm.left_min", m=math.ceil(seconds / 60))
    if seconds >= 48 * 3600:
        return translate("commands.farm.left_days", d=seconds // 86400)
    return translate("commands.farm.left_hours", h=seconds // 3600, m=f"{(seconds % 3600) // 60:02d}")


class FarmGame:
    def __init__(self, db: Any, crops_off: Optional[set] = None, rng: Optional[random.Random] = None):
        self.db = db
        self.crops_off = {c for c in (crops_off or set()) if c in CROPS}
        self.rng = rng or random.Random()
        with self.db.connection() as conn:
            for statement in SCHEMA:
                conn.execute(statement)
            conn.commit()

    # ------------------------------------------------------------------ players
    def _player(self, conn: Any, key: str) -> Optional[dict]:
        row = conn.execute("SELECT pubkey, name, coins, bank, bank_ts, xp, fields, kas, grond, workshop FROM farm_players "
                           "WHERE pubkey = ?", (key,)).fetchone()
        if not row:
            return None
        cols = ("pubkey", "name", "coins", "bank", "bank_ts", "xp", "fields", "kas", "grond", "workshop")
        return dict(zip(cols, row))

    def _save(self, conn: Any, p: dict) -> None:
        conn.execute("UPDATE farm_players SET name=?, coins=?, bank=?, bank_ts=?, xp=?, fields=?, kas=?, grond=?, workshop=?, "
                     "last_seen=? WHERE pubkey=?", (p["name"], p["coins"], p["bank"], p["bank_ts"], p["xp"], p["fields"], p["kas"],
                                                    p["grond"], p["workshop"], int(time.time()), p["pubkey"]))

    def _interest(self, p: dict, now: float) -> None:
        """Bank interest, per whole day since the last time, at most BANK_MAX_INTEREST a day."""
        last = p["bank_ts"] or int(now)
        days = int((now - last) // 86400)
        if days <= 0:
            if not p["bank_ts"]:
                p["bank_ts"] = int(now)
            return
        for _ in range(min(days, 365)):
            p["bank"] += min(BANK_MAX_INTEREST, int(p["bank"] * BANK_RATE))
        p["bank_ts"] = int(last + days * 86400)

    def _items(self, conn: Any, key: str) -> dict:
        return {i: q for i, q in conn.execute("SELECT item, qty FROM farm_items WHERE pubkey=? AND qty > 0", (key,))}

    def _add_item(self, conn: Any, key: str, item: str, qty: int) -> None:
        conn.execute("INSERT INTO farm_items (pubkey, item, qty) VALUES (?,?,?) ON CONFLICT(pubkey, item) DO UPDATE SET qty = qty + ?",
                     (key, item, qty, qty))
        conn.execute("DELETE FROM farm_items WHERE pubkey=? AND qty <= 0", (key,))

    def _fields(self, conn: Any, key: str) -> list:
        return [{"slot": s, "crop": c, "planted": t, "left": n}
                for s, c, t, n in conn.execute("SELECT slot, crop, planted, left FROM farm_fields WHERE pubkey=? ORDER BY slot", (key,))]

    def _collect_jobs(self, conn: Any, p: dict, now: float) -> tuple:
        """Finished workshop jobs go to the barn. Returns ({product: qty}, xp gained)."""
        done, xp = {}, 0
        for jid, product, qty in conn.execute("SELECT id, product, qty FROM farm_jobs WHERE pubkey=? AND ready <= ?",
                                              (p["pubkey"], int(now))).fetchall():
            self._add_item(conn, p["pubkey"], product, qty)
            done[product] = done.get(product, 0) + qty
            xp += PRODUCTS[product]["xp"] * qty
            conn.execute("DELETE FROM farm_jobs WHERE id=?", (jid,))
        p["xp"] += xp
        return done, xp

    # ------------------------------------------------------------------ daily task
    @staticmethod
    def task_of_day(now: float) -> str:
        """Today's task, the same for everyone: harvest, process or sell (from the date only)."""
        return random.Random(f"farm-task:{_day(now)}").choice(["harvest", "harvest", "process", "sell"])

    def _quest(self, conn: Any, p: dict, now: float) -> dict:
        """This player's goal for today's task: the task is the same for everyone, the amount grows with the level."""
        day = _day(now)
        cols = ("kind", "item", "need", "progress", "done", "reward_coins", "reward_xp")
        row = conn.execute(f"SELECT {', '.join(cols)} FROM farm_quests WHERE pubkey=? AND day=?", (p["pubkey"], day)).fetchone()
        if row:
            return dict(zip(cols, row))
        lvl = level_of(p["xp"])
        kind = self.task_of_day(now)
        need = {"harvest": 6 + 4 * lvl, "process": 1 + lvl // 3, "sell": 100 * lvl}[kind]
        q = {"kind": kind, "item": None, "need": need, "progress": 0, "done": 0, "reward_coins": 40 * lvl + 60, "reward_xp": 8 * lvl}
        conn.execute("INSERT INTO farm_quests (pubkey, day, name, kind, item, need, progress, done, reward_coins, reward_xp) "
                     "VALUES (?,?,?,?,NULL,?,0,0,?,?)", (p["pubkey"], day, p["name"], kind, need, q["reward_coins"], q["reward_xp"]))
        return q

    def _quest_progress(self, conn: Any, p: dict, kind: str, item: Optional[str], amount: int, now: float, translate: Callable) -> str:
        """Count towards today's task; returns the 'task done' text when it just got done (reward paid), else ''."""
        q = self._quest(conn, p, now)
        if q["done"] or q["kind"] != kind or (q["item"] and q["item"] != item) or amount <= 0:
            return ""
        progress = min(q["need"], q["progress"] + amount)
        done = progress >= q["need"]
        conn.execute("UPDATE farm_quests SET progress=?, done=?, name=? WHERE pubkey=? AND day=?",
                     (progress, 1 if done else 0, p["name"], p["pubkey"], _day(now)))
        if not done:
            return ""
        p["coins"] += q["reward_coins"]
        p["xp"] += q["reward_xp"]
        return translate("commands.farm.quest_completed", coins=q["reward_coins"], xp=q["reward_xp"])

    def quest(self, key: str, name: str, translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            p["name"] = name[:40] or p["name"]
            q = self._quest(conn, p, now)
            conn.commit()
        if q["done"]:
            return [translate("commands.farm.quest_done_today")]
        return [translate(f"commands.farm.quest.{q['kind']}", need=q["need"], progress=q["progress"],
                          coins=q["reward_coins"], xp=q["reward_xp"])]

    # ------------------------------------------------------------------ market
    def _expire_offers(self, conn: Any, now: float) -> None:
        for oid, seller, item, qty in conn.execute("SELECT id, seller, item, qty FROM farm_market WHERE created < ?",
                                                   (int(now - MARKET_DAYS * 86400),)).fetchall():
            self._add_item(conn, seller, item, qty)
            conn.execute("DELETE FROM farm_market WHERE id=?", (oid,))

    def _goods_name(self, item: str, translate: Callable) -> str:
        if item.startswith("seed:"):
            return translate("commands.farm.seed_item", n="", crop=translate(f"commands.farm.crop.{item[5:]}")).strip()
        return translate(f"commands.farm.crop.{item}") if item in CROPS else translate(f"commands.farm.product.{item}")

    def market(self, translate: Callable, now: Optional[float] = None, limit: int = 8) -> list:
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            self._expire_offers(conn, now)
            rows = conn.execute("SELECT id, seller_name, item, qty, price FROM farm_market ORDER BY item, price LIMIT ?", (limit,)).fetchall()
            orders = self._open_orders(conn, now)
            conn.commit()
        from .f1_data import pack
        out = []
        if orders:
            out += pack(translate("commands.farm.orders_head"), [
                translate("commands.farm.order_item", qty=o["qty"] - o["filled"], item=self._goods_name(o["item"], translate), price=o["price"])
                for o in orders[:6]])
        if rows:
            out += pack(translate("commands.farm.market_head"), [
                translate("commands.farm.market_item", id=i, qty=q, item=self._goods_name(it, translate), price=pr, name=n or "?")
                for i, n, it, q, pr in rows])
        return out or [translate("commands.farm.market_empty")]

    # ------------------------------------------------------------------ the market buys (orders set on the dashboard)
    def _open_orders(self, conn: Any, now: float) -> list:
        cols = ("id", "item", "price", "qty", "filled", "expires")
        return [dict(zip(cols, r)) for r in conn.execute(
            "SELECT id, item, price, qty, filled, expires FROM farm_orders WHERE filled < qty AND expires > ? ORDER BY price DESC",
            (int(now),)).fetchall()]

    def add_order(self, item: str, price: int, qty: int, days: int, now: Optional[float] = None) -> int:
        """A buy order of the market (dashboard): the market pays `price` per piece for up to `qty` pieces."""
        now = time.time() if now is None else now
        if item not in CROPS and item not in PRODUCTS:
            raise ValueError("unknown item")
        price, qty, days = max(1, min(MAX_PRICE, int(price))), max(1, min(10000, int(qty))), max(1, min(30, int(days)))
        with self.db.connection() as conn:
            cur = conn.execute("INSERT INTO farm_orders (item, price, qty, filled, created, expires) VALUES (?,?,?,0,?,?)",
                               (item, price, qty, int(now), int(now + days * 86400)))
            conn.commit()
            return cur.lastrowid

    def delete_order(self, oid: int) -> bool:
        with self.db.connection() as conn:
            n = conn.execute("DELETE FROM farm_orders WHERE id=?", (int(oid),)).rowcount
            conn.commit()
        return n > 0

    def deliver(self, key: str, name: str, word: str, count: Optional[int], translate: Callable, now: Optional[float] = None) -> list:
        """Sell to the market's buy order for this item (the best price first): paid at once."""
        now = time.time() if now is None else now
        item = find_crop(word) or find_product(word)
        if item is None:
            return [translate("commands.farm.deliver_usage")]
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            orders = [o for o in self._open_orders(conn, now) if o["item"] == item]
            if not orders:
                conn.commit()
                return [translate("commands.farm.no_order", item=self._goods_name(item, translate))]
            have = self._items(conn, key).get(item, 0)
            want = min(have, count) if count else have
            if want <= 0:
                conn.commit()
                return [translate("commands.farm.not_in_barn", have=have, item=self._goods_name(item, translate))]
            self._interest(p, now)
            delivered, paid = 0, 0
            for o in orders:
                take = min(want - delivered, o["qty"] - o["filled"])
                if take <= 0:
                    break
                conn.execute("UPDATE farm_orders SET filled = filled + ? WHERE id=?", (take, o["id"]))
                delivered += take
                paid += take * o["price"]
            self._add_item(conn, key, item, -delivered)
            p["coins"] += paid
            p["name"] = name[:40] or p["name"]
            quest_text = self._quest_progress(conn, p, "sell", None, paid, now, translate)
            self._save(conn, p)
            conn.commit()
        return [translate("commands.farm.delivered", qty=delivered, item=self._goods_name(item, translate), coins=paid,
                          total=p["coins"]) + quest_text]

    def offer(self, key: str, name: str, word: str, qty: Optional[int], price: Optional[int], translate: Callable,
              now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        item = find_crop(word) or find_product(word)
        if item is None or not qty or not price:
            return [translate("commands.farm.offer_usage")]
        qty, price = max(1, int(qty)), max(1, min(MAX_PRICE, int(price)))
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            self._expire_offers(conn, now)
            mine = conn.execute("SELECT COUNT(*) FROM farm_market WHERE seller=?", (key,)).fetchone()[0]
            if mine >= MAX_OFFERS:
                conn.commit()
                return [translate("commands.farm.offer_limit", n=mine)]
            have = self._items(conn, key).get(item, 0)
            if have < qty:
                conn.commit()
                return [translate("commands.farm.not_in_barn", have=have, item=self._goods_name(item, translate))]
            self._add_item(conn, key, item, -qty)
            cur = conn.execute("INSERT INTO farm_market (seller, seller_name, item, qty, price, created) VALUES (?,?,?,?,?,?)",
                               (key, name[:40] or p["name"], item, qty, price, int(now)))
            oid = cur.lastrowid
            conn.commit()
        return [translate("commands.farm.offered", id=oid, qty=qty, item=self._goods_name(item, translate), price=price, days=MARKET_DAYS)]

    def buy(self, key: str, name: str, oid_word: str, translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        oid_word = (oid_word or "").lstrip("#")
        if not oid_word.isdigit():
            return [translate("commands.farm.buy_usage")]
        oid = int(oid_word)
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            self._expire_offers(conn, now)
            row = conn.execute("SELECT seller, seller_name, item, qty, price FROM farm_market WHERE id=?", (oid,)).fetchone()
            if not row:
                conn.commit()
                return [translate("commands.farm.no_offer", id=oid)]
            seller, seller_name, item, qty, price = row
            if seller == key:
                conn.commit()
                return [translate("commands.farm.own_offer", id=oid)]
            self._interest(p, now)
            total = qty * price
            if total > p["coins"]:
                conn.commit()
                return [translate("commands.farm.no_money", need=total, coins=p["coins"])]
            p["coins"] -= total
            p["name"] = name[:40] or p["name"]
            self._add_item(conn, key, item, qty)
            conn.execute("UPDATE farm_players SET coins = coins + ? WHERE pubkey=?", (total, seller))
            conn.execute("DELETE FROM farm_market WHERE id=?", (oid,))
            conn.execute("INSERT INTO farm_market_sales (seller, text, ts) VALUES (?,?,?)",
                         (seller, f"{qty}|{item}|{p['name']}|{total}", int(now)))
            self._save(conn, p)
            conn.commit()
        return [translate("commands.farm.bought", qty=qty, item=self._goods_name(item, translate), name=seller_name or "?",
                          coins=total, left=p["coins"])]

    def withdraw(self, key: str, oid_word: str, translate: Callable) -> list:
        oid_word = (oid_word or "").lstrip("#")
        if not oid_word.isdigit():
            return [translate("commands.farm.buy_usage")]
        with self.db.connection() as conn:
            row = conn.execute("SELECT item, qty FROM farm_market WHERE id=? AND seller=?", (int(oid_word), key)).fetchone()
            if not row:
                return [translate("commands.farm.no_offer", id=oid_word)]
            self._add_item(conn, key, row[0], row[1])
            conn.execute("DELETE FROM farm_market WHERE id=?", (int(oid_word),))
            conn.commit()
        return [translate("commands.farm.withdrawn", qty=row[1], item=self._goods_name(row[0], translate))]

    def _market_news(self, conn: Any, key: str, translate: Callable) -> str:
        """What sold on the market since the seller last looked (shown once in the status)."""
        rows = conn.execute("SELECT text FROM farm_market_sales WHERE seller=? ORDER BY ts", (key,)).fetchall()
        if not rows:
            return ""
        conn.execute("DELETE FROM farm_market_sales WHERE seller=?", (key,))
        parts = []
        for (t,) in rows[:4]:
            qty, item, buyer, total = t.split("|", 3)
            parts.append(translate("commands.farm.market_sale", qty=qty, item=self._goods_name(item, translate), name=buyer, coins=total))
        return translate("commands.farm.market_sold", items=", ".join(parts))

    def has_player(self, key: str) -> bool:
        with self.db.connection() as conn:
            return self._player(conn, key.lower()) is not None

    def available(self, level: int) -> list:
        return [c for c, v in CROPS.items() if v["level"] <= level and c not in self.crops_off]

    # ------------------------------------------------------------------ actions (each returns a list of texts)
    def start(self, key: str, name: str, translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            if self._player(conn, key):
                return [translate("commands.farm.already")]
            conn.execute("INSERT INTO farm_players (pubkey, name, coins, bank, bank_ts, xp, fields, created, last_seen) "
                         "VALUES (?,?,?,0,?,0,?,?,?)", (key, name[:40], START_COINS, int(now), START_FIELDS, int(now), int(now)))
            for slot in range(1, START_FIELDS + 1):
                conn.execute("INSERT INTO farm_fields (pubkey, slot, crop, planted, left) VALUES (?,?,NULL,NULL,0)", (key, slot))
            conn.commit()
        return [translate("commands.farm.started", name=name, coins=START_COINS, fields=START_FIELDS,
                          crop=translate("commands.farm.crop.tomaat"))]

    def status(self, key: str, name: str, translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            p["name"] = name[:40] or p["name"]
            self._interest(p, now)
            done, _xp = self._collect_jobs(conn, p, now)
            fields = self._fields(conn, key)
            jobs = conn.execute("SELECT product, qty, ready FROM farm_jobs WHERE pubkey=? ORDER BY ready", (key,)).fetchall()
            news = self._market_news(conn, key, translate)
            self._save(conn, p)
            conn.commit()
        lvl, nxt = level_of(p["xp"]), next_level_xp(p["xp"])
        head = translate("commands.farm.status_head", level=lvl, xp=p["xp"], next=nxt if nxt else "max", coins=p["coins"], bank=p["bank"])
        ready: dict = {}
        growing = []
        empty = 0
        for f in fields:
            if not f["crop"]:
                empty += 1
                continue
            due = f["planted"] + grow_seconds(f["crop"], p["kas"])
            if due <= now:
                ready[f["crop"]] = ready.get(f["crop"], 0) + 1
            else:
                growing.append((due, f["crop"], f["left"]))
        pieces = [translate("commands.farm.ready_piece", n=n, crop=translate(f"commands.farm.crop.{c}")) for c, n in ready.items()]
        first: dict = {}
        for due, crop, left in sorted(growing):
            n, earliest, most = first.get(crop, (0, due, 0))
            first[crop] = (n + 1, earliest, max(most, left or 0))
        for crop, (n, due, most) in sorted(first.items(), key=lambda kv: kv[1][1])[:4]:
            pieces.append(translate("commands.farm.growing_piece", n=n, crop=translate(f"commands.farm.crop.{crop}"),
                                    left=left_text(due - now, translate)) + translate("commands.farm.times_left", n=most))
        if len(first) > 4:
            pieces.append(translate("commands.farm.more_growing", n=sum(v[0] for v in list(first.values())[4:])))
        if empty:
            pieces.append(translate("commands.farm.empty_piece", n=empty))
        for product, qty, ready_ts in jobs[:2]:
            pieces.append(translate("commands.farm.job_piece", n=qty, product=translate(f"commands.farm.product.{product}"),
                                    left=left_text(ready_ts - now, translate)))
        out = [head + " | ".join(pieces)]
        if done:
            out.append(self._done_text(done, translate))
        if news:
            out.append(news)
        return out

    def _done_text(self, done: dict, translate: Callable) -> str:
        return translate("commands.farm.jobs_done", items=", ".join(
            f"{q} {translate(f'commands.farm.product.{i}')}" for i, q in done.items()))

    def shop(self, key: str, translate: Callable, word: str = "", count: Optional[int] = None,
             now: Optional[float] = None) -> list:
        """The seed shop: the list (farm winkel), one crop's details (farm winkel tomaat) or buying seeds for the barn
        (farm winkel tomaat 5 / farm zaad tomaat 5)."""
        if word:
            crop = find_crop(word)
            if crop is None:
                return [translate("commands.farm.unknown_crop", q=word[:20])]
            if count:
                return self.buy_seeds(key, crop, count, translate, now)
            return [self.crop_info(crop, translate)]
        with self.db.connection() as conn:
            p = self._player(conn, key)
        lvl = level_of(p["xp"]) if p else 1
        pieces = [translate("commands.farm.shop_item", crop=translate(f"commands.farm.crop.{c}"), price=CROPS[c]["seed"],
                            hours=CROPS[c]["hours"], times=CROPS[c]["harvests"]) for c in self.available(lvl)]
        locked = [c for c, v in CROPS.items() if v["level"] > lvl and c not in self.crops_off]
        if locked:
            pieces.append(translate("commands.farm.shop_next", level=CROPS[locked[0]]["level"],
                                    crop=translate(f"commands.farm.crop.{locked[0]}")))
        from .f1_data import pack
        return pack(translate("commands.farm.shop_head"), pieces) + [translate("commands.farm.shop_hint")]

    def crop_info(self, crop: str, translate: Callable) -> str:
        c = CROPS[crop]
        made = [translate(f"commands.farm.product.{pr}") for pr, v in PRODUCTS.items() if v["crop"] == crop]
        return translate("commands.farm.crop_info", crop=translate(f"commands.farm.crop.{crop}"), level=c["level"], price=c["seed"],
                         hours=c["hours"], lo=c["units"][0], hi=c["units"][1], times=c["harvests"], sell=c["sell"],
                         made=", ".join(made) or "-")

    def buy_seeds(self, key: str, crop: str, count: int, translate: Callable, now: Optional[float] = None) -> list:
        """Buy seeds for the barn: sow them later (farm zaai uses own seed first) or offer them on the market."""
        now = time.time() if now is None else now
        cname = translate(f"commands.farm.crop.{crop}")
        if crop in self.crops_off:
            return [translate("commands.farm.crop_off", crop=cname)]
        count = max(1, min(int(count), 100))
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            if CROPS[crop]["level"] > level_of(p["xp"]):
                return [translate("commands.farm.crop_locked", crop=cname, level=CROPS[crop]["level"])]
            self._interest(p, now)
            cost = count * CROPS[crop]["seed"]
            if cost > p["coins"]:
                return [translate("commands.farm.no_money", need=cost, coins=p["coins"])]
            p["coins"] -= cost
            self._add_item(conn, key, f"seed:{crop}", count)
            have = self._items(conn, key).get(f"seed:{crop}", 0)
            self._save(conn, p)
            conn.commit()
        return [translate("commands.farm.seeds_bought", n=count, crop=cname, cost=cost, have=have, coins=p["coins"])]

    def clear(self, key: str, word: str, translate: Callable) -> list:
        """Clear fields (a crop, a field number or everything) to sow something else; the plants are lost."""
        w = (word or "").strip().lower()
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            fields = [f for f in self._fields(conn, key) if f["crop"]]
            if w in ("alles", "all", "alle", "tout"):
                chosen = fields
            elif w.isdigit():
                chosen = [f for f in fields if f["slot"] == int(w)]
            else:
                crop = find_crop(w) if w else None
                if crop is None:
                    return [translate("commands.farm.clear_usage")]
                chosen = [f for f in fields if f["crop"] == crop]
            if not chosen:
                return [translate("commands.farm.clear_none")]
            for f in chosen:
                conn.execute("UPDATE farm_fields SET crop=NULL, planted=NULL, left=0 WHERE pubkey=? AND slot=?", (key, f["slot"]))
            conn.commit()
        return [translate("commands.farm.cleared", n=len(chosen))]

    def sow(self, key: str, name: str, word: str, count: Optional[int], translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        crop = find_crop(word)
        if crop is None:
            return [translate("commands.farm.unknown_crop", q=(word or "")[:20])]
        cname = translate(f"commands.farm.crop.{crop}")
        if crop in self.crops_off:
            return [translate("commands.farm.crop_off", crop=cname)]
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            if CROPS[crop]["level"] > level_of(p["xp"]):
                return [translate("commands.farm.crop_locked", crop=cname, level=CROPS[crop]["level"])]
            self._interest(p, now)
            empty = [f["slot"] for f in self._fields(conn, key) if not f["crop"]]
            if not empty:
                return [translate("commands.farm.no_empty")]
            n = len(empty) if count is None else max(1, min(count, len(empty)))
            items = self._items(conn, key)
            own = min(n, items.get(f"seed:{crop}", 0))
            cost = (n - own) * CROPS[crop]["seed"]
            if cost > p["coins"]:
                affordable = own + p["coins"] // CROPS[crop]["seed"]
                if affordable < 1:
                    return [translate("commands.farm.no_money", need=cost, coins=p["coins"])]
                n = affordable
                cost = (n - own) * CROPS[crop]["seed"]
            p["coins"] -= cost
            if own:
                self._add_item(conn, key, f"seed:{crop}", -own)
            for slot in empty[:n]:
                conn.execute("UPDATE farm_fields SET crop=?, planted=?, left=? WHERE pubkey=? AND slot=?",
                             (crop, int(now), CROPS[crop]["harvests"], key, slot))
            p["name"] = name[:40] or p["name"]
            self._save(conn, p)
            conn.commit()
        return [translate("commands.farm.sown", n=n, crop=cname, seeds=own, left=left_text(grow_seconds(crop, p["kas"]), translate),
                          coins=p["coins"])]

    def harvest(self, key: str, name: str, translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            self._interest(p, now)
            level_before = level_of(p["xp"])
            done, _ = self._collect_jobs(conn, p, now)
            fields = self._fields(conn, key)
            ready = [f for f in fields if f["crop"] and f["planted"] + grow_seconds(f["crop"], p["kas"]) <= now]
            if not ready:
                growing = [f["planted"] + grow_seconds(f["crop"], p["kas"]) for f in fields if f["crop"]]
                out = [translate("commands.farm.nothing_ready", left=left_text(min(growing) - now, translate))
                       if growing else translate("commands.farm.nothing_planted")]
                if done:
                    self._save(conn, p)
                    conn.commit()
                    out.append(self._done_text(done, translate))
                return out
            got: dict = {}
            seeds: dict = {}
            xp = 0
            spent = []
            regrow = []
            for f in ready:
                crop = f["crop"]
                lo, hi = CROPS[crop]["units"]
                units = self.rng.randint(lo, hi) * (1 + 0.1 * p["grond"])
                units = int(units) + (1 if self.rng.random() < units - int(units) else 0)
                got[crop] = got.get(crop, 0) + units
                xp += CROPS[crop]["xp"]
                for _ in range(units):
                    if self.rng.random() < SEED_CHANCE:
                        seeds[crop] = seeds.get(crop, 0) + 1
                left = f["left"] - 1
                if left <= 0:
                    conn.execute("UPDATE farm_fields SET crop=NULL, planted=NULL, left=0 WHERE pubkey=? AND slot=?", (key, f["slot"]))
                    spent.append(crop)
                else:
                    conn.execute("UPDATE farm_fields SET planted=?, left=? WHERE pubkey=? AND slot=?", (int(now), left, key, f["slot"]))
                    regrow.append(left)
            event = ""
            if self.rng.random() < EVENT_CHANCE:
                event = self._event(conn, p, got, fields, ready, translate)
            for crop, units in got.items():
                if units > 0:
                    self._add_item(conn, key, crop, units)
            for crop, n in seeds.items():
                self._add_item(conn, key, f"seed:{crop}", n)
            p["xp"] += xp
            p["name"] = name[:40] or p["name"]
            quest_texts = [self._quest_progress(conn, p, "harvest", c, u, now, translate) for c, u in got.items()]
            self._save(conn, p)
            conn.commit()
        text = translate("commands.farm.harvested", items=", ".join(
            f"{u} {translate(f'commands.farm.crop.{c}')}" for c, u in got.items() if u > 0) or "0", xp=xp)
        extra = []
        for crop, n in seeds.items():
            extra.append(translate("commands.farm.seed_found", n=n, crop=translate(f"commands.farm.crop.{crop}")))
        if regrow:
            extra.append(translate("commands.farm.regrow", n=len(regrow), times=max(regrow)))
        if spent:
            extra.append(translate("commands.farm.spent", n=len(spent)))
        if event:
            extra.append(event)
        extra += [t for t in quest_texts if t]
        level_after = level_of(p["xp"])
        if level_after > level_before:
            new = [c for c, v in CROPS.items() if v["level"] == level_after and c not in self.crops_off]
            extra.append(translate("commands.farm.level_up", level=level_after)
                         + (translate("commands.farm.new_crop", crop=translate(f"commands.farm.crop.{new[0]}")) if new else ""))
        out = [text + ("".join(extra) if extra else "")]
        if done:
            out.append(self._done_text(done, translate))
        return out

    def _event(self, conn: Any, p: dict, got: dict, fields: list, ready: list, translate: Callable) -> str:
        options = [("top", 3), ("storm", 2), ("thief", 2)] + ([("check", 3)] if got.get("wiet") else [])
        roll = self.rng.uniform(0, sum(w for _, w in options))
        kind = options[-1][0]
        for k, w in options:
            if roll < w:
                kind = k
                break
            roll -= w
        if kind == "top":
            crop = self.rng.choice(sorted(got))
            got[crop] *= 2
            return translate("commands.farm.event_top", crop=translate(f"commands.farm.crop.{crop}"))
        if kind == "storm":
            planted = [f for f in fields if f["crop"]]
            if not planted:
                return ""
            f = self.rng.choice(planted)
            conn.execute("UPDATE farm_fields SET crop=NULL, planted=NULL, left=0 WHERE pubkey=? AND slot=?", (p["pubkey"], f["slot"]))
            return translate("commands.farm.event_storm", crop=translate(f"commands.farm.crop.{f['crop']}"))
        if kind == "thief":
            amount = min(500, p["coins"] // 10)
            if amount <= 0:
                return ""
            p["coins"] -= amount
            return translate("commands.farm.event_thief", amount=amount)
        n = got.get("wiet", 0)
        got["wiet"] = 0
        return translate("commands.farm.event_check", n=n)

    def barn(self, key: str, translate: Callable) -> list:
        with self.db.connection() as conn:
            if self._player(conn, key) is None:
                return [translate("commands.farm.no_farm")]
            items = self._items(conn, key)
        if not items:
            return [translate("commands.farm.barn_empty")]
        from .f1_data import pack
        return pack(translate("commands.farm.barn"), [self._item_text(i, q, translate) for i, q in sorted(items.items())], sep=", ")

    def _item_text(self, item: str, qty: int, translate: Callable) -> str:
        if item.startswith("seed:"):
            return translate("commands.farm.seed_item", n=qty, crop=translate(f"commands.farm.crop.{item[5:]}"))
        if item in CROPS:
            return f"{qty} {translate(f'commands.farm.crop.{item}')}"
        return f"{qty} {translate(f'commands.farm.product.{item}')}"

    def sell(self, key: str, name: str, word: str, count: Optional[int], translate: Callable, now: Optional[float] = None) -> list:
        """Sell one item (all of it, or `count`), or everything that is not seed ("alles"/"all"/empty)."""
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            self._interest(p, now)
            items = {i: q for i, q in self._items(conn, key).items() if not i.startswith("seed:")}
            w = (word or "").strip().lower()
            if w in ("", "alles", "all", "tout", "alle"):
                chosen = items
            else:
                item = find_crop(w) or find_product(w)
                if item is None or item not in items:
                    return [translate("commands.farm.nothing_to_sell", q=(word or "")[:20])]
                chosen = {item: min(items[item], count) if count else items[item]}
            if not chosen:
                return [translate("commands.farm.barn_empty")]
            total = 0
            for item, qty in chosen.items():
                price = CROPS[item]["sell"] if item in CROPS else PRODUCTS[item]["sell"]
                total += price * qty
                self._add_item(conn, key, item, -qty)
            p["coins"] += total
            p["name"] = name[:40] or p["name"]
            quest_text = self._quest_progress(conn, p, "sell", None, total, now, translate)
            self._save(conn, p)
            conn.commit()
        return [translate("commands.farm.sold", items=", ".join(self._item_text(i, q, translate) for i, q in chosen.items()),
                          coins=total, total=p["coins"]) + quest_text]

    def process(self, key: str, name: str, word: str, count: Optional[int], translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            lvl = level_of(p["xp"])
            can = [k for k, v in PRODUCTS.items() if CROPS[v["crop"]]["level"] <= lvl and v["crop"] not in self.crops_off]
            product = find_product(word)
            if product is None:
                return [translate("commands.farm.process_usage", list=", ".join(
                    translate(f"commands.farm.product.{k}") for k in can))]
            pname = translate(f"commands.farm.product.{product}")
            spec = PRODUCTS[product]
            if spec["crop"] in self.crops_off:
                return [translate("commands.farm.crop_off", crop=pname)]
            if product not in can:
                return [translate("commands.farm.crop_locked", crop=pname, level=CROPS[spec["crop"]]["level"])]
            self._interest(p, now)
            done, _ = self._collect_jobs(conn, p, now)
            busy = conn.execute("SELECT COUNT(*) FROM farm_jobs WHERE pubkey=?", (key,)).fetchone()[0]
            if busy >= p["workshop"]:
                self._save(conn, p)
                conn.commit()
                return [translate("commands.farm.workshop_full", n=p["workshop"])]
            have = self._items(conn, key).get(spec["crop"], 0)
            qty = max(1, min(count or 1, MAX_JOB_QTY))
            if have < spec["need"]:
                self._save(conn, p)
                conn.commit()
                return [translate("commands.farm.not_enough", crop=translate(f"commands.farm.crop.{spec['crop']}"),
                                  need=spec["need"], have=have)]
            qty = min(qty, have // spec["need"])
            self._add_item(conn, key, spec["crop"], -qty * spec["need"])
            ready = int(now + spec["hours"] * 3600)
            conn.execute("INSERT INTO farm_jobs (pubkey, product, qty, ready) VALUES (?,?,?,?)", (key, product, qty, ready))
            p["name"] = name[:40] or p["name"]
            quest_text = self._quest_progress(conn, p, "process", product, qty, now, translate)
            self._save(conn, p)
            conn.commit()
        out = [translate("commands.farm.processing", n=qty, product=pname, left=left_text(ready - now, translate)) + quest_text]
        if done:
            out.append(self._done_text(done, translate))
        return out

    def bank(self, key: str, name: str, action: str, amount_word: str, translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            self._interest(p, now)
            if action:
                source = p["coins"] if action == "in" else p["bank"]
                word = (amount_word or "").strip().lower()
                amount = source if word in ("alles", "all", "tout", "alle") else (int(word) if word.isdigit() else 0)
                if amount <= 0 or amount > source:
                    self._save(conn, p)
                    conn.commit()
                    return [translate("commands.farm.bad_amount", max=source)]
                if action == "in":
                    p["coins"] -= amount
                    p["bank"] += amount
                else:
                    p["bank"] -= amount
                    p["coins"] += amount
            p["name"] = name[:40] or p["name"]
            self._save(conn, p)
            conn.commit()
        key_text = {"in": "commands.farm.deposited", "out": "commands.farm.withdrew"}.get(action, "commands.farm.bank")
        return [translate(key_text, bank=p["bank"], coins=p["coins"], rate=int(BANK_RATE * 100), cap=BANK_MAX_INTEREST)]

    def upgrade(self, key: str, name: str, word: str, translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            self._interest(p, now)
            offers = {
                "veld": (field_price(p["fields"]) if p["fields"] < MAX_FIELDS else None, f"{p['fields']}/{MAX_FIELDS}"),
                "kas": (kas_price(p["kas"]) if p["kas"] < MAX_KAS else None, f"{p['kas']}/{MAX_KAS}"),
                "grond": (grond_price(p["grond"]) if p["grond"] < MAX_GROND else None, f"{p['grond']}/{MAX_GROND}"),
                "werkplaats": (workshop_price(p["workshop"]) if p["workshop"] < MAX_WORKSHOP else None, f"{p['workshop']}/{MAX_WORKSHOP}"),
            }
            what = find_upgrade(word)
            if what is None:
                self._save(conn, p)
                conn.commit()
                pieces = [translate(f"commands.farm.up.{k}", price=price if price else "max", now=state) for k, (price, state) in offers.items()]
                from .f1_data import pack
                return pack(translate("commands.farm.upgrades_head", coins=p["coins"]), pieces)
            price, _state = offers[what]
            if price is None:
                return [translate("commands.farm.upgrade_max")]
            if price > p["coins"]:
                return [translate("commands.farm.no_money", need=price, coins=p["coins"])]
            p["coins"] -= price
            if what == "veld":
                p["fields"] += 1
                conn.execute("INSERT OR IGNORE INTO farm_fields (pubkey, slot, crop, planted, left) VALUES (?,?,NULL,NULL,0)",
                             (key, p["fields"]))
            elif what == "kas":
                p["kas"] += 1
            elif what == "grond":
                p["grond"] += 1
            else:
                p["workshop"] += 1
            p["name"] = name[:40] or p["name"]
            self._save(conn, p)
            conn.commit()
        return [translate("commands.farm.upgraded", what=translate(f"commands.farm.up_name.{what}"), coins=p["coins"])]

    def give(self, key: str, name: str, target: str, amount_word: str, translate: Callable, now: Optional[float] = None) -> list:
        now = time.time() if now is None else now
        amount = int(amount_word) if (amount_word or "").isdigit() else 0
        with self.db.connection() as conn:
            p = self._player(conn, key)
            if p is None:
                return [translate("commands.farm.no_farm")]
            self._interest(p, now)
            rows = conn.execute("SELECT pubkey, name FROM farm_players WHERE LOWER(name) = ?", ((target or "").strip().lower(),)).fetchall()
            if len(rows) != 1:
                return [translate("commands.farm.give_unknown", name=(target or "")[:30])]
            to_key, to_name = rows[0]
            if to_key == key:
                return [translate("commands.farm.give_self")]
            if amount <= 0 or amount > p["coins"]:
                return [translate("commands.farm.bad_amount", max=p["coins"])]
            p["coins"] -= amount
            conn.execute("UPDATE farm_players SET coins = coins + ? WHERE pubkey = ?", (amount, to_key))
            p["name"] = name[:40] or p["name"]
            self._save(conn, p)
            conn.commit()
        return [translate("commands.farm.gave", amount=amount, name=to_name, coins=p["coins"])]

    # ------------------------------------------------------------------ seasons (a calendar month; points = farm XP gained)
    def season_settings(self) -> dict:
        """On/off, length (month or week) and the rewards for places 1-3; set on the dashboard (Games -> Farming Idle)."""
        out = dict(SEASON_DEFAULTS)
        try:
            import json as _json
            with self.db.connection() as conn:
                row = conn.execute("SELECT value FROM bot_metadata WHERE key = ?", (SEASON_SETTINGS_KEY,)).fetchone()
            saved = _json.loads(row[0]) if row and row[0] else {}
            if isinstance(saved, dict):
                out.update({k: v for k, v in saved.items() if k in SEASON_DEFAULTS})
        except Exception:  # noqa: BLE001 - no table yet or bad JSON: defaults
            pass
        out["enabled"] = bool(out["enabled"])
        out["length"] = out.get("length") if out.get("length") in ("week", "custom") else "month"
        out["start"], out["end"] = str(out.get("start") or "")[:10], str(out.get("end") or "")[:10]
        rewards = [max(0, min(MAX_PRICE, int(r))) for r in (out.get("rewards") or [])][:3]
        out["rewards"] = rewards + [0] * (3 - len(rewards))
        return out

    def save_season_settings(self, enabled: bool, length: str, rewards: list, start: str = "", end: str = "",
                             now: Optional[float] = None) -> dict:
        """ValueError when a chosen period is not valid (both dates, start <= end, end not in the past, at most a year)."""
        import datetime as _dt
        import json as _json
        now = time.time() if now is None else now
        length = length if length in ("week", "custom") else "month"
        clean = {"enabled": bool(enabled), "length": length,
                 "rewards": [max(0, min(MAX_PRICE, int(r or 0))) for r in list(rewards)[:3]], "start": "", "end": ""}
        if length == "custom":
            a, b = _date(start), _date(end)
            if not a or not b:
                raise ValueError("choose a start and an end date")
            if a > b:
                raise ValueError("the end date is before the start date")
            if b < _dt.date.fromtimestamp(now):
                raise ValueError("the end date is in the past")
            if (b - a).days + 1 > MAX_SEASON_DAYS:
                raise ValueError(f"a season lasts at most {MAX_SEASON_DAYS} days")
            clean["start"], clean["end"] = a.isoformat(), b.isoformat()
        with self.db.connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS bot_metadata (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("INSERT OR REPLACE INTO bot_metadata (key, value) VALUES (?, ?)", (SEASON_SETTINGS_KEY, _json.dumps(clean)))
            conn.commit()
        return self.season_settings()

    def _season_base(self, conn: Any, season: str, now: float) -> None:
        """Every player gets a starting point for this season: their XP when the season started (or 0 when they
        joined during the season)."""
        start = season_start(season)
        conn.execute("INSERT OR IGNORE INTO farm_season_base (season, pubkey, xp_start) "
                     "SELECT ?, pubkey, CASE WHEN COALESCE(created, 0) >= ? THEN 0 ELSE xp END FROM farm_players",
                     (season, int(start)))

    def _season_points(self, conn: Any, season: str) -> list:
        return conn.execute("SELECT p.pubkey, p.name, p.xp - b.xp_start AS pts FROM farm_players p JOIN farm_season_base b "
                            "ON b.pubkey = p.pubkey AND b.season = ? ORDER BY pts DESC, p.xp DESC", (season,)).fetchall()

    def season_roll(self, now: Optional[float] = None) -> Optional[dict]:
        """Close the previous season once (results + rewards) and start the current one. Returns the closed season
        {'season', 'results': [(rank, name, points, reward)]} when it was closed just now, else None."""
        now = time.time() if now is None else now
        settings = self.season_settings()
        if not settings["enabled"]:
            return None
        season = season_of(now, settings["length"], settings["start"], settings["end"])
        closed = None
        with self.db.connection() as conn:
            # the season before: any season with starting points but no results yet (also after a change of length,
            # or a chosen period that has ended while no new one runs)
            prev = conn.execute("SELECT season FROM farm_season_base WHERE season != ? AND season NOT IN "
                                "(SELECT season FROM farm_season_results) ORDER BY rowid DESC LIMIT 1", (season or "",)).fetchone()
            prev = prev[0] if prev else None
            if prev:
                results = []
                for rank, (key, name, pts) in enumerate([r for r in self._season_points(conn, prev) if r[2] > 0][:3], start=1):
                    reward = settings["rewards"][rank - 1]
                    conn.execute("UPDATE farm_players SET coins = coins + ? WHERE pubkey = ?", (reward, key))
                    conn.execute("INSERT INTO farm_season_results (season, rank, pubkey, name, points, reward) VALUES (?,?,?,?,?,?)",
                                 (prev, rank, key, name, pts, reward))
                    results.append((rank, name or "?", pts, reward))
                if not results:   # nobody earned anything: remember the season as closed anyway
                    conn.execute("INSERT INTO farm_season_results (season, rank, pubkey, name, points, reward) VALUES (?,0,'','',0,0)",
                                 (prev,))
                closed = {"season": prev, "results": results}
            if season:
                self._season_base(conn, season, now)
            conn.commit()
        return closed

    def season(self, key: str, translate: Callable, now: Optional[float] = None) -> list:
        """farm seizoen: the top 5 of this season, your own points and the days left."""
        now = time.time() if now is None else now
        settings = self.season_settings()
        if not settings["enabled"]:
            return [translate("commands.farm.season_off")]
        self.season_roll(now)
        current = season_of(now, settings["length"], settings["start"], settings["end"])
        if current is None:
            a = _date(settings["start"])
            if a and a > __import__("datetime").date.fromtimestamp(now):
                return [translate("commands.farm.season_planned", date=self._day_text(a, translate))]
            return [translate("commands.farm.season_none")]
        with self.db.connection() as conn:
            rows = self._season_points(conn, current)
        mine = next(((i + 1, pts) for i, (k, _n, pts) in enumerate(rows) if k == key), None)
        from .f1_data import pack
        pieces = [translate("commands.farm.season_line", rank=i + 1, name=(n or "?")[:20], points=pts)
                  for i, (_k, n, pts) in enumerate(rows[:5]) if pts > 0]
        out = pack(translate("commands.farm.season_head", days=season_days_left(now, settings["length"], settings["end"])),
                   pieces or [translate("commands.farm.season_empty")])
        if mine:
            out.append(translate("commands.farm.season_you", rank=mine[0], points=mine[1],
                                 rewards="/".join(str(r) for r in settings["rewards"])))
        return out

    @staticmethod
    def _day_text(d: Any, translate: Callable) -> str:
        return f"{d.day} {translate(f'commands.farm.month.{d.month}')}" if d else "?"

    def last_closed_season(self) -> Optional[str]:
        with self.db.connection() as conn:
            row = conn.execute("SELECT season FROM farm_season_results ORDER BY rowid DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def season_announcement(self, season: str, translate: Callable) -> Optional[str]:
        """The text for the games channel about a closed season (None when nobody earned points)."""
        with self.db.connection() as conn:
            rows = conn.execute("SELECT rank, name, points, reward FROM farm_season_results WHERE season = ? AND rank > 0 "
                                "ORDER BY rank", (season,)).fetchall()
        if not rows:
            return None
        if "_" in season:
            a, b = (_date(x) for x in season.split("_"))
            month = translate("commands.farm.period", start=self._day_text(a, translate), end=self._day_text(b, translate))
        elif "-W" in season:
            month = translate("commands.farm.week", n=int(season.split("-W")[1]))
        else:
            month = translate(f"commands.farm.month.{int(season[5:7])}")
        places = ", ".join(translate("commands.farm.season_place", rank=r, name=(n or "?")[:18], points=p, reward=w) for r, n, p, w in rows)
        return translate("commands.farm.season_post", month=month, places=places)

    # ------------------------------------------------------------------ dashboard (Games -> Farming Idle)
    def overview(self, now: Optional[float] = None) -> dict:
        """Everything of the game for the dashboard: players (with fields, jobs, barn, today's task), market, buy orders."""
        now = time.time() if now is None else now
        with self.db.connection() as conn:
            self._expire_offers(conn, now)
            players = []
            cols = ("pubkey", "name", "coins", "bank", "xp", "fields", "kas", "grond", "workshop", "last_seen")
            for row in conn.execute(f"SELECT {', '.join(cols)} FROM farm_players ORDER BY coins + bank DESC, xp DESC").fetchall():
                p = dict(zip(cols, row))
                key = p["pubkey"]
                fields = []
                for f in self._fields(conn, key):
                    if not f["crop"] or f["crop"] not in CROPS:
                        continue
                    ready = f["planted"] + grow_seconds(f["crop"], p["kas"])
                    fields.append({"slot": f["slot"], "crop": f["crop"], "ready_in": max(0, int(ready - now)), "left": f["left"]})
                jobs = [{"product": pr, "qty": q, "ready_in": max(0, int(r - now))} for pr, q, r in conn.execute(
                    "SELECT product, qty, ready FROM farm_jobs WHERE pubkey=? ORDER BY ready", (key,)).fetchall()]
                qrow = conn.execute("SELECT kind, need, progress, done FROM farm_quests WHERE pubkey=? AND day=?",
                                    (key, _day(now))).fetchone()
                offers = [{"id": i, "item": it, "qty": q, "price": pr} for i, it, q, pr in conn.execute(
                    "SELECT id, item, qty, price FROM farm_market WHERE seller=? ORDER BY id", (key,)).fetchall()]
                players.append({
                    "name": p["name"] or "?", "level": level_of(p["xp"]), "xp": p["xp"],
                    "next_xp": next_level_xp(p["xp"]), "coins": p["coins"], "bank": p["bank"], "fields_total": p["fields"],
                    "kas": p["kas"], "grond": p["grond"], "workshop": p["workshop"], "last_seen": p["last_seen"],
                    "fields": fields, "jobs": jobs, "barn": self._items(conn, key), "offers": offers,
                    "quest": dict(zip(("kind", "need", "progress", "done"), qrow)) if qrow else None})
            market = [{"id": i, "seller": n or "?", "item": it, "qty": q, "price": pr, "created": c} for i, n, it, q, pr, c in conn.execute(
                "SELECT id, seller_name, item, qty, price, created FROM farm_market ORDER BY item, price").fetchall()]
            orders = [{"id": i, "item": it, "price": pr, "qty": q, "filled": f, "created": c, "expires": e,
                       "open": f < q and e > now} for i, it, pr, q, f, c, e in conn.execute(
                "SELECT id, item, price, qty, filled, created, expires FROM farm_orders ORDER BY expires > ? DESC, id DESC LIMIT 50",
                (int(now),)).fetchall()]
            conn.commit()
        items = {c: {"kind": "crop", "sell": CROPS[c]["sell"]} for c in CROPS}
        items.update({pr: {"kind": "product", "sell": PRODUCTS[pr]["sell"]} for pr in PRODUCTS})
        self.season_roll(now)
        settings = self.season_settings()
        with self.db.connection() as conn:
            season = season_of(now, settings["length"], settings["start"], settings["end"])
            standings = ([{"name": n or "?", "points": pts} for _k, n, pts in self._season_points(conn, season)[:10]]
                         if season else [])
            past = [{"season": s_.replace("_", " – "), "rank": r, "name": n or "?", "points": p, "reward": w}
                    for s_, r, n, p, w in conn.execute(
                        "SELECT season, rank, name, points, reward FROM farm_season_results r WHERE rank > 0 ORDER BY "
                        "(SELECT MAX(rowid) FROM farm_season_results x WHERE x.season = r.season) DESC, rank LIMIT 18")]
        return {"task": self.task_of_day(now), "players": players, "market": market, "orders": orders, "items": items,
                "season": {"name": (season or "").replace("_", " – "), "running": bool(season),
                           "days_left": season_days_left(now, settings["length"], settings["end"]) if season else 0,
                           "standings": standings,
                           "past": past, "settings": settings}}

    def top(self, limit: int = 5) -> list:
        """[(name, level, worth)] best first: worth = coins + bank."""
        with self.db.connection() as conn:
            rows = conn.execute("SELECT name, xp, coins + bank FROM farm_players ORDER BY coins + bank DESC, xp DESC LIMIT ?",
                                (limit * 3,)).fetchall()
        return [(n or "?", level_of(xp), worth) for n, xp, worth in rows]
