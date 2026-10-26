# -*- coding: utf-8 -*-
"""Варианты обхода GetCursorPos: телепорт курсора на точку клика."""
import ctypes
from ctypes import wintypes
import threading
import time
import tkinter as tk

import win32gui
import win32con

from probe_wurm2 import (GAME, client_point, capture_client, diff_count,
                         centroid_bbox, rclick, send_esc)

_u = ctypes.windll.user32

orig_fg = win32gui.GetForegroundWindow()
cur = wintypes.POINT()
_u.GetCursorPos(ctypes.byref(cur))
orig_pos = (cur.x, cur.y)

P = client_point(0.5, 0.5)
T = client_point(0.30, 0.30)

d = tk.Tk()
d.title('probe3')
d.geometry('420x100+30+1100')
tk.Label(d, text='Пробник телепорта курсора, ~20 сек…',
         font=('Arial', 12)).pack(pady=16)
d.update()
d.attributes('-topmost', True)
_u.SwitchToThisWindow(d.winfo_id(), True)
time.sleep(1.0)
_u.SetCursorPos(*P)
time.sleep(0.3)


def trial(name, hold_s):
    _u.SetCursorPos(*P)
    time.sleep(0.3)
    before = capture_client(GAME)
    _u.SetCursorPos(*T)
    time.sleep(hold_s)
    rclick(*T)
    time.sleep(0.9)
    after = capture_client(GAME)
    changed = diff_count(before, after)
    c = centroid_bbox(before, after)
    print(f'{name}: изменено {changed} пикс., центроид {c}')
    if c:
        dT = ((c[0]-T[0])**2 + (c[1]-T[1])**2) ** 0.5
        dP = ((c[0]-P[0])**2 + (c[1]-P[1])**2) ** 0.5
        print(f'   до цели T={dT:.0f}px, до физ.мыши P={dP:.0f}px -> '
              + ('ЦЕЛЬ' if dT < dP else 'ФИЗ.МЫШЬ'))
    send_esc()
    time.sleep(0.6)


trial('C: телепорт, удержание 150мс', 0.15)
trial('D: телепорт, удержание 20мс', 0.02)

_u.SetCursorPos(*orig_pos)
_u.SwitchToThisWindow(orig_fg, True)
d.destroy()
print('готово')
