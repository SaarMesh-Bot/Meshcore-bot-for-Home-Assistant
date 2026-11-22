#!/usr/bin/env python3
"""Source patch: a "Watchlist" page in the web viewer (see modules/watchlist.py, templates/watchlist.html).

Runs after patch_webviewer_mailbox.py (it anchors on the Mailbox route and menu item). Adds a Watchlist item to the
top navigation, right after Mailbox, and:
- GET  /watchlist                  the page (admin only: a viewer account never gets it, see modules/web_users.py)
- GET  /api/watchlist              settings, watched senders with their statistics, the hit log
- POST /api/watchlist/reset        {"target": name}: the next message of that sender gets a DM again
- POST /api/watchlist/clear-hits   empties the hit log
- POST /api/watchlist/test         a test note through the configured Home Assistant service
Settings are saved through the existing plugin API (/api/plugins/service/watchlist), as on the card.
POSTs are under the viewer's X-Requested-With check.
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
    """        @self.app.route('/mailbox')
""",
    """        @self.app.route('/watchlist')
        def watchlist_page():
            \"\"\"(add-on) Watchlist: watched senders, their DMs and hits (modules/watchlist.py).\"\"\"
            return render_template('watchlist.html')

        @self.app.route('/api/watchlist')
        def api_watchlist():
            from modules import watchlist
            try:
                return jsonify(watchlist.overview(self.db_manager, self._load_merged_config()))
            except Exception as e:
                self.logger.error(f"Error in /api/watchlist: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/watchlist/reset', methods=['POST'])
        def api_watchlist_reset():
            from modules import watchlist
            try:
                target = str((request.get_json(silent=True) or {}).get('target', ''))
                return jsonify({'reset': watchlist.reset_cooldown(self.db_manager, target)})
            except Exception as e:
                self.logger.error(f"Error in /api/watchlist/reset: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/watchlist/clear-hits', methods=['POST'])
        def api_watchlist_clear_hits():
            from modules import watchlist
            try:
                watchlist.clear_hits(self.db_manager)
                return jsonify({'cleared': True})
            except Exception as e:
                self.logger.error(f"Error in /api/watchlist/clear-hits: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/watchlist/test', methods=['POST'])
        def api_watchlist_test():
            from modules import watchlist
            try:
                ok, detail = watchlist.send_test_note(self._load_merged_config())
                return jsonify({'ok': ok, 'detail': detail}), (200 if ok else 502)
            except Exception as e:
                self.logger.error(f"Error in /api/watchlist/test: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/mailbox')
""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <i class="fas fa-envelope"></i> Mailbox
                        </a>
                    </li>
""",
    """                            <i class="fas fa-envelope"></i> Mailbox
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if request.path == '/watchlist' }}" href="/watchlist">
                            <i class="fas fa-eye"></i> Watchlist
                        </a>
                    </li>
""",
)
