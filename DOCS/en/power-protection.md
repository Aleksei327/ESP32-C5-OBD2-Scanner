# Protecting the input from the car's electrical system

[Русская версия](../ЗАЩИТА_ПИТАНИЯ.md)

## What appears on pin 16

OBD pin 16 always carries +12 V from the battery, but it is far from clean:

| Event | Duration | Danger |
| --- | --- | --- |
| Switching spikes, ESD when plugging in | microseconds | chip breakdown |
| Negative spikes when inductive loads switch off | microseconds | down to −100 V |
| Load dump (battery terminal lost with the alternator running) | hundreds of milliseconds | ~35 V in modern cars, up to ~100 V in older ones |
| Jump start from 24 V | minutes | double voltage |
| Cranking | fractions of a second | dip to 6–8 V |
| Reverse polarity | — | never in the car, but easy on the bench |

## Circuit

Instead of a TVS, a linear limiter (source follower) is used. It passes normal voltage and absorbs anything above ~27 V. The LM2596S-ADJ DC-DC follows it (see [DC-DC](dc-dc-5v.md)).

```text
OBD 16 ─► 1 A fuse ─► HS1M ─► IRFB4110 follower (output ≤ ~27 V) ─► LM2596S-ADJ ─► 4.9 V
```

| Part | Connected | Why |
| --- | --- | --- |
| 1 A fuse (ordinary, from stock) | OBD 16 → HS1M | last line of defence: if something inside shorts, this fuse blows, not the one in the car's fuse box |
| HS1M diode (1000 V, 1 A) | anode to the fuse, cathode to the IRFB4110 drain | reverse polarity and negative spikes |
| IRFB4110 (100 V) | drain after the HS1M, source to the LM2596 input | follower: passes the supply but never more than ~27 V |
| 47 kΩ resistor, 1206 | from the drain to the gate reference node | gate bias; 1206 because it can see tens of volts |
| Two 15 V zeners in series | from the reference node to GND, cathode to the reference | 30 V threshold: the output becomes 30 − ~3.5 = ~26.5 V |
| 100 Ω resistor | reference node → gate | keeps the follower from oscillating |
| 15 V zener | gate–source, cathode to the gate | the IRFB4110 gate is rated ±20 V, and at power-up the gate already sees 30 V while the capacitors are still empty |
| 100 µF / 50 V + 100 nF | source → GND | LM2596 input |

It also gives a soft start: the gate charges through 47 kΩ in about a millisecond, so the inrush current into the capacitors is small.

## What happens in each case

| Situation | What happens |
| --- | --- |
| Normal operation, 12–14.8 V | transistor on; the output is ~4.5 V below the input (~1 V on the HS1M, ~3.5 V on the transistor), about 0.3 W lost |
| Cranking | the voltage dips and the adapter will probably reset. Harmless for a scanner |
| 24 V jump start | passes through (~19 V at the output), everything keeps working |
| ~35 V load dump | ~26.5 V at the output, the transistor dissipates ~0.5 W |
| Spike up to 100 V | ~26.5 V at the output, ~5 W in the transistor for a fraction of a second. Drain–source sees ~73 V of the 100 V rating |
| Negative spikes, reverse polarity | the HS1M blocks, rated 1000 V |

No heatsink needed: a TO-220 handles such short loads on its own.

## TVS

Not needed at the input: long surges are limited by the follower and negative ones are blocked by the HS1M. v1 has no footprint for an input TVS.

The 5V rail after the DC-DC carries a 1.5KE6.8CA as insurance in case the LM2596 fails short (see [DC-DC](dc-dc-5v.md)).

## Bench check

Before the car, test on a current-limited adjustable supply: slowly raise the input to 35–40 V and make sure the follower output stays at ~27 V or below and the transistor is only warm.
