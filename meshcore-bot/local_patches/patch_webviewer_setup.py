#!/usr/bin/env python3
"""Source patch: the first-start wizard (see modules/setup_wizard.py, templates/setup.html).

GET /setup (the page), GET /api/setup (current choices), POST /api/setup/apply (write them: cards through the same
settings store as the Plugins page, the bot's channels through the Supervisor's add-on options). A menu item "Setup"
under Settings, and on a new installation ([Setup] done = false) the start page opens the wizard and a banner is on
every other page, until the wizard is saved.
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
    """        @self.app.route('/api/plugins/<kind>/<name>', methods=['POST'])
        def api_plugins_save(kind: str, name: str):""",
    """        @self.app.context_processor
        def setup_banner():
            \"\"\"(add-on) show the first-start wizard banner until it is done.\"\"\"
            try:
                from modules.setup_wizard import is_done
                return {'setup_pending': not is_done(self.config)}
            except Exception:
                return {'setup_pending': False}

        def _setup_inputs():
            from modules.settings_schema import build_plugin_settings_view
            self.config = self._load_merged_config()
            view = build_plugin_settings_view(self.config, logger=self.logger,
                                              local_commands_dir=str(self.local_dir / "commands"),
                                              local_services_dir=str(self.local_dir / "service_plugins"))
            with self.db_manager.connection() as conn:
                has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='channels'").fetchone()
                radio = [r[0] for r in conn.execute("SELECT channel_name FROM channels ORDER BY channel_idx")] if has else []
            return view, [n for n in radio if n]

        @self.app.before_request
        def setup_first():
            \"\"\"(add-on) a new installation opens on the wizard until it is saved (the start page only).\"\"\"
            if request.method == 'GET' and request.path == '/':
                try:
                    from modules.setup_wizard import is_done
                    if not is_done(self._load_merged_config()):
                        return redirect('/setup')
                except Exception:
                    return None
            return None

        @self.app.route('/setup')
        def setup_page():
            \"\"\"(add-on) First-start wizard.\"\"\"
            return render_template('setup.html')

        @self.app.route('/api/setup')
        def api_setup():
            from modules import setup_wizard
            try:
                view, radio = _setup_inputs()
                return jsonify(setup_wizard.state(view, self.config, radio))
            except Exception:
                self.logger.exception("Error in /api/setup")
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/setup/apply', methods=['POST'])
        def api_setup_apply():
            \"\"\"(add-on) Write the wizard's answers: cards via the settings store, channels via the Supervisor.\"\"\"
            import json as _json
            import os as _os
            import urllib.request
            from modules import setup_wizard
            try:
                data = request.get_json(silent=True) or {}
                view, _radio = _setup_inputs()
                updates, channels, restart = setup_wizard.plan(data, view, self.config)
                by_target = {}
                for section, values in updates.items():
                    target = self.local_config_path if section in self._local_sections else self.config_path
                    by_target.setdefault(target, {})[section] = values
                for target, sections in by_target.items():
                    if not _os.path.exists(target):
                        _os.makedirs(_os.path.dirname(target), exist_ok=True)
                        open(target, 'w', encoding='utf-8').close()
                    get_settings_store(self.config, target, self.db_manager).write_sections(sections, {})
                options_saved = None
                if channels is not None:
                    token = _os.environ.get('SUPERVISOR_TOKEN', '')
                    if not token:
                        options_saved = False
                    else:
                        auth = {'Authorization': f'Bearer {token}'}
                        info = _json.load(urllib.request.urlopen(urllib.request.Request(
                            'http://supervisor/addons/self/info', headers=auth), timeout=15))
                        opts = info['data']['options']
                        opts.setdefault('bot', {})['channels'] = channels
                        req = urllib.request.Request('http://supervisor/addons/self/options', method='POST',
                                                     data=_json.dumps({'options': opts}).encode(),
                                                     headers={**auth, 'Content-Type': 'application/json'})
                        urllib.request.urlopen(req, timeout=15).read()
                        options_saved = True
                try:
                    with self.db_manager.connection() as conn:
                        conn.execute("INSERT INTO channel_operations (operation_type, status) VALUES ('config_reload', 'pending')")
                        conn.commit()
                except Exception:
                    self.logger.exception("Failed to queue config reload")
                self.logger.info("Setup wizard applied (%d sections, channels %s)", len(updates),
                                 'changed' if channels is not None else 'unchanged')
                return jsonify({'success': True, 'restart_required': bool(restart or channels is not None),
                                'channels_saved': options_saved})
            except Exception:
                self.logger.exception("Error in /api/setup/apply")
                return jsonify({'success': False, 'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/plugins/<kind>/<name>', methods=['POST'])
        def api_plugins_save(kind: str, name: str):""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """                            <li><hr class="dropdown-divider"></li>
                            <li>
                                <a class="dropdown-item {{ 'active' if request.path == '/config' }}" href="/config">""",
    """                            <li>
                                <a class="dropdown-item {{ 'active' if request.path == '/setup' }}" href="/setup">
                                    <i class="fas fa-wand-magic-sparkles fa-fw me-2"></i>Setup
                                </a>
                            </li>
                            <li><hr class="dropdown-divider"></li>
                            <li>
                                <a class="dropdown-item {{ 'active' if request.path == '/config' }}" href="/config">""",
)

patch(
    "modules/web_viewer/templates/base.html",
    """    <!-- Main Content -->
    <div class="container-fluid mt-4">
        {% block content %}{% endblock %}""",
    """    <!-- Main Content -->
    <div class="container-fluid mt-4">
        {% if setup_pending and request.path != '/setup' %}
        <div class="alert alert-info d-flex flex-wrap align-items-center gap-2" role="status">
            <i class="fas fa-wand-magic-sparkles"></i>
            <span class="me-auto">New here? The setup takes two minutes: channels, which commands, and a few extras.</span>
            <a class="btn btn-sm btn-primary" href="/setup">Start the setup</a>
        </div>
        {% endif %}
        {% block content %}{% endblock %}""",
)
