# -*- coding: utf-8 -*-
"""Живой тест сценария A (окно игры поверх на время нажатия) и
сценария B (тихий фокус) на открытом клиенте игры."""
import time

import win32gui

from probe_common import find_window, capture_client, diff_count, switch_to
import clicker

GAME = find_window('Wurm Online')
assert GAME, 'окно игры не найдено'
print('hwnd игры:', GAME, win32gui.GetWindowText(GAME))
print('iconic:', win32gui.IsIconic(GAME), 'visible:', win32gui.IsWindowVisible(GAME))

prev_fg = win32gui.GetForegroundWindow()
print('прежний fg:', prev_fg, win32gui.GetWindowText(prev_fg)[:60])

# --- Сценарий B: тихий фокус (ожидаем attach=0 без прав администратора) ---
with clicker.quiet_focus(GAME) as ok:
    print('quiet_focus ok =', ok)

# --- Сценарий A: поднять окно поверх, нажать Enter (чат), снять кадры ---
before = capture_client(GAME)
t0 = time.time()
with clicker.window_upfront(GAME):
    fg_mid = win32gui.GetForegroundWindow()
    print('fg внутри upfront =', fg_mid, win32gui.GetWindowText(fg_mid)[:60])
    clicker.bg_key_press(GAME, 'enter')
    time.sleep(0.6)
after = capture_client(GAME)
d = diff_count(before, after)
print('diff пикселей после Enter:', d)
after.save('probe_chat_open.png')

# Esc — закрыть чат, если открылся
clicker.bg_key_press(GAME, 'esc')
time.sleep(0.6)
closed = capture_client(GAME)
d2 = diff_count(after, closed)
print('diff пикселей после Esc:', d2)
closed.save('probe_chat_closed.png')

# вернуть прежний fg (upfront уже вернул; страховка)
if win32gui.IsWindow(prev_fg):
    switch_to(prev_fg)
print('fg в конце:', win32gui.GetForegroundWindow())
print('ГОТОВО')
