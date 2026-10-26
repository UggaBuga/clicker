# -*- coding: utf-8 -*-
"""End-to-end: RawKeyHook (выделенный поток) + keybd_event из потока -> колбэк.
Инъектированные события принимаем (ignore_injected=False) — только для теста."""
import ctypes
import threading
import time

from clicker import RawKeyHook

_user32 = ctypes.windll.user32
events = []
hook = RawKeyHook(lambda ev, vk: events.append((ev, vk)),
                  ignore_injected=False)
assert hook.start(), 'хук не установлен'

def press(vk):
    _user32.keybd_event(vk, 0, 0, None)
    time.sleep(0.06)
    _user32.keybd_event(vk, 0, 2, None)
    time.sleep(0.06)

t = threading.Thread(target=lambda: (press(0x79), press(0x78)))
t.start()
t.join(timeout=5)
time.sleep(0.3)
hook.stop()

print('События:', events)
assert len(events) == 4, f'ожидалось 4 события, получено {len(events)}'
assert events[0] == ('down', 0x79) and events[1] == ('up', 0x79), events[:2]
assert events[2] == ('down', 0x78) and events[3] == ('up', 0x78), events[2:]
print('END-TO-END ХУК + keybd_event: РАБОТАЕТ')
