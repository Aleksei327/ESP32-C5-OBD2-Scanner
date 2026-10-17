#!/usr/bin/env python3
"""Проверка схемы: ERC и сверка нетлиста из KiCad с задуманным (expected_nets.json).

Запуск (из папки hardware/scaner_v1):  py -3 tools/check_netlist.py
"""
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
PRJ = os.path.dirname(HERE)
CLI = r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe'
SCH = os.path.join(PRJ, 'scaner_v1.kicad_sch')
OUT = os.path.join(PRJ, 'build')


def run(args):
    r = subprocess.run([CLI] + args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode not in (0, 5):  # 5 = ERC нашёл нарушения
        print(r.stdout, r.stderr)
        sys.exit(f'kicad-cli завершился с кодом {r.returncode}')
    return r


def main():
    os.makedirs(OUT, exist_ok=True)
    net_xml = os.path.join(OUT, 'scaner_v1.xml')
    run(['sch', 'export', 'netlist', '--format', 'kicadxml', '-o', net_xml, SCH])
    root = ET.parse(net_xml).getroot()
    got = {}
    for net in root.iter('net'):
        nodes = {f"{n.get('ref')}.{n.get('pin')}" for n in net.iter('node') if not n.get('ref').startswith('#')}
        if nodes:
            got[net.get('name')] = nodes
    with open(os.path.join(HERE, 'expected_nets.json'), encoding='utf-8') as fh:
        expected = {k: set(v) for k, v in json.load(fh).items()}

    got_sets = {frozenset(v): k for k, v in got.items()}
    bad = 0
    for name, nodes in expected.items():
        if frozenset(nodes) in got_sets:
            continue
        bad += 1
        best = max(got.items(), key=lambda kv: len(kv[1] & nodes))
        print(f'РАСХОЖДЕНИЕ {name}: ждём {sorted(nodes)}\n   в KiCad {best[0]}: {sorted(best[1])}')
    extra = [k for k, v in got.items() if frozenset(v) not in {frozenset(n) for n in expected.values()} and len(v) > 1]
    for k in extra:
        print(f'ЛИШНЯЯ ЦЕПЬ {k}: {sorted(got[k])}')
    print(f'Нетлист: цепей в KiCad {len(got)}, задумано {len(expected)}, расхождений {bad + len(extra)}')

    erc_json = os.path.join(OUT, 'erc.json')
    run(['sch', 'erc', '--format', 'json', '--severity-all', '-o', erc_json, SCH])
    with open(erc_json, encoding='utf-8') as fh:
        erc = json.load(fh)
    viol = [v for sh in erc.get('sheets', []) for v in sh.get('violations', [])]
    by = {}
    for v in viol:
        by.setdefault((v.get('severity'), v.get('type')), []).append(v)
    print(f'ERC: нарушений {len(viol)}')
    for (sev, typ), vs in sorted(by.items()):
        print(f'  [{sev}] {typ}: {len(vs)}')
        for v in vs[:4]:
            items = '; '.join(i.get('description', '') for i in v.get('items', []))
            print(f'      {v.get("description")} -> {items}')
    return bad + len(extra)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(1 if main() else 0)
