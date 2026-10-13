"""The language of the person who wrote a message, for texts the bot sends without a command (greeting, channel hint).

Commands already answer in the sender's language when AutoLanguage is on (patch_sender_language_detection.py); the
greeter and the channel hint are started outside that path, so they always used the bot's own language: a French
"Bonne soirée" got "Welkom op de mesh" (seen 2026-10-03). This module gives them the same choice:

    detect(cfg, text) -> "fr" / "en" / ... or None (= keep the bot's language)

Only with [AutoLanguage] enabled, only the five languages the add-on has texts for, and never a switch on a word that
several of those languages share ("hallo" is Dutch, German and Danish: a Dutch bot keeps Dutch). Detection is upstream's
modules/lang_detector.py: a list of greetings for short messages, langdetect for anything longer than two words.
Short command words ("test", "ping") are not recognised and keep the bot's language.
"""
from __future__ import annotations

from typing import Any, Optional

SUPPORTED = ("nl", "en", "de", "fr", "da")

# words that are normal in more than one of our languages: no switch when the bot's language is one of them
SHARED_WORDS = {
    "hallo": {"nl", "de", "da"},
    "hoi": {"nl", "de"},
    "moin": {"nl", "de", "da"},
    "hej": {"da", "nl"},
    "tak": {"da", "nl"},
    "welkom": {"nl"},
    "bitte": {"de"},
    "salut": {"fr", "nl"},
    "merci": {"fr", "nl"},
}


def bot_language(cfg: Any) -> str:
    lang = (cfg.get("Localization", "language", fallback="en") if cfg.has_section("Localization") else "en") or "en"
    return lang.strip().lower()[:2]


def auto_on(cfg: Any) -> bool:
    try:
        return cfg.has_section("AutoLanguage") and cfg.getboolean("AutoLanguage", "enabled", fallback=False)
    except (ValueError, AttributeError):
        return False


def detect(cfg: Any, text: str) -> Optional[str]:
    """The sender's language when it is not the bot's own (and AutoLanguage is on), else None."""
    if not text or not auto_on(cfg):
        return None
    own = bot_language(cfg)
    clean = " ".join(str(text).lower().replace("@[", " ").split())
    first = clean.strip("!?.,;: ").split(" ")[0] if clean else ""
    if own in SHARED_WORDS.get(clean.strip("!?.,;: "), ()) or own in SHARED_WORDS.get(first, ()):
        return None
    try:
        from .lang_detector import detect_language
    except Exception:  # noqa: BLE001
        return None
    try:
        lang = detect_language(text, SUPPORTED, fallback=own)
    except Exception:  # noqa: BLE001
        return None
    lang = (lang or own)[:2]
    return None if lang == own or lang not in SUPPORTED else lang


def own_text(cfg: Any, section: str, key: str, lang: str) -> str:
    """The text set on a card for one language (`<key>_<lang>`), '' when empty."""
    if not lang or not cfg.has_section(section):
        return ""
    return (cfg.get(section, f"{key}_{lang}", fallback="") or "").strip()
