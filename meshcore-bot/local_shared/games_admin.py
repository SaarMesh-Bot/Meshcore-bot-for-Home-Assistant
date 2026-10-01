#!/usr/bin/env python3
"""Backend of the dashboard's Games page (see local_web/games.html and patch_webviewer_games.py).

One read-only overview of every game on the mesh: Mesh RPG (xp), DX Jacht (dx), karma, check-in streaks, the open
voorspel question, the F1 prediction game and the Farming Idle (all players, the market). The one thing it writes: the
Farming Idle's buy orders of the market (what the market buys and for how much), set on the Farming Idle tab. Everything comes from the tables the commands and the Community
service keep (modules/mesh_archive.py, modules/mesh_community.py, modules/f1_game.py); this module only reads, apart
from creating those tables when they do not exist yet. Bots (the Bots page rules, and the bot itself) are left out
of every ranking. Public keys are never sent to the browser.

This runs inside the web viewer process, which has its own DBManager and config but no bot object, so the helpers
get a small stand-in with `config`, `db_manager` and `logger` (like bots_admin.py).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, Optional

from modules.mesh_archive import (BADGES, CMD_CAP, DX_HOP_CAP, MSG_CAP, XP_CHECKIN, XP_CMD, XP_FARM_TASK, XP_HOP, XP_KARMA, XP_MSG, badges_of, dx_best,
                                  ensure_archive, known_names, month_start_day, xp_all, week_start_day, xp_of)
from modules.mesh_community import is_bot_name, local_day, local_now, streaks, table_exists, without_bots

TOP = 15


def _bot(db_manager: Any, config: Any, logger: Optional[logging.Logger]) -> Any:
    return SimpleNamespace(config=config, db_manager=db_manager, logger=logger or logging.getLogger("games_admin"))


def _dx(bot: Any, since_day: Optional[str]) -> list:
    rows = without_bots(bot, dx_best(bot, since_day), TOP)
    return [{"name": n, "hops": h, "date": local_now(bot, t).strftime("%d-%m-%Y")} for n, h, t in rows]


def xp_parts(info: dict) -> list:
    """Where someone's XP comes from, in the order the page shows it; the xp values add up to info['xp']."""
    return [
        {"key": "messages", "count": info["messages"], "per": XP_MSG, "xp": info["messages"] * XP_MSG, "cap": MSG_CAP},
        {"key": "commands", "count": info["commands"], "per": XP_CMD, "xp": info["commands"] * XP_CMD, "cap": CMD_CAP},
        {"key": "checkins", "count": info["checkins"], "per": XP_CHECKIN, "xp": info["checkins"] * XP_CHECKIN},
        {"key": "karma", "count": info["karma"], "per": XP_KARMA, "xp": info["karma"] * XP_KARMA},
        {"key": "dx", "count": info["best_hops"], "per": XP_HOP, "xp": min(info["best_hops"], DX_HOP_CAP) * XP_HOP, "cap": DX_HOP_CAP},
        {"key": "farm", "count": info.get("farm_tasks", 0), "per": XP_FARM_TASK, "xp": info.get("farm_tasks", 0) * XP_FARM_TASK},
    ]


def _xp(bot: Any, since_day: Optional[str], with_details: bool) -> list:
    ranked = sorted(((n, i) for n, i in xp_all(bot, since_day) if i["xp"] > 0), key=lambda r: (-r[1]["xp"], r[0].lower()))
    scores = without_bots(bot, ranked, TOP)   # the bot check only for the names near the top
    out = []
    for name, info in scores:
        row = {"name": name, "xp": info["xp"], "parts": xp_parts(info),
               "active_days": info["active_days"], "all_messages": info["all_messages"]}
        if with_details:
            row.update({"level": info["level"], "title": info["title"], "next": info["next"],
                        "badges": badges_of(bot, name)})
        out.append(row)
    return out


def _karma(bot: Any, conn: Any) -> list:
    rows = conn.execute("SELECT receiver, COUNT(*) AS n FROM community_karma GROUP BY LOWER(receiver) ORDER BY n DESC, MIN(ts) LIMIT 60").fetchall()
    return [{"name": n, "points": p} for n, p in without_bots(bot, rows, TOP)]


def _checkin(bot: Any, conn: Any) -> list:
    today = local_day(bot)
    per: dict = {}
    for name, day in conn.execute("SELECT name, day FROM community_checkin WHERE day >= ?", ((today - timedelta(days=400)).isoformat(),)):
        per.setdefault(name.lower(), [name, []])[1].append(day)
    rows = []
    for name, days in per.values():
        current, best = streaks(days, today)
        if current > 0:
            rows.append((name, current, best))
    rows.sort(key=lambda r: (-r[1], -r[2], r[0].lower()))
    return [{"name": n, "streak": c, "best": b} for n, c, b in without_bots(bot, rows, TOP)]


def _voorspel(bot: Any, conn: Any) -> dict:
    out: dict = {"question": None, "standings": []}
    row = conn.execute("SELECT id, question, options, state, creator_name FROM community_questions WHERE state IN ('open', 'closed') ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        qid, question, options, state, creator = row
        choices = json.loads(options)
        counts = [0] * len(choices)
        for (choice,) in conn.execute("SELECT choice FROM community_answers WHERE question_id=?", (qid,)):
            if 0 <= choice < len(counts):
                counts[choice] += 1
        out["question"] = {"text": question, "state": state, "asked_by": creator or "",
                           "choices": [{"text": c, "answers": n} for c, n in zip(choices, counts)]}
    rows = conn.execute(
        """SELECT a.pubkey, COUNT(*) FROM community_answers a JOIN community_questions q ON q.id = a.question_id
           WHERE q.state='settled' AND a.choice = q.answer GROUP BY a.pubkey ORDER BY COUNT(*) DESC LIMIT 60""").fetchall()
    named = []
    for pubkey, points in rows:
        name = conn.execute("SELECT name FROM community_answers WHERE pubkey=? ORDER BY ts DESC LIMIT 1", (pubkey,)).fetchone()
        named.append(((name[0] if name and name[0] else "?"), points))
    out["standings"] = [{"name": n, "points": p} for n, p in without_bots(bot, named, TOP)]
    return out


def _f1_open(bot: Any, conn: Any) -> Optional[dict]:
    """The latest round with predictions but no points yet: who has predicted (the picks stay hidden until scoring)."""
    row = conn.execute(
        """SELECT p.season, p.round FROM f1_predictions p WHERE NOT EXISTS
           (SELECT 1 FROM f1_points s WHERE s.season = p.season AND s.round = p.round)
           ORDER BY p.season DESC, CAST(p.round AS INTEGER) DESC LIMIT 1""").fetchone()
    if not row:
        return None
    season, rnd = row
    names = [(n or "?",) for (n,) in conn.execute(
        "SELECT name FROM f1_predictions WHERE season=? AND round=? ORDER BY created_at", (season, rnd)).fetchall()]
    names = [n for (n,) in without_bots(bot, names, 60)]
    return {"season": season, "round": rnd, "names": names} if names else None


def _f1(bot: Any, conn: Any) -> dict:
    if not table_exists(conn, "f1_predictions") or not table_exists(conn, "f1_points"):
        return {"season": None, "standings": [], "open": None}
    open_round = _f1_open(bot, conn)
    season = conn.execute("SELECT MAX(season) FROM f1_points").fetchone()[0]
    if not season:
        return {"season": open_round["season"] if open_round else None, "standings": [], "open": open_round}
    rows = conn.execute("SELECT pubkey, SUM(points), COUNT(*) FROM f1_points WHERE season=? GROUP BY pubkey ORDER BY SUM(points) DESC LIMIT 60",
                        (season,)).fetchall()
    named = []
    for pubkey, points, races in rows:
        name = conn.execute("SELECT name FROM f1_predictions WHERE pubkey=? AND season=? ORDER BY created_at DESC LIMIT 1",
                            (pubkey, season)).fetchone()
        named.append(((name[0] if name and name[0] else "?"), int(points), int(races)))
    return {"season": season, "standings": [{"name": n, "points": p, "races": r} for n, p, r in without_bots(bot, named, TOP)],
            "open": open_round}


def _farm(bot: Any, conn: Any) -> list:
    """Farming Idle (farm game): the richest farmers (coins + bank), with their level. Empty until someone plays."""
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='farm_players'").fetchone():
        return []
    from .farm_game import level_of
    rows = conn.execute("SELECT name, xp, coins + bank FROM farm_players ORDER BY coins + bank DESC, xp DESC LIMIT 60").fetchall()
    return [{"name": n or "?", "level": level_of(xp), "worth": w} for n, xp, w in without_bots(bot, rows, TOP)]


def _farm_game(db_manager: Any, config: Any) -> Any:
    from .farm_game import FarmGame
    return FarmGame(db_manager)


def farm_overview(db_manager: Any, config: Any, logger: Optional[logging.Logger] = None) -> dict:
    """The Farming Idle tab: every player (fields, workshop, barn, today's task, offers), the market and the market's buy
    orders. Bots are left out; public keys are not sent to the browser."""
    bot = _bot(db_manager, config, logger)
    data = _farm_game(db_manager, config).overview()
    data["players"] = [p for p in data["players"] if not is_bot_name(bot, p["name"])]
    for p in data["players"]:
        p.pop("key", None)
    data["generated_at"] = int(time.time())
    return data


def farm_order_add(db_manager: Any, config: Any, body: dict) -> int:
    """A buy order of the market, from the Farming Idle tab: {item, price, qty, days}. ValueError on bad input."""
    try:
        item, price, qty, days = str(body.get("item") or ""), int(body.get("price")), int(body.get("qty")), int(body.get("days") or 3)
    except (TypeError, ValueError):
        raise ValueError("item, price, qty and days are needed")
    if price < 1 or qty < 1 or days < 1:
        raise ValueError("price, qty and days must be at least 1")
    return _farm_game(db_manager, config).add_order(item, price, qty, days)


def farm_season_save(db_manager: Any, config: Any, body: dict) -> dict:
    """Season settings from the Farming Idle tab: {enabled, length: month|week, rewards: [1st, 2nd, 3rd]}."""
    try:
        rewards = [int(x) for x in (body.get("rewards") or [])][:3]
    except (TypeError, ValueError):
        raise ValueError("rewards must be numbers")
    if len(rewards) != 3 or any(r < 0 for r in rewards):
        raise ValueError("three rewards of 0 or more are needed")
    return _farm_game(db_manager, config).save_season_settings(
        bool(body.get("enabled", True)), str(body.get("length") or "month"), rewards,
        str(body.get("start") or ""), str(body.get("end") or ""))


def farm_order_delete(db_manager: Any, config: Any, oid: int) -> bool:
    return _farm_game(db_manager, config).delete_order(oid)


def standings(db_manager: Any, config: Any, logger: Optional[logging.Logger] = None) -> dict:
    """Everything the Games page shows, bots left out."""
    bot = _bot(db_manager, config, logger)
    ensure_archive(db_manager)
    week, month = week_start_day(bot), month_start_day(bot)
    with db_manager.connection() as conn:
        karma, checkin = _karma(bot, conn), _checkin(bot, conn)
        voorspel, f1 = _voorspel(bot, conn), _f1(bot, conn)
        farm = _farm(bot, conn)
        last_day = conn.execute("SELECT MAX(day) FROM community_activity").fetchone()[0]
    return {
        "generated_at": int(time.time()),
        "last_activity_day": last_day,
        "badges_total": len(BADGES),
        "xp": {"ever": _xp(bot, None, True), "week": _xp(bot, week, False)},
        "dx": {"week": _dx(bot, week), "month": _dx(bot, month), "ever": _dx(bot, None)},
        "karma": karma,
        "checkin": checkin,
        "voorspel": voorspel,
        "f1": f1,
        "farm": farm,
    }
