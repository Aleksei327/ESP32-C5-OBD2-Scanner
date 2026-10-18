# Adapter ↔ app protocol (v0)

[Русская версия](../ПРОТОКОЛ.md)

The adapter is a "dumb" transport. It knows nothing about car makes, VINs or fault codes.
It can open a CAN bus, send a request to an ECU and return the answer, keep a session alive, listen to the bus and measure voltage.
All the logic — what to ask and how to decode it — lives in the app and its knowledge base.

That way the firmware does not change for every car, and a new car is a new JSON file on the phone.

## Transport

- Wi-Fi: the adapter runs the access point `SCANER-C5`, address `ws://192.168.4.1:81/ws`.
- Simulator on a PC: `ws://<PC IP>:8765` (see [`sim/README.md`](../../sim/README.md)).
- BLE later — same JSON messages.

Every message is one JSON object in one WebSocket text frame.

## Request → response

The app sends `{"id": 7, "cmd": "...", ...}`, the adapter answers with the same `id`:

```json
{"id": 7, "ok": true, ...}
{"id": 7, "ok": false, "err": "timeout"}
```

Bytes are always hex strings without spaces (`"22F190"`), CAN IDs are hex strings (`"752"`).

| cmd | Parameters | Response | What it does |
| --- | --- | --- | --- |
| `hello` | — | `fw`, `hw`, `buses`, `mv` | Handshake: firmware version, bus list, voltage |
| `vbat` | — | `mv` | Voltage on OBD 16, mV |
| `bus.open` | `bus` (`A`/`B`), `bitrate`, `listen` | — | Open a bus. `listen: true` — listen only (driver off) |
| `bus.close` | `bus` | — | Close the bus |
| `isotp.req` | `bus`, `tx`, `rx`, `data`, `timeout_ms` | `data`, `rx` | Send a request to an ECU (ISO-TP) and wait for the answer. "Response pending" (7F xx 78) is handled by the adapter. `rx: "*"` — reply address unknown: take the first answer after the request and report which `rx` it came from (needed for ECU discovery: PSA uses both 752→652 and 6A8→688) |
| `tester.start` | `bus`, `tx`, `data`, `period_ms` | — | Keep a session alive: send `data` (usually `3E80`) every `period_ms` |
| `tester.stop` | `bus`, `tx` | — | Stop it |
| `monitor.start` | `bus`, `mode` (`summary`/`raw`), `ids` (optional) | — | Listen to the bus and send events |
| `monitor.stop` | `bus` | — | Stop listening |

The ECU's answer is returned as is, including negative responses (`7F 22 31` etc.). The app decodes it.

### Errors

| `err` | Meaning |
| --- | --- |
| `bad_args` | Missing or malformed parameters |
| `bus_closed` | The bus is not open |
| `listen_only` | The bus is open in listen-only mode, transmitting is not allowed |
| `timeout` | The ECU did not answer |
| `bus_off` | Bus error (short circuit, missing terminator, wrong bitrate) |
| `busy` | The adapter is busy with another request on this bus |

## Events (no `id`)

```json
{"ev": "vbat", "mv": 12610}
{"ev": "frames", "bus": "B", "t": 123456, "frames": [{"id": "0B6", "data": "0000000000000D0", "n": 9640, "hz": 20}]}
{"ev": "frame", "bus": "B", "t_us": 123456789, "id": "0B6", "data": "00000000000000D0"}
{"ev": "bus", "bus": "B", "state": "bus_off"}
```

- `vbat` — once a second.
- `frames` — `summary` mode: every 250 ms, the last frame of each ID with a counter and rate. For the bus monitor screen.
- `frame` — `raw` mode: every frame. For logging, preferably with an `ids` filter.

## Safety

- After power-up both buses are closed and the transceivers are in listen-only mode (Rs = 1).
- Transmitting is only possible after `bus.open` with `listen: false`. The app does this only when the user starts diagnostics.
- The app is read-only for now: ECUs, fault codes (and clearing them), live data, bus monitor. Nothing is written to the ECUs.

## On top of it (in the app)

The app and the simulator currently speak UDS (ISO 14229): `10` session, `22` read, `19` fault codes, `14` clear fault codes, `3E` tester present.
This is the common language of modern cars. The BSI of the C3 II (AEE2004) partly speaks KWP2000 — that will go into the knowledge base once we listen to the real car.

On bus A (OBD 6/14) it is plain OBD-II: `7DF`/`7E8`, modes `01`, `03`, `04`, `09`.
