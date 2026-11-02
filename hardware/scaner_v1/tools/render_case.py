#!/usr/bin/env python3
"""Картинки корпуса OBD2 рендером KiCad (после tools/gen_case.py). Запускать питоном KiCad:

  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/render_case.py

Пишет в case/: case_3d.png (корпус, крышка поднята), case_3d_inside.png (основание со штекером сверху),
board_in_case.png и board_in_case_side.png (плата scaner_v1.kicad_pcb в корпусе, как в 3D-просмотре).
Для корпуса отдельно собирается временная плата: её контур прячется в дне, модели непрозрачные.
"""
import os
import subprocess
import tempfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
OUT = os.path.join(PRJ, 'case')
CLI = r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'


def mm(v):
    return pcbnew.FromMM(v)


def render(pcb, png, rotate=None, side=None, w=1600, h=1200, zoom=1.0):
    cmd = [CLI, 'pcb', 'render', '-o', png, '-w', str(w), '-h', str(h), '--quality', 'high',
           '--background', 'opaque', '--zoom', str(zoom)]
    cmd += ['--rotate', rotate] if rotate else ['--side', side]
    subprocess.run(cmd + [pcb], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('ok', png)


def case_only(tmp, lift, with_lid):
    """Временная плата: только корпус; дно на верхней плоскости платы, крышка поднята на lift мм."""
    board = pcbnew.BOARD()
    fp = pcbnew.FootprintLoad(os.path.join(PRJ, 'scaner.pretty'), 'Case_OBD2_72x46')
    board.Add(fp)
    models = fp.Models()
    for i in range(len(models)):
        m = models[i]
        m.m_Filename = m.m_Filename.replace('${KIPRJMOD}', PRJ.replace('\\', '/'))
        m.m_Opacity = 1.0
        m.m_Offset = pcbnew.VECTOR3D(0, 0, lift if 'lid' in m.m_Filename else 0)
        m.m_Show = with_lid or 'lid' not in m.m_Filename
    # плата по полости корпуса: 1,6 мм целиком прячется в дне (2,1), а камера кадрирует по ней
    rect = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_RECTANGLE)
    rect.SetStart(pcbnew.VECTOR2I(mm(-20), mm(-34)))
    rect.SetEnd(pcbnew.VECTOR2I(mm(20), mm(34)))
    rect.SetLayer(pcbnew.Edge_Cuts)
    board.Add(rect)
    path = os.path.join(tmp, f'case_{lift}_{int(with_lid)}.kicad_pcb')
    pcbnew.SaveBoard(path, board)
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        render(case_only(tmp, 32, True), os.path.join(OUT, 'case_3d.png'), rotate='-62,0,150', zoom=0.5)
        render(case_only(tmp, 0, False), os.path.join(OUT, 'case_3d_inside.png'), rotate='-40,0,-25', zoom=0.68)
    pcb = os.path.join(PRJ, 'scaner_v1.kicad_pcb')
    render(pcb, os.path.join(OUT, 'board_in_case.png'), rotate='-50,0,-35')
    render(pcb, os.path.join(OUT, 'board_in_case_side.png'), side='right', h=700, zoom=1.3)


if __name__ == '__main__':
    main()
