"""ha command: Home Assistant over the mesh, admins only, by DM; only the entities on the card, switching only the
'Switch' list. Runs in the simulated build tree: test_ha_command.py <tree>."""
import asyncio
import configparser
import importlib
import logging
import os
import sys
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


HaCommand = imp("modules.commands.ha_command").HaCommand
MeshMessage = imp("modules.models").MeshMessage
Translator = imp("modules.i18n").Translator
tr = Translator("nl", "translations/", "local/translations")
help_filter = imp("modules.help_filter")
ADMIN = "ab" * 32

STATES = {
    "sensor.woonkamer_temperatuur": {"state": "21.4", "attributes": {"friendly_name": "Woonkamer temperatuur", "unit_of_measurement": "°C"}},
    "binary_sensor.voordeur": {"state": "off", "attributes": {"friendly_name": "Voordeur"}},
    "light.tuinlicht": {"state": "off", "attributes": {"friendly_name": "Tuinlicht"}},
    "light.tuinlicht_achter": {"state": "off", "attributes": {"friendly_name": "Tuinlicht achter"}},
    "scene.film": {"state": "2026-10-01", "attributes": {"friendly_name": "Film"}},
    "lock.voordeur": {"state": "locked", "attributes": {}},
}
calls = []


def make(card=None):
    cfg = configparser.ConfigParser()
    cfg["Bot"] = {"bot_name": "Test|🤖"}
    cfg["Admin_ACL"] = {"admin_pubkeys": ADMIN}
    cfg["Ha_Command"] = card if card is not None else {
        "read": "sensor.woonkamer_temperatuur, binary_sensor.voordeur",
        "control": "light.tuinlicht, light.tuinlicht_achter, scene.film"}
    bot = types.SimpleNamespace(config=cfg, logger=logging.getLogger("ha"), translator=tr, db_manager=MagicMock(),
                                command_manager=types.SimpleNamespace(monitor_channels=["#bot"]))
    c = HaCommand(bot)

    async def get_state(entity):
        return STATES.get(entity)

    async def call(domain, service, entity):
        calls.append((domain, service, entity))
        if service == "turn_on" and entity in STATES:
            STATES[entity]["state"] = "on"
        return True
    c._get_state, c._call = get_state, call
    return c


async def run(text, pubkey=ADMIN, dm=True, card=None):
    c = make(card)
    out = []

    async def send(message, content, **kw):
        out.append(content)
        return True
    c.send_response = send
    await c.execute(MeshMessage(content=text, sender_id="Vipje", sender_pubkey=pubkey, is_dm=dm, channel=None if dm else "#bot"))
    return out


async def main():
    r = await run("ha", pubkey="cd" * 32)
    check(r == ["ha is alleen voor de beheerder van deze bot."], f"geen beheerder: geweigerd ({r})")
    r = await run("ha", dm=False, pubkey=None)
    check(r[0].startswith("ha werkt alleen in een DM"), "in een kanaal: alleen DM")
    r = await run("ha", card={})
    check(r[0].startswith("Nog niets gedeeld"), "lege kaart: uitleg")
    r = await run("ha")
    check(r[0].startswith("HA (* = schakelbaar): woonkamer temperatuur, voordeur, tuinlicht *"), f"lijst van namen ({r})")
    r = await run("ha woonkamer temperatuur")
    check(r == ["Woonkamer temperatuur: 21.4 °C"], f"toestand met eenheid ({r})")
    r = await run("ha voordeur")
    check(r == ["Voordeur: uit"], f"aan/uit vertaald ({r})")
    r = await run("ha kelder")
    check(r[0].startswith("'kelder' staat niet op de kaart"), "onbekend")
    r = await run("ha lock voordeur")
    check("locked" not in " ".join(r), "niet op de kaart = niet te lezen (slot)")
    r = await run("ha voordeur aan")
    check(r[0].startswith("'voordeur' mag niet geschakeld worden") and not calls, "alleen lezen = niet schakelen")
    r = await run("ha tuinlicht aan")
    check(calls == [("homeassistant", "turn_on", "light.tuinlicht")] and r == ["Gedaan. Tuinlicht: aan"], f"exacte naam wint en schakelt ({calls}, {r})")
    r = await run("ha tuin aan")
    check(r[0].startswith("Welke? tuinlicht, tuinlicht achter") and len(calls) == 1, "twee mogelijk: vraagt welke, schakelt niet")
    r = await run("ha film aan")
    check(calls[-1] == ("scene", "turn_on", "scene.film"), "scène: scene.turn_on")
    r = await run("ha tuinlicht achter uit")
    check(calls[-1] == ("homeassistant", "turn_off", "light.tuinlicht_achter"), "uit")
    r = await run("ha alles")
    check(r[0].startswith("Woonkamer temperatuur: 21.4 °C | Voordeur: uit"), f"alles ({r})")
    check(not help_filter.is_public_command("ha", make()), "niet in de openbare help")
    # one row per entity with its own word (the card's repeating rows)
    STATES["switch.feest_verlichting"] = {"state": "off", "attributes": {"friendly_name": "Feest verlichting"}}
    STATES["switch.overkaping"] = {"state": "on", "attributes": {"friendly_name": "Overkapping"}}
    rows = {"entity1_entity_id": "switch.feest_verlichting", "entity1_name": "feest", "entity1_switch": "true", "entity1_enabled": "true",
            "entity2_entity_id": "switch.overkaping", "entity2_name": "overkapping", "entity2_switch": "true", "entity2_enabled": "true",
            "entity3_entity_id": "sensor.woonkamer_temperatuur", "entity3_name": "temp", "entity3_switch": "false", "entity3_enabled": "true",
            "entity4_entity_id": "light.tuinlicht", "entity4_name": "tuin", "entity4_switch": "true", "entity4_enabled": "false"}
    r = await run("ha", card=rows)
    check(r[0] == "HA (* = schakelbaar): feest *, overkapping *, temp", f"lijst met de eigen woorden; uitgezette regel weg ({r})")
    calls.clear()
    r = await run("ha feest aan", card=rows)
    check(calls == [("homeassistant", "turn_on", "switch.feest_verlichting")] and r == ["Gedaan. Feest verlichting: aan"], f"ha feest aan ({calls}, {r})")
    r = await run("ha overkapping uit", card=rows)
    check(calls[-1] == ("homeassistant", "turn_off", "switch.overkaping"), "ha overkapping uit")
    calls.clear()
    r = await run("ha feest", card=rows)
    check(calls == [("homeassistant", "toggle", "switch.feest_verlichting")] and r[0].startswith("Gedaan. Feest verlichting:"),
          f"ha feest zonder aan/uit: omzetten ({calls}, {r})")
    r = await run("ha feest status", card=rows)
    check(len(calls) == 1 and r[0].startswith("Feest verlichting:"), f"ha feest status: alleen de stand ({r})")
    r = await run("ha temp", card=rows)
    check(r == ["Woonkamer temperatuur: 21.4 °C"], f"lezen via het eigen woord ({r})")
    r = await run("ha temp aan", card=rows)
    check(r[0].startswith("'temp' mag niet geschakeld worden"), "alleen lezen: niet schakelen")
    r = await run("ha tuin aan", card=rows)
    check(r[0].startswith("'tuin' mag niet geschakeld worden") and calls[-1][2] != "light.tuinlicht", "uitgezette regel: niets")
    r = await run("ha feest_verlichting aan", card=rows)
    check(calls[-1] == ("homeassistant", "turn_on", "switch.feest_verlichting"), "de eigen naam van de entiteit werkt ook")
    # groups: every row can be in groups; 'ha tuin uit' switches all of the group that may be switched
    STATES["light.lamp_a"] = {"state": "on", "attributes": {"friendly_name": "Lamp A"}}
    STATES["light.lamp_b"] = {"state": "off", "attributes": {"friendly_name": "Lamp B"}}
    STATES["light.lamp_c"] = {"state": "off", "attributes": {"friendly_name": "Lamp C"}}
    grp = {"entity1_entity_id": "light.lamp_a", "entity1_name": "a", "entity1_switch": "true", "entity1_groups": "tuin, alles",
           "entity2_entity_id": "light.lamp_b", "entity2_name": "b", "entity2_switch": "true", "entity2_groups": "Tuin",
           "entity3_entity_id": "light.lamp_c", "entity3_name": "c", "entity3_switch": "true", "entity3_groups": "tuin",
           "entity4_entity_id": "sensor.woonkamer_temperatuur", "entity4_name": "temp", "entity4_groups": "tuin"}
    r = await run("ha", card=grp)
    check("tuin (groep van 4)" in r[0] and "alles (groep van 1)" in r[0], f"ha: groepen in de lijst ({r})")
    calls.clear()
    r = await run("ha tuin uit", card=grp)
    check(sorted(calls) == [("homeassistant", "turn_off", "light.lamp_a"), ("homeassistant", "turn_off", "light.lamp_b"),
                            ("homeassistant", "turn_off", "light.lamp_c")] and r == ["Gedaan, 3 uit: a, b, c"],
          f"ha tuin uit: alle schakelbare lampen, de sensor niet ({calls}, {r})")
    calls.clear()
    r = await run("ha tuin", card=grp)
    check(all(c[1] == "turn_off" for c in calls) and len(calls) == 3, f"ha tuin: er brandt er een, dus alles uit ({calls})")
    STATES["light.lamp_a"]["state"] = "off"
    calls.clear()
    r = await run("ha tuin om", card=grp)
    check(all(c[1] == "turn_on" for c in calls) and len(calls) == 3, f"alles uit: omzetten = allemaal aan ({calls})")
    r = await run("ha tuin status", card=grp)
    check("Woonkamer temperatuur: 21.4 °C" in " ".join(r) and "Lamp A" in " ".join(r), f"ha tuin status: stand van de groep ({r})")
    calls.clear()
    r = await run("ha a uit", card=grp)
    check(calls == [("homeassistant", "turn_off", "light.lamp_a")], "losse lamp blijft los te bedienen")
    mixed = dict(rows); mixed["control"] = "scene.film"
    r = await run("ha", card=mixed)
    check("film *" in r[0], "oude lijst werkt nog naast de regels")

asyncio.run(main())
print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
