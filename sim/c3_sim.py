#!/usr/bin/env python3
"""Симулятор адаптера сканера: изображает XIAO ESP32-C5 с подключённой Citroen C3 II.

Говорит по протоколу из DOCS/ПРОТОКОЛ.md (JSON по WebSocket), чтобы приложение
можно было писать и проверять без железа и без машины.

  python sim/c3_sim.py                 # слушать на 0.0.0.0:8765
  python sim/c3_sim.py --engine-off    # зажигание есть, мотор не крутится

Шина B (OBD 3/8): блоки говорят на KWP2000 по-PSA, как на настоящей C3 II (AEE2004):
сеанс 81 или 10 C0, чтение записей 21 xx, ошибки 17 FF 00, сброс 14 FF 00.
Какие стоят модели, их адреса, номера деталей и раскладка данных — из базы знаний
приложения (app/assets/kb/c3_ii.json, собрана из PSA-RE), значения — от «машины» ниже.
Запись в блоки симулятор не даёт: отвечает отказом, как блок без доступа.
Шина A (OBD 6/14): обычный OBD-II, 7DF/7E0 -> 7E8, режимы 01, 02, 03, 04, 09.
"""
import argparse
import asyncio
import json
import math
import os
import random
import time

import websockets

FW = 'sim-0.2.0'
VIN = 'VF7SIMULATORC3001'          # 17 знаков, заведомо не настоящий
KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'assets', 'kb', 'c3_ii.json')
KWP_IDLE_S = 5.0                   # сеанс KWP гаснет без запросов


def hx(b):
    return b.hex().upper()


def u16(v):
    return bytes([(v >> 8) & 0xFF, v & 0xFF])


def nrc(sid, code):
    return bytes([0x7F, sid, code])


class Car:
    """Состояние машины: мотор, температура, бортсеть."""

    def __init__(self, engine_on=True):
        self.t0 = time.monotonic()
        self.last = self.t0
        self.engine_on = engine_on
        self.coolant = 62.0

    def warm(self):
        now = time.monotonic()
        dt, self.last = now - self.last, now
        if self.engine_on:
            self.coolant = min(90.0, self.coolant + dt * 0.4)

    @property
    def rpm(self):
        if not self.engine_on:
            return 0
        t = (time.monotonic() - self.t0) % 20
        if 6 <= t <= 12:                       # каждые 20 с — подгазовка до ~3400
            return int(800 + 2600 * math.sin((t - 6) / 6 * math.pi))
        return int(800 + random.uniform(-25, 25))

    @property
    def vbat_mv(self):
        base = 14100 if self.engine_on else 12600
        return int(base + random.uniform(-40, 40))

    @property
    def lambda_mv(self):
        if not self.engine_on:
            return 450
        return 720 if int(time.monotonic() * 2) % 2 else 180

    @property
    def throttle(self):
        r = self.rpm
        return 3 if r < 1000 else min(100, r // 60)

    @property
    def speed(self):
        return max(0, (self.rpm - 800) // 40)


# ---------- значения по раскладке PSA-RE: "<байт>.<бит>-<байт>.<бит>" ----------

def _pos(s):
    b, bit = s.split('.')
    return (int(b) - 1) * 8 + (7 - int(bit))


def bit_range(spec, nbytes):
    if '-' in spec:
        a, b = spec.split('-')
        return _pos(a), (nbytes * 8 - 1 if b == 'n' else _pos(b))
    return _pos(spec), _pos(spec)


def put(buf, spec, raw):
    s, e = bit_range(spec, len(buf))
    n = e - s + 1
    raw &= (1 << n) - 1
    for i in range(n):
        idx = s + i
        mask = 0x80 >> (idx & 7)
        if (raw >> (n - 1 - i)) & 1:
            buf[idx >> 3] |= mask
        else:
            buf[idx >> 3] &= ~mask & 0xFF


def put_bytes(buf, spec, data):
    s, e = bit_range(spec, len(buf))
    first, last = s >> 3, e >> 3
    data = data[:last - first + 1].ljust(last - first + 1, b'\x00')
    buf[first:last + 1] = data


def bcd_bytes(digits):
    digits = digits if len(digits) % 2 == 0 else '0' + digits
    return bytes.fromhex(digits)


def encode(rec, values, car):
    """Ответ на запись данных: значения машины туда, где их ждёт раскладка, остальное — «ноль»."""
    params = rec.get('params', [])
    n = rec.get('len') or max((bit_range(p['bits'], 255)[1] >> 3) + 1 for p in params)
    buf = bytearray(n)
    for p in params:
        if bit_range(p['bits'], n)[1] >> 3 >= n:
            continue
        v = values.get(p['key'])
        v = v(car) if callable(v) else v
        t = p.get('type', 'uint')
        if t == 'str':
            put_bytes(buf, p['bits'], (v or '').encode())
        elif t == 'bcd':
            if v:
                put_bytes(buf, p['bits'], bcd_bytes(v))
        elif t in ('bytes', 'float'):
            continue
        else:
            factor, offset = p.get('factor', 1), p.get('offset', 0)
            phys = 0 if v is None else v           # «ноль» в физических единицах
            s, e = bit_range(p['bits'], n)
            size = e - s + 1
            raw = int(round((phys - offset) / factor))
            lo, hi = (-(1 << (size - 1)), (1 << (size - 1)) - 1) if t == 'sint' else (0, (1 << size) - 1)
            put(buf, p['bits'], max(lo, min(hi, raw)))   # put() сам переведёт отрицательное в доп. код
    return bytes(buf)


def load_kb():
    with open(KB_PATH, encoding='utf-8') as f:
        return json.load(f)


def kb_model(kb, node, name):
    for e in kb['ecus']:
        if e['node'] == node:
            for m in e['models']:
                if m['model'] == name:
                    return e, m
    raise KeyError(f'{node}/{name} нет в базе знаний — пересобери её (app/tool/build_kb.py)')


# Значения «машины» по названиям параметров PSA-RE (в их единицах)
ENGINE_VALUES = {
    'ENGINE_SPEED': lambda c: c.rpm,
    'SUPPLY_VOLTAGE': lambda c: c.vbat_mv / 1000,
    'ENGINE_COOLANT_TEMPERATURE': lambda c: c.coolant,
    'UNCORRECTED_COOLANT_TEMPERATURE': lambda c: c.coolant,
    'VEHICLE_SPEED': lambda c: c.speed,
    'INLET_AIR_TEMPERATURE': 24,
    'UNCORRECTED_AIR_TEMPERATURE': 24,
    'EXTERIOR_AIR_TEMPERATURE': 14,
    'MEASURED_THROTTLE_ANGLE': lambda c: c.throttle,
    'UPSTREAM_OXYGEN_SENSOR_VOLTAGE': lambda c: c.lambda_mv,
    'INTAKE_AIR_MANIFOLD_PRESSURE': lambda c: 300 + c.throttle * 6,
    'FUEL_LEVEL_DISPLAYED': 31,
}
ABS_VALUES = {'VEHICLE_SPEED': lambda c: c.speed, 'SUPPLY_VOLTAGE': lambda c: c.vbat_mv / 1000,
              'ENGINE_SPEED': lambda c: c.rpm}


class KwpEcu:
    """Блок на шине B, KWP2000 по-PSA. Модель, адрес и данные — из базы знаний."""

    def __init__(self, kb, node, model, part, dtcs=(), values=None, extra=None):
        e, m = kb_model(kb, node, model)
        self.name, self.bus = f'{node} {model}', 'B'
        self.tx, self.rx = int(e['tx'], 16), int(e['rx'], 16)
        self.model = m
        self.open_req = bytes.fromhex(m.get('open') or '81')
        self.part = part
        self.dtcs = list(dtcs)                 # [(2 байта кода, байт состояния)]
        self.values = dict(values or {})
        self.values.update(extra or {})
        self.records = {bytes.fromhex(r['req']): r for r in m.get('records', [])}
        self.last = 0.0                        # когда был последний запрос в сеансе

    def session_ok(self):
        return time.monotonic() - self.last < KWP_IDLE_S

    def read(self, req, car):
        rec = self.records.get(bytes(req))
        ident = self.model.get('ident') or {}
        is_ident = ident.get('req') and bytes.fromhex(ident['req']) == bytes(req)
        if rec is None and not is_ident:
            return None
        if rec is not None:
            body = bytearray(encode(rec, self.values, car))
        else:
            body = bytearray(24)
        if is_ident and ident.get('part'):
            s, e = bit_range(ident['part'], 255)
            need = (e >> 3) + 1
            if len(body) < need:
                body += bytes(need - len(body))
            put_bytes(body, ident['part'], bcd_bytes(self.part))
        return bytes(body)

    def handle(self, req, sim):
        car = sim.car
        sid = req[0]
        if sid == 0x81 or (sid == 0x10 and len(req) > 1 and req[1] == 0xC0):
            if bytes(req[:len(self.open_req)]) != self.open_req:
                return nrc(sid, 0x11)          # этот блок открывается другим запросом
            self.last = time.monotonic()
            return bytes([0xC1, 0xD0, 0x8F]) if sid == 0x81 else bytes([0x50, 0xC0])
        if sid == 0x82 or (sid == 0x10 and len(req) > 1 and req[1] == 0x81):
            self.last = 0.0
            return bytes([0xC2]) if sid == 0x82 else bytes([0x50, 0x81])
        if sid == 0x3E:                        # «я здесь» — отвечает и без сеанса
            if self.session_ok():
                self.last = time.monotonic()
            return bytes([0x7E])
        if sid in (0x21, 0x17, 0x14, 0x22) and not self.session_ok():
            return nrc(sid, 0x80)              # без открытого сеанса не отвечает
        self.last = time.monotonic()
        if sid in (0x21, 0x22):
            n = 2 if sid == 0x21 else 3
            if len(req) < n:
                return nrc(sid, 0x12)
            body = self.read(req[:n], car)
            if body is None:
                return nrc(sid, 0x31 if sid == 0x21 else 0x11)
            return bytes([sid + 0x40]) + bytes(req[1:n]) + body
        if sid == 0x17:
            out = bytearray([0x57, len(self.dtcs)])
            for code, st in self.dtcs:
                out += code + bytes([st])
            return bytes(out)
        if sid == 0x14:                        # сброс; те, что есть сейчас (биты 6–5 = 11), вернутся
            self.dtcs = [d for d in self.dtcs if (d[1] >> 5) & 3 == 3]
            return bytes([0x54, 0xFF, 0x00])
        if sid in (0x27, 0x3B, 0x30, 0x31, 0x34, 0x2E):
            return nrc(sid, 0x33)              # запись и управление — только с доступом, а его нет
        return nrc(sid, 0x11)


class UdsEcu:
    """Блок, которого нет в базе знаний (на нём проверяется «поиск блоков»). UDS."""

    def __init__(self, name, tx, rx):
        self.name, self.bus, self.tx, self.rx = name, 'B', tx, rx

    def handle(self, req, sim):
        sid = req[0]
        if sid == 0x3E:
            return bytes([0x7E, 0x00])
        if sid == 0x22 and bytes(req[1:3]) == b'\xF1\x90':
            return b'\x62\xF1\x90' + VIN.encode()
        return nrc(sid, 0x11)


class ObdEngine:
    """OBD-II на шине A: 7DF/7E0 -> 7E8."""
    bus, rx = 'A', 0x7E8
    PIDS = (0x04, 0x05, 0x06, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x2F, 0x42, 0x46)

    def __init__(self):
        self.dtcs = [b'\x01\x30']             # P0130

    def mask(self, base):
        m = sum(1 << (32 - (p - base)) for p in self.PIDS if base < p <= base + 32)
        if any(p > base + 32 for p in self.PIDS):
            m |= 1
        return m.to_bytes(4, 'big')

    def handle(self, req, sim):
        car = sim.car
        mode = req[0]
        if mode == 0x01 and len(req) >= 2:
            pid = req[1]
            if pid in (0x00, 0x20, 0x40):
                v = self.mask(pid)
            elif pid == 0x05:
                v = bytes([int(car.coolant) + 40])
            elif pid == 0x0C:
                v = u16(car.rpm * 4)
            elif pid == 0x0D:                   # скорость: «едем» во время подгазовки
                v = bytes([car.speed])
            elif pid == 0x0F:
                v = bytes([24 + 40])
            elif pid == 0x11:
                v = bytes([car.throttle * 255 // 100])
            elif pid == 0x42:
                v = u16(car.vbat_mv)
            elif pid == 0x04:                   # нагрузка, %
                v = bytes([min(255, (18 + car.throttle) * 255 // 100)])
            elif pid == 0x06:                   # кратковременная коррекция, %
                v = bytes([128 + random.randint(-4, 4)])
            elif pid == 0x0B:                   # давление во впуске, кПа
                v = bytes([min(255, 30 + car.throttle)])
            elif pid == 0x0E:                   # угол опережения, °
                v = bytes([(10 + car.rpm // 300) * 2 + 128 & 0xFF])
            elif pid == 0x10:                   # расход воздуха, г/с ×100
                v = u16(int(car.rpm / 800 * 300))
            elif pid == 0x2F:                   # уровень топлива, %
                v = bytes([62 * 255 // 100])
            elif pid == 0x46:                   # наружная температура
                v = bytes([14 + 40])
            else:
                return nrc(mode, 0x12)
            return bytes([0x41, pid]) + v
        if mode == 0x02 and len(req) >= 2:  # стоп-кадр: 02 <PID> [кадр 00]
            ff = {0x02: b'0', 0x04: bytes([52 * 255 // 100]), 0x05: bytes([88 + 40]),
                  0x0C: u16(2140 * 4), 0x0D: bytes([62]), 0x11: bytes([34 * 255 // 100])}
            pid = req[1]
            if pid == 0x00:
                m = sum(1 << (32 - p) for p in ff)
                return bytes([0x42, 0x00, 0x00]) + m.to_bytes(4, 'big')
            if pid not in ff:
                return nrc(mode, 0x12)
            return bytes([0x42, pid, 0x00]) + ff[pid]
        if mode == 0x03:
            return bytes([0x43, len(self.dtcs)]) + b''.join(self.dtcs)
        if mode == 0x04:
            return bytes([0x44])                # P0130 активна — после сброса вернётся
        if mode == 0x09 and len(req) >= 2 and req[1] == 0x02:
            return bytes([0x49, 0x02, 0x01]) + VIN.encode()
        return nrc(mode, 0x11)


ACTIVE, STORED = 0x60, 0x20                    # состояние ошибки KWP: биты 6–5 = 11 / 01


class Sim:
    def __init__(self, car):
        self.car = car
        self.kb = load_kb()
        self.reset()

    def reset(self):
        """Как после включения адаптера: шины закрыты, у блоков свои ошибки, сеансы закрыты.
        Делается при каждом новом подключении — проверки не зависят от прошлых."""
        kb = self.kb
        obd = ObdEngine()
        self.ecus = {('A', 0x7DF): obd, ('A', 0x7E0): obd}
        # Модели и номера деталей — из вариантов C3 II в базе знаний (A51_…)
        for e in (
            KwpEcu(kb, 'BSI', 'BSI', '9659285680',
                   dtcs=[(b'\xC0\x45', STORED), (b'\xF5\x34', ACTIVE)],   # U0045 — общий SAE, U3534 — код PSA
                   values={'VIN': VIN, 'SUPPLY_VOLTAGE': lambda c: c.vbat_mv / 1000}),
            KwpEcu(kb, 'CMM', 'V46', '789168',
                   dtcs=[(b'\x01\x30', ACTIVE), (b'\x03\x00', STORED)], values=ENGINE_VALUES),
            KwpEcu(kb, 'ABS', 'ESPMK100', '749567', values=ABS_VALUES),
            KwpEcu(kb, 'RBG', 'SAC_AUTOLIV', '9665386180'),
            KwpEcu(kb, 'CMB', 'CLUSTER', '9666453877',
                   values={'SUPPLY_VOLTAGE': lambda c: c.vbat_mv / 1000}),
            # блоки, которых нет в базе знаний — на них проверяется «поиск блоков»
            UdsEcu('чужой 1 (sim)', 0x6B1, 0x691),
            UdsEcu('чужой 2 (sim)', 0x77A, 0x67A),
        ):
            self.ecus[(e.bus, e.tx)] = e
        self.buses = {}                        # bus -> listen (bool)
        self.monitors = {}                     # bus -> mode

    async def reply(self, msg):
        rid, cmd = msg.get('id'), msg.get('cmd')

        def ok(**kw):
            return {'id': rid, 'ok': True, **kw}

        def err(e):
            return {'id': rid, 'ok': False, 'err': e}

        if cmd == 'hello':
            return ok(fw=FW, hw='sim', buses=['A', 'B'], mv=self.car.vbat_mv)
        if cmd == 'vbat':
            return ok(mv=self.car.vbat_mv)
        if cmd == 'bus.open':
            bus = msg.get('bus')
            if bus not in ('A', 'B'):
                return err('bad_args')
            self.buses[bus] = bool(msg.get('listen', True))
            return ok()
        if cmd == 'bus.close':
            self.buses.pop(msg.get('bus'), None)
            self.monitors.pop(msg.get('bus'), None)
            return ok()
        if cmd == 'isotp.req':
            bus = msg.get('bus')
            if bus not in self.buses:
                return err('bus_closed')
            if self.buses[bus]:
                return err('listen_only')
            try:
                tx = int(msg['tx'], 16)
                data = bytes.fromhex(msg['data'])
            except (KeyError, ValueError, TypeError):
                return err('bad_args')
            if not data:
                return err('bad_args')
            ecu = self.ecus.get((bus, tx))
            await asyncio.sleep(random.uniform(0.01, 0.04))
            if ecu is None:
                await asyncio.sleep(min(msg.get('timeout_ms', 1000), 3000) / 1000)
                return err('timeout')
            self.car.warm()
            return ok(data=hx(ecu.handle(data, self)), rx='%X' % ecu.rx)
        if cmd in ('tester.start', 'tester.stop'):
            return ok()
        if cmd == 'monitor.start':
            if msg.get('bus') not in ('A', 'B'):
                return err('bad_args')
            self.monitors[msg['bus']] = msg.get('mode', 'summary')
            return ok()
        if cmd == 'monitor.stop':
            self.monitors.pop(msg.get('bus'), None)
            return ok()
        return err('bad_args')

    def frames(self, bus):
        car = self.car
        t = int(time.monotonic() * 1000)
        cool = int(car.coolant) + 40
        if bus == 'B':
            rpm = car.rpm
            fr = [
                ('036', '0E00000F010000A0', 10),
                ('0B6', hx(u16(rpm * 8) + bytes([0, 0, 0, 0, 0, 0xD0])), 20),
                ('0F6', '8E3C0000%02X005220' % cool, 2),
                ('128', '0080000000000000', 5),
                ('161', '00005A00000000', 2),
                ('1A1', '7FFF000000000000', 5),
                ('221', '00FFFFFFFFFFFF', 1),
                ('3B6', VIN.encode()[:6].hex().upper(), 1),
            ]
        else:
            fr = [('7E8', '04410C%04X000000' % (car.rpm * 4), 0)]
        up = time.monotonic() - car.t0
        return {'ev': 'frames', 'bus': bus, 't': t,
                'frames': [{'id': i, 'data': d, 'hz': hz, 'n': int(up * hz) or 1} for i, d, hz in fr]}


async def handler(ws, sim):
    peer = getattr(ws, 'remote_address', ('?',))[0]
    print(f'[+] подключился {peer}')
    sim.reset()

    async def pump():
        n = 0
        while True:
            await asyncio.sleep(0.25)
            n += 1
            if n % 4 == 0:
                await ws.send(json.dumps({'ev': 'vbat', 'mv': sim.car.vbat_mv}))
            for bus in list(sim.monitors):
                await ws.send(json.dumps(sim.frames(bus)))

    task = asyncio.ensure_future(pump())
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except ValueError:
                await ws.send(json.dumps({'ok': False, 'err': 'bad_args'}))
                continue
            await ws.send(json.dumps(await sim.reply(msg)))
    except websockets.ConnectionClosed:
        pass
    finally:
        task.cancel()
        print(f'[-] отключился {peer}')


async def main():
    ap = argparse.ArgumentParser(description='Симулятор адаптера и Citroen C3 II')
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--engine-off', action='store_true', help='мотор заглушен')
    args = ap.parse_args()

    sim = Sim(Car(engine_on=not args.engine_off))
    print(f'Симулятор C3 II: ws://{args.host}:{args.port}  (прошивка {FW})')
    for e in sim.ecus.values():
        if getattr(e, 'bus', '') == 'B':
            print(f'  {e.tx:X} -> {e.rx:X}  {e.name}')
    async with websockets.serve(lambda ws: handler(ws, sim), args.host, args.port):
        await asyncio.Future()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nстоп')
