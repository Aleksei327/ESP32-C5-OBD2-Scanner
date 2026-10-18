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

- Bus B (OBD 3/8), UDS: BSI `752/652`, engine `6A8/688`, ABS `6AD/68D`, airbag `744/644`, cluster `75F/65F`.
  VIN, part numbers, fault codes (BSI: U0100, U0155; engine: P0130, P0300), engine live data, 5 BSI settings (read only).
- Writing settings is refused with the answer of an ECU without security access. The app only reads anyway.
- Bus A (OBD 6/14): plain OBD-II `7DF/7E8`, modes `01` (rpm, coolant, throttle, voltage), `03`, `04`, `09 02` (VIN).
- Bus monitor (`summary`): BSI bus frames every 250 ms, voltage once a second.
- Freeze frames (`19 04`): conditions at the moment a fault was stored, for the BSI and the engine; OBD-II mode `02`.
- Two more ECUs that are not in the knowledge base (`76D/66D`, `6B5/5B5`) to exercise ECU discovery.
  Their addresses are made up, for testing only.
- The `isotp.req` answer always contains `rx`; `rx: "*"` means "accept the answer from any address" (ECU discovery).

All live-data and settings DIDs are made up: the real ones will go into the knowledge base once we listen to the car.

## Checking

```sh
python sim/test_client.py                         # simulator on this PC
python sim/test_client.py ws://192.168.4.1:81/ws  # later: the real adapter
```
