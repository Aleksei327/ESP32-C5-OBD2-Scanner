#!/usr/bin/env python3
"""Коды неисправностей PSA для приложения — из заводского списка «STE Liste codes diagnostic».

Документ PSA (96.272.978.9A) помечен «ne peut être reproduit», поэтому ни он, ни тексты из него
в репозиторий не идут: файл assets/kb/psa_codes.json и переводы в tool/.cache/ — только локально
(.gitignore), приложение работает и без них.

    python tool/build_psa_codes.py <psa.pdf> --dump   # пронумерованные тексты для перевода в tool/.cache/
    python tool/build_psa_codes.py <psa.pdf>          # собрать assets/kb/psa_codes.json

Переводы: tool/.cache/psa_ru_desc.txt и psa_ru_check.txt, строки «номер<TAB>перевод» —
номера из psa_fr_desc.txt / psa_fr_check.txt, которые пишет --dump.

Код PSA на KWP — два байта: первая шестнадцатеричная цифра — тип неисправности (7…F), остальные
три — номер (BSI 0x400–0x5FF, климат 0x700–0x7FF, датчик АКБ 0xFF0–0xFFE…). Номер без типа — 0.
P-коды двигателя записаны отдельно: название по SAE и пояснение PSA.
"""
import json
import os
import re
import sys

import fitz   # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.cache')
OUT = os.path.join(HERE, '..', 'assets', 'kb', 'psa_codes.json')

CODE = re.compile(r'^(P[0-9A-F]{4}|[0-9A-F]{3,4})$')
TYPES = {
    '7': ('Distant non caractérisé', 'удалённая, без уточнения', 'remote, unspecified'),
    '8': ('Absence de signal', 'нет сигнала', 'no signal'),
    '9': ('Cohérence, plausibilité', 'неправдоподобное значение', 'implausible value'),
    'A': ('Court-circuit au plus', 'замыкание на плюс', 'short to battery'),
    'B': ('Court-circuit à la masse', 'замыкание на массу', 'short to ground'),
    'C': ('Circuit ouvert', 'обрыв цепи', 'open circuit'),
    'D': ('Butée basse', 'ниже допустимого', 'below range'),
    'E': ('Butée haute', 'выше допустимого', 'above range'),
    'F': ('Non caractérisé', 'без уточнения', 'unspecified'),
}
SUFFIX = re.compile(r'\s*\((' + '|'.join(re.escape(v[0]) for v in TYPES.values()) + r')\)\s*$')
SECTION = re.compile(r'CODES\s+([A-Z][A-Z0-9 ]*?),\s*0[xX]([0-9A-F]{3})\s*à\s*0[xX]([0-9A-F]{3})\b')
# Чей раздел номеров — по-русски, где понятно (сокращения — PSA)
SECTION_RU = {
    'AAS': 'парктроник', 'AS': 'парктроник', 'ADDGO': 'присадка сажевого фильтра', 'ADGO': 'присадка сажевого фильтра',
    'ALARME': 'сигнализация', 'BECB': 'датчик состояния АКБ', 'BSI': 'BSI', 'BSM': 'блок моторного отсека',
    'BTEL': 'мультимедиа', 'CDC': 'CD-чейнджер', 'CDPL': 'датчик дождя и света', 'CLIM': 'климат',
    'CMB': 'щиток приборов', 'COMMUNICATION': 'связь по сети', 'COMMUN AUTRE': 'прочая связь',
    'HDC': 'подрулевые переключатели', 'HIFI': 'HiFi-усилитель', 'KML': 'громкая связь / USB',
    'MAE': 'модуль автошколы', 'RADIO': 'магнитола', 'RBG': 'подушки безопасности', 'TO': 'люк',
    'LVEAP AVG': 'стеклоподъёмник передний левый', 'LVEAP AVD': 'стеклоподъёмник передний правый',
    'LVEAP ARG': 'стеклоподъёмник задний левый', 'LVEAP ARD': 'стеклоподъёмник задний правый',
}


def sections(pdf):
    """Разделы номеров по оглавлению: [(название, от, до)]."""
    doc = fitz.open(pdf)
    out = {}
    for pno in range(min(8, doc.page_count)):
        for m in SECTION.finditer(doc[pno].get_text()):
            out.setdefault(m.group(1).strip(), (m.group(2).upper(), m.group(3).upper()))
    return [(k, lo, hi) for k, (lo, hi) in sorted(out.items(), key=lambda x: x[1])]


def parse(pdf):
    """→ {код: (описание, что проверить)} в порядке документа."""
    doc = fitz.open(pdf)
    codes = {}
    for pno in range(doc.page_count):
        lines = []
        for b in doc[pno].get_text('dict')['blocks']:
            for l in b.get('lines', []):
                t = ''.join(s['text'] for s in l['spans']).strip()
                x0, y0, x1, _ = l['bbox']
                if t and 50 < y0 < 760:        # без шапки и подвала страницы
                    lines.append((round(y0, 1), x0, x1, t))
        lines.sort()
        cur = None
        for _, x0, x1, t in lines:
            if x1 < 92 and CODE.match(t):
                cur = None if t in codes else {'desc': [], 'check': []}
                if cur is not None:
                    codes[t] = cur
                continue
            if cur is None or t in ('CODE', 'SIGNIFICATION'):
                continue
            if x0 < 300:
                if t not in cur['desc']:        # у P-кодов название повторено второй строкой
                    cur['desc'].append(t)
            elif x0 > 380:
                cur['check'].append(t)
    out = {}
    for c, e in codes.items():
        desc = re.sub(r'\s+', ' ', ' '.join(e['desc'])).strip()
        if desc and not desc.startswith('A VERIFIER'):
            out[c] = (desc, re.sub(r'\s+', ' ', ' '.join(e['check'])).strip())
    return out


def split(code, desc):
    """Код PSA → (номер из 3 цифр, тип или '', описание без типа). P-коды — как есть."""
    if code.startswith('P'):
        return code, '', desc
    if len(code) == 4:
        return code[1:], code[0], SUFFIX.sub('', desc)
    return code, '', desc


def numbered(path):
    with open(path, encoding='utf-8') as f:
        return {int(a): b for a, b in (l.rstrip('\n').split('\t', 1) for l in f if '\t' in l)}


def main():
    pdf = sys.argv[1]
    codes = parse(pdf)
    descs, checks = {}, {}
    for c, (d, ch) in codes.items():
        if not c.startswith('P'):
            descs.setdefault(split(c, d)[2], None)
            if ch:
                checks.setdefault(ch, None)
    descs, checks = sorted(descs), sorted(checks)
    os.makedirs(CACHE, exist_ok=True)
    if '--dump' in sys.argv:
        for name, items in (('psa_fr_desc.txt', descs), ('psa_fr_check.txt', checks)):
            with open(os.path.join(CACHE, name), 'w', encoding='utf-8') as f:
                f.writelines(f'{i}\t{x}\n' for i, x in enumerate(items))
        print(f'кодов {len(codes)}, описаний {len(descs)}, «проверить» {len(checks)} → {CACHE}')
        return
    ru = {}
    for fr_name, ru_name in (('psa_fr_desc.txt', 'psa_ru_desc.txt'), ('psa_fr_check.txt', 'psa_ru_check.txt')):
        fr, tr = numbered(os.path.join(CACHE, fr_name)), {}
        try:
            tr = numbered(os.path.join(CACHE, ru_name))
        except OSError:
            pass
        ru.update({fr[i]: t for i, t in tr.items() if i in fr})
    out = {'source': 'PSA STE «Liste codes diagnostic» 96.272.978.9A (03/14) — локальная копия, не публикуется',
           'types': {k: {'fr': v[0], 'ru': v[1], 'en': v[2]} for k, v in TYPES.items()},
           'sections': [{'name': n, 'ru': SECTION_RU.get(n, n), 'lo': lo, 'hi': hi} for n, lo, hi in sections(pdf)],
           'unknown': {'ru': 'Нет описания в списке PSA: раздел «{s}», номер {n}',
                       'en': 'No description in the PSA list: section "{s}", number {n}'},
           'codes': {}}
    missing = 0
    for c, (d, ch) in codes.items():
        _, t, base = split(c, d)
        e = {'fr': base}
        if any(f'({v[0]})' in base for v in TYPES.values()):
            e['typed'] = True                   # тип уже внутри текста — второй раз не дописывать
        if base in ru:
            e['ru'] = ru[base]
        elif not c.startswith('P'):
            missing += 1
        if ch:
            e['check'] = ch
            if ch in ru:
                e['check_ru'] = ru[ch]
        out['codes'][c] = e
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'{OUT}: {len(out["codes"])} кодов, без перевода {missing}')


if __name__ == '__main__':
    main()
