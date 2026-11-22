"""Watchlist ([Watchlist]): react when a watched sender writes in a channel.

Why: a node with an offensive name (21.11.2026 "Führerhauptquartier" in Public) should get a short, direct request
to change it, and the operator wants to know when it shows up again - without giving it a stage in the channel.
People end up on the list for different reasons, so every watched sender has a text template (Baustein): the DM
text for that reason, whether a DM goes out at all, and whether the bot ignores that sender's commands.

What it does:
- every channel message whose sender name matches a target is reported to Home Assistant (default
  telegram_bot.send_message): sender, channel, text, hops, template, and what happened with the DM;
- the sender gets one DM per `dm_cooldown_hours` (kept in the bot's database, survives restarts), after
  `delay_seconds`, with the text of its template (no DM for a template with dm = false). A channel message carries
  no public key, so the DM goes to the key given with the target; when that key is not among the radio's contacts
  yet, the bot adds it as a contact first. Without a key the DM only works when the name is already a contact.
- with a template that has ignore = true the bot does not answer that sender's commands in channels (the message
  handler stops after this hook, as it does for other bots). Never anything in the channel.

Config (config.ini, set on the Watchlist page or the Watchlist card of the Plugins page):

    [Watchlist]
    enabled = true
    targets = Führerhauptquartier=7cf26cbf...=name, Troll==spam
                      ; comma-separated "name", "name=public key" or "name=public key=template id" (key may be
                      ; empty); the name matches case-insensitively as part of the sender name
    templates = [{"id": "name", "label": "Name", "text": "...", "dm": true, "ignore": false}, ...]
                      ; JSON; empty = DEFAULT_TEMPLATES. "%" is stored as \\u0025 (configparser interpolation)
    default_template = name      ; for targets without a template
    channels =                   ; empty = every channel
    dm_cooldown_hours = 24
    delay_seconds = 15
    notify = true
    ha_notify_service = telegram_bot.send_message
    corescope_url =              ; optional, e.g. https://live.saarmesh.de: the page links keys there

`message_dm` (1.5.1-sm.24) is still read: while no templates are saved it is the text of the default template.

The Watchlist page (menu, /watchlist) shows the targets with their statistics, the hit log (last MAX_HITS), the
templates and the settings; statistics and hits live in bot_metadata (STATS_KEY, HITS_KEY).
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Any, Optional

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]

SECTION = "Watchlist"
DM_KEY = "watchlist.dm_sent"   # bot_metadata: {target name (lower case): unix time of the last DM}
STATS_KEY = "watchlist.stats"  # bot_metadata: {target name (lower case): {last_seen, msgs, dms, ...}}
HITS_KEY = "watchlist.hits"    # bot_metadata: [newest first] {ts, target, sender, channel, text, hops, snr, dm, tpl}
MAX_HITS = 200
MAX_DM_BYTES = 158
SETTINGS_TTL_SECONDS = 30
DELAY_JITTER_SECONDS = 5
DEFAULT_DM = ("Hallo, bitte wähl einen anderen Node-Namen, der jetzige ist hier im Netz nicht erwünscht. "
              "Danke! – SaarMesh")
DEFAULT_TEMPLATES = [
    {"id": "name", "label": "Name", "dm": True, "ignore": False, "text": DEFAULT_DM},
    {"id": "ton", "label": "Ton", "dm": True, "ignore": False,
     "text": "Hallo, bitte achte im Mesh auf einen respektvollen Ton, Beleidigungen sind hier nicht erwünscht. "
             "Danke! – SaarMesh"},
    {"id": "spam", "label": "Spam", "dm": True, "ignore": True,
     "text": "Hallo, du sendest sehr viele Nachrichten. Bitte weniger, das Funknetz hat nur wenig Kapazität. "
             "Danke! – SaarMesh"},
    {"id": "kanal", "label": "Falscher Kanal", "dm": True, "ignore": False,
     "text": "Hallo, Public ist für kurze Nachrichten an alle. Für Tests und Spiele nutz bitte die passenden Kanäle. "
             "Danke! – SaarMesh"},
    {"id": "werbung", "label": "Werbung", "dm": True, "ignore": True,
     "text": "Hallo, Werbung und Kettenbriefe gehören nicht ins Mesh. Bitte lass das. Danke! – SaarMesh"},
    {"id": "beobachten", "label": "Nur beobachten", "dm": False, "ignore": False, "text": ""},
]


def _split(value: str) -> list:
    return [p.strip() for p in (value or "").split(",") if p.strip()]


def _norm(name: str) -> str:
    return (name or "").strip().casefold()


def _get(cfg: Any, key: str, fallback: str = "") -> str:
    """A [Watchlist] value without interpolation (texts may contain '%' and '{sender}')."""
    if not cfg.has_section(SECTION):
        return fallback
    return cfg.get(SECTION, key, fallback=fallback, raw=True)


def parse_targets(value: str) -> list:
    """'Name=key=tpl, Other' -> [(name lower case, name as written, key or '', template id or '')]."""
    targets = []
    for item in _split(value):
        parts = item.split("=")
        name = parts[0].strip()
        key = parts[1].strip().lower() if len(parts) > 1 else ""
        tpl = parts[2].strip().lower() if len(parts) > 2 else ""
        if _norm(name):
            targets.append((_norm(name), name, key if len(key) == 64 else "", tpl))
    return targets


def load_templates(cfg: Any) -> list:
    """The templates from config ([Watchlist] templates, JSON), else the defaults (with the old message_dm)."""
    raw = _get(cfg, "templates", "").strip()
    out = []
    if raw:
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        seen = set()
        for t in data if isinstance(data, list) else []:
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id", "")).strip().lower()
            if not tid or tid in seen or "=" in tid or "," in tid:
                continue
            seen.add(tid)
            out.append({"id": tid, "label": str(t.get("label") or tid).strip(), "text": str(t.get("text") or "").strip(),
                        "dm": bool(t.get("dm", True)), "ignore": bool(t.get("ignore", False))})
    if not out:
        out = [dict(t) for t in DEFAULT_TEMPLATES]
        old = _get(cfg, "message_dm", "").strip()
        if old:
            out[0]["text"] = old
    return out


def default_template_id(cfg: Any, templates: list) -> str:
    want = _get(cfg, "default_template", "").strip().lower()
    ids = [t["id"] for t in templates]
    return want if want in ids else ids[0]


def resolve_template(templates: list, default_id: str, tpl_id: str) -> dict:
    by_id = {t["id"]: t for t in templates}
    return by_id.get(tpl_id) or by_id.get(default_id) or templates[0]


def _load_json(db: Any, key: str, default):
    try:
        raw = db.get_metadata(key)
        data = json.loads(raw) if raw else default
        return data if isinstance(data, type(default)) else default
    except Exception:  # noqa: BLE001
        return default


def record_hit(db: Any, target: str, message: Any, dm_result: str, now: Optional[float] = None,
               template: str = "", ignored: bool = False) -> None:
    """Per-target statistics and the hit log (newest first, at most MAX_HITS), both in the bot's database."""
    now = time.time() if now is None else now
    stats = _load_json(db, STATS_KEY, {})
    st = stats.get(target) if isinstance(stats.get(target), dict) else {}
    st["last_seen"] = now
    st["msgs"] = int(st.get("msgs", 0)) + 1
    st["last_sender"] = getattr(message, "sender_id", "") or ""
    st["last_channel"] = getattr(message, "channel", "") or ""
    if dm_result == "gesendet":
        st["last_dm"] = now
        st["dms"] = int(st.get("dms", 0)) + 1
    if not dm_result.startswith("keine"):
        st["last_dm_result"] = dm_result
    stats[target] = st
    db.set_metadata(STATS_KEY, json.dumps(stats, ensure_ascii=False))
    hits = _load_json(db, HITS_KEY, [])
    hits.insert(0, {
        "ts": now, "target": target, "sender": st["last_sender"], "channel": st["last_channel"],
        "text": (getattr(message, "content", "") or "")[:300], "hops": _hops(message),
        "snr": getattr(message, "snr", None), "dm": dm_result, "tpl": template, "ignored": bool(ignored),
    })
    db.set_metadata(HITS_KEY, json.dumps(hits[:MAX_HITS], ensure_ascii=False))


def overview(db: Any, cfg: Any, now: Optional[float] = None) -> dict:
    """Everything the Watchlist page shows: settings, templates, the targets with their statistics, the hit log."""
    now = time.time() if now is None else now
    has = cfg.has_section(SECTION)
    try:
        cooldown_h = int(float(_get(cfg, "dm_cooldown_hours", "24") or 24))
    except ValueError:
        cooldown_h = 24
    templates = load_templates(cfg)
    default_id = default_template_id(cfg, templates)
    settings = {
        "enabled": cfg.getboolean(SECTION, "enabled", fallback=False) if has else False,
        "targets": _get(cfg, "targets", ""),
        "channels": _get(cfg, "channels", ""),
        "default_template": default_id,
        "dm_cooldown_hours": cooldown_h,
        "delay_seconds": _get(cfg, "delay_seconds", "15"),
        "notify": cfg.getboolean(SECTION, "notify", fallback=True) if has else True,
        "ha_notify_service": _get(cfg, "ha_notify_service", "telegram_bot.send_message"),
        "corescope_url": _get(cfg, "corescope_url", "").rstrip("/"),
        "max_dm_bytes": MAX_DM_BYTES,
    }
    stats = _load_json(db, STATS_KEY, {})
    dm_sent = _load_json(db, DM_KEY, {})
    hits = _load_json(db, HITS_KEY, [])
    targets = []
    for norm, name, key, tpl in parse_targets(settings["targets"]):
        st = stats.get(norm) if isinstance(stats.get(norm), dict) else {}
        last_dm = float(dm_sent.get(norm, 0) or 0)
        t = resolve_template(templates, default_id, tpl)
        targets.append({
            "id": norm, "name": name, "key": key, "tpl": tpl, "tpl_used": t["id"],
            "msgs": int(st.get("msgs", 0)), "last_seen": st.get("last_seen"),
            "last_sender": st.get("last_sender"), "last_channel": st.get("last_channel"),
            "dms": int(st.get("dms", 0)), "last_dm": last_dm or None,
            "last_dm_result": st.get("last_dm_result"),
            "next_dm": (last_dm + cooldown_h * 3600) if t["dm"] and last_dm and last_dm + cooldown_h * 3600 > now else None,
        })
    week = now - 7 * 86400
    return {
        "settings": settings,
        "templates": templates,
        "default_templates": DEFAULT_TEMPLATES,
        "targets": targets,
        "hits": hits,
        "counts": {
            "targets": len(targets),
            "hits_7d": sum(1 for h in hits if float(h.get("ts", 0)) >= week),
            "dms": sum(t["dms"] for t in targets),
            "last_hit": hits[0]["ts"] if hits else None,
        },
    }


def reset_cooldown(db: Any, target: str) -> bool:
    """The next message of this target gets a DM again."""
    data = _load_json(db, DM_KEY, {})
    if _norm(target) not in data:
        return False
    del data[_norm(target)]
    db.set_metadata(DM_KEY, json.dumps(data, ensure_ascii=False))
    return True


def clear_hits(db: Any) -> None:
    db.set_metadata(HITS_KEY, "[]")


def send_test_note(cfg: Any) -> tuple:
    """A test note through the configured HA service (called from the web viewer, synchronous). (ok, detail)"""
    import urllib.error
    import urllib.request
    service = (_get(cfg, "ha_notify_service", "telegram_bot.send_message") or "").strip()
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if "." not in service:
        return False, "no Home Assistant service set"
    if not token:
        return False, "no SUPERVISOR_TOKEN (not running as an add-on?)"
    domain, name = service.split(".", 1)
    body = json.dumps({"title": "👀 Watchlist", "message": "Test: so sieht eine Watchlist-Meldung aus."}).encode()
    req = urllib.request.Request(f"http://supervisor/core/api/services/{domain}/{name}", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status < 300, f"{service}: HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return False, f"{service}: HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return False, f"{service}: {e}"


def _hops(message: Any) -> Optional[int]:
    ri = getattr(message, "routing_info", None)
    if isinstance(ri, dict) and ri.get("path_len_byte") is not None:
        try:
            return int(ri["path_len_byte"]) & 63
        except (TypeError, ValueError):
            pass
    hops = getattr(message, "hops", None)
    return hops if isinstance(hops, int) and 0 <= hops < 64 else None


class Watchlist:
    def __init__(self, bot: Any):
        self.bot = bot
        self._settings_at = -SETTINGS_TTL_SECONDS - 1.0
        self._pending: set = set()
        self._tasks: set = set()
        self._load_settings()

    # ---- settings (re-read every SETTINGS_TTL_SECONDS: a change on the page works without a restart) ----
    def _load_settings(self) -> None:
        self._settings_at = time.monotonic()
        cfg = self.bot.config
        has = cfg.has_section(SECTION)

        def num(key, fallback, low, high):
            try:
                return max(low, min(high, int(float(_get(cfg, key, str(fallback)) or fallback))))
            except ValueError:
                return fallback

        self.enabled = cfg.getboolean(SECTION, "enabled", fallback=False) if has else False
        self.targets = parse_targets(_get(cfg, "targets", ""))
        self.templates = load_templates(cfg)
        self.default_template = default_template_id(cfg, self.templates)
        self.channels = {_norm(c) for c in _split(_get(cfg, "channels", ""))}
        self.dm_cooldown = num("dm_cooldown_hours", 24, 0, 24 * 365) * 3600
        self.delay_seconds = num("delay_seconds", 15, 0, 600)
        self.notify = cfg.getboolean(SECTION, "notify", fallback=True) if has else True
        self.ha_notify_service = (_get(cfg, "ha_notify_service", "telegram_bot.send_message") or "").strip()

    def _refresh_settings(self) -> None:
        if time.monotonic() - self._settings_at > SETTINGS_TTL_SECONDS:
            try:
                self._load_settings()
            except Exception:  # noqa: BLE001 - keep the last good settings
                self._settings_at = time.monotonic()

    def template_for(self, target: tuple) -> dict:
        return resolve_template(self.templates, self.default_template, target[3])

    # ---- when the last DM went out (bot database) ----
    def _dm_sent(self) -> dict:
        try:
            raw = self.bot.db_manager.get_metadata(DM_KEY)
            data = json.loads(raw) if raw else {}
            return {str(k): float(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def _remember_dm(self, target: str, when: float) -> None:
        data = self._dm_sent()
        data[target] = when
        try:
            self.bot.db_manager.set_metadata(DM_KEY, json.dumps(data, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            self.bot.logger.warning("Watchlist: could not save the DM time: %s", e)

    # ---- the check, for every channel message ----
    def match(self, message: Any):
        self._refresh_settings()
        if not self.enabled or not self.targets or getattr(message, "is_dm", False):
            return None
        sender = _norm(getattr(message, "sender_id", "") or "")
        if not sender or sender == _norm(self.bot.config.get("Bot", "bot_name", fallback="")):
            return None
        if self.channels and _norm(getattr(message, "channel", "") or "") not in self.channels:
            return None
        for target in self.targets:
            if target[0] in sender:
                return target
        return None

    def observe(self, message: Any) -> Optional[tuple]:
        """Called for every channel message. Works in the background; the matched target, or None."""
        target = self.match(message)
        if target is None:
            return None
        task = asyncio.ensure_future(self._handle(message, target))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return target

    def ignores_commands(self, target: Optional[tuple]) -> bool:
        """True when the bot should not answer this target's commands (its template says so)."""
        return bool(target) and bool(self.template_for(target).get("ignore"))

    async def _handle(self, message: Any, target: tuple) -> None:
        key_name = target[0]
        tpl = self.template_for(target)
        if not tpl["dm"] or not tpl["text"]:
            dm_result = "keine (Baustein ohne DM)"
        else:
            dm_result = "keine (Abstand %d h)" % (self.dm_cooldown // 3600)
            try:
                now = time.time()
                due = now - self._dm_sent().get(key_name, 0.0) >= self.dm_cooldown and key_name not in self._pending
                if due:
                    self._pending.add(key_name)
                    try:
                        if self.delay_seconds:
                            await asyncio.sleep(self.delay_seconds + random.uniform(0, DELAY_JITTER_SECONDS))
                        dm_result = await self._send_dm(message, target, tpl["text"])
                    finally:
                        self._pending.discard(key_name)
            except Exception as e:  # noqa: BLE001
                dm_result = f"Fehler: {e}"
                self.bot.logger.warning("Watchlist: DM to %s failed: %s", getattr(message, "sender_id", "?"), e)
        try:
            record_hit(self.bot.db_manager, key_name, message, dm_result, template=tpl["label"], ignored=bool(tpl["ignore"]))
        except Exception as e:  # noqa: BLE001
            self.bot.logger.info("Watchlist: could not save the hit: %s", e)
        if self.notify:
            await self._ha_notify(message, dm_result, tpl)

    async def _ensure_contact(self, pubkey: str, name: str) -> None:
        mc = self.bot.meshcore
        if mc.get_contact_by_key_prefix(pubkey):
            return
        contact = {
            "public_key": pubkey, "type": 1, "flags": 0,
            "out_path_len": -1, "out_path": "", "out_path_hash_mode": 0,
            "adv_name": name[:31], "last_advert": 0, "adv_lat": 0.0, "adv_lon": 0.0,
        }
        res = await mc.commands.add_contact(contact)
        self.bot.logger.info("Watchlist: added %s (%s...) as a contact: %s", name, pubkey[:8],
                             getattr(res, "type", None))
        try:
            await mc.commands.get_contacts()
        except Exception:  # noqa: BLE001
            pass

    async def _send_dm(self, message: Any, target: tuple, text: str) -> str:
        sender = (getattr(message, "sender_id", "") or "").strip()
        pubkey = (getattr(message, "sender_pubkey", None) or target[2] or "").strip().lower()
        recipient = sender
        if len(pubkey) == 64:
            try:
                await self._ensure_contact(pubkey, sender or target[1])
            except Exception as e:  # noqa: BLE001
                self.bot.logger.info("Watchlist: could not add the contact: %s", e)
            recipient = pubkey
        ok = bool(await self.bot.command_manager.send_dm(
            recipient, text.replace("{sender}", sender), skip_user_rate_limit=True))
        if ok:
            self._remember_dm(target[0], time.time())
            self.bot.logger.info("Watchlist: DM sent to %s", sender)
            return "gesendet"
        self.bot.logger.info("Watchlist: DM to %s not possible", sender)
        return "nicht möglich (kein Kontakt)" if len(pubkey) != 64 else "fehlgeschlagen"

    async def _ha_notify(self, message: Any, dm_result: str, tpl: dict) -> None:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not (aiohttp and token and "." in self.ha_notify_service):
            return
        hops = _hops(message)
        snr = getattr(message, "snr", None)
        lines = [
            f"Von: {getattr(message, 'sender_id', '?')}",
            f"Kanal: {getattr(message, 'channel', '?')}",
            f"Text: {getattr(message, 'content', '') or ''}",
        ]
        rf = " • ".join(x for x in (f"{hops} Hops" if hops is not None else "",
                                     f"SNR {snr}" if snr is not None else "") if x)
        if rf:
            lines.append(rf)
        lines.append(f"Baustein: {tpl['label']}" + (" • Befehle ignoriert" if tpl.get("ignore") else ""))
        lines.append(f"DM: {dm_result}")
        domain, service = self.ha_notify_service.split(".", 1)
        body = {"title": "👀 Watchlist", "message": "\n".join(lines)}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"http://supervisor/core/api/services/{domain}/{service}", json=body,
                                        headers={"Authorization": f"Bearer {token}"},
                                        timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status >= 300:
                        self.bot.logger.info("Watchlist: HA notify returned status %s", resp.status)
        except Exception as e:  # noqa: BLE001
            self.bot.logger.info("Watchlist: HA notify failed: %s", e)


def get_watchlist(bot: Any) -> Watchlist:
    """One shared instance per bot, created on first use."""
    wl = bot.__dict__.get("_watchlist") if hasattr(bot, "__dict__") else None
    if wl is None:
        wl = Watchlist(bot)
        bot._watchlist = wl
    return wl
