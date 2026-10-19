#!/usr/bin/env python3
"""Проверка симулятора (и потом настоящего адаптера) по протоколу DOCS/ПРОТОКОЛ.md.

  python sim/test_client.py                       # ws://127.0.0.1:8765
  python sim/test_client.py ws://192.168.4.1:81/ws
"""
import asyncio
import json
import sys

import websockets

URL = sys.argv[1] if len(sys.argv) > 1 else 'ws://127.0.0.1:8765'


class Client:
    def __init__(self, ws):
        self.ws, self.n, self.events = ws, 0, []

    async def call(self, cmd, **kw):
        self.n += 1
        await self.ws.send(json.dumps({'id': self.n, 'cmd': cmd, **kw}))
        while True:
            msg = json.loads(await self.ws.recv())
            if 'ev' in msg:
                self.events.append(msg)
            elif msg.get('id') == self.n:
                return msg

    async def uds(self, bus, tx, rx, data):
        r = await self.call('isotp.req', bus=bus, tx=tx, rx=rx, data=data, timeout_ms=500)
        return r.get('data', '') if r['ok'] else '!' + r['err']


fails = 0


def check(name, cond, got=''):
    global fails
    print(('  ok  ' if cond else '  FAIL') + f' {name}' + ('' if cond else f'  -> {got}'))
    fails += 0 if cond else 1


async def main():
    async with websockets.connect(URL) as ws:
        c = Client(ws)
        h = await c.call('hello')
        check('hello', h['ok'] and 'fw' in h, h)
        print(f"     прошивка {h.get('fw')}, АКБ {h.get('mv')} мВ")

        r = await c.call('isotp.req', bus='B', tx='752', rx='652', data='10C0')
        check('без bus.open -> bus_closed', r.get('err') == 'bus_closed', r)
        await c.call('bus.open', bus='B', bitrate=500000, listen=True)
        r = await c.call('isotp.req', bus='B', tx='752', rx='652', data='10C0')
        check('только слушать -> listen_only', r.get('err') == 'listen_only', r)

        await c.call('bus.open', bus='B', bitrate=500000, listen=False)
        # BSI: KWP2000, сеанс 10 C0
        check('BSI: без сеанса не отвечает -> 7F 21 80', await c.uds('B', '752', '652', '21B0') == '7F2180')
        check('BSI: сеанс 10 C0', await c.uds('B', '752', '652', '10C0') == '50C0')
        vin = await c.uds('B', '752', '652', '21B0')
        check('VIN из BSI (21 B0)', vin.startswith('61B0') and len(vin) == 4 + 34, vin)
        print(f'     VIN {bytes.fromhex(vin[4:]).decode()}')
        ident = await c.uds('B', '752', '652', '2180')
        check('опознание BSI (21 80): номер детали', ident[4:14] == '9659285680', ident)
        d = await c.uds('B', '752', '652', '17FF00')
        check('ошибки BSI (17 FF 00, 2 шт.)', d.startswith('5702') and len(d) == 4 + 2 * 6, d)
        w = await c.uds('B', '752', '652', '3BB0' + '00' * 17)
        check('запись без доступа -> 7F 3B 33', w == '7F3B33', w)

        # двигатель: KWP2000, сеанс 81
        check('двигатель: 10 C0 не его сеанс -> 7F 10 11', await c.uds('B', '6A8', '688', '10C0') == '7F1011')
        o = await c.uds('B', '6A8', '688', '81')
        check('двигатель: сеанс 81 -> C1', o.startswith('C1'), o)
        fe = await c.uds('B', '6A8', '688', '21FE')
        check('опознание двигателя (21 FE): номер детали', fe[4:][42:48] == '789168', fe)
        c0 = await c.uds('B', '6A8', '688', '21C0')
        check('двигатель: запись C0, обороты', c0.startswith('61C0') and int(c0[4:8], 16) > 0, c0)
        print(f'     обороты {int(c0[4:8], 16)}, ОЖ {int(c0[10:12], 16) - 50} °C')
        t = await c.uds('B', '7AA', '6AA', '3E00')
        check('нет такого блока -> timeout', t == '!timeout', t)
        u = await c.uds('B', '6B1', '691', '3E00')
        check('чужой блок (для поиска) отвечает', u == '7E00', u)

        await c.call('bus.open', bus='A', bitrate=500000, listen=False)
        rpm = await c.uds('A', '7DF', '7E8', '010C')
        check('OBD-II обороты', rpm.startswith('410C'), rpm)
        print(f'     обороты {int(rpm[4:8], 16) / 4:.0f}')
        vin2 = await c.uds('A', '7DF', '7E8', '0902')
        check('OBD-II VIN', bytes.fromhex(vin2[6:]).decode() == bytes.fromhex(vin[4:]).decode(), vin2)

        await c.call('monitor.start', bus='B', mode='summary')
        await asyncio.sleep(1.1)
        await c.call('monitor.stop', bus='B')
        fr = [e for e in c.events if e.get('ev') == 'frames']
        check('монитор шины присылает кадры', len(fr) >= 2 and fr[0]['frames'], len(fr))
        check('событие vbat', any(e.get('ev') == 'vbat' for e in c.events))

        await c.uds('B', '752', '652', '1081')
        await c.call('bus.close', bus='A')
        await c.call('bus.close', bus='B')

    print('\nВСЁ ОК' if not fails else f'\nОШИБОК: {fails}')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    asyncio.run(main())
