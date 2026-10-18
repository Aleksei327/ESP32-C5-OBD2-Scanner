#!/usr/bin/env python3
"""Запасной вариант: автоматическая разводка через Freerouting. Основная разводка платы v1 —
ручная (tools/routes.py + tools/hand_route.py); этот скрипт её затрёт. Запуск питоном KiCad:

  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/route.py

Плата односторонняя: дорожки — нижняя медь (B.Cu), верхняя медь (F.Cu) — перемычки
из провода между отверстиями. Поэтому:
  - верхний слой для роутера намного дороже нижнего, переход (= перемычка) тоже дорогой;
  - к ножкам выводных деталей сверху не подходим: там стоит сама деталь (запретные зоны);
  - земля не разводится дорожками — это сплошная заливка снизу (делается после роутера);
  - сигналы 0.8 мм, питание 1.0–1.5 мм, зазор 0.4 мм; перемычка — площадка 2.0 мм, отверстие 0.6.
После разводки считаем перемычки и сколько раз каждая цепь прыгает наверх (норма — не больше 2).
Перезапускать только на плате прямо из gen_pcb.py — ручные дорожки перезапишутся.

Настройки через окружение: TRACK, PTRACK (мм), VIA_COST, TOP_COST, PASSES.
"""
import collections
import os
import re
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
PCB = os.path.join(PRJ, 'scaner_v1.kicad_pcb')
BUILD = os.path.join(PRJ, 'build')
JAVA = r'C:\Program Files\Android\Android Studio1\jbr\bin\java.exe'
FREEROUTING = r'D:\esp\tools\freerouting-2.5.0.jar'

TRACK = float(os.environ.get('TRACK', '0.8'))
POWER_TRACK = float(os.environ.get('PTRACK', '1.2'))
CLEARANCE = 0.4
VIA, VIA_DRILL = 2.0, 0.6
VIA_COST = int(os.environ.get('VIA_COST', '200'))
TOP_COST = float(os.environ.get('TOP_COST', '20'))
PASSES = int(os.environ.get('PASSES', '60'))
POWER = {'VBAT_OBD', 'VIN_F', 'VIN_PROT', 'VIN_BUCK', 'SW', 'V5_BUCK', 'V5'}
GROUND = 'GND'


def mm(v):
    return pcbnew.FromMM(v)


def um(v):
    return int(round(v * 1000))


def full_pads_for_router(board):
    """Для экспорта роутеру: у ножек снова обычная площадка на обоих слоях
    (экспорт KiCad не понимает разные размеры по слоям)."""
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH:
                continue
            size, shape = p.GetSize(pcbnew.B_Cu), p.GetShape(pcbnew.B_Cu)
            rr = p.GetRoundRectRadiusRatio(pcbnew.B_Cu)
            ps = p.Padstack()
            ps.SetMode(pcbnew.PADSTACK.MODE_NORMAL)
            p.SetPadstack(ps)
            p.SetSize(pcbnew.F_Cu, size)
            p.SetShape(pcbnew.F_Cu, shape)
            if shape == pcbnew.PAD_SHAPE_ROUNDRECT:
                p.SetRoundRectRadiusRatio(pcbnew.F_Cu, rr)


def _block_end(t, i):
    depth = 0
    for j in range(i, len(t)):
        if t[j] == '(':
            depth += 1
        elif t[j] == ')':
            depth -= 1
            if depth == 0:
                return j + 1
    return len(t)


def _remove_blocks(t, pattern):
    out, pos = [], 0
    for m in re.finditer(pattern, t):
        if m.start() < pos:
            continue
        end = _block_end(t, m.start())
        out.append(t[pos:m.start()])
        pos = end
    out.append(t[pos:])
    return ''.join(out)


def _strip_top_shapes(t):
    """У сквозных площадок ([A] — все слои) вырезаем форму на F.Cu (по скобкам: бывает многострочной)."""
    out, pos = [], 0
    for m in re.finditer(r'\(padstack ("[^"]*"|\S+)', t):
        if m.start() < pos or '[A]' not in m.group(1):
            continue
        end = _block_end(t, m.start())
        block = t[m.start():end]
        parts, k = [], 0
        for s in re.finditer(r'\(shape \(\w+ F\.Cu', block):
            parts.append(block[k:s.start()])
            k = _block_end(block, s.start())
        parts.append(block[k:])
        out.append(t[pos:m.start()] + ''.join(parts))
        pos = end
    out.append(t[pos:])
    return ''.join(out)


def _pad_dia(name):
    nums = [float(x) for x in re.findall(r'(\d+(?:\.\d+)?)', name.split('Pad_', 1)[-1])[:2]]
    return max(nums) if nums else 2000.0


def patch_dsn(t, nets):
    via = f'Via[0-1]_{um(VIA)}:{um(VIA_DRILL)}_um'
    t = re.sub(r'\(via "Via\[0-1\][^"]*"\)', f'(via "{via}")', t)
    t = re.sub(r'\(padstack "Via\[0-1\][^"]*"\s*\(shape \(circle F\.Cu \d+\)\)\s*\(shape \(circle B\.Cu \d+\)\)',
               f'(padstack "{via}"\n      (shape (circle F.Cu {um(VIA)}))\n      (shape (circle B.Cu {um(VIA)}))', t)
    t = re.sub(r'(\(structure.*?\(rule\s*)\(width \d+\)\s*\(clearance \d+\)',
               lambda m: m.group(1) + f'(width {um(TRACK)})\n      (clearance {um(CLEARANCE)})', t, count=1, flags=re.S)
    autoroute = f'''
    (autoroute_settings
      (fanout off) (autoroute on) (postroute on) (vias on)
      (via_costs {VIA_COST}) (plane_via_costs 5) (start_ripup_costs 100) (start_pass_no 1)
      (layer_rule F.Cu (active on) (preferred_direction horizontal)
        (preferred_direction_trace_costs {TOP_COST}) (against_preferred_direction_trace_costs {TOP_COST}))
      (layer_rule B.Cu (active on) (preferred_direction vertical)
        (preferred_direction_trace_costs 1) (against_preferred_direction_trace_costs 1.1))
    )
  )
  (placement'''
    t = re.sub(r'\)\s*\(placement', autoroute, t, count=1)

    # ножки выводных деталей: сверху у них нет меди, а есть корпус детали — запретная зона
    def add_keepouts(m):
        block = m.group(0)
        keep = []
        for pm in re.finditer(r'\(pin (\S+)(?: \(rotate [^)]*\))? \S+ (-?[\d.]+) (-?[\d.]+)\)', block):
            if '[A]' in pm.group(1):
                d = _pad_dia(pm.group(1))
                keep.append(f'      (keepout "" (circle F.Cu {d:.0f} {pm.group(2)} {pm.group(3)}))\n')
        if not keep:
            return block
        return block[:-1].rstrip() + '\n' + ''.join(keep) + '    )'
    t = re.sub(r'\(image .*?\n    \)', add_keepouts, t, flags=re.S)
    # у самих площадок ножек убираем верхний слой — сверху к ним не подключиться
    t = _strip_top_shapes(t)

    # землю роутер не трогает — будет заливкой
    t = _remove_blocks(t, r'\(net "?' + GROUND + r'"?\s*\(pins')
    t = _remove_blocks(t, r'\(class kicad_default')
    name = lambda n: n.strip('"').lstrip('/')
    sig = [n for n in nets if name(n) not in POWER and name(n) != GROUND]
    pwr = [n for n in nets if name(n) in POWER]

    def cls(cname, members, w):
        return (f'    (class {cname} {" ".join(members)}\n      (circuit (use_via "{via}"))\n'
                f'      (rule (width {um(w)}) (clearance {um(CLEARANCE)}))\n    )\n')
    t = re.sub(r'\n  \)\n  \(wiring', lambda m: '\n' + cls('signal', sig, TRACK) + cls('power', pwr, POWER_TRACK)
               + '  )\n  (wiring', t, count=1)
    return t


def add_ground_fill(board):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.B_Cu)
    zone.SetNet(board.FindNet(GROUND))
    o = zone.Outline()
    o.NewOutline()
    for x, y in ((100.3, 100.3), (139.7, 100.3), (139.7, 169.7), (100.3, 169.7)):
        o.Append(mm(x), mm(y))
    zone.SetLocalClearance(mm(1.0))     # земля отступает от чужой меди на 1 мм (так удобнее травить)
    zone.SetMinThickness(mm(1.0))       # и нигде не уже 1 мм
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)   # земля прилегает к площадкам сплошь, без щелей
    board.Add(zone)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def jumpers(board):
    """Перемычки = связные куски верхней меди. Возвращает {цепь: [(сегментов, длина мм), ...]}."""
    top = [tr for tr in board.GetTracks() if tr.GetLayer() == pcbnew.F_Cu and tr.Type() == pcbnew.PCB_TRACE_T]
    parent = list(range(len(top)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    pts = collections.defaultdict(list)
    for i, tr in enumerate(top):
        for p in (tr.GetStart(), tr.GetEnd()):
            pts[(p.x // 1000, p.y // 1000)].append(i)
    for idx in pts.values():
        for j in idx[1:]:
            parent[find(j)] = find(idx[0])
    groups = collections.defaultdict(list)
    for i, tr in enumerate(top):
        groups[find(i)].append(tr)
    out = collections.defaultdict(list)
    for g in groups.values():
        length = sum(pcbnew.ToMM(tr.GetLength()) for tr in g)
        out[g[0].GetNetname()].append((len(g), round(length, 1)))
    return out


def main():
    os.makedirs(BUILD, exist_ok=True)
    dsn = os.path.join(BUILD, 'route.dsn')
    ses = os.path.join(BUILD, 'route.ses')
    if os.path.exists(ses):
        os.remove(ses)

    tmp = pcbnew.LoadBoard(PCB)
    for tr in list(tmp.GetTracks()):
        tmp.Remove(tr)
    for z in list(tmp.Zones()):
        tmp.Remove(z)
    full_pads_for_router(tmp)
    pcbnew.ExportSpecctraDSN(tmp, dsn)
    t = open(dsn, encoding='utf-8').read()
    net_sec = t.split('(network', 1)[1]
    nets = sorted(set(re.findall(r'\(net ("[^"]*"|[^\s()]+)', net_sec)))
    open(dsn, 'w', encoding='utf-8').write(patch_dsn(t, nets))

    print(f'Freerouting: {len(nets) - 1} цепей (без земли), до {PASSES} проходов…', flush=True)
    r = subprocess.run([JAVA, '-jar', FREEROUTING, '-de', dsn, '-do', ses, '-mp', str(PASSES), '-l', 'en'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    open(os.path.join(BUILD, 'route.log'), 'w', encoding='utf-8').write(r.stdout + r.stderr)
    if not os.path.exists(ses):
        print(r.stdout[-3000:], r.stderr[-3000:])
        sys.exit('Freerouting не выдал результат')

    board = pcbnew.LoadBoard(PCB)
    for tr in list(board.GetTracks()):
        board.Remove(tr)
    for z in list(board.Zones()):
        board.Remove(z)
    pcbnew.ImportSpecctraSES(board, ses)
    add_ground_fill(board)
    pcbnew.SaveBoard(PCB, board)

    m = re.findall(r'(\d+) unrouted and (\d+) violations', r.stdout + r.stderr)
    print('Роутер:', f'не разведено {m[-1][0]}, нарушений {m[-1][1]}' if m else '?')
    vias = [x for x in board.GetTracks() if x.Type() == pcbnew.PCB_VIA_T]
    j = jumpers(board)
    total = sum(len(v) for v in j.values())
    worst = max((len(v) for v in j.values()), default=0)
    print(f'Отверстий под перемычки: {len(vias)}, перемычек сверху: {total}, больше всего у одной цепи: {worst}')
    for net, items in sorted(j.items(), key=lambda kv: -len(kv[1])):
        flag = '  <-- больше 2!' if len(items) > 2 else ''
        bends = ', '.join(f'{L} мм' + ('' if n == 1 else f' ({n} сегм.)') for n, L in items)
        print(f'  {net}: {len(items)} шт: {bends}{flag}')


if __name__ == '__main__':
    main()
