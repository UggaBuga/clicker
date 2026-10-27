# -*- coding: utf-8 -*-
"""Тесты: позиция мыши для фоновых нажатий клавиш."""
import time
import tkinter as tk

import clicker
import os as _os, tempfile as _tf
clicker.STATE_PATH = _os.path.join(_tf.gettempdir(), "state_test_keypos.json")
_os.path.exists(clicker.STATE_PATH) and _os.remove(clicker.STATE_PATH)
from clicker import ClickerApp, bg_mouse_move

# --- 1) bg_mouse_move шлёт WM_MOUSEMOVE ---
msgs = []
real_pm, real_sc = clicker.win32gui.PostMessage, clicker.win32gui.ScreenToClient
clicker.win32gui.PostMessage = lambda hwnd, msg, wp, lp: msgs.append(msg)
clicker.win32gui.ScreenToClient = lambda hwnd, p: p
try:
    bg_mouse_move(123, 40, 50)
finally:
    clicker.win32gui.PostMessage, clicker.win32gui.ScreenToClient = real_pm, real_sc
assert msgs and all(m == clicker.win32con.WM_MOUSEMOVE for m in msgs), msgs
print('1. bg_mouse_move шлёт WM_MOUSEMOVE — OK')

# --- 2) фоновое нажатие клавиши: сначала WM_MOUSEMOVE, потом KEYDOWN ---
root = tk.Tk()
app = ClickerApp(root)

seq = []
clicker.win32gui.PostMessage = lambda hwnd, msg, wp, lp: seq.append(msg)
clicker.win32gui.ScreenToClient = lambda hwnd, p: p
clicker.win32gui.IsWindow = lambda hwnd: True
try:
    p = {'which': 'key', 'action': 'key', 'mode': 'background', 'hwnd': 1,
         'key': 'a', 'pos': (40, 50),
         'quiet_focus': False, 'bring_up': False,
         'interval': 100, 'jitter': 0, 'repeats': 0}
    app._do_action(p)
finally:
    clicker.win32gui.PostMessage, clicker.win32gui.ScreenToClient = real_pm, real_sc
assert seq[0] == clicker.win32con.WM_MOUSEMOVE, f'первое: {seq[0]}'
assert clicker.win32con.WM_KEYDOWN in seq and clicker.win32con.WM_KEYUP in seq
assert seq.index(clicker.win32con.WM_MOUSEMOVE) < seq.index(clicker.win32con.WM_KEYDOWN)
print('2. Клавиша с позицией: WM_MOUSEMOVE перед KEYDOWN — OK')

# --- 3) collect_params: фон + фиксированная точка ---
def pump(n=3):
    for _ in range(n):
        root.update(); time.sleep(0.01)

app.key_mode.set('background')
app.key_pos_mode.set('fixed')
try:
    app.collect_params('key')
    raise AssertionError('должна быть ошибка без захваченной точки')
except ValueError:
    pass
app.key_fixed_pos = type('P', (), {'x': 100, 'y': 200})()
p = app.collect_params('key')
assert p['pos'] == (100, 200), p.get('pos')
app.key_pos_mode.set('none')
p = app.collect_params('key')
assert 'pos' not in p
app.key_mode.set('active')
print('3. collect_params: точка мыши для клавиш — OK')

# --- 4) профиль сохраняет точку клавиш ---
app.key_pos_mode.set('fixed')  # режим фиксированной точки перед сбором профиля
snap = app._gather_settings()
assert snap['key']['fixed'] == [100, 200]
app.key_fixed_pos = None
app.key_pos_mode.set('none')
app._apply_settings(snap)
assert app.key_pos_mode.get() == 'fixed'
assert app.key_fixed_pos.x == 100 and app.key_fixed_pos.y == 200
print('4. Профили: точка мыши клавиш сохраняется — OK')

print('\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ')
