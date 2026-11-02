"""Печать шаблонов (etch_print) прямо на принтер Windows, 1:1, без PDF-просмотрщика.

Профиль принтера = полный DEVMODE драйвера (вместе с его внутренними настройками), хранится в
%APPDATA%\\etch_print\\<принтер>.devmode:
  film_max()      — «плёнка: максимум» через PrintTicket: тип бумаги «прозрачная плёнка», лучшее качество
                    и разрешение, экономия тонера выкл., монохром, A4 (что из этого есть у драйвера);
  driver_dialog() — окно настроек самого драйвера, выбранное запоминается целиком.
Плотность тонера у HP LaserJet M1530 в драйвере нет — она задаётся в меню самого принтера.
"""
import array
import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

winspool = ctypes.WinDLL('winspool.drv')
gdi = ctypes.WinDLL('gdi32')

DM_OUT_BUFFER, DM_IN_PROMPT, DM_IN_BUFFER = 2, 4, 8
DM_ORIENTATION, DM_PAPERSIZE, DM_PAPERLENGTH, DM_PAPERWIDTH, DM_SCALE, DM_COPIES = 0x1, 0x2, 0x4, 0x8, 0x10, 0x100
DMPAPER_A4 = 9
LOGPIXELSX, LOGPIXELSY = 88, 90
PHYSICALWIDTH, PHYSICALHEIGHT, PHYSICALOFFSETX, PHYSICALOFFSETY = 110, 111, 112, 113
HORZRES, VERTRES = 8, 10
WHITE_BRUSH, BLACK_BRUSH, NULL_PEN = 0, 4, 8
ALTERNATE = 1

PROFILE_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'etch_print')

PSF = 'http://schemas.microsoft.com/windows/2003/08/printing/printschemaframework'
PSK = 'http://schemas.microsoft.com/windows/2003/08/printing/printschemakeywords'


class PRINTER_INFO_4W(ctypes.Structure):
    _fields_ = [('pPrinterName', wt.LPWSTR), ('pServerName', wt.LPWSTR), ('Attributes', wt.DWORD)]


class DOCINFOW(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.c_int), ('lpszDocName', wt.LPCWSTR), ('lpszOutput', wt.LPCWSTR),
                ('lpszDatatype', wt.LPCWSTR), ('fwType', wt.DWORD)]


winspool.DocumentPropertiesW.argtypes = [wt.HWND, wt.HANDLE, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]
winspool.DocumentPropertiesW.restype = ctypes.c_long
winspool.OpenPrinterW.argtypes = [wt.LPWSTR, ctypes.POINTER(wt.HANDLE), ctypes.c_void_p]
winspool.ClosePrinter.argtypes = [wt.HANDLE]
gdi.CreateDCW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p]
gdi.CreateDCW.restype = wt.HDC
gdi.CreateICW.argtypes = [wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ctypes.c_void_p]
gdi.CreateICW.restype = wt.HDC
gdi.DeleteDC.argtypes = [wt.HDC]
gdi.GetDeviceCaps.argtypes = [wt.HDC, ctypes.c_int]
gdi.StartDocW.argtypes = [wt.HDC, ctypes.POINTER(DOCINFOW)]
gdi.StartPage.argtypes = gdi.EndPage.argtypes = gdi.EndDoc.argtypes = gdi.AbortDoc.argtypes = [wt.HDC]
gdi.GetStockObject.restype = wt.HGDIOBJ
gdi.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi.SelectObject.restype = wt.HGDIOBJ
gdi.SetPolyFillMode.argtypes = [wt.HDC, ctypes.c_int]
gdi.PolyPolygon.argtypes = [wt.HDC, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]


# --- принтеры и профили ---

def printers():
    flags = 2 | 4   # PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    need, got = wt.DWORD(), wt.DWORD()
    winspool.EnumPrintersW(flags, None, 4, None, 0, ctypes.byref(need), ctypes.byref(got))
    buf = ctypes.create_string_buffer(need.value)
    if not winspool.EnumPrintersW(flags, None, 4, buf, need, ctypes.byref(need), ctypes.byref(got)):
        return []
    arr = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_4W))
    return [arr[i].pPrinterName for i in range(got.value)]


def default_printer():
    n = wt.DWORD(0)
    winspool.GetDefaultPrinterW(None, ctypes.byref(n))
    buf = ctypes.create_unicode_buffer(n.value)
    return buf.value if winspool.GetDefaultPrinterW(buf, ctypes.byref(n)) else ''


def _doc_props(printer, dm_in=None, mode=DM_OUT_BUFFER, hwnd=None):
    """DocumentPropertiesW: (код, DEVMODE на выходе)."""
    h = wt.HANDLE()
    if not winspool.OpenPrinterW(printer, ctypes.byref(h), None):
        raise OSError('не открыть принтер %s' % printer)
    try:
        size = winspool.DocumentPropertiesW(hwnd, h, printer, None, None, 0)
        if size <= 0:
            raise OSError('драйвер %s не отдаёт настройки' % printer)
        out = ctypes.create_string_buffer(max(size, len(dm_in or b'')) + 1024)
        inp = ctypes.create_string_buffer(dm_in, len(dm_in)) if dm_in else None
        if inp is not None:
            mode |= DM_IN_BUFFER
        r = winspool.DocumentPropertiesW(hwnd, h, printer, out, inp, mode)
        dm_size = int.from_bytes(out.raw[68:70], 'little') + int.from_bytes(out.raw[70:72], 'little')
        return r, out.raw[:dm_size]
    finally:
        winspool.ClosePrinter(h)


def _profile_file(printer, ext):
    return os.path.join(PROFILE_DIR, re.sub(r'[^\w.-]+', '_', printer) + ext)


def load_profile(printer):
    """(DEVMODE или None, описание)."""
    try:
        with open(_profile_file(printer, '.devmode'), 'rb') as f:
            dm = f.read()
    except OSError:
        return None, 'профиль не задан — настройки драйвера по умолчанию'
    try:
        with open(_profile_file(printer, '.json'), encoding='utf-8') as f:
            info = json.load(f).get('summary', '')
    except (OSError, ValueError):
        info = ''
    return dm, info or 'свои настройки драйвера'


def save_profile(printer, dm, summary):
    os.makedirs(PROFILE_DIR, exist_ok=True)
    with open(_profile_file(printer, '.devmode'), 'wb') as f:
        f.write(dm)
    with open(_profile_file(printer, '.json'), 'w', encoding='utf-8') as f:
        json.dump({'printer': printer, 'summary': summary}, f, ensure_ascii=False, indent=1)


def driver_dialog(printer, hwnd=None):
    """Окно настроек драйвера, начиная с сохранённого профиля; OK — профиль перезаписывается."""
    dm, _ = load_profile(printer)
    r, out = _doc_props(printer, dm, DM_OUT_BUFFER | DM_IN_PROMPT, hwnd)
    if r != 1:   # IDOK
        return None
    summary = 'свои настройки драйвера (окно драйвера)'
    save_profile(printer, out, summary)
    return summary


def page_devmode(printer, dm, landscape=False):
    """Профиль + A4, ориентация, масштаб 100 %, 1 копия; драйвер проверяет и дополняет."""
    if dm is None:
        dm = _doc_props(printer)[1]
    b = bytearray(dm)
    fields = int.from_bytes(b[72:76], 'little')
    fields = (fields | DM_ORIENTATION | DM_PAPERSIZE | DM_SCALE | DM_COPIES) & ~(DM_PAPERLENGTH | DM_PAPERWIDTH)
    b[72:76] = fields.to_bytes(4, 'little')
    b[76:78] = (2 if landscape else 1).to_bytes(2, 'little')
    b[78:80] = DMPAPER_A4.to_bytes(2, 'little')
    b[84:86] = (100).to_bytes(2, 'little')
    b[86:88] = (1).to_bytes(2, 'little')
    return _doc_props(printer, bytes(b))[1]


# --- «плёнка: максимум» через PrintTicket ---

PS_SCRIPT = r'''
param([string]$Mode, [string]$Printer, [string]$Out, [string]$Base = '', [string]$Delta = '')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Printing
Add-Type -AssemblyName ReachFramework
$q = (New-Object System.Printing.LocalPrintServer).GetPrintQueue($Printer)
function Save-Stream($s, $path) { $ms = New-Object System.IO.MemoryStream; $s.CopyTo($ms); [IO.File]::WriteAllBytes($path, $ms.ToArray()) }
if ($Mode -eq 'caps') { Save-Stream $q.GetPrintCapabilitiesAsXml() $Out; exit 0 }
$conv = New-Object System.Printing.Interop.PrintTicketConverter($Printer, 1)
if ($Base) { $pt = $conv.ConvertDevModeToPrintTicket([IO.File]::ReadAllBytes($Base)) }
else { $pt = $q.UserPrintTicket; if (-not $pt) { $pt = $q.DefaultPrintTicket } }
$d = New-Object System.Printing.PrintTicket(([IO.File]::OpenRead($Delta)))
$v = $q.MergeAndValidatePrintTicket($pt, $d).ValidatedPrintTicket
[IO.File]::WriteAllBytes($Out, $conv.ConvertPrintTicketToDevMode($v, [System.Printing.Interop.BaseDevModeType]::UserDefault))
Save-Stream $v.GetXmlStream() ($Out + '.xml')
'''


def _ps(tmp, *args):
    script = os.path.join(tmp, 'ticket.ps1')
    with open(script, 'w', encoding='utf-8-sig') as f:
        f.write(PS_SCRIPT)
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script] + list(args),
                       capture_output=True, text=True, creationflags=0x08000000)   # CREATE_NO_WINDOW
    if r.returncode:
        raise OSError('PrintTicket: ' + (r.stderr or r.stdout).strip()[-400:])


def _features(caps_xml):
    """{feature: [(option, отображаемое имя, разрешение X)]} из PrintCapabilities."""
    root = ET.fromstring(caps_xml)
    feats = {}
    for f in root.iter('{%s}Feature' % PSF):
        opts = []
        for o in f.findall('{%s}Option' % PSF):
            disp, resx = '', 0
            for p in o.iter('{%s}Property' % PSF):
                if p.get('name') == 'psk:DisplayName':
                    v = p.find('{%s}Value' % PSF)
                    disp = (v.text or '') if v is not None else ''
            for p in o.iter('{%s}ScoredProperty' % PSF):
                if p.get('name') == 'psk:ResolutionX':
                    v = p.find('{%s}Value' % PSF)
                    resx = int(v.text) if v is not None and (v.text or '').isdigit() else 0
            if o.get('name'):
                opts.append((o.get('name'), disp, resx))
        if f.get('name'):
            feats[f.get('name')] = opts
    return feats


def _film_choice(feats):
    """Что выставить: {feature: option}."""
    pick = {}

    def first(feat, test):
        for name, disp, _ in feats.get(feat, []):
            if test(name.lower(), disp.lower()):
                pick[feat] = name
                return

    first('psk:PageMediaType', lambda n, d: 'transparen' in n or 'transparen' in d or 'film' in d or 'плён' in d
          or 'пленк' in d)
    first('psk:PageMediaSize', lambda n, d: n == 'psk:isoa4')
    first('psk:PageOutputColor', lambda n, d: n == 'psk:monochrome')
    first('psk:PageOutputQuality', lambda n, d: n == 'psk:high')
    if feats.get('psk:PageResolution'):
        pick['psk:PageResolution'] = max(feats['psk:PageResolution'], key=lambda o: o[2])[0]
    for feat, opts in feats.items():
        low = feat.lower()
        if 'econo' in low or 'tonersav' in low:
            first(feat, lambda n, d: n.endswith(('false', 'off')))
        elif 'printquality' in low and not feat.startswith('psk:') and opts:
            pick[feat] = max(opts, key=lambda o: max([int(x) for x in re.findall(r'\d+', o[1])] or [0]))[0]
    return pick


def film_max(printer):
    """Профиль «плёнка: максимум»; возвращает описание выставленного (имена — как в драйвере)."""
    with tempfile.TemporaryDirectory() as tmp:
        caps = os.path.join(tmp, 'caps.xml')
        _ps(tmp, '-Mode', 'caps', '-Printer', printer, '-Out', caps)
        with open(caps, 'rb') as f:
            caps_xml = f.read()
        feats = _features(caps_xml)
        pick = _film_choice(feats)
        ns = dict(re.findall(rb'xmlns:(\w+)="([^"]+)"', caps_xml))
        decl = ' '.join('xmlns:%s="%s"' % (k.decode(), v.decode()) for k, v in ns.items())
        body = ''.join('<psf:Feature name="%s"><psf:Option name="%s"/></psf:Feature>' % kv for kv in pick.items())
        delta = os.path.join(tmp, 'delta.xml')
        with open(delta, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?><psf:PrintTicket %s version="1">%s</psf:PrintTicket>'
                    % (decl, body))
        dm_path = os.path.join(tmp, 'film.devmode')
        args = ['-Mode', 'apply', '-Printer', printer, '-Out', dm_path, '-Delta', delta]
        dm_old, _ = load_profile(printer)
        if dm_old:
            base = os.path.join(tmp, 'base.devmode')
            with open(base, 'wb') as f:
                f.write(dm_old)
            args += ['-Base', base]
        _ps(tmp, *args)
        with open(dm_path, 'rb') as f:
            dm = f.read()
        with open(dm_path + '.xml', 'rb') as f:
            got = dict(re.findall(rb'<psf:Feature name="([^"]+)">\s*<psf:Option name="([^"]+)"', f.read()))
    shown = []
    for feat in pick:
        opt = got.get(feat.encode(), b'').decode()
        disp = next((d for n, d, _ in feats.get(feat, []) if n == opt), opt) or opt
        low = feat.lower()
        label = ('экономия тонера: ' if 'econo' in low or 'tonersav' in low else
                 'качество: ' if 'quality' in low else 'бумага: ' if feat == 'psk:PageMediaType' else '')
        shown.append(label + disp)
    summary = '; '.join(s for s in shown if s)
    save_profile(printer, dm, summary)
    return summary


# --- печать ---

def fill_hdc(hdc, ops, kx, ky, dx=0, dy=0):
    """Заливки etch_print в контекст GDI: точка (x, y) мм -> (x·kx + dx, y·ky + dy) px, even-odd.
    Тем же путём рисуется просмотр в окне — на экране то же, что уйдёт на принтер."""
    gdi.SetPolyFillMode(hdc, ALTERNATE)
    old_pen = gdi.SelectObject(hdc, gdi.GetStockObject(NULL_PEN))
    old_brush = gdi.SelectObject(hdc, gdi.GetStockObject(BLACK_BRUSH))
    for gray, shapes in ops:
        if not shapes:
            continue
        pts, counts = array.array('i'), array.array('i')
        for poly in shapes:
            for x, y in poly:
                pts.append(round(x * kx + dx))
                pts.append(round(y * ky + dy))
            counts.append(len(poly))
        gdi.SelectObject(hdc, gdi.GetStockObject(BLACK_BRUSH if gray < 0.5 else WHITE_BRUSH))
        p = (ctypes.c_int * len(pts)).from_buffer(pts)
        n = (ctypes.c_int * len(counts)).from_buffer(counts)
        gdi.PolyPolygon(hdc, p, n, len(counts))
    gdi.SelectObject(hdc, old_brush)
    gdi.SelectObject(hdc, old_pen)


def page_info(printer, dm=None, landscape=False):
    """(лист Ш, В, отступ поля X, Y, печатаемая Ш, В) в мм — для серой рамки в просмотре."""
    dm = page_devmode(printer, dm, landscape)
    buf = ctypes.create_string_buffer(dm, len(dm))
    hdc = gdi.CreateICW('WINSPOOL', printer, None, buf)
    if not hdc:
        raise OSError('не получить параметры листа у %s' % printer)
    try:
        c = lambda i: gdi.GetDeviceCaps(hdc, i)
        dx, dy = c(LOGPIXELSX) / 25.4, c(LOGPIXELSY) / 25.4
        return (c(PHYSICALWIDTH) / dx, c(PHYSICALHEIGHT) / dy, c(PHYSICALOFFSETX) / dx, c(PHYSICALOFFSETY) / dy,
                c(HORZRES) / dx, c(VERTRES) / dy)
    finally:
        gdi.DeleteDC(hdc)


def print_ops(printer, W, H, ops, title, dm=None, output=None):
    """Лист W x H мм из заливок etch_print (серый, контуры) — на принтер; output — в файл (для проверки)."""
    dm = page_devmode(printer, dm, W > H)
    buf = ctypes.create_string_buffer(dm, len(dm))
    hdc = gdi.CreateDCW('WINSPOOL', printer, None, buf)
    if not hdc:
        raise OSError('не открыть принтер %s' % printer)
    try:
        c = lambda i: gdi.GetDeviceCaps(hdc, i)
        kx, ky = c(LOGPIXELSX) / 25.4, c(LOGPIXELSY) / 25.4
        ox, oy = c(PHYSICALOFFSETX), c(PHYSICALOFFSETY)
        pw, ph = c(PHYSICALWIDTH) / kx, c(PHYSICALHEIGHT) / ky
        if abs(pw - W) > 3 or abs(ph - H) > 3:
            raise OSError('у принтера лист %.0f x %.0f мм, а нужен %.0f x %.0f' % (pw, ph, W, H))
        di = DOCINFOW(ctypes.sizeof(DOCINFOW), title, output, None, 0)
        if gdi.StartDocW(hdc, ctypes.byref(di)) <= 0:
            raise OSError('принтер не принял задание')
        gdi.StartPage(hdc)
        fill_hdc(hdc, ops, kx, ky, -ox, -oy)
        gdi.EndPage(hdc)
        gdi.EndDoc(hdc)
    finally:
        gdi.DeleteDC(hdc)
