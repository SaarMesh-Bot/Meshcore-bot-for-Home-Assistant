"""meshcore-proxy: voorrangspoort - wie op de voorrangspoort zit, gaat voor wie op de gewone poort wacht."""
import asyncio, importlib.util, pathlib, sys, types

HERE = pathlib.Path(__file__).resolve().parent
sys.modules.setdefault("serial", types.ModuleType("serial"))           # pyserial is niet nodig voor deze test
spec = importlib.util.spec_from_file_location("proxy", HERE.parent / "meshcore-proxy" / "proxy.py")
proxy_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(proxy_mod)


class FakeSerial:
    is_open = True
    def __init__(self): self.writes = []
    def write(self, data): self.writes.append(data)


def make(priority_port=5011):
    p = proxy_mod.Proxy("/dev/null", 115200, "127.0.0.1", 5010, quiet_release=0.2, max_hold=2.0,
                        priority_port=priority_port)
    p.ser = FakeSerial()
    return p


async def order(prio_on: bool):
    p = make(5011 if prio_on else 0)
    a, b, bot = object(), object(), object()          # stand-ins voor de StreamWriters
    if prio_on:
        p.priority_clients.add(bot)
    first = asyncio.create_task(p.forward_to_device(b"A", a))      # A heeft de beurt
    await asyncio.sleep(0.05)
    t_b = asyncio.create_task(p.forward_to_device(b"B", b))        # B wacht eerst ...
    await asyncio.sleep(0.02)
    t_bot = asyncio.create_task(p.forward_to_device(b"BOT", bot))  # ... daarna de bot
    await asyncio.sleep(0.02)
    assert p.ser.writes == [b"A"], p.ser.writes                     # lopende beurt wordt niet onderbroken
    await asyncio.gather(first, t_b, t_bot)
    assert not p.turn_busy and p.priority_waiting == 0
    return p.ser.writes


assert asyncio.run(order(True)) == [b"A", b"BOT", b"B"]     # bot springt voor B
assert asyncio.run(order(False)) == [b"A", b"B", b"BOT"]    # uit: gewoon op volgorde
print("1 voorrang en volgorde: OK")


async def alone():
    p = make(); bot = object(); p.priority_clients.add(bot)
    await p.forward_to_device(b"X", bot)
    await p.forward_to_device(b"Y", object())                       # niemand wacht: gewone client gaat meteen
    assert p.ser.writes == [b"X", b"Y"] and not p.turn_busy


asyncio.run(alone())


async def serial_closed():
    p = make(); p.ser.is_open = False
    await p.forward_to_device(b"X", object())                       # beurt moet weer vrij zijn
    assert not p.turn_busy
    p.ser.is_open = True
    await asyncio.wait_for(p.forward_to_device(b"Y", object()), 2)
    assert p.ser.writes == [b"Y"]


asyncio.run(serial_closed())
print("2 vrijgeven, ook bij fouten: OK")


async def ports():
    p = make(); p.listen_port = 0; p.priority_port = 0
    # handle_priority_client markeert de client en ruimt hem op
    class R:
        async def read(self, n): return b""
    class W:
        def get_extra_info(self, k): return ("127.0.0.1", 1)
        def close(self): pass
    w = W()
    await p.handle_priority_client(R(), w)
    assert w not in p.priority_clients and w not in p.clients


asyncio.run(ports())
print("3 voorrangsclient op- en afmelden: OK")
print("ALLES OK")
