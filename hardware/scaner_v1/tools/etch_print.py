#!/usr/bin/env python3
"""Шаблоны для травления 1:1 на A4 — вместо окна «Печать» KiCad: геометрия, раскладка, PDF.
Окно с просмотром, перетаскиванием копий и печатью на принтер — tools/etch_window.py (оно же кнопка
в редакторе плат). Без окна, сразу четыре PDF с автоматической раскладкой (плата должна быть сохранена):

  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/etch_print.py [плата.kicad_pcb] [--copies N] [--open]

Пишет в <папка платы>/etch/ четыре PDF (по одной странице, лист заполняется копиями платы —
выбрать лучшую или сложить две для плотности):
  1_NEGATIV_TONEROM_VNIZ.pdf      плёночный (негативный) фоторезист: прозрачное = медь остаётся
  1M_NEGATIV_TONEROM_VVERH.pdf    то же, если класть тонером вверх (зеркально)
  2_POZITIV_LUT_TONEROM_VNIZ.pdf  ЛУТ и позитивный резист: чёрное = медь остаётся
  2M_POZITIV_TONEROM_VVERH.pdf    то же тонером вверх (зеркально)

«Тонером вниз» = печать лежит на меди (нет зазора, края резкие). KiCad рисует B.Cu так, как он виден
сверху сквозь плату, поэтому для нижней меди «тонером вниз» — БЕЗ зеркала, для F.Cu — с зеркалом.
Заливки перезаливаются перед печатью (как кнопка B). Медь берётся из KiCad целиком (дорожки,
пятаки, заливки, текст на слое); в центрах сверлёных пятаков — точки под сверло, в центрах круглых
вырезов Edge.Cuts — крестик. Снаружи углов платы — уголки для совмещения и резки.
Надписи на листе рисуются шрифтом KiCad (полигонами), поэтому PDF не зависит от шрифтов Windows.
"""
import argparse
import datetime
import math
import os
import sys
import zlib

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)

MARGIN = 12.0      # поля листа, мм (непечатаемая зона у принтеров ~5 мм)
FRAME = 3.0        # чёрное поле вокруг платы в негативе
GAP = 8.0          # между копиями
DOT = 0.4          # метка под сверло
MARK_W, MARK_L, MARK_OFF = 0.3, 4.0, 0.5   # уголки: толщина, длина, отступ от края платы
RULER = 100.0      # линейки для проверки масштаба

BLACK, WHITE = 0.0, 1.0

VARIANTS = [  # (файл, негатив, тонером вниз)
    ('1_NEGATIV_TONEROM_VNIZ', True, True),
    ('1M_NEGATIV_TONEROM_VVERH', True, False),
    ('2_POZITIV_LUT_TONEROM_VNIZ', False, True),
    ('2M_POZITIV_TONEROM_VVERH', False, False),
]


def iu(v):
    return pcbnew.FromMM(v)


def mm(v):
    return pcbnew.ToMM(v)


# --- геометрия: страница = список заливок (серый, контуры в мм от левого верхнего угла, even-odd) ---

def contours(ps, xf):
    out = []
    for i in range(ps.OutlineCount()):
        chains = [ps.Outline(i)] + [ps.Hole(i, h) for h in range(ps.HoleCount(i))]
        for ch in chains:
            out.append([xf(ch.CPoint(k)) for k in range(ch.PointCount())])
    return out


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def circle(cx, cy, d, n=24):
    return [(cx + d / 2 * math.cos(2 * math.pi * k / n), cy + d / 2 * math.sin(2 * math.pi * k / n))
            for k in range(n)]


def cross(cx, cy, arm, w):
    a, h = arm, w / 2
    return [(cx - a, cy - h), (cx - h, cy - h), (cx - h, cy - a), (cx + h, cy - a), (cx + h, cy - h),
            (cx + a, cy - h), (cx + a, cy + h), (cx + h, cy + h), (cx + h, cy + a), (cx - h, cy + a),
            (cx - h, cy + h), (cx - a, cy + h)]


def corner(cx, cy, sx, sy):
    """Уголок снаружи угла платы (cx, cy); sx, sy = ±1 — куда «наружу»."""
    ox, oy = cx + sx * (MARK_OFF + MARK_W), cy + sy * (MARK_OFF + MARK_W)
    ix, iy = cx + sx * MARK_OFF, cy + sy * MARK_OFF
    return [(ox, oy), (ox - sx * MARK_L, oy), (ox - sx * MARK_L, iy), (ix, iy), (ix, oy - sy * MARK_L),
            (ox, oy - sy * MARK_L)]


def text(board, s, x, y, h, align='left', max_w=None):
    """Строка шрифтом KiCad; (x, y) — верх строки (левый край или центр)."""
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetTextSize(pcbnew.VECTOR2I(iu(h), iu(h)))
    t.SetTextThickness(iu(h * 0.14))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER if align == 'center' else pcbnew.GR_TEXT_H_ALIGN_LEFT)
    t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_TOP)
    t.SetPosition(pcbnew.VECTOR2I(0, 0))
    ps = pcbnew.SHAPE_POLY_SET()
    t.TransformTextToPolySet(ps, 0, iu(0.005), pcbnew.ERROR_INSIDE)
    ps.Simplify()
    w = mm(ps.BBox().GetWidth())
    if max_w and w > max_w:
        return text(board, s, x, y, h * max_w / w * 0.98, align)
    return contours(ps, lambda p: (x + mm(p.x), y + mm(p.y)))


# --- что берём с платы ---

class Board:
    def __init__(self, board, layer):
        self.board = board
        self.layer = layer
        out = pcbnew.SHAPE_POLY_SET()
        if board.GetBoardPolygonOutlines(out, False) and out.OutlineCount():
            bb = out.BBox()
        else:
            bb = board.GetBoardEdgesBoundingBox()
        self.x0, self.y0 = mm(bb.GetX()), mm(bb.GetY())
        self.x1, self.y1 = mm(bb.GetRight()), mm(bb.GetBottom())
        self.w, self.h = self.x1 - self.x0, self.y1 - self.y0

        self.copper = pcbnew.SHAPE_POLY_SET()
        board.ConvertBrdLayerToPolygonalContours(layer, self.copper)
        self.copper.Simplify()

        self.dots = []      # (x, y, d) — сверлёные пятаки и переходные
        self.crosses = []   # (x, y, arm) — вырезы и отверстия без меди
        for fp in board.GetFootprints():
            for p in fp.Pads():
                d = p.GetDrillSize()
                if not min(d.x, d.y):
                    continue
                c = p.GetPosition()
                if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH or not p.IsOnLayer(layer):
                    self.crosses.append((mm(c.x), mm(c.y), min(1.0, mm(min(d.x, d.y)) * 0.4)))
                else:
                    self.dots.append((mm(c.x), mm(c.y), min(DOT, mm(min(d.x, d.y)))))
        for t in board.GetTracks():
            if t.GetClass() == 'PCB_VIA' and t.IsOnLayer(layer):
                c = t.GetPosition()
                self.dots.append((mm(c.x), mm(c.y), min(DOT, mm(t.GetDrillValue()))))
        edge = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
        for fp in board.GetFootprints():
            edge += [g for g in fp.GraphicalItems() if g.GetLayer() == pcbnew.Edge_Cuts]
        for d in edge:
            if d.GetShape() != pcbnew.SHAPE_T_CIRCLE:
                continue
            c, r = d.GetCenter(), mm(d.GetRadius())
            x, y = mm(c.x), mm(c.y)
            if self.x0 < x - r and x + r < self.x1 and self.y0 < y - r and y + r < self.y1:
                self.crosses.append((x, y, min(1.0, r * 0.4)))


def mirror_for(layer, toner_down):
    """KiCad рисует слои видом сверху: нижняя медь тонером к меди — без зеркала, верхняя — с зеркалом."""
    return toner_down == (layer == pcbnew.F_Cu)


def copy_ops(b, px, py, negative, mirror, dots=True, marks=True):
    """Одна копия платы; (px, py) — левый верхний угол платы на листе."""
    def xf_mm(x, y):
        return (px + (b.x1 - x if mirror else x - b.x0), py + (y - b.y0))

    def xf(p):
        return xf_mm(mm(p.x), mm(p.y))

    cu, bare = (WHITE, BLACK) if negative else (BLACK, WHITE)
    ops = []
    if negative:
        ops.append((BLACK, [rect(px - FRAME, py - FRAME, px + b.w + FRAME, py + b.h + FRAME)]))
    ops.append((cu, contours(b.copper, xf)))
    if marks:
        ms = [corner(px, py, -1, -1), corner(px + b.w, py, 1, -1),
              corner(px, py + b.h, -1, 1), corner(px + b.w, py + b.h, 1, 1)]
        ms += [cross(*xf_mm(x, y), arm, 0.3) for x, y, arm in b.crosses]
        ops.append((cu, ms))
    if dots:
        ops.append((bare, [circle(*xf_mm(x, y), d) for x, y, d in b.dots]))
    return ops


def ruler_ops(board, x0, y0):
    """Линейки RULER мм вправо и вверх от (x0, y0), риски наружу, подписи в сантиметрах."""
    lw, tw = 0.25, 0.15
    shapes = [rect(x0 - lw, y0, x0 + RULER, y0 + lw), rect(x0 - lw, y0 - RULER, x0, y0)]
    for i in range(int(RULER) + 1):
        ln = 3.0 if i % 10 == 0 else 2.0 if i % 5 == 0 else 1.2
        shapes.append(rect(x0 + i - tw / 2, y0 + lw, x0 + i + tw / 2, y0 + lw + ln))
        shapes.append(rect(x0 - lw - ln, y0 - i - tw / 2, x0 - lw, y0 - i + tw / 2))
        if i % 10 == 0:
            shapes += text(board, str(i // 10), x0 + i, y0 + lw + 3.6, 1.8, 'center')
            if i:
                shapes += text(board, str(i // 10), x0 - lw - 6.2, y0 - i - 0.9, 1.8)
    shapes += text(board, 'см', x0 + RULER + 2.5, y0 + 0.2, 1.8)
    return [(BLACK, shapes)]


def ruler_origin(H):
    return MARGIN + 7.5, H - MARGIN - 20.0


def free_area(W, H, labels=True):
    """Где можно ставить копии (с рамкой): x0, y0, x1, y1 в мм."""
    if not labels:
        return MARGIN, MARGIN, W - MARGIN, H - MARGIN
    rx, ry = ruler_origin(H)
    return rx + 4.0, MARGIN + 17.0, W - MARGIN, ry - 4.0


def auto_positions(b, copies=0, labels=True, page=None):
    """Сетка копий: (W, H, [(x, y) левых верхних углов плат]). copies=0 — сколько влезет."""
    fw, fh = b.w + 2 * FRAME, b.h + 2 * FRAME
    for W, H in ([page] if page else [(210.0, 297.0), (297.0, 210.0)]):
        gx0, gy0, gx1, gy1 = free_area(W, H, labels)
        cols_max = int((gx1 - gx0 + GAP) // (fw + GAP))
        rows_max = int((gy1 - gy0 + GAP) // (fh + GAP))
        if cols_max * rows_max:
            break
    else:
        return W, H, []
    n = min(copies or cols_max * rows_max, cols_max * rows_max)
    cols = min(cols_max, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)
    if rows > rows_max:
        cols, rows = cols_max, math.ceil(n / cols_max)
    x_start = gx0 + (gx1 - gx0 - (cols * fw + (cols - 1) * GAP)) / 2
    pos = []
    for k in range(n):
        r, c = divmod(k, cols)
        pos.append((x_start + c * (fw + GAP) + FRAME, gy0 + r * (fh + GAP) + FRAME))
    return W, H, pos


def label_ops(b, name, W, H, negative, toner_down, n, stamp):
    mirror = mirror_for(b.layer, toner_down)
    lname = b.board.GetLayerName(b.layer)
    tw = W - 2 * MARGIN
    kind = 'НЕГАТИВ — плёночный фоторезист' if negative else 'ПОЗИТИВ — ЛУТ и позитивный фоторезист'
    head = [
        text(b.board, '%s  ·  %s  ·  %s' % (kind, name, lname), MARGIN, MARGIN, 3.5, max_w=tw),
        text(b.board, 'Класть ТОНЕРОМ %s (печатью %s меди). %s.' % (
            'ВНИЗ' if toner_down else 'ВВЕРХ', 'к' if toner_down else 'от',
            'Зеркально' if mirror else 'Без зеркала'), MARGIN, MARGIN + 5.5, 2.6, max_w=tw),
        text(b.board, ('Прозрачное = медь остаётся, чёрное = вытравится.' if negative else
                       'Чёрное = медь остаётся, белое = вытравится.') +
             ' Точки в пятаках — метки под сверло.', MARGIN, MARGIN + 9.5, 2.2, max_w=tw),
    ]
    fy = H - MARGIN - 9.6
    foot = [
        text(b.board, 'Печать: «Фактический размер» / 100 %%, НЕ «Подогнать». Линейки ровно %d мм — '
                      'проверь обе.' % RULER, MARGIN, fy, 2.2, max_w=tw),
        text(b.board, 'Принтер: максимальная плотность, экономия тонера выкл.' +
             (' Для плотности можно сложить 2 копии.' if negative else ''), MARGIN, fy + 3.4, 2.2, max_w=tw),
        text(b.board, 'Плата %.1f × %.1f мм, копий %d.  %s  ·  «Печать для травления»' % (
            b.w, b.h, n, stamp), MARGIN, fy + 6.8, 2.2, max_w=tw),
    ]
    return [(BLACK, [c for t in head + foot for c in t])] + ruler_ops(b.board, *ruler_origin(H))


def sheet_ops(b, name, W, H, positions, negative, toner_down, dots=True, marks=True, labels=True, stamp=None):
    """Весь лист: копии в positions + подписи и линейки."""
    mirror = mirror_for(b.layer, toner_down)
    ops = []
    for px, py in positions:
        ops += copy_ops(b, px, py, negative, mirror, dots, marks)
    if labels:
        stamp = stamp or datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
        ops += label_ops(b, name, W, H, negative, toner_down, len(positions), stamp)
    return ops


# --- запись PDF/SVG ---

def pdf_str(s):
    return '<FEFF' + s.encode('utf-16-be').hex().upper() + '>'


def write_pdf(path, W, H, ops, title):
    k = 72 / 25.4
    out = []
    for gray, shapes in ops:
        if not shapes:
            continue
        out.append('%g g' % gray)
        for pts in shapes:
            out.append('%.3f %.3f m' % (pts[0][0] * k, (H - pts[0][1]) * k))
            out += ['%.3f %.3f l' % (x * k, (H - y) * k) for x, y in pts[1:]]
            out.append('h')
        out.append('f*')
    stream = zlib.compress('\n'.join(out).encode('ascii'))
    now = datetime.datetime.now().strftime('D:%Y%m%d%H%M%S')
    objs = [
        '<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /PrintScaling /None >> >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.3f %.3f] /Contents 4 0 R /Resources << >> >>'
        % (W * k, H * k),
        None,
        '<< /Title %s /Producer (etch_print.py) /CreationDate (%s) >>' % (pdf_str(title), now),
    ]
    data = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(data))
        if o is None:
            data += b'%d 0 obj\n<< /Length %d /Filter /FlateDecode >>\nstream\n' % (i, len(stream))
            data += stream + b'\nendstream\nendobj\n'
        else:
            data += ('%d 0 obj\n%s\nendobj\n' % (i, o)).encode('ascii')
    xref = len(data)
    data += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objs) + 1)
    data += b''.join(b'%010d 00000 n \n' % o for o in offs)
    data += b'trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objs) + 1, xref)
    with open(path, 'wb') as f:
        f.write(data)


def write_svg(path, W, H, ops):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" height="%gmm" viewBox="0 0 %g %g">'
           % (W, H, W, H), '<rect width="100%" height="100%" fill="#fff"/>']
    for gray, shapes in ops:
        if shapes:
            d = ' '.join('M' + ' L'.join('%.3f %.3f' % p for p in pts) + ' Z' for pts in shapes)
            out.append('<path fill="%s" fill-rule="evenodd" d="%s"/>' % ('#000' if gray == BLACK else '#fff', d))
    out.append('</svg>')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))


def load(board, layer=pcbnew.B_Cu):
    """Перезаливает зоны (как кнопка B) и собирает медь слоя; возвращает (Board, имя платы)."""
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return Board(board, layer), os.path.splitext(os.path.basename(board.GetFileName()))[0]


def make_all(board, layer=pcbnew.B_Cu, copies=0, out_dir=None, svg=False):
    """Пишет 4 PDF с автоматической раскладкой; возвращает (папка, [файлы], копий на листе)."""
    out_dir = out_dir or os.path.join(os.path.dirname(board.GetFileName()), 'etch')
    os.makedirs(out_dir, exist_ok=True)
    b, name = load(board, layer)
    W, H, pos = auto_positions(b, copies)
    if not pos:
        raise SystemExit('плата %.1f x %.1f мм не влезает на A4' % (b.w, b.h))
    stamp = datetime.datetime.now().strftime('%d.%m.%Y %H:%M')
    files = []
    for fname, negative, toner_down in VARIANTS:
        ops = sheet_ops(b, name, W, H, pos, negative, toner_down, stamp=stamp)
        f = os.path.join(out_dir, fname + '.pdf')
        write_pdf(f, W, H, ops, '%s %s %s' % (name, board.GetLayerName(layer), fname))
        files.append(f)
        if svg:
            write_svg(f[:-4] + '.svg', W, H, ops)
    return out_dir, files, len(pos)


def main():
    p = argparse.ArgumentParser(description='Шаблоны для травления 1:1 (негатив/позитив, с зеркалом и без); '
                                            'окно печати с раскладкой — tools/etch_window.py')
    p.add_argument('board', nargs='?', default=os.path.join(PRJ, 'scaner_v1.kicad_pcb'))
    p.add_argument('--layer', default='B.Cu', help='медь для травления (B.Cu или F.Cu)')
    p.add_argument('--copies', type=int, default=0, help='копий платы на листе (0 = сколько влезет)')
    p.add_argument('--out', help='папка (по умолчанию etch рядом с платой)')
    p.add_argument('--svg', action='store_true', help='ещё и SVG рядом с PDF (посмотреть в браузере)')
    p.add_argument('--open', action='store_true', help='открыть главный PDF')
    a = p.parse_args()
    board = pcbnew.LoadBoard(a.board)
    layer = {'B.Cu': pcbnew.B_Cu, 'F.Cu': pcbnew.F_Cu}[a.layer]
    out_dir, files, n = make_all(board, layer, a.copies, a.out, a.svg)
    print('копий на листе:', n)
    for f in files:
        print('ok', f)
    if a.open:
        os.startfile(files[0])


if __name__ == '__main__':
    sys.exit(main())
