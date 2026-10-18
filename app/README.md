# OBD Scanner app

[Русская версия](README.ru.md)

Flutter app for Android (developed on a Galaxy A55) that talks to the adapter over Wi-Fi (JSON over WebSocket, see [the protocol](../DOCS/en/protocol.md)). The adapter is a dumb transport; everything car-specific lives here and in the knowledge base.

**Read-only:** ECU scan and discovery, identification (VIN, part and software numbers), fault codes with freeze frames — read and clear, live data, OBD-II gauges with charts and CSV logging, a CAN bus monitor, and a PDF report. Nothing is written to the ECUs except clearing fault codes.

Also: a garage of cars recognised by VIN with up to 5 photos per car, two themes (dark "engineering" and bright light), Russian and English.

## Build and run

Requires Flutter 3.44 (Dart 3.12) and the Android SDK.

```sh
cd app
flutter pub get        # also generates lib/l10n/gen from the .arb files
flutter run            # phone connected over USB
```

Connection: the adapter's access point `SCANER-C5` and `ws://192.168.4.1:81/ws`, or the [simulator](../sim/README.md) at `ws://<PC IP>:8765` (Settings → adapter address).

Tests:

```sh
flutter test                                   # unit tests
python ../sim/c3_sim.py                        # in another terminal
flutter test --tags sim --run-skipped          # integration test against the simulator
```

## Layout

| Path | Contents |
| --- | --- |
| `lib/transport/` | WebSocket client, UDS and OBD-II requests |
| `lib/state/` | app state, diagnostics service, garage, car photos |
| `lib/kb/` | knowledge base loader, OBD-II sensor catalogue |
| `lib/ui/` | screens: car, ECUs, ECU detail, gauges, bus monitor, garage, settings, report |
| `lib/l10n/` | translations (`app_ru.arb`, `app_en.arb`) |
| `assets/kb/c3_ii.json` | knowledge base for the C3 II (PSA AEE2004). Live-data and settings DIDs are placeholders until the real car is sniffed |
| `assets/google_fonts/` | bundled Exo 2 and IBM Plex fonts with their OFL licence texts |
| `tool/` | scripts that draw the app icon |
