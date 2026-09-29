#!/usr/bin/env python3
"""Source patch: a "Restart now" banner on the Plugins page when a change needs a restart.

Commands reload at once, but a service (MapUploader, BotNetwork, ...) only starts or stops when the bot starts. Upstream
said so in a small line inside the card (hidden when the card is collapsed) and the dashboard had no way to restart.
Now a banner appears at the top of the page, with a button that restarts the add-on through Home Assistant's
Supervisor (POST /addons/self/restart, the add-on has hassio_api); the page reloads itself once the bot is back.
POST /api/addon/restart falls under the viewer's X-Requested-With check like every other POST.
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
    """        @self.app.route('/api/addon/restart', methods=['POST'])
        def api_addon_restart():
            \"\"\"(add-on) Restart the whole add-on via the Supervisor, a second after answering.\"\"\"
            import os as _os
            import threading
            import urllib.request
            token = _os.environ.get('SUPERVISOR_TOKEN', '')
            if not token:
                return jsonify({'error': 'Not running as a Home Assistant add-on'}), 400

            def _restart():
                import time as _time
                _time.sleep(1.0)
                try:
                    req = urllib.request.Request('http://supervisor/addons/self/restart', method='POST',
                                                 headers={'Authorization': f'Bearer {token}'})
                    urllib.request.urlopen(req, timeout=30).read()
                except Exception as e:  # the restart itself ends this process; only log real failures
                    self.logger.warning(f"Add-on restart request: {e}")
            self.logger.info("Add-on restart requested from the Plugins page")
            threading.Thread(target=_restart, daemon=True).start()
            return jsonify({'restarting': True})

        @self.app.route('/api/plugins/<kind>/<name>', methods=['POST'])
        def api_plugins_save(kind: str, name: str):""",
)

HTML = "modules/web_viewer/templates/plugins.html"
patch(
    HTML,
    """    <div class="plugins-toolbar mb-3">""",
    """    <div class="plugins-toolbar mb-3">
        <!-- (add-on) inside the toolbar, which stays at the top while scrolling, so the banner is always in sight -->
        <div class="alert alert-warning d-none d-flex flex-wrap align-items-center gap-2 py-2 mb-2" id="restart-banner" role="status">
            <i class="fas fa-rotate"></i>
            <span class="me-auto" id="restart-text">A change needs a restart of the bot to take effect.</span>
            <button type="button" class="btn btn-sm btn-warning" id="restart-now"><i class="fas fa-power-off"></i> Restart now</button>
        </div>""",
)
patch(
    HTML,
    """            if (data.restart_required) msg += ' Restart the bot to start/stop this service.';""",
    """            if (data.restart_required) msg += ' Restart the bot to start/stop this service.';
            if (data.restart_required) this.showRestart(plugin.label || plugin.name);""",
)
patch(
    HTML,
    """    setStatus(el, msg, type) {""",
    """    // (add-on) banner at the top: which changes wait for a restart, and a button to restart now
    showRestart(label) {
        this.pendingRestart = this.pendingRestart || [];
        if (!this.pendingRestart.includes(label)) this.pendingRestart.push(label);
        const banner = document.getElementById('restart-banner');
        document.getElementById('restart-text').textContent =
            'Takes effect after a restart of the bot: ' + this.pendingRestart.join(', ') + '.';
        banner.classList.remove('d-none');
        const btn = document.getElementById('restart-now');
        if (btn.dataset.bound) return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', async () => {
            if (!confirm('Restart the MeshCore Bot add-on now? It is back in about half a minute.')) return;
            btn.disabled = true;
            const text = document.getElementById('restart-text');
            text.textContent = 'Restarting... this page reloads when the bot is back.';
            try {
                const resp = await fetch('/api/addon/restart', { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
                if (!resp.ok) throw new Error((await resp.json().catch(() => ({}))).error || ('HTTP ' + resp.status));
            } catch (err) {
                text.textContent = 'Restart failed: ' + err.message + '. Restart the add-on in Home Assistant instead.';
                btn.disabled = false;
                return;
            }
            const started = Date.now();
            let sawDown = false;   // reload only once the old bot was gone and the new one answers
            const poll = async () => {
                try {
                    const r = await fetch('/api/plugins', { cache: 'no-store' });
                    if (r.ok && (sawDown || Date.now() - started > 90000)) { window.location.reload(); return; }
                    if (!r.ok) sawDown = true;
                } catch (e) { sawDown = true; }
                if (Date.now() - started > 180000) {
                    text.textContent = 'The bot is taking long to come back; reload this page in a moment.';
                    return;
                }
                setTimeout(poll, 3000);
            };
            poll();
        });
    }

    setStatus(el, msg, type) {""",
)
