#!/usr/bin/env python3
"""Source patch: a "Games" page in the web viewer (see modules/games_admin.py, templates/games.html).

Runs once during the Docker build, after patch_webviewer_bots.py (it anchors on the Bots menu item).

Adds to the dashboard:
- a "Games" item in the top navigation, right after Bots;
- GET /games (the page) and GET /api/games (read-only: Mesh RPG, DX Jacht, karma, check-in streaks, voorspel and
  the F1 prediction game, bots left out);
- the Farming Idle tab: GET /api/games/farm (all players, market, buy orders) and POST /api/games/farm/orders (+ /<id>/delete)
  for the market's buy orders, the only thing the page writes (under the viewer's X-Requested-With check).
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
    """        @self.app.route('/region-warnings')
        def region_warnings_page():""",
    """        @self.app.route('/games')
        def games_page():
            \"\"\"Games: standings of every game on the mesh (see modules/games_admin.py).\"\"\"
            return render_template('games.html')

        @self.app.route('/api/games')
        def api_games():
            \"\"\"Read-only standings, bots left out, no public keys.\"\"\"
            from modules import games_admin
            try:
                return jsonify(games_admin.standings(self.db_manager, self.config, self.logger))
            except Exception as e:
                self.logger.error(f"Error in /api/games: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/games/farm')
        def api_games_farm():
            \"\"\"The Farming Idle tab: players, market, the market's buy orders (no public keys).\"\"\"
            from modules import games_admin
            try:
                return jsonify(games_admin.farm_overview(self.db_manager, self.config, self.logger))
            except Exception as e:
                self.logger.error(f"Error in /api/games/farm: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/games/farm/orders', methods=['POST'])
        def api_games_farm_order_add():
            \"\"\"A buy order of the market: {item, price, qty, days}.\"\"\"
            from modules import games_admin
            try:
                oid = games_admin.farm_order_add(self.db_manager, self.config, request.get_json(silent=True) or {})
                return jsonify({'id': oid})
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                self.logger.error(f"Error in /api/games/farm/orders: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/games/farm/season', methods=['POST'])
        def api_games_farm_season():
            \"\"\"Season settings: {enabled, length, rewards}.\"\"\"
            from modules import games_admin
            try:
                return jsonify(games_admin.farm_season_save(self.db_manager, self.config, request.get_json(silent=True) or {}))
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                self.logger.error(f"Error in /api/games/farm/season: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/games/farm/orders/<int:oid>/delete', methods=['POST'])
        def api_games_farm_order_delete(oid):
            from modules import games_admin
            try:
                return jsonify({'deleted': games_admin.farm_order_delete(self.db_manager, self.config, oid)})
            except Exception as e:
                self.logger.error(f"Error in /api/games/farm/orders delete: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/region-warnings')
        def region_warnings_page():""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <i class="fas fa-robot"></i> Bots
                        </a>
                    </li>
""",
    """                            <i class="fas fa-robot"></i> Bots
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if request.path == '/games' }}" href="/games">
                            <i class="fas fa-trophy"></i> Games
                        </a>
                    </li>
""",
)
