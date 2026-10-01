#!/usr/bin/env python3
"""
'ha' command for the MeshCore Bot: Home Assistant over the mesh, for the bot's admins only.

Only in a real direct message, and only when the sender's public key is in the admin list (Bot > Admin public keys);
everyone else gets a short "admins only". Only the entities on the card can be read, and only the ones marked "may be
switched" can be switched. On the card every entity is a row of its own: the entity ID, the word you type after 'ha'
(switch.feest_verlichting -> 'ha feest aan') and whether it may be switched. The older Read / Switch lists still work
(the word is then the entity's own name). Handy when the internet is down (with the power down the bot is down too).

  ha                          the names you can use
  ha <name>                   its state, for example: ha woonkamer temperatuur
  ha alles                    the state of everything on the card
  ha <name> aan|uit|om        switch (light, switch, fan, ...); scenes and scripts: ha <name> aan
  ha <name>                   something that may be switched: toggle it (scene/script: on); anything else: its state
  ha <name> status            the state, also of something that may be switched
  ha <group> aan|uit|om|status   a group from the card (every row can be in groups): all of it at once
"""

import os
import re
from typing import Any, Optional

from ..models import MeshMessage
from .base_command import BaseCommand

API = "http://supervisor/core/api"
MAX_BYTES = 130
ON = {"aan", "on", "an", "ein", "allume", "allumer", "start"}
OFF = {"uit", "off", "aus", "éteins", "eteins", "eteindre", "stop"}
TOGGLE = {"om", "toggle", "wissel", "um", "bascule"}
ALL = {"alles", "all", "alle", "tout"}
STATUS = {"status", "stand", "staat", "?", "état", "etat", "zustand"}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _entities(raw: Any) -> list:
    return [e.strip().lower() for e in str(raw or "").strip("[]").replace("'", "").split(",")
            if re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", e.strip().lower())]


class HaCommand(BaseCommand):
    """Home Assistant over the mesh: read and switch the entities on the card, admins only, by DM."""

    name = "ha"
    keywords = ["ha"]
    description = "Home Assistant over the mesh: read or switch the entities on the card (admins only, by DM)"
    category = "special"
    requires_dm = True

    short_description = "Home Assistant over the mesh (admins)"
    usage = "ha [name] [aan|uit|om]"
    examples = ["ha", "ha woonkamer temperatuur", "ha tuinlicht aan"]

    settings_repeating_blocks = [
        {
            "id": "entity",
            "label": "Entities",
            "item_label": "entity",
            "enabled_field": "enabled",
            "help": ("One row per entity: its ID in Home Assistant (Settings > Devices & services > Entities), the word you "
                     "type after ha (for example feest for switch.feest_verlichting: ha feest aan) and whether it may be "
                     "switched. Nothing that is not here can be read or switched."),
            "fields": [
                {"key": "entity_id", "label": "Entity ID", "type": "str", "default": "",
                 "help": "For example switch.feest_verlichting or sensor.woonkamer_temperatuur."},
                {"key": "name", "label": "Word after ha", "type": "str", "default": "",
                 "help": "Short, one or two words, for example feest. Empty = the entity's own name."},
                {"key": "switch", "label": "May be switched (aan / uit / om)", "type": "bool", "default": False,
                 "help": "Off = only read. Scenes and scripts are turned on with 'ha <word> aan'."},
                {"key": "groups", "label": "Groups", "type": "str", "default": "",
                 "help": ("Optional, comma-separated, for example tuin, alles. 'ha tuin uit' switches everything in the group "
                          "tuin that may be switched; 'ha tuin' toggles the group (one on: all off, else all on).")},
            ],
        }
    ]

    settings_schema = [
        {"key": "read", "label": "Read (old list, without own words)", "type": "list", "default": [],
         "help": ("Entity IDs an admin may ask for, for example sensor.woonkamer_temperatuur, binary_sensor.voordeur, "
                  "alarm_control_panel.huis. Nothing else can be read.")},
        {"key": "control", "label": "Switch (old list, without own words)", "type": "list", "default": [],
         "help": ("Entity IDs an admin may switch with 'ha <name> aan/uit/om': lights, switches, fans, scenes, scripts. "
                  "They can be read too. Think twice before adding locks or the alarm.")},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        cfg = bot.config
        has = cfg.has_section("Ha_Command")
        self.ha_enabled = cfg.getboolean("Ha_Command", "enabled", fallback=True) if has else True
        self.control = _entities(cfg.get("Ha_Command", "control", fallback="") if has else "")
        self.read = [e for e in _entities(cfg.get("Ha_Command", "read", fallback="") if has else "") if e not in self.control]
        self.read += self.control
        self.alias: dict = {}   # entity -> the word typed after ha
        self.groups: dict = {}  # group word -> [entities]
        if has:
            rows: dict = {}
            for key, value in cfg.items("Ha_Command", raw=True):
                m = re.fullmatch(r"entity(\d+)_(entity_id|name|switch|enabled|groups)", key)
                if m:
                    rows.setdefault(int(m.group(1)), {})[m.group(2)] = (value or "").strip()
            for _i, row in sorted(rows.items()):
                entity = row.get("entity_id", "").lower()
                if not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", entity) or row.get("enabled", "true").lower() in ("false", "0", "no", "off"):
                    continue
                if row.get("name"):
                    self.alias[entity] = row["name"][:30]
                if entity not in self.read:
                    self.read.append(entity)
                if row.get("switch", "").lower() in ("true", "1", "yes", "on") and entity not in self.control:
                    self.control.append(entity)
                for g in row.get("groups", "").split(","):
                    g = _norm(g)
                    if g and entity not in self.groups.setdefault(g, []):
                        self.groups[g].append(entity)

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.ha_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.ha.help")

    # ---- Home Assistant (replaced in the tests) -------------------------------------------------------------
    async def _get_state(self, entity: str) -> Optional[dict]:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            return None
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(f"{API}/states/{entity}", headers={"Authorization": f"Bearer {token}"}) as r:
                return await r.json() if r.status == 200 else None

    async def _call(self, domain: str, service: str, entity: str) -> bool:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
        if not token:
            return False
        import aiohttp
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.post(f"{API}/services/{domain}/{service}", json={"entity_id": entity},
                              headers={"Authorization": f"Bearer {token}"}) as r:
                return r.status in (200, 201)

    # ---- helpers ---------------------------------------------------------------------------------------------
    def _short(self, entity: str) -> str:
        """The word for this entity: the one chosen on the card, else its own name without the domain."""
        return self.alias.get(entity) or entity.split(".", 1)[1].replace("_", " ")

    def _match(self, words: str, pool: list) -> list:
        """Entities whose name (without the domain) contains every typed word; an exact name wins."""
        want = _norm(words)
        if not want:
            return []
        exact = [e for e in pool if _norm(self._short(e)) == want]
        if exact:
            return exact
        parts = want.split()
        # the chosen word, or (also) the entity's own name, contains every typed word
        return [e for e in pool if all(p in _norm(self._short(e)) for p in parts)
                or all(p in _norm(e.split(".", 1)[1]) for p in parts)]

    def _state_text(self, entity: str, st: Optional[dict]) -> str:
        if not st:
            return self.translate("commands.ha.state", name=self._short(entity), state="?", unit="")
        attrs = st.get("attributes") or {}
        name = attrs.get("friendly_name") or self._short(entity)
        state = str(st.get("state", "?"))
        state = {"on": self.translate("commands.ha.on"), "off": self.translate("commands.ha.off")}.get(state, state)
        unit = attrs.get("unit_of_measurement") or ""
        return self.translate("commands.ha.state", name=str(name)[:40], state=state[:30], unit=(" " + unit) if unit else "")

    async def execute(self, message: MeshMessage) -> bool:
        try:
            if not message.is_dm or not message.sender_pubkey:
                return await self.send_response(message, self.translate("commands.ha.dm_only"))
            if not self._check_admin_access(message):
                self.logger.warning(f"ha: geweigerd voor {message.sender_id} (geen beheerder)")
                return await self.send_response(message, self.translate("commands.ha.not_admin"))
            _trigger, rest = self.split_trigger_and_args(message.content)
            words = (rest or "").split()
            if not self.read:
                return await self.send_response(message, self.translate("commands.ha.nothing_shared"))
            if not words:
                from ..f1_data import pack
                names = [self._short(e) + (" *" if e in self.control else "") for e in self.read]
                names += [self.translate("commands.ha.group_item", name=g, n=len(m)) for g, m in self.groups.items()]
                return await self._send_all(message, pack(self.translate("commands.ha.list_head"), names, sep=", "))
            action = words[-1].lower() if len(words) > 1 else ""
            target = _norm(" ".join(words[:-1]) if action in ON | OFF | TOGGLE | STATUS else " ".join(words))
            if target in self.groups:
                return await self._group(message, target, action)
            if action in ON | OFF | TOGGLE:
                return await self._switch(message, " ".join(words[:-1]), action)
            if action in STATUS:
                words = words[:-1]
            else:
                # 'ha feest' for something that may be switched: toggle it (a scene or script: turn it on)
                hit = self._match(" ".join(words), self.control)
                if len(hit) == 1 and self._match(" ".join(words), self.read) == hit:
                    return await self._switch(message, " ".join(words), "om")
            if len(words) == 1 and words[0].lower() in ALL:
                texts = [self._state_text(e, await self._get_state(e)) for e in self.read[:12]]
                from ..f1_data import pack
                return await self._send_all(message, pack("", texts, sep=" | "))
            found = self._match(" ".join(words), self.read)
            if not found:
                return await self.send_response(message, self.translate("commands.ha.unknown", q=" ".join(words)[:30]))
            texts = [self._state_text(e, await self._get_state(e)) for e in found[:4]]
            from ..f1_data import pack
            return await self._send_all(message, pack("", texts, sep=" | "))
        except Exception as e:
            self.logger.error(f"Error executing ha command: {e}", exc_info=True)
            return await self.send_response(message, self.translate("commands.ha.error"))

    async def _switch(self, message: MeshMessage, words: str, action: str) -> bool:
        found = self._match(words, self.control)
        if len(found) != 1:
            key = "commands.ha.not_switchable" if not found else "commands.ha.which"
            return await self.send_response(message, self.translate(key, q=words[:30],
                                                                    names=", ".join(self._short(e) for e in found[:4])))
        entity = found[0]
        domain = entity.split(".", 1)[0]
        if domain in ("scene", "script"):
            service_domain, service = domain, "turn_on"
        else:
            service_domain = "homeassistant"
            service = "turn_on" if action in ON else "turn_off" if action in OFF else "toggle"
        self.logger.info(f"ha: {message.sender_id} -> {service_domain}.{service} {entity}")
        if not await self._call(service_domain, service, entity):
            return await self.send_response(message, self.translate("commands.ha.error"))
        st = await self._get_state(entity)
        return await self.send_response(message, self.translate("commands.ha.done") + " " + self._state_text(entity, st))

    async def _group(self, message: MeshMessage, group: str, action: str) -> bool:
        """A group: aan/uit for all of it, 'om' or nothing = toggle (one on: all off, else all on), status = states."""
        members = self.groups[group]
        if action in STATUS:
            from ..f1_data import pack
            texts = [self._state_text(e, await self._get_state(e)) for e in members[:8]]
            return await self._send_all(message, pack("", texts, sep=" | "))
        targets = [e for e in members if e in self.control]
        if not targets:
            return await self.send_response(message, self.translate("commands.ha.not_switchable", q=group[:30], names=""))
        if action in ON:
            turn_on = True
        elif action in OFF:
            turn_on = False
        else:
            states = [await self._get_state(e) for e in targets]
            turn_on = not any(str((st or {}).get("state")) == "on" for st in states)
        done = []
        for e in targets:
            domain = e.split(".", 1)[0]
            if domain in ("scene", "script"):
                if not turn_on:
                    continue
                ok = await self._call(domain, "turn_on", e)
            else:
                ok = await self._call("homeassistant", "turn_on" if turn_on else "turn_off", e)
            if ok:
                done.append(self._short(e))
        self.logger.info(f"ha: {message.sender_id} -> groep {group} {'aan' if turn_on else 'uit'}: {', '.join(done)}")
        if not done:
            return await self.send_response(message, self.translate("commands.ha.error"))
        return await self.send_response(message, self.translate(
            "commands.ha.group_done", n=len(done), state=self.translate("commands.ha.on" if turn_on else "commands.ha.off"),
            names=", ".join(done)))

    async def _send_all(self, message: MeshMessage, texts: list) -> bool:
        ok = True
        for t in texts:
            ok = await self.send_response(message, t) and ok
        return ok
