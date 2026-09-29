#!/usr/bin/env python3
"""Source patch: a "Repeater" page in the web viewer (see modules/repeater_page.py, templates/repeater.html).

Runs after patch_webviewer_radar.py (it anchors on the Channel radar route and menu item). Adds a menu item right after
Channel radar, GET /repeater (the page) and GET /api/repeater?key=&days=1|7|30 (read-only history of the repeaters the
HARepeater service follows: battery, temperature, noise floor, airtime, signal, neighbours).
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
    """        @self.app.route('/radar')
        def radar_page():""",
    """        @self.app.route('/repeater')
        def repeater_page():
            \"\"\"Repeater: history of the repeaters the HARepeater service follows (see modules/repeater_page.py).\"\"\"
            return render_template('repeater.html')

        @self.app.route('/api/repeater')
        def api_repeater():
            \"\"\"Read-only telemetry of one repeater over 1, 7 or 30 days, plus its latest neighbour list.\"\"\"
            from modules import repeater_page
            try:
                return jsonify(repeater_page.summary(self.db_manager, request.args.get('key'), request.args.get('days', '7')))
            except Exception as e:
                self.logger.error(f"Error in /api/repeater: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/radar')
        def radar_page():""",
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
                        <a class="nav-link {{ 'active' if request.path == '/repeater' }}" href="/repeater">
                            <i class="fas fa-broadcast-tower"></i> Repeater
                        </a>
                    </li>
""",
)
