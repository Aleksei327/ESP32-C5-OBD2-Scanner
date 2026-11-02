"""Полный опрос машины через адаптер: все блоки из базы знаний, их ошибки и данные, плюс OBD-II.

    python remote/scan.py                      # через посредника (remote/relay.py)
    python remote/scan.py --url ws://192.168.4.1:81/ws
    python remote/scan.py --only BSI,CMM       # только эти блоки
    python remote/scan.py --no-obd             # без OBD-II на шине A

Только чтение: сеанс диагностики, чтение записей и ошибок. Сервисы, которые что-то меняют
в блоках (сброс ошибок, запись, тесты исполнительных механизмов…), отправить нельзя — их
отсекает send(). Результат — папка scans/<дата_время>/: scan.json (всё, с сырыми байтами)
и report.md (по-человечески). Папка scans/ в git не идёт: там VIN и номера деталей машины.

База знаний — та же, что у приложения: app/assets/kb/c3_ii.json (+ тексты ошибок GPL).
Разбор значений повторяет app/lib/kb/bits.dart и knowledge_base.dart.
"""
import argparse
import asyncio
import json
import os
import struct
import sys
import time

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KB_DIR = os.path.join(ROOT, 'app', 'assets', 'kb')
LANG = 'ru'

# Чтение: сеанс (10, 81), «я здесь» (3E), записи (21, 22, 1A), ошибки (17, 18, 19),
# OBD-II: текущие данные (01), ошибки (03, 07, 0A), сведения о машине (09)
READ_SIDS = {0x10, 0x81, 0x3E, 0x21, 0x22, 0x1A, 0x17, 0x18, 0x19, 0x01, 0x03, 0x07, 0x09, 0x0A}
KWP_IDLE = 2.0      # с, после простоя сеанс KWP открываем заново
PROBE_MS = 400
READ_MS = 1500


# ---------- база знаний ----------

def txt(m, lang=LANG):
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        return m.get(lang) or m.get('en') or ''
    return ''


def unhex(s):
    return bytes.fromhex(s)


class Bits:
    """`<байт>.<бит>[-<байт>.<бит>|n]`, байты с 1, биты 7..0 (как в PSA-RE)."""

    def __init__(self, s):
        def pos(x):
            b, bit = x.split('.')
            return (int(b) - 1) * 8 + (7 - int(bit))
        if '-' not in s:
            self.start = self.end = pos(s)
        else:
            a, b = s.split('-', 1)
            self.start, self.end = pos(a), (None if b == 'n' else pos(b))

    def last(self, n):
        return self.end if self.end is not None else n * 8 - 1

    def fits(self, p):
        return self.start < len(p) * 8 and self.start <= self.last(len(p)) < len(p) * 8

    def uint(self, p):
        v = 0
        for i in range(self.start, self.last(len(p)) + 1):
            v = v * 2 + ((p[i >> 3] >> (7 - (i & 7))) & 1)
        return v

    def sint(self, p):
        n = self.last(len(p)) - self.start + 1
        v = self.uint(p)
        return v - (1 << n) if v >= 1 << (n - 1) else v

    def bytes(self, p):
        return p[self.start >> 3:(self.last(len(p)) >> 3) + 1]


def bcd(b):
    return ''.join(f'{x:02X}' for x in b)


def ascii_(b):
    return ''.join(chr(c) for c in b if 0x20 <= c < 0x7F).strip()


def decode_param(prm, p):
    """→ (число или None, текст)."""
    bits = Bits(prm['bits'])
    t = prm.get('type', 'uint')
    if t == 'str':
        return None, ascii_(bits.bytes(p))
    if t == 'bcd':
        return None, bcd(bits.bytes(p))
    if t == 'bytes':
        return None, ' '.join(f'{x:02X}' for x in bits.bytes(p))
    factor, offset = prm.get('factor', 1), prm.get('offset', 0)
    if t == 'float':
        b = bits.bytes(p)
        v = struct.unpack('>f', bytes(b[:4]))[0] if len(b) >= 4 else float('nan')
        return v * factor + offset, None
    if prm.get('le'):
        raw = int.from_bytes(bytes(bits.bytes(p)), 'little')
    else:
        raw = bits.sint(p) if t == 'sint' else bits.uint(p)
    label = (prm.get('values') or {}).get(str(raw))
    if t in ('enum', 'bool'):
        return raw, txt(label) if label is not None else str(raw)
    v = raw * factor + offset
    return v, txt(label) if label is not None else None


def fmt_value(prm, num, text):
    if text is not None and num is None:
        return text
    if text is not None:
        return text
    f = abs(prm.get('factor', 1))
    dec = 0
    if f and not (f >= 1 and f == round(f)):
        for d in (1, 2, 3):
            s = f * 10 ** d
            if abs(s - round(s)) < 1e-6:
                dec = d
                break
        else:
            dec = 3
    u = prm.get('units', '')
    return f'{num:.{dec}f}' + (f' {u}' if u else '')


def match_variant(pats, v):
    return any(v.startswith(p[:-1]) if p.endswith('*') else v == p for p in pats)


def record_applies(r, variant):
    vs = r.get('variants') or []
    if variant is None or not vs or match_variant(vs, variant):
        return True
    return any(not a.get('variants') or match_variant(a['variants'], variant) for a in r.get('alts') or [])


def record_params(r, variant):
    vs = r.get('variants') or []
    if variant is None or not vs or match_variant(vs, variant):
        return r.get('params') or []
    for a in r.get('alts') or []:
        if not a.get('variants') or match_variant(a['variants'], variant):
            return a.get('params') or []
    return r.get('params') or []


def protos(ecu):
    n = {}
    for m in ecu['models']:
        ps = m.get('proto') or ['uds']
        for p in ps:
            n[p] = n.get(p, 0) + (2 if p == ps[0] else 1)
    return sorted(n, key=lambda p: -n[p])


def kwp_opens(ecu):
    n = {}
    for m in ecu['models']:
        if m.get('open'):
            n[m['open']] = n.get(m['open'], 0) + 1
    return sorted(n, key=lambda k: -n[k])


def is_sae(c):
    if len(c) != 5:
        return False
    d = c[1]
    return {'P': d == '0' or d == '2' or (d == '3' and c[2] in '456789'),
            'B': d == '0', 'C': d == '0', 'U': d == '0'}.get(c[0], False)


def dtc_code(raw):
    b = raw[0]
    return f"{'PCBU'[(b >> 6) & 3]}{(b >> 4) & 3}{b & 0xF:X}{raw[1]:02X}"


# ---------- связь с адаптером ----------

class Link:
    def __init__(self, ws):
        self.ws = ws
        self.n = 0
        self.log = []   # все запросы и ответы

    async def call(self, cmd, timeout=10, **kw):
        self.n += 1
        rid = self.n
        await self.ws.send(json.dumps({'id': rid, 'cmd': cmd, **kw}))
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return {'ok': False, 'err': 'no answer (relay)'}
            try:
                msg = json.loads(await asyncio.wait_for(self.ws.recv(), left))
            except asyncio.TimeoutError:
                return {'ok': False, 'err': 'no answer (relay)'}
            if msg.get('id') == rid:
                return msg
            if msg.get('err') == 'no_phone':
                raise ConnectionError('телефон отключился от посредника')

    async def send(self, bus, tx, rx, data, timeout_ms=READ_MS):
        """→ (ответ bytes | None, ошибка | None). Отказ блока (7F) — ответ, ошибка 'NRC xx'."""
        req = unhex(data)
        if req[0] not in READ_SIDS:
            raise ValueError(f'сервис {req[0]:02X} не чтение — не отправляю')
        r = await self.call('isotp.req', timeout=timeout_ms / 1000 + 8, bus=bus, tx=tx, rx=rx, data=data,
                            timeout_ms=timeout_ms)
        entry = {'bus': bus, 'tx': tx, 'rx': r.get('rx', rx), 'req': data}
        if not r.get('ok'):
            entry['err'] = r.get('err')
            self.log.append(entry)
            return None, r.get('err') or 'error'
        resp = unhex(r['data'])
        entry['resp'] = r['data']
        self.log.append(entry)
        if resp and resp[0] == (req[0] + 0x40) & 0xFF:
            return resp, None
        if len(resp) >= 3 and resp[0] == 0x7F:
            return resp, f'NRC {resp[2]:02X}'
        return resp, 'unexpected'


# ---------- блоки PSA по шине диагностики ----------

class Ecu:
    def __init__(self, link, bus, d):
        self.link, self.bus, self.d = link, bus, d
        self.tx, self.rx = d['tx'], d['rx']
        self.proto = None
        self.open = None
        self.last = 0.0

    async def probe(self):
        alive = False
        for p in protos(self.d):
            if p == 'kwp':
                for o in kwp_opens(self.d):
                    resp, err = await self.link.send(self.bus, self.tx, self.rx, o, PROBE_MS)
                    if resp is not None and err is None:
                        self.proto, self.open, self.last = 'kwp', o, time.monotonic()
                        return True
                    if resp is not None:
                        alive = True
                    elif not alive:
                        break
            else:
                resp, err = await self.link.send(self.bus, self.tx, self.rx, '3E00', PROBE_MS)
                if resp is not None:
                    self.proto = 'uds'
                    return True
        if alive:
            self.proto = 'kwp'
        return alive

    async def ask(self, data, timeout_ms=READ_MS):
        if self.proto == 'kwp' and self.open and time.monotonic() - self.last > KWP_IDLE:
            await self.link.send(self.bus, self.tx, self.rx, self.open, PROBE_MS)
        resp, err = await self.link.send(self.bus, self.tx, self.rx, data, timeout_ms)
        self.last = time.monotonic()
        return resp, err

    async def detect_model(self):
        """→ (модель, вариант ПО, номер детали)."""
        tried = {}
        for m in self.d['models']:
            ident = m.get('ident') or {}
            if not ident.get('req') or not ident.get('part'):
                continue
            if self.proto and self.proto not in (m.get('proto') or ['uds']):
                continue
            req = ident['req']
            if req not in tried:
                resp, err = await self.ask(req)
                tried[req] = resp[len(unhex(req)):] if resp is not None and err is None else None
            payload = tried[req]
            if payload is None:
                continue
            bits = Bits(ident['part'])
            if not bits.fits(payload):
                continue
            part = bcd(bits.bytes(payload))
            variant = (m.get('parts') or {}).get(part)
            if variant:
                return m, variant, part
        parts = [bcd(Bits(m['ident']['part']).bytes(p)) for m in self.d['models']
                 for r, p in tried.items() if p is not None and (m.get('ident') or {}).get('req') == r
                 and Bits(m['ident']['part']).fits(p)]
        part = parts[0] if parts else None
        cands = [m for m in self.d['models'] if not self.proto or self.proto in (m.get('proto') or ['uds'])]
        if len(cands) == 1:
            return cands[0], None, part
        return None, None, part

    async def read_dtcs(self):
        if self.proto == 'kwp':
            resp, err = await self.ask('17FF00')
            if err:
                return None, err
            out = []
            for i in range(2, len(resp) - 2, 3):
                raw, st = resp[i:i + 2], resp[i + 2]
                out.append({'code': dtc_code(raw), 'raw': raw.hex().upper(), 'status': f'{st:02X}',
                            'active': (st >> 5) & 3 == 3})
            return out, None
        resp, err = await self.ask('1902FF')
        if err:
            return None, err
        body = resp[3:]
        out = []
        for i in range(0, len(body) - 3, 4):
            raw, st = body[i:i + 3], body[i + 3]
            code = dtc_code(raw)
            out.append({'code': code, 'key': f'{code}-{raw[2]:02X}', 'raw': raw.hex().upper(),
                        'status': f'{st:02X}', 'active': bool(st & 1)})
        return out, None


def sae_p(ecu):
    """Блок пишет P-коды SAE (двигатель, коробка), а не коды PSA «тип + номер»."""
    return any(str(k).startswith('P') for m in ecu['models'] for k in (m.get('dtc') or {}))


def psa_text(psa, d, saep):
    """Текст по списку кодов PSA (app/assets/kb/psa_codes.json, только локально)."""
    codes = psa.get('codes') or {}
    raw = d['raw']
    if len(raw) != 4:
        return None
    if saep:
        e, t = codes.get(d['code']), None
    elif raw[0] == '0':
        e, t = codes.get(raw[1:]), None
    elif raw[0] in '789ABCDEF':
        e, t = codes.get(raw) or codes.get(raw[1:]), raw[0]
    else:
        return None
    if not e:
        n = int(raw[1:], 16)
        for s in [] if saep else psa.get('sections') or []:
            if int(s['lo'], 16) <= n <= int(s['hi'], 16):
                text = psa['unknown']['ru'].replace('{s}', s['ru']).replace('{n}', raw[1:])
                return text + (f" ({psa['types'][t]['ru']})" if t else '') + ' [список PSA]'
        return None
    text = e.get('ru') or e['fr']
    if t and not e.get('typed'):
        text += f" ({psa['types'][t]['ru']})"
    if e.get('check'):
        text += f"; проверить: {e.get('check_ru') or e['check']}"
    return text + ' [список PSA]'


def dtc_text(model, extra, generic, d, psa=None, saep=False):
    for key in (d.get('key'), d['code']):
        if not key or model is None:
            continue
        for src in (model.get('dtc') or {}, extra.get(model['model'], {})):
            if key in src:
                return txt(src[key])
    t = psa_text(psa or {}, d, saep)
    if t:
        return t
    if is_sae(d['code']) and d['code'] in generic:
        return txt(generic[d['code']]) + ' (общее описание SAE)'
    return None


# ---------- OBD-II на шине A ----------

def _pct(a):
    return a * 100 / 255


OBD_PIDS = {
    0x01: ('Состояние MIL и число ошибок', lambda d: f"MIL {'горит' if d[0] & 0x80 else 'не горит'}, ошибок {d[0] & 0x7F}"),
    0x03: ('Режим топливной системы', lambda d: {1: 'разомкнутый (прогрев)', 2: 'замкнутый (по лямбде)', 4: 'разомкнутый (нагрузка)',
                                                 8: 'разомкнутый (неисправность)', 16: 'замкнутый, неисправность датчика'}.get(d[0], f'{d[0]:02X}')),
    0x04: ('Нагрузка двигателя', lambda d: f'{_pct(d[0]):.1f} %'),
    0x05: ('Температура ОЖ', lambda d: f'{d[0] - 40} °C'),
    0x06: ('Краткосрочная коррекция топлива', lambda d: f'{(d[0] - 128) * 100 / 128:+.1f} %'),
    0x07: ('Долгосрочная коррекция топлива', lambda d: f'{(d[0] - 128) * 100 / 128:+.1f} %'),
    0x0B: ('Давление во впуске', lambda d: f'{d[0]} кПа'),
    0x0C: ('Обороты', lambda d: f'{(d[0] * 256 + d[1]) / 4:.0f} об/мин'),
    0x0D: ('Скорость', lambda d: f'{d[0]} км/ч'),
    0x0E: ('Угол опережения зажигания', lambda d: f'{d[0] / 2 - 64:.1f} °'),
    0x0F: ('Температура воздуха на впуске', lambda d: f'{d[0] - 40} °C'),
    0x10: ('Расход воздуха', lambda d: f'{(d[0] * 256 + d[1]) / 100:.2f} г/с'),
    0x11: ('Дроссель', lambda d: f'{_pct(d[0]):.1f} %'),
    0x13: ('Датчики кислорода', lambda d: f'{d[0]:08b}'),
    0x14: ('Лямбда 1 (до катализатора)', lambda d: f'{d[0] / 200:.3f} В, коррекция {(d[1] - 128) * 100 / 128:+.1f} %'),
    0x15: ('Лямбда 2 (после катализатора)', lambda d: f'{d[0] / 200:.3f} В'),
    0x1C: ('Стандарт OBD', lambda d: {1: 'OBD-II (CARB)', 2: 'OBD (EPA)', 3: 'OBD и OBD-II', 6: 'EOBD', 7: 'EOBD и OBD-II',
                                       9: 'EOBD, OBD и OBD II'}.get(d[0], str(d[0]))),
    0x1F: ('Время работы мотора', lambda d: f'{d[0] * 256 + d[1]} с'),
    0x21: ('Пробег с горящим MIL', lambda d: f'{d[0] * 256 + d[1]} км'),
    0x2E: ('Продувка адсорбера (команда)', lambda d: f'{_pct(d[0]):.1f} %'),
    0x2F: ('Уровень топлива', lambda d: f'{_pct(d[0]):.1f} %'),
    0x30: ('Прогревов после сброса ошибок', lambda d: f'{d[0]}'),
    0x31: ('Пробег после сброса ошибок', lambda d: f'{d[0] * 256 + d[1]} км'),
    0x33: ('Атмосферное давление', lambda d: f'{d[0]} кПа'),
    0x42: ('Напряжение блока', lambda d: f'{(d[0] * 256 + d[1]) / 1000:.2f} В'),
    0x43: ('Абсолютная нагрузка', lambda d: f'{(d[0] * 256 + d[1]) * 100 / 255:.1f} %'),
    0x44: ('Заданная лямбда', lambda d: f'{(d[0] * 256 + d[1]) * 2 / 65536:.3f}'),
    0x45: ('Относительное положение дросселя', lambda d: f'{_pct(d[0]):.1f} %'),
    0x46: ('Температура наружного воздуха', lambda d: f'{d[0] - 40} °C'),
    0x47: ('Дроссель B', lambda d: f'{_pct(d[0]):.1f} %'),
    0x49: ('Педаль газа D', lambda d: f'{_pct(d[0]):.1f} %'),
    0x4A: ('Педаль газа E', lambda d: f'{_pct(d[0]):.1f} %'),
    0x4C: ('Заданное положение дросселя', lambda d: f'{_pct(d[0]):.1f} %'),
    0x4D: ('Время с горящим MIL', lambda d: f'{d[0] * 256 + d[1]} мин'),
    0x4E: ('Время после сброса ошибок', lambda d: f'{d[0] * 256 + d[1]} мин'),
    0x51: ('Тип топлива', lambda d: {1: 'бензин', 4: 'дизель', 8: 'электро'}.get(d[0], str(d[0]))),
}


def obd_dtcs(resp):
    body = resp[1:]
    if len(body) % 2 == 1:      # CAN: первый байт — число кодов
        body = body[1:]
    return [dtc_code(body[i:i + 2]) for i in range(0, len(body) - 1, 2) if body[i] or body[i + 1]]


async def scan_obd(link):
    out = {'pids': {}, 'supported': [], 'dtc': {}}
    o = await link.call('bus.open', bus='A', listen=False, bitrate=500000)
    if not o.get('ok'):
        out['err'] = o.get('err')
        return out
    tx, rx = '7DF', '7E8'
    supported = []
    base = 0
    while True:
        resp, err = await link.send('A', tx, rx, f'01{base:02X}', 1000)
        if err or resp is None or len(resp) < 6:
            if base == 0:
                out['err'] = err or 'no answer'
            break
        mask = int.from_bytes(resp[2:6], 'big')
        for i in range(32):
            if mask & (1 << (31 - i)):
                supported.append(base + i + 1)
        if not mask & 1 or base >= 0xC0:
            break
        base += 0x20
    out['supported'] = [f'{p:02X}' for p in supported]
    for pid in supported:
        if pid % 0x20 == 0:
            continue
        resp, err = await link.send('A', tx, rx, f'01{pid:02X}', 1000)
        if err or resp is None:
            out['pids'][f'{pid:02X}'] = {'err': err}
            continue
        d = resp[2:]
        name, f = OBD_PIDS.get(pid, (f'PID {pid:02X}', None))
        try:
            val = f(d) if f else ' '.join(f'{x:02X}' for x in d)
        except Exception:
            val = ' '.join(f'{x:02X}' for x in d)
        out['pids'][f'{pid:02X}'] = {'name': name, 'value': val, 'raw': d.hex().upper()}
    for mode, name in (('03', 'сохранённые'), ('07', 'ожидающие'), ('0A', 'постоянные')):
        resp, err = await link.send('A', tx, rx, mode, 1500)
        out['dtc'][name] = obd_dtcs(resp) if resp is not None and not err else {'err': err}
    resp, err = await link.send('A', tx, rx, '0902', 2000)
    if resp is not None and not err:
        out['vin'] = ascii_(resp[3:])
    await link.call('bus.close', bus='A')
    return out


# ---------- опрос ----------

async def scan(args):
    kb = json.load(open(os.path.join(KB_DIR, 'c3_ii.json'), encoding='utf-8'))
    try:
        extra = json.load(open(os.path.join(KB_DIR, 'c3_ii_dtc_gpl.json'), encoding='utf-8')).get('models', {})
    except OSError:
        extra = {}
    generic = kb.get('dtc_generic', {})
    try:
        psa = json.load(open(os.path.join(KB_DIR, 'psa_codes.json'), encoding='utf-8'))
    except OSError:
        psa = {}
    only = set(args.only.split(',')) if args.only else None
    if args.url:
        url = args.url
    else:
        s = json.load(open(os.path.join(HERE, '.session.json'), encoding='utf-8'))
        url = f"ws://127.0.0.1:{s['port']}/claude?key={s['key']}"

    result = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'kb': kb.get('title'), 'ecus': []}
    t0 = time.monotonic()
    async with websockets.connect(url, max_size=2 ** 22, open_timeout=15) as ws:
        link = Link(ws)
        try:
            h = await link.call('hello')
            result['adapter'] = {k: h.get(k) for k in ('fw', 'hw', 'mv')}
            print(f"адаптер {h.get('fw')}, АКБ {h.get('mv', 0) / 1000:.2f} В", flush=True)
            bus = kb.get('diag_bus', 'B')
            o = await link.call('bus.open', bus=bus, listen=False, bitrate=kb.get('bitrate', 500000))
            if not o.get('ok'):
                raise RuntimeError(f"шина {bus} не открылась: {o.get('err')}")
            for d in kb['ecus']:
                if only and d['node'] not in only:
                    continue
                e = Ecu(link, bus, d)
                info = {'node': d['node'], 'name': txt(d['name']), 'tx': d['tx'], 'rx': d['rx']}
                result['ecus'].append(info)
                if not await e.probe():
                    info['present'] = False
                    print(f"  {d['node']:8} {d['tx']}: нет ответа", flush=True)
                    continue
                info.update(present=True, proto=e.proto, open=e.open)
                model, variant, part = await e.detect_model()
                info.update(model=model['model'] if model else None,
                            model_name=txt(model.get('name')) if model else None, variant=variant, part=part)
                dtcs, err = await e.read_dtcs()
                if dtcs is not None:
                    for x in dtcs:
                        x['text'] = dtc_text(model, extra, generic, x, psa, sae_p(d))
                info['dtc'] = dtcs if dtcs is not None else {'err': err}
                info['records'] = []
                if model:
                    for kind in ('identification', 'config', 'live'):
                        for r in model.get('records') or []:
                            if r.get('kind', 'live') != kind or not record_applies(r, variant):
                                continue
                            resp, err = await e.ask(r['req'])
                            rec = {'req': r['req'], 'kind': kind, 'name': txt(r.get('name'))}
                            if err or resp is None:
                                rec['err'] = err
                            else:
                                payload = resp[len(unhex(r['req'])):]
                                rec['raw'] = payload.hex().upper()
                                vals = []
                                for prm in record_params(r, variant):
                                    if not Bits(prm['bits']).fits(payload):
                                        continue
                                    num, text = decode_param(prm, payload)
                                    vals.append({'key': prm.get('key'), 'name': txt(prm.get('name')) or prm.get('key'),
                                                 'value': fmt_value(prm, num, text),
                                                 'num': num if isinstance(num, (int, float)) and num == num else None})
                                rec['values'] = vals
                            info['records'].append(rec)
                n_dtc = len(dtcs) if dtcs is not None else '?'
                n_rec = sum(1 for r in info['records'] if 'values' in r)
                print(f"  {d['node']:8} {d['tx']}: {e.proto}, {info['model'] or 'модель ?'} {variant or ''} "
                      f"деталь {part or '?'}, ошибок {n_dtc}, записей {n_rec}/{len(info['records'])}", flush=True)
            await link.call('bus.close', bus=bus)
            if not args.no_obd:
                print('OBD-II на шине A…', flush=True)
                result['obd'] = await scan_obd(link)
            h = await link.call('vbat')
            result['adapter']['mv_end'] = h.get('mv')
        except ConnectionError as ex:
            result['aborted'] = str(ex)
            print('ПРЕРВАНО:', ex, flush=True)
        finally:
            result['seconds'] = round(time.monotonic() - t0, 1)
            result['log'] = link.log
    return result


def report(res):
    L = [f"# Опрос машины {res['time']}", '', f"База знаний: {res.get('kb')}  ", f"Адаптер: {res.get('adapter', {}).get('fw')}, "
         f"АКБ {res.get('adapter', {}).get('mv', 0) / 1000:.2f} В в начале, "
         f"{(res.get('adapter', {}).get('mv_end') or 0) / 1000:.2f} В в конце; опрос {res.get('seconds')} с", '']
    if res.get('aborted'):
        L += [f"**Опрос прерван:** {res['aborted']}", '']
    found = [e for e in res['ecus'] if e.get('present')]
    L += ['## Блоки', '', '| Блок | Адрес | Протокол | Модель | Вариант ПО | Деталь | Ошибок |', '|---|---|---|---|---|---|---|']
    for e in res['ecus']:
        if e.get('present'):
            n = len(e['dtc']) if isinstance(e.get('dtc'), list) else e.get('dtc', {}).get('err')
            L.append(f"| {e['node']} — {e['name']} | {e['tx']}/{e['rx']} | {e.get('proto')} | {e.get('model') or '?'} "
                     f"| {e.get('variant') or ''} | {e.get('part') or ''} | {n} |")
    missing = [e['node'] for e in res['ecus'] if e.get('present') is False]
    L += ['', f"Не ответили: {', '.join(missing) or 'все ответили'}", '']
    L += ['## Ошибки', '']
    any_dtc = False
    for e in found:
        if isinstance(e.get('dtc'), list) and e['dtc']:
            any_dtc = True
            L.append(f"**{e['node']} — {e['name']}**")
            for x in e['dtc']:
                state = 'активна' if x['active'] else 'сохранена'
                L.append(f"- `{x.get('key') or x['code']}` ({state}, статус {x['status']}): {x.get('text') or 'текста в базе нет'}")
            L.append('')
    if not any_dtc:
        L += ['Ошибок нет ни в одном ответившем блоке.', '']
    if res.get('obd'):
        o = res['obd']
        L += ['## OBD-II (шина A)', '']
        if o.get('err'):
            L.append(f"Ошибка: {o['err']}")
        if o.get('vin'):
            L.append(f"VIN: {o['vin']}  ")
        for k, v in (o.get('dtc') or {}).items():
            L.append(f"Ошибки {k}: {', '.join(v) if isinstance(v, list) and v else ('нет' if isinstance(v, list) else v)}  ")
        L += ['', '| PID | Параметр | Значение |', '|---|---|---|']
        for pid, v in (o.get('pids') or {}).items():
            L.append(f"| {pid} | {v.get('name', '')} | {v.get('value', v.get('err'))} |")
        L.append('')
    L += ['## Данные блоков', '']
    for e in found:
        recs = [r for r in e.get('records', []) if r.get('values')]
        if not recs:
            continue
        L.append(f"### {e['node']} — {e['name']} ({e.get('model') or '?'})")
        for r in recs:
            L += ['', f"**{r['req']} — {r['name']}** ({r['kind']})", '', '| Параметр | Значение |', '|---|---|']
            for v in r['values']:
                L.append(f"| {v['name']} | {v['value']} |")
        failed = [r['req'] + ' ' + str(r.get('err')) for r in e.get('records', []) if 'err' in r]
        if failed:
            L += ['', f"Не прочитались: {', '.join(failed)}"]
        L.append('')
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--url', help='напрямую: ws://192.168.4.1:81/ws')
    ap.add_argument('--only', help='только эти блоки, через запятую: BSI,CMM')
    ap.add_argument('--no-obd', action='store_true', help='без OBD-II на шине A')
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding='utf-8')
    res = asyncio.run(scan(args))
    out = os.path.join(ROOT, 'scans', time.strftime('%Y-%m-%d_%H%M%S'))
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'scan.json'), 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out, 'report.md'), 'w', encoding='utf-8') as f:
        f.write(report(res))
    print('записано:', out)


if __name__ == '__main__':
    main()
