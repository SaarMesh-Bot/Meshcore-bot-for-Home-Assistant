"""Problems page (modules/problem_log.py): warnings and errors grouped per kind and per day, and commands without an
answer. Runs in the simulated build tree: test_problem_log.py <tree>."""
import json
import logging
import os
import sqlite3
import sys
import tempfile
import time

TREE = sys.argv[1] if len(sys.argv) > 1 else os.environ["SIM_TREE"]
os.chdir(TREE)
sys.path.insert(0, TREE)
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


from modules import problem_log as P  # noqa: E402

check(P.kind_of("Contact list at 99.7% capacity (349/350)") == P.kind_of("Contact list at 98.1% capacity (344/350)"),
      "getallen tellen niet: zelfde soort")
check(P.kind_of("Channel check: still missing after scan: ['#mowas', '#mowas-en']") == "Channel check: still missing after scan: […]",
      f"lijsten weggelaten ({P.kind_of(chr(39))})")
check("#" in P.kind_of("RoomServer_Login: inloggen op a1b2c3d4e5f6 mislukt"), "hex-sleutels weggelaten")

path = tempfile.mktemp()
log = logging.getLogger("MeshCoreBotTest")
log.propagate = False
h = P.install(log, path)
check(h is not None and P.install(log, path) is None, "handler maar één keer")
log.info("gewone info")                               # not stored
log.warning("Contact list at 99.7% capacity (349/350)")
log.warning("Contact list at 98.0% capacity (343/350)")
try:
    raise ValueError("kapot")
except ValueError:
    log.error("Error executing farm command: kapot", exc_info=True)
log.error("Web viewer stderr: 1.2.3.4 - - [..] POST /api/stream_data")   # dashboard request lines: skipped

now = time.time()
conn = sqlite3.connect(path)
conn.execute("CREATE TABLE packet_stream (timestamp REAL, type TEXT, data TEXT)")
rows = [("ping", True, "ping", "Pong"), ("ping", False, "ping", ""), ("trace", False, "trace", "Trace failed: x"), ("wx", True, "wx", "")]
for i, (cmd, ok, inp, resp) in enumerate(rows):
    conn.execute("INSERT INTO packet_stream VALUES (?, 'command', ?)", (now - i * 60, json.dumps(
        {"command": cmd, "success": ok, "user_input": inp, "user": "Carol", "channel": "#bot", "timestamp": now - i * 60, "response": resp})))
conn.execute("INSERT INTO packet_stream VALUES (?, 'command', ?)", (now - 300, json.dumps(
    {"command": "farm", "success": False, "user_input": "farm oogst", "user": "Vipje", "channel": None, "timestamp": now - 300,
     "response": "Geoogst: 12 tomaat (+8 xp)."})))
conn.execute("INSERT INTO packet_stream VALUES (?, 'command', ?)", (now - 3 * 86400, json.dumps({"command": "old", "success": False})))
conn.commit()
s = P.summary(conn, 1, now=now)
kinds = {p["kind"]: p for p in s["problems"]}
cap = kinds.get(P.kind_of("Contact list at 99.7% capacity (349/350)"))
check(cap and cap["count"] == 2 and cap["level"] == "WARNING" and "343/350" in cap["example"], f"twee waarschuwingen, één soort, laatste voorbeeld ({cap})")
err = [p for p in s["problems"] if p["level"] == "ERROR"]
check(len(err) == 1 and "ValueError: kapot" in err[0]["example"] and s["problems"][0]["level"] == "ERROR", "fout met oorzaak, fouten bovenaan")
check(s["errors"] == 1 and s["warnings"] == 2, "tellers")
check(s["commands"] == 5 and s["unanswered_total"] == 2 and s["unconfirmed_total"] == 1,
      f"commando's van 24 uur: 2 zonder antwoord, 1 DM zonder bevestiging ({s['commands']}, {s['unanswered_total']}, {s['unconfirmed_total']})")
farm_row = next(u for u in s["unanswered"] if u["command"] == "farm")
check(farm_row["kind"] == "unconfirmed" and farm_row["channel"] == "DM", "DM met antwoord maar zonder ACK: niet bevestigd, geen 'geen antwoord'")
check(sorted(f["command"] for f in s["failing_commands"]) == ["farm", "ping", "trace"] and s["failing_commands"][-1]["command"] == "farm",
      "per commando, echte fouten eerst")
check(any(u["user"] == "Carol" and u["channel"] == "#bot" for u in s["unanswered"]), "met wie en waar")
check(P.summary(conn, 7, now=now)["unanswered_total"] == 3, "7 dagen: ook de oudere")
# 'Done' after looking into it
farm_key = farm_row["key"]
check(P.dismiss(conn, {"type": "command", "key": farm_key}), "commando afgevinkt")
s2 = P.summary(conn, 1, now=now)
check(s2["unconfirmed_total"] == 0 and all(u["key"] != farm_key for u in s2["unanswered"]), "afgevinkt commando weg")
cap_kind = P.kind_of("Contact list at 99.7% capacity (349/350)")
check(P.dismiss(conn, {"type": "problem", "level": "WARNING", "kind": cap_kind}), "waarschuwing afgevinkt")
check(not any(p["kind"] == cap_kind for p in P.summary(conn, 1, now=now)["problems"]), "soort weg")
log.warning("Contact list at 97.0% capacity (340/350)")
check(any(p["kind"] == cap_kind and p["count"] == 1 for p in P.summary(conn, 1, now=now)["problems"]), "gebeurt het opnieuw: komt terug")
check(not P.dismiss(conn, {"type": "x"}), "onbekend: niets")
P.clear_all(conn, now=now + 1)
s3 = P.summary(conn, 7, now=now + 2)
check(s3["problems"] == [] and s3["unanswered_total"] == 0 and s3["unconfirmed_total"] == 0, "Clear all: alles weg")
conn.execute("INSERT INTO packet_stream VALUES (?, 'command', ?)", (now + 5, json.dumps(
    {"command": "ping", "success": False, "user_input": "ping", "user": "Z", "channel": "#bot", "timestamp": now + 5, "response": ""})))
conn.commit()
check(P.summary(conn, 1, now=now + 10)["unanswered_total"] == 1, "een nieuwe na Clear all is er gewoon")
conn.close()

print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
