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

        r = await c.call('isotp.req', bus='B', tx='752', rx='652', data='22F190')
        check('без bus.open -> bus_closed', r.get('err') == 'bus_closed', r)
        await c.call('bus.open', bus='B', bitrate=500000, listen=True)
        r = await c.call('isotp.req', bus='B', tx='752', rx='652', data='22F190')
        check('только слушать -> listen_only', r.get('err') == 'listen_only', r)

        await c.call('bus.open', bus='B', bitrate=500000, listen=False)
        vin = await c.uds('B', '752', '652', '22F190')
        check('VIN из BSI', vin.startswith('62F190') and len(vin) == 6 + 34, vin)
        print(f'     VIN {bytes.fromhex(vin[6:]).decode()}')

        d = await c.uds('B', '752', '652', '1902FF')
        check('ошибки BSI (2 шт.)', d.startswith('5902') and (len(d) - 6) // 8 == 2, d)

        w = await c.uds('B', '752', '652', '2E220201')
        check('запись в обычной сессии -> 7F 2E 7F', w == '7F2E7F', w)
        await c.uds('B', '752', '652', '1003')
        w = await c.uds('B', '752', '652', '2E220201')
        check('запись без доступа -> 7F 2E 33', w == '7F2E33', w)
        t = await c.uds('B', '7AA', '6AA', '22F190')
        check('нет такого блока -> timeout', t == '!timeout', t)

        await c.call('bus.open', bus='A', bitrate=500000, listen=False)
        rpm = await c.uds('A', '7DF', '7E8', '010C')
        check('OBD-II обороты', rpm.startswith('410C'), rpm)
        print(f'     обороты {int(rpm[4:8], 16) / 4:.0f}')
        vin2 = await c.uds('A', '7DF', '7E8', '0902')
        check('OBD-II VIN', bytes.fromhex(vin2[6:]).decode() == bytes.fromhex(vin[6:]).decode(), vin2)

        await c.call('monitor.start', bus='B', mode='summary')
        await asyncio.sleep(1.1)
        await c.call('monitor.stop', bus='B')
        fr = [e for e in c.events if e.get('ev') == 'frames']
        check('монитор шины присылает кадры', len(fr) >= 2 and fr[0]['frames'], len(fr))
        check('событие vbat', any(e.get('ev') == 'vbat' for e in c.events))

        await c.uds('B', '752', '652', '1001')
        await c.call('bus.close', bus='A')
        await c.call('bus.close', bus='B')

    print('\nВСЁ ОК' if not fails else f'\nОШИБОК: {fails}')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    asyncio.run(main())
