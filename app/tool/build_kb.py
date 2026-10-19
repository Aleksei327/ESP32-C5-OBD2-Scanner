#!/usr/bin/env python3
"""Собирает базу знаний приложения (assets/kb/) из открытых источников.

- PSA-RE (https://github.com/prototux/PSA-RE, Apache-2.0) — электроника PSA: какие блоки
  стоят на машине, их адреса и протоколы, записи данных, тексты ошибок. Отсюда всё,
  что относится к Citroën C3 II (код A51, файл cars/A5.yml) → c3_ii.json.
- OBD Codes List (https://obdcodeslist.com/code-data.html, через github.com/tekseport/obd2-codes):
  общие коды SAE J2012 — расшифровка любого кода, которого нет в таблице блока → c3_ii.json.
- ludwig-v/arduino-psa-diag (GPL-3.0) — тексты ошибок для блоков, у которых их нет в PSA-RE
  (прежде всего BSI). Под GPL, поэтому отдельным файлом со своей лицензией → c3_ii_dtc_gpl.json.

Русские тексты — из tool/kb_ru.json (английский текст → русский).

  python tool/build_kb.py            # из каталога app/

Версии источников закреплены: архивы скачиваются один раз в tool/.cache/.
Только чтение: процедуры, управление исполнителями и запись в базу не попадают.
Нужен PyYAML (python -m pip install pyyaml).
"""
import csv
import io
import json
import os
import posixpath
import re as regex
import sys
import tarfile
import urllib.request
from collections import Counter

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sae_ru  # noqa: E402  (общие коды SAE: перевод по частям)

PSA_RE_COMMIT = '67f7581e7622410efdbb29c7eda3b86982b9b450'
PSA_RE_URL = 'https://github.com/prototux/PSA-RE'
LUDWIG_COMMIT = 'c1409e60798f66bb63149505826170b5eb3c163f'
LUDWIG_URL = 'https://github.com/ludwig-v/arduino-psa-diag'
SAE_COMMIT = 'ddadc77e443ebd39182d3a89e8ed5ccd3b6f59b4'
SAE_URL = 'https://obdcodeslist.com/code-data.html'   # так просит указывать источник их лицензия
CAR_FILE = 'A5'          # cars/A5.yml: C3 II, DS3, C3 Picasso
CAR_CODE = 'A51'         # сам C3 II

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.cache')
OUT = os.path.join(HERE, '..', 'assets', 'kb', 'c3_ii.json')
RU = os.path.join(HERE, 'kb_ru.json')
LICENCE_OUT = os.path.join(HERE, '..', 'assets', 'kb', 'PSA-RE-LICENCE.txt')
GPL_OUT = os.path.join(HERE, '..', 'assets', 'kb', 'c3_ii_dtc_gpl.json')
GPL_LICENCE_OUT = os.path.join(HERE, '..', 'assets', 'kb', 'GPL-3.0.txt')

# какие записи данных берём: живые данные, идентификация, настройки (только показать)
KINDS = ('live', 'identification', 'config')

# значок блока в приложении
ICONS = {'BSI': 'bsi', 'CMM': 'engine', 'BVA': 'gearbox', 'ABS': 'abs', 'RBG': 'airbag',
         'CMB': 'cluster', 'CLIM_AV': 'climate', 'DAE': 'steering', 'RAD': 'radio',
         'BTEL': 'radio', 'AAS': 'parking', 'ALARM': 'alarm', 'BECB': 'power'}


class PsaRe:
    """Нужные файлы PSA-RE прямо из архива (без распаковки), со ссылками-симлинками.
    Архив читается один раз подряд: прыгать по .tar.gz — это каждый раз распаковка с начала."""

    def __init__(self, path, prefixes):
        self.data, self.links = {}, {}
        with tarfile.open(path, 'r:gz') as tar:
            for m in tar:
                name = m.name.split('/', 1)[1] if '/' in m.name else ''
                if not name.startswith(prefixes):
                    continue
                if m.issym():
                    self.links[name] = m.linkname
                elif m.isfile():
                    self.data[name] = tar.extractfile(m).read()

    def _real(self, path):
        for _ in range(8):
            if path not in self.links:
                return path
            path = posixpath.normpath(posixpath.join(posixpath.dirname(path), self.links[path]))
        return path

    def has(self, path):
        return self._real(path) in self.data

    def yaml(self, path):
        loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)   # libyaml в разы быстрее
        return yaml.load(self.data[self._real(path)].decode('utf-8'), Loader=loader) or {}

    def ls(self, prefix):
        return sorted(p for p in list(self.data) + list(self.links) if p.startswith(prefix))


def fetch(repo, commit, name):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'{name}-{commit[:12]}.tar.gz')
    if not os.path.exists(path):
        url = f'https://codeload.github.com/{repo}/tar.gz/{commit}'
        print('скачиваю', url)
        urllib.request.urlretrieve(url, path + '.part')
        os.replace(path + '.part', path)
    return path


def tar_files(path, wanted):
    """{путь внутри репозитория: байты} для файлов, чьи пути проходят wanted(path)."""
    out = {}
    with tarfile.open(path, 'r:gz') as tar:
        for m in tar:
            name = m.name.split('/', 1)[1] if '/' in m.name else ''
            if m.isfile() and wanted(name):
                out[name] = tar.extractfile(m).read()
    return out


def raw_to_code(h):
    """'F534' (два байта, как их шлёт блок) → 'U3534' (SAE J2012)."""
    v = int(h, 16)
    return f'{"PCBU"[v >> 14]}{v & 0x3FFF:04X}'


def ludwig_dtcs(path):
    """Таблицы ошибок ludwig-v: {МОДЕЛЬ: {код: текст}}."""
    out = {}
    for name, data in tar_files(path, lambda n: n.startswith('dtc/') and n.endswith('.md')).items():
        rows = {}
        for code, text in regex.findall(r'^\|\s*([0-9A-Za-z]{4,5})\s*\|\s*(.+?)\s*\|\s*$', data.decode('utf-8', 'replace'), regex.M):
            code = code.upper()
            if regex.fullmatch(r'[0-9A-F]{4}', code):
                code = raw_to_code(code)
            elif not regex.fullmatch(r'[PCBU][0-9A-F]{4}', code):
                continue
            rows.setdefault(code, text.strip())
        out[name[4:-3].upper()] = rows
    return out


def is_sae_code(c):
    """Диапазоны, которые определяет сам SAE J2012: P0, P2, P34-P39, B0, C0, U0.
    В остальных коды у каждого производителя свои (у PSA там ошибки BSI) — как в приложении."""
    return len(c) == 5 and (c[1] == '0' or (c[0] == 'P' and (c[1] == '2' or (c[1] == '3' and c[2] in '456789'))))


def sae_dtcs(path):
    """Общие коды SAE J2012: {код: описание}."""
    data = tar_files(path, lambda n: n == 'obd2-codes.csv')['obd2-codes.csv'].decode('utf-8')
    return {r['code'].strip(): r['description'].strip() for r in csv.DictReader(io.StringIO(data)) if r.get('code')}


class Texts:
    """Тексты en + ru. Русский берётся из kb_ru.json по английскому тексту: точно,
    потом без учёта регистра, потом по шаблонам («Data record 0xC0 (19 values)»).
    Что не нашлось — копится по разделам (cat) для списка «перевести»."""

    PATTERNS = [
        (r'Data record 0x([0-9A-F]+) \((\d+) values?\)', r'Запись 0x\1 (\2 знач.)'),
        (r'Data record 0x([0-9A-F]+)', r'Запись 0x\1'),
        (r'Reset 0x([0-9A-F]+)', r'Сброс 0x\1'),
        (r'(.+) \(([A-Za-z0-9_ .-]+)\)', None),   # «Engine control unit (V46)»: переводим часть до скобок
    ]

    def __init__(self, ru):
        self.ru = ru.get('text', {})
        self.lower = {k.lower(): v for k, v in self.ru.items()}
        self.keep = set(ru.get('keep', []))
        self.sae_parts = ru.get('sae_parts', {})
        self.sae_faults = ru.get('sae_faults', {})
        self.missing = {}

    def lookup(self, en):
        if en in self.ru:
            return self.ru[en]
        if en.lower() in self.lower:
            return self.lower[en.lower()]
        if en in self.keep or not regex.search(r'[A-Za-z]{2}', en):
            return en                  # коды и числа — как есть
        for pat, rep in self.PATTERNS:
            m = regex.fullmatch(pat, en)
            if m and rep:
                return m.expand(rep)
            if m and rep is None:
                head = self.lookup(m.group(1))
                if head is not None:
                    return f'{head} ({m.group(2)})'
        return None

    def __call__(self, ml, fallback=None, cat='other'):
        en = ml.get('en') if isinstance(ml, dict) else (ml or None)
        en = (en or fallback or '').strip()
        if not en:
            return None
        out = {'en': en}
        ru = self.lookup(en)
        if ru is None and cat == 'dtc_sae':
            ru = sae_ru.compose(en, self.sae_parts, self.sae_faults)
        if ru is not None:
            if ru != en:
                out['ru'] = ru
        else:
            self.missing.setdefault(cat, Counter())[en] += 1
        return out


def hexid(b):
    return ''.join(f'{x:02X}' for x in b)


def match(patterns, variant):
    """Подходит ли вариант ПО под список из PSA-RE ('A51_*' — все варианты с этим началом)."""
    return any(variant.startswith(p[:-1]) if p.endswith('*') else variant == p for p in patterns)


def socket_addr(ecu):
    """Адрес блока со стороны диагностического разъёма: 11-битный, без указания шины."""
    for a in ecu.get('addressing', []):
        if a.get('transport') == 'can-tp' and 'bus' not in a and a.get('request_id', 0) < 0x800:
            return a['request_id'], a['response_id'], a.get('protocol')
    for a in ecu.get('addressing', []):
        if a.get('transport') == 'can-tp' and a.get('request_id', 0) < 0x800:
            return a['request_id'], a['response_id'], a.get('protocol')
    return None


def param(key, p, tx):
    out = {'key': key, 'bits': p['bits'], 'type': p.get('type', 'uint')}
    name = tx(p.get('comment') or p.get('display_name') or {}, key.replace('_', ' ').capitalize(), cat='param')
    out['name'] = name
    for src, dst in (('factor', 'factor'), ('offset', 'offset'), ('units', 'units')):
        if p.get(src) not in (None, '', 1 if src == 'factor' else None, 0 if src == 'offset' else None):
            out[dst] = p[src]
    if p.get('byte_order') == 'little':
        out['le'] = True
    vals = p.get('values')
    if isinstance(vals, dict) and vals:
        out['values'] = {str(int(k)): tx(v, cat='value') for k, v in vals.items() if tx(v, cat='value')}
    return out


def params(ps, tx):
    return [param(k, v, tx) for k, v in (ps or {}).items() if isinstance(v, dict) and v.get('bits')]


def record(doc, sid, ident, car_variants, tx):
    """Одна запись данных (LID для KWP, DID для UDS). None — не берём."""
    if doc.get('kind') not in KINDS or doc.get('mapped') or not doc.get('params'):
        return None
    pats = doc.get('variants') or []
    layouts = []
    if not pats or any(match(pats, v) for v in car_variants):
        layouts.append((pats, doc.get('params')))
    for alt in doc.get('alternatives') or []:
        ap = alt.get('variants') or []
        if alt.get('params') and (not ap or any(match(ap, v) for v in car_variants)):
            layouts.append((ap, alt['params']))
    if not layouts:
        return None
    sid = doc.get('service') or sid
    rec = {'req': hexid([sid] + ident), 'kind': doc['kind']}
    name = tx(doc.get('display_name') or {}, doc.get('name'), cat='record')
    if name:
        rec['name'] = name
    if doc.get('length'):
        rec['len'] = doc['length']
    pats0, ps0 = layouts[0]
    if pats0:
        rec['variants'] = pats0
    rec['params'] = params(ps0, tx)
    if len(layouts) > 1:
        rec['alts'] = [{'variants': p, 'params': params(ps, tx)} for p, ps in layouts[1:]]
    return rec


def model_json(re, base, name, car_variant_ids, tx):
    e = re.yaml(base + 'ecu.yml')
    addr = socket_addr(e)
    protos = []
    for p in ([addr[2]] if addr else []) + list(e.get('protocols') or []):
        q = {'KWP-PSA2000': 'kwp', 'UDS': 'uds'}.get(p)
        if q and q not in protos:
            protos.append(q)
    if not protos:
        return None, None
    # в PSA-RE у части блоков в адресе стоит UDS, а все команды — KWP (21 xx, 81...):
    # главный протокол — тот, на котором блок называет себя (команда опознания)
    ident_req = ((e.get('identification') or {}).get('request') or '').replace(' ', '').upper()
    first = 'kwp' if ident_req[:2] in ('21', '1A') else 'uds' if ident_req[:2] == '22' else None
    if first in protos:
        protos.remove(first)
        protos.insert(0, first)
    m = {'model': name}
    dn = tx(e.get('display_name') or {}, cat='model')
    if dn:
        m['name'] = dn
    m['proto'] = protos
    if 'kwp' in protos:
        sess = e.get('sessions') or {}
        services = e.get('services') or []
        # блоки салона (через BSI) открывают сеанс 10 C0, блоки шины IS — 81
        m['open'] = '10C0' if 0xC0 in sess else ('81' if 0x81 in services else None)
    ident = e.get('identification') or {}
    if ident.get('request'):
        m['ident'] = {'req': ident['request'].replace(' ', ''), 'part': ident.get('part_number')}
    variants = e.get('variants') or {}
    parts = {}
    for vid, v in variants.items():
        for part in v.get('parts') or []:
            parts.setdefault(str(part), str(vid))
    if parts:
        m['parts'] = parts
    mine = [str(v) for v, d in variants.items() if CAR_FILE in (d.get('cars') or []) or str(v).startswith(CAR_CODE)]
    car_variant_ids.update(mine)
    check = mine or [f'{CAR_CODE}_']   # нет вариантов для машины — сравниваем по коду машины
    recs = []
    for p in re.ls(base + 'lids/') + re.ls(base + 'dids/'):
        doc = re.yaml(p)
        if '/lids/' in p:
            lid = doc.get('lid')
            if lid is None:
                continue
            r = record(doc, 0x21, [lid], check, tx)
        else:
            did = doc.get('did')
            if did is None:
                continue
            r = record(doc, 0x22, [did >> 8, did & 0xFF], check, tx)
        if r:
            recs.append(r)
    if recs:
        m['records'] = recs
    if re.has(base + 'dtcs.yml'):
        d = re.yaml(base + 'dtcs.yml')
        dtc = {}
        for code, v in d.items():
            if code == 'failure_types' or not isinstance(v, dict):
                continue
            t = tx(v.get('display_name') or {}, cat='dtc')
            if t:
                dtc[str(code)] = t
        if dtc:
            m['dtc'] = dtc
    return m, addr


def main():
    re = PsaRe(fetch('prototux/PSA-RE', PSA_RE_COMMIT, 'psa-re'), ('LICENCE', 'architectures.yml', 'cars/', 'nodes/', 'diag/'))
    # Apache-2.0: текст лицензии едет вместе с данными (приложение показывает его в «Лицензиях»)
    with open(LICENCE_OUT, 'wb') as f:
        f.write(re.data['LICENCE'])
    ru = json.load(open(RU, encoding='utf-8')) if os.path.exists(RU) else {}
    tx = Texts(ru)
    car = re.yaml(f'cars/{CAR_FILE}.yml')
    ver = car['versions']['all']
    arch, variant = ver['architecture'].split('.')
    archs = re.yaml('architectures.yml')
    chain = [f'{arch}.{variant}']
    while archs[arch][variant].get('parent'):
        variant = archs[arch][variant]['parent']
        chain.append(f'{arch}.{variant}')
    node_names = {}
    for a in reversed(chain):
        if re.has(f'nodes/{a}.yml'):
            node_names.update(re.yaml(f'nodes/{a}.yml'))

    order = []
    for _, ns in ver['nodes'].items():
        order += [n for n in ns if n not in order]
    optional = set(ver.get('optional_nodes') or [])
    ecus, seen_addr = [], {}
    for node in order:
        groups = {}
        for mdl in (ver.get('ecu_models') or {}).get(node, [None]):
            base = None
            for a in chain:
                d = f'diag/{a}/{node}/' + (f'{mdl}/' if mdl else '')
                if re.has(d + 'ecu.yml'):
                    base = d
                    break
            if base is None:
                continue
            ids = set()
            m, addr = model_json(re, base, mdl or node, ids, tx)
            if not m or not addr:
                continue
            groups.setdefault((addr[0], addr[1]), []).append(m)
        for (rq, rs), models in groups.items():
            if (rq, rs) in seen_addr:
                # BSM, BSR отвечают через тот же адрес, что и BSI — это его «половинки»
                print(f'  {node}: адрес {rq:X} уже занят {seen_addr[(rq, rs)]}, пропускаю')
                continue
            seen_addr[(rq, rs)] = node
            nn = node_names.get(node, {}).get('name') or {}
            name = {'en': nn.get('en') or node}
            ru_name = (ru.get('nodes') or {}).get(node) or nn.get('ru')
            if ru_name:
                name['ru'] = ru_name
            en_short = (ru.get('nodes_en') or {}).get(node)
            if en_short:
                name['en'] = en_short
            e = {'node': node, 'name': name, 'tx': f'{rq:X}', 'rx': f'{rs:X}'}
            if node in ICONS:
                e['icon'] = ICONS[node]
            if node in optional:
                e['optional'] = True
            e['models'] = models
            ecus.append(e)

    # ошибки, которых нет в PSA-RE: тексты ludwig-v (GPL-3.0) — отдельным файлом
    lv_path = fetch('ludwig-v/arduino-psa-diag', LUDWIG_COMMIT, 'ludwig-v')
    lv = ludwig_dtcs(lv_path)
    gpl, added = {}, 0
    for e in ecus:
        for m in e['models']:
            mine = m.get('dtc', {})
            extra = {c: tx(t, cat='dtc_gpl') for c, t in lv.get(m['model'].upper(), {}).items()
                     if c not in mine and c.split('-')[0] not in mine}
            if extra:
                gpl[m['model']] = extra
                added += len(extra)
    with open(GPL_OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump({'source': {'name': 'ludwig-v/arduino-psa-diag', 'url': LUDWIG_URL, 'commit': LUDWIG_COMMIT,
                              'license': 'GPL-3.0'}, 'models': gpl}, f, ensure_ascii=False, separators=(',', ':'))
    with open(GPL_LICENCE_OUT, 'wb') as f:
        f.write(tar_files(lv_path, lambda n: n == 'LICENSE')['LICENSE'])

    # общие коды SAE J2012 — если у блока своего текста нет
    sae = sae_dtcs(fetch('tekseport/obd2-codes', SAE_COMMIT, 'sae'))
    generic = {c: tx(t, cat='dtc_sae') for c, t in sorted(sae.items()) if is_sae_code(c)}

    kb = {
        'format': 2,
        'id': 'psa_a51',
        'title': 'Citroën C3 II (A51) · PSA AEE2004',
        'source': {'name': 'PSA-RE', 'url': PSA_RE_URL, 'commit': PSA_RE_COMMIT, 'license': 'Apache-2.0'},
        'sources': [
            {'name': 'PSA-RE', 'url': PSA_RE_URL, 'commit': PSA_RE_COMMIT, 'license': 'Apache-2.0', 'what': 'ECUs, data, fault codes'},
            {'name': 'OBD Codes List', 'url': SAE_URL, 'commit': SAE_COMMIT, 'license': 'attribution', 'what': 'generic SAE J2012 codes'},
            {'name': 'ludwig-v/arduino-psa-diag', 'url': LUDWIG_URL, 'commit': LUDWIG_COMMIT, 'license': 'GPL-3.0',
             'what': 'fault codes missing in PSA-RE (c3_ii_dtc_gpl.json)'},
        ],
        'diag_bus': 'B',
        'obd_bus': 'A',
        'bitrate': 500000,
        'ecus': ecus,
        'dtc_generic': generic,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(kb, f, ensure_ascii=False, separators=(',', ':'))
    # что ещё не переведено — по разделам, частые сверху
    seen, total = set(), 0
    with open(os.path.join(CACHE, 'untranslated.txt'), 'w', encoding='utf-8', newline='\n') as f:
        for cat in ('model', 'record', 'value', 'param', 'dtc', 'dtc_gpl', 'dtc_sae', 'other'):
            for t, n in (tx.missing.get(cat) or Counter()).most_common():
                if t not in seen:
                    seen.add(t)
                    total += 1
                    f.write(f'{cat}\t{n}\t{t}\n')
    nm = sum(len(e['models']) for e in ecus)
    nr = sum(len(m.get('records', [])) for e in ecus for m in e['models'])
    nd = sum(len(m.get('dtc', {})) for e in ecus for m in e['models'])
    by = ', '.join(f'{c} {len(v)}' for c, v in tx.missing.items())
    print(f'{len(ecus)} блоков, {nm} моделей, {nr} записей данных, {nd} ошибок + {added} из ludwig-v + '
          f'{len(generic)} общих SAE; {os.path.getsize(OUT) // 1024} КБ; без перевода {total} строк ({by})')


if __name__ == '__main__':
    sys.exit(main())
