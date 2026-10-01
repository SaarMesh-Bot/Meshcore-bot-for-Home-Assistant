#!/usr/bin/env python3
"""
'farm' command for the MeshCore Bot: the Farming Idle game (see modules/farm_game.py). Played by direct message, because a
DM carries the sender's key (nobody can play in your name); 'farm top' also works in a channel.

  farm                     your farm: level, coins, what is ripe or when
  farm start               open your farm (4 fields, 200 coins)
  farm winkel [gewas [n]]  the seed shop: the list, one crop's details, or buy n seeds for the barn (also: farm zaad)
  farm seizoen             this month's season: top 5, your points (farm XP this month), rewards for the top 3
  farm ruim <gewas|nr|alles>  clear fields to sow something else (a plant gives several harvests, then the field is empty)
  farm zaai tomaat 2       sow (own seeds first, then bought)        farm oogst      harvest everything that is ripe
  farm schuur              what is in your barn                      farm verkoop [x] sell (everything, or one item)
  farm verwerk jam 2       process in the workshop (soup, jam, wine, ...)
  farm bank / stort 100 / haal 100    the bank: 1% interest a day, safe from the pickpocket
  farm upgrade [veld|kas|grond|werkplaats]   farm geef <name> 100   farm top
  farm opdracht            today's task (reward: coins, farm XP and 5 Mesh RPG XP)
  farm markt / bied jam 3 60 / koop 2 / intrekken 2   the market between players (markt also in a channel)
  farm lever jam [n]       sell to the market's buy order (set on the dashboard: Games -> Farming Idle), paid at once
"""

from typing import Any

from ..farm_game import FarmGame
from ..mesh_community import is_bot_name, without_bots
from ..models import MeshMessage
from .base_command import BaseCommand

START = {"start", "begin", "beginnen", "starten", "commencer"}
SOW = {"zaai", "zaaien", "plant", "planten", "sow", "säen", "saen", "säe", "sème", "seme", "semer", "planter"}
HARVEST = {"oogst", "oogsten", "harvest", "ernte", "ernten", "récolte", "recolte", "récolter", "recolter"}
BARN = {"schuur", "voorraad", "barn", "inventory", "scheune", "lager", "grange", "stock"}
SELL = {"verkoop", "verkopen", "sell", "verkaufe", "verkaufen", "vendre", "vends"}
PROCESS = {"verwerk", "verwerken", "maak", "make", "process", "mach", "koche", "fabrique", "préparer", "preparer"}
SHOP = {"winkel", "shop", "laden", "boutique", "zaad", "zaden", "seeds", "samen", "graines"}
BANK = {"bank", "banque"}
DEPOSIT = {"stort", "storten", "deposit", "einzahlen", "déposer", "deposer"}
WITHDRAW = {"haal", "opnemen", "withdraw", "abheben", "retirer"}
UPGRADE = {"upgrade", "upgrades", "verbeter", "ausbau", "amélioration", "amelioration"}
GIVE = {"geef", "give", "gib", "donne", "donner"}
TOP = {"top", "ranking", "rangliste", "classement"}
QUEST = {"opdracht", "opdrachten", "quest", "task", "aufgabe", "mission", "tache", "tâche"}
MARKET = {"markt", "marktplaats", "market", "marche", "marché"}
OFFER = {"bied", "aanbieden", "offer", "biete", "offre", "offrir"}
BUY = {"koop", "kopen", "buy", "kaufe", "kaufen", "achete", "achète", "acheter"}
CANCEL = {"intrekken", "annuleer", "cancel", "zurueck", "zurück", "annuler"}
SEASON = {"seizoen", "season", "saison"}
CLEAR = {"ruim", "opruimen", "clear", "räume", "raeume", "räumen", "vide", "vider"}
DELIVER = {"lever", "leveren", "deliver", "liefere", "liefern", "livre", "livrer"}


class FarmCommand(BaseCommand):
    """Farming Idle: grow, harvest, process and sell crops; levels 1-10."""

    name = "farm"
    keywords = ["farm"]
    description = "Farming Idle: a farming game by DM - grow crops, harvest, process them (soup, jam, wine, ...), sell, bank, level 1-10"
    category = "games"

    short_description = "Farming game (by DM)"
    usage = "farm [start|winkel|zaai <gewas> [n]|oogst|schuur|verkoop [x]|verwerk <product> [n]|opdracht|markt|bied|koop|lever|bank|upgrade|geef|top]"
    examples = ["farm start", "farm zaai tomaat 4", "farm oogst", "farm opdracht", "farm markt", "farm top"]

    settings_schema = [
        {"key": "crops_off", "label": "Crops that are off", "type": "list", "default": [],
         "help": ("Crops players cannot buy on this bot (and their products), for example wiet. Choose from: tomaat, "
                  "aardbei, pompoen, wiet, druif, zonnebloem, appel, hop, koffie, cacao. Fields already sown keep growing.")},
    ]

    def __init__(self, bot: Any):
        super().__init__(bot)
        self.farm_enabled = self.get_config_value("Farm_Command", "enabled", fallback=True, value_type="bool")
        raw = self.get_config_value("Farm_Command", "crops_off", fallback="") or ""
        self.crops_off = {c.strip().lower() for c in str(raw).strip("[]").replace("'", "").split(",") if c.strip()}
        self._game = None

    @property
    def game(self) -> FarmGame:
        if self._game is None:
            self._game = FarmGame(self.bot.db_manager, self.crops_off)
        return self._game

    def can_execute(self, message: MeshMessage, skip_channel_check: bool = False) -> bool:
        if not self.farm_enabled:
            return False
        return super().can_execute(message, skip_channel_check=skip_channel_check)

    def get_help_text(self) -> str:
        return self.translate("commands.farm.help")

    def _arguments(self, message: MeshMessage) -> list:
        tokens = (message.content or "").split()
        for i, token in enumerate(tokens):
            if token.lstrip("!/").lower() in self.keywords:
                return tokens[i + 1:]
        return []

    async def _reply(self, message: MeshMessage, texts: list) -> bool:
        texts = [t for t in texts if t]
        if len(texts) == 1:
            return await self.send_response(message, texts[0])
        return await self.send_response_chunked(message, texts[:3])

    async def execute(self, message: MeshMessage) -> bool:
        try:
            args = self._arguments(message)
            sub = args[0].lower() if args else ""
            rest = args[1:]
            if sub in TOP:
                return await self._top(message)
            if sub in MARKET:
                return await self._reply(message, self.game.market(self.translate))
            if not message.is_dm or not message.sender_pubkey:
                if not message.is_dm and await self._invite_by_dm(message):
                    return True
                return await self.send_response(message, self.translate("commands.farm.dm_only", bot=self._bot_name()))
            name = (message.sender_id or "").strip()
            if is_bot_name(self.bot, name):
                return await self.send_response(message, self.translate("commands.games.no_bots", name=name))
            key, t, g = message.sender_pubkey.lower(), self.translate, self.game

            def count(words):
                nums = [w for w in words if w.isdigit()]
                return int(nums[-1]) if nums else None

            def word(words):
                return next((w for w in words if not w.isdigit()), "")

            if sub == "":
                out = g.status(key, name, t)
            elif sub in START:
                out = g.start(key, name, t)
            elif sub in SHOP:
                out = g.shop(key, t, word(rest), count(rest))
            elif sub in SEASON:
                out = g.season(key, t)
            elif sub in CLEAR:
                out = g.clear(key, word(rest) or (rest[0] if rest else ""), t)
            elif sub in SOW:
                out = g.sow(key, name, word(rest), count(rest), t) if word(rest) else [t("commands.farm.sow_usage")]
            elif sub in HARVEST:
                out = g.harvest(key, name, t)
            elif sub in BARN:
                out = g.barn(key, t)
            elif sub in SELL:
                out = g.sell(key, name, word(rest), count(rest), t)
            elif sub in PROCESS:
                out = g.process(key, name, word(rest), count(rest), t)
            elif sub in BANK:
                action = "in" if rest and rest[0].lower() in DEPOSIT else ("out" if rest and rest[0].lower() in WITHDRAW else "")
                out = g.bank(key, name, action, rest[1] if len(rest) > 1 else "", t)
            elif sub in DEPOSIT or sub in WITHDRAW:
                out = g.bank(key, name, "in" if sub in DEPOSIT else "out", rest[0] if rest else "", t)
            elif sub in QUEST:
                out = g.quest(key, name, t)
            elif sub in OFFER:
                nums = [int(w) for w in rest if w.isdigit()]
                out = g.offer(key, name, word(rest), nums[0] if nums else None, nums[1] if len(nums) > 1 else None, t)
            elif sub in BUY:
                out = g.buy(key, name, rest[0] if rest else "", t)
            elif sub in CANCEL:
                out = g.withdraw(key, rest[0] if rest else "", t)
            elif sub in DELIVER:
                out = g.deliver(key, name, word(rest), count(rest), t) if word(rest) else [t("commands.farm.deliver_usage")]
            elif sub in UPGRADE:
                out = g.upgrade(key, name, word(rest), t)
            elif sub in GIVE:
                if len(rest) < 2 or not rest[-1].isdigit():
                    out = [t("commands.farm.give_usage")]
                else:
                    out = g.give(key, name, " ".join(rest[:-1]), rest[-1], t)
            else:
                out = [t("commands.farm.usage")]
            return await self._reply(message, out)
        except Exception as e:
            self.logger.error(f"Error executing farm command: {e}", exc_info=True)
            return await self.send_response(message, self.translate("commands.farm.error"))

    def _contact_key(self, name: str) -> str:
        """Public key of the one contact on the radio with exactly this name ("" when none or more than one)."""
        name = (name or "").strip()
        contacts = getattr(getattr(self.bot, "meshcore", None), "contacts", None) or {}
        if not name or not isinstance(contacts, dict):
            return ""
        keys = [str(c.get("public_key") or k).lower() for k, c in contacts.items()
                if isinstance(c, dict) and (c.get("adv_name") or c.get("name") or "").strip() == name]
        return keys[0] if len(keys) == 1 else ""

    async def _invite_by_dm(self, message: MeshMessage) -> bool:
        """'farm' in a channel: the bot opens a DM with that person, so they can answer there at once. Only when the
        sender's name matches exactly one contact on the radio, not for bots, and at most once per person per day
        (a channel message carries only a name, so someone could use another's name)."""
        name = (message.sender_id or "").strip()
        if not name or is_bot_name(self.bot, name):
            return False
        key = self._contact_key(name)
        cm = getattr(self.bot, "command_manager", None)
        if not key or cm is None or not hasattr(cm, "send_dm"):
            return False
        import time as _time
        day = _time.strftime("%Y-%m-%d")
        meta_key = f"farm.dm_invite.{key[:12]}"
        db = self.bot.db_manager
        if db.get_metadata(meta_key) == day:
            return False
        has_farm = self.game.has_player(key)
        text = self.translate("commands.farm.dm_invite_player" if has_farm else "commands.farm.dm_invite", name=name[:30])
        if not await cm.send_dm(key, text, skip_user_rate_limit=True):
            return False
        db.set_metadata(meta_key, day)
        self.logger.info(f"Farming Idle: DM gestuurd aan {name} (farm in een kanaal)")
        await self.send_response(message, self.translate("commands.farm.dm_sent", name=name[:30]))
        return True

    def _bot_name(self) -> str:
        """The bot's name as people see it in their contacts, for "open a DM with ..." (the text says where to go)."""
        return (self.bot.config.get("Bot", "bot_name", fallback="") or "de bot").strip()

    async def _top(self, message: MeshMessage) -> bool:
        rows = without_bots(self.bot, self.game.top(15), 5)
        if not rows:
            return await self.send_response(message, self.translate("commands.farm.top_empty"))
        return await self.send_response(message, self.translate("commands.farm.top_head") + " | ".join(
            f"{i} {n} L{lvl} {worth}" for i, (n, lvl, worth) in enumerate(rows, 1)))
