# -*- coding: utf-8 -*-
"""Тесты: WM_MOUSEMOVE, режим удержания, кнопка Тест, hold в профилях."""
import time
import tkinter as tk

import clicker
from clicker import ClickerApp

# --- 1) bg_mouse_click шлёт WM_MOUSEMOVE первым ---
msgs = []
real_pm, real_sc = clicker.win32gui.PostMessage, clicker.win32gui.ScreenToClient
clicker.win32gui.PostMessage = lambda hwnd, msg, wp, lp: msgs.append(msg)
clicker.win32gui.ScreenToClient = lambda hwnd, p: p
try:
    clicker.bg_mouse_click(123, 50, 60)
finally:
    clicker.win32gui.PostMessage, clicker.win32gui.ScreenToClient = real_pm, real_sc
assert msgs[0] == clicker.win32con.WM_MOUSEMOVE, f'первое сообщение: {msgs[0]}'
i = 1
while msgs[i] == clicker.win32con.WM_MOUSEMOVE:
    i += 1
assert msgs[i] == clicker.win32con.WM_LBUTTONDOWN and msgs[i+1] == clicker.win32con.WM_LBUTTONUP
print('1. WM_MOUSEMOVE перед кликом — OK')

root = tk.Tk()
app = ClickerApp(root)
app.interval_var.set('40'); app.jitter_var.set('5')

def pump(n=15):
    for _ in range(n):
        root.update(); time.sleep(0.02)

# --- 2) режим удержания: флаг hold в спецификациях ---
assert len(app._hotkey_specs) == 2, 'обычный режим: 2 горячие клавиши'
assert not app._hotkey_specs['mouse']['hold']
app.mouse_hold.set(True)
app.register_hotkeys()
assert len(app._hotkey_specs) == 2
assert app._hotkey_specs['mouse']['hold'] is True, 'флаг удержания не выставлен'
app.mouse_hold.set(False)
app.register_hotkeys()
assert len(app._hotkey_specs) == 2 and not app._hotkey_specs['mouse']['hold']
print('2. Режим удержания: флаг hold в спецификациях — OK')

# --- 3) логика старт/стоп как при удержании ---
hits = [0]
app._do_action = lambda p: hits.__setitem__(0, hits[0] + 1)
app.start_engine('mouse'); pump()
assert app.engines['mouse'].running
app.engines['mouse'].stop_ev.set(); pump()   # имитация отпускания клавиши
assert not app.engines['mouse'].running
assert hits[0] > 0
print('3. Удержание: старт по нажатию, мгновенный стоп по отпусканию — OK')

# --- 4) кнопка Тест: одно действие, статус мигает ---
before = hits[0]
app.test_action('mouse'); pump()
assert hits[0] == before + 1, 'тест должен выполнить ровно одно действие'
assert 'тест выполнен' in app.status_lbl.cget('text')
print('4. Кнопка Тест: ровно одно действие — OK')

# --- 5) hold сохраняется в профиле ---
app.mouse_hold.set(True)
snap = app._gather_settings()
app.mouse_hold.set(False)
app._apply_settings(snap)
assert app.mouse_hold.get() is True, 'hold не восстановился из профиля'
assert len(app._hotkey_specs) == 2 and app._hotkey_specs['mouse']['hold'] is True, \
    'регистрация не обновилась после профиля'
print('5. Профили: режим удержания сохраняется — OK')

# --- 6) кнопки не берут фокус (защита от пробела) ---
bad = []
def walk(w):
    for c in w.winfo_children():
        if c.__class__.__name__ in ('Button', 'Checkbutton', 'Radiobutton'):
            if str(c.cget('takefocus')) != '0':
                bad.append(str(c))
        walk(c)
walk(root)
assert not bad, f'виджеты с фокусом: {bad[:3]}'
print('6. Кнопки/чекбоксы без фокуса (пробел их не «нажмёт») — OK')

# --- 7) активный режим возвращает фокус игре ---
calls = []
real_gfw, real_sfw = clicker.win32gui.GetForegroundWindow, clicker.win32gui.SetForegroundWindow
real_isw = clicker.win32gui.IsWindow
clicker.win32gui.GetForegroundWindow = lambda: app.root.winfo_id()  # фокус на кликере
clicker.win32gui.SetForegroundWindow = lambda h: calls.append(h)
clicker.win32gui.IsWindow = lambda h: True
try:
    app._last_external_fg = 4242
    hits2 = [0]
    app._do_action = lambda p: hits2.__setitem__(0, hits2[0] + 1)
    app.key_mode.set('active')
    app.start_engine('key')
    for _ in range(15): root.update(); time.sleep(0.02)
    assert calls == [4242], f'фокус не возвращён: {calls}'
    assert app.engines['key'].running
    app.engines['key'].stop_ev.set()
    for _ in range(15): root.update(); time.sleep(0.02)
finally:
    clicker.win32gui.GetForegroundWindow, clicker.win32gui.SetForegroundWindow = real_gfw, real_sfw
    clicker.win32gui.IsWindow = real_isw
print('7. Активный режим: фокус возвращён прежнему окну — OK')

# --- 8) cursor_at: телепорт курсора с возвратом на место ---
class _FakeUser32:
    def __init__(self):
        self.pos = (111, 222)
        self.log = []
    def GetCursorPos(self, pt):
        pt._obj.x, pt._obj.y = self.pos
        return True
    def SetCursorPos(self, x, y):
        self.log.append((x, y))
        self.pos = (x, y)
        return True

import clicker as _c
fake = _FakeUser32()
real_u32 = _c._user32
_c._user32 = fake
try:
    with _c.cursor_at(500, 600, settle=0, restore_delay=0):
        assert fake.pos == (500, 600), 'курсор не переместился к точке'
    assert fake.pos == (111, 222), 'позиция курсора не восстановлена'
    assert fake.log == [(500, 600), (111, 222)], fake.log
finally:
    _c._user32 = real_u32
print('8. Телепорт курсора: перемещение к точке и возврат — OK')

print('\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ')
