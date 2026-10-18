# SN65HVD230 CAN transceiver

[Русская версия](../CAN_SN65HVD230.md)

The transceiver converts the ESP32's 3.3 V logic signals to the car's differential CAN-H/CAN-L bus and back. The protocol itself is handled by the CAN controllers inside the ESP32-C5.

We buy Waveshare SN65HVD230 CAN Board modules ([Gotronic](https://www.gotronic.fr/art-module-sn65hvd230-can-48593.htm), code 3945), **desolder the SOIC-8 chips with hot air and mount them on our board**. The board stays compact and the Rs pin becomes available, which gives a hardware listen-only mode.

## Characteristics (TI data)

- 3.3 V supply (3–3.6 V), connects to the ESP32 directly.
- Up to 1 Mbit/s, classic CAN only. Enough for the C3 (500 kbit/s).
- Bus pins withstand −4 to 16 V and more than ±16 kV ESD (HBM).
- Rs pin: high = listen-only (driver off, receiver on, ~370 µA), low = normal full-speed operation.

## Waveshare module (for reference)

From the Waveshare schematic and board photos:

- 4-pin header: 1 — CAN_TX, 2 — CAN_RX, 3 — GND, 4 — 3.3V (silkscreen top to bottom: 3.3V, GND, CAN RX, CAN TX);
- CANL and CANH on two pins and a screw terminal on the other side;
- 120 Ω terminator R2 soldered in permanently, Rs tied to ground through 10 kΩ (R1).

With our board, a complete module is only needed for the STM32 bench.

## The chip on our board (SOIC-8)

| Pin | Function | Channel A (U2) | Channel B (U3) |
| --- | --- | --- | --- |
| 1 D | transmit data | D8 (GPIO8) | D1 (GPIO0) |
| 2 GND | ground | GND | GND |
| 3 VCC | 3.3 V supply | 3V3 | 3V3 |
| 4 R | receive data | D7 (GPIO12) | D10 (GPIO10) |
| 5 Vref | VCC/2 reference | not connected | not connected |
| 6 CANL | CAN-L bus | OBD 14 | OBD 8 |
| 7 CANH | CAN-H bus | OBD 6 | OBD 3 |
| 8 Rs | mode | D9 (GPIO9) | D5 (GPIO24) |

- **Rs is pulled up to 3.3 V** with 10 kΩ (R11, R12). While the ESP32 boots or is being flashed, the transceivers physically cannot transmit anything into the car. The firmware pulls Rs low only when it is time to transmit.
- No pull-ups on D: while Rs is high the driver is off whatever D does. The firmware first starts the CAN controller (D = 1, recessive) and only then pulls Rs low.
- 100 nF on VCC right at the pin (C6, C7).
- **Terminator:** 120 Ω on each channel (R7, R8), enabled by solder jumper JP2/JP3, open by default. Whether channel 3/8 needs it will be decided by a measurement on the car (see [board v1](board-v1.md)).

## When CAN-FD is needed

The newest cars need an FD-capable transceiver, e.g. TCAN3413/TCAN3414 (±58 V bus, different pinout) or TJA1051T/3. That is a job for v2.

## Sources

- [SN65HVD230 (TI)](https://www.ti.com/product/SN65HVD230)
- [Waveshare: SN65HVD230 CAN Board](https://www.waveshare.com/wiki/SN65HVD230_CAN_Board), [module schematic](https://files.waveshare.com/upload/c/c5/SN65HVD230-CAN-Board-Schematic.pdf)
