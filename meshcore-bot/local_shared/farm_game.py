"""Kwekerij (the `farm` command): grow crops, harvest, process them in the workshop, sell, save in the bank, and level up
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
                growing.append((due, f["crop"]))
        pieces = [translate("commands.farm.ready_piece", n=n, crop=translate(f"commands.farm.crop.{c}")) for c, n in ready.items()]
        first: dict = {}
        for due, crop in sorted(growing):
            n, earliest = first.get(crop, (0, due))
            first[crop] = (n + 1, earliest)
        for crop, (n, due) in sorted(first.items(), key=lambda kv: kv[1][1])[:4]:
            pieces.append(translate("commands.farm.growing_piece", n=n, crop=translate(f"commands.farm.crop.{crop}"),
                                    left=left_text(due - now, translate)))
        if len(first) > 4:
            pieces.append(translate("commands.farm.more_growing", n=sum(n for n, _ in list(first.values())[4:])))
        if empty:
            pieces.append(translate("commands.farm.empty_piece", n=empty))
        for product, qty, ready_ts in jobs[:2]:
            pieces.append(translate("commands.farm.job_piece", n=qty, product=translate(f"commands.farm.product.{product}"),
                                    left=left_text(ready_ts - now, translate)))
        out = [head + " | ".join(pieces)]
        if done:
            out.append(self._done_text(done, translate))
        return out

    def _done_text(self, done: dict, translate: Callable) -> str:
        return translate("commands.farm.jobs_done", items=", ".join(
            f"{q} {translate(f'commands.farm.product.{i}')}" for i, q in done.items()))

    def shop(self, key: str, translate: Callable) -> list:
        with self.db.connection() as conn:
            p = self._player(conn, key)
        lvl = level_of(p["xp"]) if p else 1
        pieces = [translate("commands.farm.shop_item", crop=translate(f"commands.farm.crop.{c}"), price=CROPS[c]["seed"],
                            hours=CROPS[c]["hours"]) for c in self.available(lvl)]
        locked = [c for c, v in CROPS.items() if v["level"] > lvl and c not in self.crops_off]
        if locked:
            pieces.append(translate("commands.farm.shop_next", level=CROPS[locked[0]]["level"],
                                    crop=translate(f"commands.farm.crop.{locked[0]}")))
        from .f1_data import pack
        return pack(translate("commands.farm.shop_head"), pieces)

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
            self._save(conn, p)
            conn.commit()
        text = translate("commands.farm.harvested", items=", ".join(
            f"{u} {translate(f'commands.farm.crop.{c}')}" for c, u in got.items() if u > 0) or "0", xp=xp)
        extra = []
        for crop, n in seeds.items():
            extra.append(translate("commands.farm.seed_found", n=n, crop=translate(f"commands.farm.crop.{crop}")))
        if spent:
            extra.append(translate("commands.farm.spent", n=len(spent)))
        if event:
            extra.append(event)
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
            self._save(conn, p)
            conn.commit()
        return [translate("commands.farm.sold", items=", ".join(self._item_text(i, q, translate) for i, q in chosen.items()),
                          coins=total, total=p["coins"])]

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
            self._save(conn, p)
            conn.commit()
        out = [translate("commands.farm.processing", n=qty, product=pname, left=left_text(ready - now, translate))]
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

    def top(self, limit: int = 5) -> list:
        """[(name, level, worth)] best first: worth = coins + bank."""
        with self.db.connection() as conn:
            rows = conn.execute("SELECT name, xp, coins + bank FROM farm_players ORDER BY coins + bank DESC, xp DESC LIMIT ?",
                                (limit * 3,)).fetchall()
        return [(n or "?", level_of(xp), worth) for n, xp, worth in rows]
