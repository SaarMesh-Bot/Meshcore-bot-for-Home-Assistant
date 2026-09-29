#!/usr/bin/env python3
"""Source patch: GET /api/botnet for the "Bots in the network" part of the Bots page (see modules/bot_network.py).

Runs after patch_webviewer_bots.py (it anchors on the /api/bots/set route that patch added). Read-only: the bots heard on
the network channel with their last hello and status, totals, and the channel and bot names they shared.
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
    "modules/web_viewer/app.py",
    """        @self.app.route('/api/bots/set', methods=['POST'])
        def api_bots_set():""",
    """        @self.app.route('/api/botnet')
        def api_botnet():
            \"\"\"Bots in the network (card BotNetwork): read-only.\"\"\"
            import logging as _logging
            from types import SimpleNamespace
            from modules import bot_network
            try:
                bot = SimpleNamespace(config=self.config, db_manager=self.db_manager, logger=self.logger or _logging.getLogger('botnet'))
                return jsonify(bot_network.summary(bot))
            except Exception as e:
                self.logger.error(f"Error in /api/botnet: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/bots/set', methods=['POST'])
        def api_bots_set():""",
)
