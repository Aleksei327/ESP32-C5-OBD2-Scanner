# OBD Scanner app

[Русская версия](README.ru.md)

Flutter app for Android (developed on a Galaxy A55) that talks to the adapter over Wi-Fi (JSON over WebSocket, see [the protocol](../DOCS/en/protocol.md)). The adapter is a dumb transport; everything car-specific lives here and in the knowledge base.

**Read-only:** ECU scan and discovery, ECU model recognition by part number, identification (VIN, part and software numbers), fault codes with descriptions — read and clear (freeze frames on UDS ECUs), live data and settings (view only), OBD-II gauges with charts and CSV logging, a CAN bus monitor, and a PDF report. Nothing is written to the ECUs except clearing fault codes.

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
| `lib/transport/` | WebSocket client; PSA-style KWP2000 and UDS (`diag.dart`), OBD-II (`obd.dart`) |
| `lib/state/` | app state, diagnostics service (protocol and model detection, KWP session keep-alive), garage, car photos |
| `lib/kb/` | knowledge base model, value decoding in PSA-RE bit notation, OBD-II sensor catalogue |
| `lib/ui/` | screens: car, ECUs, ECU detail, gauges, bus monitor, garage, settings, report |
| `lib/l10n/` | translations (`app_ru.arb`, `app_en.arb`) |
| `assets/kb/c3_ii.json` | knowledge base for the C3 II (PSA AEE2004), generated from [PSA-RE](https://github.com/prototux/PSA-RE) — do not edit by hand; `PSA-RE-LICENCE.txt` next to it |
| `assets/kb/c3_ii_dtc_gpl.json` | extra fault-code texts from [ludwig-v/arduino-psa-diag](https://github.com/ludwig-v/arduino-psa-diag), GPL-3.0 (`GPL-3.0.txt` next to it); generated too |
| `assets/google_fonts/` | bundled Exo 2 and IBM Plex fonts with their OFL licence texts |
| `tool/` | `build_kb.py` + `kb_ru.json` (knowledge base and its Russian texts), scripts that draw the app icon |

## Knowledge base

`assets/kb/c3_ii.json` is built from the PSA-RE project (Apache-2.0) at a pinned commit: every ECU fitted to the C3 II (code A51), its possible models with their protocol, session, identification request and known part numbers, data records (live data, identification, settings) with bit layouts, and fault-code texts. Routines, actuator tests and anything that writes are left out.

```sh
python -m pip install pyyaml
python tool/build_kb.py       # from app/; downloads PSA-RE once into tool/.cache/
```

Where a fault code has no text, the script adds it from two more sources: ludwig-v's PSA lists (GPL-3.0, so they go to the separate file `c3_ii_dtc_gpl.json`) and the generic SAE J2012 texts from [OBD Codes List](https://obdcodeslist.com/code-data.html). The app looks for a text in this order: the identified ECU model, any model of that ECU, the ludwig-v file, the generic SAE text. The generic text is used only for codes whose meaning the standard itself fixes (P0, P2, P34–P39, B0, C0, U0); in the manufacturer ranges, and in U3 where PSA puts its own BSI codes, it would be wrong. The app marks it as "generic SAE description".

Russian texts come from `tool/kb_ru.json` (English text → Russian); the list of strings not translated yet is written to `tool/.cache/untranslated.txt`. Generic SAE texts follow a pattern ("Fuel Temperature Sensor B Circuit Low"), so they are translated in parts: `sae_parts` (the component) and `sae_faults` (the kind of fault), put together by `tool/sae_ru.py`. `tool/kb_translate.py export` writes the untranslated strings to `tool/.cache/tr/` in batches, `merge` takes the translated batches back into `kb_ru.json`.
