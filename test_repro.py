# -*- coding: utf-8 -*-
"""Полнофиделити репродьюсер: реальный ClickerApp в фоновом режиме,
действия логируются, эффект проверяется снимками игры."""
import sys
import time
import tkinter as tk

import win32gui
import win32con

import clicker
from clicker import ClickerApp
from probe_common import (find_window, capture_client, diff_count,
                          bbox_client, client_point, post)

GAME = find_window('Wurm Online')
assert GAME, 'игра не найдена'
title = win32gui.GetWindowText(GAME)
print('цель:', title[:50])

root = tk.Tk()
app = ClickerApp(root)

# настройка как у пользователя: фоновый режим, фикс. точка, ПКМ
T = client_point(GAME, 0.25, 0.25)
app.mouse_mode.set('background')
app.pos_mode.set('fixed')
app.fixed_pos = type('P', (), {'x': T[0], 'y': T[1]})()
app.pos_lbl.config(text=f'X={T[0]}  Y={T[1]}', foreground='green')
app.mouse_button.set('right')
app.shift_var.set('0')
app.interval_var.set('1200')
app.jitter_var.set('300')
app._select_window('mouse', title)
app.tp_vars['mouse'].set(True)

p = app.collect_params('mouse')
print('параметры:', {k: v for k, v in p.items() if k != 'which'})

# обёртка: лог каждого действия + проверка эффекта
orig_do = app._do_action
effects = []
def wrapped(param):
    before = capture_client(GAME)
    try:
        orig_do(param)
        err = None
    except Exception as e:
        err = repr(e)
    time.sleep(0.9)
    after = capture_client(GAME)
    bbox, n = bbox_client(GAME, before, after)
    effects.append(bool(bbox))
    print(f'  действие: err={err}, эффект={"ДА" if bbox else "нет"}, '
          f'hwnd={param["hwnd"]}, pos={param["pos"]}')
app._do_action = wrapped

# фокус оставляем на браузере пользователя (не трогаем foreground)
app.start_engine('mouse')

t0 = time.time()
while time.time() - t0 < 12 and app.engines['mouse'].running:
    root.update()
    time.sleep(0.05)
app.engines['mouse'].stop_ev.set()
for _ in range(10):
    root.update()
    time.sleep(0.02)

# закрыть возможное меню
post(GAME, 0, 0, win32con.WM_KEYDOWN, win32con.VK_ESCAPE)
time.sleep(0.1)
post(GAME, 0, 0, win32con.WM_KEYUP, win32con.VK_ESCAPE)

print(f'ИТОГ: {len(effects)} действий, с эффектом: {sum(effects)}')
root.destroy()
