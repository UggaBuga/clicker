# -*- coding: utf-8 -*-
"""Общие утилиты пробников: поиск окна, снимок клиентской области,
подсчёт различий, постинг сообщений. Цель задаётся подстрокой заголовка."""
import ctypes
import time
from ctypes import wintypes

import win32gui
import win32con
from PIL import Image, ImageChops

_u = ctypes.windll.user32
_g = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', ctypes.c_ulong), ('biWidth', ctypes.c_long),
                ('biHeight', ctypes.c_long), ('biPlanes', ctypes.c_ushort),
                ('biBitCount', ctypes.c_ushort), ('biCompression', ctypes.c_ulong),
                ('biSizeImage', ctypes.c_ulong), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', ctypes.c_ulong),
                ('biClrImportant', ctypes.c_ulong)]


def find_window(title_sub):
    """HWND первого видимого окна, чей заголовок содержит подстроку."""
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = ctypes.create_unicode_buffer(256)
        _u.GetWindowTextW(hwnd, n, 256)
        if title_sub.lower() in n.value.lower():
            found.append(hwnd)
        return True

    _u.EnumWindows(cb, 0)
    return found[0] if found else None


def capture_client(hwnd):
    """Содержимое клиентской области окна — даже если перекрыто."""
    w, h = win32gui.GetClientRect(hwnd)[2:]
    hdc_win = _u.GetDC(hwnd)
    hdc_mem = _g.CreateCompatibleDC(hdc_win)
    hbmp = _g.CreateCompatibleBitmap(hdc_win, w, h)
    _g.SelectObject(hdc_mem, hbmp)
    _u.PrintWindow(hwnd, hdc_mem, 3)  # CLIENTONLY | RENDERFULLCONTENT
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


def diff_count(a, b, threshold=60):
    d = ImageChops.difference(a, b)
    return sum(1 for px in d.getdata() if sum(px) > threshold)


def bbox_client(hwnd, a, b, threshold=90, step=2):
    """bbox изменений в экранных координатах для конкретного окна."""
    d = ImageChops.difference(a, b)
    px = d.load()
    x0 = y0 = 10**9
    x1 = y1 = -1
    n = 0
    w, h = d.size
    for y in range(0, h, step):
        for x in range(0, w, step):
            if sum(px[x, y]) > threshold:
                n += 1
                x0 = min(x0, x); x1 = max(x1, x)
                y0 = min(y0, y); y1 = max(y1, y)
    if n < 200:
        return None, n
    ox, oy = win32gui.ClientToScreen(hwnd, (0, 0))
    return (ox + x0, oy + y0, ox + x1, oy + y1), n


def client_point(hwnd, fx, fy):
    """Точка клиентской области (доли fx, fy) в экранных координатах."""
    ox, oy = win32gui.ClientToScreen(hwnd, (0, 0))
    w, h = win32gui.GetClientRect(hwnd)[2:]
    return ox + int(w * fx), oy + int(h * fy)


def post(hwnd, x, y, msg, w=0):
    cx, cy = win32gui.ScreenToClient(hwnd, (x, y))
    lp = (cy << 16) | (cx & 0xFFFF)
    win32gui.PostMessage(hwnd, msg, w, lp)


def post_moves(hwnd, x, y, n, gap=0.0):
    for _ in range(n):
        post(hwnd, x, y, win32con.WM_MOUSEMOVE)
        if gap:
            time.sleep(gap)


def get_cursor():
    pt = wintypes.POINT()
    _u.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def set_cursor(x, y):
    _u.SetCursorPos(int(x), int(y))


def switch_to(hwnd):
    _u.SwitchToThisWindow(hwnd, True)
