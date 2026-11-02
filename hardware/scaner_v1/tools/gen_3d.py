#!/usr/bin/env python3
"""3D-модели (.wrl) деталей, которых нет в библиотеке KiCad: XIAO на гнёздах, дроссель 10 x 13,5,
стабилитрон DO-35 с шагом 5,08, электролиты в живой высоте 12,3, провода от разъёма OBD на J1/J2.
Обычный питон:

  python tools/gen_3d.py

Пишет в scaner.3dshapes/. Подключают их gen_schematic.py (свои посадочные места) и gen_pcb.py.
Правила VRML для KiCad (проверено в проекте блока питания):
  - единица VRML = 0,1 дюйма = 2,54 мм (здесь всё в мм, делится само);
  - оси: X — вправо, Y — ВВЕРХ на экране (= минус Y платы), Z — высота над платой;
  - встроенный Cylinder KiCad 10 не рисует — всё круглое делается сеткой (IndexedFaceSet);
  - начало координат = начало посадочного места (обычно вывод 1); нижние детали KiCad зеркалит сам.
Координаты ниже — как в посадочном месте (Y вниз), переворот Y делает box()/cyl().
"""
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'scaner.3dshapes')
K = 2.54

MAT = {  # diffuse r g b, specular, shininess, transparency
    'pcb_x': (0.04, 0.10, 0.22, 0.20, 0.30, 0.0),   # плата XIAO (тёмно-синяя)
    'gold':  (0.85, 0.65, 0.20, 0.70, 0.60, 0.0),
    'tin':   (0.55, 0.56, 0.58, 0.45, 0.50, 0.0),
    'steel': (0.62, 0.64, 0.66, 0.40, 0.45, 0.0),
    'black': (0.08, 0.08, 0.09, 0.15, 0.20, 0.0),
    'ferr':  (0.16, 0.16, 0.18, 0.20, 0.25, 0.0),
    'ferr_t': (0.30, 0.30, 0.32, 0.20, 0.25, 0.0),
    'glass': (0.85, 0.88, 0.90, 0.60, 0.80, 0.55),
    'glass_z': (0.90, 0.42, 0.12, 0.60, 0.80, 0.30),  # стекло стабилитрона (оранжевое)
    'sleeve': (0.10, 0.10, 0.13, 0.25, 0.30, 0.0),    # плёнка электролита
    'stripe': (0.60, 0.60, 0.64, 0.25, 0.30, 0.0),    # полоса минуса на ней
    'alu':   (0.78, 0.79, 0.81, 0.60, 0.60, 0.0),     # алюминиевый торец
    'white': (0.92, 0.92, 0.90, 0.10, 0.20, 0.0),
    'cu':    (0.80, 0.52, 0.25, 0.55, 0.55, 0.0),
    'red':   (0.85, 0.08, 0.06, 0.20, 0.30, 0.0),
    'wire_k': (0.10, 0.10, 0.10, 0.20, 0.30, 0.0),
    'green': (0.15, 0.80, 0.25, 0.30, 0.40, 0.0),
    'yellow': (1.00, 0.85, 0.15, 0.30, 0.40, 0.0),
    'led':   (1.00, 0.55, 0.10, 0.30, 0.40, 0.0),
    'case':  (0.20, 0.20, 0.22, 0.15, 0.20, 0.0),   # корпус OBD2 (tools/gen_case.py)
}


def mat(name):
    r, g, b, sp, sh, tr = MAT[name]
    return ('appearance Appearance { material Material {\n'
            f'  diffuseColor {r:.3f} {g:.3f} {b:.3f}\n  specularColor {sp:.2f} {sp:.2f} {sp:.2f}\n'
            f'  shininess {sh:.2f}\n  transparency {tr:.2f}\n  ambientIntensity 0.3\n}} }}')


def box(x, y, z, sx, sy, sz, m):
    """Коробка: центр (x, y, z) в мм в координатах посадочного места, размеры в мм."""
    return (f'Transform {{ translation {x / K:.4f} {-y / K:.4f} {z / K:.4f} children [ Shape {{\n  {mat(m)}\n'
            f'  geometry Box {{ size {sx / K:.4f} {sy / K:.4f} {sz / K:.4f} }}\n}} ] }}\n')


def cyl(x, y, z, r, h, m, axis='z', seg=24):
    """Цилиндр сеткой: центр (x, y, z), радиус r, длина h вдоль оси axis."""
    pts, faces = [], []
    for s in (-0.5, 0.5):
        for i in range(seg):
            a = 2 * math.pi * i / seg
            c, d = r * math.cos(a), r * math.sin(a)
            p = {'x': (h * s, c, d), 'y': (c, h * s, d), 'z': (c, d, h * s)}[axis]
            pts.append(((x + p[0]) / K, -(y + p[1]) / K, (z + p[2]) / K))
    for i in range(seg):
        j = (i + 1) % seg
        faces.append((i, j, seg + j, seg + i))
    faces.append(tuple(range(seg - 1, -1, -1)))
    faces.append(tuple(range(seg, 2 * seg)))
    ps = ',\n'.join('%.4f %.4f %.4f' % p for p in pts)
    fs = ',\n'.join(', '.join(str(i) for i in f) + ', -1' for f in faces)
    return (f'Transform {{ children [ Shape {{\n  {mat(m)}\n'
            f'  geometry IndexedFaceSet {{ solid FALSE creaseAngle 1.0\n'
            f'    coord Coordinate {{ point [\n{ps}\n] }}\n    coordIndex [\n{fs}\n]\n  }}\n}} ] }}\n')


def write(name, parts):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('#VRML V2.0 utf8\n# scaner_v1, tools/gen_3d.py\n\n' + ''.join(parts))
    print('ok', name)


# ---------- XIAO ESP32-C5 на двух гнёздах 1x7 (10 мм от платы) ----------
# Посадочное место: вывод 1 в (0, 0), ряд 1–7 вниз по Y при X = 0, ряд 8–14 при X = 15,24.
# Плата XIAO 17,8 x 21 мм, USB-C на торце со стороны вывода 1 (Y < 0).
def xiao():
    p = []
    for x in (0.0, 15.24):
        p.append(box(x, 7.62, 4.25, 2.54, 17.78, 8.5, 'black'))          # гнездо 1x7, высота 8,5
        p.append(box(x, 7.62, 9.25, 2.4, 17.78, 1.5, 'black'))           # пластик штыревой гребёнки
        for i in range(7):
            y = 2.54 * i
            if not (x == 0 and i in (2, 3, 4, 6)):                         # D2, D3, D4, D6 выкушены
                p.append(box(x, y, -1.5, 0.64, 0.64, 3.0, 'gold'))       # ножки гнезда сквозь плату
            p.append(box(x, y, 8.52, 1.0, 1.0, 0.04, 'black'))           # гнёзда сверху (тень)
    p.append(box(7.62, 7.62, 10.6, 17.78, 21.0, 1.2, 'pcb_x'))            # плата XIAO
    for x in (-0.77, 16.01):                                             # полукруглые площадки по краю
        for i in range(7):
            p.append(box(x, 2.54 * i, 11.22, 1.0, 1.5, 0.04, 'gold'))
    p.append(box(7.62, -1.0, 12.8, 8.9, 7.3, 3.2, 'tin'))                # USB-C, торчит за край на ~1,3
    p.append(box(7.62, -4.64, 12.8, 7.0, 0.02, 2.0, 'black'))            # отверстие разъёма
    p.append(box(7.62, 10.6, 12.3, 12.0, 10.5, 2.2, 'tin'))              # экран ESP32-C5
    p.append(box(13.6, 16.3, 11.5, 3.0, 3.0, 0.6, 'tin'))                # U.FL
    p.append(cyl(13.6, 16.3, 12.2, 1.0, 1.0, 'gold'))
    for x in (1.2, 14.0):                                                # кнопки BOOT и RESET
        p.append(box(x, 1.4, 11.7, 2.6, 2.0, 1.0, 'steel'))
        p.append(box(x, 1.4, 12.3, 1.2, 1.0, 0.4, 'white'))
    p.append(box(1.6, 4.4, 11.45, 1.0, 0.6, 0.5, 'led'))                 # светодиод
    write('XIAO_ESP32C5_on_sockets.wrl', p)


# ---------- дроссель выводной в ферритовом чулке, стоя (живой: 10 x 13,5, шаг 5) ----------
# Вывод 1 в (0, 0), вывод 2 в (pitch, 0); корпус по центру между ними.
def radial_inductor(name, d, h, pitch):
    r, cx = d / 2, pitch / 2
    p = [cyl(cx, 0, 0.15, r - 0.6, 0.3, 'black'),                         # основание
         cyl(cx, 0, 0.3 + (h - 0.6) / 2, r, h - 0.6, 'ferr'),             # ферритовый чулок
         cyl(cx, 0, h - 0.15, r - 0.15, 0.3, 'ferr_t'),                    # торец
         cyl(cx, 0, h + 0.01, r * 0.45, 0.02, 'black')]                    # торец катушки внутри чулка
    for x in (0.0, pitch):
        p.append(cyl(x, 0, -0.7, 0.2, 1.8, 'cu', seg=12))                 # провод 0,3–0,35 сквозь плату
    write(name, p)


# ---------- стабилитрон DO-35 лёжа, шаг 5,08 ----------
# Вывод 1 (катод, полоска) в (0, 0), вывод 2 в (5,08, 0). Стекляшка 3,5 x 1,9 лежит на плате.
def zener_do35():
    r, z = 0.95, 0.95
    p = [cyl(2.54, 0, z, r, 3.5, 'glass_z', axis='x'),
         cyl(1.35, 0, z, r + 0.01, 0.4, 'black', axis='x')]               # полоска катода
    for x0, x1 in ((0.0, 0.79), (4.29, 5.08)):
        p.append(cyl((x0 + x1) / 2, 0, z, 0.25, x1 - x0, 'tin', axis='x', seg=12))
    for x in (0.0, 5.08):                                                # ноги вниз сквозь плату
        p.append(cyl(x, 0, (z - 1.5) / 2, 0.25, z + 1.5, 'tin', seg=12))
    write('D_DO-35_P5.08mm_Horizontal.wrl', p)


# ---------- электролит стоя (живые банки: 10 x 12,3 шаг 5 и 8 x 12,3 шаг 3,5) ----------
# Вывод 1 (+) в (0, 0), вывод 2 (−) в (pitch, 0), полоса минуса со стороны вывода 2.
def electrolytic(name, d, h, pitch):
    r, cx = d / 2, pitch / 2
    p = [cyl(cx, 0, 0.25, r - 0.3, 0.5, 'black'),                         # резиновая пробка снизу
         cyl(cx, 0, 0.5 + (h - 0.8) / 2, r, h - 0.8, 'sleeve'),
         cyl(cx, 0, h - 0.15, r - 0.35, 0.3, 'alu'),                       # торец с насечкой
         box(cx + r - 0.15, 0, 0.5 + (h - 0.8) / 2, 0.4, d * 0.4, h - 0.9, 'stripe')]
    for a in (0, 90):                                                    # насечка крестом
        sx, sy = (d * 0.6, 0.3) if a == 0 else (0.3, d * 0.6)
        p.append(box(cx, 0, h + 0.01, sx, sy, 0.02, 'black'))
    for x in (0.0, pitch):
        p.append(cyl(x, 0, -0.7, 0.3, 1.8, 'tin', seg=12))                # ноги сквозь плату
    write(name, p)


# ---------- провода от разъёма OBD (впаяны в отверстия, торчат вверх) ----------
# Посадочное место PinHeader: выводы вдоль Y через 2,54.
def wires(name, colors):
    p = []
    for i, c in enumerate(colors):
        y = 2.54 * i
        p.append(cyl(0, y, -0.9, 0.35, 2.6, 'cu', seg=12))               # медь сквозь плату
        p.append(cyl(0, y, -1.8, 0.9, 0.5, 'tin', seg=16))               # пайка снизу
        p.append(cyl(0, y, 0.6, 0.45, 1.2, 'cu', seg=12))                # зачищенный кончик
        p.append(cyl(0, y, 5.2, 0.8, 8.0, c, seg=16))                    # изоляция
    write(name, p)


if __name__ == '__main__':
    xiao()
    radial_inductor('L_Radial_D10_H13.5_P5.00mm.wrl', 10.0, 13.5, 5.0)  # L1 100 мкГн
    zener_do35()
    electrolytic('CP_D10_H12.3_P5.00mm.wrl', 10.0, 12.3, 5.0)            # C1 100 мкФ / 63 В
    electrolytic('CP_D8_H12.3_P3.50mm.wrl', 8.0, 12.3, 3.5)              # C3 220 мкФ / 25 В
    wires('Wires_OBD_power_1x03.wrl', ['red', 'wire_k', 'wire_k'])            # OBD 16, 4, 5
    wires('Wires_OBD_CAN_1x04.wrl', ['green', 'yellow', 'green', 'yellow'])   # 14 L, 6 H, 8 L, 3 H
