# -*- coding: utf-8 -*-
"""
Кликер / клавишенажималка.
Вкладки «Мышь» и «Клавиши» — независимые движки, у каждого своя горячая
клавиша (старт/стоп), свой список фоновых окон и свой счётчик.
Профили сохраняют все настройки (тайминги, действия, окна, горячие клавиши).

Горячие клавиши — собственный WH_KEYBOARD_LL (RawKeyHook) на выделенном
потоке с прокачкой GetMessage; события маршалятся в GUI через очередь.
"""
import contextlib
import json
import os
import queue
import random
import sys
import threading
import time
import ctypes
from ctypes import wintypes

import tkinter as tk
from tkinter import ttk, messagebox
import winsound

import pyautogui
import win32gui
import win32con

pyautogui.FAILSAFE = True  # аварийная остановка: мышь в левый верхний угол экрана

APP_DIR = os.path.dirname(sys.executable if getattr(sys, 'frozen', False)
                          else os.path.abspath(__file__))
PROFILES_PATH = os.path.join(APP_DIR, 'clicker_profiles.json')

# ---------- Win32 константы ----------
WM = {
    'left':   (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON),
    'right':  (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON),
    'middle': (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP, win32con.MK_MBUTTON),
}

VK_SHIFT, VK_CONTROL, VK_MENU = 0x10, 0x11, 0x12
MOD_VKS = {'ctrl': VK_CONTROL, 'shift': VK_SHIFT, 'alt': VK_MENU}
MOD_ORDER = ('ctrl', 'shift', 'alt')

VK_EXTRA = {
    'space': 0x20, 'enter': 0x0D, 'return': 0x0D, 'tab': 0x09,
    'esc': 0x1B, 'escape': 0x1B, 'backspace': 0x08, 'delete': 0x2E,
    'insert': 0x2D, 'home': 0x24, 'end': 0x23,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'pageup': 0x21, 'pagedown': 0x22,
    'shift': VK_SHIFT, 'ctrl': VK_CONTROL, 'alt': VK_MENU,
}

VK_NAMES = {}
for _n, _v in VK_EXTRA.items():
    VK_NAMES.setdefault(_v, _n)
for _c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
    VK_NAMES.setdefault(ord(_c), _c.lower())
for _d in '0123456789':
    VK_NAMES.setdefault(ord(_d), _d)
for _i in range(1, 25):
    VK_NAMES.setdefault(0x70 + _i - 1, f'f{_i}')

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
WM_KEYUP, WM_SYSKEYUP = 0x0101, 0x0105
KEYEVENTF_KEYUP = 0x0002

_user32 = ctypes.windll.user32
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                      wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                   wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = ctypes.c_long
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD,
                                ctypes.POINTER(ctypes.c_ulong)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD),
                ('flags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong))]


_HOOKCB = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM,
                             wintypes.LPARAM)


def name_to_vk(name):
    """Имя клавиши ('f5', 'space', 'a', '5') -> виртуальный код."""
    n = name.strip().lower()
    if n in VK_EXTRA:
        return VK_EXTRA[n]
    if len(n) == 1 and n.isalpha():
        return ord(n.upper())
    if len(n) == 1 and n.isdigit():
        return ord(n)
    if n.startswith('f') and n[1:].isdigit() and 1 <= int(n[1:]) <= 24:
        return 0x70 + int(n[1:]) - 1
    vk = _user32.VkKeyScanA(ord(n[0])) & 0xFF
    if vk == 0xFF:
        raise ValueError(f'Неизвестная клавиша: {name}')
    return vk


def mods_now():
    """Какие модификаторы сейчас зажаты."""
    return {m for m, vk in MOD_VKS.items() if _user32.GetAsyncKeyState(vk) & 0x8000}


def send_key(combo):
    """Настоящее нажатие клавиши в активное окно (keybd_event)."""
    parts = [p.strip().lower() for p in combo.split('+') if p.strip()]
    main = [p for p in parts if p not in MOD_VKS]
    if not main:
        raise ValueError('Не указана основная клавиша')
    vk_main = name_to_vk(main[-1])
    mods = [MOD_VKS[p] for p in parts if p in MOD_VKS]
    scan = _user32.MapVirtualKeyW(vk_main, 0)
    for vk in mods:
        _user32.keybd_event(vk, 0, 0, None)
        time.sleep(0.02)
    _user32.keybd_event(vk_main, scan, 0, None)
    time.sleep(random.uniform(0.03, 0.07))
    _user32.keybd_event(vk_main, scan, KEYEVENTF_KEYUP, None)
    for vk in reversed(mods):
        _user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, None)
        time.sleep(0.02)


LLKHF_INJECTED = 0x00000010
WM_QUIT = 0x0012


class RawKeyHook:
    """WH_KEYBOARD_LL на выделенном потоке с собственной прокачкой сообщений.
    Колбэки вызываются в потоке хука — Tk-вызовы из них НЕ безопасны,
    маршаль через queue. Инъектированные события (keybd_event/SendInput)
    игнорируются, чтобы собственные нажатия кликера не дёргали хоткеи."""

    def __init__(self, on_event, ignore_injected=True):
        self._on_event = on_event
        self._ignore_injected = ignore_injected
        self._cb = _HOOKCB(self._proc)
        self._hook = None
        self._thread = None
        self._started = threading.Event()
        self._stop = threading.Event()

    def _proc(self, nCode, wParam, lParam):
        if nCode == HC_ACTION:
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                ev = 'down'
            elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                ev = 'up'
            else:
                ev = None
            if ev:
                kb = ctypes.cast(lParam,
                                 ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not (self._ignore_injected and (kb.flags & LLKHF_INJECTED)):
                    try:
                        self._on_event(ev, kb.vkCode)
                    except Exception:
                        pass
        return _user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def _pump(self):
        self._hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._cb,
                                               None, 0)
        self._started.set()
        if not self._hook:
            return
        msg = wintypes.MSG()
        pmsg = ctypes.byref(msg)
        while not self._stop.is_set():
            r = _user32.GetMessageW(pmsg, None, 0, 0)
            if r in (0, -1):
                break
            _user32.TranslateMessage(pmsg)
            _user32.DispatchMessageW(pmsg)
        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def start(self):
        if self._thread:
            return True
        self._thread = threading.Thread(target=self._pump,
                                        name='keyhook', daemon=True)
        self._thread.start()
        self._started.wait(3.0)
        return bool(self._hook)

    def stop(self):
        self._stop.set()
        if self._thread:
            _user32.PostThreadMessageW(self._thread.ident, WM_QUIT, 0, 0)
            self._thread.join(timeout=2.0)
            self._thread = None


def list_visible_windows():
    """Список (hwnd, заголовок) видимых окон с непустым заголовком."""
    result = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if title:
                result.append((hwnd, title))
    win32gui.EnumWindows(cb, None)
    return sorted(result, key=lambda t: t[1].lower())


def bg_mouse_move(hwnd, x, y):
    """Виртуально переместить курсор в фоновом окне (WM_MOUSEMOVE).
    GLFW (LWJGL) хранит позицию из этого сообщения — важно перед нажатием
    клавиши/кликом. Два сообщения подряд сужают окно гонки с реальной мышью."""
    cx, cy = win32gui.ScreenToClient(hwnd, (int(x), int(y)))
    lparam = (int(cy) << 16) | (cx & 0xFFFF)
    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.004)
    win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.004)


def bg_mouse_click(hwnd, x, y, button='left', double=False):
    """Клик в фоновое окно по экранным координатам (окно НЕ активируется)."""
    down, up, wparam_down = WM[button]
    bg_mouse_move(hwnd, x, y)
    cx, cy = win32gui.ScreenToClient(hwnd, (int(x), int(y)))
    lparam = (int(cy) << 16) | (cx & 0xFFFF)
    for i in range(2 if double else 1):
        win32gui.PostMessage(hwnd, down, wparam_down, lparam)
        time.sleep(random.uniform(0.02, 0.06))
        win32gui.PostMessage(hwnd, up, 0, lparam)
        if double and i == 0:
            time.sleep(random.uniform(0.03, 0.08))


@contextlib.contextmanager
def cursor_at(x, y, settle=0.15, restore_delay=0.1):
    """Временно переместить физический курсор в (x, y) и вернуть на место.
    Нужно для окон, которые читают позицию мыши через GetCursorPos
    (GLFW/glfwGetCursorPos), а не из WM_MOUSEMOVE: без этого клик
    происходит там, где реально стоит мышь."""
    pt = wintypes.POINT()
    if not _user32.GetCursorPos(ctypes.byref(pt)):
        yield
        return
    _user32.SetCursorPos(int(x), int(y))
    time.sleep(settle)
    try:
        yield
    finally:
        time.sleep(restore_delay)
        _user32.SetCursorPos(pt.x, pt.y)


def bg_key_press(hwnd, combo):
    """Нажатие клавиши в фоновое окно. combo вида 'f5' или 'ctrl+1'."""
    parts = [p for p in combo.lower().replace(' ', '').split('+') if p]
    main = [p for p in parts if p not in MOD_VKS]
    if not main:
        raise ValueError('Не указана основная клавиша')
    vk = name_to_vk(main[-1])
    mods = [MOD_VKS[p] for p in parts if p in MOD_VKS]
    scan = _user32.MapVirtualKeyW(vk, 0)
    lp_down = 1 | (scan << 16)
    lp_up = lp_down | (1 << 30) | (1 << 31)
    for m in mods:
        win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, m, 1)
        time.sleep(0.02)
    win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, lp_down)
    time.sleep(random.uniform(0.03, 0.07))
    win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, lp_up)
    for m in reversed(mods):
        win32gui.PostMessage(hwnd, win32con.WM_KEYUP, m, lp_up)
        time.sleep(0.02)


# ---------- Движок ----------

class Engine:
    """Состояние одного независимого кликера (мышь или клавиши)."""
    def __init__(self, name):
        self.name = name
        self.running = False
        self.stop_ev = threading.Event()
        self.thread = None
        self.done = 0


# ---------- Приложение ----------

class ClickerApp:
    def __init__(self, root):
        self.root = root
        root.title('Кликер')
        root.geometry('580x800')
        root.minsize(580, 800)

        self.engines = {'mouse': Engine('Мышь'), 'key': Engine('Клавиши')}
        self._uiq = queue.Queue()
        self._hotkey_specs = {}   # which -> {vk, mods, hold, held}
        self._recording = None
        self.fixed_pos = None
        self.key_fixed_pos = None
        self._last_external_fg = None
        self.profiles = self._load_profiles()

        self._build_ui()
        self._strip_takefocus()
        self.root.bind('<FocusOut>',
                         lambda e: self.root.after(150, self._remember_fg))
        self.refresh_windows()
        self.register_hotkeys()

        self.keyhook = RawKeyHook(self._on_key_event_queued)
        self._key_q = queue.Queue()
        if not self.keyhook.start():
            self.log('ВНИМАНИЕ: не удалось установить клавиатурный хук — '
                     'горячие клавиши не работают (запусти от администратора?)')
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self._poll_ui()

    def _on_close(self):
        for e in self.engines.values():
            e.stop_ev.set()
        self.keyhook.stop()
        self.root.destroy()

    def _strip_takefocus(self):
        """Кнопки/чекбоксы/радиокнопки не берут фокус — иначе пробел
        «нажимает» их, когда активный движок шлёт клавиши."""
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, (ttk.Button, ttk.Checkbutton,
                                  ttk.Radiobutton, ttk.Combobox)):
                    try:
                        c.configure(takefocus=False)
                    except Exception:
                        pass
                walk(c)
        walk(self.root)

    def _remember_fg(self):
        try:
            fg = win32gui.GetForegroundWindow()
            if fg and fg != self.root.winfo_id():
                self._last_external_fg = fg
        except Exception:
            pass

    def _refocus_game(self):
        """Активный режим: если фокус на нашем окне — вернуть его игре,
        иначе клавиши будут «жать» по кнопкам самого кликера."""
        try:
            if win32gui.GetForegroundWindow() != self.root.winfo_id():
                return
            target = self._last_external_fg
            if not target or not win32gui.IsWindow(target):
                self.log('Активный режим: не помню прежнее окно — '
                         'переведи фокус на игру сам')
                return
            try:
                win32gui.SetForegroundWindow(target)
            except Exception:
                _user32.SwitchToThisWindow(target, True)
            self.log(f'Фокус возвращён окну: {win32gui.GetWindowText(target)[:50]}')
        except Exception:
            pass

    # ---------- UI ----------

    def _build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill='both', expand=True, padx=10, pady=(10, 4))
        self.tab_mouse = ttk.Frame(nb, padding=10)
        self.tab_key = ttk.Frame(nb, padding=10)
        nb.add(self.tab_mouse, text='  Мышь  ')
        nb.add(self.tab_key, text='  Клавиши  ')
        self.nb = nb

        self.win_combos = {}
        self.tp_vars = {}
        self._build_mouse_tab()
        self._build_key_tab()
        self._build_common()

    def _target_frame(self, parent, which):
        """Блок выбора окна-цели; у каждой вкладки СВОЙ список окон."""
        frm = ttk.LabelFrame(parent, text='Окно-цель', padding=8)
        frm.pack(fill='x', pady=(0, 8))
        mode = tk.StringVar(value='active')
        ttk.Radiobutton(frm, text='Активное окно (реальный ввод, окно в фокусе)',
                        variable=mode, value='active').pack(anchor='w')
        row = ttk.Frame(frm)
        row.pack(fill='x', pady=(4, 0))
        ttk.Radiobutton(row, text='Фоновое окно:', variable=mode,
                        value='background').pack(side='left')
        combo = ttk.Combobox(row, state='readonly', width=42)
        combo.pack(side='left', padx=6)
        ttk.Button(row, text='Обновить', command=self.refresh_windows).pack(side='left')
        self.win_combos[which] = combo
        tp = tk.BooleanVar(value=True)
        ttk.Checkbutton(frm, text='Телепорт курсора к точке действия '
                                   '(игры, читающие мышь напрямую: курсор на '
                                   '~0,3 с переместится к точке и вернётся)',
                        variable=tp).pack(anchor='w', pady=(4, 0))
        self.tp_vars[which] = tp
        return mode

    def _hotkey_row(self, parent, default, which):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=(8, 0))
        ttk.Label(row, text='Горячая клавиша (старт/стоп):').pack(side='left')
        entry = ttk.Entry(row, width=12)
        entry.insert(0, default)
        entry.pack(side='left', padx=6)
        ttk.Button(row, text='◉', width=3,
                   command=lambda: self.record_key(entry, is_hotkey=True)).pack(side='left')
        hold = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text='удержание',
                        variable=hold,
                        command=self.register_hotkeys).pack(side='left', padx=(10, 2))
        ttk.Button(row, text='Тест', width=6,
                   command=lambda: self.test_action(which)).pack(side='right')
        setattr(self, f'{which}_hold', hold)
        entry.bind('<FocusOut>', lambda e: self.register_hotkeys())
        entry.bind('<KeyRelease>', lambda e: self.register_hotkeys())
        return entry

    def _build_mouse_tab(self):
        p = self.tab_mouse
        self.mouse_mode = self._target_frame(p, 'mouse')

        pos = ttk.LabelFrame(p, text='Позиция клика', padding=8)
        pos.pack(fill='x', pady=(0, 8))
        self.pos_mode = tk.StringVar(value='cursor')
        ttk.Radiobutton(pos, text='По позиции курсора', variable=self.pos_mode,
                        value='cursor').pack(anchor='w')
        row = ttk.Frame(pos)
        row.pack(fill='x', pady=(4, 0))
        ttk.Radiobutton(row, text='Фиксированная:', variable=self.pos_mode,
                        value='fixed').pack(side='left')
        self.pos_lbl = ttk.Label(row, text='не задана')
        self.pos_lbl.pack(side='left', padx=6)
        ttk.Button(row, text='Захватить (5 с)',
                   command=self.capture_position).pack(side='left')

        opts = ttk.LabelFrame(p, text='Параметры клика', padding=8)
        opts.pack(fill='x', pady=(0, 8))
        r1 = ttk.Frame(opts); r1.pack(fill='x')
        ttk.Label(r1, text='Кнопка:').pack(side='left')
        self.mouse_button = ttk.Combobox(r1, state='readonly', width=10,
                                         values=['left', 'right', 'middle'])
        self.mouse_button.set('left')
        self.mouse_button.pack(side='left', padx=6)
        self.mouse_double = tk.BooleanVar(value=False)
        ttk.Checkbutton(r1, text='Двойной клик',
                        variable=self.mouse_double).pack(side='left', padx=12)
        r2 = ttk.Frame(opts); r2.pack(fill='x', pady=(6, 0))
        ttk.Label(r2, text='Случайный сдвиг точки клика: ±').pack(side='left')
        self.shift_var = tk.StringVar(value='2')
        ttk.Entry(r2, textvariable=self.shift_var, width=5).pack(side='left', padx=4)
        ttk.Label(r2, text='px  (0 — без сдвига)').pack(side='left')

        self.hk_mouse = self._hotkey_row(p, 'insert', 'mouse')

    def _build_key_tab(self):
        p = self.tab_key
        self.key_mode = self._target_frame(p, 'key')

        frm = ttk.LabelFrame(p, text='Клавиша', padding=8)
        frm.pack(fill='x', pady=(0, 8))
        row = ttk.Frame(frm); row.pack(fill='x')
        ttk.Label(row, text='Клавиша / комбинация:').pack(side='left')
        self.key_entry = ttk.Entry(row, width=22)
        self.key_entry.pack(side='left', padx=6)
        self.key_entry.insert(0, 'space')
        ttk.Button(row, text='Записать',
                   command=lambda: self.record_key(self.key_entry)).pack(side='left')
        ttk.Label(p, text='Для активного окна работают комбинации (ctrl+1 и т.п.).\n'
                          'Для фонового окна модификаторы поддерживаются частично.',
                  foreground='#666').pack(anchor='w', pady=4)

        pos = ttk.LabelFrame(p, text='Позиция мыши при нажатии (для фонового окна)',
                             padding=8)
        pos.pack(fill='x', pady=(0, 8))
        self.key_pos_mode = tk.StringVar(value='none')
        ttk.Radiobutton(pos, text='Не перемещать курсор (где стоит — там и нажмёт)',
                        variable=self.key_pos_mode, value='none').pack(anchor='w')
        row = ttk.Frame(pos)
        row.pack(fill='x', pady=(4, 0))
        ttk.Radiobutton(row, text='Фиксированная:', variable=self.key_pos_mode,
                        value='fixed').pack(side='left')
        self.key_pos_lbl = ttk.Label(row, text='не задана')
        self.key_pos_lbl.pack(side='left', padx=6)
        ttk.Button(row, text='Захватить (5 с)',
                   command=self.capture_key_position).pack(side='left')

        self.hk_key = self._hotkey_row(p, 'home', 'key')

    def _build_common(self):
        frm = ttk.LabelFrame(self.root, text='Тайминг', padding=8)
        frm.pack(fill='x', padx=10, pady=(0, 4))

        r1 = ttk.Frame(frm); r1.pack(fill='x')
        ttk.Label(r1, text='Интервал, мс:').pack(side='left')
        self.interval_var = tk.StringVar(value='500')
        ttk.Entry(r1, textvariable=self.interval_var, width=8).pack(side='left', padx=4)
        ttk.Label(r1, text='Разброс ± мс:').pack(side='left', padx=(12, 0))
        self.jitter_var = tk.StringVar(value='150')
        ttk.Entry(r1, textvariable=self.jitter_var, width=8).pack(side='left', padx=4)
        ttk.Label(r1, text='Повторов (0 = ∞):').pack(side='left', padx=(12, 0))
        self.repeats_var = tk.StringVar(value='0')
        ttk.Entry(r1, textvariable=self.repeats_var, width=6).pack(side='left', padx=4)

        prof = ttk.LabelFrame(self.root, text='Профили', padding=8)
        prof.pack(fill='x', padx=10, pady=(0, 4))
        rp = ttk.Frame(prof); rp.pack(fill='x')
        ttk.Label(rp, text='Профиль:').pack(side='left')
        self.profile_combo = ttk.Combobox(rp, state='readonly', width=24)
        self.profile_combo.pack(side='left', padx=6)
        self.profile_combo.bind('<<ComboboxSelected>>', self.apply_profile)
        self.profile_name = ttk.Entry(rp, width=22)
        self.profile_name.pack(side='left', padx=6)
        ttk.Button(rp, text='Сохранить', command=self.save_profile).pack(side='left')
        ttk.Button(rp, text='Удалить', command=self.delete_profile).pack(side='left', padx=(6, 0))
        ttk.Label(prof, text='Сохраняет/загружает тайминги, действия, окна и горячие клавиши.',
                  foreground='#666').pack(anchor='w', pady=(4, 0))
        self._reload_profile_combo()

        ctl = ttk.Frame(self.root, padding=(10, 4))
        ctl.pack(fill='x')
        self.btn_start = ttk.Button(ctl, text='▶ Старт', command=self.start_active)
        self.btn_start.pack(side='left')
        self.btn_stop = ttk.Button(ctl, text='■ Стоп', command=self.stop_active, state='disabled')
        self.btn_stop.pack(side='left', padx=6)
        ttk.Label(ctl, text='— управляют активную вкладку', foreground='#666').pack(side='left', padx=4)
        self.status_lbl = ttk.Label(ctl, text='—', foreground='#a00')
        self.status_lbl.pack(side='right')
        self.counts_lbl = ttk.Label(self.root, text='Мышь: 0 | Клавиши: 0',
                                    padding=(10, 0))
        self.counts_lbl.pack(fill='x')
        self._update_status()

        logf = ttk.LabelFrame(self.root, text='Журнал', padding=4)
        logf.pack(fill='both', expand=True, padx=10, pady=(0, 8))
        self.log_list = tk.Listbox(logf, height=7, font=('Consolas', 8),
                                   activestyle='none')
        sb = ttk.Scrollbar(logf, orient='vertical',
                           command=self.log_list.yview)
        self.log_list.configure(yscrollcommand=sb.set)
        self.log_list.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.log('Кликер готов. Горячие клавиши: мышь — Insert, клавиши — Home.')

    # ---------- Окна ----------

    def refresh_windows(self):
        current = {w: self.win_combos[w].get() for w in ('mouse', 'key')}
        self._windows = list_visible_windows()
        values = [f'{t}  [{h}]' for h, t in self._windows]
        for w in ('mouse', 'key'):
            combo = self.win_combos[w]
            combo['values'] = values
            if current[w] in values:
                combo.set(current[w])
            elif values and not combo.get():
                combo.current(0)

    def selected_hwnd(self, which):
        combo = self.win_combos[which]
        idx = combo.current()
        if idx < 0 or idx >= len(self._windows):
            raise ValueError('Не выбрано фоновое окно')
        hwnd, _ = self._windows[idx]
        if not win32gui.IsWindow(hwnd):
            raise ValueError('Окно уже закрыто, обновите список')
        return hwnd

    def selected_title(self, which):
        combo = self.win_combos[which]
        idx = combo.current()
        if idx < 0 or idx >= len(self._windows):
            return ''
        return self._windows[idx][1]

    def _select_window(self, which, title):
        if not title:
            return
        combo = self.win_combos[which]
        for i, (hwnd, t) in enumerate(self._windows):
            if t == title:
                combo.current(i)
                return

    # ---------- Захват ----------

    CAPTURE_SECONDS = 5

    def _countdown(self, lbl, finish):
        def tick(left):
            if left > 0:
                lbl.config(text=f'Наведите курсор… {left}')
                self.root.after(1000, lambda: tick(left - 1))
            else:
                finish()
        tick(self.CAPTURE_SECONDS)

    def capture_position(self):
        self._countdown(self.pos_lbl, self._grab_pos)

    def _grab_pos(self):
        self.fixed_pos = pyautogui.position()
        self.pos_mode.set('fixed')
        self.pos_lbl.config(text=f'X={self.fixed_pos.x}  Y={self.fixed_pos.y}',
                            foreground='green')
        winsound.Beep(1000, 200)
        self.log(f'Точка клика: {self.fixed_pos.x}, {self.fixed_pos.y}')

    def capture_key_position(self):
        self._countdown(self.key_pos_lbl, self._grab_key_pos)

    def _grab_key_pos(self):
        self.key_fixed_pos = pyautogui.position()
        self.key_pos_mode.set('fixed')
        self.key_pos_lbl.config(text=f'X={self.key_fixed_pos.x}  Y={self.key_fixed_pos.y}',
                                foreground='green')
        winsound.Beep(1000, 200)
        self.log(f'Точка нажатия клавиши: {self.key_fixed_pos.x}, {self.key_fixed_pos.y}')

    # ---------- Клавиатурный хук: горячие клавиши и запись ----------

    def register_hotkeys(self):
        """Пересобрать спецификации горячих клавиш из полей вкладок."""
        self._hotkey_specs = {}
        for which, entry, hold_var in (('mouse', self.hk_mouse, self.mouse_hold),
                                       ('key', self.hk_key, self.key_hold)):
            combo = entry.get().strip()
            if not combo or 'Нажмите' in combo:
                continue
            hold = hold_var.get()
            parts = [p.strip().lower() for p in combo.split('+') if p.strip()]
            mods = frozenset(p for p in parts if p in MOD_VKS)
            main = [p for p in parts if p not in MOD_VKS]
            if not main:
                self.log(f'Горячая клавиша ({which}): нет основной клавиши')
                continue
            if hold and len(parts) > 1:
                self.log(f'Удержание ({which}): нужна одиночная клавиша, не комбинация')
                continue
            try:
                vk = name_to_vk(main[-1])
            except ValueError as e:
                self.log(f'Горячая клавиша ({which}): {e}')
                continue
            self._hotkey_specs[which] = {'vk': vk, 'mods': mods,
                                         'hold': hold, 'held': False}

    def _on_key_event_queued(self, ev, vk):
        """Колбэк хука (поток хука): только в очередь, GUI качает в _poll_ui."""
        try:
            self._key_q.put_nowait((ev, vk))
        except Exception:
            pass

    def _drain_key_events(self):
        """Качает события хука в GUI-потоке (вызывается из _poll_ui)."""
        for _ in range(200):
            try:
                ev, vk = self._key_q.get_nowait()
            except queue.Empty:
                break
            self._on_key_event(ev, vk)

    def _on_key_event(self, ev, vk):
        """Вызывается из GUI-потока (через очередь из _poll_ui)."""
        if self._recording is not None:
            self._on_record_key(ev, vk)
            return
        for which, s in self._hotkey_specs.items():
            if s['vk'] != vk:
                continue
            if ev == 'down':
                if not s['held'] and mods_now() == set(s['mods']):
                    s['held'] = True
                    if s['hold']:
                        self.start_engine(which)
                    else:
                        self.toggle_engine(which)
            else:
                if s['held']:
                    s['held'] = False
                    if s['hold']:
                        self.engines[which].stop_ev.set()

    def record_key(self, entry, is_hotkey=False):
        """Записать следующее нажатие клавиш в поле."""
        if is_hotkey:
            self._hotkey_specs = {}  # не срабатывать во время записи
        entry.delete(0, tk.END)
        entry.insert(0, 'Нажмите клавиши…')
        entry.config(foreground='#b58900')
        self._recording = {'entry': entry, 'mods': set(),
                          'is_hotkey': is_hotkey}

    def _on_record_key(self, ev, vk):
        rec = self._recording
        if ev != 'down':
            return
        if vk in MOD_VKS.values():
            rec['mods'].add(vk)
            return
        name = VK_NAMES.get(vk)
        if name is None:
            return
        combo = '+'.join([m for m in MOD_ORDER if MOD_VKS[m] in rec['mods']]
                         + [name])
        entry, is_hotkey = rec['entry'], rec['is_hotkey']
        self._recording = None
        entry.delete(0, tk.END)
        entry.insert(0, combo)
        entry.config(foreground='')
        if is_hotkey:
            self.register_hotkeys()
        self.log(f'Записана клавиша: {combo}')

    # ---------- Логика движков ----------

    def active_tab(self):
        return 'mouse' if self.nb.index(self.nb.select()) == 0 else 'key'

    def toggle_engine(self, which):
        e = self.engines[which]
        if e.running:
            e.stop_ev.set()
        else:
            self.start_engine(which)

    def start_active(self):
        self.start_engine(self.active_tab())

    def stop_active(self):
        self.engines[self.active_tab()].stop_ev.set()

    def test_action(self, which):
        """Одно действие с текущими настройками — проверка без запуска цикла."""
        try:
            params = self.collect_params(which)
        except Exception as ex:
            messagebox.showerror('Ошибка', str(ex))
            return
        try:
            self._do_action(params)
            self._flash_status(f'{self.engines[which].name}: тест выполнен')
            self.log(f'{self.engines[which].name}: тест выполнен')
        except Exception as ex:
            messagebox.showerror('Ошибка', f'Действие не выполнено: {ex}')
            self.log(f'Тест ({which}): ошибка — {ex}')

    def _flash_status(self, text):
        prev = (self.status_lbl.cget('text'), self.status_lbl.cget('foreground'))
        self.status_lbl.config(text=text, foreground='green')
        self.root.after(1500, lambda: self.status_lbl.config(
            text=prev[0], foreground=prev[1]))

    def start_engine(self, which):
        e = self.engines[which]
        if e.running:
            return
        self.register_hotkeys()  # подхватить свежие значения полей
        try:
            params = self.collect_params(which)
        except Exception as ex:
            messagebox.showerror('Ошибка', str(ex))
            self.log(f'{e.name}: не запущен — {ex}')
            return
        e.stop_ev.clear()
        e.running = True
        e.done = 0
        self._sync_buttons()
        self._update_status()
        if params['mode'] == 'active':
            self._refocus_game()
        state = self._bg_window_state(params)
        if state == 'свёрнуто':
            self.log(f'{e.name}: ВНИМАНИЕ — целевое окно свёрнуто, '
                     'действия не пойдут, пока его не развернут')
        elif state == 'закрыто':
            self.log(f'{e.name}: ВНИМАНИЕ — целевое окно закрыто')
        self.log(f'{e.name}: старт ({params["mode"]}, '
                 f'интервал {params["interval"]:g}±{params["jitter"]:g} мс)')
        e.thread = threading.Thread(target=self._run, args=(e, params), daemon=True)
        e.thread.start()

    def _sync_buttons(self):
        e = self.engines[self.active_tab()]
        self.btn_start.config(state='disabled' if e.running else 'normal')
        self.btn_stop.config(state='normal' if e.running else 'disabled')

    def _update_status(self):
        parts = []
        for which in ('mouse', 'key'):
            e = self.engines[which]
            parts.append(f'{e.name}: {"работает" if e.running else "стоит"}')
        self.status_lbl.config(text=' · '.join(parts),
                               foreground='green' if any(
                                   self.engines[w].running for w in ('mouse', 'key'))
                               else '#a00')

    def _update_counts(self):
        self.counts_lbl.config(
            text=f'Мышь: {self.engines["mouse"].done} | Клавиши: {self.engines["key"].done}')

    def _engine_stopped(self, e):
        e.running = False
        self._sync_buttons()
        self._update_status()
        self.log(f'{e.name}: стоп, выполнено {e.done}')

    def _poll_ui(self):
        try:
            while True:
                self._uiq.get_nowait()()
        except queue.Empty:
            pass
        self._drain_key_events()
        self.root.after(80, self._poll_ui)

    def log(self, msg):
        """Строка в журнал. Вызывать только из GUI-потока
        (из рабочих потоков — через self._uiq)."""
        if not hasattr(self, 'log_list'):
            return
        self.log_list.insert(tk.END,
                             f'{time.strftime("%H:%M:%S")}  {msg}')
        self.log_list.see(tk.END)
        while self.log_list.size() > 100:
            self.log_list.delete(0)

    # ---------- Параметры ----------

    def _parse_timing(self, p):
        p['interval'] = float(self.interval_var.get().replace(',', '.'))
        p['jitter'] = float(self.jitter_var.get().replace(',', '.'))
        p['repeats'] = int(self.repeats_var.get())
        if p['interval'] < 10:
            raise ValueError('Интервал не может быть меньше 10 мс')
        if p['jitter'] < 0:
            raise ValueError('Разброс не может быть отрицательным')

    def collect_params(self, which):
        p = {'which': which}
        self._parse_timing(p)
        if which == 'mouse':
            p['action'] = 'mouse'
            p['mode'] = self.mouse_mode.get()
            p['button'] = self.mouse_button.get()
            p['double'] = self.mouse_double.get()
            p['shift'] = int(self.shift_var.get())
            if p['shift'] < 0:
                raise ValueError('Сдвиг не может быть отрицательным')
            p['pos'] = (self.fixed_pos.x, self.fixed_pos.y) \
                if self.pos_mode.get() == 'fixed' and self.fixed_pos else None
            if p['mode'] == 'background' and p['pos'] is None:
                raise ValueError('Для фонового окна нужна фиксированная точка — нажмите «Захватить»')
        else:
            p['action'] = 'key'
            p['mode'] = self.key_mode.get()
            p['key'] = self.key_entry.get().strip()
            if not p['key'] or 'Нажмите' in p['key']:
                raise ValueError('Не указана клавиша')
        if p['mode'] == 'background':
            p['hwnd'] = self.selected_hwnd(which)
            p['teleport'] = self.tp_vars[which].get()
            if which == 'key' and self.key_pos_mode.get() == 'fixed':
                if not self.key_fixed_pos:
                    raise ValueError('Захватите точку мыши — нажмите «Захватить (5 с)»')
                p['pos'] = (self.key_fixed_pos.x, self.key_fixed_pos.y)
        return p

    def _do_action(self, p):
        if p['action'] == 'mouse':
            if p['mode'] == 'background':
                x, y = p['pos']
            else:
                x, y = p['pos'] if p['pos'] else pyautogui.position()
            if p['shift']:
                x += random.randint(-p['shift'], p['shift'])
                y += random.randint(-p['shift'], p['shift'])
            if p['mode'] == 'background':
                if p.get('teleport', True):
                    with cursor_at(x, y):
                        bg_mouse_click(p['hwnd'], x, y, p['button'], p['double'])
                else:
                    bg_mouse_click(p['hwnd'], x, y, p['button'], p['double'])
            else:
                pyautogui.click(x, y, clicks=2 if p['double'] else 1,
                                interval=random.uniform(0.05, 0.1), button=p['button'])
        else:
            if p['mode'] == 'background':
                if p.get('pos'):
                    if p.get('teleport', True):
                        with cursor_at(*p['pos']):
                            bg_mouse_move(p['hwnd'], *p['pos'])
                            bg_key_press(p['hwnd'], p['key'])
                    else:
                        bg_mouse_move(p['hwnd'], *p['pos'])
                        bg_key_press(p['hwnd'], p['key'])
                else:
                    bg_key_press(p['hwnd'], p['key'])
            else:
                send_key(p['key'])

    @staticmethod
    def _bg_window_state(p):
        """Состояние фонового окна: None — готово, 'свёрнуто',
        'закрыто'. Проверять каждый цикл: в свёрнутое окно ввод
        не доходит, и тихий пропуск действий выглядел бы как поломка."""
        if p.get('mode') != 'background':
            return None
        hwnd = p.get('hwnd')
        if not hwnd or not win32gui.IsWindow(hwnd):
            return 'закрыто'
        if win32gui.IsIconic(hwnd):
            return 'свёрнуто'
        return None

    def _run(self, e, p):
        try:
            while not e.stop_ev.is_set():
                if p['repeats'] and e.done >= p['repeats']:
                    break
                state = self._bg_window_state(p)
                if state == 'закрыто':
                    self._uiq.put(lambda n=e.name: self.log(
                        f'{n}: целевое окно закрыто — движок остановлен'))
                    break
                if state:
                    if not getattr(e, 'warned_iconic', False):
                        e.warned_iconic = True
                        self._uiq.put(lambda n=e.name: self.log(
                            f'{n}: целевое окно свёрнуто — действия пропускаются. '
                            f'Разверни окно (Alt-Tab, не сворачивай игру).'))
                else:
                    e.warned_iconic = False
                    try:
                        self._do_action(p)
                    except pyautogui.FailSafeException:
                        self._uiq.put(lambda: self.log(
                            'Аварийная остановка: мышь в углу экрана'))
                        break
                    except Exception as ex:
                        self._uiq.put(lambda m=f'Ошибка ({e.name}): {ex}': self.log(m))
                    e.done += 1
                    self._uiq.put(self._update_counts)
                delay = max(10.0, p['interval'] + random.uniform(-p['jitter'], p['jitter']))
                if e.stop_ev.wait(timeout=delay / 1000.0):
                    break
        finally:
            self._uiq.put(lambda en=e: self._engine_stopped(en))

    # ---------- Профили ----------

    def _load_profiles(self):
        try:
            with open(PROFILES_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('profiles', {})
        except Exception:
            return {}

    def _store_profiles(self):
        try:
            with open(PROFILES_PATH, 'w', encoding='utf-8') as f:
                json.dump({'profiles': self.profiles}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            messagebox.showerror('Ошибка', f'Не удалось сохранить профили: {e}')

    def _reload_profile_combo(self, select=None):
        names = sorted(self.profiles)
        self.profile_combo['values'] = names
        if select and select in names:
            self.profile_combo.set(select)

    def _gather_settings(self):
        return {
            'interval': self.interval_var.get(),
            'jitter': self.jitter_var.get(),
            'repeats': self.repeats_var.get(),
            'mouse': {
                'mode': self.mouse_mode.get(),
                'pos_mode': self.pos_mode.get(),
                'fixed': [self.fixed_pos.x, self.fixed_pos.y] if self.fixed_pos else None,
                'button': self.mouse_button.get(),
                'double': self.mouse_double.get(),
                'shift': self.shift_var.get(),
                'win': self.selected_title('mouse'),
                'hotkey': self.hk_mouse.get(),
                'hold': self.mouse_hold.get(),
                'teleport': self.tp_vars['mouse'].get(),
            },
            'key': {
                'mode': self.key_mode.get(),
                'key': self.key_entry.get(),
                'win': self.selected_title('key'),
                'hotkey': self.hk_key.get(),
                'hold': self.key_hold.get(),
                'teleport': self.tp_vars['key'].get(),
                'pos_mode': self.key_pos_mode.get(),
                'fixed': ([self.key_fixed_pos.x, self.key_fixed_pos.y]
                          if self.key_fixed_pos else None),
            },
        }

    def _apply_settings(self, d):
        self.interval_var.set(str(d.get('interval', '500')))
        self.jitter_var.set(str(d.get('jitter', '150')))
        self.repeats_var.set(str(d.get('repeats', '0')))

        m = d.get('mouse', {})
        self.mouse_mode.set(m.get('mode', 'active'))
        self.pos_mode.set(m.get('pos_mode', 'cursor'))
        fx = m.get('fixed')
        if fx:
            self.fixed_pos = type('P', (), {'x': fx[0], 'y': fx[1]})()
            self.pos_lbl.config(text=f'X={fx[0]}  Y={fx[1]}', foreground='green')
        self.mouse_button.set(m.get('button', 'left'))
        self.mouse_double.set(bool(m.get('double', False)))
        self.shift_var.set(str(m.get('shift', '2')))
        self._set_entry(self.hk_mouse, m.get('hotkey', 'insert'))
        self.mouse_hold.set(bool(m.get('hold', False)))
        self.tp_vars['mouse'].set(bool(m.get('teleport', True)))

        k = d.get('key', {})
        self.key_mode.set(k.get('mode', 'active'))
        self._set_entry(self.key_entry, k.get('key', 'space'))
        self._set_entry(self.hk_key, k.get('hotkey', 'home'))
        self.key_hold.set(bool(k.get('hold', False)))
        self.tp_vars['key'].set(bool(k.get('teleport', True)))
        self.key_pos_mode.set(k.get('pos_mode', 'none'))
        kfx = k.get('fixed')
        if kfx:
            self.key_fixed_pos = type('P', (), {'x': kfx[0], 'y': kfx[1]})()
            self.key_pos_lbl.config(text=f'X={kfx[0]}  Y={kfx[1]}', foreground='green')

        self.refresh_windows()
        self._select_window('mouse', m.get('win', ''))
        self._select_window('key', k.get('win', ''))
        self.register_hotkeys()
        self._sync_buttons()

    @staticmethod
    def _set_entry(entry, text):
        entry.delete(0, tk.END)
        entry.insert(0, text)

    def save_profile(self):
        name = self.profile_name.get().strip()
        if not name:
            messagebox.showerror('Ошибка', 'Введите имя профиля')
            return
        self.profiles[name] = self._gather_settings()
        self._store_profiles()
        self._reload_profile_combo(select=name)
        self.profile_name.delete(0, tk.END)
        self.log(f'Профиль сохранён: {name}')

    def delete_profile(self):
        name = self.profile_combo.get() or self.profile_name.get().strip()
        if name not in self.profiles:
            return
        del self.profiles[name]
        self._store_profiles()
        self._reload_profile_combo()
        self.profile_combo.set('')
        self.log(f'Профиль удалён: {name}')

    def apply_profile(self, _event=None):
        name = self.profile_combo.get()
        if name in self.profiles:
            self._apply_settings(self.profiles[name])
            self.log(f'Профиль применён: {name}')


def _hide_console():
    """Скрыть консольное окно (exe собран в console-режиме из-за антивируса)."""
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)


if __name__ == '__main__':
    _hide_console()
    root = tk.Tk()
    app = ClickerApp(root)
    root.mainloop()
