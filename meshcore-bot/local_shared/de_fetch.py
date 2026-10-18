"""Network side of the German data commands and services (de_warn, de_pegel): small async fetches with aiohttp.

Kept apart from de_warn/de_pegel so those stay pure (testable without network). Every function returns None (or an
empty result) when the source cannot be reached; the caller says so in its own words.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import aiohttp

UA = {"User-Agent": "meshcore-bot-ha (DE data on the mesh)"}


async def get_text(url: str, timeout: float = 15) -> Optional[str]:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), headers=UA) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                return await r.text(errors="replace")
    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError):
        return None


async def get_json(url: str, timeout: float = 15) -> Any:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), headers=UA) as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return None
                return await r.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None


async def dwd(now) -> Optional[dict]:
    """The DWD answer, one retry after a short pause (the first call after a start sometimes fails on DNS)."""
    from .de_warn import DWD_URL, parse_dwd_payload
    for attempt in range(2):
        text = await get_text(DWD_URL, timeout=20)
        data = parse_dwd_payload(text) if text else None
        if data is not None:
            return data
        if not attempt:
            await asyncio.sleep(2)
    return None


async def nina(districts: dict, now, region_tokens) -> tuple:
    """(warnings, cancels, reached) over all districts {ars5: name}; reached = how many answered."""
    from .de_warn import NINA_URL, nina_items, normalize_ars
    sem = asyncio.Semaphore(4)

    async def one(ars, name):
        ars12 = normalize_ars(ars)
        if not ars12:
            return None
        async with sem:
            data = await get_json(NINA_URL.format(ars=ars12), timeout=12)
        return None if data is None else nina_items(data, name, now, region_tokens)

    items = list(districts.items())
    results = list(await asyncio.gather(*(one(a, n) for a, n in items)))
    if any(r is None for r in results):
        # one retry for the districts that did not answer, one after the other
        await asyncio.sleep(2)
        for i, (a, n) in enumerate(items):
            if results[i] is None:
                results[i] = await one(a, n)
    warns, cancels, reached, keys, ckeys = [], [], 0, set(), set()
    for r in results:
        if r is None:
            continue
        reached += 1
        for w in r[0]:
            if w["key"] not in keys:
                keys.add(w["key"])
                warns.append(w)
        for c in r[1]:
            if c[0] not in ckeys:
                ckeys.add(c[0])
                cancels.append(c)
    return warns, cancels, reached


async def pegelonline_station(number: str) -> Optional[dict]:
    from .de_pegel import PO_STATION
    return await get_json(PO_STATION.format(number=number), timeout=12)


async def pegelonline_history(number: str, hours: int = 3) -> Optional[list]:
    from .de_pegel import PO_HISTORY
    data = await get_json(PO_HISTORY.format(number=number, hours=hours), timeout=12)
    return data if isinstance(data, list) else None


async def hmd_series(number: str, tz) -> list:
    """The newest of the hosts' series [(datetime, cm)], [] when none answers."""
    from .de_pegel import hmd_urls, parse_hmd
    best: list = []
    for url in hmd_urls(number):
        text = await get_text(url, timeout=12)
        series = parse_hmd(text, tz) if text else []
        if series and (not best or series[-1][0] > best[-1][0]):
            best = series
    return best
