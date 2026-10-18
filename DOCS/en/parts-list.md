# Parts list

[Русская версия](../ПОКУПКИ.md)

## To buy

| Item | Where | Qty | ≈ € |
| --- | --- | --- | --- |
| Waveshare SN65HVD230 CAN module — the chip is desoldered from it | [Gotronic](https://www.gotronic.fr/art-module-sn65hvd230-can-48593.htm) | 2 | 9.50 |
| Seeed XIAO ESP32-C5 board (code 100010048) | [Gotronic](https://www.gotronic.fr/art-carte-xiao-esp32-c5-100010048-49303.htm) | 1 | 6.90 |
| Gotronic "Lettre suivie" shipping, about 4 days | | | 2.90 |
| OBD2 enclosure with built-in connector (72 × 45 mm) | AliExpress | 1 | ~10 + 3 € duty |

**Total: ~32 €** (Gotronic 19.30 € with shipping + enclosure ~13 €).

When the enclosure arrives: check that the connector has pins 3, 4, 5, 6, 8, 14, 16 and measure it inside (see [board v1](board-v1.md), "Enclosure and dimensions").

## From stock

**Power** (see [power protection](power-protection.md) and [DC-DC](dc-dc-5v.md)):

- 1 A fuse, 5×20 glass, and clips;
- HS1M;
- IRFB4110;
- 15 V zeners — **3 pcs** (check you have enough);
- resistors 47 kΩ, 100 Ω, 1 kΩ, 3.0 kΩ;
- LM2596S-ADJ and a 120 µH inductor (marking 121, shielded 12×12 mm);
- SS34 — 2 pcs;
- 1.5KE6.8CA TVS (on the 5V rail);
- capacitors 100 µF / 50 V, 220 µF / 16–25 V low ESR, 100 nF, 10 µF.

**Battery voltage divider:** 220 kΩ, 33 kΩ, 100 nF.

**CAN:** 10 kΩ resistors — 2 pcs (Rs pull-ups), 120 Ω — 2 pcs (terminators), 100 nF — 2 pcs. All resistors and capacitors are 1206.

**Other:** female headers 1×7 and male pin headers for the XIAO, wire from the connector to the board.

## Check you have at home

- An adjustable current-limited bench supply: used to test the limiter up to 35–40 V.
- A USB-C data cable, not a charge-only one.

## Not buying

- A separate OBD plug — the connector is built into the enclosure.
- A DC-DC module and a batch of TVS diodes — our own LM2596 DC-DC, and no input TVS is needed with the follower.
- NUP2105L — the SN65HVD230's own protection is enough.
- A third SN65HVD230 module for the bench — only if a bench is needed (~5 € at Gotronic).
- TJA1051T/3, TPS26600, KONNWEI KW906, ESP32-C3 SuperMini, ESP32-C6, MCP2562FD, a female OBD socket, breadboards and Dupont wires, L9637D, DIP switch, Y splitter.
