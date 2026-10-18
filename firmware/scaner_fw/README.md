# Board self-test firmware

[Русская версия](README.ru.md)

ESP-IDF 6.1 firmware for the XIAO ESP32-C5 on board v1. It checks the hardware before the real adapter firmware (WebSocket server for the app) is written. The console runs over the XIAO's built-in USB Serial/JTAG.

| Command | What it does |
| --- | --- |
| `selftest` | Channels A and B wired together, JP2/JP3 closed: sends frames A→B and B→A and reports the result |
| `listen [seconds]` | Listens to both channels without transmitting (Rs = 1, controllers in listen-only mode) |
| `vbat` | Battery voltage from the divider on D0 |
| `status` | Channel and battery status |

Pins are defined in [`main/board.h`](main/board.h). On the board there are no pull-ups on the transceiver D inputs: the firmware holds TX high as a GPIO until the CAN controller takes over, and pulls Rs low only after the controller is running.

## Build

```sh
idf.py set-target esp32c5   # once
idf.py build flash monitor
```
