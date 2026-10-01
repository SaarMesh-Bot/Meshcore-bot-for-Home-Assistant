# MeshCore Proxy – documentation

## Hardware

A MeshCore radio flashed with the **companion (USB)** firmware, connected by USB to the machine that runs
Home Assistant. The author uses the [Seeed XIAO ESP32S3 + Wio-SX1262 kit](https://www.seeedstudio.com/XIAO-ESP32S3-for-Meshtastic-LoRa-with-3D-Printed-Enclosure-p-6314.html) (sold as a Meshtastic
kit, flashed with MeshCore firmware from the [MeshCore project](https://github.com/meshcore-dev/MeshCore)).
Any other board that runs the MeshCore companion firmware over USB serial works the same way.

**A WiFi companion works too** (for example when Home Assistant runs in a virtual machine, such as Proxmox, and USB
passthrough is awkward). Flash the companion **WiFi** firmware, give the radio a fixed IP address in your router, and set
**Serial port** to `socket://<ip of the radio>:5000` (`tcp://...` or just `192.168.1.50:5000` work as well; 5000 is the
MeshCore default port). A WiFi companion accepts only one TCP connection at a time: the proxy is that one connection and
shares it with every client, exactly as with USB. Baud rate is ignored then. If the radio drops off WiFi, the proxy
reconnects every 2 seconds. Do not connect the MeshCore app to the radio over WiFi at the same time.

**Home Assistant in Proxmox:** either pass the USB radio through (Proxmox: VM -> Hardware -> Add -> USB Device -> *Use USB
Vendor/Device ID*, then stop and start the VM) or use a WiFi companion as above. Step by step: INSTALL.md, section
*Home Assistant in Proxmox*.

Typical clients: the **MeshCore Bot** add-on from this repository, the
[meshcore-ha](https://github.com/meshcore-dev/meshcore-ha) integration and, through it, the
[MeshCore Chat](https://github.com/mwolter805/meshcore-ha-chat) panel.

## Set-up

1. Plug in the radio and set **Serial port** to its path. A `/dev/serial/by-id/usb-...` path is the most
   stable one. If the port cannot be found, the add-on log lists the paths that exist.
2. Start the add-on. The log shows `Luistert op 0.0.0.0:5010` (the proxy's log messages are Dutch).
3. Point every program that used the USB device at the proxy instead:
   - **MeshCore Bot** add-on: *Connection type* `tcp`, host `localhost`, port `5011` (the priority port, so the bot's replies
     go first; `5010` works too, without priority).
   - **meshcore-ha** integration: connection type TCP, host `localhost`, port `5010`.

Start the proxy first, so the clients find it when they start.

## Options

| Option | Meaning |
|---|---|
| Serial port | Path of the radio, for example `/dev/ttyACM0`, or `socket://<ip>:5000` for a WiFi companion. |
| Baud rate | 115200 for MeshCore companion firmware. |
| Listen port | TCP port for clients. Default 5010. |
| Priority port | Clients on this port go first when several want the radio (a running turn is finished first). Default 5011, 0 = off. |
| Turn ends after silence | See *Turns* below. Default 0.75 s. |
| Longest turn | Hard limit for one turn. Default 8 s. |
| Log level | `DEBUG` shows every turn. |

## Turns

The MeshCore companion protocol has no request id. If two clients sent a command at the same time and
both waited for "the next OK", each could pick up the other's answer and fail with random errors.

The proxy therefore gives a client a *turn* as soon as it sends something. During the turn:

- the radio's answers go live to that client only;
- the other clients get the same bytes a moment later (nothing is dropped);
- the turn ends after *Turn ends after silence* seconds without radio traffic, or after *Longest turn*.

Outside a turn, spontaneous events from the mesh (incoming messages, adverts) go to everyone at once.
The defaults work well; only change them if a client misses replies (raise the silence time) or feels slow
(lower it).

## Troubleshooting

| Problem | Try |
|---|---|
| `Serial port ... does not exist` | Radio not plugged in, or another path. Check the list in the log. |
| Add-on cannot open the port | Another add-on or integration still has the USB device open. Point it at the proxy instead. |
| Clients see random `ERR_CODE_ILLEGAL_ARG` errors | Raise *Turn ends after silence* to 1.5 s. |
