# ESP32-C5 OBD2 Scanner

[Русская версия](README.ru.md)

A DIY dual-CAN OBD2 diagnostic adapter built on the Seeed XIAO ESP32-C5, together with a read-only Android app. The first target is my own Citroën C3 II (2011, 1.4 KFT): ECU list, fault codes (read and clear), live data, freeze frames, a bus monitor and a PDF report. Other cars are added through a JSON knowledge base, without changing the firmware.

> **Development status:** the schematic and the single-sided PCB are complete — the board is routed on one copper layer with **no wire jumpers**. The app runs against a Python simulator and has been tested on a phone. No board has been etched or brought up yet: every hardware figure below is a design value, not a measurement.

![Board v1, 3D view](DOCS/images/board-3d-front.png)

## Key decisions

| What | Choice | Why |
| --- | --- | --- |
| MCU | Seeed XIAO ESP32-C5 | two CAN (TWAI) controllers, both CAN-FD capable; Wi-Fi 6 on 2.4 and 5 GHz; BLE; 8 MB PSRAM |
| CAN channel A | OBD 6/14 | legislated OBD-II (engine) |
| CAN channel B | OBD 3/8 | PSA Diag-on-CAN through the BSI, access to every ECU |
| Transceivers | 2 × SN65HVD230 (SOIC-8), desoldered from Waveshare modules | 3.3 V, enough for the C3; Rs on D9/D5 with pull-ups gives a hardware listen-only mode. CAN-FD transceivers in v2 |
| Power | OBD 16 → fuse → HS1M → IRFB4110 source follower (≤ 27 V) → LM2596S-ADJ (4.9 V) → SS34 (+ 1.5KE6.8CA TVS) → 3.3 V LDO on the XIAO | all from parts in stock; survives a 24 V jump start and surges up to 100 V |
| Hardware | own single-sided 40 × 70 mm board inside an OBD2 enclosure with a built-in connector; tracks on the bottom only, no jumpers | one dongle, no cables |
| App | Flutter for Android (Galaxy A55): read-only plus fault-code clearing; two themes; Russian and English | |
| Link | Wi-Fi, JSON over WebSocket; the adapter is a "dumb" transport, all logic lives in the app | a new car is a new JSON file |

## Repository

| Folder | Contents |
| --- | --- |
| [`hardware/scaner_v1/`](hardware/scaner_v1/README.md) | KiCad 10 project: schematic, PCB, footprints, 3D models, and the Python scripts that generate and route the board; PDF exports in `build/` |
| [`firmware/scaner_fw/`](firmware/scaner_fw/README.md) | ESP-IDF 6.1 board self-test firmware (both CAN channels, listen-only, battery voltage) |
| [`app/`](app/README.md) | Flutter app |
| [`sim/`](sim/README.md) | Python simulator of the adapter with a C3 attached, to develop the app without hardware or a car |
| [`DOCS/en/`](DOCS/en/) | documentation in English ([`DOCS/`](DOCS/) — Russian originals) |

## Documentation

- [Board v1](DOCS/en/board-v1.md): block diagram, enclosure, OBD wiring, pin assignment, layout notes, first power-up
- [Input protection](DOCS/en/power-protection.md): what the car's electrical system does to pin 16 and how the board survives it
- [LM2596 DC-DC](DOCS/en/dc-dc-5v.md): parts and values
- [XIAO ESP32-C5](DOCS/en/xiao-esp32c5.md): pinout and which pins are used
- [SN65HVD230 transceiver](DOCS/en/can-sn65hvd230.md): wiring, listen-only mode, terminators
- [Adapter ↔ app protocol](DOCS/en/protocol.md)
- [Parts list](DOCS/en/parts-list.md)

PDF exports: [schematic](hardware/scaner_v1/build/scaner_v1.pdf), [placement and copper](hardware/scaner_v1/build/pcb_placement.pdf), [bottom copper 1:1 for etching](hardware/scaner_v1/build/pcb_bottom_cu.pdf).

## What is known about the C3 (PSA, AEE2004/2010 architecture)

- Full diagnostics run on pins **3/8** (Diag-on-CAN, 500 kbit/s) through the BSI. Pins **6/14** only give legislated engine OBD-II.
- Protocols: KWP2000 and UDS over CAN (ISO-TP).
- ECU addresses (request:response): BSI `752:652`, engine `6A8:688`, ABS/ESP `6AD:68D`, airbag `744:644`, instrument cluster `75F:65F`.
- Which engine ECU is fitted is not known yet; the scanner will tell.

## Rules

1. The app only reads. The only write is clearing fault codes.
2. Airbag and ABS: read only. Emissions systems are not touched.
3. The adapter is not left in the car: pin 16 is powered from the battery at all times.

## Credits and third-party work

No third-party code is copied into this repository. These projects, tools and libraries were used or consulted:

- [ludwig-v/arduino-psa-diag](https://github.com/ludwig-v/arduino-psa-diag) — PSA ECU addresses ([ECU_LIST.md](https://github.com/ludwig-v/arduino-psa-diag/blob/master/ECU_LIST.md)).
- [KiCad](https://www.kicad.org/) and its official symbol, footprint and 3D-model libraries.
- [Freerouting](https://github.com/freerouting/freerouting) — used to explore routing (`hardware/scaner_v1/tools/route.py`); the final layout is routed by hand.
- [ESP-IDF](https://github.com/espressif/esp-idf) (Espressif) — firmware framework; [Seeed Studio wiki](https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/) — XIAO ESP32-C5 pinout.
- [Flutter](https://flutter.dev/) and the Dart packages listed in [`app/pubspec.yaml`](app/pubspec.yaml): web_socket_channel, flutter_svg, google_fonts, shared_preferences, intl, image_picker, path_provider, pdf, share_plus.
- Fonts [Exo 2](https://fonts.google.com/specimen/Exo+2) and [IBM Plex](https://github.com/IBM/plex), SIL Open Font License 1.1 (licence texts in `app/assets/google_fonts/`).
- [websockets](https://github.com/python-websockets/websockets) — the simulator's WebSocket server.
- Datasheets and application data: Texas Instruments (SN65HVD230, LM2596), Espressif (ESP32-C5), Waveshare (SN65HVD230 CAN Board schematic).

Each of these keeps its own licence.

## License

See [NOTICE.md](NOTICE.md) and [LICENSE](LICENSE) (CC BY-NC-ND 4.0, with permission to build one unit for yourself).
