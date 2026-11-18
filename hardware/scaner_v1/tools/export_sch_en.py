#!/usr/bin/env python3
"""Английская версия схемы: build/scaner_v1_en.pdf.

Берёт scaner_v1.kicad_sch, во временной копии заменяет русские надписи (заголовки, заметки, рамку)
на английские по словарю TR и выводит PDF через kicad-cli. Сама схема не меняется.
Если в схеме появилась надпись, которой нет в словаре, скрипт остановится и покажет её — допиши перевод в TR.

Запуск (из папки hardware/scaner_v1):  py -3 tools/export_sch_en.py
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
CLI = r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
SCH = 'scaner_v1.kicad_sch'
OUT = os.path.join(PRJ, 'build', 'scaner_v1_en.pdf')
COPY = ['scaner_v1.kicad_pro', 'sym-lib-table', 'fp-lib-table', 'scaner.kicad_sym']

TR = {
    '1. Вход, защита, замер напряжения АКБ': '1. Input, protection, battery voltage sense',
    '2. DC-DC LM2596S-ADJ -> 4,92 В': '2. DC-DC LM2596S-ADJ -> 4.92 V',
    '4. CAN: канал A — OBD 6/14, канал B — OBD 3/8 (Diag-on-CAN PSA)':
        '4. CAN: channel A — OBD 6/14, channel B — OBD 3/8 (PSA Diag-on-CAN)',
    'D2, D3 (strapping), D4, D6 (лог загрузки) не подключены: пятаков нет, ножки гнезда выкусить':
        'D2, D3 (strapping), D4, D6 (boot log) not connected: no pads, clip those header pins',
    'D8 1.5KE6.8CA — страховка: при пробое LM2596 зажимает линию 5V, сгорает F1':
        'D8 1.5KE6.8CA is insurance: if the LM2596 fails short, it clamps the 5V rail and F1 blows',
    'OBD питание': 'OBD power',
    'R1 и R9 — корпус 1206: на них бывают десятки вольт. VBAT_ADC: 12 В -> ~1,6 В на D0':
        'R1 and R9 are 1206: they can see tens of volts. VBAT_ADC: 12 V -> ~1.6 V at D0',
    'R7/R8 — терминаторы 120 Ом, ставим по замеру H–L на машине: ~60 Ом -> не паять, ~120 Ом -> паять. '
    'C3 II: 6–14 = 57 Ом (R7 не ставим), 3–8 = 128 Ом (R8 стоит)':
        'R7/R8: 120 Ω terminators, fitted by measuring H–L on the car: ~60 Ω -> leave out, ~120 Ω -> fit. '
        'C3 II: 6–14 = 57 Ω (R7 not fitted), 3–8 = 128 Ω (R8 fitted)',
    'Seeed Studio XIAO ESP32-C5 на панельках 2x7': 'Seeed Studio XIAO ESP32-C5 on 2x7 female headers',
    'U2/U3 — SN65HVD230, выпаянные с модулей Waveshare. Rs: 1 (подтяжка) = только слушать, '
    'передатчик выключен; прошивка опускает в 0':
        'U2/U3: SN65HVD230 desoldered from Waveshare modules. Rs = 1 (pull-up): listen only, driver off; '
        'the firmware pulls it to 0',
    'Uвых = 1,23 x (1 + R3/R4) = 4,92 В; после D7 ~4,6 В — ниже USB, обратно в ноутбук не пойдёт':
        'Vout = 1.23 x (1 + R3/R4) = 4.92 V; ~4.6 V after D7, below USB, so nothing flows back into a laptop',
    'XIAO ESP32-C5, 2x CAN (SN65HVD230), защита питания + LM2596':
        'XIAO ESP32-C5, 2x CAN (SN65HVD230), input protection + LM2596',
    'Повторитель Q1 ограничивает вход LM2596 ~26,5 В (IRFB4110 держит до 100 В)':
        'Source follower Q1 limits the LM2596 input to ~26.5 V (IRFB4110 is rated 100 V)',
    'Посадочное место XIAO — проверить по живой плате (ряды через 15,24 мм)':
        'XIAO footprint: check against the real module (rows 15.24 mm apart)',
    'Провода от выводов разъёма OBD: J1 1 = OBD16 (+12 В), 2 = OBD4, 3 = OBD5; '
    'J2 (у трансиверов) 1 = OBD14, 2 = OBD6, 3 = OBD8, 4 = OBD3':
        'Wires from the OBD connector pins: J1 1 = OBD16 (+12 V), 2 = OBD4, 3 = OBD5; '
        'J2 (by the transceivers) 1 = OBD14, 2 = OBD6, 3 = OBD8, 4 = OBD3',
    'Сканер-адаптер OBD — плата v1': 'OBD scanner adapter, board v1',
}


def main():
    with open(os.path.join(PRJ, SCH), encoding='utf-8') as f:
        s = f.read()
    for ru, en in TR.items():
        s = s.replace('"%s"' % ru, '"%s"' % en)
    left = sorted(set(re.findall(r'"([^"]*[А-Яа-яЁё][^"]*)"', s)))
    if left:
        print('Нет перевода в TR:')
        for t in left:
            print('  ' + t)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        for name in COPY:
            shutil.copy2(os.path.join(PRJ, name), tmp)
        with open(os.path.join(tmp, SCH), 'w', encoding='utf-8', newline='') as f:
            f.write(s)
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        r = subprocess.run([CLI, 'sch', 'export', 'pdf', '-o', OUT, SCH], cwd=tmp,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        if r.returncode != 0:
            print(r.stdout, r.stderr)
            sys.exit(f'kicad-cli завершился с кодом {r.returncode}')
    print('OK:', OUT)


if __name__ == '__main__':
    main()
