#!/usr/bin/env python3
"""Ручная разводка: дорожки из tools/routes.py кладутся на плату, земля — заливкой. Запуск питоном KiCad:

  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/hand_route.py

Берёт плату прямо из gen_pcb.py (scaner_v1.kicad_pcb), стирает старые дорожки и заливки,
кладёт дорожки по нижней меди и перемычки сверху, заливает землю снизу, сохраняет
и прогоняет DRC. В конце — сколько перемычек и сколько раз каждая цепь прыгает наверх.
"""
import collections
import json
import os
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
PCB = os.path.join(PRJ, 'scaner_v1.kicad_pcb')
CLI = r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
sys.path.insert(0, HERE)
from route import add_ground_fill, jumpers  # noqa: E402
from routes import JUMPERS, TRACKS  # noqa: E402

VIA, VIA_DRILL = 2.0, 0.6


def mm(v):
    return pcbnew.FromMM(v)


def pad_pos(board, ref):
    r, num = ref.split('.')
    fp = board.FindFootprintByReference(r)
    if fp is None:
        sys.exit(f'нет детали {r}')
    for p in fp.Pads():
        if p.GetNumber() == num:
            c = p.GetPosition()
            return pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)
    sys.exit(f'нет площадки {ref}')


def point(board, p):
    return pad_pos(board, p) if isinstance(p, str) else p


def find_net(board, name):
    net = board.FindNet(name) or board.FindNet('/' + name)
    if net is None:
        sys.exit(f'нет цепи {name}')
    return net


def add_seg(board, net, layer, w, a, b):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
    t.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
    t.SetWidth(mm(w))
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)


def main():
    board = pcbnew.LoadBoard(PCB)
    for tr in list(board.GetTracks()):
        board.Remove(tr)
    for z in list(board.Zones()):
        if not z.GetIsRuleArea():  # запреты (под дросселем) ставит gen_pcb.py — их не трогаем
            board.Remove(z)

    for name, w, pts in TRACKS:
        net = find_net(board, name)
        pts = [point(board, p) for p in pts]
        for a, b in zip(pts, pts[1:]):
            add_seg(board, net, pcbnew.B_Cu, w, a, b)

    for name, a, b in JUMPERS:
        net = find_net(board, name)
        ends = []
        for p in (a, b):
            q = point(board, p)
            ends.append(q)
            if isinstance(p, str):
                continue  # перемычка втыкается прямо в отверстие выводной детали
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(mm(q[0]), mm(q[1])))
            v.SetWidth(mm(VIA))
            v.SetDrill(mm(VIA_DRILL))
            v.SetNet(net)
            board.Add(v)
        add_seg(board, net, pcbnew.F_Cu, 0.8, ends[0], ends[1])

    add_ground_fill(board)
    pcbnew.SaveBoard(PCB, board)

    out = os.path.join(PRJ, 'build', 'drc.json')
    subprocess.run([CLI, 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', out, PCB],
                   capture_output=True)
    d = json.load(open(out, encoding='utf-8'))
    skip = {'silk_overlap', 'silk_over_copper', 'silk_edge_clearance', 'lib_footprint_mismatch'}
    viol = [v for v in d.get('violations', []) if v['type'] not in skip]
    unc = d.get('unconnected_items', [])
    print(f'DRC: нарушений {len(viol)}, не разведено {len(unc)}')
    for v in viol:
        print('  ', v['type'], '|', ' / '.join(i['description'][:70] for i in v['items']))
    for u in unc:
        print('   не соединено:', ' / '.join(i['description'][:70] for i in u['items']))
    j = jumpers(board)
    print(f'Перемычек: {sum(len(v) for v in j.values())}')
    for net, items in sorted(j.items()):
        print(f'  {net}: {len(items)}' + ('  <-- больше 2!' if len(items) > 2 else ''))


if __name__ == '__main__':
    main()
