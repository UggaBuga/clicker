# -*- coding: utf-8 -*-
"""Комплексный тест логики кликера: движки, горячие клавиши, запись, профили."""
import time
import tkinter as tk
import types

import clicker
import os as _os, tempfile as _tf
clicker.STATE_PATH = _os.path.join(_tf.gettempdir(), "state_test_logic.json")
_os.path.exists(clicker.STATE_PATH) and _os.remove(clicker.STATE_PATH)
from clicker import ClickerApp

root = tk.Tk()
app = ClickerApp(root)

def pump(n=15):
    for _ in range(n):
        root.update()
        time.sleep(0.02)

# 1) Списки окон — у каждой вкладки СВОЙ комбобокс, оба заполнены
assert app.win_combos['mouse'] is not app.win_combos['key'], 'комбобоксы общие!'
assert len(app.win_combos['mouse']['values']) > 0, 'мышь: список окон пуст'
assert len(app.win_combos['key']['values']) > 0, 'клавиши: список окон пуст'
assert len(app.win_combos['mouse']['values']) == len(app.win_combos['key']['values'])
print('1. Списки окон: у каждой вкладки свой, оба заполнены — OK')

# 2) Горячие клавиши по умолчанию и регистрация
assert app.hk_mouse.get() == 'insert', app.hk_mouse.get()
assert app.hk_key.get() == 'home', app.hk_key.get()
assert len(app._hotkey_specs) == 2, f'зарегистрировано {len(app._hotkey_specs)}'
assert set(app._hotkey_specs) == {'mouse', 'key'}
print('2. Горячие клавиши по умолчанию: insert (мышь), home (клавиши), обе зарегистрированы — OK')

# 3) Запись горячей клавиши через свой хук (симуляция нажатия F9, vk=0x78)
app.record_key(app.hk_mouse, is_hotkey=True)
assert app.hk_mouse.get() == 'Нажмите клавиши…'
assert len(app._hotkey_specs) == 0, 'горячие клавиши не сняты на время записи'

app._on_key_event('down', 0x78)   # F9
pump()
assert app.hk_mouse.get() == 'f9', app.hk_mouse.get()
assert len(app._hotkey_specs) == 2, 'горячие клавиши не восстановлены после записи'

# 4) Триггер горячей клавиши — переключает движок
assert not app.engines['mouse'].running
app._do_action = lambda p: None   # без реального клика (мышь может стоять в углу)
app.interval_var.set('40'); app.jitter_var.set('5')
app._on_key_event('down', 0x78)   # F9 снова = старт мыши
pump()
assert app.engines['mouse'].running, 'нажатие F9 не запустило движок мыши'
app._on_key_event('up', 0x78)
app.engines['mouse'].stop_ev.set()
pump()
assert not app.engines['mouse'].running
print('3. Запись горячей клавиши (F9) + переключение движка клавишей — OK')

# 4) Независимость движков: оба работают, оба останавливаются
hits = {'mouse': 0, 'key': 0}
def fake_action(p): hits[p['which']] += 1
app._do_action = fake_action
app.interval_var.set('40'); app.jitter_var.set('5')

app.toggle_engine('mouse')
app.toggle_engine('key')
pump()
assert app.engines['mouse'].running and app.engines['key'].running
m_done = app.engines['mouse'].done
app.toggle_engine('mouse')   # стоп мыши
pump()
assert not app.engines['mouse'].running
assert app.engines['key'].running, 'движок клавиш остановился вместе с мышью!'
app.toggle_engine('key')
pump()
assert not app.engines['key'].running
assert hits['mouse'] > 0 and hits['key'] > 0
print(f'4. Движки независимы: мышь {hits["mouse"]} действий, клавиши {hits["key"]} — OK')

# 5) Сдвиг точки клика — параметр собирается
app.shift_var.set('7')
app.mouse_mode.set('active')
p = app.collect_params('mouse')
assert p['shift'] == 7
app.shift_var.set('0')
p = app.collect_params('mouse')
assert p['shift'] == 0
# фоновый режим без фиксированной точки — ошибка
app.mouse_mode.set('background')
try:
    app.collect_params('mouse')
    raise AssertionError('должна быть ошибка без фикс. точки')
except ValueError:
    pass
app.mouse_mode.set('active')
# телепорт курсора: по умолчанию включён, в параметрах фонового режима
assert app.tp_vars['mouse'].get() is True and app.tp_vars['key'].get() is True
print('5. Настраиваемый сдвиг, проверка фонового режима, телепорт по умолчанию — OK')

# 6) Профили: собрать -> применить -> сохранить/удалить
app.interval_var.set('777'); app.jitter_var.set('33'); app.repeats_var.set('5')
app.mouse_button.set('right')
app.mouse_double.set(True)
app.shift_var.set('4')
app.hk_mouse.delete(0, tk.END); app.hk_mouse.insert(0, 'ctrl+9')
app.key_entry.delete(0, tk.END); app.key_entry.insert(0, 'f3')

snap = app._gather_settings()
# сброс настроек
app.interval_var.set('100'); app.mouse_button.set('left')
app.mouse_double.set(False); app.shift_var.set('0')
app._apply_settings(snap)
assert app.interval_var.get() == '777' and app.jitter_var.get() == '33'
assert app.repeats_var.get() == '5'
assert app.mouse_button.get() == 'right' and app.mouse_double.get() is True
assert app.shift_var.get() == '4'
assert app.hk_mouse.get() == 'ctrl+9' and app.key_entry.get() == 'f3'
assert len(app._hotkey_specs) == 2, 'горячие клавиши не переназначены из профиля'
assert app.tp_vars['mouse'].get() is True, 'телепорт не восстановился из профиля'
print('6. Профиль: gather -> apply (включая горячие клавиши) — OK')

# сохранение/удаление на диске
app.profiles['тест-активность'] = snap
app._store_profiles()
loaded = app._load_profiles()
assert 'тест-активность' in loaded
assert loaded['тест-активность']['interval'] == '777'
del app.profiles['тест-активность']
app._store_profiles()
assert 'тест-активность' not in app._load_profiles()
print('7. Профили на диске: сохранение и удаление — OK')

print('\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ')
