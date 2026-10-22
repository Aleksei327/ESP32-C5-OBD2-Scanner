"""Посредник удалённого помощника.

Телефон у машины соединяет адаптер (по Wi-Fi) с этим посредником (через интернет),
а помощник на компьютере говорит с адаптером через посредника по обычному протоколу
(DOCS/ПРОТОКОЛ.md), как будто адаптер рядом.

    телефон  ── wss://…/phone?key=K ──┐
                                       ├── relay.py (127.0.0.1:8790)
    помощник ── ws://…/claude?key=K ──┘

Снаружи посредник доступен через бесплатный туннель Cloudflare (cloudflared, без аккаунта):
скрипт сам его запускает и печатает адрес для телефона. Ключ создаётся заново при каждом запуске,
без него подключиться нельзя. Адрес и ключ пишутся в remote/.session.json для remote/adapter.py.

    python remote/relay.py              # с туннелем
    python remote/relay.py --no-tunnel  # только на этом компьютере (проверка с симулятором)
"""
import argparse
import asyncio
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
SESSION = os.path.join(HERE, '.session.json')
PORT = 8790


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


class Relay:
    def __init__(self, key):
        self.key = key
        self.phone = None
        self.helpers = set()

    async def handler(self, ws):
        req = getattr(ws, 'request', None)
        path = req.path if req is not None else ws.path
        u = urlparse(path)
        if parse_qs(u.query).get('key', [''])[0] != self.key:
            log('отказ: неверный ключ', u.path)
            await ws.close(4001, 'bad key')
            return
        if u.path == '/phone':
            await self.serve_phone(ws)
        elif u.path == '/claude':
            await self.serve_helper(ws)
        else:
            await ws.close(4004, 'unknown path')

    async def serve_phone(self, ws):
        if self.phone is not None:
            await self.phone.close(4000, 'replaced')
        self.phone = ws
        log('телефон подключился')
        try:
            async for msg in ws:  # ответы и события адаптера — всем помощникам
                for h in list(self.helpers):
                    try:
                        await h.send(msg)
                    except websockets.ConnectionClosed:
                        pass
        except websockets.ConnectionClosed:
            pass
        finally:
            if self.phone is ws:
                self.phone = None
                log('телефон отключился')

    async def serve_helper(self, ws):
        self.helpers.add(ws)
        try:
            async for msg in ws:
                if self.phone is None:
                    try:
                        rid = json.loads(msg).get('id')
                    except (ValueError, AttributeError):
                        rid = None
                    await ws.send(json.dumps({'id': rid, 'ok': False, 'err': 'no_phone'}))
                    continue
                try:
                    await self.phone.send(msg)
                except websockets.ConnectionClosed:
                    await ws.send(json.dumps({'ok': False, 'err': 'no_phone'}))
        except websockets.ConnectionClosed:
            pass
        finally:
            self.helpers.discard(ws)


def find_cloudflared():
    for p in (shutil.which('cloudflared'),
              r'C:\Program Files (x86)\cloudflared\cloudflared.exe',
              r'C:\Program Files\cloudflared\cloudflared.exe',
              os.path.expandvars(r'%LOCALAPPDATA%\cloudflared\cloudflared.exe'),
              os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe')):
        if p and os.path.exists(p):
            return p
    return None


def start_tunnel(exe, port, on_url):
    """cloudflared пишет адрес вида https://xxx.trycloudflare.com в свой лог (stderr)."""
    proc = subprocess.Popen([exe, 'tunnel', '--no-autoupdate', '--url', f'http://127.0.0.1:{port}'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                            encoding='utf-8', errors='replace')

    def read():
        found = False
        for line in proc.stderr:
            m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
            if m and not found:
                found = True
                on_url(m.group(0))
            elif ' ERR ' in line:
                log('cloudflared:', line.strip())
    threading.Thread(target=read, daemon=True).start()
    return proc


async def main():
    ap = argparse.ArgumentParser(description='Посредник удалённого помощника')
    ap.add_argument('--port', type=int, default=PORT)
    ap.add_argument('--no-tunnel', action='store_true', help='без туннеля Cloudflare')
    args = ap.parse_args()

    key = secrets.token_urlsafe(18)
    relay = Relay(key)
    session = {'port': args.port, 'key': key, 'phone_url': None}

    def save():
        with open(SESSION, 'w', encoding='utf-8') as f:
            json.dump(session, f, ensure_ascii=False, indent=2)

    save()
    async with websockets.serve(relay.handler, '127.0.0.1', args.port, max_size=2 ** 22, ping_interval=20):
        log(f'посредник на 127.0.0.1:{args.port}')
        log(f'для телефона в той же сети: ws://<IP компьютера>:{args.port}/phone?key={key}')
        proc = None
        if not args.no_tunnel:
            exe = find_cloudflared()
            if exe is None:
                log('cloudflared не найден: winget install Cloudflare.cloudflared')
            else:
                def on_url(url):
                    session['phone_url'] = 'wss://' + url[len('https://'):] + f'/phone?key={key}'
                    save()
                    log('АДРЕС ДЛЯ ТЕЛЕФОНА:', session['phone_url'])
                proc = start_tunnel(exe, args.port, on_url)
                log('запускаю туннель Cloudflare…')
        try:
            await asyncio.Future()
        finally:
            if proc:
                proc.terminate()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
