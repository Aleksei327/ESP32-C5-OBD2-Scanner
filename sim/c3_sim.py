#!/usr/bin/env python3
"""Симулятор адаптера сканера: изображает XIAO ESP32-C5 с подключённой Citroen C3 II.

Говорит по протоколу из DOCS/ПРОТОКОЛ.md (JSON по WebSocket), чтобы приложение
можно было писать и проверять без железа и без машины.

  python sim/c3_sim.py                 # слушать на 0.0.0.0:8765
  python sim/c3_sim.py --engine-off    # зажигание есть, мотор не крутится

Шина B (OBD 3/8): блоки отвечают на UDS (ISO 14229). Адреса BSI/двигателя/ABS/подушек/щитка —
как у PSA AEE2004. Идентификаторы (DID) живых данных и настроек BSI — выдуманные для
симулятора: настоящие узнаем, когда послушаем машину. Запись в блоки симулятор
не даёт: отвечает отказом, как блок без доступа.
Шина A (OBD 6/14): обычный OBD-II, 7DF/7E0 -> 7E8, режимы 01, 03, 04, 09.
"""
import argparse
import asyncio
import json
import math
import random
import time

import websockets

FW = 'sim-0.1.0'
VIN = 'VF7SIMULATORC3001'          # 17 знаков, заведомо не настоящий


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


class Ecu:
    """Блок на шине B, UDS."""

    def __init__(self, name, bus, tx, rx, dtcs=(), dids=None, cfg=None):
        self.name, self.bus, self.tx, self.rx = name, bus, tx, rx
        self.dtcs = list(dtcs)                 # [(3 байта DTC, байт статуса)]
        self.dids = dict(dids or {})           # DID -> bytes или f(car) -> bytes
        self.cfg = dict(cfg or {})             # DID -> bytearray, их можно писать
        self.snapshots = {}                    # DTC (3 байта) -> [(DID, bytes)] — стоп-кадр
        self.session = 1
        self.unlocked = False
        self.seed = None

    def read_did(self, did, car):
        if did in self.cfg:
            return bytes(self.cfg[did])
        v = self.dids.get(did)
        return v(car) if callable(v) else v

    def routine(self, rid, args, sim):
        return None

    def handle(self, req, sim):
        car = sim.car
        sid = req[0]

        if sid == 0x10:                        # сессия
            if len(req) < 2:
                return nrc(sid, 0x13)
            self.session = req[1] & 0x7F
            if self.session == 1:
                self.unlocked = False
            return bytes([0x50, self.session, 0x00, 0x32, 0x01, 0xF4])

        if sid == 0x3E:                        # "я здесь"
            return bytes([0x7E, 0x00])

        if sid == 0x22:                        # чтение по DID
            if len(req) < 3:
                return nrc(sid, 0x13)
            val = self.read_did((req[1] << 8) | req[2], car)
            if val is None:
                return nrc(sid, 0x31)
            return bytes([0x62, req[1], req[2]]) + val

        if sid == 0x19:                        # ошибки
            sub = req[1] if len(req) > 1 else 0x02
            if sub == 0x04:                    # стоп-кадр по номеру ошибки: 19 04 <DTC> <запись>
                if len(req) < 5:
                    return nrc(sid, 0x13)
                dtc = bytes(req[2:5])
                found = [s for d, s in self.dtcs if d == dtc]
                if not found:
                    return nrc(sid, 0x31)
                body = bytearray([0x59, 0x04]) + dtc + bytes([found[0]])
                snap = self.snapshots.get(dtc)
                if snap:
                    body += bytes([0x01, len(snap)])
                    for did, val in snap:
                        body += u16(did) + val
                return bytes(body)
            body = bytearray([0x59, 0x02, 0xFF])
            for dtc, status in self.dtcs:
                body += dtc + bytes([status])
            return bytes(body)

        if sid == 0x14:                        # сброс ошибок; активные (бит 0) остаются
            self.dtcs = [d for d in self.dtcs if d[1] & 0x01]
            return bytes([0x54])

        if sid in (0x27, 0x2E, 0x31) and self.session == 1:
            return nrc(sid, 0x7F)              # не в этой сессии

        if sid == 0x2E:                        # запись по DID
            if len(req) < 4:
                return nrc(sid, 0x13)
            did = (req[1] << 8) | req[2]
            if did not in self.cfg:
                return nrc(sid, 0x31)
            if not self.unlocked:
                return nrc(sid, 0x33)
            if car.vbat_mv < 12000:
                return nrc(sid, 0x22)          # условия не те: низкое напряжение
            self.cfg[did] = bytearray(req[3:])
            return bytes([0x6E, req[1], req[2]])

        if sid == 0x31:                        # процедуры
            if len(req) < 4:
                return nrc(sid, 0x13)
            rid = (req[2] << 8) | req[3]
            res = self.routine(rid, bytes(req[4:]), sim)
            if res is None:
                return nrc(sid, 0x31)
            if isinstance(res, int):
                return nrc(sid, res)
            return bytes([0x71, req[1], req[2], req[3]]) + res

        return nrc(sid, 0x11)


class Bsi(Ecu):
    def __init__(self):
        super().__init__(
            'BSI', 'B', 0x752, 0x652,
            dtcs=[(bytes([0xC1, 0x00, 0x00]), 0x08),     # U0100, сохранена
                  (bytes([0xC1, 0x55, 0x00]), 0x09)],    # U0155, активна
            dids={0xF190: VIN.encode(),
                  0xF187: b'9665000000',
                  0xF195: b'SIM 0.1'},
            cfg={0x2201: bytearray([1]),       # закрывать двери в движении
                 0x2202: bytearray([0]),       # дневные ходовые огни
                 0x2203: bytearray([30]),      # сопровождающий свет, с
                 0x2204: bytearray([0]),       # открывать только водительскую
                 0x2205: bytearray([0])})      # звук при закрытии


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
                v = bytes([max(0, (car.rpm - 800) // 40)])
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
            ff = {0x02: b'0', 0x04: bytes([52 * 255 // 100]), 0x05: bytes([88 + 40]),
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


class Sim:
    def __init__(self, car):
        self.car = car
        obd = ObdEngine()
        self.ecus = {('A', 0x7DF): obd, ('A', 0x7E0): obd}
        for e in (Bsi(),
                  Ecu('Двигатель', 'B', 0x6A8, 0x688,
                      dtcs=[(bytes([0x01, 0x30, 0x00]), 0x09),    # P0130, активна
                            (bytes([0x03, 0x00, 0x00]), 0x08)],   # P0300, сохранена
                      dids={0xF190: VIN.encode(),
                            0x1001: lambda c: u16(c.rpm),
                            0x1002: lambda c: bytes([int(c.coolant) + 40]),
                            0x1003: lambda c: bytes([c.throttle]),
                            0x1004: lambda c: u16(c.lambda_mv),
                            0x1005: lambda c: u16(c.vbat_mv)}),
                  Ecu('ABS/ESP', 'B', 0x6AD, 0x68D, dids={0xF190: VIN.encode()}),
                  Ecu('Подушки', 'B', 0x744, 0x644, dids={0xF190: VIN.encode()}),
                  Ecu('Щиток', 'B', 0x75F, 0x65F, dids={0xF190: VIN.encode()})):
            self.ecus[(e.bus, e.tx)] = e
        snap = lambda rpm, cool, thr, mv, spd: [
            (0x1001, u16(rpm)), (0x1002, bytes([cool + 40])), (0x1003, bytes([thr])),
            (0x1005, u16(mv)), (0x1006, bytes([spd]))]
        eng = self.ecus[('B', 0x6A8)]
        eng.snapshots = {bytes([0x01, 0x30, 0x00]): snap(2140, 88, 34, 14180, 62),
                         bytes([0x03, 0x00, 0x00]): snap(3100, 91, 60, 14020, 95)}
        bsi = self.ecus[('B', 0x752)]
        bsi.snapshots = {bytes([0xC1, 0x00, 0x00]): [(0x1005, u16(12410)), (0x1006, bytes([0]))],
                         bytes([0xC1, 0x55, 0x00]): [(0x1005, u16(11930)), (0x1006, bytes([47]))]}
        # блоки, которых нет в базе знаний — на них проверяется «поиск блоков».
        # Адреса для симулятора, не сверены с машиной.
        for e in (Ecu('Климат (sim)', 'B', 0x76D, 0x66D, dids={0xF190: VIN.encode()}),
                  Ecu('Усилитель руля (sim)', 'B', 0x6B5, 0x5B5, dids={0xF190: VIN.encode()})):
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
    async with websockets.serve(lambda ws: handler(ws, sim), args.host, args.port):
        await asyncio.Future()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nстоп')
