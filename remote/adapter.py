"""Команды адаптеру — через посредника (remote/relay.py), напрямую или к симулятору.

    python remote/adapter.py hello
    python remote/adapter.py open B             # шина B для запросов (listen: false)
    python remote/adapter.py open B --listen    # только слушать
    python remote/adapter.py req B 752 652 10C0 2180 17FF00
    python remote/adapter.py any B 6A8 3E00     # rx «*»: кто ответит
    python remote/adapter.py monitor B 5        # сводка шины 5 с
    python remote/adapter.py close B

По умолчанию — через посредника (адрес и ключ из remote/.session.json).
--url ws://192.168.4.1:81/ws — напрямую к адаптеру, --url ws://127.0.0.1:8765 — к симулятору.
Только чтение: команды записи в блоки этот инструмент не шлёт.
"""
import argparse
import asyncio
import json
import os
import sys
import time

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
# Сервисы, которые меняют что-то в блоке, кроме сброса ошибок (14, 54 ответ) — не отправляем
WRITE_SIDS = {0x27, 0x2E, 0x2F, 0x31, 0x34, 0x35, 0x36, 0x37, 0x3B, 0x3D, 0x11, 0x28, 0x85}


def relay_url():
    with open(os.path.join(HERE, '.session.json'), encoding='utf-8') as f:
        s = json.load(f)
    return f"ws://127.0.0.1:{s['port']}/claude?key={s['key']}"


class Client:
    def __init__(self, ws):
        self.ws = ws
        self.n = 0

    async def call(self, cmd, timeout=10, **kw):
        self.n += 1
        rid = self.n
        await self.ws.send(json.dumps({'id': rid, 'cmd': cmd, **kw}))
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return {'id': rid, 'ok': False, 'err': 'no answer (relay)'}
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), left))
            if msg.get('id') == rid:
                return msg
            if msg.get('err') == 'no_phone':
                return msg


def check_read_only(data):
    sid = int(data[:2], 16)
    if sid in WRITE_SIDS:
        sys.exit(f'сервис {sid:02X} меняет блок — этот инструмент только читает')


async def run(args):
    url = args.url or relay_url()
    async with websockets.connect(url, max_size=2 ** 22, open_timeout=15) as ws:
        c = Client(ws)
        a = args.args
        t0 = time.monotonic()
        if args.cmd == 'hello':
            print(await c.call('hello'))
        elif args.cmd == 'vbat':
            print(await c.call('vbat'))
        elif args.cmd == 'open':
            print(await c.call('bus.open', bus=a[0], listen=args.listen, bitrate=500000))
        elif args.cmd == 'close':
            print(await c.call('bus.close', bus=a[0]))
        elif args.cmd in ('req', 'any'):
            bus, tx = a[0], a[1]
            rx = '*' if args.cmd == 'any' else a[2]
            o = await c.call('bus.open', bus=bus, listen=False, bitrate=500000)  # уже открыта так же — ничего не меняет
            if not o.get('ok'):
                sys.exit(f'шина {bus} не открылась: {o.get("err")}')
            for data in a[2 if args.cmd == 'any' else 3:]:
                check_read_only(data)
                t = time.monotonic()
                r = await c.call('isotp.req', bus=bus, tx=tx, rx=rx, data=data, timeout_ms=args.timeout)
                ms = (time.monotonic() - t) * 1000
                if r.get('ok'):
                    print(f'{tx}->{r.get("rx")} {data}: {r["data"]}  ({ms:.0f} мс)')
                else:
                    print(f'{tx} {data}: ошибка {r.get("err")}  ({ms:.0f} мс)')
        elif args.cmd == 'monitor':
            bus, secs = a[0], float(a[1]) if len(a) > 1 else 5
            print(await c.call('monitor.start', bus=bus, mode='summary'))
            end = time.monotonic() + secs
            last = None
            while time.monotonic() < end:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), max(0.1, end - time.monotonic())))
                except asyncio.TimeoutError:
                    break
                if msg.get('ev') == 'frames' and msg.get('bus') == bus:
                    last = msg
            await c.call('monitor.stop', bus=bus)
            for f in (last or {}).get('frames', []):
                print(f"{f['id']:>4} {f['hz']:>4} Гц  {f['data']}")
            print(f"{len((last or {}).get('frames', []))} ID")
        else:
            sys.exit(f'не знаю команду {args.cmd}')
        if args.cmd != 'monitor':
            print(f'всего {(time.monotonic() - t0) * 1000:.0f} мс')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd')
    ap.add_argument('args', nargs='*')
    ap.add_argument('--url', help='напрямую: ws://192.168.4.1:81/ws или симулятор')
    ap.add_argument('--timeout', type=int, default=1500, help='ожидание ответа блока, мс')
    ap.add_argument('--listen', action='store_true', help='open: только слушать')
    asyncio.run(run(ap.parse_args()))


if __name__ == '__main__':
    main()
