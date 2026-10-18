# Seeed XIAO ESP32-C5 board

[Русская версия](../ESP32-C5_ПЛАТА.md)

The brain of the adapter. Bought from [Gotronic](https://www.gotronic.fr/art-carte-xiao-esp32-c5-100010048-49303.htm), code 100010048, 6.90 €. Size 21 × 17.8 mm.

## Characteristics

| Parameter | Value |
| --- | --- |
| Chip | ESP32-C5HR8: RISC-V 240 MHz, 384 KB RAM + 8 MB in-package PSRAM |
| Flash | 8 MB |
| Radio | Wi-Fi 6 on 2.4 + 5 GHz, Bluetooth 5 (BLE), Zigbee/Thread |
| CAN | 2 TWAI controllers, both CAN-FD capable |
| Antenna | external, U.FL connector, antenna included |
| USB | USB-C, built-in USB Serial/JTAG: flashing and console over one cable |
| Pins | 11 (D0–D10), 2.54 mm pitch |
| Other | LiPo charger (not used), RST and BOOT buttons |

## Pinout (from the Seeed wiki)

| Pin | GPIO | Notes | Use on board v1 |
| --- | --- | --- | --- |
| D0 | GPIO1 | the only ADC pin on the header | **battery voltage** |
| D1 | GPIO0 | — | **CAN-B TX** |
| D2 | GPIO25 | strapping | not used |
| D3 | GPIO7 | strapping | not used |
| D4 | GPIO23 | I2C SDA | spare |
| D5 | GPIO24 | I2C SCL | **channel B Rs** (listen-only) |
| D6 | GPIO11 | UART0 TX, boot log output | **not for CAN** |
| D7 | GPIO12 | UART0 RX (our console is on USB) | **CAN-A RX** |
| D8 | GPIO8 | — | **CAN-A TX** |
| D9 | GPIO9 | — | **channel A Rs** (listen-only) |
| D10 | GPIO10 | — | **CAN-B RX** |
| 5V | VBUS | USB line, input/output | powered by our DC-DC |
| 3V3 | regulator output | | powers the CAN transceivers |
| GND | | | |

Inside the board and not on the header: LED on GPIO27, BOOT button on GPIO28, battery measurement (GPIO6 and GPIO26), JTAG pads underneath (GPIO2–5) — left alone.

**Strapping pins.** The chip samples their level at power-up. Signals that drive a level at power-up by themselves (such as a CAN receiver output) are kept off D2 and D3.

**D6 (GPIO11).** The chip writes its boot log there. A CAN TX on this pin would push that log into the car's bus as garbage.

**Pull-ups.** The transceiver Rs pins (D9 and D5) get 10 kΩ to 3.3 V each. While the ESP32 boots or is flashed, nothing drives these pins, and the pull-ups keep the transceivers in listen-only mode, so nothing reaches the car. More in [SN65HVD230](can-sn65hvd230.md).

**Powering through the 5V pin.** This is the USB line, and the wiki does not say whether it has its own diode. That is why our DC-DC delivers ~4.6 V to this pin, slightly less than USB. With a laptop plugged in while running from the car, nothing flows into the laptop. More in [DC-DC](dc-dc-5v.md).

## Sources

- [Seeed Wiki: XIAO ESP32-C5, pinout](https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/)
- [ESP32-C5 Datasheet](https://documentation.espressif.com/esp32-c5_datasheet_en.pdf): strapping pins
- [ESP-IDF, TWAI on the ESP32-C5](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c5/api-reference/peripherals/twai.html): 2 controllers, CAN-FD
