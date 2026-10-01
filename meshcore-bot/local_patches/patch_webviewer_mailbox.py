#!/usr/bin/env python3
"""Source patch: a "Mailbox" page in the web viewer (see modules/mailbox.py, templates/mailbox.html).

Runs after patch_webviewer_radar.py (it anchors on the Radar menu item). Adds a Mailbox item to the top navigation,
GET /mailbox (the page), GET /api/mailbox (every message of the last 30 days with its status; the text of a message
left by DM is not shown) and POST /api/mailbox/<id>/delete (take a message out; under the viewer's X-Requested-With
check).
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
    """        @self.app.route('/radar')""",
    """        @self.app.route('/mailbox')
        def mailbox_page():
            \"\"\"(add-on) Mailbox: messages left with 'post' (modules/mailbox.py).\"\"\"
            return render_template('mailbox.html')

        @self.app.route('/api/mailbox')
        def api_mailbox():
            from modules import mailbox
            try:
                return jsonify(mailbox.overview(self.db_manager))
            except Exception as e:
                self.logger.error(f"Error in /api/mailbox: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/mailbox/<int:mid>/delete', methods=['POST'])
        def api_mailbox_delete(mid):
            from modules import mailbox
            try:
                return jsonify({'deleted': mailbox.remove(self.db_manager, mid)})
            except Exception as e:
                self.logger.error(f"Error in /api/mailbox delete: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/radar')""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <i class="fas fa-satellite-dish"></i> Radar
                        </a>
                    </li>
""",
    """                            <i class="fas fa-satellite-dish"></i> Radar
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if request.path == '/mailbox' }}" href="/mailbox">
                            <i class="fas fa-envelope"></i> Mailbox
                        </a>
                    </li>
""",
)
