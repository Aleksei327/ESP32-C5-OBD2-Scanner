# Board v1 — KiCad project

[Русская версия](README.ru.md)

KiCad 10 project of the adapter board: 40 × 70 mm, single-sided (all tracks on the bottom copper, no wire jumpers), designed for home etching. Description and design notes: [DOCS/en/board-v1.md](../../DOCS/en/board-v1.md).

| Top | Bottom |
| --- | --- |
| ![Top](../../DOCS/images/board-3d-top.png) | ![Bottom](../../DOCS/images/board-3d-bottom.png) |

## Files

| Path | Contents |
| --- | --- |
| `scaner_v1.kicad_sch`, `scaner_v1.kicad_pcb`, `scaner_v1.kicad_pro` | schematic, board, project (design rules: 0.8 mm tracks, 0.4 mm clearance) |
| `scaner.pretty/` | project footprints: XIAO ESP32-C5 on two 1×7 sockets, 12×12 inductor with wide pads |
| `scaner.3dshapes/` | hand-written 3D models (VRML) for parts missing from the KiCad library |
| `build/*.pdf` | schematic, placement with copper, bottom copper 1:1 for etching |
| `tools/` | Python scripts that generate everything (see below) |

## The board is generated, not drawn by hand

The schematic, placement and routing are produced by scripts, so a change is made in the script and everything is regenerated:

```sh
python tools/gen_schematic.py        # parts, nets, project footprints -> scaner_v1.kicad_sch
python tools/check_netlist.py        # ERC and netlist check against tools/expected_nets.json
"C:\Program Files\KiCad\10.0\bin\python.exe" tools/gen_pcb.py       # placement (PLACE table), pad rules, keep-outs
"C:\Program Files\KiCad\10.0\bin\python.exe" tools/hand_route.py    # tracks from tools/routes.py, ground pour, DRC
python tools/gen_3d.py               # 3D models into scaner.3dshapes/
```

- `routes.py` — every track as a list of points (or `REF.pad` references) with its width.
- `view_board.py` — an SVG view of the board with net names on the pads, ratsnest and DRC markers; handy while routing.
- `route.py` — Freerouting experiment kept for reference; it overwrites the hand routing.

Manual edits made in KiCad are overwritten by the next `gen_pcb.py` / `hand_route.py` run — carry them over into `routes.py` first.
