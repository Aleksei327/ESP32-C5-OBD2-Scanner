# LM2596S-ADJ DC-DC → 4.9 V

[Русская версия](../DC-DC_5V.md)

Built directly on the board from parts in stock. The input comes after the [limiter](power-protection.md), so it never exceeds ~27 V, and the LM2596 is rated for 40 V. The output goes through an SS34 diode to the 5V pin of the XIAO ESP32-C5, whose regulator makes 3.3 V for the ESP32 and the transceivers.

## Parts

| Part | Value | Note |
| --- | --- | --- |
| LM2596S-ADJ | TO-263 package | from stock |
| R3 (output → FB) | 3.0 kΩ | Vout = 1.23 × (1 + R3/R4) = 1.23 × 4 = **4.92 V** |
| R4 (FB → GND) | 1 kΩ | the datasheet suggests 1–5 kΩ for the lower resistor |
| Inductor | 120 µH (marking 121), shielded SMD 12×12×4 mm | from stock. A 68 µH 10×3 mm part would also work, the large one has more current margin |
| Diode | SS34 (40 V, 3 A) | the switching node never sees more than ~27 V |
| Cin | 100 µF / 50 V + 100 nF | shared with the follower output |
| Cout | 220 µF / 16–25 V low ESR + 100 nF | |
| ON/OFF (pin 5) | to GND | regulator always on |
| Isolation diode | SS34 | from the output to the XIAO 5V pin |
| TVS | 1.5KE6.8CA | on the 5V rail at the XIAO, see below |

**Why 4.9 V and not exactly 5 V.** After the isolation diode the XIAO 5V pin gets ~4.6 V, slightly less than USB provides (5 V). The XIAO 5V pin is the USB line, and Seeed's wiki does not say whether it has its own diode. If a laptop is plugged in while the board runs from the car, the board takes power from USB and nothing flows into the laptop. 4.6 V is plenty for the XIAO's 3.3 V LDO: it needs only a few tenths of a volt of headroom.

**Why the isolation diode.** When the board runs from the laptop's USB, it keeps the voltage from flowing back into the LM2596.

**1.5KE6.8CA on the 5V rail.** It does not conduct below 5.8 V, so in normal operation it is idle. If the LM2596 fails short and the input voltage reaches the output, the TVS clamps it, the current rises sharply and the input fuse blows. The XIAO and the CAN transceivers survive. It also catches ESD from the USB side.

Until the firmware has a sleep mode, the adapter is not left in the car: the ESP32 with Wi-Fi draws noticeably more than the DC-DC itself.
