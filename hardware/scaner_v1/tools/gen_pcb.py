#!/usr/bin/env python3
"""Черновая расстановка платы v1 под корпус OBD2 (40 x 70 мм). Запускать питоном KiCad:

  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/gen_pcb.py

Берёт нетлист build/scaner_v1.xml (его делает tools/check_netlist.py), ставит посадочные места,
назначает цепи и привязывает их к символам схемы, рисует контур и крепёжные отверстия.
Дорожки НЕ разводит: плата односторонняя, разводка по нижней меди — вручную, как у тебя принято.
Разовый генератор: после ручной расстановки в KiCad НЕ запускать — перезапишет плату.
"""
import os
import sys
import xml.etree.ElementTree as ET

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
FPLIB = r'C:\Program Files\KiCad\10.0\share\kicad\footprints'
NET_XML = os.path.join(PRJ, 'build', 'scaner_v1.xml')
OUT = os.path.join(PRJ, 'scaner_v1.kicad_pcb')

X0, Y0, W, H = 100.0, 100.0, 40.0, 70.0   # контур платы, мм (разъём OBD — сверху)

# ref: (x, y, угол, сторона)   F — сверху (выводные), B — снизу (SMD)
PLACE = {
    # верх: выводные
    'J1': (112.38, 102.0, 90, 'F'),     # провода от разъёма OBD
    'F1': (110.0, 107.0, 0, 'F'),       # клипсы 5x20
    'D1': (104.0, 124.0, 0, 'F'),       # 1.5KE27A стоя, по умолчанию не ставится
    'C1': (104.5, 133.0, 0, 'F'),       # 100u/50V — класть на бок
    'C3': (104.5, 144.0, 0, 'F'),       # 220u/25V — класть на бок
    'D8': (103.5, 163.0, 0, 'F'),       # 1.5KE6.8CA стоя
    'D3': (116.0, 130.0, 0, 'F'),
    'D4': (116.0, 134.0, 0, 'F'),
    'D5': (121.0, 130.0, 0, 'F'),
    'Q1': (127.5, 140.0, 0, 'F'),       # IRFB4110 лёжа, теплоотвод вниз
    'U4': (128.14, 166.5, 180, 'F'),    # XIAO, USB к дальнему торцу
    # стойки корпуса: 35 мм поперёк, 40 мм вдоль, по центру длины — уточнить по корпусу
    'H1': (102.5, 115.0, 0, 'F'),
    'H2': (137.5, 115.0, 0, 'F'),
    'H3': (102.5, 155.0, 0, 'F'),
    'H4': (137.5, 155.0, 0, 'F'),
    # низ: SMD
    'D2': (105.5, 103.5, 0, 'B'),
    'C2': (109.0, 112.0, 90, 'B'),
    'U1': (117.5, 116.5, 0, 'B'),
    'D6': (131.5, 113.5, 90, 'B'),
    'L1': (132.5, 132.0, 180, 'B'),
    'R1': (122.5, 136.5, 0, 'B'),
    'R2': (123.5, 133.5, 0, 'B'),
    'R3': (113.0, 124.5, 0, 'B'),
    'R4': (113.0, 129.0, 0, 'B'),
    'C4': (137.5, 141.0, 90, 'B'),
    'D7': (120.0, 145.0, 0, 'B'),
    'JP1': (131.3, 143.5, 0, 'B'),
    'U2': (120.5, 156.0, 90, 'B'),
    'U3': (120.5, 164.0, 90, 'B'),
    'R5': (115.75, 153.0, 90, 'B'),
    'R6': (115.75, 156.5, 90, 'B'),
    'R11': (115.75, 160.0, 90, 'B'),
    'R12': (115.75, 163.5, 90, 'B'),
    'JP3': (115.75, 167.2, 90, 'B'),
    'C6': (125.4, 153.0, 90, 'B'),
    'R7': (125.4, 156.5, 90, 'B'),
    'JP2': (125.4, 160.1, 90, 'B'),
    'C7': (125.4, 163.5, 90, 'B'),
    'R8': (125.4, 167.1, 90, 'B'),
    'R9': (132.0, 164.6, 0, 'B'),
    'R10': (131.5, 168.0, 0, 'B'),
    'C8': (135.5, 168.0, 0, 'B'),
    'C5': (109.0, 166.5, 90, 'B'),
}


def mm(v):
    return pcbnew.FromMM(v)


def load_netlist():
    root = ET.parse(NET_XML).getroot()
    comps = {}
    for c in root.iter('comp'):
        comps[c.get('ref')] = {
            'value': c.findtext('value'),
            'footprint': c.findtext('footprint'),
            'uuid': c.findtext('tstamps'),
        }
    nets = {}
    for n in root.iter('net'):
        for node in n.iter('node'):
            nets.setdefault(node.get('ref'), {})[node.get('pin')] = n.get('name')
    return comps, nets


def main():
    comps, pinnets = load_netlist()
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)

    netinfo = {}
    for ref in pinnets:
        for name in pinnets[ref].values():
            if name not in netinfo:
                ni = pcbnew.NETINFO_ITEM(board, name)
                board.Add(ni)
                netinfo[name] = ni

    missing = [r for r in comps if not r.startswith('#') and r not in PLACE]
    if missing:
        sys.exit(f'нет позиции для: {missing}')

    for ref, c in sorted(comps.items()):
        if ref.startswith('#'):
            continue
        lib, name = c['footprint'].split(':')
        path = os.path.join(PRJ, 'scaner.pretty') if lib == 'scaner' else os.path.join(FPLIB, lib + '.pretty')
        fp = pcbnew.FootprintLoad(path, name)
        if fp is None:
            sys.exit(f'не найдено посадочное место {c["footprint"]}')
        fp.SetReference(ref)
        fp.SetValue(c['value'])
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetPath(pcbnew.KIID_PATH(f"/{c['uuid']}"))
        board.Add(fp)
        x, y, ang, side = PLACE[ref]
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(ang)
        if side == 'B':
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        for pad in fp.Pads():
            net = pinnets.get(ref, {}).get(pad.GetNumber())
            if net:
                pad.SetNet(netinfo[net])

    rect = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECTANGLE)
    rect.SetStart(pcbnew.VECTOR2I(mm(X0), mm(Y0)))
    rect.SetEnd(pcbnew.VECTOR2I(mm(X0 + W), mm(Y0 + H)))
    rect.SetLayer(pcbnew.Edge_Cuts)
    rect.SetWidth(mm(0.1))
    board.Add(rect)

    for text, x, y, layer in [('OBD scaner v1', X0 + W / 2, Y0 + 12.5, pcbnew.F_SilkS),
                              ('OBD -> вверх', X0 + W / 2, Y0 + H - 1.5, pcbnew.F_Fab)]:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
        board.Add(t)

    pcbnew.SaveBoard(OUT, board)
    print(f'ok: {OUT}')


if __name__ == '__main__':
    main()
