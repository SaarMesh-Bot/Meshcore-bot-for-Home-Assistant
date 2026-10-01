"""meshcore-proxy with a WiFi companion: serial_port = socket://ip:port (or tcp://, ip:port). A fake radio listens on
TCP; the proxy connects to it, a client on the proxy gets the radio's reply quickly, and the proxy reconnects when the
radio drops off."""
import asyncio
import importlib.util
import pathlib
import socket
import sys
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("proxy", HERE.parent / "meshcore-proxy" / "proxy.py")
proxy_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(proxy_mod)
fails = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


u = proxy_mod.radio_url
check(u("/dev/ttyACM0") == "/dev/ttyACM0" and u("/dev/serial/by-id/usb-Espressif_1:2") == "/dev/serial/by-id/usb-Espressif_1:2",
      "een apparaatpad blijft een apparaatpad (ook met een dubbele punt erin)")
check(u("socket://192.168.1.50:5000") == "socket://192.168.1.50:5000" and u("tcp://192.168.1.50:5000") == "socket://192.168.1.50:5000"
      and u("192.168.1.50:5000") == "socket://192.168.1.50:5000" and u("radio.local:5000") == "socket://radio.local:5000",
      "socket://, tcp:// en ip:poort worden socket://")


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


RADIO, LISTEN = free_port(), free_port()
radio_conns = []


def fake_radio(stop):
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", RADIO)); srv.listen(1); srv.settimeout(0.2)
    while not stop.is_set():
        try:
            c, _ = srv.accept()
        except socket.timeout:
            continue
        radio_conns.append(c)
        c.settimeout(0.2)
        while not stop.is_set():
            try:
                d = c.recv(100)
            except socket.timeout:
                continue
            except OSError:
                break
            if not d:
                break
            if d.startswith(b"<"):
                c.sendall(b">\x02\x00OK")      # a companion frame back
    srv.close()


async def main():
    stop = threading.Event()
    threading.Thread(target=fake_radio, args=(stop,), daemon=True).start()
    p = proxy_mod.Proxy(f"tcp://127.0.0.1:{RADIO}", 115200, "127.0.0.1", LISTEN, quiet_release=0.2, max_hold=2.0, priority_port=0)
    task = asyncio.create_task(p.run())
    await asyncio.sleep(0.8)
    check(p._tcp and p.ser is not None and len(radio_conns) == 1, "de proxy verbindt met de WiFi-radio (één verbinding)")
    r1, w1 = await asyncio.open_connection("127.0.0.1", LISTEN)
    r2, w2 = await asyncio.open_connection("127.0.0.1", LISTEN)
    await asyncio.sleep(0.1)
    t0 = time.monotonic()
    w1.write(b"<\x01\x00\x16"); await w1.drain()
    got = await asyncio.wait_for(r1.readexactly(5), 2)
    check(got == b">\x02\x00OK" and time.monotonic() - t0 < 0.5, f"antwoord van de radio snel bij de client ({time.monotonic() - t0:.2f}s)")
    got2 = await asyncio.wait_for(r2.readexactly(5), 2)
    check(got2 == b">\x02\x00OK", "de andere client krijgt het ook (na de beurt)")
    check(len(radio_conns) == 1, "twee clients, nog steeds één verbinding met de radio")
    radio_conns[0].close()                      # the radio drops off WiFi
    await asyncio.sleep(3.5)
    check(len(radio_conns) == 2, "radio weg en terug: de proxy verbindt opnieuw")
    w1.write(b"<\x01\x00\x16"); await w1.drain()
    check(await asyncio.wait_for(r1.readexactly(5), 2) == b">\x02\x00OK", "daarna werkt het weer")
    p._stop = True; stop.set(); task.cancel()
    for w in (w1, w2):
        w.close()

asyncio.run(main())
print(f"\n{len(fails)} fouten")
sys.exit(1 if fails else 0)
