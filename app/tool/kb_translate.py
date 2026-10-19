#!/usr/bin/env python3
"""Перевод базы знаний на русский пачками.

  python tool/build_kb.py              # собрать базу; непереведённое → tool/.cache/untranslated.txt
  python tool/kb_translate.py export   # разложить по пачкам в tool/.cache/tr/:
                                       #   en_001.txt …  строки целиком (номер<TAB>раздел<TAB>текст)
                                       #   en_s001.txt … узлы общих кодов SAE (номер<TAB>узел), см. sae_ru.py
  # перевести: ru_001.txt / ru_s001.txt …  (номер<TAB>перевод), по строке на номер
  python tool/kb_translate.py merge    # влить в tool/kb_ru.json: text (строки) и sae_parts (узлы)
  python tool/build_kb.py              # пересобрать с переводом
"""
import glob
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '.cache', 'tr')
RU = os.path.join(HERE, 'kb_ru.json')
BATCH = 300

sys.path.insert(0, HERE)
import sae_ru  # noqa: E402


def _write(prefix, rows):
    """rows: [(номер, раздел или None, текст)] → пачки prefix_001.txt …"""
    for f in glob.glob(os.path.join(TR, f'{prefix}_*.txt')):
        os.remove(f)
    for i in range(0, len(rows), BATCH):
        with open(os.path.join(TR, f'{prefix}_{i // BATCH + 1:03d}.txt'), 'w', encoding='utf-8', newline='\n') as f:
            for n, cat, text in rows[i:i + BATCH]:
                f.write(f'{n}\t{cat}\t{text}\n' if cat else f'{n}\t{text}\n')
    return (len(rows) + BATCH - 1) // BATCH


def export():
    src = os.path.join(HERE, '.cache', 'untranslated.txt')
    rows = [line.rstrip('\n').split('\t', 2) for line in open(src, encoding='utf-8') if line.strip()]
    kb_ru = json.load(open(RU, encoding='utf-8'))
    faults = sorted(kb_ru.get('sae_faults', {}), key=len, reverse=True)
    parts = kb_ru.get('sae_parts', {})
    os.makedirs(TR, exist_ok=True)
    whole, stems = [], Counter()
    for cat, _, text in rows:
        if cat == 'dtc_sae':
            pre = next((p for p, _ in sae_ru.PREFIXES if text.startswith(p)), None)
            if pre:
                rest = text[len(pre):]
                m = re.fullmatch(r'(.+?) ([A-J]|\d{1,2}|"[A-Z]")', rest)
                stem = m.group(1) if m else rest
            else:
                s = sae_ru.split(text, faults)
                stem = s[0] if s else None
            if stem is not None and stem not in parts:
                stems[stem] += 1
                continue
            if stem is not None:
                continue            # узел есть, а фраза не собралась — значит, вид неисправности не в словаре
        whole.append((cat, text))
    nw = _write('en', [(i + 1, c, t) for i, (c, t) in enumerate(whole)])
    ns = _write('en_s', [(i + 1, None, s) for i, (s, _) in enumerate(stems.most_common())])
    print(f'{len(whole)} строк ({nw} пачек en_*), {len(stems)} узлов SAE ({ns} пачек en_s_*) в {TR}')


def _pairs(en_glob, ru_glob, has_cat):
    en = {}
    for f in glob.glob(os.path.join(TR, en_glob)):
        for line in open(f, encoding='utf-8'):
            p = line.rstrip('\n').split('\t', 2 if has_cat else 1)
            en[p[0]] = p[-1]
    out, bad = {}, []
    for f in sorted(glob.glob(os.path.join(TR, ru_glob))):
        for line in open(f, encoding='utf-8'):
            line = line.rstrip('\n')
            if not line.strip():
                continue
            n, _, ru = line.partition('\t')
            if n not in en or not ru.strip():
                bad.append(f'{os.path.basename(f)}: {line[:60]}')
                continue
            out[en[n]] = ru.strip()
    return out, bad


def merge():
    kb_ru = json.load(open(RU, encoding='utf-8'))
    text, bad1 = _pairs('en_[0-9]*.txt', 'ru_[0-9]*.txt', True)
    parts, bad2 = _pairs('en_s_*.txt', 'ru_s_*.txt', False)
    kb_ru.setdefault('text', {}).update(text)
    kb_ru.setdefault('sae_parts', {}).update(parts)
    with open(RU, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(kb_ru, f, ensure_ascii=False, indent=2)
        f.write('\n')
    bad = bad1 + bad2
    print(f'строк {len(text)}, узлов SAE {len(parts)}; всего text {len(kb_ru["text"])}, sae_parts {len(kb_ru["sae_parts"])}'
          + (f'; не разобрал {len(bad)}:\n  ' + '\n  '.join(bad[:20]) if bad else ''))


if __name__ == '__main__':
    {'export': export, 'merge': merge}.get(sys.argv[1] if len(sys.argv) > 1 else '', lambda: print(__doc__))()
