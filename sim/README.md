# Adapter simulator

[Русская версия](README.ru.md)

Pretends to be the adapter (XIAO ESP32-C5) with a Citroën C3 II attached, so the app can be written and tested without hardware or a car.
It speaks the protocol described in [DOCS/en/protocol.md](../DOCS/en/protocol.md).

## Running

```sh
python -m pip install -r sim/requirements.txt
python sim/c3_sim.py
```

It listens on `ws://0.0.0.0:8765`. In the app settings, enter `ws://<PC IP>:8765`
(phone and PC on the same Wi-Fi network; Windows may ask about the firewall — allow it for private networks).
With the phone on USB you can also use `adb reverse tcp:8765 tcp:8765` and `ws://127.0.0.1:8765`.

Options:

| | |
|---|---|
| `--port 8765` | port |
| `--engine-off` | ignition on, engine not running (battery at 12.6 V) |

## What it does

- Bus B (OBD 3/8), KWP2000 the PSA way, like a real C3 II (AEE2004): BSI `752/652` (session `10 C0`), engine Valeo V46 `6A8/688` (session `81`), ABS/ESP ESPMK100 `6AD/68D`, airbag Autoliv `744/644`, cluster `75F/65F`.
  ECU models, addresses, part numbers and data layouts come from the app's knowledge base (`app/assets/kb/c3_ii.json`, built from PSA-RE); the values come from the simulated car (rpm, coolant, battery…).
  Identification (`21 80` / `21 FE`) with a part number of a real C3 II variant, so the app recognises the model; VIN (`21 B0`); data records (`21 xx`); fault codes (`17 FF 00`: BSI two, engine P0130 present and P0300 stored); clearing (`14 FF 00`).
- Every new connection starts from scratch, like a power-up: buses closed, the ECUs' fault codes back, sessions closed.
- Without an open session the ECUs refuse (`7F xx 80`), and the session drops after 5 s without requests — this checks that the app keeps it alive.
- Writing and security access are refused with the answer of an ECU without access (`7F xx 33`). The app only reads anyway.
- Bus A (OBD 6/14): plain OBD-II `7DF/7E8`, modes `01` (rpm, coolant, throttle, voltage), `03`, `04`, `09 02` (VIN).
- Bus monitor (`summary`): BSI bus frames every 250 ms, voltage once a second.
- Freeze frames: OBD-II mode `02`. The PSA KWP ECUs have no `19 04` freeze frames.
- Two more ECUs that are not in the knowledge base (`6B1/691`, `77A/67A`, UDS) to exercise ECU discovery.
  Their addresses are made up, for testing only.
- The `isotp.req` answer always contains `rx`; `rx: "*"` means "accept the answer from any address" (ECU discovery).

The part numbers are taken from the C3 II variants in PSA-RE; whether the real car has the same ECUs, the first scan will show.

## Checking

```sh
python sim/test_client.py                         # simulator on this PC
python sim/test_client.py ws://192.168.4.1:81/ws  # later: the real adapter
```
