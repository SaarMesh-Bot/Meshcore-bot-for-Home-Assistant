#!/usr/bin/env python3
"""Source patch: on the dashboard's Plugins page, the on/off switch of a card saves at once.

Upstream only changes the look of the card when the switch is flipped; the change is lost unless the Save button is
pressed as well (GitHub issue #1: "no autosave when pushing the slider"). Now flipping the switch runs the same save
as the button (it also saves other changed fields of that card).
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
    "modules/web_viewer/templates/plugins.html",
    """        toggle.addEventListener('change', () => {
            card.classList.toggle('disabled', !toggle.checked);
        });""",
    """        toggle.addEventListener('change', () => {
            card.classList.toggle('disabled', !toggle.checked);
            // (add-on) save at once: a flipped switch is not lost when Save is forgotten
            this.save(plugin, toggle, inputs, saveBtn, status, dynamicEditors, blockEditors);
        });""",
)
