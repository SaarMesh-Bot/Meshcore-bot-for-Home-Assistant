#!/usr/bin/env python3
"""Source patch: languages that only exist in the add-on's own catalogue count as available.

Upstream's Translator.get_available_languages() only lists translations/*.json, so AutoLanguage (and anything else
asking the bot which languages it has) never picked a language the add-on ships on its own (local/translations,
Danish since 2.46.0). Also a few Danish greetings for the keyword detector ("hej" alone stays out: Swedish too).
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


patch(
    "modules/i18n.py",
    """        languages = []
        trans_path = Path(self.translation_path)
        if trans_path.exists():
            for file in trans_path.glob('*.json'):
                languages.append(file.stem)""",
    """        languages = []
        trans_path = Path(self.translation_path)
        if trans_path.exists():
            for file in trans_path.glob('*.json'):
                languages.append(file.stem)
        # (add-on) languages only in our own catalogue (e.g. da)
        local_path = Path(self.local_translation_path)
        if local_path.exists():
            for file in local_path.glob('*.json'):
                languages.append(file.stem)""",
)

patch(
    "modules/lang_detector.py",
    """    # Portuguese
""",
    """    # Danish (add-on)
    "godmorgen": "da", "goddag": "da", "godaften": "da", "godnat": "da",
    "tak": "da", "mange tak": "da", "velkommen": "da", "hej hej": "da",
    # Portuguese
""",
)
