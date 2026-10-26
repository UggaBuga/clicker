# -*- coding: utf-8 -*-
"""Пробник v4: PrintWindow (не боится перекрытия) + SwitchToThisWindow."""
import ctypes
import time
import tkinter as tk
import win32gui
import win32con
from PIL import Image, ImageChops

GAME = 69928574
_u = ctypes.windll.user32
_g = ctypes.windll.gdi32


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', ctypes.c_ulong), ('biWidth', ctypes.c_long),
                ('biHeight', ctypes.c_long), ('biPlanes', ctypes.c_ushort),
                ('biBitCount', ctypes.c_ushort), ('biCompression', ctypes.c_ulong),
                ('biSizeImage', ctypes.c_ulong), ('biXPelsPerMeter', ctypes.c_long),
                ('biYPelsPerMeter', ctypes.c_long), ('biClrUsed', ctypes.c_ulong),
                ('biClrImportant', ctypes.c_ulong)]


def capture_client(hwnd):
    """Содержимое клиентской области окна — даже если перекрыто."""
    w, h = win32gui.GetClientRect(hwnd)[2:]
    hdc_win = _u.GetDC(hwnd)
    hdc_mem = _g.CreateCompatibleDC(hdc_win)
    hbmp = _g.CreateCompatibleBitmap(hdc_win, w, h)
    _g.SelectObject(hdc_mem, hbmp)
    _u.PrintWindow(hwnd, hdc_mem, 3)  # CLIENTONLY | RENDERFULLCONTENT
    hdr = BITMAPINFOHEADER()
    hdr.biSize = ctypes.sizeof(hdr)
    hdr.biWidth, hdr.biHeight = w, -h
    hdr.biPlanes, hdr.biBitCount, hdr.biCompression = 1, 32, 0
    buf = (ctypes.c_char * (w * h * 4))()
    _g.GetDIBits(hdc_mem, hbmp, 0, h, buf, ctypes.byref(hdr), 0)
    raw = bytearray(buf.raw)
    raw[3::4] = b'\xff' * (w * h)  # альфа-канал в ноль не обнуляем: выставляем 255
    img = Image.frombytes('RGBA', (w, h), bytes(raw)).convert('RGB')
    _g.DeleteObject(hbmp)
    _g.DeleteDC(hdc_mem)
    _u.ReleaseDC(hwnd, hdc_win)
    return img


def diff_count(a, b):
    d = ImageChops.difference(a, b)
    return sum(1 for px in d.getdata() if sum(px) > 60)


def switch_to(hwnd):
    _u.SwitchToThisWindow(hwnd, True)


def post(x, y, msgs):
    cx, cy = win32gui.ScreenToClient(GAME, (x, y))
    lp = (cy << 16) | (cx & 0xFFFF)
    for m, w in msgs:
        win32gui.PostMessage(GAME, m, w, lp)
        time.sleep(0.06)


def client_point(fx, fy):
    ox, oy = win32gui.ClientToScreen(GAME, (0, 0))
    w, h = win32gui.GetClientRect(GAME)[2:]
    return ox + int(w * fx), oy + int(h * fy)


assert win32gui.IsWindow(GAME)
print('игра:', win32gui.GetWindowText(GAME)[:45])
px, py = client_point(0.5, 0.45)
qx, qy = client_point(0.52, 0.47)

# --- фаза 1: фокус на другое окно ---
d = tk.Tk()
d.title('probe')
d.geometry('500x160+30+1100')
tk.Label(d, text='Тест фонового ввода, ~15 секунд…', font=('Arial', 12)).pack(pady=20)
d.update()
d.attributes('-topmost', True)
switch_to(d.winfo_id())
time.sleep(1.5)
unfocused = win32gui.GetForegroundWindow() != GAME
print('игра без фокуса:', unfocused, '| iconic =', win32gui.IsIconic(GAME))

if unfocused:
    base1 = capture_client(GAME)
    time.sleep(0.8)
    base2 = capture_client(GAME)
    baseline = diff_count(base1, base2)
    print(f'фон без кликов (живость рендера): {baseline} пикселей')

    before = capture_client(GAME)
    post(px, py, [(win32con.WM_MOUSEMOVE, 0),
                  (win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON),
                  (win32con.WM_RBUTTONUP, 0)])
    time.sleep(1.2)
    after = capture_client(GAME)
    changed = diff_count(before, after)
    print(f'фон + ПКМ: {changed} пикселей')
    # закрыть возможное меню ЛКМ рядом
    post(qx, qy, [(win32con.WM_MOUSEMOVE, 0),
                  (win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON),
                  (win32con.WM_LBUTTONUP, 0)])
    time.sleep(0.6)

    if baseline > 50:
        bg_works = changed > baseline * 3
    else:
        bg_works = changed > 200
    print('ВЫВОД (фон):', 'клиент ОБРАБОТАЛ клик без фокуса' if bg_works
          else 'реакции на клик без фокуса НЕТ')
else:
    print('не удалось отвести фокус — пропуск фоновой фазы')

# --- фаза 2: контроль с фокусом ---
switch_to(GAME)
time.sleep(1.0)
print('фокус у игры:', win32gui.GetForegroundWindow() == GAME)
before = capture_client(GAME)
post(px, py, [(win32con.WM_MOUSEMOVE, 0),
              (win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON),
              (win32con.WM_RBUTTONUP, 0)])
time.sleep(1.2)
after = capture_client(GAME)
changed_fg = diff_count(before, after)
post(qx, qy, [(win32con.WM_MOUSEMOVE, 0),
              (win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON),
              (win32con.WM_LBUTTONUP, 0)])
time.sleep(0.4)
d.destroy()
print(f'фокус + ПКМ: {changed_fg} пикселей')
print('ВЫВОД (фокус):', 'реагирует' if changed_fg > 200 else 'НЕ реагирует')
