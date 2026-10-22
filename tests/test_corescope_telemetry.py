"""CoreScopeTelemetry: welche Messwerte aus Home Assistant als MQTT-Telemetrie an CoreScope gehen (ohne Broker, ohne Funk)."""
import pathlib as _pl
_TESTS = _pl.Path(__file__).resolve().parent
FIXTURES = str(_TESTS / "fixtures")
import asyncio, configparser, json, logging, os, sys, time, types
sys.path.insert(0, sys.argv[1]); os.chdir(sys.argv[1])
sys.path.insert(0, FIXTURES)
import ha_states as F
K64 = F.KEY[:64]       # a real MeshCore key has 64 hex characters (the shared fixture's is longer)

def k64(states):
    return [dict(st, attributes=dict(st["attributes"], public_key=K64))
            if (st.get("attributes") or {}).get("public_key") == F.KEY else st for st in states]

from modules.service_plugins.corescope_telemetry_service import CoreScopeTelemetryService, build_payload

fails = []
def check(c, m):
    print(("OK   " if c else "FAIL ") + m)
    if not c: fails.append(m)

def make(**extra):
    cfg = configparser.ConfigParser()
    cfg["CoreScopeTelemetry"] = {"enabled": "true", "host": "broker.example", "port": "8883", "tls": "true",
                                 "username": "u", "password": "p", "region": "scn", "repeaters": "",
                                 "read_interval_minutes": "10", "max_age_hours": "6", **extra}
    log = logging.getLogger("t"); log.handlers = []
    return CoreScopeTelemetryService(types.SimpleNamespace(config=cfg, logger=log, db_manager=None))

NOW = time.time()
svc = make()
check(svc.region == "SCN" and svc.interval == 600 and svc.max_age_s == 6 * 3600, "Karte gelesen (Region gross, Intervall, Alter)")

states = k64(F.repeater_states(NOW, mv=3920, age=900)) + F.room_states(NOW)
due = svc.due(states, NOW)
check(len(due) == 1, f"nur der Repeater, nicht der Room-Server ({len(due)})")
pk, payload, key = due[0]
check(pk == K64 and payload["public_key"] == K64, "voller 64-stelliger Schlüssel")
check(payload["battery_mv"] == 3920 and payload["temperature_c"] == 21.4, f"Akku und Temperatur ({payload})")
check(payload["ts"] == time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 900)), "ts = Zeitpunkt der Messung, nicht des Sendens")
check(payload["source"] == "ha-bot", "Quelle markiert")

svc._sent[pk] = key
check(svc.due(states, NOW) == [], "dieselbe Messung wird nicht nochmal gesendet")
newer = k64(F.repeater_states(NOW, stats_key="2026-09-21T19:30:00", mv=3900, age=60))
check(len(svc.due(newer, NOW)) == 1, "neue Messung wird gesendet")

old = k64(F.repeater_states(NOW, stats_key="x-old", mv=3800, age=7 * 3600))
check(make().due(old, NOW) == [], "zu alte Messung (Repeater antwortet nicht mehr) wird übersprungen")

offline = [dict(st, state="off") if st["entity_id"].startswith("binary_sensor.") and "online" in st["entity_id"] else st
           for st in k64(F.repeater_states(NOW))]
check(make().due(offline, NOW) == [], "offline gemeldeter Repeater wird übersprungen")

check(make(repeaters="ffff").due(states, NOW) == [], "Filter auf andere Schlüssel: nichts")
check(len(make(repeaters=F.KEY[:6]).due(states, NOW)) == 1, "Filter auf diesen Schlüssel: gesendet")

check(build_payload({"public_key": "abcd", "battery_mv": 4000}) is None, "nur Präfix bekannt: nichts (kein Geister-Node)")
check(build_payload({"public_key": K64}) is None, "keine Werte: nichts")

class FakeClient:
    def __init__(self): self.sent = []
    def publish(self, topic, data, qos=0): self.sent.append((topic, json.loads(data), qos)); return types.SimpleNamespace(rc=0)

async def run():
    s = make(); s._client = FakeClient(); s.connected = True
    async def fetch(): return states
    s._fetch = fetch
    n1 = await s.run_once(); n2 = await s.run_once()
    return s, n1, n2
s, n1, n2 = asyncio.run(run())
check(n1 == 1 and n2 == 0 and s.published == 1, f"run_once publiziert einmal ({n1}, {n2})")
topic, data, qos = s._client.sent[0]
check(topic == f"meshcore/SCN/{K64}/telemetry" and qos == 1, f"Topic und QoS ({topic})")

s2 = make(); s2.connected = False
check(asyncio.run(s2.run_once()) == 0, "ohne Broker-Verbindung: nichts, kein Absturz")
off = make(enabled="false"); asyncio.run(off.start())
check(off._task is None and off._client is None, "ausgeschaltet: startet nicht")

print(f"\n{'ALLES OK' if not fails else f'{len(fails)} fouten'}")
sys.exit(1 if fails else 0)
