#!/usr/bin/env python3
"""Корпус OBD2 72 x 46 x 26 с Алиэкспресса: 3D, чертежи и слой в KiCad. Запускать питоном FreeCAD:

  "C:\\Program Files\\FreeCAD 1.0\\bin\\python.exe" tools/gen_case.py [--no-drawings]

Пишет:
  case/case_base.step, case_lid.step, obd_plug.step, case_assembly.step, case.FCStd — модель;
  case/case_drawing.pdf (+ case_sheet1..2.png) — чертежи с размерами;
  scaner.3dshapes/Case_OBD2_base.wrl, Case_OBD2_lid.wrl — модели для 3D-просмотра KiCad;
  scaner.pretty/Case_OBD2_72x46.kicad_mod — посадочное место «корпус»: внутренний контур, стойки,
  контакты штекера (слои Eco1/Eco2/Dwgs), 3D-модели корпуса. На плату его ставит gen_pcb.py.

Оси модели: X — поперёк (0 посередине), Y — вдоль, 0 на внутренней грани задней стенки,
штекер в сторону +Y; Z — вверх, 0 на дне основания изнутри. Основание — половинка со стойками Ø8
(винты вкручиваются снизу), крышка — со стойками Ø5,2.
"""
import math
import os
import sys
import uuid

sys.path.append(os.path.dirname(sys.executable))   # FreeCAD.pyd лежит рядом с его python.exe
import FreeCAD as App   # noqa: E402
import Part
import TechDraw
from FreeCAD import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
OUT = os.path.join(PRJ, 'case')
SHAPES = os.path.join(PRJ, 'scaner.3dshapes')
PRETTY = os.path.join(PRJ, 'scaner.pretty')
sys.path.insert(0, HERE)
from gen_3d import K, mat   # noqa: E402  (единицы VRML и материалы — те же, что у деталей)

# ---------- измерено ----------
L, W, H = 72.0, 45.0, 26.0           # снаружи: длина без штекера, ширина, высота в сборе
W_RIB = 46.0                         # ширина по рифлению на боках (рифление не рисуем)
CHAMF = 5.0                          # фаски 45° шириной 5: рёбра передней грани и 4 продольных, задние острые
W_IN = 41.0                          # ширина внутри
T_SIDE = 2.0                         # боковые стенки
T_END = 1.9                          # передняя и задняя стенки
BASE_IN, BASE_OUT = 11.6, 10.8       # основание: внутренняя и наружная половина стенки, от дна
LID_IN, LID_OUT = 10.2, 11.0         # крышка: то же от потолка (в сборе внутри 21,8)
WIN_W, WIN_H = 34.0, 14.0            # окно под штекер
PLUG_OUT, PLUG_IN = 15.0, 4.0        # штекер торчит от передней грани; задняя грань штекера внутри
PIN_L, PIN_W, PIN_T = 4.0, 1.4, 0.8  # хвосты контактов от задней грани штекера
POST_D, POST_H = 8.0, 17.0           # стойки основания, высота от дна
POST_Y = 11.4 + POST_D / 2           # центр задней пары от задней стенки
POST_DY = 27.6 + POST_D              # между центрами вдоль
POST_DX = 22.8 + POST_D              # между центрами поперёк
CB_D, CB_DEPTH = 5.5, 3.6            # отверстие стойки сверху
MID_D = 2.3                          # между ними
HEAD_D, HEAD_DEPTH = 4.4, 13.0       # снизу, снаружи корпуса (под головку винта)
LPOST_D, LPOST_H = 5.2, 6.2          # стойки крышки
LPOST_HOLE = 1.1                     # глухое отверстие под винт

# ---------- не мерили, принято (на чертежах со звёздочкой) ----------
H_IN = BASE_IN + LID_IN              # 21,8
T_FLOOR = T_CEIL = (H - H_IN) / 2    # 2,1 — дно и потолок поровну
WIN_Z = H / 2 - T_FLOOR - WIN_H / 2  # окно посередине высоты корпуса: низ окна от дна
PIN_PITCH = 3.7                      # шаг контактов вдоль ряда (по фото)
PIN_ROWS = 4.5                       # между рядами контактов по высоте
LPOST_HOLE_DEPTH = 4.0
PLUG_BODY_W, PLUG_BODY_H = 31.0, 12.0   # наружная часть штекера — условно

# ---------- плата в корпусе (для 3D в KiCad) ----------
BOARD_Z = 5.0                        # низ платы над дном: снизу дроссель и LM2596 (до 4,5)
PCB_T = 1.6

L_IN = L - 2 * T_END                 # 68,2
Y_BACK, Y_FRONT = -T_END, L_IN + T_END
Z_BOT, Z_TOP = -T_FLOOR, H_IN + T_CEIL
Y_MID = L_IN / 2                     # начало координат посадочного места — середина полости
LEG = CHAMF / math.sqrt(2)           # катет фаски
T_AVG = (T_SIDE + T_END + T_FLOOR) / 3
CH_IN = LEG - (2 - math.sqrt(2)) * T_AVG   # фаски изнутри: стенка на фаске той же толщины (принято)
Y_PLUG = Y_FRONT - PLUG_IN           # задняя грань штекера
Y_PINS = Y_PLUG - PIN_L              # концы контактов (намерено 62 от задней стенки)
Z_WIN_MID = WIN_Z + WIN_H / 2
POSTS = [(sx * POST_DX / 2, y) for y in (POST_Y, POST_Y + POST_DY) for sx in (-1, 1)]
PINS = [((i - 3.5) * PIN_PITCH, Z_WIN_MID + dz) for dz in (PIN_ROWS / 2, -PIN_ROWS / 2) for i in range(8)]


def plan(xh, y0, y1, ch):
    """Контур в плане: прямоугольник ±xh по X, y0..y1 по Y, передние углы срезаны катетом ch."""
    return [(-xh, y0), (xh, y0), (xh, y1 - ch), (xh - ch, y1), (-xh + ch, y1), (-xh, y1 - ch)]


def prism(pts, z0, z1):
    w = Part.makePolygon([V(x, y, z0) for x, y in pts] + [V(pts[0][0], pts[0][1], z0)])
    return Part.Face(w).extrude(V(0, 0, z1 - z0))


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(x, y, d, z0, z1):
    return Part.makeCylinder(d / 2, z1 - z0, V(x, y, z0), V(0, 0, 1))


# контуры в плане на высоте шва (там на боках фасок нет): снаружи, изнутри, середина стенки
OUTER = plan(W / 2, Y_BACK, Y_FRONT, LEG)
INNER = plan(W_IN / 2, 0, L_IN, CH_IN)
MIDW = plan(W_IN / 2 + T_SIDE / 2, -T_END / 2, L_IN + T_END / 2, (LEG + CH_IN) / 2)


def chamfered(x0, x1, y0, y1, z0, z1, leg):
    """Коробка с фасками на рёбрах передней грани (y1) и на 4 продольных рёбрах; рёбра задней (y0) острые."""
    b = box(x0, x1, y0, y1, z0, z1)
    edges = [e for e in b.Edges if not all(abs(v.Point.y - y0) < 1e-6 for v in e.Vertexes)]
    return b.makeChamfer(leg, edges)


def build():
    shell = chamfered(-W / 2, W / 2, Y_BACK, Y_FRONT, Z_BOT, Z_TOP, LEG).cut(
        chamfered(-W_IN / 2, W_IN / 2, 0, L_IN, 0, H_IN, CH_IN))
    shell = shell.cut(box(-WIN_W / 2, WIN_W / 2, L_IN - 1, Y_FRONT + 1, WIN_Z, WIN_Z + WIN_H))
    # шов: у основания внутренняя половина стенки выше наружной на 0,8, у крышки наоборот
    region = box(-W, W, Y_BACK - 1, Y_FRONT + 1, Z_BOT - 1, BASE_OUT).fuse(prism(MIDW, BASE_OUT, BASE_IN))
    base, lid = shell.common(region), shell.cut(region)

    for x, y in POSTS:
        base = base.fuse(cyl(x, y, POST_D, Z_BOT, POST_H))
    for x, y in POSTS:
        base = base.cut(cyl(x, y, CB_D, POST_H - CB_DEPTH, POST_H + 1))
        base = base.cut(cyl(x, y, MID_D, Z_BOT - 1, POST_H))
        base = base.cut(cyl(x, y, HEAD_D, Z_BOT - 1, Z_BOT + HEAD_DEPTH))
        lid = lid.fuse(cyl(x, y, LPOST_D, H_IN - LPOST_H, H_IN + 0.5))
        lid = lid.cut(cyl(x, y, LPOST_HOLE, H_IN - LPOST_H - 1, H_IN - LPOST_H + LPOST_HOLE_DEPTH))

    # штекер: вкладыш в окне (до задней грани штекера) и наружная часть с защёлкой сверху
    zc = Z_WIN_MID
    plug = box(-WIN_W / 2, WIN_W / 2, Y_PLUG, Y_FRONT, WIN_Z, WIN_Z + WIN_H)
    bw, bh, c = PLUG_BODY_W / 2, PLUG_BODY_H / 2, 2.5
    face = [(-bw, zc + bh), (bw, zc + bh), (bw, zc - bh + c), (bw - c, zc - bh), (-bw + c, zc - bh), (-bw, zc - bh + c)]
    w = Part.makePolygon([V(x, Y_FRONT, z) for x, z in face] + [V(face[0][0], Y_FRONT, face[0][1])])
    plug = plug.fuse(Part.Face(w).extrude(V(0, PLUG_OUT, 0)))
    plug = plug.fuse(box(-4.5, 4.5, Y_FRONT + 3, Y_FRONT + PLUG_OUT, zc + bh, zc + bh + 1.5))
    pins = Part.makeCompound([box(x - PIN_W / 2, x + PIN_W / 2, Y_PINS, Y_PLUG, z - PIN_T / 2, z + PIN_T / 2)
                              for x, z in PINS])
    return {'base': base.removeSplitter(), 'lid': lid.removeSplitter(), 'plug': plug.removeSplitter(), 'pins': pins}


# ---------- модель: STEP, FCStd, VRML ----------
def write_models(parts):
    os.makedirs(OUT, exist_ok=True)
    plug = Part.makeCompound([parts['plug'], parts['pins']])
    parts['base'].exportStep(os.path.join(OUT, 'case_base.step'))
    parts['lid'].exportStep(os.path.join(OUT, 'case_lid.step'))
    plug.exportStep(os.path.join(OUT, 'obd_plug.step'))
    Part.makeCompound([parts['base'], parts['lid'], plug]).exportStep(os.path.join(OUT, 'case_assembly.step'))
    doc = App.newDocument('case')
    for name, shape in (('Base', parts['base']), ('Lid', parts['lid']), ('Plug', plug)):
        doc.addObject('Part::Feature', name).Shape = shape
    fcstd = os.path.join(OUT, 'case.FCStd')
    if os.path.exists(fcstd):
        os.remove(fcstd)   # иначе FreeCAD оставит рядом .FCBak
    doc.saveAs(fcstd)
    App.closeDocument(doc.Name)

    def shape_wrl(shape, m):
        pts, tris = shape.tessellate(0.05)
        ps = ',\n'.join('%.4f %.4f %.4f' % (p.x / K, (p.y - Y_MID) / K, p.z / K) for p in pts)
        fs = ',\n'.join('%d, %d, %d, -1' % t for t in tris)
        return (f'Shape {{\n  {mat(m)}\n  geometry IndexedFaceSet {{ solid FALSE creaseAngle 0.6\n'
                f'    coord Coordinate {{ point [\n{ps}\n] }}\n    coordIndex [\n{fs}\n]\n  }}\n}}\n')

    for name, items in (('Case_OBD2_base.wrl', [(parts['base'], 'case'), (parts['plug'], 'black'),
                                                 (parts['pins'], 'tin')]),
                        ('Case_OBD2_lid.wrl', [(parts['lid'], 'case')])):
        with open(os.path.join(SHAPES, name), 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('#VRML V2.0 utf8\n# scaner_v1, tools/gen_case.py\n\n')
            fh.write(''.join(shape_wrl(s, m) for s, m in items))
        print('ok', name)


# ---------- посадочное место для KiCad ----------
def write_footprint():
    n = [0]

    def uid():
        n[0] += 1
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f'scaner_v1/case/{n[0]}'))

    def p(x, y):   # модель -> посадочное место (Y вниз, штекер сверху)
        return f'{x:.3f} {Y_MID - y:.3f}'

    def poly(pts, layer, width, dash=False):
        xy = ' '.join(f'(xy {p(x, y)})' for x, y in pts)
        st = 'dash' if dash else 'solid'
        return (f'  (fp_poly (pts {xy}) (stroke (width {width}) (type {st})) (fill no) (layer "{layer}") '
                f'(uuid "{uid()}"))\n')

    def circle(x, y, d, layer, width):
        return (f'  (fp_circle (center {p(x, y)}) (end {p(x + d / 2, y)}) (stroke (width {width}) (type solid)) '
                f'(fill no) (layer "{layer}") (uuid "{uid()}"))\n')

    def line(x0, y0, x1, y1, layer, width, kind='solid'):
        return (f'  (fp_line (start {p(x0, y0)}) (end {p(x1, y1)}) (stroke (width {width}) (type {kind})) '
                f'(layer "{layer}") (uuid "{uid()}"))\n')

    def text(s, x, y, layer, size=1.0, just=''):
        j = f' (justify {just})' if just else ''
        return (f'  (fp_text user "{s}" (at {p(x, y)}) (layer "{layer}") (uuid "{uid()}") '
                f'(effects (font (size {size} {size}) (thickness {size * 0.12:.3f})){j}))\n')

    def rect(x0, x1, y0, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    e1, e2, dw = 'Eco1.User', 'Eco2.User', 'Dwgs.User'
    s = ['(footprint "Case_OBD2_72x46"\n  (version 20241229) (generator "scaner_gen") (layer "F.Cu")\n',
         '  (descr "Корпус OBD2 72x46x26 (Алиэкспресс): внутренний контур, стойки, штекер. tools/gen_case.py")\n',
         '  (tags "enclosure OBD2")\n',
         f'  (property "Reference" "CASE1" (at {p(0, -T_END - 2)}) (layer "{e2}") (hide yes) (uuid "{uid()}") '
         '(effects (font (size 1 1) (thickness 0.12))))\n',
         f'  (property "Value" "Корпус OBD2 72x46x26" (at {p(0, -T_END - 4)}) (layer "{e2}") (hide yes) (uuid "{uid()}") '
         '(effects (font (size 1 1) (thickness 0.12))))\n',
         '  (attr board_only exclude_from_pos_files exclude_from_bom)\n']
    # Eco1 — что внутри: стенки изнутри, стойки, вкладыш штекера с контактами
    s.append(poly(INNER, e1, 0.2))
    for x, y in POSTS:
        s.append(circle(x, y, POST_D, e1, 0.2))
        s.append(circle(x, y, CB_D, e1, 0.1))
        s.append(line(x - 5, y, x + 5, y, e1, 0.05, 'dash_dot'))
        s.append(line(x, y - 5, x, y + 5, e1, 0.05, 'dash_dot'))
    s.append(poly(rect(-WIN_W / 2, WIN_W / 2, Y_PLUG, L_IN), e1, 0.15))
    for x in sorted({x for x, _ in PINS}):
        s.append(poly(rect(x - PIN_W / 2, x + PIN_W / 2, Y_PINS, Y_PLUG), e1, 0.1))
    def fmt(v):
        return f'{v:.2f}'.rstrip('0').rstrip('.').replace('.', ',')

    s.append(text(f'контакты OBD, ряды на {fmt(PINS[8][1])} и {fmt(PINS[0][1])} от дна (принято)',
                  0, Y_PINS - 1.2, e1, 0.8))
    for i, t in enumerate(['Корпус, высота от дна основания, мм:',
                           f'стойки Ø8 — до {fmt(POST_H)} (сверху в них Ø5,5 на {fmt(CB_DEPTH)})',
                           f'стойки крышки Ø5,2 — от {fmt(H_IN - LPOST_H)} вверх',
                           f'шов {fmt(BASE_OUT)} снаружи / {fmt(BASE_IN)} изнутри',
                           f'потолок крышки {fmt(H_IN)}',
                           f'контакты OBD {fmt(PINS[8][1])} и {fmt(PINS[0][1])} (принято)',
                           f'плата в 3D: низ {fmt(BOARD_Z)}, верх {fmt(BOARD_Z + PCB_T)}']):
        s.append(text(t, W / 2 + 3, 50 - 1.8 * i, e1, 1.0, 'left'))   # справа от корпуса, не на плате
    # Eco2 — снаружи: стенки, наружная часть штекера
    s.append(poly(OUTER, e2, 0.15))
    s.append(poly(rect(-W / 2 + LEG, W / 2 - LEG, Y_BACK, Y_FRONT - LEG), e2, 0.05))   # где начинаются фаски
    s.append(text(f'по рифлению {fmt(W_RIB)}', -W / 2 - 1, Y_MID, e2, 0.9, 'right'))
    bw = PLUG_BODY_W / 2
    s.append(poly(rect(-bw, bw, Y_FRONT, Y_FRONT + PLUG_OUT), e2, 0.15))
    s.append(text('штекер OBD (съёмный, ставится любой стороной)', 0, Y_FRONT + PLUG_OUT / 2, e2, 0.9))
    s.append(text('задняя стенка', 0, Y_BACK - 1.5, e2, 0.9))
    # Dwgs — куда класть плату 40 x 60
    s.append(poly(rect(-20, 20, 0.5, 60.5), dw, 0.15, dash=True))
    s.append(text('плата 40 x 60', 0, 2.2, dw, 1.2))
    z = -(BOARD_Z + PCB_T)
    for name, op in (('Case_OBD2_base.wrl', 0.55), ('Case_OBD2_lid.wrl', 0.3)):
        s.append(f'  (model "${{KIPRJMOD}}/scaner.3dshapes/{name}" (opacity {op}) (offset (xyz 0 0 {z:.2f})) '
                 '(scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))\n')
    s.append(')\n')
    path = os.path.join(PRETTY, 'Case_OBD2_72x46.kicad_mod')
    with open(path, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(''.join(s))
    print('ok', path)


if __name__ == '__main__':
    parts = build()
    write_models(parts)
    write_footprint()
    if '--no-drawings' not in sys.argv:
        import case_drawing
        case_drawing.draw(sys.modules[__name__], parts)
