#!/usr/bin/env python3
"""Картинка платы для разводки: площадки с именами цепей, корпуса деталей (низ — красным, верх — синим),
крепёжные отверстия с зоной под стойку, дорожки, заливка земли; без дорожек — линии связей (MST по цепям),
с файлом DRC — несоединённое красным пунктиром и нарушения кружками. Запуск питоном KiCad:

  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/view_board.py scaner_v1.kicad_pcb build/view.svg [build/drc.json]

SVG открывается в браузере. Масштаб 20 пикселей на мм, сетка 5 мм с координатами KiCad.
"""
import json, math, sys
import pcbnew

PCB, OUT = sys.argv[1], sys.argv[2]
DRC = sys.argv[3] if len(sys.argv) > 3 else None
S = 20.0  # px/mm
X0, Y0, W, H = 100.0, 100.0, 40.0, 70.0
M = 2.0
b = pcbnew.LoadBoard(PCB)
mm = pcbnew.ToMM

PAL = ['#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4', '#42d4f4', '#f032e6', '#9a6324', '#469990',
       '#800000', '#808000', '#000075', '#e6a800', '#008080', '#aa6e28', '#5c5cff', '#d00070', '#2e8b57',
       '#8b4513', '#6a5acd', '#b8860b', '#228b22', '#c71585', '#1e90ff', '#ff4500', '#2f4f4f']
nets = sorted({p.GetNetname() for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()})
col = {n: PAL[i % len(PAL)] for i, n in enumerate(nets)}
col['GND'] = '#555555'


def X(v):
    return (v - X0 + M) * S


def Y(v):
    return (v - Y0 + M) * S


out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{(W + 2 * M) * S:.0f}" height="{(H + 2 * M) * S:.0f}" '
       f'font-family="Arial" style="background:#fff">']
out.append(f'<rect x="{X(X0)}" y="{Y(Y0)}" width="{W * S}" height="{H * S}" fill="#fbfaf2" stroke="#000" stroke-width="2"/>')
# сетка 5 мм
for gx in range(100, 141, 5):
    out.append(f'<line x1="{X(gx)}" y1="{Y(100)}" x2="{X(gx)}" y2="{Y(170)}" stroke="#eee" stroke-width="1"/>')
    out.append(f'<text x="{X(gx)}" y="{Y(99.2)}" font-size="16" text-anchor="middle" fill="#999">{gx}</text>')
for gy in range(100, 171, 5):
    out.append(f'<line x1="{X(100)}" y1="{Y(gy)}" x2="{X(140)}" y2="{Y(gy)}" stroke="#eee" stroke-width="1"/>')
    out.append(f'<text x="{X(99.8)}" y="{Y(gy) + 5}" font-size="16" text-anchor="end" fill="#999">{gy}</text>')

# зоны
for z in b.Zones():
    if not z.IsOnLayer(pcbnew.B_Cu):
        continue
    fp_ = z.GetFilledPolysList(pcbnew.B_Cu)
    for i in range(fp_.OutlineCount()):
        o = fp_.Outline(i)
        pts = ' '.join(f'{X(mm(o.CPoint(k).x)):.1f},{Y(mm(o.CPoint(k).y)):.1f}' for k in range(o.PointCount()))
        out.append(f'<polygon points="{pts}" fill="#cfd8cf" stroke="none"/>')
        for h in range(fp_.HoleCount(i)):
            hh = fp_.Hole(i, h)
            pts = ' '.join(f'{X(mm(hh.CPoint(k).x)):.1f},{Y(mm(hh.CPoint(k).y)):.1f}' for k in range(hh.PointCount()))
            out.append(f'<polygon points="{pts}" fill="#fbfaf2" stroke="none"/>')

# корпуса
for fp in b.GetFootprints():
    side = fp.IsFlipped()
    cy = fp.GetCourtyard(pcbnew.B_CrtYd if side else pcbnew.F_CrtYd)
    if cy.OutlineCount():
        bb = cy.BBox()
        x, y, w, h = mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetWidth()), mm(bb.GetHeight())
    else:
        bb = fp.GetBoundingBox(False)
        x, y, w, h = mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetWidth()), mm(bb.GetHeight())
    c = '#d33' if side else '#33d'
    dash = '6,4' if side else '2,3'
    out.append(f'<rect x="{X(x):.1f}" y="{Y(y):.1f}" width="{w * S:.1f}" height="{h * S:.1f}" fill="none" '
               f'stroke="{c}" stroke-width="1.5" stroke-dasharray="{dash}" opacity="0.7"/>')
    p = fp.GetPosition()
    out.append(f'<text x="{X(x) + 3:.1f}" y="{Y(y) + 15:.1f}" font-size="15" font-weight="bold" fill="{c}">{fp.GetReference()}</text>')

# дорожки
for t in b.GetTracks():
    if t.Type() == pcbnew.PCB_VIA_T:
        c = t.GetPosition()
        out.append(f'<circle cx="{X(mm(c.x)):.1f}" cy="{Y(mm(c.y)):.1f}" r="{mm(t.GetWidth(pcbnew.F_Cu)) / 2 * S:.1f}" fill="#2a2" opacity="0.8"/>')
        continue
    a, e = t.GetStart(), t.GetEnd()
    top = t.GetLayer() == pcbnew.F_Cu
    c = '#1a1' if top else '#c87533'
    out.append(f'<line x1="{X(mm(a.x)):.1f}" y1="{Y(mm(a.y)):.1f}" x2="{X(mm(e.x)):.1f}" y2="{Y(mm(e.y)):.1f}" '
               f'stroke="{c}" stroke-width="{mm(t.GetWidth()) * S:.1f}" stroke-linecap="round" opacity="{0.6 if top else 0.85}"/>')

# площадки
padinfo = []
for fp in b.GetFootprints():
    for p in fp.Pads():
        c = p.GetPosition()
        n = p.GetNetname()
        bb = p.GetBoundingBox()
        w, h = mm(bb.GetWidth()), mm(bb.GetHeight())
        cx, cy_ = mm(c.x), mm(c.y)
        if not p.GetNumber():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                out.append(f'<circle cx="{X(cx)}" cy="{Y(cy_)}" r="{w / 2 * S}" fill="#000"/>')
                out.append(f'<circle cx="{X(cx)}" cy="{Y(cy_)}" r="{2.4 * S}" fill="none" stroke="#000" stroke-dasharray="3,3"/>')
            continue
        fill = col.get(n, '#bbb') if n and not n.startswith('unconnected') else '#ccc'
        tht = p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
        if p.GetShape(pcbnew.B_Cu) == pcbnew.PAD_SHAPE_CIRCLE:
            out.append(f'<circle cx="{X(cx):.1f}" cy="{Y(cy_):.1f}" r="{w / 2 * S:.1f}" fill="{fill}" opacity="0.9"/>')
        else:
            out.append(f'<rect x="{X(cx - w / 2):.1f}" y="{Y(cy_ - h / 2):.1f}" width="{w * S:.1f}" height="{h * S:.1f}" fill="{fill}" opacity="0.9"/>')
        if tht:
            out.append(f'<circle cx="{X(cx):.1f}" cy="{Y(cy_):.1f}" r="{0.3 * S:.1f}" fill="#fff"/>')
        lab = (n or '').lstrip('/').replace('unconnected-', 'nc').replace('VIN_', 'V').replace('CAN', '')
        if lab.startswith('nc'):
            lab = 'nc'
        out.append(f'<text x="{X(cx):.1f}" y="{Y(cy_) + 4:.1f}" font-size="11" text-anchor="middle" fill="#000" '
                   f'stroke="#fff" stroke-width="2.5" paint-order="stroke">{lab}</text>')
        if n and not n.startswith('unconnected'):
            padinfo.append((n, cx, cy_))

# связи: MST по площадкам каждой цепи (кроме земли), только если дорожек нет совсем
if not any(True for _ in b.GetTracks()):
    by = {}
    for n, x, y in padinfo:
        if n == 'GND':
            continue
        by.setdefault(n, []).append((x, y))
    for n, pts in by.items():
        pts = list(dict.fromkeys(pts))
        if len(pts) < 2:
            continue
        inside = {0}
        while len(inside) < len(pts):
            best = min(((math.dist(pts[i], pts[j]), i, j) for i in inside for j in range(len(pts)) if j not in inside))
            _, i, j = best
            inside.add(j)
            out.append(f'<line x1="{X(pts[i][0]):.1f}" y1="{Y(pts[i][1]):.1f}" x2="{X(pts[j][0]):.1f}" y2="{Y(pts[j][1]):.1f}" '
                       f'stroke="{col[n]}" stroke-width="2" opacity="0.6"/>')
if DRC:
    d = json.load(open(DRC, encoding='utf-8'))
    for u in d.get('unconnected_items', []):
        it = u['items']
        if len(it) == 2:
            a, e = it[0]['pos'], it[1]['pos']
            out.append(f'<line x1="{X(a["x"]):.1f}" y1="{Y(a["y"]):.1f}" x2="{X(e["x"]):.1f}" y2="{Y(e["y"]):.1f}" '
                       f'stroke="#f00" stroke-width="3" stroke-dasharray="6,3"/>')
    for v in d.get('violations', []):
        if v['type'].startswith('silk') or v['type'] == 'lib_footprint_mismatch':
            continue
        for it in v['items']:
            pos = it['pos']
            out.append(f'<circle cx="{X(pos["x"]):.1f}" cy="{Y(pos["y"]):.1f}" r="12" fill="none" stroke="#f0f" stroke-width="3"/>')
out.append('</svg>')
open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
print('ok', OUT)
