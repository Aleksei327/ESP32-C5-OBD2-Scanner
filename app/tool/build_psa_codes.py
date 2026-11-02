#!/usr/bin/env python3
"""Коды неисправностей PSA для приложения — из заводского списка «STE Liste codes diagnostic».

Документ PSA (96.272.978.9A) помечен «ne peut être reproduit», поэтому ни он, ни тексты из него
в репозиторий не идут: файл assets/kb/psa_codes.json и переводы в tool/.cache/ — только локально
(.gitignore), приложение работает и без них.

    python tool/build_psa_codes.py <psa.pdf>          # собрать assets/kb/psa_codes.json
    python tool/build_psa_codes.py <psa.pdf> export   # непереведённое — пачками в tool/.cache/psa_tr/
    # перевести: ru_001.txt, en_001.txt … рядом с fr_ru_001.txt, fr_en_001.txt (номер<TAB>перевод)
    python tool/build_psa_codes.py <psa.pdf> merge    # влить переводы в tool/.cache/psa_tr.json

Переводы хранятся по французскому тексту: {текст: {ru, en}} — разбор PDF можно менять, готовые
переводы не теряются. У P-кодов название — английское по SAE: русский к нему берётся из общих
текстов SAE базы знаний (assets/kb/c3_ii.json), переводить надо только пояснения PSA.

Код PSA на KWP — два байта: первая шестнадцатеричная цифра — тип неисправности (7…F), остальные
три — номер (BSI 0x400–0x5FF, климат 0x700–0x7FF, датчик АКБ 0xFF0–0xFFE…). Номер без типа — 0.
"""
import glob
import json
import os
import re
import sys

import fitz   # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.cache')
TR = os.path.join(CACHE, 'psa_tr.json')
TR_DIR = os.path.join(CACHE, 'psa_tr')
OUT = os.path.join(HERE, '..', 'assets', 'kb', 'psa_codes.json')
KB = os.path.join(HERE, '..', 'assets', 'kb', 'c3_ii.json')
BATCH = 200

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
# Чей раздел номеров — где понятно (сокращения — PSA): русский, английский
SECTION_NAMES = {
    'AAS': ('парктроник', 'parking sensors'), 'AS': ('парктроник', 'parking sensors'),
    'ADDGO': ('присадка сажевого фильтра', 'DPF additive'), 'ADGO': ('присадка сажевого фильтра', 'DPF additive'),
    'ALARME': ('сигнализация', 'alarm'), 'BECB': ('датчик состояния АКБ', 'battery sensor'), 'BSI': ('BSI', 'BSI'),
    'BSM': ('блок моторного отсека', 'engine bay fuse box'), 'BTEL': ('мультимедиа', 'telematics'),
    'CDC': ('CD-чейнджер', 'CD changer'), 'CDPL': ('датчик дождя и света', 'rain and light sensor'),
    'CLIM': ('климат', 'climate'), 'CMB': ('щиток приборов', 'instrument cluster'),
    'COMMUNICATION': ('связь по сети', 'network communication'), 'COMMUN AUTRE': ('прочая связь', 'other communication'),
    'HDC': ('подрулевые переключатели', 'steering column switches'), 'HIFI': ('HiFi-усилитель', 'HiFi amplifier'),
    'KML': ('громкая связь / USB', 'hands-free / USB'), 'MAE': ('модуль автошколы', 'driving school module'),
    'RADIO': ('магнитола', 'radio'), 'RBG': ('подушки безопасности', 'airbags'), 'TO': ('люк', 'sunroof'),
    'LVEAP AVG': ('стеклоподъёмник передний левый', 'front left window'),
    'LVEAP AVD': ('стеклоподъёмник передний правый', 'front right window'),
    'LVEAP ARG': ('стеклоподъёмник задний левый', 'rear left window'),
    'LVEAP ARD': ('стеклоподъёмник задний правый', 'rear right window'),
}
# Шапка таблицы и заголовки разделов — не текст кода
NOISE = re.compile(r'^(CODE|SIGNIFICATION|A VERIFIER.*|CO, Pb alimentation\)|\d+(\.\d+)+|\. CODES .*)$')
TOL = 3.0   # текст в колонке начинается на долю пункта выше строки своего кода


def sections(pdf):
    """Разделы номеров по оглавлению: [(название, от, до)]."""
    doc = fitz.open(pdf)
    out = {}
    for pno in range(min(8, doc.page_count)):
        for m in SECTION.finditer(doc[pno].get_text()):
            out.setdefault(m.group(1).strip(), (m.group(2).upper(), m.group(3).upper()))
    return [(k, lo, hi) for k, (lo, hi) in sorted(out.items(), key=lambda x: x[1])]


def parse(pdf):
    """→ {код: (описание, что проверить)} в порядке документа.

    Строка текста принадлежит тому коду, чья строка таблицы начинается не ниже неё (с допуском
    [TOL]): так «проверить» не съезжает к соседнему коду. Код, который уже был, второй раз не берём.
    """
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
        rows = []                              # (y, запись или None — повтор)
        for y, x0, x1, t in lines:
            if x1 < 92 and CODE.match(t):
                e = None if t in codes else {'desc': [], 'check': []}
                if e is not None:
                    codes[t] = e
                rows.append((y, e))
        for y, x0, x1, t in lines:
            if (x1 < 92 and CODE.match(t)) or NOISE.match(t):
                continue
            owner = None
            for ry, e in rows:
                if ry > y + TOL:
                    break
                owner = e
            if owner is None:
                continue
            if x0 < 300:
                if t not in owner['desc']:     # у P-кодов название повторено второй строкой
                    owner['desc'].append(t)
            elif x0 > 380:
                owner['check'].append(t)
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


STANDARD = re.compile(r'^P(0|2|3[4-9])')   # смысл кода задаёт сам SAE J2012


def sae_ru(code, base, generic):
    """Русское название P-кода из общих текстов SAE, если у PSA тут английское название по SAE."""
    g = generic.get(code)
    if g and g.get('ru') and STANDARD.match(code) and is_english(base):
        return g['ru']
    return None


FRENCH = re.compile(r"[àâçéèêëîïôûùœ]|\b(de|du|des|la|le|les|et|ou|sur|pour|au|aux|en|par|défaut|capteur|"
                    r"circuit ouvert|tension|commande|moteur|vanne|sonde|entrée|sortie)\b", re.I)


def is_english(s):
    return not FRENCH.search(s)


def load_tr():
    """Переводы {французский текст: {ru, en}}; при первом запуске — из старых пронумерованных файлов."""
    if os.path.exists(TR):
        return json.load(open(TR, encoding='utf-8'))
    tr = {}

    def numbered(path):
        with open(path, encoding='utf-8') as f:
            return {int(a): b for a, b in (l.rstrip('\n').split('\t', 1) for l in f if '\t' in l)}

    for kind in ('desc', 'check'):
        fr_path, ru_path = (os.path.join(CACHE, f'psa_{lang}_{kind}.txt') for lang in ('fr', 'ru'))
        if os.path.exists(fr_path) and os.path.exists(ru_path):
            fr, ru = numbered(fr_path), numbered(ru_path)
            for i, t in ru.items():
                if i in fr:
                    tr.setdefault(fr[i], {})['ru'] = t
    return tr


def save_tr(tr):
    os.makedirs(CACHE, exist_ok=True)
    with open(TR, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(dict(sorted(tr.items())), f, ensure_ascii=False, indent=0)


def texts(codes, generic):
    """Что нужно перевести: {французский текст: нужные языки}."""
    need = {}
    for c, (d, ch) in codes.items():
        _, _, base = split(c, d)
        if c.startswith('P'):
            if sae_ru(c, base, generic):
                pass                           # название SAE: русский есть в базе знаний
            elif is_english(base):
                need.setdefault(base, set()).add('ru')
            else:
                need.setdefault(base, set()).update(('ru', 'en'))
        else:
            need.setdefault(base, set()).update(('ru', 'en'))
        if ch:
            need.setdefault(ch, set()).update(('ru', 'en'))
    return need


def export(codes, generic, tr):
    os.makedirs(TR_DIR, exist_ok=True)
    for f in glob.glob(os.path.join(TR_DIR, 'fr_*.txt')):
        os.remove(f)
    for lang in ('ru', 'en'):
        todo = sorted(t for t, langs in texts(codes, generic).items() if lang in langs and lang not in tr.get(t, {}))
        for i in range(0, len(todo), BATCH):
            with open(os.path.join(TR_DIR, f'fr_{lang}_{i // BATCH + 1:03d}.txt'), 'w', encoding='utf-8', newline='\n') as f:
                f.writelines(f'{i + n}\t{t}\n' for n, t in enumerate(todo[i:i + BATCH]))
        print(f'{lang}: {len(todo)} строк, {sum(map(len, todo))} знаков → {(len(todo) + BATCH - 1) // BATCH} пачек')


def merge(tr):
    added = 0
    for src in sorted(glob.glob(os.path.join(TR_DIR, 'fr_*_*.txt'))):
        lang, num = os.path.basename(src)[3:-4].split('_')
        done = os.path.join(TR_DIR, f'{lang}_{num}.txt')
        if not os.path.exists(done):
            continue
        fr = dict(l.rstrip('\n').split('\t', 1) for l in open(src, encoding='utf-8') if '\t' in l)
        for l in open(done, encoding='utf-8'):
            if '\t' in l:
                n, t = l.rstrip('\n').split('\t', 1)
                if n in fr and t.strip():
                    tr.setdefault(fr[n], {})[lang] = t.strip()
                    added += 1
    save_tr(tr)
    print(f'влито {added} переводов → {TR}')


def build(pdf, codes, generic, tr):
    out = {'source': 'PSA STE «Liste codes diagnostic» 96.272.978.9A (03/14) — локальная копия, не публикуется',
           'types': {k: {'fr': v[0], 'ru': v[1], 'en': v[2]} for k, v in TYPES.items()},
           'sections': [{'name': n, 'ru': SECTION_NAMES.get(n, (n, n))[0], 'en': SECTION_NAMES.get(n, (n, n))[1],
                         'lo': lo, 'hi': hi} for n, lo, hi in sections(pdf)],
           'unknown': {'ru': 'Нет описания в списке PSA: раздел «{s}», номер {n}',
                       'en': 'No description in the PSA list: section "{s}", number {n}'},
           'codes': {}}
    missing = {'ru': 0, 'en': 0}
    for c, (d, ch) in codes.items():
        _, _, base = split(c, d)
        e = {'fr': base}
        if any(f'({v[0]})' in base for v in TYPES.values()):
            e['typed'] = True                   # тип уже внутри текста — второй раз не дописывать
        ru = sae_ru(c, base, generic) if c.startswith('P') else None
        if ru:
            e['en'], e['ru'] = base, ru
        else:
            t = tr.get(base, {})
            if c.startswith('P') and is_english(base):
                e['en'] = base
            for lang in ('ru', 'en'):
                if lang in t:
                    e[lang] = t[lang]
                elif lang not in e:
                    missing[lang] += 1
        if ch:
            e['check'] = ch
            for lang in ('ru', 'en'):
                if lang in tr.get(ch, {}):
                    e[f'check_{lang}'] = tr[ch][lang]
        out['codes'][c] = e
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'{OUT}: {len(out["codes"])} кодов, без перевода: ru {missing["ru"]}, en {missing["en"]}')


def main():
    fitz.TOOLS.mupdf_display_errors(False)    # у файла битый хвост xref, текст читается
    pdf = sys.argv[1]
    cmd = sys.argv[2] if len(sys.argv) > 2 else 'build'
    codes = parse(pdf)
    generic = json.load(open(KB, encoding='utf-8')).get('dtc_generic', {})
    tr = load_tr()
    if not os.path.exists(TR):
        save_tr(tr)                           # перенесли старые переводы — дальше только этот файл
    if cmd == 'export':
        export(codes, generic, tr)
    elif cmd == 'merge':
        merge(tr)
    else:
        build(pdf, codes, generic, tr)


if __name__ == '__main__':
    main()
