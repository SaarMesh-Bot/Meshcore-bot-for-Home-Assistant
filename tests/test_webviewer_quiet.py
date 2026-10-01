"""Web viewer: live events only to subscribed pages, and a stop signal is not a crash (patch_webviewer_quiet.py).
Runs in the simulated build tree: test_webviewer_quiet.py <tree>."""
import os
import re
import sys
import threading
import types
import logging

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


app = open(os.path.join(TREE, "modules", "web_viewer", "app.py")).read()
check(not re.search(r"socketio\.emit\([^)]*room=None", app), "geen enkel live-bericht meer naar alle open pagina's")
check(app.count("to=_sid)") == 6, f"zes soorten live-berichten alleen naar wie zich aanmeldde ({app.count('to=_sid)')})")

integ = open(os.path.join(TREE, "modules", "web_viewer", "integration.py")).read()
start = integ.index("            if self.running and self.viewer_process and self.viewer_process.poll() is not None:")
block = integ[start:integ.index("                self.restart_viewer()\n                return", start) + len("                self.restart_viewer()\n                return")]
code = "def monitor(self, time):\n" + "\n".join(line[8:] if line.startswith("        ") else line for line in block.splitlines())
ns = {}
exec(code, ns)


class Rec(logging.Handler):
    def __init__(self):
        super().__init__(); self.records = []

    def emit(self, r):
        self.records.append(r)


def run(code_, shutting=False, later=False):
    rec = Rec()
    log = logging.getLogger(f"wv{code_}{shutting}{later}"); log.addHandler(rec); log.setLevel(logging.DEBUG); log.propagate = False
    ev = threading.Event()
    if shutting:
        ev.set()
    restarted = []
    self = types.SimpleNamespace(running=True, shutting_down=False, logger=log,
                                 viewer_process=types.SimpleNamespace(poll=lambda: code_, returncode=code_),
                                 bot=types.SimpleNamespace(_shutdown_event=ev, connected=True),
                                 restart_viewer=lambda: restarted.append(1))
    fake_time = types.SimpleNamespace(sleep=lambda s: ev.set() if later else None)
    ns["monitor"](self, fake_time)
    return [r.levelname for r in rec.records], restarted


levels, restarted = run(-15, later=True)
check(levels == ["INFO"] and not restarted, f"stopsignaal tijdens het stoppen van de bot: info, geen herstart ({levels})")
levels, restarted = run(-15)
check(levels == ["INFO"] and restarted == [1], f"stopsignaal terwijl de bot doorloopt: info, dashboard weer gestart ({levels})")
levels, restarted = run(1)
check("WARNING" in levels and restarted == [1], f"echte crash: nog steeds een waarschuwing en herstart ({levels})")

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
