#!/usr/bin/env python3
"""Source patch: the greeting in the language of the person who is greeted (with AutoLanguage on).

The greeter is started outside the command path, so AutoLanguage never reached it: a French "Bonne soirée et bonne
nuit" got "Welkom op de mesh" with Dutch mesh info (seen 2026-10-03). Now the language of the message that triggers the
greeting is detected (modules/sender_language.py: only with [AutoLanguage] enabled, only nl/en/de/fr/da, words such as
"hallo" that several of them share keep the bot's language). When it is another language than the bot's:

- the greeting is the card's text for that language (Greeter card, "Greeting in French" = greeting_message_fr), or
  else the standard greeting in that language (translation key greeter_lang.greeting);
- the mesh info uses mesh_info_format_<lang> from the config, or else the standard text (greeter_lang.mesh_info).

The bot's own language keeps the normal greeting_message and mesh_info_format, exactly as before.
"""
import pathlib
import sys

ROOT = pathlib.Path.cwd()


def patch(path: str, old: str, new: str) -> None:
    p = ROOT / path
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        sys.exit(
            f"PATCH FAILED - anchor text found {count} time(s) in {path} "
            f"(expected 1; upstream code likely changed):\n{old!r}"
        )
    p.write_text(text.replace(old, new))
    print(f"Patched {path}")


F = "modules/commands/greeter_command.py"
LANG_NAMES = (("nl", "Dutch"), ("en", "English"), ("de", "German"), ("fr", "French"), ("da", "Danish"))

patch(
    F,
    """        {"key": "auto_backfill", "label": "Auto-backfill greeted users", "type": "bool",""",
    "".join(
        f"""        {{"key": "greeting_message_{code}", "label": "Greeting in {name}", "type": "str", "default": "",
         "help": "Only with AutoLanguage on: for someone whose first message is in {name}. Empty = the standard {name} greeting. Not used when {name} is the bot's own language."}},
""" for code, name in LANG_NAMES)
    + """        {"key": "auto_backfill", "label": "Auto-backfill greeted users", "type": "bool",""",
)

patch(
    F,
    """            greeting_parts = await self._format_greeting_parts(message.sender_id, message.channel)
""",
    """            # (add-on) the language of the person greeted, when AutoLanguage is on (modules/sender_language.py)
            try:
                from ..sender_language import detect as _detect_lang
                self._greet_lang = _detect_lang(self.bot.config, getattr(message, 'content', '') or '')
            except Exception:  # noqa: BLE001
                self._greet_lang = None
            try:
                greeting_parts = await self._format_greeting_parts(message.sender_id, message.channel)
            finally:
                self._greet_lang = None
""",
)

patch(
    F,
    """        # A greeting that ends in "|" sends the mesh info as its own message
""",
    """        # (add-on) another language than the bot's: that language's greeting and mesh info
        _mesh_format = self.mesh_info_format
        _lang = getattr(self, '_greet_lang', None)
        if _lang:
            greeting_template, _mesh_format = self._texts_in_language(_lang, greeting_template, _mesh_format)

        # A greeting that ends in "|" sends the mesh info as its own message
""",
)

patch(
    F,
    """                mesh_info_text = self.mesh_info_format.format(""",
    """                mesh_info_text = _mesh_format.format(""",
)

patch(
    F,
    """    async def _format_greeting_parts(self, sender_id: str,""",
    """    def _texts_in_language(self, lang: str, greeting: str, mesh_format: str) -> tuple:
        \"\"\"(greeting, mesh info format) for another language: the card's own text, else the standard one.\"\"\"
        from ..sender_language import own_text
        cfg = self.bot.config

        def standard(key: str) -> str:
            try:
                tr = self.bot.get_translator(lang)
                text = tr.translate(key) if tr is not None else ''
            except Exception:  # noqa: BLE001
                text = ''
            return '' if not text or text == key else text

        g = own_text(cfg, 'Greeter_Command', 'greeting_message', lang) or standard('greeter_lang.greeting')
        m = own_text(cfg, 'Greeter_Command', 'mesh_info_format', lang)
        if not m:
            m = standard('greeter_lang.mesh_info')
            g_used = g or greeting
            if m and not g_used.rstrip().endswith('|'):
                m = '\\n' + m   # mesh info on its own line under a greeting without "|"
        return (decode_escape_sequences(g) if g else greeting), (decode_escape_sequences(m) if m else mesh_format)

    async def _format_greeting_parts(self, sender_id: str,""",
)
