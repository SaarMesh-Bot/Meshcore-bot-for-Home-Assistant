# Changelog

## 1.1.0

- Priority port (`priority_port`, default 5011, 0 = off): clients connected there go before clients on the normal port when
  both want the radio. Put the MeshCore Bot on it (its `tcp_port` 5011) so its replies do not wait behind meshcore-ha's polling.
  A running turn is always finished first.

## 1.0.0

First public release.

- Shares one MeshCore radio (USB, companion firmware) over TCP (`localhost:5010`) so meshcore-ha, the MeshCore Bot and other
  clients can use it at the same time, with exactly the same protocol as over USB.
- Turn-aware: the answers to one client's command are not sent to the other clients.
- The serial port is a free path (any `/dev/tty*` or `/dev/serial/by-id/*`); a clear error with the available ports when it
  does not exist.
- Options: serial port, baud rate, listen port, `turn_quiet_seconds`, `turn_max_seconds`, log level. English and Dutch.
