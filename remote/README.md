# Remote assistant

[Русская версия](README.ru.md)

The car is in a car park, the computer is at home. The phone at the car connects the adapter to the computer over mobile internet, and a program on the computer (Claude Code, for example) works with the adapter as if it were next to it.

```text
adapter ──Wi-Fi── phone ──mobile internet── Cloudflare ── relay.py (home) ── adapter.py / assistant
```

- **Phone**: the app reaches the adapter over its Wi-Fi and the computer over mobile data. The phone keeps its internet: the adapter does not offer itself as a gateway, so Android leaves internet on the mobile network.
- **Computer**: `relay.py` is a relay on `127.0.0.1:8790`. From outside it is reached through a free Cloudflare tunnel (`cloudflared`, no account); the computer needs no incoming connections, any internet works, even a phone hotspot.
- **The key** is created anew on every `relay.py` start: 8 characters without 0/o and 1/l/i, so it can be typed by hand. Without it nobody can connect to the relay. The tunnel address is new every time as well. The tunnel runs HTTP/2 over TCP: QUIC kept dropping on the home network.

## How to run

1. On the computer:

   ```sh
   python remote/relay.py
   ```

   The script starts `cloudflared` itself and prints the **phone address** like `wss://….trycloudflare.com/phone?key=…`. The address and key are written to `remote/.session.json` (not in git).

   `cloudflared` is a single file: [Cloudflare's download page](https://github.com/cloudflare/cloudflared/releases), put `cloudflared-windows-amd64.exe` at `%LOCALAPPDATA%\cloudflared\cloudflared.exe`, or `winget install Cloudflare.cloudflared`.

2. On the phone: tap "Connect adapter" in the app (it joins the adapter's Wi-Fi by itself), then Settings → **Remote assistant**: paste the address and tap "Start". While the assistant is connected, a green bar with a stop button is shown on top of every screen and the screen stays on.

3. On the computer — commands to the adapter:

   ```sh
   python remote/adapter.py hello
   python remote/adapter.py open B
   python remote/adapter.py req B 752 652 10C0 2180 17FF00
   python remote/adapter.py monitor B 5
   ```

   `--url ws://192.168.4.1:81/ws` talks to the adapter directly, `--url ws://127.0.0.1:8765` to the simulator.

`adapter.py` only sends read requests (and fault clearing): it does not send services that change anything in the ECUs.

## Full car scan

```sh
python remote/scan.py              # every ECU in the knowledge base + OBD-II
python remote/scan.py --only BSI,CMM
```

Goes through every ECU in `app/assets/kb/c3_ii.json`: finds which ones answer, recognises the model by part number, reads fault codes (with texts from the knowledge base) and every data record, then OBD-II on bus A. The result goes to `scans/<date_time>/`: `report.md` and `scan.json` with raw answers. `scans/` stays out of git: it holds the car's VIN and part numbers. `scan.py` cannot send anything but reads; clearing faults is blocked there too.

## Latency

One request round trip through the tunnel and the mobile network takes about 0.2 s (`hello` took 170–300 ms when tested over mobile internet). That is enough for reading faults and data; an autoscan is slower than next to the car.
