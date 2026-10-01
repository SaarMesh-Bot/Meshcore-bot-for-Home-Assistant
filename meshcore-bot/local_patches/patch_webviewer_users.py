#!/usr/bin/env python3
"""Source patch: dashboard users with roles, and the dashboard in the bot's language (see modules/web_users.py).

- The Home Assistant sidebar (ingress, only from the Supervisor's own address 172.30.32.2) needs no second login: HA
  already checked the user, and the panel is for HA admins.
- Login: besides the add-on's web viewer password (admin, as before; name empty or "admin") named accounts from the
  Users page (Settings -> Users). A login is needed as soon as there is a password OR at least one account. Failed
  logins are limited per address. Logging out clears the whole session.
- Every request of a viewer is checked on the server (modules/web_users.may_request): GET only, only its pages and the
  read-only API paths those pages use. No live connection (socket.io) for viewers. On the Repeater page a viewer only
  gets its repeaters / repeater groups.
- Users page (/users) and its API (/api/users...), admin only (a viewer never gets that page).
- Every HTML page gets three small scripts: /webui/me.js (who is logged in), /webui/i18n.js (the dashboard texts in the
  bot's language, [Localization] language) and /webui/webui.js (translates the page, also what appears later, hides
  menu items a viewer cannot open, adds "Log out").
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


APP = "modules/web_viewer/app.py"

# 1. helpers + login needed with a password or with accounts; the role check right after it
patch(
    APP,
    """        # Authentication middleware (BUG-001)
        _EXEMPT_PATHS = frozenset([""",
    """        # (add-on) dashboard users (modules/web_users.py)
        import sqlite3 as _wu_sqlite3
        from contextlib import closing as _wu_closing
        from modules import web_users as _web_users

        def _wu_db():
            return _wu_closing(_wu_sqlite3.connect(self.db_path, timeout=30))

        def _wu_auth_on():
            return bool(self.web_viewer_password) or _web_users.any_users(_wu_db)

        def _wu_lang():
            try:
                return (self.config.get('Localization', 'language', fallback='en') or 'en').strip().lower()[:2]
            except Exception:
                return 'en'

        def _wu_from_ha():
            # the Home Assistant sidebar (ingress): HA already logged the user in (the panel is for HA admins only).
            # Trusted only when it really comes from the Supervisor's fixed internal address, never on the header alone.
            return bool(request.headers.get('X-Ingress-Path')) and request.remote_addr == '172.30.32.2'

        self._wu_db = _wu_db
        self._wu_from_ha = _wu_from_ha
        self._wu_auth_on = _wu_auth_on
        self._wu_lang = _wu_lang

        # Authentication middleware (BUG-001)
        _EXEMPT_PATHS = frozenset([""",
)

patch(
    APP,
    """        def require_auth():
            if not self.web_viewer_password:
                return  # Auth disabled — no password configured
            if request.path in _EXEMPT_PATHS or request.path.startswith('/static/'):
                return
            if session.get('authenticated'):
                return
            if request.path.startswith('/api/'):
                return make_response(jsonify({'error': 'Authentication required'}), 401)
            next_url = request.path
            return redirect(url_for('login', next=next_url))
""",
    """        def require_auth():
            if not _wu_auth_on():
                return  # Auth disabled — no password and no dashboard accounts
            if request.path in _EXEMPT_PATHS or request.path.startswith(('/static/', '/webui/')):
                return
            if _wu_from_ha():
                return
            if session.get('authenticated'):
                return
            if request.path.startswith('/api/'):
                return make_response(jsonify({'error': 'Authentication required'}), 401)
            next_url = request.path
            return redirect(url_for('login', next=next_url))

        @self.app.before_request
        def web_user_access():
            # (add-on) named accounts: reload the account on every request (a change or a delete works at once)
            g.web_user = None
            if _wu_from_ha():
                return
            if not session.get('authenticated') or not session.get('user'):
                return
            try:
                with _wu_db() as conn:
                    user = _web_users.get_user(conn, session.get('user'))
            except Exception as e:
                self.logger.error(f"web users: {e}")
                user = None
            if not user:
                session.clear()
                if request.path.startswith('/api/'):
                    return make_response(jsonify({'error': 'Authentication required'}), 401)
                return redirect(url_for('login'))
            session['role'] = user['role']
            g.web_user = user
            if _web_users.may_request(user, request.method, request.path):
                return
            if request.path.startswith(('/api/', '/socket.io')) or request.method not in ('GET', 'HEAD'):
                return make_response(jsonify({'error': 'Not allowed for this account (read-only)'}), 403)
            target = _web_users.first_page(user)
            if target and target != request.path:
                return redirect(target)
            return make_response('No pages are shared with this account. <a href="/logout">Log out</a>', 403)
""",
)

# 2. login with a name, rate limit, role in the session; logout clears everything
patch(
    APP,
    """            if not self.web_viewer_password:
                return redirect(url_for('index'))
            if request.method == 'POST':
                password = request.form.get('password', '')
                if password == self.web_viewer_password:
                    session['authenticated'] = True
                    next_url = request.args.get('next', '/')
                    parsed = urlparse(next_url)
                    if parsed.scheme or parsed.netloc or not next_url.startswith('/'):
                        next_url = '/'
                    return redirect(next_url)
                return render_template('login.html', error='Invalid password')
            return render_template('login.html')
""",
    """            if not _wu_auth_on():
                return redirect(url_for('index'))
            if request.method == 'POST':
                address = request.remote_addr or '?'
                if _web_users.login_blocked(address):
                    self.logger.warning(f"Web viewer: too many failed logins from {address}")
                    return render_template('login.html', error='Too many attempts. Try again in 15 minutes.'), 429
                name = ' '.join((request.form.get('username') or '').split())
                password = request.form.get('password', '')
                user = None
                if not name or name.lower() == 'admin':
                    if _web_users.same_secret(password, self.web_viewer_password or ''):
                        user = {'name': '', 'role': 'admin'}
                else:
                    try:
                        with _wu_db() as conn:
                            user = _web_users.authenticate(conn, name, password)
                    except Exception as e:
                        self.logger.error(f"web users: login: {e}")
                if user:
                    _web_users.login_ok(address)
                    session.clear()
                    session.permanent = True
                    session['authenticated'] = True
                    session['user'] = user['name']
                    session['role'] = user['role']
                    next_url = request.args.get('next', '/')
                    parsed = urlparse(next_url)
                    if parsed.scheme or parsed.netloc or not next_url.startswith('/'):
                        next_url = '/'
                    if user['role'] != 'admin' and not _web_users.may_request(user, 'GET', next_url):
                        next_url = _web_users.first_page(user) or '/'
                    self.logger.info(f"Web viewer: login {user['name'] or 'admin'} ({user['role']}) from {address}")
                    return redirect(next_url)
                _web_users.login_failed(address)
                self.logger.warning(f"Web viewer: failed login{' for ' + name if name else ''} from {address}")
                return render_template('login.html', error='Invalid name or password')
            return render_template('login.html')
""",
)

patch(
    APP,
    """            \"\"\"Logout and clear session\"\"\"
            session.pop('authenticated', None)
            return redirect(url_for('login'))
""",
    """            \"\"\"Logout and clear session\"\"\"
            session.clear()
            if not _wu_auth_on():
                return redirect(url_for('index'))
            return redirect(url_for('login'))

        @self.app.route('/users')
        def users_page():
            # (add-on) Users: dashboard accounts (admin only; a viewer never gets this page)
            return render_template('users.html')

        @self.app.route('/api/users')
        def api_users():
            try:
                with _wu_db() as conn:
                    users = _web_users.list_users(conn)
                    groups = _web_users.list_groups(conn)
                    reps = []
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='repeater_telemetry'").fetchone():
                        reps = [{'key': k, 'name': n or k[:10]} for k, n in conn.execute(
                            "SELECT repeater_key, repeater_name FROM repeater_telemetry WHERE id IN "
                            "(SELECT MAX(id) FROM repeater_telemetry GROUP BY repeater_key) ORDER BY repeater_name COLLATE NOCASE")]
                return jsonify({
                    'users': users, 'groups': groups, 'repeaters': reps,
                    'pages': [{'id': k, 'label': v['label'], 'path': v['path']} for k, v in _web_users.PAGES.items()],
                    'password_set': bool(self.web_viewer_password),
                    'me': session.get('user') or ('admin' if session.get('authenticated') else None),
                })
            except Exception as e:
                self.logger.error(f"Error in /api/users: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/users/save', methods=['POST'])
        def api_users_save():
            data = request.get_json(silent=True) or {}
            try:
                with _wu_db() as conn:
                    before = _web_users.get_user(conn, data.get('name') or '')
                    if not self.web_viewer_password and data.get('role') != 'admin' \\
                            and not any(u['role'] == 'admin' and u['name'].lower() != str(data.get('name') or '').strip().lower()
                                        for u in _web_users.list_users(conn)):
                        return jsonify({'error': 'Make an admin account first (or set the add-on password): '
                                                 'otherwise nobody can get in as admin.'}), 400
                    user = _web_users.save_user(conn, data)
                self.logger.info(f"Web viewer: account {user['name']} {'changed' if before else 'added'} ({user['role']})")
                return jsonify({'user': user})
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                self.logger.error(f"Error in /api/users/save: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/users/delete', methods=['POST'])
        def api_users_delete():
            name = str((request.get_json(silent=True) or {}).get('name') or '')
            try:
                with _wu_db() as conn:
                    gone = _web_users.get_user(conn, name)
                    if not gone:
                        return jsonify({'error': 'No such account'}), 404
                    others = [u for u in _web_users.list_users(conn) if u['name'].lower() != gone['name'].lower()]
                    if not self.web_viewer_password and others and not any(u['role'] == 'admin' for u in others):
                        return jsonify({'error': 'This is the last admin account and there is no add-on password: '
                                                 'nobody could get in as admin any more.'}), 400
                    _web_users.delete_user(conn, name)
                self.logger.info(f"Web viewer: account {name} deleted")
                return jsonify({'deleted': True})
            except Exception as e:
                self.logger.error(f"Error in /api/users/delete: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        @self.app.route('/api/users/group', methods=['POST'])
        def api_users_group():
            data = request.get_json(silent=True) or {}
            try:
                with _wu_db() as conn:
                    if data.get('delete'):
                        return jsonify({'deleted': _web_users.delete_group(conn, data.get('name') or '')})
                    return jsonify({'group': _web_users.save_group(conn, data.get('name'), data.get('repeaters'))})
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                self.logger.error(f"Error in /api/users/group: {e}", exc_info=True)
                return jsonify({'error': 'Internal error - see server logs'}), 500

        # ---- the dashboard in the bot's language + who is logged in (modules/local_data/webui.js, ui_i18n.json)
        _wu_data = Path(__file__).resolve().parent.parent / 'local_data'
        _wu_i18n_cache = {}

        def _wu_js(body, cache):
            resp = make_response(body)
            resp.headers['Content-Type'] = 'application/javascript; charset=utf-8'
            resp.headers['Cache-Control'] = 'private, max-age=3600' if cache else 'no-store'
            return resp

        @self.app.route('/webui/me.js')
        def webui_me():
            user = getattr(g, 'web_user', None)
            if _wu_from_ha():
                return _wu_js('window.WEBUI_ME = ' + json.dumps({'auth': bool(_wu_auth_on()), 'user': None, 'role': 'admin',
                                                                  'pages': [], 'lang': _wu_lang(), 'ha': True}) + ';', False)
            me = {
                'auth': bool(_wu_auth_on()),
                'user': (user or {}).get('name') or ('admin' if session.get('authenticated') else None),
                'role': (user or {}).get('role') or ('admin' if session.get('authenticated') or not _wu_auth_on() else None),
                'pages': [_web_users.PAGES[p]['path'] for p in (user or {}).get('pages') or [] if p in _web_users.PAGES],
                'lang': _wu_lang(),
            }
            return _wu_js('window.WEBUI_ME = ' + json.dumps(me) + ';', False)

        @self.app.route('/webui/i18n.js')
        def webui_i18n():
            lang = _wu_lang()
            if lang not in _wu_i18n_cache:
                table = {}
                try:
                    table = json.loads((_wu_data / 'ui_i18n.json').read_text(encoding='utf-8')).get(lang) or {}
                except Exception as e:
                    self.logger.error(f"webui: ui_i18n.json: {e}")
                _wu_i18n_cache[lang] = 'window.WEBUI_I18N = ' + json.dumps(table, ensure_ascii=False) + ';'
            return _wu_js(_wu_i18n_cache[lang], True)

        @self.app.route('/webui/webui.js')
        def webui_js():
            try:
                return _wu_js((_wu_data / 'webui.js').read_text(encoding='utf-8'), True)
            except OSError:
                return _wu_js('', False)

        @self.app.after_request
        def webui_inject(response):
            # (add-on) the three scripts in every dashboard page, right before </head>
            try:
                if (response.status_code == 200 and response.mimetype == 'text/html'
                        and not response.direct_passthrough and not request.path.startswith('/webui/')):
                    html = response.get_data(as_text=True)
                    at = html.find('</head>')
                    if at != -1 and '/webui/webui.js' not in html:
                        v = f"{_wu_lang()}-{int((_wu_data / 'ui_i18n.json').stat().st_mtime) if (_wu_data / 'ui_i18n.json').exists() else 0}"
                        tags = (f'<script src="/webui/me.js"></script><script src="/webui/i18n.js?v={v}"></script>'
                                f'<script src="/webui/webui.js?v={v}"></script>')
                        response.set_data(html[:at] + tags + html[at:])
            except Exception as e:
                self.logger.debug(f"webui inject: {e}")
            return response
""",
)

# 3. no live connection for viewers; also needed when only accounts (no password) exist
patch(
    APP,
    """                if self.web_viewer_password and not session.get('authenticated'):
                    self.logger.warning(f"Rejected unauthenticated SocketIO connection from {client_id}")""",
    """                if not self._wu_from_ha() and ((self._wu_auth_on() and not session.get('authenticated'))
                                               or session.get('role') == 'viewer'):
                    self.logger.warning(f"Rejected unauthenticated SocketIO connection from {client_id}")""",
)

# 4. Repeater page: a viewer only gets its repeaters
patch(
    APP,
    """                return jsonify(repeater_page.summary(self.db_manager, request.args.get('key'), request.args.get('days', '7')))""",
    """                allowed = None
                if getattr(g, 'web_user', None):
                    with self._wu_db() as conn:
                        allowed = _web_users.allowed_repeaters(conn, g.web_user)
                return jsonify(repeater_page.summary(self.db_manager, request.args.get('key'), request.args.get('days', '7'),
                                                     allowed=allowed))""",
)

# 5. menu: Settings -> Users
patch(
    "modules/web_viewer/templates/base.html",
    """                                    <i class="fas fa-triangle-exclamation fa-fw me-2"></i>Problems
                                </a>
                            </li>""",
    """                                    <i class="fas fa-triangle-exclamation fa-fw me-2"></i>Problems
                                </a>
                            </li>
                            <li>
                                <a class="dropdown-item {{ 'active' if request.path == '/users' }}" href="/users">
                                    <i class="fas fa-users fa-fw me-2"></i>Users
                                </a>
                            </li>""",
)

# 6. login form: a name field (empty = the add-on password, as before)
patch(
    "modules/web_viewer/templates/login.html",
    """                    <p class="login-hint mb-0">Enter your password to continue.</p>""",
    """                    <p class="login-hint mb-0">Sign in with your name and password. Admin: leave the name empty.</p>""",
)
patch(
    "modules/web_viewer/templates/login.html",
    """                    <div class="mb-3">
                        <label for="password" class="form-label fw-medium">Password</label>
                        <input type="password" class="form-control" id="password" name="password"
                               autofocus autocomplete="current-password" required>
                    </div>""",
    """                    <div class="mb-3">
                        <label for="username" class="form-label fw-medium">Name</label>
                        <input type="text" class="form-control" id="username" name="username"
                               autofocus autocomplete="username" autocapitalize="none" spellcheck="false">
                    </div>
                    <div class="mb-3">
                        <label for="password" class="form-label fw-medium">Password</label>
                        <input type="password" class="form-control" id="password" name="password"
                               autocomplete="current-password" required>
                    </div>""",
)
