# -*- coding: utf-8 -*-
"""Пробник гонки курсора: физическая мышь над игрой vs WM_MOUSEMOVE.
ПКМ открывает меню там, где GLFW думает, что курсор — по позиции меню судим."""
import ctypes
from ctypes import wintypes
import threading
import time
import tkinter as tk

import win32gui
import win32con
from PIL import Image, ImageChops

_u = ctypes.windll.user32
_g = ctypes.windll.gdi32
GAME = 18156224  # окно Wurm (актуальный hwnd)


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', ctypes.c_ulong), ('biWidth', ctypes.c_long),
                ('biHeight', ctypes.c_long), ('biPlanes', ctypes.c_ushort),
                ('biBitCount', ctypes.c_ushort), ('biCompression', ctypes.c_ulong),
                ('biSizeImage', ctypes.c_ulong), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', ctypes.c_ulong),
                ('biClrImportant', ctypes.c_ulong)]


def capture_client(hwnd):
    w, h = win32gui.GetClientRect(hwnd)[2:]
    hdc_win = _u.GetDC(hwnd)
    hdc_mem = _g.CreateCompatibleDC(hdc_win)
    hbmp = _g.CreateCompatibleBitmap(hdc_win, w, h)
    _g.SelectObject(hdc_mem, hbmp)
    _u.PrintWindow(hwnd, hdc_mem, 3)
    hdr = BITMAPINFOHEADER()
    hdr.biSize = ctypes.sizeof(hdr)
    hdr.biWidth, hdr.biHeight = w, -h
    hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
    buf = (ctypes.c_char * (w * h * 4))()
    _g.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(hdr), 0)
    raw = bytearray(buf.raw)
    raw[3::4] = b'\xff' * (w * h)
    img = Image.frombytes('RGBA', (w, h), bytes(raw)).convert('RGB')
    _g.DeleteObject(hbmp)
    _g.DeleteDC(hdc_mem)
    _u.ReleaseDC(hwnd, hdc_win)
    return img


def diff_count(a, b):
    d = ImageChops.difference(a, b)
    return sum(1 for px in d.getdata() if sum(px) > 60)


def client_point(fx, fy):
    ox, oy = win32gui.ClientToScreen(GAME, (0, 0))
    w, h = win32gui.GetClientRect(GAME)[2:]
    return ox + int(w * fx), oy + int(h * fy)


def centroid_bbox(a, b):
    d = ImageChops.difference(a, b)
    px = d.load()
    xs, ys, n = 0, 0, 0
    w, h = d.size
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            if sum(px[x, y]) > 90:
                xs += x; ys += y; n += 1
    if not n:
        return None
    ox, oy = win32gui.ClientToScreen(GAME, (0, 0))
    return (ox + xs / n, oy + ys / n)


def post_moves(x, y, n, gap):
    cx, cy = win32gui.ScreenToClient(GAME, (x, y))
    lp = (cy << 16) | (cx & 0xFFFF)
    for _ in range(n):
        win32gui.PostMessage(GAME, win32con.WM_MOUSEMOVE, 0, lp)
        if gap:
            time.sleep(gap)


def rclick(x, y):
    cx, cy = win32gui.ScreenToClient(GAME, (x, y))
    lp = (cy << 16) | (cx & 0xFFFF)
    win32gui.PostMessage(GAME, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, lp)
    time.sleep(0.03)
    win32gui.PostMessage(GAME, win32con.WM_RBUTTONUP, 0, lp)


def send_esc():
    win32gui.PostMessage(GAME, win32con.WM_KEYDOWN, win32con.VK_ESCAPE, 0)
    time.sleep(0.03)
    win32gui.PostMessage(GAME, win32con.WM_KEYUP, win32con.VK_ESCAPE, 0)


# --- подготовка ---
orig_fg = win32gui.GetForegroundWindow()
cur = wintypes.POINT()
_u.GetCursorPos(ctypes.byref(cur))
orig_pos = (cur.x, cur.y)

P = client_point(0.5, 0.5)    # физическая мышь стоит в центре окна
T = client_point(0.30, 0.30)  # целевая точка клика — заметно elsewhere

d = tk.Tk()
d.title('probe2')
d.geometry('420x100+30+1100')
tk.Label(d, text='Пробник гонки курсора, ~20 сек…',
         font=('Arial', 12)).pack(pady=16)
d.update()
d.attributes('-topmost', True)
_u.SwitchToThisWindow(d.winfo_id(), True)
time.sleep(1.2)
print('игра без фокуса:', win32gui.GetForegroundWindow() != GAME)

_u.SetCursorPos(*P)
time.sleep(0.3)

# поток-«дрожание» физической мыши (имитация джиттера оптики)
wiggle_stop = threading.Event()
def wiggle():
    i = 0
    while not wiggle_stop.is_set():
        i += 1
        _u.SetCursorPos(P[0] + (i % 3) - 1, P[1] + ((i // 3) % 3) - 1)
        time.sleep(0.004)

def trial(name, moves_n, gap):
    w = threading.Thread(target=wiggle)
    w.start()
    time.sleep(0.2)
    before = capture_client(GAME)
    post_moves(*T, moves_n, gap)
    rclick(*T)
    time.sleep(0.9)
    after = capture_client(GAME)
    wiggle_stop.set(); w.join()
    wiggle_stop.clear()
    changed = diff_count(before, after)
    c = centroid_bbox(before, after)
    print(f'{name}: изменено {changed} пикс., центроид {c}')
    if c:
        dT = ((c[0]-T[0])**2 + (c[1]-T[1])**2) ** 0.5
        dP = ((c[0]-P[0])**2 + (c[1]-P[1])**2) ** 0.5
        print(f'   расстояние до цели T={dT:.0f}px, до физ. мыши P={dP:.0f}px -> '
              + ('ЦЕЛЬ' if dT < dP else 'ФИЗ.МЫШЬ'))
    send_esc()
    time.sleep(0.6)
    _u.SetCursorPos(*P)

trial('старая схема (2 move, 4мс)', 2, 0.004)
trial('плотный burst (8 move, 0мс)', 8, 0)

# уборка
_u.SetCursorPos(*orig_pos)
_u.SwitchToThisWindow(orig_fg, True)
d.destroy()
print('готово')
