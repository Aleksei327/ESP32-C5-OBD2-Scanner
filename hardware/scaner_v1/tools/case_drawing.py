"""Чертежи корпуса OBD2 для tools/gen_case.py: виды и разрезы снимаются с 3D-модели (TechDraw.projectEx),
размеры проставлены по параметрам gen_case.py. Пишет case/case_drawing.pdf и case_sheet1..2.png.
Лист A3, координаты листа — мм от левого нижнего угла.
"""
import datetime
import math
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt                        # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages   # noqa: E402
from matplotlib.patches import PathPatch, Rectangle   # noqa: E402
from matplotlib.path import Path                       # noqa: E402

import Part        # noqa: E402
import TechDraw    # noqa: E402
from FreeCAD import Matrix, Vector as V   # noqa: E402

MM = 72 / 25.4              # пунктов в миллиметре
THICK, THIN = 0.5 * MM, 0.18 * MM
FS = 8.5                    # кегль размеров
SHEET_W, SHEET_H = 420, 297
plt.rcParams['hatch.linewidth'] = 0.35
plt.rcParams['font.family'] = 'DejaVu Sans'
HATCH = {'base': '////', 'lid': '\\\\\\\\', 'plug': 'xxx', 'pins': ''}


def num(v):
    s = f'{v:.2f}'.rstrip('0').rstrip('.')
    return s.replace('.', ',')


class View:
    """Вид или разрез. r, u — куда смотрят ось X и ось Y листа в координатах модели; зритель — по r × u.
    cut — положение секущей плоскости вдоль r × u (оставляется то, что за ней)."""

    def __init__(self, ax, parts, r, u, ox, oy, s, cut=None, hidden=False, clip=None):
        self.ax, self.ox, self.oy, self.s = ax, ox, oy, s
        r, u = V(*r), V(*u)
        v = r.cross(u)
        self.m = Matrix(r.x, r.y, r.z, 0, u.x, u.y, u.z, 0, v.x, v.y, v.z, 0, 0, 0, 0, 1)
        self.clip = None
        if clip:
            (x0, y0), (x1, y1) = self.P(clip[0], clip[1]), self.P(clip[2], clip[3])
            self.clip = Rectangle((x0, y0), x1 - x0, y1 - y0, transform=ax.transData)
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=THIN, ls=(0, (6, 2))))
        shapes = {}
        for name, shape in parts.items():
            t = shape.copy()
            t.transformShape(self.m)
            if cut is not None:
                t = t.common(Part.makeBox(1000, 1000, 500, V(-500, -500, cut - 500)))
                for f in self._section(t, cut):
                    self._hatch(f, HATCH[name])
            shapes[name] = t
        res = TechDraw.projectEx(Part.makeCompound(list(shapes.values())), V(0, 0, 1))
        for i in (0, 3):
            self._edges(res[i], THICK, '-')
        if hidden:
            for i in (5, 8):
                self._edges(res[i], THIN, (0, (4, 2)))

    def P(self, x, y):
        return self.ox + self.s * x, self.oy + self.s * y

    def _add(self, art):
        if self.clip is not None:
            art.set_clip_path(self.clip)
        return art

    def _edges(self, comp, lw, ls):
        if comp is None or comp.isNull():
            return
        for e in comp.Edges:
            pts = e.discretize(Deflection=0.005)
            self._add(self.ax.plot([self.P(p.x, p.y)[0] for p in pts], [self.P(p.x, p.y)[1] for p in pts],
                                   color='k', lw=lw, ls=ls, solid_capstyle='round')[0])

    def _section(self, shape, cut):
        """Грани, лежащие в секущей плоскости (после обрезки по ней) — это и есть сечение."""
        if shape.isNull():
            return []
        return [f for f in shape.Faces
                if abs(f.BoundBox.ZMin - cut) < 1e-6 and abs(f.BoundBox.ZMax - cut) < 1e-6]

    def _hatch(self, face, hatch):
        verts, codes = [], []
        for k, w in enumerate(face.Wires):
            pts = [self.P(p.x, p.y) for p in w.discretize(Deflection=0.005)]
            area = sum(pts[i][0] * pts[i - 1][1] - pts[i - 1][0] * pts[i][1] for i in range(len(pts)))
            outer = w.isSame(face.OuterWire)
            if (area < 0) == outer:      # внешний контур — против часовой, дырки — по часовой
                pts.reverse()
            verts += pts + [pts[0]]
            codes += [Path.MOVETO] + [Path.LINETO] * (len(pts) - 1) + [Path.CLOSEPOLY]
        fill = '#d8d8d8' if not hatch else 'none'
        self._add(self.ax.add_patch(PathPatch(Path(verts, codes), facecolor=fill, edgecolor='k',
                                              lw=0, hatch=hatch or None)))

    # ---------- оформление ----------
    def text(self, x, y, s, size=FS, rot=0, ha='center', va='center', paper=False, **kw):
        if not paper:
            x, y = self.P(x, y)
        return self.ax.text(x, y, s, fontsize=size, rotation=rot, ha=ha, va=va, **kw)

    def dim(self, p1, p2, at, text=None, vertical=False, side=None):
        """Размер между точками p1, p2 (координаты вида); at — где линия размера (y' или x')."""
        ax, k = self.ax, 0 if not vertical else 1
        a, b = sorted([p1, p2], key=lambda p: p[k])
        val = abs(b[k] - a[k])
        label = text if text is not None else num(val)
        for p in (a, b):        # выносные линии
            q = (p[0], at) if not vertical else (at, p[1])
            (x0, y0), (x1, y1) = self.P(*p), self.P(*q)
            d = math.hypot(x1 - x0, y1 - y0)
            if d > 0.1:
                ux, uy = (x1 - x0) / d, (y1 - y0) / d
                ax.plot([x0 + ux * 0.8, x1 + ux * 1.5], [y0 + uy * 0.8, y1 + uy * 1.5], color='k', lw=THIN)
        A = self.P(a[0], at) if not vertical else self.P(at, a[1])
        B = self.P(b[0], at) if not vertical else self.P(at, b[1])
        span = math.hypot(B[0] - A[0], B[1] - A[1])
        ar = dict(arrowstyle='-|>', lw=THIN, color='k', shrinkA=0, shrinkB=0, mutation_scale=7)
        tw = 1.75 * len(label)
        if span >= 7:
            ax.annotate('', xy=A, xytext=((A[0] + B[0]) / 2, (A[1] + B[1]) / 2), arrowprops=ar)
            ax.annotate('', xy=B, xytext=((A[0] + B[0]) / 2, (A[1] + B[1]) / 2), arrowprops=ar)
        else:
            ux, uy = (B[0] - A[0]) / max(span, 1e-6), (B[1] - A[1]) / max(span, 1e-6)
            ax.annotate('', xy=A, xytext=(A[0] - ux * 4, A[1] - uy * 4), arrowprops=ar)
            ax.annotate('', xy=B, xytext=(B[0] + ux * 4, B[1] + uy * 4), arrowprops=ar)
            ax.plot([A[0], B[0]], [A[1], B[1]], color='k', lw=THIN)
        inside = span >= tw + 2
        if side is None:
            side = 'mid' if inside else 'after'
        if not vertical:
            y = A[1] + 1.1
            x = {'mid': (A[0] + B[0]) / 2, 'after': B[0] + 2 + tw / 2, 'before': A[0] - 2 - tw / 2}[side]
            if side != 'mid':
                ax.plot([B[0], B[0] + 4 + tw] if side == 'after' else [A[0] - 4 - tw, A[0]], [A[1], A[1]],
                        color='k', lw=THIN)
            ax.text(x, y, label, fontsize=FS, ha='center', va='bottom')
        else:
            x = A[0] - 1.1
            y = {'mid': (A[1] + B[1]) / 2, 'after': B[1] + 2 + tw / 2, 'before': A[1] - 2 - tw / 2}[side]
            if side != 'mid':
                ax.plot([A[0], A[0]], [B[1], B[1] + 4 + tw] if side == 'after' else [A[1] - 4 - tw, A[1]],
                        color='k', lw=THIN)
            ax.text(x, y, label, fontsize=FS, ha='right', va='center', rotation=90)

    def note(self, p, dx, dy, text, arrow=True):
        """Выноска: от точки вида p на (dx, dy) мм листа, полка с текстом."""
        x0, y0 = self.P(*p)
        x1, y1 = x0 + dx, y0 + dy
        lines = text.split('\n')
        tw = 1.75 * max(len(t) for t in lines)
        x2 = x1 + tw if dx >= 0 else x1 - tw
        if arrow:
            self.ax.annotate('', xy=(x0, y0), xytext=(x1, y1),
                             arrowprops=dict(arrowstyle='-|>', lw=THIN, color='k', shrinkA=0, shrinkB=0,
                                             mutation_scale=7))
        else:
            self.ax.plot([x0, x1], [y0, y1], color='k', lw=THIN)
        self.ax.plot([x1, x2], [y1, y1], color='k', lw=THIN)
        self.ax.text((x1 + x2) / 2, y1 + 0.8, text, fontsize=FS, ha='center', va='bottom', linespacing=1.2)

    def center(self, x, y, size=6.0):
        for dx, dy in ((size, 0), (0, size)):
            (x0, y0), (x1, y1) = self.P(x - dx, y - dy), self.P(x + dx, y + dy)
            self._add(self.ax.plot([x0, x1], [y0, y1], color='k', lw=THIN, ls=(0, (10, 2, 1.5, 2)))[0])

    def axis(self, p1, p2):
        (x0, y0), (x1, y1) = self.P(*p1), self.P(*p2)
        self._add(self.ax.plot([x0, x1], [y0, y1], color='k', lw=THIN, ls=(0, (10, 2, 1.5, 2)))[0])

    def cutline(self, p1, p2, look, label):
        """След секущей плоскости: штрихи на концах, стрелки — куда смотрим (look — вектор в осях вида)."""
        for p in (p1, p2):
            x, y = self.P(*p)
            dx, dy = (p2[0] - p1[0]), (p2[1] - p1[1])
            d = math.hypot(dx, dy)
            sgn = 1 if p is p1 else -1
            self.ax.plot([x, x + sgn * dx / d * 6], [y, y + sgn * dy / d * 6], color='k', lw=THICK * 1.4)
            self.ax.annotate('', xy=(x + look[0] * 7, y + look[1] * 7), xytext=(x, y),
                             arrowprops=dict(arrowstyle='-|>', lw=THICK, color='k', shrinkA=0, shrinkB=0,
                                             mutation_scale=10))
            self.ax.text(x + look[0] * 9 - sgn * dx / d * 1.5, y + look[1] * 9 - sgn * dy / d * 1.5, label,
                         fontsize=12, ha='center', va='center', weight='bold')


def sheet(title, scale, no, total):
    fig = plt.figure(figsize=(SHEET_W / 25.4, SHEET_H / 25.4))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, SHEET_W)
    ax.set_ylim(0, SHEET_H)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.add_patch(Rectangle((10, 10), SHEET_W - 20, SHEET_H - 20, fill=False, lw=THICK))
    x0, y0, w, h = SHEET_W - 10 - 150, 10, 150, 30
    ax.add_patch(Rectangle((x0, y0), w, h, fill=False, lw=THICK))
    for y in (y0 + 10, y0 + 20):
        ax.plot([x0, x0 + w], [y, y], color='k', lw=THIN)
    ax.plot([x0 + 110, x0 + 110], [y0, y0 + 20], color='k', lw=THIN)
    ax.text(x0 + 3, y0 + 25, 'Корпус OBD2 72×46×26 (AliExpress) — ' + title, fontsize=10.5, va='center',
            weight='bold')
    ax.text(x0 + 3, y0 + 15, 'Размеры в мм, по замерам линейкой (±0,5). * — не мерили, принято.',
            fontsize=8, va='center')
    ax.text(x0 + 3, y0 + 5, f'scaner_v1 · tools/gen_case.py · {datetime.date.today():%d.%m.%Y}', fontsize=8,
            va='center')
    ax.text(x0 + 130, y0 + 15, f'М {scale}', fontsize=9, ha='center', va='center')
    ax.text(x0 + 130, y0 + 5, f'Лист {no} из {total}', fontsize=9, ha='center', va='center')
    return fig, ax


def heading(ax, x, y, s):
    ax.text(x, y, s, fontsize=11, ha='left', va='bottom', weight='bold')


def draw(g, parts):
    os.makedirs(g.OUT, exist_ok=True)
    all4 = {k: parts[k] for k in ('base', 'lid', 'plug', 'pins')}
    no_lid = {k: parts[k] for k in ('base', 'plug', 'pins')}
    px, py = g.POST_DX / 2, g.POST_Y
    py2 = g.POST_Y + g.POST_DY
    figs = []

    # ===== лист 1: основание в плане, разрезы А–А и Б–Б =====
    fig, ax = sheet('основание и штекер', '2:1', 1, 2)
    pv = View(ax, no_lid, (1, 0, 0), (0, 1, 0), 102, 54, 2)
    heading(ax, 30, 252, 'Основание со штекером, вид сверху (крышка снята)')
    for x, y in g.POSTS:
        pv.center(x, y)
    pv.axis((0, g.Y_BACK - 4), (0, g.Y_FRONT + g.PLUG_OUT + 4))
    pv.dim((-g.W_IN / 2, 0), (g.W_IN / 2, 0), -9)
    pv.dim((-g.W / 2, g.Y_BACK), (g.W / 2, g.Y_BACK), -17, text=f'{num(g.W)} (по рифлению {num(g.W_RIB)})')
    pv.dim((-px, py), (px, py), 26, side='mid')
    pv.dim((-g.W / 2, g.Y_BACK), (-g.W / 2, g.Y_FRONT), -g.W / 2 - 16, vertical=True)
    pv.dim((-g.W_IN / 2, 0), (-g.W_IN / 2, g.L_IN), -g.W / 2 - 8, vertical=True)
    xr = g.W / 2 + 9
    pv.dim((px, 0), (px, py), xr, vertical=True)
    pv.dim((px, py), (px, py2), xr, vertical=True)
    pv.dim((px, py2), (6, g.Y_PINS), xr, vertical=True)
    pv.dim((6, g.Y_PINS), (6, g.Y_PLUG), xr, vertical=True, side='mid', text='4')
    pv.dim((6, g.Y_PLUG), (g.W / 2, g.Y_FRONT), xr, vertical=True, side='after', text='4')
    pv.dim((g.WIN_W / 2, g.Y_FRONT), (g.W / 2 - 4, g.Y_FRONT + g.PLUG_OUT), xr, vertical=True, text='15')
    pv.dim((g.W_IN / 2, 0), (6, g.Y_PINS), xr + 9, vertical=True, text=num(g.Y_PINS))
    pv.dim((-g.WIN_W / 2, g.L_IN), (g.WIN_W / 2, g.L_IN), g.Y_FRONT + g.PLUG_OUT + 6, text='окно 34')
    pv.note((-px + 2.83, py + 2.83), 16, 30, '4 стойки Ø8, высота 17\nсверху отв. Ø5,5')
    pv.note((-g.W / 2 + g.LEG / 2, g.Y_FRONT - g.LEG / 2), -10, 12, 'фаски 45°, ширина 5,\nсм. примечание 3')
    pv.note((-(3.5 * g.PIN_PITCH), g.Y_PINS), 8, -26, '16 контактов 1,4×0,8\nшаг ≈3,7*')
    pv.cutline((px, g.Y_BACK - 2.5), (px, g.Y_FRONT + 3), (-1, 0), 'А')
    pv.cutline((-g.W / 2 - 1.5, py2), (g.W / 2 + 1.5, py2), (0, 1), 'Б')

    heading(ax, 200, 274, 'Разрез А–А (в сборе, через стойки)')
    sa = View(ax, all4, (0, 1, 0), (0, 0, 1), 212, 224, 2, cut=px)
    sa.dim((g.Y_BACK, g.Z_BOT), (g.Y_BACK, g.Z_TOP), g.Y_BACK - 14, vertical=True)
    sa.dim((0, 0), (0, g.H_IN), g.Y_BACK - 7, vertical=True)
    sa.dim((py, 0), (py, g.POST_H), py + 8, vertical=True)
    sa.dim((py2, g.H_IN - g.LPOST_H), (py2, g.H_IN), py2 - 7, vertical=True, side='before')
    sa.dim((g.Y_FRONT + g.PLUG_OUT, g.WIN_Z), (g.Y_FRONT + g.PLUG_OUT, g.WIN_Z + g.WIN_H),
           g.Y_FRONT + g.PLUG_OUT + 6, vertical=True)
    sa.dim((g.Y_FRONT, g.Z_BOT), (g.Y_FRONT + g.PLUG_OUT, g.WIN_Z), g.Z_BOT - 7)
    sa.dim((g.Y_PLUG, g.WIN_Z), (g.Y_FRONT, g.Z_BOT), g.Z_BOT - 7, side='before')
    sa.note((g.Y_BACK, 12.9 - g.T_FLOOR), -10, 9, 'шов')
    sa.note((g.Y_BACK + 0.4, g.Z_BOT + 0.6), -9, -10, 'дно 2,1*')
    sa.note((g.Y_PINS, g.Z_WIN_MID - g.PIN_ROWS / 2), -20, -30, 'контакты: 2 ряда*')

    heading(ax, 200, 186, 'Разрез Б–Б (в сборе, смотрим на штекер изнутри)')
    sb = View(ax, all4, (1, 0, 0), (0, 0, 1), 256, 122, 2, cut=-py2)
    sb.dim((-g.W_IN / 2, 0), (g.W_IN / 2, 0), g.Z_BOT - 7)
    sb.dim((-g.W / 2, g.Z_BOT), (g.W / 2, g.Z_BOT), g.Z_BOT - 14, text=f'{num(g.W)} (по рифлению {num(g.W_RIB)})')
    sb.dim((-g.WIN_W / 2, g.WIN_Z + g.WIN_H), (g.WIN_W / 2, g.WIN_Z + g.WIN_H), g.Z_TOP + 5)
    sb.dim((-g.W / 2, g.WIN_Z), (-g.W / 2, g.WIN_Z + g.WIN_H), -g.W / 2 - 7, vertical=True)
    sb.dim((-g.W / 2, g.Z_BOT), (-g.W / 2, g.WIN_Z), -g.W / 2 - 7, vertical=True, side='before',
           text=num(g.WIN_Z + g.T_FLOOR) + '*')
    sb.dim((g.W / 2, 0), (g.W / 2, g.PINS[8][1]), g.W / 2 + 7, vertical=True, text=num(g.PINS[8][1]) + '*')
    sb.dim((g.W / 2, g.PINS[8][1]), (g.W / 2, g.PINS[0][1]), g.W / 2 + 7, vertical=True, side='after',
           text=num(g.PIN_ROWS) + '*')
    for x, _ in g.POSTS[2:]:
        sb.axis((x, g.Z_BOT - 3), (x, g.Z_TOP + 3))

    notes = ['Примечания',
             '1. Основание — половинка со стойками Ø8, винты',
             '    вкручиваются снизу; крышка — со стойками Ø5,2.',
             '2. * — не мерили, принято: дно и потолок по 2,1;',
             '    окно по середине высоты; контакты — шаг 3,7',
             '    (по фото), ряды через 4,5; форма штекера снаружи.',
             '3. Фаски 45° шириной 5 — на 4 рёбрах передней грани',
             '    и на 4 продольных; рёбра задней грани острые.',
             '    Изнутри фаски повторяют наружные (принято).',
             '    На боках рифление: по нему 46, корпус 45.',
             '4. Штекер съёмный, встаёт любой стороной (на 180°).',
             '5. Стойки крышки заходят в стойки основания на 1,4.',
             '6. Вид сверху: Y от внутренней грани задней стенки.']
    for i, t in enumerate(notes):
        ax.text(318, 172 - 5.2 * i, t, fontsize=8.5, weight='bold' if i == 0 else 'normal', va='top')
    figs.append(fig)

    # ===== лист 2: вид спереди, крышка изнутри, узлы =====
    fig, ax = sheet('крышка, вид спереди, узлы', '2:1, 4:1, 8:1', 2, 2)
    heading(ax, 30, 262, 'Вид спереди (на штекер)')
    fv = View(ax, all4, (-1, 0, 0), (0, 0, 1), 85, 202, 2, hidden=False)
    fv.dim((-g.W / 2, g.Z_BOT), (g.W / 2, g.Z_BOT), g.Z_BOT - 8, text=f'{num(g.W)} (по рифлению {num(g.W_RIB)})')
    fv.dim((-g.W / 2, g.Z_BOT), (-g.W / 2, g.Z_TOP), -g.W / 2 - 8, vertical=True)
    fv.dim((g.W / 2, g.Z_BOT), (g.W / 2, 12.9 - g.T_FLOOR), g.W / 2 + 7, vertical=True, text='12,9*')
    fv.dim((g.W / 2, 12.9 - g.T_FLOOR), (g.W / 2, g.Z_TOP), g.W / 2 + 7, vertical=True, text='13,1*')
    fv.note((g.W / 2 - g.LEG / 2, g.Z_TOP - g.LEG / 2), 10, 8, 'фаски 45°, ширина 5')

    heading(ax, 30, 172, 'Крышка изнутри (перевёрнута через длинную сторону)')
    lv = View(ax, {'lid': parts['lid']}, (-1, 0, 0), (0, 1, 0), 85, 22, 2)
    for x, y in g.POSTS:
        lv.center(x, y)
    lv.dim((-px, py), (px, py), py - 9, side='mid')
    lv.dim((px, py), (px, py2), g.W / 2 + 7, vertical=True)
    lv.dim((px, 0), (px, py), g.W / 2 + 7, vertical=True)
    lv.dim((g.W / 2, g.Y_BACK), (g.W / 2, g.Y_FRONT), -g.W / 2 - 8, vertical=True)
    lv.note((-px + 1.84, py2 + 1.84), 14, 16, '4 стойки Ø5,2, высота 6,2\nотв. Ø1,1 глухое')
    lv.note((0, g.L_IN + g.T_END / 2), 52, -4, 'окно под штекер')

    heading(ax, 175, 262, 'Стойка в сборе (разрез А–А), 4:1')
    dv = View(ax, all4, (0, 1, 0), (0, 0, 1), 200 - 4 * (py - 7), 140 + 4 * 2.1, 4, cut=px,
              clip=(py - 7, g.Z_BOT - 0.01, py + 7, g.Z_TOP + 0.01))
    dv.axis((py, g.Z_BOT - 3), (py, g.Z_TOP + 3))
    dv.dim((py - g.POST_D / 2, 0), (py + g.POST_D / 2, 0), g.Z_BOT - 11, text='Ø8')
    dv.dim((py - g.CB_D / 2, g.POST_H), (py + g.CB_D / 2, g.POST_H), g.POST_H + 1.6, text='Ø5,5', side='after')
    dv.dim((py - g.LPOST_D / 2, g.H_IN), (py + g.LPOST_D / 2, g.H_IN), g.H_IN - 2.2, text='Ø5,2', side='before')
    dv.dim((py - g.HEAD_D / 2, g.Z_BOT), (py + g.HEAD_D / 2, g.Z_BOT), g.Z_BOT - 5, text='Ø4,4')
    dv.dim((py - g.MID_D / 2, 11), (py + g.MID_D / 2, 11), 11.6, text='Ø2,3', side='after')
    xl = py - 9
    dv.dim((py - 4, g.Z_BOT), (py - 4, g.Z_BOT + g.HEAD_DEPTH), xl, vertical=True)
    dv.dim((py - 4, g.POST_H - g.CB_DEPTH), (py - 4, g.POST_H), xl, vertical=True)
    dv.dim((py - 4, 0), (py - 4, g.POST_H), xl - 7, vertical=True)
    xr = py + 9
    dv.dim((py + 3, g.H_IN - g.LPOST_H), (py + 3, g.H_IN), xr, vertical=True)
    dv.dim((py + 3, g.H_IN - g.LPOST_H), (py + 3, g.POST_H), xr + 7, vertical=True, text='1,4', side='before')
    dv.note((py, g.H_IN - g.LPOST_H + 2), 26, 14, 'отв. Ø1,1 глухое,\nглубина ≈4*')

    heading(ax, 290, 262, 'Стык половинок (разрез Б–Б), 8:1')
    xs, xw = g.W_IN / 2, g.W / 2
    zv = View(ax, all4, (1, 0, 0), (0, 0, 1), 318 - 8 * 20.0, 205 - 8 * 9.3, 8, cut=-py2,
              clip=(20.0, 9.3, xw + 0.01, 13.1))
    zv.dim((xs, 9.3), (xs + g.T_SIDE / 2, 9.3), 8.6, text=num(g.T_SIDE / 2) + '*', side='before')
    zv.dim((xs + g.T_SIDE / 2, 9.3), (xw, 9.3), 8.6, text=num(g.T_SIDE / 2) + '*', side='after')
    zv.dim((xw, g.BASE_OUT), (xw, g.BASE_IN), xw + 1.2, vertical=True, text='0,8')
    zv.text(19.7, 12.4, 'крышка', ha='right')
    zv.text(19.7, 10.0, 'основание', ha='right')
    ax.text(290, 185, 'от дна основания: наружная половина стенки 10,8,\n'
                      'внутренняя 11,6; от потолка крышки: 11,0 и 10,2.\n'
                      'Внутри в сборе 11,6 + 10,2 = 21,8.', fontsize=8.5, va='top', linespacing=1.4)
    figs.append(fig)

    pdf = os.path.join(g.OUT, 'case_drawing.pdf')
    with PdfPages(pdf) as pp:
        for i, f in enumerate(figs, 1):
            pp.savefig(f)
            f.savefig(os.path.join(g.OUT, f'case_sheet{i}.png'), dpi=150)
            plt.close(f)
    print('ok', pdf)
