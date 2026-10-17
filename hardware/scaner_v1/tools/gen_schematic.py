#!/usr/bin/env python3
"""Генератор схемы платы v1 сканера-адаптера OBD (KiCad 10).

Разовый генератор. Создаёт scaner_v1.kicad_sch, библиотеку символов scaner.kicad_sym,
посадочное место XIAO, таблицы библиотек и файл проекта. Связи — через короткие провода
и метки цепей. После ручных правок в KiCad источником правды становится .kicad_sch:
повторный запуск его ПЕРЕЗАПИШЕТ.

Запуск (из папки hardware/scaner_v1):  py -3 tools/gen_schematic.py
Проверка:  py -3 tools/check_netlist.py
"""
import json
import math
import os
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from sexp import parse, unq, q, dump, find, get, load_lib  # noqa: E402

KICAD_SYM = r'C:\Program Files\KiCad\10.0\share\kicad\symbols'
NAME = 'scaner_v1'
VERSION = '20251024'
STUB = 2.54

_uuid_n = [0]


def uid():
    _uuid_n[0] += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'scaner_v1/{_uuid_n[0]}'))


ROOT = str(uuid.uuid5(uuid.NAMESPACE_URL, 'scaner_v1/root'))


def f(v):
    s = ('%.4f' % v).rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


# ---------------------------------------------------------------- local symbols
def _pin(ptype, x, y, ang, name, num, length=5.08):
    return (f'(pin {ptype} line (at {f(x)} {f(y)} {ang}) (length {f(length)}) '
            f'(name "{name}" (effects (font (size 1.27 1.27)))) '
            f'(number "{num}" (effects (font (size 1.27 1.27)))))')


def _local_symbol(name, ref, value, fp, ds, descr, body, pins, ref_y, val_y):
    x1, y1, x2, y2 = body
    return f'''(symbol "{name}"
  (pin_names (offset 1.016))
  (exclude_from_sim no) (in_bom yes) (on_board yes)
  (property "Reference" "{ref}" (at 0 {f(ref_y)} 0) (effects (font (size 1.27 1.27))))
  (property "Value" "{value}" (at 0 {f(val_y)} 0) (effects (font (size 1.27 1.27))))
  (property "Footprint" "{fp}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Datasheet" "{ds}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (property "Description" "{descr}" (at 0 0 0) (effects (font (size 1.27 1.27)) (hide yes)))
  (symbol "{name}_0_1"
    (rectangle (start {f(x1)} {f(y1)}) (end {f(x2)} {f(y2)}) (stroke (width 0.254) (type default)) (fill (type background))))
  (symbol "{name}_1_1"
    {chr(10).join("    " + p for p in pins)})
)'''


XIAO_PINS = [  # (номер, имя, тип, сторона, y)
    ('1', 'D0/GPIO1/A0', 'bidirectional', 'L', 7.62),
    ('2', 'D1/GPIO0', 'bidirectional', 'L', 5.08),
    ('3', 'D2/GPIO25', 'bidirectional', 'L', 2.54),
    ('4', 'D3/GPIO7', 'bidirectional', 'L', 0),
    ('5', 'D4/GPIO23/SDA', 'bidirectional', 'L', -2.54),
    ('6', 'D5/GPIO24/SCL', 'bidirectional', 'L', -5.08),
    ('7', 'D6/GPIO11/TX', 'bidirectional', 'L', -7.62),
    ('14', '5V', 'power_in', 'R', 7.62),
    ('13', 'GND', 'power_in', 'R', 5.08),
    ('12', '3V3', 'power_out', 'R', 2.54),
    ('11', 'D10/GPIO10', 'bidirectional', 'R', 0),
    ('10', 'D9/GPIO9', 'bidirectional', 'R', -2.54),
    ('9', 'D8/GPIO8', 'bidirectional', 'R', -5.08),
    ('8', 'D7/GPIO12/RX', 'bidirectional', 'R', -7.62),
]
XIAO_SYM = _local_symbol(
    'XIAO_ESP32C5', 'U', 'XIAO_ESP32C5', 'scaner:XIAO_ESP32C5_Socket',
    'https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/',
    'Seeed Studio XIAO ESP32-C5 на панельках 2x7',
    (-15.24, 11.43, 15.24, -11.43),
    [_pin(t, -20.32 if s == 'L' else 20.32, y, 0 if s == 'L' else 180, n, num) for num, n, t, s, y in XIAO_PINS],
    13.97, -13.97)

LOCAL_LIB = f'''(kicad_symbol_lib
  (version 20241209)
  (generator "scaner_gen")
  {XIAO_SYM}
)
'''


# ---------------------------------------------------------------- libraries
def flatten(libs, lib_id):
    lib, name = lib_id.split(':')
    if lib == 'scaner':
        s = parse(XIAO_SYM)[0]
        s = list(s)
        s[1] = q(lib_id)
        return s
    syms = libs[lib]
    s = syms[name]
    ext = get(s, 'extends')
    if not ext:
        s = list(s)
        s[1] = q(lib_id)
        return s
    parent = syms[unq(ext[1])]
    pname = unq(parent[1])
    new = ['symbol', q(lib_id)]
    for item in parent[2:]:
        if isinstance(item, list) and item[0] in ('property', 'symbol', 'embedded_fonts'):
            continue
        new.append(item)
    new += find(s, 'property')
    for u in find(parent, 'symbol'):
        u2 = list(u)
        u2[1] = q(unq(u[1]).replace(pname, name, 1))
        new.append(u2)
    emb = get(parent, 'embedded_fonts')
    if emb:
        new.append(emb)
    return new


def sym_pins(sym):
    """Выводы единицы 1 (и общей 0): номер -> (x, y, угол)."""
    out = {}
    for u in find(sym, 'symbol'):
        parts = unq(u[1]).rsplit('_', 2)
        if len(parts) == 3 and parts[1] in ('0', '1') and parts[2] in ('0', '1'):
            for p in find(u, 'pin'):
                at = get(p, 'at')
                num = unq(get(p, 'number')[1])
                out[num] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0)
    return out


def pin_world(X, Y, rot, px, py, pa):
    t = math.radians(rot)
    xr = px * math.cos(t) - py * math.sin(t)
    yr = px * math.sin(t) + py * math.cos(t)
    a = math.radians(pa + rot)
    ox, oy = -math.cos(a), math.sin(a)
    return X + xr, Y - yr, round(ox), round(oy)


# ---------------------------------------------------------------- design
R0805 = 'Resistor_SMD:R_0805_2012Metric'
R1206 = 'Resistor_SMD:R_1206_3216Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
CP8 = 'Capacitor_THT:CP_Radial_D8.0mm_P3.50mm'
SMA = 'Diode_SMD:D_SMA'
DO35 = 'Diode_THT:D_DO-35_SOD27_P2.54mm_Vertical_AnodeUp'
DO201 = 'Diode_THT:D_DO-201AD_P5.08mm_Vertical_AnodeUp'
SJ = 'Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm'

# (ref, lib_id, value, footprint, x, y, rot, {pin: net}, dnp)
PARTS = [
    # 1. вход, защита, замер АКБ
    ('J1', 'Connector_Generic:Conn_01x07', 'OBD кабель', 'Connector_PinHeader_2.54mm:PinHeader_1x07_P2.54mm_Vertical',
     30.48, 66.04, 0, {'1': 'VBAT_OBD', '2': 'GND', '3': 'GND', '4': 'CANA_H', '5': 'CANA_L', '6': 'CANB_H', '7': 'CANB_L'}, False),
    ('F1', 'Device:Fuse', '1A 5x20', 'Fuse:Fuseholder_Clip-5x20mm_Littelfuse_111_Inline_P20.00x5.00mm_D1.05mm_Horizontal',
     50.8, 58.42, 0, {'1': 'VBAT_OBD', '2': 'VIN_F'}, False),
    ('D1', 'Device:D_Zener', '1.5KE27A', DO201, 66.04, 78.74, 0, {'1': 'VIN_F', '2': 'GND'}, True),
    ('D2', 'Device:D', 'HS1M', SMA, 66.04, 55.88, 180, {'1': 'VIN_PROT', '2': 'VIN_F'}, False),
    ('R1', 'Device:R', '47k', R1206, 91.44, 66.04, 0, {'1': 'VIN_PROT', '2': 'GATE_REF'}, False),
    ('D3', 'Device:D_Zener', '15V', DO35, 91.44, 81.28, 0, {'1': 'GATE_REF', '2': 'ZMID'}, False),
    ('D4', 'Device:D_Zener', '15V', DO35, 91.44, 93.98, 0, {'1': 'ZMID', '2': 'GND'}, False),
    ('R2', 'Device:R', '100', R0805, 106.68, 76.2, 0, {'1': 'GATE_REF', '2': 'Q1_G'}, False),
    ('Q1', 'Transistor_FET:Q_NMOS_GDS', 'IRFB4110', 'Package_TO_SOT_THT:TO-220-3_Horizontal_TabDown',
     127.0, 66.04, 0, {'1': 'Q1_G', '2': 'VIN_PROT', '3': 'VIN_BUCK'}, False),
    ('D5', 'Device:D_Zener', '15V', DO35, 127.0, 86.36, 0, {'1': 'Q1_G', '2': 'VIN_BUCK'}, False),
    ('JP1', 'Jumper:SolderJumper_2_Open', 'BYPASS_Q1', SJ, 127.0, 45.72, 0, {'1': 'VIN_PROT', '2': 'VIN_BUCK'}, False),
    ('R9', 'Device:R', '220k', R1206, 152.4, 66.04, 0, {'1': 'VIN_PROT', '2': 'VBAT_ADC'}, False),
    ('R10', 'Device:R', '33k', R0805, 152.4, 81.28, 0, {'1': 'VBAT_ADC', '2': 'GND'}, False),
    ('C8', 'Device:C', '100n', C0805, 162.56, 81.28, 0, {'1': 'VBAT_ADC', '2': 'GND'}, False),
    # 2. DC-DC
    ('C1', 'Device:C_Polarized', '100u/50V', CP8, 187.96, 66.04, 0, {'1': 'VIN_BUCK', '2': 'GND'}, False),
    ('C2', 'Device:C', '100n/50V', C0805, 203.2, 66.04, 0, {'1': 'VIN_BUCK', '2': 'GND'}, False),
    ('U1', 'Regulator_Switching:LM2596S-ADJ', 'LM2596S-ADJ', 'Package_TO_SOT_SMD:TO-263-5_TabPin3',
     241.3, 63.5, 0, {'1': 'VIN_BUCK', '2': 'SW', '3': 'GND', '4': 'FB', '5': 'GND'}, False),
    ('D6', 'Device:D_Schottky', 'SS34', SMA, 266.7, 81.28, 0, {'1': 'SW', '2': 'GND'}, False),
    ('L1', 'Device:L', '120uH', 'Inductor_SMD:L_12x12mm_H4.5mm', 274.32, 58.42, 0, {'1': 'SW', '2': 'V5_BUCK'}, False),
    ('C3', 'Device:C_Polarized', '220u/25V', CP8, 284.48, 71.12, 0, {'1': 'V5_BUCK', '2': 'GND'}, False),
    ('C4', 'Device:C', '100n', C0805, 299.72, 71.12, 0, {'1': 'V5_BUCK', '2': 'GND'}, False),
    ('R3', 'Device:R', '3k0', R0805, 314.96, 63.5, 0, {'1': 'V5_BUCK', '2': 'FB'}, False),
    ('R4', 'Device:R', '1k', R0805, 314.96, 78.74, 0, {'1': 'FB', '2': 'GND'}, False),
    ('D7', 'Device:D_Schottky', 'SS34', SMA, 332.74, 50.8, 180, {'1': 'V5', '2': 'V5_BUCK'}, False),
    ('D8', 'Device:D_TVS', '1.5KE6.8CA', DO201, 347.98, 66.04, 0, {'1': 'V5', '2': 'GND'}, False),
    ('C5', 'Device:C', '10u', C0805, 363.22, 66.04, 0, {'1': 'V5', '2': 'GND'}, False),
    # 3. XIAO
    ('U4', 'scaner:XIAO_ESP32C5', 'XIAO_ESP32C5', 'scaner:XIAO_ESP32C5_Socket', 76.2, 172.72, 0,
     {'1': 'VBAT_ADC', '2': 'CANB_RX', '5': 'RS_A', '6': 'RS_B', '9': 'CANB_TX', '10': 'CANA_RX',
      '11': 'CANA_TX', '12': '+3V3', '13': 'GND', '14': 'V5'}, False),
    ('R5', 'Device:R', '10k', R0805, 127.0, 160.02, 0, {'1': '+3V3', '2': 'CANA_TX'}, False),
    ('R6', 'Device:R', '10k', R0805, 139.7, 160.02, 0, {'1': '+3V3', '2': 'CANB_TX'}, False),
    ('R11', 'Device:R', '10k', R0805, 152.4, 160.02, 0, {'1': '+3V3', '2': 'RS_A'}, False),
    ('R12', 'Device:R', '10k', R0805, 165.1, 160.02, 0, {'1': '+3V3', '2': 'RS_B'}, False),
    # 4. CAN
    ('U2', 'Interface_CAN_LIN:SN65HVD230', 'SN65HVD230', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
     228.6, 162.56, 0, {'1': 'CANA_TX', '2': 'GND', '3': '+3V3', '4': 'CANA_RX', '6': 'CANA_L', '7': 'CANA_H', '8': 'RS_A'}, False),
    ('C6', 'Device:C', '100n', C0805, 190.5, 162.56, 0, {'1': '+3V3', '2': 'GND'}, False),
    ('R7', 'Device:R', '120', R0805, 266.7, 160.02, 0, {'1': 'CANA_H', '2': 'TERM_A'}, False),
    ('JP2', 'Jumper:SolderJumper_2_Open', 'TERM_A', SJ, 281.94, 170.18, 0, {'1': 'TERM_A', '2': 'CANA_L'}, False),
    ('U3', 'Interface_CAN_LIN:SN65HVD230', 'SN65HVD230', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
     228.6, 203.2, 0, {'1': 'CANB_TX', '2': 'GND', '3': '+3V3', '4': 'CANB_RX', '6': 'CANB_L', '7': 'CANB_H', '8': 'RS_B'}, False),
    ('C7', 'Device:C', '100n', C0805, 190.5, 203.2, 0, {'1': '+3V3', '2': 'GND'}, False),
    ('R8', 'Device:R', '120', R0805, 266.7, 200.66, 0, {'1': 'CANB_H', '2': 'TERM_B'}, False),
    ('JP3', 'Jumper:SolderJumper_2_Open', 'TERM_B', SJ, 281.94, 210.82, 0, {'1': 'TERM_B', '2': 'CANB_L'}, False),
    # механика
    ('H1', 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 320.04, 162.56, 0, {}, False),
    ('H2', 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 335.28, 162.56, 0, {}, False),
    ('H3', 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 350.52, 162.56, 0, {}, False),
    ('H4', 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 365.76, 162.56, 0, {}, False),
]
FLAGS = [('GND', 330.2, 190.5), ('VIN_BUCK', 345.44, 190.5), ('V5', 360.68, 190.5)]

TEXTS = [
    (20.32, 30.48, 2.0, '1. Вход, защита, замер напряжения АКБ'),
    (190.5, 30.48, 2.0, '2. DC-DC LM2596S-ADJ -> 4,92 В'),
    (20.32, 142.24, 2.0, '3. Seeed XIAO ESP32-C5'),
    (190.5, 142.24, 2.0, '4. CAN: канал A — OBD 6/14, канал B — OBD 3/8 (Diag-on-CAN PSA)'),
    (20.32, 107.95, 1.27, 'J1 — короткие провода от выводов разъёма в корпусе OBD: 1 = OBD16 (+12 В), 2 = OBD4, 3 = OBD5, 4 = OBD6, 5 = OBD14, 6 = OBD3, 7 = OBD8'),
    (20.32, 111.76, 1.27, 'D1 1.5KE27A — опция, по умолчанию не ставится (DNP). Повторитель Q1 ограничивает вход LM2596 ~26,5 В'),
    (20.32, 115.57, 1.27, 'JP1 замкнуть, только если Q1, D3–D5, R1, R2 не установлены (вариант без повторителя)'),
    (20.32, 119.38, 1.27, 'R1 и R9 — корпус 1206: на них бывают десятки вольт. VBAT_ADC: 12 В -> ~1,4 В на D0'),
    (190.5, 107.95, 1.27, 'Uвых = 1,23 x (1 + R3/R4) = 4,92 В; после D7 ~4,6 В — ниже USB, обратно в ноутбук не пойдёт'),
    (190.5, 111.76, 1.27, 'D8 1.5KE6.8CA — страховка: при пробое LM2596 зажимает линию 5V, сгорает F1'),
    (20.32, 233.68, 1.27, 'Не занимать: D2, D3 (strapping), D6 (лог загрузки). D4/D5 — Rs трансиверов, D7 — резерв'),
    (20.32, 237.49, 1.27, 'Посадочное место XIAO — проверить по живой плате (ряды через 15,24 мм)'),
    (190.5, 233.68, 1.27, 'U2/U3 — SN65HVD230, выпаянные с модулей Waveshare. Rs: 1 (подтяжка) = только слушать, прошивка опускает в 0'),
    (190.5, 237.49, 1.27, 'JP2/JP3 — терминаторы 120 Ом, по умолчанию разомкнуты. Канал B по замеру: между OBD 3 и 8 ~120 Ом -> замкнуть JP3'),
]


# ---------------------------------------------------------------- writer
def prop(name, val, x, y, hide=False, justify=None, size=1.27):
    j = f' (justify {justify})' if justify else ''
    h = ' (hide yes)' if hide else ''
    return (f'(property "{name}" {q(val)} (at {f(x)} {f(y)} 0) '
            f'(effects (font (size {f(size)} {f(size)})){j}{h}))')


def ref_value_pos(lib_id, x, y):
    if lib_id in ('Device:R', 'Device:C', 'Device:C_Polarized', 'Device:L', 'Device:Fuse'):
        return (x + 2.54, y - 1.27, 'left'), (x + 2.54, y + 1.27, 'left')
    if lib_id.startswith('Device:D') or lib_id.startswith('Jumper:'):
        return (x, y - 3.81, None), (x, y + 3.81, None)
    if lib_id.startswith('Transistor_FET'):
        return (x + 5.08, y - 1.27, 'left'), (x + 5.08, y + 1.27, 'left')
    if lib_id.startswith('Regulator'):
        return (x, y - 8.89, None), (x, y + 11.43, None)
    if lib_id == 'scaner:XIAO_ESP32C5':
        return (x, y - 13.97, None), (x, y + 13.97, None)
    if lib_id == 'scaner:SN65HVD230_Module':
        return (x, y - 10.16, None), (x, y + 8.89, None)
    if lib_id.startswith('Connector'):
        return (x, y - 10.16, None), (x, y + 10.16, None)
    return (x, y - 3.81, None), (x, y + 3.81, None)


def instance(lib_id, ref, value, fp, x, y, rot, pin_nums, dnp=False, ds='', hide_value=False, vpos=None):
    (rx, ry, rj), (vx, vy, vj) = ref_value_pos(lib_id, x, y)
    if vpos:
        vx, vy, vj = vpos[0], vpos[1], None
    hide_ref = ref.startswith('#')
    pins = ' '.join(f'(pin "{n}" (uuid "{uid()}"))' for n in pin_nums)
    return (f'(symbol (lib_id "{lib_id}") (at {f(x)} {f(y)} {rot}) (unit 1) '
            f'(exclude_from_sim no) (in_bom {"no" if hide_ref else "yes"}) (on_board {"no" if hide_ref else "yes"}) '
            f'(dnp {"yes" if dnp else "no"}) (uuid "{uid()}") '
            + prop('Reference', ref, rx, ry, hide=hide_ref, justify=rj) + ' '
            + prop('Value', value, vx, vy, hide=hide_value, justify=vj) + ' '
            + prop('Footprint', fp, x, y, hide=True) + ' '
            + prop('Datasheet', ds, x, y, hide=True) + ' '
            + f'{pins} (instances (project "{NAME}" (path "/{ROOT}" (reference "{ref}") (unit 1)))))')


def wire(x1, y1, x2, y2):
    return (f'(wire (pts (xy {f(x1)} {f(y1)}) (xy {f(x2)} {f(y2)})) '
            f'(stroke (width 0) (type default)) (uuid "{uid()}"))')


def label(name, x, y, ox, oy):
    # Текст всегда горизонтальный: влево от конца провода, если провод уходит влево, иначе вправо.
    if ox < 0:
        ang, j = 180, 'right bottom'
    else:
        ang, j = 0, 'left bottom'
    return (f'(label {q(name)} (at {f(x)} {f(y)} {ang}) '
            f'(effects (font (size 1.27 1.27)) (justify {j})) (uuid "{uid()}"))')


_pwr = [0]


def gnd_symbol(x, y, ox, oy):
    rot = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[(ox, oy)]
    _pwr[0] += 1
    # У боковых (повёрнутых) земель подпись «GND» прячем: она налезает на соседние выводы.
    return instance('power:GND', f'#PWR{_pwr[0]:02d}', 'GND', '', x, y, rot, ['1'],
                    vpos=(x + 3.81 * ox, y + 3.81 * oy), hide_value=ox != 0)


def main():
    libs = {lib: load_lib(os.path.join(KICAD_SYM, lib + '.kicad_sym'))
            for lib in ('Device', 'Connector_Generic', 'Regulator_Switching', 'Transistor_FET',
                        'Jumper', 'Mechanical', 'power', 'Interface_CAN_LIN')}
    used = sorted({p[1] for p in PARTS} | {'power:GND', 'power:PWR_FLAG'})
    lib_syms = {lid: flatten(libs, lid) for lid in used}

    items = []
    expected = {}  # net -> set of "REF.pin"
    for ref, lid, val, fp, x, y, rot, nets, dnp in PARTS:
        pins = sym_pins(lib_syms[lid])
        items.append(instance(lid, ref, val, fp, x, y, rot, sorted(pins), dnp=dnp))
        for num, (px, py, pa) in pins.items():
            wx, wy, ox, oy = pin_world(x, y, rot, px, py, pa)
            net = nets.get(num)
            if net is None:
                items.append(f'(no_connect (at {f(wx)} {f(wy)}) (uuid "{uid()}"))')
                continue
            expected.setdefault(net, set()).add(f'{ref}.{num}')
            ex, ey = wx + STUB * ox, wy + STUB * oy
            items.append(wire(wx, wy, ex, ey))
            items.append(gnd_symbol(ex, ey, ox, oy) if net == 'GND' else label(net, ex, ey, ox, oy))

    for i, (net, x, y) in enumerate(FLAGS, 1):
        items.append(instance('power:PWR_FLAG', f'#FLG{i:02d}', 'PWR_FLAG', '', x, y, 0, ['1']))
        ex, ey = x, y + STUB
        items.append(wire(x, y, ex, ey))
        items.append(gnd_symbol(ex, ey, 0, 1) if net == 'GND' else label(net, ex, ey, 0, 1))

    for x, y, size, text in TEXTS:
        items.append(f'(text {q(text)} (exclude_from_sim no) (at {f(x)} {f(y)} 0) '
                     f'(effects (font (size {f(size)} {f(size)})) (justify left bottom)) (uuid "{uid()}"))')

    sch = (f'(kicad_sch (version {VERSION}) (generator "eeschema") (generator_version "10.0") '
           f'(uuid "{ROOT}") (paper "A3")\n'
           f'(title_block (title "Сканер-адаптер OBD — плата v1") (date "2026-10-17") (rev "1") '
           f'(comment 1 "XIAO ESP32-C5, 2x CAN (SN65HVD230), защита питания + LM2596"))\n'
           '(lib_symbols\n' + '\n'.join(dump(s, 1) for s in lib_syms.values()) + '\n)\n'
           + '\n'.join(items) + '\n'
           '(sheet_instances (path "/" (page "1")))\n(embedded_fonts no)\n)\n')

    with open(os.path.join(PRJ, f'{NAME}.kicad_sch'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(sch)
    with open(os.path.join(PRJ, 'scaner.kicad_sym'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write(LOCAL_LIB)
    with open(os.path.join(PRJ, 'sym-lib-table'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('(sym_lib_table\n  (version 7)\n  (lib (name "scaner")(type "KiCad")'
                 '(uri "${KIPRJMOD}/scaner.kicad_sym")(options "")(descr "Символы проекта"))\n)\n')
    with open(os.path.join(PRJ, 'fp-lib-table'), 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('(fp_lib_table\n  (version 7)\n  (lib (name "scaner")(type "KiCad")'
                 '(uri "${KIPRJMOD}/scaner.pretty")(options "")(descr "Посадочные места проекта"))\n)\n')
    pro = os.path.join(PRJ, f'{NAME}.kicad_pro')
    if not os.path.exists(pro):
        with open(pro, 'w', encoding='utf-8') as fh:
            json.dump({'meta': {'filename': f'{NAME}.kicad_pro', 'version': 3}}, fh, indent=2)
    write_xiao_footprint()
    with open(os.path.join(HERE, 'expected_nets.json'), 'w', encoding='utf-8') as fh:
        json.dump({k: sorted(v) for k, v in sorted(expected.items())}, fh, ensure_ascii=False, indent=1)
    print(f'ok: {len(PARTS)} деталей, {len(expected)} цепей')


def write_xiao_footprint():
    """Две панельки 1x7, шаг 2,54, ряды через 15,24 мм.
    Пады 1-7 — левый ряд сверху вниз (D0..D6), 8-14 — правый ряд снизу вверх (D7..5V).
    USB-разъём XIAO — сверху. Проверить по живой плате!"""
    pads = []
    for i in range(7):
        pads.append((str(i + 1), 0.0, 2.54 * i))
        pads.append((str(8 + i), 15.24, 2.54 * (6 - i)))
    lines = [
        '(footprint "XIAO_ESP32C5_Socket"',
        '  (version 20241229) (generator "scaner_gen") (layer "F.Cu")',
        '  (descr "Seeed XIAO ESP32-C5 на двух панельках 1x7, шаг 2,54, ряды через 15,24 мм. Проверить по живой плате!")',
        '  (tags "XIAO ESP32C5 socket")',
        f'  (property "Reference" "REF**" (at 7.62 -5 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))',
        f'  (property "Value" "XIAO_ESP32C5_Socket" (at 7.62 19.5 0) (layer "F.Fab") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))',
        '  (attr through_hole)',
        f'  (fp_rect (start -1.27 -2.88) (end 16.51 18.12) (stroke (width 0.12) (type solid)) (fill no) (layer "F.SilkS") (uuid "{uid()}"))',
        f'  (fp_rect (start -1.52 -3.13) (end 16.76 18.37) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{uid()}"))',
        f'  (fp_text user "USB" (at 7.62 -1.6 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))',
    ]
    for num, x, y in pads:
        shape = 'rect' if num == '1' else 'circle'
        lines.append(f'  (pad "{num}" thru_hole {shape} (at {f(x)} {f(y)}) (size 1.7 1.7) (drill 1) '
                     f'(layers "*.Cu" "*.Mask") (uuid "{uid()}"))')
    lines.append(')')
    with open(os.path.join(PRJ, 'scaner.pretty', 'XIAO_ESP32C5_Socket.kicad_mod'), 'w',
              encoding='utf-8', newline='\n') as fh:
        fh.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
