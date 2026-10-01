"""Dashboard: the live connection (socket.io) only starts on pages that use it (patch_webviewer_lazy_socket.py).
Renders /games and /realtime with the real viewer and, when node + jsdom are there, runs their scripts with a fake io()
that counts connections. Runs in the simulated build tree: test_lazy_socket.py <tree>."""
import configparser
import os
import shutil
import subprocess
import sys
import tempfile

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


from modules.web_viewer.app import BotDataViewer  # noqa: E402

work = tempfile.mkdtemp()
cfg = configparser.ConfigParser()
cfg["Bot"] = {"db_path": f"{work}/viewer.db", "bot_name": "Test|🤖"}
cfg["Web_Viewer"] = {"enabled": "true", "web_viewer_password": ""}
with open(f"{work}/config.ini", "w") as f:
    cfg.write(f)
v = BotDataViewer(config_path=f"{work}/config.ini")
v.app.config["TESTING"] = True
c = v.app.test_client()
pages = {}
for path in ("/games", "/radar", "/realtime"):
    html = c.get(path).get_data(as_text=True)
    pages[path] = f"{work}/{path.strip('/')}.html"
    open(pages[path], "w").write(html)
base = open(os.path.join(TREE, "modules", "web_viewer", "templates", "base.html")).read()
check("get socket()" in base and "this.initializeSocket();\n                this.startPingInterval();\n            }\n\n            initializeSocket" not in base,
      "base.html: de verbinding start pas als een pagina erom vraagt")

check("setInterval(pollBanners, 10000)" not in base and "if (!document.hidden) pollBanners()" in base, "bannercontrole: elke 30 s en alleen als zichtbaar")
node = shutil.which("node")
jsd = os.environ.get("JSDOM_PATH") or next((p for p in ("/tmp/meshcore-tests/jsd/node_modules", "/tmp/claude-0/jsd/node_modules")
                                            if os.path.isdir(os.path.join(p, "jsdom"))), None)
if node and jsd:
    script = f"""
const {{ JSDOM, VirtualConsole }} = require('jsdom');
const fs = require('fs');
for (const [name, file] of [['games', '{pages['/games']}'], ['radar', '{pages['/radar']}'], ['realtime', '{pages['/realtime']}']]) {{
  let html = fs.readFileSync(file, 'utf8').replace(/<script src="https:[^"]*socket\\.io[^"]*"><\\/script>/, '');
  let opened = 0;
  const dom = new JSDOM(html, {{ runScripts: 'dangerously', url: 'http://x/' + name, virtualConsole: new VirtualConsole(),
    beforeParse(w) {{
      w.io = function () {{ opened++; return {{ on() {{}}, emit() {{}}, connected: false }}; }};
      w.matchMedia = () => ({{ matches: false, addEventListener() {{}}, addListener() {{}} }});
      w.fetch = () => Promise.resolve({{ ok: true, status: 200, json: () => Promise.resolve({{}}) }});
    }} }});
  setTimeout(() => {{ console.log(name + ' ' + opened + ' ' + (dom.window.document.getElementById('connection-text') || {{}}).textContent); }}, 800);
}}
setTimeout(() => process.exit(0), 1500);
"""
    js = f"{work}/run.js"
    open(js, "w").write(script)
    out = subprocess.run([node, js], capture_output=True, text=True, env={**os.environ, "NODE_PATH": jsd}, timeout=60).stdout
    res = {line.split()[0]: line.split(" ", 2)[1:] for line in out.strip().splitlines() if line.strip()}
    check(res.get("games", ["?"])[0] == "0" and "Live: off" in res.get("games", ["", ""])[1], f"Games: geen live-verbinding, 'Live: off' ({res.get('games')})")
    check(res.get("radar", ["?"])[0] == "0", f"Radar: geen live-verbinding ({res.get('radar')})")
    check(res.get("realtime", ["0"])[0] == "1", f"Realtime: wel een live-verbinding, één ({res.get('realtime')})")
else:
    print("skip  browser-test (node/jsdom niet aanwezig)")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
