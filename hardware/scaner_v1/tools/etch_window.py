#!/usr/bin/env python3
"""Окно «Печать для травления»: лист A4 как на просмотре печати, копии платы таскаются мышкой,
негатив/позитив, тонером вниз/вверх (зеркало считается само), печать прямо на принтер 1:1 с профилем
«плёнка: максимум» или в PDF. Геометрия — etch_print.py, принтер — etch_printer.py.

Кнопка в редакторе плат KiCad — пакетом для менеджера плагинов (переживает переустановку KiCad):
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/etch_window.py --pack
  -> tools/etch_print_kicad_plugin.zip; KiCad > Менеджер плагинов и библиотек > Установить из файла.
Для правки кода — загрузчик прямо из репозитория (молчит, если пакет установлен):
  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/etch_window.py --install
Без KiCad (плата берётся из файла — сохрани её):
  "C:\\Program Files\\KiCad\\10.0\\bin\\pythonw.exe" tools/etch_window.py [плата.kicad_pcb]   (или etch_window.cmd)

Раскладка и настройки запоминаются в <папка платы>/etch/layout.json.
"""
import json
import os
import shutil
import sys
import traceback
import zipfile

import pcbnew
import wx

HERE = os.path.dirname(os.path.abspath(__file__))
try:                              # в пакете KiCad (менеджер плагинов) — модули рядом в пакете
    from . import etch_print as ep
    from . import etch_printer as pr
except ImportError:               # из репозитория / загрузчика
    sys.path.insert(0, HERE)
    import etch_print as ep       # noqa: E402
    import etch_printer as pr     # noqa: E402

TITLE = 'Печать для травления'
VERSION = '1.2.0'
PCM_ID = 'com.github.aleksei327.etchprint'
STEP = 0.5                        # шаг перетаскивания и стрелок, мм
SUPER = 2                         # просмотр рисуется вдвое крупнее и сглаживается уменьшением
LAYERS = [('B.Cu', pcbnew.B_Cu), ('F.Cu', pcbnew.F_Cu)]


def bitmap(w_mm, h_mm, s, ops):
    """Картинка заливок etch_print, s px/мм. Рисует GDI, как на принтер (GraphicsContext внутри KiCad
    оставлял лист пустым)."""
    w, h = max(1, round(w_mm * s)), max(1, round(h_mm * s))
    big = wx.Bitmap(w * SUPER, h * SUPER, 24)
    dc = wx.MemoryDC(big)
    dc.SetBackground(wx.Brush(wx.Colour(255, 255, 255)))
    dc.Clear()
    pr.fill_hdc(int(dc.GetHandle()), ops, s * SUPER, s * SUPER)
    del dc
    return big.ConvertToImage().Scale(w, h, wx.IMAGE_QUALITY_BOX_AVERAGE).ConvertToBitmap()


def solid(dc, colour):
    """Перо и кисть одного цвета. Готовые wx.TRANSPARENT_BRUSH и т.п. внутри KiCad не работают
    (рамка выделения заливала копию), поэтому всё создаётся явно и без прозрачности."""
    dc.SetPen(wx.Pen(colour))
    dc.SetBrush(wx.Brush(colour))


def frame(dc, x, y, w, h, t, colour):
    """Рамка толщиной t px из четырёх полос — внутренность не трогается."""
    solid(dc, colour)
    for r in ((x, y, w, t), (x, y + h - t, w, t), (x, y, t, h), (x + w - t, y, t, h)):
        dc.DrawRectangle(*r)


class Sheet(wx.Panel):
    """Лист: страница, непечатаемые поля, подписи, копии; мышь и клавиши двигают копии."""

    def __init__(self, parent, frame):
        super().__init__(parent, style=wx.WANTS_CHARS | wx.FULL_REPAINT_ON_RESIZE)
        self.f = frame
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((200, 250))
        self.sel = None
        self.drag = None
        self.cache = {}
        for ev, h in ((wx.EVT_PAINT, self.on_paint), (wx.EVT_SIZE, self.on_size),
                      (wx.EVT_LEFT_DOWN, self.on_down), (wx.EVT_MOTION, self.on_move),
                      (wx.EVT_LEFT_UP, self.on_up), (wx.EVT_MOUSE_CAPTURE_LOST, self.on_lost),
                      (wx.EVT_RIGHT_DOWN, self.on_right), (wx.EVT_KEY_DOWN, self.on_key)):
            self.Bind(ev, h)

    # геометрия вида
    def view(self):
        W, H = self.f.page()
        cw, ch = self.GetClientSize()
        s = max(0.5, min((cw - 30) / W, (ch - 30) / H))
        return s, (cw - W * s) / 2, (ch - H * s) / 2

    def to_mm(self, pt):
        s, x0, y0 = self.view()
        return (pt.x - x0) / s, (pt.y - y0) / s

    def frame_rect(self, p):
        b = self.f.b
        return (p[0] - ep.FRAME, p[1] - ep.FRAME, b.w + 2 * ep.FRAME, b.h + 2 * ep.FRAME)

    def invalidate(self):
        self.cache = {}
        self.Refresh()

    def on_size(self, ev):
        self.invalidate()
        ev.Skip()

    def bitmaps(self, s):
        key = (round(s, 3), self.f.settings_key())
        if self.cache.get('key') != key:
            f, b = self.f, self.f.b
            W, H = f.page()
            labels = ep.label_ops(b, f.name, W, H, f.negative(), f.toner_down(), len(f.pos), '') \
                if f.labels.GetValue() else []
            copy = ep.copy_ops(b, ep.FRAME, ep.FRAME, f.negative(), ep.mirror_for(b.layer, f.toner_down()),
                               f.dots.GetValue(), f.marks.GetValue())
            self.cache = {'key': key, 'page': bitmap(W, H, s, labels),
                          'copy': bitmap(b.w + 2 * ep.FRAME, b.h + 2 * ep.FRAME, s, copy)}
        return self.cache['page'], self.cache['copy']

    def on_paint(self, ev):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(wx.Colour(96, 96, 104)))
        dc.Clear()
        f = self.f
        if f.b is None:
            return
        s, x0, y0 = self.view()
        W, H = f.page()
        try:
            page, copy = self.bitmaps(s)
        except Exception:
            f.SetStatusText('Ошибка просмотра: ' + traceback.format_exc().strip().splitlines()[-1])
            raise
        solid(dc, wx.Colour(40, 40, 44))
        dc.DrawRectangle(round(x0 + 4), round(y0 + 4), round(W * s), round(H * s))
        dc.DrawBitmap(page, round(x0), round(y0))
        info = f.paper
        if info:          # непечатаемые поля принтера — бледно-красные полосы по краю листа
            pw, ph, ox, oy, aw, ah = info
            solid(dc, wx.Colour(255, 200, 200))
            for r in ((0, 0, W, oy), (0, oy + ah, W, H - oy - ah), (0, oy, ox, ah), (ox + aw, oy, W - ox - aw, ah)):
                if r[2] > 0 and r[3] > 0:
                    dc.DrawRectangle(round(x0 + r[0] * s), round(y0 + r[1] * s), round(r[2] * s) + 1, round(r[3] * s) + 1)
        bad = f.problems()
        order = [i for i in range(len(f.pos)) if i != self.sel] + ([self.sel] if self.sel is not None else [])
        for i in order:        # выбранная — поверх остальных
            rx, ry, rw, rh = self.frame_rect(f.pos[i])
            X, Y, w, h = round(x0 + rx * s), round(y0 + ry * s), round(rw * s), round(rh * s)
            dc.DrawBitmap(copy, X, Y)
            if i in bad:
                frame(dc, X - 4, Y - 4, w + 8, h + 8, 3, wx.Colour(230, 40, 40))
            if i == self.sel:
                frame(dc, X - 8, Y - 8, w + 16, h + 16, 3, wx.Colour(40, 120, 255))

    def hit(self, x, y):
        for i in range(len(self.f.pos) - 1, -1, -1):
            rx, ry, rw, rh = self.frame_rect(self.f.pos[i])
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return i
        return None

    def on_down(self, ev):
        self.SetFocus()
        x, y = self.to_mm(ev.GetPosition())
        self.sel = self.hit(x, y)
        if self.sel is not None:
            p = self.f.pos[self.sel]
            self.drag = (x - p[0], y - p[1])
            self.CaptureMouse()
        self.f.update_status()
        self.Refresh()

    def on_move(self, ev):
        if self.drag is None or not ev.Dragging():
            return
        x, y = self.to_mm(ev.GetPosition())
        self.place(self.sel, x - self.drag[0], y - self.drag[1])

    def place(self, i, x, y):
        b = self.f.b
        W, H = self.f.page()
        x = min(max(round(x / STEP) * STEP, ep.FRAME), W - b.w - ep.FRAME)
        y = min(max(round(y / STEP) * STEP, ep.FRAME), H - b.h - ep.FRAME)
        self.f.pos[i] = (x, y)
        self.f.update_status()
        self.Refresh()

    def on_up(self, ev):
        if self.drag is not None:
            self.drag = None
            if self.HasCapture():
                self.ReleaseMouse()

    def on_lost(self, ev):
        self.drag = None

    def on_right(self, ev):
        self.on_down(ev)
        if self.drag is not None and self.HasCapture():
            self.ReleaseMouse()
        self.drag = None
        if self.sel is None:
            return
        m = wx.Menu()
        dup, rem = m.Append(wx.ID_ANY, 'Копия рядом'), m.Append(wx.ID_ANY, 'Убрать')
        self.Bind(wx.EVT_MENU, lambda e: self.f.add_copy(near=self.sel), dup)
        self.Bind(wx.EVT_MENU, lambda e: self.f.remove_copy(), rem)
        self.PopupMenu(m)
        m.Destroy()

    def on_key(self, ev):
        k = ev.GetKeyCode()
        if self.sel is None:
            ev.Skip()
            return
        d = 5.0 if ev.ShiftDown() else STEP
        dx, dy = {wx.WXK_LEFT: (-d, 0), wx.WXK_RIGHT: (d, 0), wx.WXK_UP: (0, -d), wx.WXK_DOWN: (0, d)}.get(k, (0, 0))
        if dx or dy:
            x, y = self.f.pos[self.sel]
            self.place(self.sel, x + dx, y + dy)
        elif k in (wx.WXK_DELETE, wx.WXK_BACK):
            self.f.remove_copy()
        else:
            ev.Skip()


class EtchFrame(wx.Frame):
    def __init__(self, parent, board, editor):
        super().__init__(parent, title=TITLE, size=(1100, 820),
                         style=wx.DEFAULT_FRAME_STYLE | (wx.FRAME_FLOAT_ON_PARENT if parent else 0))
        self.board, self.editor = board, editor
        self.b = None
        self.paper = None
        self.dir = os.path.join(os.path.dirname(board.GetFileName()), 'etch')
        st = self.load_state()
        self.pos = [tuple(p) for p in st.get('positions', [])]

        # слева кнопки (с прокруткой), справа лист; границу между ними таскает мышь
        self.split = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE | wx.SP_3DSASH)
        side = wx.ScrolledWindow(self.split, style=wx.VSCROLL | wx.HSCROLL)
        side.SetScrollRate(10, 10)
        self.panel = side
        self.sheet = Sheet(self.split, self)
        L = wx.BoxSizer(wx.VERTICAL)
        # все кнопки и списки — по ширине своей надписи, не растягиваются за панелью
        A = wx.ALL | wx.ALIGN_LEFT

        box = wx.StaticBoxSizer(wx.VERTICAL, side, 'Что печатать')
        sb = box.GetStaticBox()
        self.layer = wx.Choice(sb, choices=[n for n, _ in LAYERS])
        self.layer.SetSelection(next((i for i, (n, _) in enumerate(LAYERS) if n == st.get('layer')), 0))
        self.kind = wx.RadioBox(sb, label='Резист', choices=['Негатив — плёночный фоторезист',
                                                             'Позитив — ЛУТ, позитивный резист'],
                                majorDimension=1, style=wx.RA_SPECIFY_COLS)
        self.kind.SetSelection(0 if st.get('negative', True) else 1)
        self.side = wx.RadioBox(sb, label='Плёнку кладу на медь', choices=['Тонером вниз (к меди)',
                                                                           'Тонером вверх'],
                                majorDimension=1, style=wx.RA_SPECIFY_COLS)
        self.side.SetSelection(0 if st.get('toner_down', True) else 1)
        self.mirror = wx.StaticText(sb, label='→ печать без зеркала')
        self.mirror.SetFont(self.mirror.GetFont().Bold())
        self.dots = wx.CheckBox(sb, label='Точки под сверло')
        self.marks = wx.CheckBox(sb, label='Уголки и крестики в отверстиях')
        self.labels = wx.CheckBox(sb, label='Подписи и линейки 100 мм')
        self.landscape = wx.CheckBox(sb, label='Лист A4 альбомный')
        for c, k in ((self.dots, 'dots'), (self.marks, 'marks'), (self.labels, 'labels')):
            c.SetValue(st.get(k, True))
        self.landscape.SetValue(st.get('landscape', False))
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(sb, label='Слой меди:'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        row.Add(self.layer, 0)
        for w in (row, self.kind, self.side, self.mirror, self.dots, self.marks, self.labels, self.landscape):
            box.Add(w, 0, A, 3)
        L.Add(box, 0, wx.EXPAND | wx.ALL, 4)
        self.wrap = max(self.kind.GetBestSize().width, self.side.GetBestSize().width, 240)

        box = wx.StaticBoxSizer(wx.VERTICAL, side, 'Копии на листе')
        sb = box.GetStaticBox()
        g = wx.GridSizer(2, 2, 4, 4)
        for label, h in (('+ Копия', lambda e: self.add_copy()), ('− Убрать', lambda e: self.remove_copy()),
                         ('Заполнить лист', self.on_fill), ('Очистить', self.on_clear)):
            btn = wx.Button(sb, label=label)
            btn.Bind(wx.EVT_BUTTON, h)
            g.Add(btn, 0, wx.EXPAND)
        box.Add(g, 0, A, 3)
        hint = wx.StaticText(sb, label='Тащи копию мышкой. Стрелки — 0,5 мм (Shift — 5 мм), Delete — убрать, '
                                       'правая кнопка — меню. Красная рамка — налезает или вне поля печати.')
        hint.Wrap(self.wrap)
        box.Add(hint, 0, A, 3)
        L.Add(box, 0, wx.EXPAND | wx.ALL, 4)

        box = wx.StaticBoxSizer(wx.VERTICAL, side, 'Принтер')
        sb = box.GetStaticBox()
        self.printers = pr.printers()
        self.printer = wx.Choice(sb, choices=self.printers)
        want = st.get('printer') or pr.default_printer()
        self.printer.SetSelection(self.printers.index(want) if want in self.printers else 0)
        self.profile = wx.StaticText(sb)
        film = wx.Button(sb, label='Плёнка: максимум')
        drv = wx.Button(sb, label='Настройки драйвера…')
        film.SetToolTip('Тип бумаги «прозрачная плёнка», лучшее качество, экономия тонера выкл., A4. '
                        'Запоминается для этого принтера.')
        drv.SetToolTip('Окно драйвера принтера; выбранное запоминается целиком и идёт в каждую печать отсюда.')
        film.Bind(wx.EVT_BUTTON, self.on_film)
        drv.Bind(wx.EVT_BUTTON, self.on_driver)
        box.Add(self.printer, 0, A, 3)
        box.Add(self.profile, 0, A, 3)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(film, 0, wx.RIGHT, 4)
        row.Add(drv, 0)
        box.Add(row, 0, A, 3)
        L.Add(box, 0, wx.EXPAND | wx.ALL, 4)

        self.btn_print = wx.Button(side, label='Печать')
        self.btn_print.SetFont(self.btn_print.GetFont().Bold().Scaled(1.2))
        pdf = wx.Button(side, label='Сохранить PDF')
        reload_ = wx.Button(side, label='Обновить с платы')
        self.btn_print.Bind(wx.EVT_BUTTON, self.on_print)
        pdf.Bind(wx.EVT_BUTTON, self.on_pdf)
        reload_.Bind(wx.EVT_BUTTON, lambda e: self.reload())
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self.btn_print, 0, wx.RIGHT, 4)
        row.Add(pdf, 0, wx.RIGHT, 4)
        row.Add(reload_, 0)
        L.Add(row, 0, A, 6)
        side.SetSizer(L)
        side.FitInside()
        self.split.SetMinimumPaneSize(120)
        self.split.SetSashGravity(0.0)
        self.split.SplitVertically(side, self.sheet, st.get('sash', L.GetMinSize().width + 24))
        self.CreateStatusBar()

        for c in (self.kind, self.side):
            c.Bind(wx.EVT_RADIOBOX, self.on_settings)
        for c in (self.dots, self.marks, self.labels):
            c.Bind(wx.EVT_CHECKBOX, self.on_settings)
        self.landscape.Bind(wx.EVT_CHECKBOX, self.on_page)
        self.layer.Bind(wx.EVT_CHOICE, lambda e: self.reload())
        self.printer.Bind(wx.EVT_CHOICE, self.on_printer)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.reload()
        self.on_printer(None)
        if not self.pos:
            self.on_fill(None)
        self.CentreOnScreen()

    # --- состояние ---
    def state_file(self):
        return os.path.join(self.dir, 'layout.json')

    def load_state(self):
        try:
            with open(self.state_file(), encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_state(self):
        st = {'layer': LAYERS[self.layer.GetSelection()][0], 'negative': self.negative(),
              'toner_down': self.toner_down(), 'dots': self.dots.GetValue(), 'marks': self.marks.GetValue(),
              'labels': self.labels.GetValue(), 'landscape': self.landscape.GetValue(),
              'printer': self.printer.GetStringSelection(), 'sash': self.split.GetSashPosition(),
              'positions': [list(p) for p in self.pos]}
        try:
            os.makedirs(self.dir, exist_ok=True)
            with open(self.state_file(), 'w', encoding='utf-8') as f:
                json.dump(st, f, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def negative(self):
        return self.kind.GetSelection() == 0

    def toner_down(self):
        return self.side.GetSelection() == 0

    def page(self):
        return (297.0, 210.0) if self.landscape.GetValue() else (210.0, 297.0)

    def settings_key(self):
        return (self.layer.GetSelection(), self.negative(), self.toner_down(), self.dots.GetValue(),
                self.marks.GetValue(), self.labels.GetValue(), self.landscape.GetValue(), len(self.pos),
                id(self.b))

    def variant(self):
        n = ('1' if self.negative() else '2') + ('' if self.toner_down() else 'M')
        return '%s_%s_TONEROM_%s' % (n, 'NEGATIV' if self.negative() else 'POZITIV_LUT' if self.toner_down()
                                     else 'POZITIV', 'VNIZ' if self.toner_down() else 'VVERH')

    # --- плата ---
    def reload(self):
        with wx.BusyCursor():
            if self.editor:
                self.board = pcbnew.GetBoard()
            elif self.b is not None:
                self.board = pcbnew.LoadBoard(self.board.GetFileName())
            self.b, self.name = ep.load(self.board, LAYERS[self.layer.GetSelection()][1])
            if self.editor:
                pcbnew.Refresh()
        self.SetTitle('%s — %s (%.1f × %.1f мм)' % (TITLE, self.name, self.b.w, self.b.h))
        self.on_settings(None)

    def on_settings(self, ev):
        mirror = ep.mirror_for(self.b.layer, self.toner_down())
        self.mirror.SetLabel('→ печать %s' % ('ЗЕРКАЛЬНО' if mirror else 'без зеркала'))
        self.sheet.invalidate()
        self.update_status()

    def on_page(self, ev):
        W, H = self.page()
        self.pos = [p for p in self.pos if p[0] + self.b.w <= W and p[1] + self.b.h <= H]
        self.on_printer(None)
        self.on_settings(None)

    # --- копии ---
    def problems(self):
        """Номера копий, которые налезают друг на друга, на подписи или вне поля печати."""
        bad = set()
        rects = [self.sheet.frame_rect(p) for p in self.pos]
        W, H = self.page()
        if self.paper:
            _, _, ox, oy, aw, ah = self.paper
        else:
            ox, oy, aw, ah = 0, 0, W, H
        gx0, gy0, gx1, gy1 = ep.free_area(W, H, True)
        for i, (x, y, w, h) in enumerate(rects):
            if x < ox or y < oy or x + w > ox + aw or y + h > oy + ah:
                bad.add(i)
            if self.labels.GetValue() and (y < gy0 or y + h > gy1 or x < gx0):
                bad.add(i)
            for j in range(i):
                X, Y, Ww, Hh = rects[j]
                if x < X + Ww and X < x + w and y < Y + Hh and Y < y + h:
                    bad.update((i, j))
        return bad

    def add_copy(self, near=None):
        W, H = self.page()
        fw, fh = self.b.w + 2 * ep.FRAME, self.b.h + 2 * ep.FRAME
        gx0, gy0, gx1, gy1 = ep.free_area(W, H, self.labels.GetValue())
        rects = [self.sheet.frame_rect(p) for p in self.pos]

        def free(x, y):
            return all(x + fw + ep.GAP <= X or X + Ww + ep.GAP <= x or y + fh + ep.GAP <= Y or Y + Hh + ep.GAP <= y
                       for X, Y, Ww, Hh in rects)
        spot = None
        y = gy0
        while spot is None and y + fh <= gy1:
            x = gx0
            while x + fw <= gx1:
                if free(x, y):
                    spot = (x, y)
                    break
                x += 1.0
            y += 1.0
        if spot is None:
            bx, by = self.pos[near if near is not None else -1] if self.pos else (gx0 + ep.FRAME, gy0 + ep.FRAME)
            spot = (bx + 5 - ep.FRAME, by + 5 - ep.FRAME)
            self.SetStatusText('Свободного места нет — копия положена поверх, перетащи её')
        self.pos.append((spot[0] + ep.FRAME, spot[1] + ep.FRAME))
        self.sheet.sel = len(self.pos) - 1
        self.sheet.invalidate()
        self.update_status()

    def remove_copy(self):
        i = self.sheet.sel if self.sheet.sel is not None else len(self.pos) - 1
        if 0 <= i < len(self.pos):
            del self.pos[i]
        self.sheet.sel = None
        self.sheet.invalidate()
        self.update_status()

    def on_fill(self, ev):
        W, H, self.pos = ep.auto_positions(self.b, 0, self.labels.GetValue(), self.page())
        self.sheet.sel = None
        self.sheet.invalidate()
        self.update_status()

    def on_clear(self, ev):
        self.pos = []
        self.sheet.sel = None
        self.sheet.invalidate()
        self.update_status()

    def update_status(self):
        bad = self.problems()
        txt = 'Копий: %d' % len(self.pos)
        if bad:
            txt += '  ·  с красной рамкой: %d (налезают или вне поля печати)' % len(bad)
        if self.sheet.sel is not None and self.sheet.sel < len(self.pos):
            x, y = self.pos[self.sheet.sel]
            txt += '  ·  выбрана №%d: %.1f, %.1f мм от угла листа' % (self.sheet.sel + 1, x, y)
        self.SetStatusText(txt)

    # --- принтер ---
    def on_printer(self, ev):
        name = self.printer.GetStringSelection()
        dm, info = pr.load_profile(name)
        self.profile.Wrap(-1)       # wx не переносит заново на ту же ширину — сначала сброс
        self.profile.SetLabel('Профиль: ' + info)
        self.profile.Wrap(self.wrap)
        self.profile.InvalidateBestSize()
        self.panel.Layout()
        self.panel.FitInside()
        try:
            self.paper = pr.page_info(name, dm, self.landscape.GetValue())
        except OSError:
            self.paper = None
        self.sheet.invalidate()

    def on_film(self, ev):
        name = self.printer.GetStringSelection()
        try:
            with wx.BusyCursor():
                info = pr.film_max(name)
        except OSError as e:
            wx.MessageBox('Не получилось: %s\n\nОткрой «Настройки драйвера…» и выставь вручную.' % e, TITLE)
            return
        self.on_printer(None)
        self.SetStatusText('Профиль «плёнка» сохранён: ' + info)

    def on_driver(self, ev):
        name = self.printer.GetStringSelection()
        try:
            if pr.driver_dialog(name, self.GetHandle()):
                self.on_printer(None)
        except OSError as e:
            wx.MessageBox(str(e), TITLE)

    # --- вывод ---
    def ops(self):
        W, H = self.page()
        return W, H, ep.sheet_ops(self.b, self.name, W, H, self.pos, self.negative(), self.toner_down(),
                                  self.dots.GetValue(), self.marks.GetValue(), self.labels.GetValue())

    def on_print(self, ev):
        if not self.pos:
            return
        name = self.printer.GetStringSelection()
        dm, info = pr.load_profile(name)
        msg = 'Печатать %d копий (%s, %s) на\n%s?\n\nПрофиль: %s' % (
            len(self.pos), 'негатив' if self.negative() else 'позитив',
            'зеркально' if ep.mirror_for(self.b.layer, self.toner_down()) else 'без зеркала', name, info)
        if self.problems():
            msg += '\n\nВНИМАНИЕ: есть копии с красной рамкой — налезают или выходят за поле печати.'
        if wx.MessageBox(msg, TITLE, wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
            return
        self.save_state()
        try:
            with wx.BusyCursor():
                W, H, ops = self.ops()
                pr.print_ops(name, W, H, ops, '%s %s' % (self.name, self.variant()), dm)
        except OSError as e:
            wx.MessageBox('Печать не удалась: %s' % e, TITLE)
            return
        self.SetStatusText('Отправлено на %s' % name)

    def on_pdf(self, ev):
        self.save_state()
        f = os.path.join(self.dir, self.variant() + '.pdf')
        try:
            W, H, ops = self.ops()
            ep.write_pdf(f, W, H, ops, '%s %s %s' % (self.name, self.board.GetLayerName(self.b.layer),
                                                    self.variant()))
        except PermissionError:
            wx.MessageBox('Не могу записать %s — закрой этот PDF и нажми ещё раз.' % f, TITLE)
            return
        self.SetStatusText('Сохранено: ' + f)
        os.startfile(f)

    def on_close(self, ev):
        self.save_state()
        ev.Skip()


# --- кнопка в редакторе плат ---

class EtchPrintPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = TITLE
        self.category = 'Печать'
        self.description = 'Лист A4 с копиями платы: негатив/позитив, тонером вниз/вверх, печать 1:1 с профилем плёнки'
        self.show_toolbar_button = True
        for icon in (os.path.join(HERE, 'icon.png'), os.path.join(plugin_dir(), 'etch_print.png')):
            if os.path.exists(icon):
                self.icon_file_name = self.dark_icon_file_name = icon
                break

    def Run(self):
        board = pcbnew.GetBoard()
        if not board.GetFileName():
            wx.MessageBox('Сначала сохрани плату — раскладка и PDF лежат в папке etch рядом с ней.', TITLE)
            return
        parent = next((w for w in wx.GetTopLevelWindows() if w.GetName() == 'PcbFrame'), None)
        EtchFrame(parent, board, editor=True).Show()


# --- установка: пакет для менеджера плагинов KiCad и загрузчик из репозитория ---

KICAD_DOCS = os.path.join(os.path.expanduser('~'), 'Documents', 'KiCad', '10.0')
PCM_DIR = os.path.join(KICAD_DOCS, '3rdparty', 'plugins', PCM_ID.replace('.', '_'))
PACKAGE = os.path.join(HERE, 'etch_print_kicad_plugin.zip')


def plugin_dir():
    return os.path.join(KICAD_DOCS, 'scripting', 'plugins')


LOADER = '''# Кнопка «%s» в редакторе плат прямо из репозитория (etch_window.py --install).
# Если пакет поставлен менеджером плагинов KiCad — кнопку даёт он, а этот загрузчик молчит.
import os
import sys
if not os.path.isdir(r'%s'):
    sys.path.insert(0, r'%s')
    import etch_window
    etch_window.EtchPrintPlugin().register()
'''

METADATA = {
    '$schema': 'https://go.kicad.org/pcm/schemas/v1',
    'name': TITLE,
    'description': 'Шаблоны 1:1 для фоторезиста и ЛУТ: негатив/позитив, зеркало, копии на листе A4, '
                   'печать прямо на принтер с профилем «плёнка».',
    'description_full': 'Окно печати для домашнего травления плат. Лист A4 как на предварительном просмотре: '
                        'копии платы таскаются мышкой, «+ копия», «заполнить лист». Негатив (плёночный '
                        'фоторезист) или позитив (ЛУТ); «тонером вниз / вверх» — зеркало считается само. '
                        'Печать на принтер Windows в масштабе 1:1 без просмотрщика PDF; профиль принтера '
                        '«плёнка: максимум» (тип бумаги «прозрачная плёнка», лучшее качество, экономия тонера '
                        'выкл.) или любые настройки драйвера запоминаются. Точки под сверло, уголки, линейки '
                        '100 мм для проверки масштаба. Только Windows.',
    'identifier': PCM_ID,
    'type': 'plugin',
    'author': {'name': 'Aleksei Subbotin', 'contact': {'github': 'https://github.com/Aleksei327'}},
    'license': 'CC-BY-NC-ND-4.0',
    'resources': {'homepage': 'https://github.com/Aleksei327/ESP32-C5-OBD2-Scanner'},
    'tags': ['fabrication', 'printing', 'photoresist'],
    'versions': [{'version': VERSION, 'status': 'stable', 'kicad_version': '9.0', 'runtime': 'swig',
                  'platforms': ['windows']}],
}

PKG_INIT = '''# Пакет «%s» для менеджера плагинов KiCad (собран etch_window.py --pack)
from .etch_window import EtchPrintPlugin
EtchPrintPlugin().register()
''' % TITLE


def make_icon(path, size=24):
    """Значок: чёрная плёнка с прозрачными дорожками и пятаками (нарисован в сетке 24x24)."""
    bmp = wx.Bitmap.FromRGBA(size, size, 0, 0, 0, 0)
    dc = wx.MemoryDC(bmp)
    gc = wx.GraphicsContext.Create(dc)
    gc.Scale(size / 24, size / 24)
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(20, 20, 20)))
    gc.DrawRoundedRectangle(2, 1, 20, 22, 3)
    gc.SetPen(wx.Pen(wx.Colour(250, 250, 250), 2))
    gc.StrokeLines([(6, 6), (12, 6), (12, 12), (18, 12)])
    gc.StrokeLines([(6, 18), (12, 18), (16, 14)])
    gc.SetPen(wx.TRANSPARENT_PEN)
    gc.SetBrush(wx.Brush(wx.Colour(250, 250, 250)))
    for x, y in ((6, 6), (18, 12), (6, 18)):
        gc.DrawEllipse(x - 2.5, y - 2.5, 5, 5)
    del gc
    dc.SelectObject(wx.NullBitmap)
    bmp.SaveFile(path, wx.BITMAP_TYPE_PNG)


def pack():
    """etch_print_kicad_plugin.zip рядом со скриптом: KiCad > Менеджер плагинов и библиотек >
    Установить из файла. Ставится в Documents\\KiCad\\<версия>\\3rdparty и переживает переустановку KiCad."""
    app = wx.App(False)
    tmp = os.path.join(HERE, '_pack')
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, 'resources'))
    make_icon(os.path.join(tmp, 'icon24.png'), 24)
    make_icon(os.path.join(tmp, 'resources', 'icon.png'), 64)
    del app
    with zipfile.ZipFile(PACKAGE, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('metadata.json', json.dumps(METADATA, ensure_ascii=False, indent=2))
        z.writestr('plugins/__init__.py', PKG_INIT)
        for name in ('etch_window.py', 'etch_print.py', 'etch_printer.py'):
            z.write(os.path.join(HERE, name), 'plugins/' + name)
        z.write(os.path.join(tmp, 'icon24.png'), 'plugins/icon.png')
        z.write(os.path.join(tmp, 'resources', 'icon.png'), 'resources/icon.png')
    shutil.rmtree(tmp, ignore_errors=True)
    print('пакет:', PACKAGE)
    print('KiCad > Менеджер плагинов и библиотек > Установить из файла… > этот zip')


def install():
    """Загрузчик для разработки: кнопка берёт модули прямо из репозитория."""
    d = plugin_dir()
    os.makedirs(d, exist_ok=True)
    old = os.path.join(d, 'etch_print_loader.py')
    if os.path.exists(old):
        os.remove(old)
    with open(os.path.join(d, 'etch_window_loader.py'), 'w', encoding='utf-8') as f:
        f.write(LOADER % (TITLE, PCM_DIR, HERE))
    app = wx.App(False)
    make_icon(os.path.join(d, 'etch_print.png'))
    del app
    print('загрузчик установлен в', d)
    print('перезапусти KiCad: кнопка на верхней панели редактора плат и в Инструменты > Внешние модули')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if '--install' in sys.argv:
        install()
        return
    if '--pack' in sys.argv:
        pack()
        return
    path = args[0] if args else os.path.join(os.path.dirname(HERE), 'scaner_v1.kicad_pcb')
    app = wx.App(False)
    frame = EtchFrame(None, pcbnew.LoadBoard(path), editor=False)
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
