# -*- coding: utf-8 -*-
"""Тест фонового клика: каретка Блокнота, строгая проверка сдвига."""
import ctypes
import subprocess
import time
import win32gui
import win32con

_user32 = ctypes.windll.user32
proc = subprocess.Popen(['notepad.exe'])
time.sleep(2.0)

def find_notepad():
    result = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd) and 'Блокнот' in win32gui.GetWindowText(hwnd):
            result.append(hwnd)
    win32gui.EnumWindows(cb, None)
    return result[0] if result else None

try:
    hwnd = find_notepad()
    assert hwnd, 'окно Блокнота не найдено'
    edit = win32gui.FindWindowEx(hwnd, 0, 'Edit', None)
    assert edit, 'поле ввода не найдено'

    text = 'HELLO WORLD THIS IS A TEST'
    for ch in text:
        _user32.SendMessageW(edit, win32con.WM_CHAR, ord(ch), 0)

    def get_caret():
        s = ctypes.c_uint(0); e = ctypes.c_uint(0)
        _user32.SendMessageW(edit, win32con.EM_GETSEL, ctypes.byref(s), ctypes.byref(e))
        return s.value

    # каретку в начало
    _user32.SendMessageW(edit, win32con.EM_SETSEL, 0, 0)
    time.sleep(0.2)
    before = get_caret()
    print('Каретка до клика:', before)

    rect = win32gui.GetClientRect(edit)
    x, y = int(rect[2] * 0.7), 5
    lp = (y << 16) | (x & 0xFFFF)
    _user32.PostMessageW(edit, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    time.sleep(0.05)
    _user32.PostMessageW(edit, win32con.WM_LBUTTONUP, 0, lp)
    time.sleep(0.4)

    after = get_caret()
    print('Каретка после клика:', after)
    ok = before == 0 and 0 < after <= len(text)
    print('ФОНОВЫЙ КЛИК (нативный контрол):', 'РАБОТАЕТ' if ok else 'НЕ СРАБОТАЛ')
finally:
    proc.terminate()
