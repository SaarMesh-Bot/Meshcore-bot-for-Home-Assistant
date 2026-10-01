#!/usr/bin/env python3
"""Source patch: a "Problems" page in the web viewer (Settings -> Problems; see modules/problem_log.py).

Runs after patch_webviewer_setup.py (it anchors on the Setup menu item and route). GET /problems (the page) and
GET /api/problems?days=1|7|14: the bot's warnings and errors grouped per kind, and commands it did not answer.
POST /api/problems/dismiss and /api/problems/clear: 'Done' after looking into it (under the X-Requested-With check).
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
    """        @self.app.route('/setup')""",
    """        @self.app.route('/problems')
        def problems_page():
            \"\"\"(add-on) Problems: warnings, errors and unanswered commands (modules/problem_log.py).\"\"\"
            return render_template('problems.html')

        @self.app.route('/api/problems')
        def api_problems():
            import sqlite3 as _sqlite3
            from contextlib import closing as _closing
            from modules import problem_log
            try:
                days = request.args.get('days', 1, type=int) or 1
                with _closing(_sqlite3.connect(self.db_path, timeout=30)) as conn:
                    return jsonify(problem_log.summary(conn, days))
            except Exception as e:
                self.logger.error(f"Error in /api/problems: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/problems/dismiss', methods=['POST'])
        def api_problems_dismiss():
            \"\"\"(add-on) 'Done': {type: problem, level, kind} or {type: command, key}.\"\"\"
            import sqlite3 as _sqlite3
            from contextlib import closing as _closing
            from modules import problem_log
            try:
                with _closing(_sqlite3.connect(self.db_path, timeout=30)) as conn:
                    return jsonify({'dismissed': problem_log.dismiss(conn, request.get_json(silent=True) or {})})
            except Exception as e:
                self.logger.error(f"Error in /api/problems/dismiss: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/problems/clear', methods=['POST'])
        def api_problems_clear():
            import sqlite3 as _sqlite3
            from contextlib import closing as _closing
            from modules import problem_log
            try:
                with _closing(_sqlite3.connect(self.db_path, timeout=30)) as conn:
                    problem_log.clear_all(conn)
                return jsonify({'cleared': True})
            except Exception as e:
                self.logger.error(f"Error in /api/problems/clear: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/setup')""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                                    <i class="fas fa-wand-magic-sparkles fa-fw me-2"></i>Setup
                                </a>
                            </li>""",
    """                                    <i class="fas fa-wand-magic-sparkles fa-fw me-2"></i>Setup
                                </a>
                            </li>
                            <li>
                                <a class="dropdown-item {{ 'active' if request.path == '/problems' }}" href="/problems">
                                    <i class="fas fa-triangle-exclamation fa-fw me-2"></i>Problems
                                </a>
                            </li>""",
)
