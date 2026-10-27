# -*- coding: utf-8 -*-
"""Пробник фонового клика: реагирует ли окно на PostMessage без фокуса.
Использование: python probe_bgclick.py <подстрока заголовка окна>"""
import sys
import time
import tkinter as tk

import win32gui
import win32con

from probe_common import (find_window, capture_client, diff_count,
                          client_point, post, switch_to)

target = find_window(sys.argv[1] if len(sys.argv) > 1 else '')
assert target, 'окно не найдено — укажи подстроку заголовка'
print('цель:', sys.argv[1])

px, py = client_point(target, 0.5, 0.45)
qx, qy = client_point(target, 0.52, 0.47)

# --- фаза 1: фокус на другое окно ---
d = tk.Tk()
d.title('probe')
d.geometry('500x160+30+1100')
tk.Label(d, text='Тест фонового ввода, ~15 секунд…', font=('Arial', 12)).pack(pady=20)
d.update()
d.attributes('-topmost', True)
switch_to(d.winfo_id())
time.sleep(1.5)
unfocused = win32gui.GetForegroundWindow() != target
print('цель без фокуса:', unfocused)

if unfocused:
    base1 = capture_client(target)
    time.sleep(0.8)
    base2 = capture_client(target)
    baseline = diff_count(base1, base2)
    print(f'фон без кликов (живость рендера): {baseline} пикселей')

    before = capture_client(target)
    post(target, px, py, win32con.WM_MOUSEMOVE)
    time.sleep(0.06)
    post(target, px, py, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON)
    time.sleep(0.06)
    post(target, px, py, win32con.WM_RBUTTONUP)
    time.sleep(1.2)
    after = capture_client(target)
    changed = diff_count(before, after)
    print(f'фон + ПКМ: {changed} пикселей')
    # закрыть возможное меню ЛКМ рядом
    post(target, qx, qy, win32con.WM_MOUSEMOVE)
    post(target, qx, qy, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON)
    time.sleep(0.05)
    post(target, qx, qy, win32con.WM_LBUTTONUP)
    time.sleep(0.6)

    bg_works = changed > baseline * 3 if baseline > 50 else changed > 200
    print('ВЫВОД (фон):', 'окно ОБРАБОТАЛО клик без фокуса' if bg_works
          else 'реакции на клик без фокуса НЕТ')
else:
    print('не удалось отвести фокус — пропуск фоновой фазы')

# --- фаза 2: контроль с фокусом ---
switch_to(target)
time.sleep(1.0)
before = capture_client(target)
post(target, px, py, win32con.WM_MOUSEMOVE)
post(target, px, py, win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON)
time.sleep(0.06)
post(target, px, py, win32con.WM_RBUTTONUP)
time.sleep(1.2)
after = capture_client(target)
changed_fg = diff_count(before, after)
post(target, qx, qy, win32con.WM_MOUSEMOVE)
post(target, qx, qy, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON)
time.sleep(0.05)
post(target, qx, qy, win32con.WM_LBUTTONUP)
time.sleep(0.4)
d.destroy()
print(f'фокус + ПКМ: {changed_fg} пикселей')
print('ВЫВОД (фокус):', 'реагирует' if changed_fg > 200 else 'НЕ реагирует')
