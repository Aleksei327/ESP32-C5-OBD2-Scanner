#!/usr/bin/env python3
"""Расстановка платы v1 под корпус OBD2 (40 x 70 мм). Запускать питоном KiCad:

  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/gen_pcb.py
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/hand_route.py

Берёт нетлист build/scaner_v1.xml (его делает tools/check_netlist.py), ставит посадочные места,
назначает цепи и привязывает их к символам схемы, рисует контур и крепёжные отверстия.
Плата односторонняя: дорожки по нижней меди кладёт tools/hand_route.py по списку tools/routes.py
(после gen_pcb.py его надо запускать заново). Правки в KiCad руками этими скриптами перезапишутся.
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
DRILL = 0.6                                 # все отверстия под выводы — засверловка 0.6 мм
THT_PAD = 2.0                               # пятаки выводных: не меньше 2 мм (удобно травить и паять)
SOIC_PAD_W = 0.8                            # ширина площадок SN65HVD230, как и дорожки к ним
KEEPOUT = {'L1': 6.0}                       # под корпусом дросселя 12x12 никакой меди, кроме его площадок
REF_AT = {'J2': (125.8, 141.6)}             # куда сдвинуть позиционное обозначение
MODELS = {'F1': 'Fuseholder_5x20_Littelfuse111_with_fuse.wrl',   # своя 3D-модель вместо библиотечной
          'J1': 'Wires_OBD_power_1x03.wrl', 'J2': 'Wires_OBD_CAN_1x04.wrl'}   # (модели — tools/gen_3d.py)
SMA_GAP = {'D7'}                            # SMA с площадками 2,0 мм: между ними 2,5 мм — там идёт земля

# ref: (x, y, угол, сторона)   F — сверху (выводные), B — снизу (SMD)
PLACE = {
    # верх: выводные (их ножки — снизу в меди)
    'J1': (120.0, 102.0, 90, 'F'),      # провода питания от разъёма OBD: 16, 4, 5
    'F1': (118.2, 107.0, 0, 'F'),       # клипсы 5x20
    'D8': (102.4, 106.0, 0, 'F'),       # 1.5KE6.8CA лёжа, на линии 5V
    'C3': (109.2, 113.5, 0, 'F'),       # 220u/25V стоя (не выше XIAO на гнёздах)
    'C1': (131.3, 120.3, 90, 'F'),      # 100u/50V стоя
    'Q1': (131.5, 131.0, 90, 'F'),      # IRFB4110 лёжа теплоотводом вниз, корпус над LM2596, без винта
    'D5': (134.0, 132.27, 90, 'F'),     # стабилитроны лёжа (DO-35, шаг 7.62)
    'D3': (136.5, 138.5, 270, 'F'),
    'D4': (133.3, 146.12, 90, 'F'),
    'J2': (115.0, 141.6, 90, 'F'),      # провода CAN от разъёма: 14, 6 (канал A), 8, 3 (канал B) — у трансиверов
    'U4': (128.14, 166.5, 180, 'F'),    # XIAO на гнёздах, USB к дальнему торцу
    # стойки корпуса: 35 мм поперёк, 40 мм вдоль, по центру длины — уточнить по корпусу
    'H1': (102.5, 115.0, 0, 'F'),
    'H2': (137.5, 115.0, 0, 'F'),
    'H3': (102.5, 155.0, 0, 'F'),
    'H4': (137.5, 155.0, 0, 'F'),
    # низ: SMD
    'D2': (135.6, 109.6, 180, 'B'),     # HS1M под клипсой VIN_F
    'JP1': (133.0, 122.3, 0, 'B'),
    'R1': (136.8, 131.5, 270, 'B'),
    'R2': (134.0, 135.0, 90, 'B'),
    'R9': (137.3, 149.5, 0, 'B'),       # делитель АКБ: 220k у края, 33k и 100n у ножки D0
    'R10': (132.5, 166.5, 180, 'B'),
    'C8': (132.5, 163.0, 180, 'B'),
    'U1': (123.1, 118.95, 90, 'B'),     # LM2596, ножки вниз
    'C2': (128.6, 124.55, 90, 'B'),     # 100n прямо у VIN и теплоотвода
    'D6': (123.1, 131.9, 90, 'B'),      # SS34 между SW и землёй, под ножками
    'R3': (119.44, 132.7, 180, 'B'),
    'R4': (119.44, 130.2, 0, 'B'),
    'L1': (109.8, 127.0, 90, 'B'),      # площадки — две пластины, земли под корпусом нет
    'C4': (113.5, 116.0, 0, 'B'),
    'D7': (107.0, 109.5, 180, 'B'),
    'C5': (104.3, 140.0, 180, 'B'),
    'JP2': (115.0, 138.13, 270, 'B'),   # терминатор A стоймя над J2.1-J2.2
    'R7': (117.54, 138.94, 90, 'B'),
    'JP3': (120.08, 138.13, 270, 'B'),  # терминатор B над J2.3-J2.4
    'R8': (122.62, 138.94, 90, 'B'),
    'U2': (116.5, 146.5, 90, 'B'),      # SN65HVD230 канала A над XIAO
    'C6': (111.0, 146.5, 90, 'B'),
    'U3': (122.2, 158.0, 90, 'B'),      # SN65HVD230 канала B под XIAO (между рядами гнёзд)
    'C7': (118.0, 163.0, 270, 'B'),
    'R11': (116.0, 159.9, 90, 'B'),
    'R12': (125.825, 157.0, 90, 'B'),
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


def add_keepout(board, x, y, half, side):
    """Запрет на медь под корпусом (кроме площадок самой детали): ни заливки, ни дорожек."""
    ra = pcbnew.ZONE(board)
    ra.SetIsRuleArea(True)
    ra.SetLayer(pcbnew.B_Cu if side == 'B' else pcbnew.F_Cu)
    ra.SetDoNotAllowZoneFills(True)
    ra.SetDoNotAllowTracks(True)
    ra.SetDoNotAllowVias(True)
    ra.SetDoNotAllowPads(False)
    ra.SetDoNotAllowFootprints(False)
    o = ra.Outline()
    o.NewOutline()
    for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        o.Append(mm(x + dx * half), mm(y + dy * half))
    board.Add(ra)


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
        if ref == 'Q1':
            # IRFB4110 лежит на трёх ногах без винта — крепёжное отверстие не нужно
            for pad in list(fp.Pads()):
                if pad.GetNumber() == '':
                    fp.Remove(pad)
        if ref in MODELS:
            fp.Models().clear()
            m = pcbnew.FP_3DMODEL()
            m.m_Filename = '${KIPRJMOD}/scaner.3dshapes/' + MODELS[ref]
            fp.Models().push_back(m)
        board.Add(fp)
        x, y, ang, side = PLACE[ref]
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        fp.SetOrientationDegrees(ang)
        if side == 'B':
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        if ref in REF_AT:   # подпись детали — туда, где не мешает
            fp.Reference().SetPosition(pcbnew.VECTOR2I(mm(REF_AT[ref][0]), mm(REF_AT[ref][1])))
            fp.Reference().SetTextAngleDegrees(0)
        for pad in fp.Pads():
            net = pinnets.get(ref, {}).get(pad.GetNumber())
            if net:
                pad.SetNet(netinfo[net])
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                # все отверстия — засверловка 0.6 мм (дальше рассверливаешь под ногу)
                pad.SetDrillSize(pcbnew.VECTOR2I(mm(DRILL), mm(DRILL)))
                pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_CIRCLE)
                s = pad.GetSize(pcbnew.F_Cu)
                pad.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(max(s.x, mm(THT_PAD)), max(s.y, mm(THT_PAD))))
            elif ref in ('U2', 'U3'):
                s = pad.GetSize(pcbnew.F_Cu)
                pad.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(s.x, mm(SOIC_PAD_W)))
            elif ref in SMA_GAP:
                # внешний край площадки на месте (±3,25 мм), внутренний отодвинут: 2,0 мм длина вместо 2,5
                s = pad.GetSize(pcbnew.F_Cu)
                pad.SetSize(pcbnew.F_Cu, pcbnew.VECTOR2I(mm(2.0), s.y))
                p0 = pad.GetFPRelativePosition()
                pad.SetFPRelativePosition(pcbnew.VECTOR2I(mm(2.25) if p0.x > 0 else -mm(2.25), p0.y))
        if ref in KEEPOUT:
            add_keepout(board, x, y, KEEPOUT[ref], side)

    rect = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECTANGLE)
    rect.SetStart(pcbnew.VECTOR2I(mm(X0), mm(Y0)))
    rect.SetEnd(pcbnew.VECTOR2I(mm(X0 + W), mm(Y0 + H)))
    rect.SetLayer(pcbnew.Edge_Cuts)
    rect.SetWidth(mm(0.1))
    board.Add(rect)

    # куда паять провода от разъёма OBD (номера выводов OBD слева направо)
    for text, x, y, layer in [('OBD scaner v1', X0 + W / 2, Y0 + 12.5, pcbnew.F_SilkS),
                              ('OBD -> вверх', X0 + W / 2, Y0 + H - 1.5, pcbnew.F_Fab),
                              ('OBD 16 4 5', 132.0, 102.0, pcbnew.F_SilkS),
                              ('OBD', 111.9, 143.6, pcbnew.F_SilkS),
                              ('14', 115.0, 143.6, pcbnew.F_SilkS), ('6', 117.54, 143.6, pcbnew.F_SilkS),
                              ('8', 120.08, 143.6, pcbnew.F_SilkS), ('3', 122.62, 143.6, pcbnew.F_SilkS)]:
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
