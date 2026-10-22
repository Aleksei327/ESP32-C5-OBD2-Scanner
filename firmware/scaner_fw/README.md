# Adapter firmware

[Русская версия](README.ru.md)

ESP-IDF 6.1 firmware for the XIAO ESP32-C5 on board v1. The adapter runs its own Wi-Fi network and waits for the app at `ws://192.168.4.1:81/ws`; the protocol is [DOCS/en/protocol.md](../../DOCS/en/protocol.md), the same as the simulator's. The console runs over the XIAO's built-in USB Serial/JTAG.

## Wi-Fi

Network `SCANER-C5-XXXX` (XXXX is the end of the MAC address), WPA2. The password is 10 random characters, created on first power-up and stored in NVS. The `wifi` console command shows or changes it. The adapter is 192.168.4.1; the phone gets an address over DHCP.

## Console

| Command | What it does |
| --- | --- |
| `status` | Bus, Wi-Fi, memory and battery status |
| `wifi` | Network name, password, how many phones are on the network and apps connected |
| `wifi pass <password>` | Change the password (8–63 characters) |
| `vbat` | Battery voltage from the divider on D0 |
| `listen [seconds]` | Print the frames of both buses without transmitting (Rs = 1, controllers in listen-only mode) |
| `selftest` | Channels A and B wired together, JP2/JP3 closed: sends frames A→B and B→A. Only while no app is connected |

## How it works

| File | What it does |
| --- | --- |
| `main/main.c` | Start-up and console |
| `main/wifi_ap.c` | Access point, password in NVS |
| `main/ws_server.c` | WebSocket server (`esp_http_server`), list of connected apps, sending from any task |
| `main/proto.c` | App commands; per bus a command queue, a frame receive task and an exchange task (ISO-TP, tester present); monitor summary and voltage every 250 ms / 1 s |
| `main/can_ch.c` | CAN channel: TWAI controller and transceiver with Rs control |
| `main/vbat.c` | Battery voltage |

Pins are defined in [`main/board.h`](main/board.h). On the board there are no pull-ups on the transceiver D inputs: the firmware holds TX high as a GPIO until the CAN controller takes over, and pulls Rs low only after the controller is running. After power-up both buses are closed; when the app disconnects, the adapter closes them itself.

## Build

```sh
idf.py set-target esp32c5   # once
idf.py build flash monitor
```

JSON is parsed by cJSON: it is not part of ESP-IDF 6, `idf.py` downloads it on the first build (component `espressif/cjson`, needs internet; the version is pinned in `dependencies.lock`).
