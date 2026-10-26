# -*- coding: utf-8 -*-
"""Пробник низкоуровневого хука: видит ли система вообще нажатия."""
import ctypes
import threading
import time
from ctypes import wintypes

u = ctypes.windll.user32

HC_ACTION = 0
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
LLKHF_INJECTED = 0x00000010


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.POINTER(wintypes.ULONG))]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM,
                              wintypes.LPARAM)
seen = []


@HOOKPROC
def cb(nCode, wParam, lParam):
    if nCode == HC_ACTION:
        k = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        seen.append((wParam, k.vkCode, bool(k.flags & LLKHF_INJECTED)))
    return u.CallNextHookEx(None, nCode, wParam, lParam)


def press_stuff():
    import keyboard
    time.sleep(0.8)
    keyboard.press_and_release('f8')      # библиотека (SendInput)
    time.sleep(0.5)
    k = ctypes.windll.user32
    k.keybd_event(0x79, 0, 0, 0)          # F10 через keybd_event
    time.sleep(0.05)
    k.keybd_event(0x79, 0, 2, 0)


threading.Thread(target=press_stuff).start()

hook = u.SetWindowsHookExW(WH_KEYBOARD_LL, cb, None, 0)
print('хук установлен:', bool(hook))
t0 = time.time()
msg = wintypes.MSG()
while time.time() - t0 < 3.0:
    r = u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
    if r:
        u.TranslateMessage(ctypes.byref(msg))
        u.DispatchMessageW(ctypes.byref(msg))
    else:
        time.sleep(0.01)
u.UnhookWindowsHookEx(hook)
print('события (сообщение, vk, инъектировано):')
for s in seen:
    print(' ', 'DOWN' if s[0] == WM_KEYDOWN else 'UP  ', hex(s[1]), 'inj=' + str(s[2]))
print('всего:', len(seen))
