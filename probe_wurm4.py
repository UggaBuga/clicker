# -*- coding: utf-8 -*-
"""Точный пробник: где открывается меню ПКМ при разных способах клика.
Детектор — bounding box меню на скриншоте клиента."""
import ctypes
from ctypes import wintypes
import time
import tkinter as tk

import win32gui
import win32con
from PIL import Image, ImageChops

_u = ctypes.windll.user32
_g = ctypes.windll.gdi32

# --- найти окно игры ---
GAME = None
@ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
def _cb(hwnd, _):
    global GAME
    n = ctypes.create_unicode_buffer(256)
    _u.GetWindowTextW(hwnd, n, 256)
    if 'Wurm Online' in n.value:
        GAME = hwnd
    return True
_u.EnumWindows(_cb, 0)
assert GAME, 'окно Wurm не найдено'
print('игра:', win32gui.GetWindowText(GAME)[:45], 'hwnd =', GAME)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', ctypes.c_ulong), ('biWidth', ctypes.c_long),
                ('biHeight', ctypes.c_long), ('biPlanes', ctypes.c_ushort),
                ('biBitCount', ctypes.c_ushort), ('biCompression', ctypes.c_ulong),
                ('biSizeImage', ctypes.c_ulong), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', ctypes.c_ulong),
                ('biClrImportant', ctypes.c_ulong)]


def capture_client():
    w, h = win32gui.GetClientRect(GAME)[2:]
    hdc_win = _u.GetDC(GAME)
    hdc_mem = _g.CreateCompatibleDC(hdc_win)
    hbmp = _g.CreateCompatibleBitmap(hdc_win, w, h)
    _g.SelectObject(hdc_mem, hbmp)
    _u.PrintWindow(GAME, hdc_mem, 3)
    hdr = BITMAPINFOHEADER()
    hdr.biSize = ctypes.sizeof(hdr)
    hdr.biWidth, hdr.biHeight = w, -h
    hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
    buf = (ctypes.c_char * (w * h * 4))()
    _g.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(hdr), 0)
    raw = bytearray(buf.raw)
    raw[3::4] = b'\xff' * (w * h)
    img = Image.frombytes('RGBA', (w, h), bytes(raw)).convert('RGB')
    _g.DeleteObject(hbmp); _g.DeleteDC(hdc_mem); _u.ReleaseDC(GAME, hdc_win)
    return img


def client_point(fx, fy):
    ox, oy = win32gui.ClientToScreen(GAME, (0, 0))
    w, h = win32gui.GetClientRect(GAME)[2:]
    return ox + int(w * fx), oy + int(h * fy)


def post(x, y, msg, w=0):
    cx, cy = win32gui.ScreenToClient(GAME, (x, y))
    lp = (cy << 16) | (cx & 0xFFFF)
    win32gui.PostMessage(GAME, msg, w, lp)


def menu_bbox(a, b):
    """bbox изменившихся пикселей в экранных координатах."""
    d = ImageChops.difference(a, b)
    px = d.load()
    x0 = y0 = 10**9; x1 = y1 = -1; n = 0
    w, h = d.size
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if sum(px[x, y]) > 90:
                n += 1
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    if n < 200:
        return None, n
    ox, oy = win32gui.ClientToScreen(GAME, (0, 0))
    return (ox + x0, oy + y0, ox + x1, oy + y1), n


orig_fg = win32gui.GetForegroundWindow()
cur = wintypes.POINT(); _u.GetCursorPos(ctypes.byref(cur))
orig_pos = (cur.x, cur.y)

P = client_point(0.55, 0.55)   # физическая мышь
T = client_point(0.25, 0.25)   # цель клика

d = tk.Tk()
d.title('probe4'); d.geometry('420x100+30+1100')
tk.Label(d, text='Пробник позиции клика, ~25 сек…',
         font=('Arial', 12)).pack(pady=16)
d.update(); d.attributes('-topmost', True)
_u.SwitchToThisWindow(d.winfo_id(), True)
time.sleep(1.0)
print('игра без фокуса:', win32gui.GetForegroundWindow() != GAME)


def esc():
    post(0, 0, win32con.WM_KEYDOWN, win32con.VK_ESCAPE)
    time.sleep(0.04)
    post(0, 0, win32con.WM_KEYUP, win32con.VK_ESCAPE)


def trial(name, fn, shot):
    _u.SetCursorPos(*P)
    time.sleep(0.4)
    before = capture_client()
    fn()
    time.sleep(0.8)
    after = capture_client()
    bbox, n = menu_bbox(before, after)
    after.save(shot)
    if bbox:
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        dT = ((cx-T[0])**2 + (cy-T[1])**2) ** .5
        dP = ((cx-P[0])**2 + (cy-P[1])**2) ** .5
        print(f'{name}: меню ({bbox[0]},{bbox[1]})-({bbox[2]},{bbox[3]}), '
              f'центр=({cx:.0f},{cy:.0f}), n={n} -> '
              + ('ЦЕЛЬ' if dT < dP else 'ФИЗ.МЫШЬ'))
    else:
        print(f'{name}: меню НЕ открылось (n={n})')
    esc()
    time.sleep(0.5)


def clickA():   # как сейчас в кликере: 2 move + кнопка
    post(*T, win32con.WM_MOUSEMOVE); time.sleep(0.004)
    post(*T, win32con.WM_MOUSEMOVE); time.sleep(0.004)
    post(*T, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON)
    time.sleep(0.03)
    post(*T, win32con.WM_RBUTTONUP)

def clickB():   # телепорт к T, пауза, move+кнопка, курсор остаётся на T
    _u.SetCursorPos(*T); time.sleep(0.12)
    post(*T, win32con.WM_MOUSEMOVE)
    post(*T, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON)
    time.sleep(0.03)
    post(*T, win32con.WM_RBUTTONUP)

def clickC():   # телепорт к T, кнопка, вернуть курсор на P
    _u.SetCursorPos(*T); time.sleep(0.012)
    post(*T, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON)
    time.sleep(0.03)
    post(*T, win32con.WM_RBUTTONUP)
    _u.SetCursorPos(*P)

trial('A post-only          ', clickA, 'trialA.png')
trial('B телепорт+удержание ', clickB, 'trialB.png')
trial('C телепорт+возврат   ', clickC, 'trialC.png')

_u.SetCursorPos(*orig_pos)
_u.SwitchToThisWindow(orig_fg, True)
d.destroy()
print('готово')
