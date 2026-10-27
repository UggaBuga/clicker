# -*- coding: utf-8 -*-
"""Пробник гонки курсора: перебивает ли физическая мышь WM_MOUSEMOVE.
Детектор — позиция всплывающего меню ПКМ (bbox изменений на снимке).
Использование: python probe_position.py <подстрока заголовка окна>"""
import sys
import time
import tkinter as tk

import win32con

from probe_common import (find_window, capture_client, diff_count,
                          bbox_client, client_point, post, post_moves,
                          get_cursor, set_cursor, switch_to)

target = find_window(sys.argv[1] if len(sys.argv) > 1 else '')
assert target, 'окно не найдено — укажи подстроку заголовка'

orig_fg = win32gui.GetForegroundWindow()
orig_pos = get_cursor()

P = client_point(target, 0.55, 0.55)   # физическая мышь
T = client_point(target, 0.25, 0.25)   # цель клика

d = tk.Tk()
d.title('probe')
d.geometry('420x100+30+1100')
tk.Label(d, text='Пробник позиции клика, ~25 сек…',
         font=('Arial', 12)).pack(pady=16)
d.update()
d.attributes('-topmost', True)
switch_to(d.winfo_id())
time.sleep(1.0)
print('цель без фокуса:', win32gui.GetForegroundWindow() != target)


def esc():
    post(target, 0, 0, win32con.WM_KEYDOWN, win32con.VK_ESCAPE)
    time.sleep(0.04)
    post(target, 0, 0, win32con.WM_KEYUP, win32con.VK_ESCAPE)


def rclick(x, y):
    post(target, x, y, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON)
    time.sleep(0.03)
    post(target, x, y, win32con.WM_RBUTTONUP)


def trial(name, fn, shot):
    set_cursor(*P)
    time.sleep(0.4)
    before = capture_client(target)
    fn()
    time.sleep(0.8)
    after = capture_client(target)
    changed = diff_count(before, after)
    bbox, n = bbox_client(target, before, after)
    after.save(shot)
    if bbox:
        cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
        dT = ((cx - T[0])**2 + (cy - T[1])**2) ** .5
        dP = ((cx - P[0])**2 + (cy - P[1])**2) ** .5
        print(f'{name}: изменено {changed} пикс., центр меню ({cx:.0f},{cy:.0f}) -> '
              + ('ЦЕЛЬ' if dT < dP else 'ФИЗ.МЫШЬ'))
    else:
        print(f'{name}: меню не открылось (изменений {changed})')
    esc()
    time.sleep(0.5)


def clickA():   # только сообщения, без телепорта
    post_moves(target, *T, 2, gap=0.004)
    rclick(*T)

def clickB():   # телепорт к T с удержанием, кнопка, курсор остаётся
    set_cursor(*T)
    time.sleep(0.12)
    post(target, *T, win32con.WM_MOUSEMOVE)
    rclick(*T)

def clickC():   # телепорт к T, кнопка, курсор сразу возвращён
    set_cursor(*T)
    time.sleep(0.012)
    rclick(*T)
    set_cursor(*P)


trial('A post-only           ', clickA, 'trialA.png')
trial('B телепорт+удержание  ', clickB, 'trialB.png')
trial('C телепорт+возврат    ', clickC, 'trialC.png')

set_cursor(*orig_pos)
switch_to(orig_fg)
d.destroy()
print('готово')
