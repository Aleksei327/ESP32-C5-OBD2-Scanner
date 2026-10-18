# Плата v1 — проект KiCad

[English version](README.md)

Проект платы адаптера в KiCad 10: 40 × 70 мм, односторонняя (все дорожки на нижней меди, перемычек нет), под домашнее травление. Описание и решения: [DOCS/ПЛАТА_v1.md](../../DOCS/ПЛАТА_v1.md).

| Сверху | Снизу |
| --- | --- |
| ![Сверху](../../DOCS/images/board-3d-top.png) | ![Снизу](../../DOCS/images/board-3d-bottom.png) |

## Файлы

| Путь | Что там |
| --- | --- |
| `scaner_v1.kicad_sch`, `scaner_v1.kicad_pcb`, `scaner_v1.kicad_pro` | схема, плата, проект (правила: дорожка 0,8 мм, зазор 0,4 мм) |
| `scaner.pretty/` | свои посадочные места: XIAO ESP32-C5 на двух гнёздах 1×7, дроссель 12×12 с широкими площадками |
| `scaner.3dshapes/` | свои 3D-модели (VRML) для деталей, которых нет в библиотеке KiCad |
| `build/*.pdf` | схема, расстановка с медью, нижняя медь 1:1 для травления |
| `tools/` | скрипты на Python, которые всё генерируют (см. ниже) |

## Плата генерируется, а не рисуется руками

Схема, расстановка и разводка получаются скриптами: правка вносится в скрипт, и всё пересобирается:

```sh
python tools/gen_schematic.py        # детали, цепи, свои посадочные места -> scaner_v1.kicad_sch
python tools/check_netlist.py        # ERC и сверка нетлиста с tools/expected_nets.json
"C:\Program Files\KiCad\10.0\bin\python.exe" tools/gen_pcb.py       # расстановка (таблица PLACE), правила площадок, запреты
"C:\Program Files\KiCad\10.0\bin\python.exe" tools/hand_route.py    # дорожки из tools/routes.py, заливка земли, DRC
python tools/gen_3d.py               # 3D-модели в scaner.3dshapes/
```

- `routes.py` — каждая дорожка списком точек (или ссылок `ДЕТАЛЬ.площадка`) с шириной.
- `view_board.py` — картинка платы в SVG: цепи на площадках, связи, отметки DRC; удобно при разводке.
- `route.py` — опыт с автороутером Freerouting, оставлен для справки; ручную разводку он затирает.

Ручные правки в KiCad затираются следующим запуском `gen_pcb.py` / `hand_route.py` — сначала перенеси их в `routes.py`.
