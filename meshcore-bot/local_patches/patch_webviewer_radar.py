#!/usr/bin/env python3
"""Source patch: a "Channel radar" page in the web viewer (see modules/channel_radar.py, templates/radar.html).

Runs after patch_webviewer_games.py (it anchors on the Games menu item). Adds a menu item right after Games,
GET /radar (the page) and GET /api/radar (read-only counts; no message content, nothing to change).
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
    """        @self.app.route('/radar')
        def radar_page():
            \"\"\"Channel radar: which hashtag channels are in use around the bot (see modules/channel_radar.py).\"\"\"
            return render_template('radar.html')

        @self.app.route('/api/radar')
        def api_radar():
            \"\"\"Read-only counts per channel and day; no message content.\"\"\"
            import logging as _logging
            from types import SimpleNamespace
            from modules import channel_radar
            try:
                bot = SimpleNamespace(config=self.config, db_manager=self.db_manager, logger=self.logger or _logging.getLogger('radar'))
                return jsonify(channel_radar.summary(bot))
            except Exception as e:
                self.logger.error(f"Error in /api/radar: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/radar/name', methods=['POST'])
        def api_radar_name():
            \"\"\"(add-on) 'Name it': {hash, name}. Kept only when logged messages of that channel byte really belong to
            '#name' (byte and check code); then the radar recognises it within a minute, no restart.\"\"\"
            from modules import channel_radar
            try:
                data = request.get_json(silent=True) or {}
                name = channel_radar.clean_name(data.get('name'))
                if not name:
                    return jsonify({'error': 'Type a hashtag name (no spaces).'}), 400
                hits = channel_radar.verify_name(self.db_manager, name, str(data.get('hash') or ''))
                if not hits:
                    return jsonify({'error': f'#{name} is not this channel.', 'match': False}), 400
                channel_radar.add_dashboard_name(self.db_manager, name)
                return jsonify({'match': True, 'name': '#' + name, 'messages': hits})
            except Exception as e:
                self.logger.error(f"Error in /api/radar/name: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/radar/channel', methods=['POST'])
        def api_radar_channel():
            \"\"\"(add-on) 'Add a channel': {name, key?}. #name = hashtag channel; a name with a 32-hex key = its own key.\"\"\"
            from modules import channel_radar
            try:
                data = request.get_json(silent=True) or {}
                return jsonify({'added': channel_radar.add_channel(self.db_manager, data.get('name'), data.get('key') or '')})
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                self.logger.error(f"Error in /api/radar/channel: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/radar/name/delete', methods=['POST'])
        def api_radar_name_delete():
            from modules import channel_radar
            try:
                data = request.get_json(silent=True) or {}
                return jsonify({'deleted': channel_radar.remove_channel(self.db_manager, data.get('name'))})
            except Exception as e:
                self.logger.error(f"Error in /api/radar/name/delete: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/radar/add_to_radio', methods=['POST'])
        def api_radar_add_to_radio():
            \"\"\"(add-on) 'Add to radio': a hashtag channel goes on the list AutoChannels makes on the radio (within a
            minute, only in a free slot that the radio itself reports empty; never overwrites).\"\"\"
            from modules import channel_radar
            try:
                data = request.get_json(silent=True) or {}
                return jsonify({'queued': channel_radar.request_add_to_radio(self.db_manager, data.get('name'))})
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                self.logger.error(f"Error in /api/radar/add_to_radio: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/radar/repeaters')
        def api_radar_repeaters():
            \"\"\"Repeater radar: the repeaters heard in the last 1, 7 or 30 days (see modules/repeater_radar.py).\"\"\"
            from modules import repeater_radar
            try:
                return jsonify(repeater_radar.summary(self.db_manager, self.config, request.args.get('days', '1')))
            except Exception as e:
                self.logger.error(f"Error in /api/radar/repeaters: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/region-warnings')
        def region_warnings_page():""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <i class="fas fa-trophy"></i> Games
                        </a>
                    </li>
""",
    """                            <i class="fas fa-trophy"></i> Games
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {{ 'active' if request.path == '/radar' }}" href="/radar">
                            <i class="fas fa-satellite-dish"></i> Radar
                        </a>
                    </li>
""",
)
