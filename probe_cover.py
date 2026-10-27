# -*- coding: utf-8 -*-
"""Пробник: перестаёт ли целевое окно обрабатывать ввод,
когда его полностью перекрывает другое окно."""
import sys
import time
import tkinter as tk

import win32gui
import win32con

from probe_common import (find_window, capture_client, diff_count,
                          bbox_client, client_point, post, post_moves,
                          get_cursor, set_cursor, switch_to)

target = find_window(sys.argv[1] if len(sys.argv) > 1 else '')
assert target, 'цель не найдена'
print('цель:', win32gui.GetWindowText(target)[:50])

orig_fg = win32gui.GetForegroundWindow()
orig_pos = get_cursor()

P = client_point(target, 0.55, 0.55)
T = client_point(target, 0.25, 0.25)

# перекрывает ли цель кто-то полностью прямо сейчас
tr = win32gui.GetWindowRect(target)
overlap = None
for h, t in []:
    pass
def covers():
    """Найти окна, полностью перекрывающие цель (упрощённо: видимые, fg-area)."""
    res = []
    def cb(hwnd, _):
        if hwnd == target or not win32gui.IsWindowVisible(hwnd):
            return True
        try:
            r = win32gui.GetWindowRect(hwnd)
        except Exception:
            return True
        tx0, ty0, tx1, ty1 = tr
        ax0, ay0 = max(tx0, r[0]), max(ty0, r[1])
        ax1, ay1 = min(tx1, r[2]), min(ty1, r[3])
        area_c = max(0, ax1 - ax0) * max(0, ay1 - ay0)
        area_t = (tx1 - tx0) * (ty1 - ty0)
        if area_t > 0 and area_c / area_t > 0.98:
            res.append((hwnd, win32gui.GetWindowText(hwnd)[:45],
                        area_c / area_t))
        return True
    win32gui.EnumWindows(cb, None)
    return res

def esc():
    post(target, 0, 0, win32con.WM_KEYDOWN, win32con.VK_ESCAPE)
    time.sleep(0.04)
    post(target, 0, 0, win32con.WM_KEYUP, win32con.VK_ESCAPE)

def trial(name, cover):
    set_cursor(*P)
    time.sleep(0.3)
    cov = None
    if cover:
        cov = tk.Tk()
        sw, sh = cov.winfo_screenwidth(), cov.winfo_screenheight()
        cov.geometry(f'{sw}x{sh}+0+0')
        tk.Label(cov, text='перекрытие', font=('Arial', 24)).pack(pady=40)
        cov.update()
        cov.attributes('-topmost', True)
        switch_to(cov.winfo_id())
        time.sleep(0.8)
        print(f'  перекрытие: {[(hex(h), t) for h, t, _ in covers()]}')
    before = capture_client(target)
    if cover:
        time.sleep(0.8)
        base2 = capture_client(target)
        print(f'  живость рендера под перекрытием: {diff_count(before, base2)} пикс.')
    post_moves(target, *T, 2, gap=0.004)
    post(target, *T, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON)
    time.sleep(0.03)
    post(target, *T, win32con.WM_RBUTTONUP)
    time.sleep(1.2)
    after = capture_client(target)
    changed = diff_count(before, after)
    bbox, n = bbox_client(target, before, after)
    if cover and cov:
        cov.destroy()
        time.sleep(0.6)
    print(f'{name}: изменено {changed} пикс., меню: {"ДА " + str(bbox) if bbox else "нет"}')
    after.save(f'cover_{name.replace(" ", "_")}.png')
    esc()
    time.sleep(0.5)
    return bool(bbox)

print('перекрывающие окна сейчас:', [(hex(h), t, f'{a:.0%}') for h, t, a in covers()])

rA = trial('A_как_есть', cover=False)
rB = trial('B_перекрыто', cover=True)

set_cursor(*orig_pos)
switch_to(orig_fg)
print(f'ИТОГ: как есть = {"работает" if rA else "МОЛЧИТ"}, '
      f'перекрыто = {"работает" if rB else "МОЛЧИТ"}')
