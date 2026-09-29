#!/usr/bin/env python3
"""Source patch: a "Bot network" page in the web viewer (see modules/bot_network.py, templates/botnet.html).

Runs after patch_webviewer_repeater.py (it anchors on the Repeater route and menu item) and patch_webviewer_botnet.py
(which added /api/botnet). Adds a menu item right after Repeater (only while the BotNetwork card is on), GET /botnet (the page) and GET /api/botnet/history?days=1|7|30
(read-only status numbers of every bot in the network, for the charts).
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
    """        @self.app.route('/repeater')
        def repeater_page():""",
    """        @self.app.context_processor
        def botnet_menu():
            \"\"\"The Bot network menu item only shows when the BotNetwork card is on.\"\"\"
            try:
                on = self.config.has_section('BotNetwork') and self.config.getboolean('BotNetwork', 'enabled', fallback=False)
            except Exception:
                on = False
            return {'botnet_enabled': on}

        @self.app.route('/botnet')
        def botnet_page():
            \"\"\"Bot network: the bots running this add-on, over the internet (see modules/bot_network.py).\"\"\"
            return render_template('botnet.html')

        @self.app.route('/api/botnet/history')
        def api_botnet_history():
            \"\"\"Read-only status numbers of every bot in the network over 1, 7 or 30 days.\"\"\"
            import logging as _logging
            from types import SimpleNamespace
            from modules import bot_network
            try:
                bot = SimpleNamespace(config=self.config, db_manager=self.db_manager, logger=self.logger or _logging.getLogger('botnet'))
                return jsonify(bot_network.history(bot, request.args.get('days', '7')))
            except Exception as e:
                self.logger.error(f"Error in /api/botnet/history: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/repeater')
        def repeater_page():""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <i class="fas fa-broadcast-tower"></i> Repeater
                        </a>
                    </li>
""",
    """                            <i class="fas fa-broadcast-tower"></i> Repeater
                        </a>
                    </li>
                    {% if botnet_enabled %}
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if request.path == '/botnet' }}" href="/botnet">
                            <i class="fas fa-network-wired"></i> Bot network
                        </a>
                    </li>
                    {% endif %}
""",
)
