'''
Copyright (C) 2023-2025 by tinbox.wu, All Rights Reserved. 

FilePath     : host-monitor.py
Author       : tinbox.wu tinboxwu@gmail.com

Date         : 2025-02-05 16:41:34
LastEditors  : tinbox.wu tinboxwu@gmail.com
LastEditTime : 2025-12-23 15:32:20
Description  : 

'''
import socket
import time
import re
import os
import sys
import json
import ctypes
import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog, Listbox
from datetime import datetime
from collections import deque
import psutil
import threading
import win32gui
import win32con
import win32api
import win32event
import winerror
import pywintypes
import subprocess
from ctypes import wintypes


# Windows 系统 hosts 文件路径
WINDOWS_HOSTS_FILE = r'C:\Windows\System32\drivers\etc\hosts'
# 全局变量
running = False
interval = 60  # 检查间隔时间（秒）
wsl_names = []  # 存储 WSL 名称
domains = []  # 存储需要更新的域名
monitor_button = None
wsl_listbox = None
domain_listbox = None
message_display = None
root = None
single_instance_var = None
monitor_status_var = None
monitor_status_label = None
monitor_thread = None
monitor_state = 'idle'
monitor_health_job = None
auto_start_var = None
log_level_var = None
ip_strategy_var = None
adapter_var = None
adapter_combo = None
interval_var = None
WINDOW_ICON_IMAGE = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else BASE_DIR


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, '_MEIPASS', BASE_DIR)
    return os.path.join(base_path, relative_path)


def resolve_icon_path() -> str | None:
    return locate_icon_file('icon.ico')


def locate_icon_file(filename: str) -> str | None:
    if not filename:
        return None

    relative = os.path.join('icon', filename)
    search_paths = [
        os.path.join(APP_DIR, 'icon', filename),
        resource_path(relative),
        os.path.join(BASE_DIR, 'icon', filename),
        os.path.join(APP_DIR, filename),
        resource_path(filename),
        os.path.join(BASE_DIR, filename)
    ]

    for candidate in search_paths:
        if candidate and os.path.exists(candidate):
            return candidate
    return None

# 保存 WSL 列表和域名列表的文件路径
WSL_FILE = os.path.join(APP_DIR, 'wsl_list.txt')
DOMAIN_FILE = os.path.join(APP_DIR, 'domain_list.txt')
CONFIG_FILE = os.path.join(APP_DIR, 'host_monitor_config.json')

DEFAULT_CONFIG = {
    "enforce_single_instance": True,
    "auto_start_monitor": False,
    "log_level": 'INFO',
    "ip_lookup_strategy": 'auto',
    "preferred_adapter": '',
    "scan_interval": 60
}

config = {}
single_instance_mutex = None

LOG_CAPACITY = 500
log_buffer = deque(maxlen=LOG_CAPACITY)
WINDOWS_STARTUPINFO = None

TRAY_MESSAGE_ID = win32con.WM_USER + 20
TRAY_TOOLTIP = "IP 监控工具"
hwnd = None
nid = None
tray_icon_created = False
tray_window_class_atom = None
tray_icon_handles = {'idle': None, 'running': None, 'error': None}
tray_icon_state = 'idle'

THEME = {
    'bg': '#f4f6fb',
    'panel': '#ffffff',
    'accent': '#2563eb',
    'accent_hover': '#1d4ed8',
    'text': '#0f172a',
    'muted': '#64748b',
    'list_bg': '#ffffff',
    'list_fg': '#0f172a',
    'list_sel_bg': '#dbeafe',
    'list_sel_fg': '#1e3a8a',
    'log_bg': '#fbfcff',
    'log_fg': '#0f172a',
    'border': '#dbe1ee',
    'titlebar': '#e8efff',
    'title_text': '#1e3a8a',
    'toolbar_bg': '#f8fafc',
    'toolbar_border': '#e2e8f0',
    'button_action_bg': '#eff6ff',
    'button_action_hover': '#dbeafe',
    'button_action_fg': '#1e3a8a',
    'button_action_border': '#bfdbfe',
    'status_running_bg': '#dbeafe',
    'status_running_fg': '#1d4ed8',
    'status_idle_bg': '#fee2e2',
    'status_idle_fg': '#b91c1c'
}

LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
LOG_LEVEL_INDEX = {level: idx for idx, level in enumerate(LOG_LEVELS)}

IP_STRATEGIES = {
    'auto': '自动探测 (UDP)',
    'adapter': '指定网卡 (IPv4)'
}

DEFAULT_FONT = ('Microsoft YaHei UI', 10)
HEADER_FONT = ('Microsoft YaHei UI', 11, 'bold')


CHECKBOX_IMAGES = {}


def ensure_checkbox_images(master: tk.Misc):
    global CHECKBOX_IMAGES
    if CHECKBOX_IMAGES:
        return CHECKBOX_IMAGES

    size = 18

    def create_box(fill_color, border_color):
        image = tk.PhotoImage(master=master, width=size, height=size)
        image.put(fill_color, to=(0, 0, size, size))
        image.put(border_color, to=(0, 0, size, 1))
        image.put(border_color, to=(0, size - 1, size, size))
        image.put(border_color, to=(0, 0, 1, size))
        image.put(border_color, to=(size - 1, 0, size, size))
        return image

    def draw_checkmark(image, color):
        stroke = [
            (5, 9), (6, 10), (7, 11),
            (8, 10), (9, 9), (10, 8), (11, 7)
        ]
        for x, y in stroke:
            image.put(color, to=(x, y, x + 1, y + 1))
            image.put(color, to=(x, y - 1, x + 1, y))

    unchecked = create_box(THEME['panel'], THEME['border'])
    unchecked_hover = create_box(THEME['toolbar_bg'], THEME['toolbar_border'])
    unchecked_disabled = create_box('#eef2fb', '#e4e9f5')

    checked = create_box(THEME['accent'], THEME['accent'])
    checked_hover = create_box(THEME['accent_hover'], THEME['accent_hover'])
    checked_disabled = create_box('#cbd5f5', '#cbd5f5')

    draw_checkmark(checked, '#ffffff')
    draw_checkmark(checked_hover, '#ffffff')
    draw_checkmark(checked_disabled, '#f8fafc')

    CHECKBOX_IMAGES = {
        'unchecked': unchecked,
        'unchecked_hover': unchecked_hover,
        'unchecked_disabled': unchecked_disabled,
        'checked': checked,
        'checked_hover': checked_hover,
        'checked_disabled': checked_disabled
    }
    return CHECKBOX_IMAGES


def load_config():
    global config
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as file:
                user_config = json.load(file)
            for key in DEFAULT_CONFIG:
                if key in user_config:
                    config[key] = user_config[key]
        except (OSError, json.JSONDecodeError) as exc:
            print(f"读取配置文件失败，将使用默认配置: {exc}")


def sanitize_interval(value) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_CONFIG['scan_interval']
    return max(5, min(3600, parsed))


def sync_interval_from_config():
    global interval
    interval = sanitize_interval(config.get('scan_interval', DEFAULT_CONFIG['scan_interval']))
    config['scan_interval'] = interval


def monitor_worker():
    global monitor_thread, running
    try:
        check_ip_change()
    except Exception as exc:
        running = False
        log_message(f"监控线程异常: {exc}", level='ERROR')
        update_monitor_status_indicator('error', '线程异常')
        if monitor_button and monitor_button.winfo_exists():
            monitor_button.after(0, lambda: monitor_button.config(text="开启定时监测"))
    finally:
        monitor_thread = None


def start_monitoring():
    global running, monitor_thread
    if running:
        log_message("监测已经在运行中，无需重复启动。")
        return

    running = True
    try:
        monitor_thread = threading.Thread(target=monitor_worker, name='HostMonitorThread', daemon=True)
        monitor_thread.start()
        monitor_button.config(text="关闭定时监测")
        update_monitor_status_indicator('running')
        log_message("IP 监测已启动。")
    except Exception as e:
        log_message(f"启动监测线程时出错: {e}", level='ERROR')
        running = False
        monitor_thread = None
        monitor_button.config(text="开启定时监测")
        update_monitor_status_indicator('error', '启动失败')


def stop_monitoring():
    global running
    running = False
    monitor_button.config(text="开启定时监测")
    update_monitor_status_indicator('idle')
    log_message("IP 监测已停止。")


def render_log_buffer():
    if not message_display:
        return

    def refresh():
        try:
            message_display.configure(state='normal')
            message_display.delete('1.0', tk.END)
            if log_buffer:
                message_display.insert('1.0', '\n'.join(log_buffer) + '\n')
            message_display.see('1.0')
            message_display.configure(state='disabled')
        except tk.TclError:
            pass

    try:
        message_display.after(0, refresh)
    except tk.TclError:
        pass


def normalize_log_level(level: str) -> str:
    level = (level or 'INFO').upper()
    if level not in LOG_LEVEL_INDEX:
        return 'INFO'
    return level


def should_log(level: str) -> bool:
    configured = normalize_log_level(config.get('log_level', 'INFO'))
    return LOG_LEVEL_INDEX[level] >= LOG_LEVEL_INDEX[configured]


def log_message(message, level: str = 'INFO'):
    level = normalize_log_level(level)
    if not should_log(level):
        return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    text = f'[{timestamp}] [{level}] {message}'
    print(text)
    log_buffer.appendleft(text)
    render_log_buffer()


def save_config():
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
    except OSError as exc:
        log_message(f'保存配置失败: {exc}', level='ERROR')


def prepare_startupinfo():
    global WINDOWS_STARTUPINFO
    if WINDOWS_STARTUPINFO is None:
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = win32con.SW_HIDE
        WINDOWS_STARTUPINFO = info
    return WINDOWS_STARTUPINFO


def run_command(args, **kwargs):
    if os.name == 'nt':
        kwargs.setdefault('creationflags', subprocess.CREATE_NO_WINDOW)
        kwargs.setdefault('startupinfo', prepare_startupinfo())
    return subprocess.run(args, **kwargs)


def enforce_single_instance():
    global single_instance_mutex
    if not config.get('enforce_single_instance', True):
        return

    mutex_name = r"Global\IPMonitorHostMutex"
    try:
        single_instance_mutex = win32event.CreateMutex(None, False, mutex_name)
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            warning = "IP 监控工具已在运行，如需重新打开请先退出当前实例。"
            try:
                ctypes.windll.user32.MessageBoxW(
                    None,
                    warning,
                    "IP 监控工具",
                    win32con.MB_OK | win32con.MB_ICONWARNING
                )
            except Exception:
                print(warning)
            sys.exit(0)
    except pywintypes.error as exc:
        log_message(f'创建单实例互斥量失败: {exc}', level='ERROR')


def get_adapter_names():
    adapters = []
    for name, addrs in psutil.net_if_addrs().items():
        if any(addr.family == socket.AF_INET and addr.address and not addr.address.startswith('127.') for addr in addrs):
            adapters.append(name)
    return sorted(set(adapters))


def strategy_label_for_key(key: str) -> str:
    return IP_STRATEGIES.get(key, IP_STRATEGIES['auto'])


def strategy_key_from_label(label: str) -> str:
    for key, text in IP_STRATEGIES.items():
        if text == label:
            return key
    return 'auto'


def on_auto_start_toggle():
    config["auto_start_monitor"] = auto_start_var.get()
    save_config()
    log_message('自动启动设置已更新。')


def on_log_level_change(event=None):
    level = normalize_log_level(log_level_var.get())
    config['log_level'] = level
    save_config()
    log_message(f'日志级别已更新为 {level}。')


def update_adapter_combobox_state():
    if not adapter_combo:
        return
    adapters = get_adapter_names()
    preferred = config.get('preferred_adapter', '')
    if preferred and preferred not in adapters:
        adapter_var.set('')
        preferred = ''
        if config.get('preferred_adapter'):
            config['preferred_adapter'] = ''
            save_config()
            log_message('首选网卡已清空（未找到指定网卡）。', level='WARNING')
    adapter_combo['values'] = adapters
    if config.get('ip_lookup_strategy', 'auto') == 'adapter':
        adapter_combo.configure(state='readonly')
    else:
        adapter_combo.configure(state='disabled')


def on_ip_strategy_change(event=None):
    strategy_key = strategy_key_from_label(ip_strategy_var.get())
    config['ip_lookup_strategy'] = strategy_key
    save_config()
    update_adapter_combobox_state()
    log_message(f"IP 获取策略已切换为 {IP_STRATEGIES[strategy_key]}。")


def on_adapter_selected(event=None):
    adapter_name = adapter_var.get()
    config['preferred_adapter'] = adapter_name
    save_config()
    log_message(f'首选网卡已更新为 {adapter_name or "(未指定)"}。')


def on_interval_change(event=None):
    global interval
    if interval_var is None:
        return
    try:
        new_value = int(interval_var.get())
    except (tk.TclError, ValueError):
        interval_var.set(interval)
        return
    new_value = max(5, new_value)
    if new_value != interval:
        interval = new_value
        config['scan_interval'] = interval
        save_config()
        log_message(f'扫描间隔已更新为 {interval} 秒')
    if interval_var.get() != interval:
        interval_var.set(interval)


def update_tray_icon_state(state: str, tooltip_detail: str | None = None):
    global tray_icon_state
    desired_state = 'running' if state == 'running' else 'error' if state == 'error' else 'idle'
    tray_icon_state = desired_state

    if not (tray_icon_created and nid):
        return

    handle = tray_icon_handles.get(desired_state) or tray_icon_handles.get('idle') or tray_icon_handles.get('running')
    if not handle:
        return

    tooltip_suffix = tooltip_detail or ''
    tooltip_text = TRAY_TOOLTIP if not tooltip_suffix else f"{TRAY_TOOLTIP} · {tooltip_suffix}"
    tooltip_text = tooltip_text[:127]

    try:
        win32gui.Shell_NotifyIcon(
            win32gui.NIM_MODIFY,
            (hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_TIP, TRAY_MESSAGE_ID, handle, tooltip_text)
        )
    except pywintypes.error as exc:
        log_message(f'托盘图标更新失败: {exc}', level='ERROR')


def update_monitor_status_indicator(state: str, message: str | None = None):
    def apply():
        state_map = {
            'running': ('监控运行中', 'StatusRunning.TLabel'),
            'error': ('监控异常', 'StatusError.TLabel'),
            'idle': ('已暂停', 'StatusIdle.TLabel')
        }
        label_text, style_name = state_map.get(state, state_map['idle'])
        if message:
            label_text = f"{label_text} · {message}"
        monitor_status_var.set(label_text)
        monitor_status_label.configure(style=style_name)
        update_tray_icon_state(state, label_text)

    if not (monitor_status_var and monitor_status_label):
        return

    if root and threading.current_thread() is not threading.main_thread():
        root.after(0, lambda: apply())
    else:
        apply()


def monitor_health_tick():
    global monitor_health_job, running
    if root is None:
        return

    if running and (monitor_thread is None or not monitor_thread.is_alive()):
        running = False
        update_monitor_status_indicator('error')
        log_message('监控线程已停止运行，请检查日志。', level='ERROR')
        try:
            monitor_button.config(text="开启定时监测")
        except Exception:
            pass

    monitor_health_job = root.after(2000, monitor_health_tick)


def show_selection_dialog(title, options, multi=False, empty_message='暂无可选项'):
    if not options:
        log_message(empty_message)
        return []

    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.transient(root)
    dialog.grab_set()
    dialog.resizable(False, False)
    dialog.configure(bg=THEME['panel'])

    container = ttk.Frame(dialog, style='Card.TFrame', padding=12)
    container.pack(fill=tk.BOTH, expand=True)

    ttk.Label(container, text="请选择:", style='Muted.TLabel').pack(anchor='w', pady=(0, 6))

    select_mode = tk.MULTIPLE if multi else tk.SINGLE
    listbox = tk.Listbox(container, selectmode=select_mode, width=48, height=12)
    for option in options:
        listbox.insert(tk.END, option)
    listbox.pack(fill=tk.BOTH, expand=True)
    apply_listbox_theme(listbox)

    result = {'selection': []}

    def on_ok(event=None):
        selection = listbox.curselection()
        if not selection:
            return
        result['selection'] = [options[i] for i in selection]
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    button_frame = ttk.Frame(container, style='Card.TFrame')
    button_frame.pack(pady=(10, 0), fill=tk.X)
    ttk.Button(button_frame, text="确定", width=12, command=on_ok, style='Action.TButton').pack(side=tk.LEFT, padx=4)
    ttk.Button(button_frame, text="取消", width=12, command=on_cancel, style='Secondary.TButton').pack(side=tk.LEFT, padx=4)

    listbox.bind('<Double-Button-1>', on_ok)
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)
    position_dialog_near_root(dialog)
    dialog.wait_window()

    return result['selection']


def position_dialog_near_root(dialog):
    if not root:
        return
    try:
        root.update_idletasks()
        dialog.update_idletasks()
        parent_w = root.winfo_width()
        parent_h = root.winfo_height()
        parent_x = root.winfo_rootx()
        parent_y = root.winfo_rooty()
        dialog_w = dialog.winfo_width()
        dialog_h = dialog.winfo_height()
        x = parent_x + max(0, (parent_w - dialog_w) // 2)
        y = parent_y + max(0, (parent_h - dialog_h) // 2)
        dialog.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass


def apply_listbox_theme(widget):
    widget.configure(
        background=THEME['list_bg'],
        foreground=THEME['list_fg'],
        selectbackground=THEME['list_sel_bg'],
        selectforeground=THEME['list_sel_fg'],
        highlightthickness=1,
        highlightbackground=THEME['border'],
        relief='flat',
        borderwidth=0
    )


def apply_text_theme(widget):
    widget.configure(
        background=THEME['log_bg'],
        foreground=THEME['log_fg'],
        insertbackground=THEME['accent'],
        borderwidth=0,
        highlightthickness=0,
        relief='flat'
    )


def configure_theme(style: ttk.Style, window: tk.Tk):
    base_theme = 'ipmonitor'
    if base_theme not in style.theme_names():
        style.theme_create(base_theme, parent='clam', settings={
            '.': {
                'configure': {
                    'background': THEME['bg'],
                    'foreground': THEME['text'],
                    'font': DEFAULT_FONT
                }
            },
            'TFrame': {
                'configure': {'background': THEME['bg']}
            },
            'Surface.TFrame': {
                'configure': {'background': THEME['bg']}
            },
            'Toolbar.TFrame': {
                'configure': {'background': THEME['toolbar_bg']}
            },
            'Card.TLabelframe': {
                'configure': {
                    'background': THEME['panel'],
                    'foreground': THEME['text'],
                    'bordercolor': THEME['border'],
                    'borderwidth': 1,
                    'relief': 'solid'
                }
            },
            'Card.TLabelframe.Label': {
                'configure': {
                    'background': THEME['panel'],
                    'foreground': THEME['text'],
                    'font': HEADER_FONT
                }
            },
            'Settings.TCheckbutton': {
                'configure': {
                    'background': THEME['panel'],
                    'foreground': THEME['text']
                }
            },
            'TLabel': {
                'configure': {
                    'background': THEME['bg'],
                    'foreground': THEME['text']
                }
            }
        })

    style.theme_use(base_theme)
    style.configure('Primary.TButton',
                    background=THEME['accent'],
                    foreground='#ffffff',
                    padding=8,
                    relief='flat',
                    borderwidth=0)
    style.map('Primary.TButton',
              background=[('active', THEME['accent_hover'])],
              foreground=[('active', '#ffffff')])

    style.configure('Secondary.TButton',
                background=THEME['toolbar_bg'],
                foreground=THEME['text'],
                padding=6,
                relief='flat',
                borderwidth=1,
                bordercolor=THEME['toolbar_border'])
    style.map('Secondary.TButton',
            background=[('active', '#dbeafe')],
            foreground=[('active', THEME['text'])])

    style.configure('Action.TButton',
                background=THEME['button_action_bg'],
                foreground=THEME['button_action_fg'],
                padding=6,
                relief='flat',
                borderwidth=1,
                bordercolor=THEME['button_action_border'])
    style.map('Action.TButton',
            background=[('active', THEME['button_action_hover'])],
            foreground=[('active', THEME['button_action_fg'])])

    style.configure('Card.TFrame', background=THEME['panel'])
    style.configure('Muted.TLabel', background=THEME['panel'], foreground=THEME['muted'])
    style.configure('Surface.TFrame', background=THEME['bg'])
    style.configure('Settings.TCheckbutton', focuscolor=THEME['accent'])
    style.configure('StatusIdle.TLabel',
                    background=THEME['status_idle_bg'],
                    foreground=THEME['status_idle_fg'],
                    padding=(12, 4),
                    font=DEFAULT_FONT)
    style.configure('StatusRunning.TLabel',
                    background=THEME['status_running_bg'],
                    foreground=THEME['status_running_fg'],
                    padding=(12, 4),
                    font=DEFAULT_FONT)
    style.configure('StatusError.TLabel',
                    background='#fee2e2',
                    foreground='#b91c1c',
                    padding=(12, 4),
                    font=DEFAULT_FONT)

    checkbox_images = ensure_checkbox_images(window)
    if 'FlatCheckbox.indicator' not in style.element_names():
        style.element_create(
            'FlatCheckbox.indicator',
            'image',
            checkbox_images['unchecked'],
            ('disabled', 'selected', checkbox_images['checked_disabled']),
            ('disabled', checkbox_images['unchecked_disabled']),
            ('selected', checkbox_images['checked']),
            ('pressed', 'selected', checkbox_images['checked_hover']),
            ('active', 'selected', checkbox_images['checked_hover']),
            ('pressed', checkbox_images['unchecked_hover']),
            ('active', checkbox_images['unchecked_hover'])
        )

    def replace_indicator(layout_spec):
        replaced = []
        for element, options in layout_spec:
            new_element = 'FlatCheckbox.indicator' if element == 'Checkbutton.indicator' else element
            new_options = dict(options)
            if 'children' in new_options:
                new_options['children'] = replace_indicator(tuple(new_options['children']))
            replaced.append((new_element, new_options))
        return tuple(replaced)

    default_check_layout = style.layout('TCheckbutton')
    style.layout('Settings.TCheckbutton', replace_indicator(default_check_layout))
    style.map('Settings.TCheckbutton', foreground=[('disabled', THEME['muted'])])

    window.configure(bg=THEME['bg'])
    apply_system_titlebar(window)


DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36


def hex_to_colorref(hex_color: str) -> int:
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        hex_color = 'ffffff'
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_system_titlebar(window: tk.Tk):
    try:
        dwm = ctypes.windll.dwmapi
    except (AttributeError, OSError):
        return

    window.update_idletasks()
    hwnd_local = window.winfo_id()
    caption_color = ctypes.c_int(hex_to_colorref(THEME['titlebar']))
    text_color = ctypes.c_int(hex_to_colorref(THEME['title_text']))
    border_color = ctypes.c_int(hex_to_colorref(THEME['border']))

    for attr, value in (
        (DWMWA_CAPTION_COLOR, caption_color),
        (DWMWA_TEXT_COLOR, text_color),
        (DWMWA_BORDER_COLOR, border_color),
    ):
        try:
            dwm.DwmSetWindowAttribute(
                wintypes.HWND(hwnd_local),
                ctypes.c_int(attr),
                ctypes.byref(value),
                ctypes.sizeof(value)
            )
        except Exception:
            continue


def get_available_wsl_distros():
    try:
        result = run_command(['wsl', '-l', '-q'], capture_output=True, check=True)
        raw_bytes = result.stdout
        try:
            decoded = raw_bytes.decode('utf-16')
        except UnicodeDecodeError:
            decoded = raw_bytes.decode('utf-8', errors='ignore')
        distros = [line.strip() for line in decoded.splitlines() if line.strip()]
        return distros
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        log_message(f"获取 WSL 列表失败: {exc}", level='ERROR')
        return []


HOST_IGNORE_SET = {
    'localhost', 'localhost.localdomain', 'localhost6', 'ip6-localhost', 'ip6-loopback',
    'ip6-localnet', 'ip6-mcastprefix', 'ip6-allnodes', 'ip6-allrouters', 'ip6-allhosts'
}


def parse_hosts_lines(lines):
    entries = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if '#' in line:
            line = line.split('#', 1)[0].strip()
        parts = line.split()
        if len(parts) < 2:
            continue
        ip = parts[0]
        for host in parts[1:]:
            hostname = host.strip()
            if not hostname or hostname in HOST_IGNORE_SET:
                continue
            entries.append({'ip': ip, 'domain': hostname})
    return entries


def fetch_windows_hosts_entries():
    try:
        with open(WINDOWS_HOSTS_FILE, 'r', encoding='utf-8') as file:
            lines = file.readlines()
        return parse_hosts_lines(lines)
    except OSError as exc:
        log_message(f'读取 Windows hosts 文件失败: {exc}', level='ERROR')
        return []


def fetch_wsl_hosts_entries(wsl_name):
    try:
        result = run_command([
            'wsl', '-d', wsl_name, 'cat', '/etc/hosts'
        ], capture_output=True, text=True, check=True, encoding='utf-8')
        lines = result.stdout.splitlines()
        return parse_hosts_lines(lines)
    except subprocess.CalledProcessError as exc:
        log_message(f"读取 {wsl_name} hosts 文件失败: {exc.stderr.strip() if exc.stderr else exc}", level='ERROR')
    except Exception as exc:
        log_message(f"访问 {wsl_name} hosts 文件出错: {exc}", level='ERROR')
    return []


def gather_domain_candidates():
    candidates = []
    windows_entries = fetch_windows_hosts_entries()
    for entry in windows_entries:
        candidates.append({
            'source': 'Windows',
            'domain': entry['domain'],
            'ip': entry['ip']
        })

    for distro in wsl_names:
        distro_entries = fetch_wsl_hosts_entries(distro)
        for entry in distro_entries:
            candidates.append({
                'source': f'WSL:{distro}',
                'domain': entry['domain'],
                'ip': entry['ip']
            })

    return candidates


def get_ip_from_adapter(adapter_name: str | None) -> str | None:
    if not adapter_name:
        return None
    addrs = psutil.net_if_addrs().get(adapter_name)
    if not addrs:
        return None
    for addr in addrs:
        if addr.family == socket.AF_INET and addr.address and not addr.address.startswith('127.'):
            return addr.address
    return None


def detect_ip_via_udp() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        local_ip = sock.getsockname()[0]
        sock.close()
        return local_ip
    except Exception as exc:
        log_message(f"自动探测 IP 时出错: {exc}", level='ERROR')
        return None


def get_current_ip():
    strategy = config.get('ip_lookup_strategy', 'auto')
    if strategy == 'adapter':
        adapter_name = config.get('preferred_adapter', '')
        adapter_ip = get_ip_from_adapter(adapter_name)
        if adapter_ip:
            return adapter_ip
        log_message('指定网卡无法获取 IPv4 地址，回退到自动探测。', level='WARNING')
    return detect_ip_via_udp()

def update_hosts_file(new_ip):
    if len(domains) > 0:
        update_windows_hosts(new_ip)
        update_wsl_hosts(new_ip)

        log_message('更新完成...')
    else:
        log_message('未指定域名，忽略更新...')

def update_windows_hosts(new_ip):
    try:
        with open(WINDOWS_HOSTS_FILE, 'r', encoding='utf-8') as file:
            lines = file.readlines()

        new_lines = []
        append_lines = []
        changed = False
        for domain in domains:
            domain_found = False
            for i, line in enumerate(lines):
                if domain in line:
                    new_line = re.sub(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', new_ip, line)
                    if lines[i] != new_line:
                        changed = True
                        lines[i] = new_line
                    domain_found = True
            if not domain_found:
                changed = True
                append_lines.append(f'{new_ip} {domain}\n')

        if changed == False:
            log_message(f'Windows Hosts 文件不需要更新，新 IP 地址为: {new_ip}')
            return 

        new_lines.extend(lines)

        if len(append_lines) > 0:
            new_lines.append(f'\n')
            new_lines.append(f'\n')
            new_lines.append(f'# Added by host-updater\n')
            new_lines.extend(append_lines)
            new_lines.append(f'# End of section')

        with open(WINDOWS_HOSTS_FILE, 'w', encoding='utf-8') as file:
            file.writelines(new_lines)

        log_message(f'Windows Hosts 文件已更新，新 IP 地址为: {new_ip}')

    except Exception as e:
        log_message(f'更新 Windows Hosts 文件时出错: {e}', level='ERROR')

def update_wsl_hosts(new_ip):
    for wsl_name in wsl_names:
        try:
            result = run_command([
                'wsl', '-d', wsl_name, 'cat', '/etc/hosts'
            ], capture_output=True, text=True, check=True, encoding='utf-8')
            wsl_hosts_lines = result.stdout.splitlines()
        except subprocess.CalledProcessError as exc:
            log_message(f"读取 {wsl_name} 的 hosts 文件失败: {exc.stderr.strip() if exc.stderr else exc}", level='ERROR')
            continue
        except Exception as exc:
            log_message(f"访问 WSL {wsl_name} 时出现未知错误: {exc}", level='ERROR')
            continue

        append_lines = []
        changed = False
        for domain in domains:
            domain_found = False
            domain_pattern = re.compile(rf'(?:^|\s){re.escape(domain)}(?:\s|$)')
            for i, line in enumerate(wsl_hosts_lines):
                if domain_pattern.search(line):
                    new_line = f'{new_ip}\t{domain}'
                    if wsl_hosts_lines[i].strip() != new_line:
                        wsl_hosts_lines[i] = new_line
                        changed = True
                    domain_found = True
                    break
            if not domain_found:
                append_lines.append(f'{new_ip}\t{domain}')
                changed = True

        if not changed:
            log_message(f'WSL {wsl_name} 中的 hosts 文件不需要更新，新 IP 地址为: {new_ip}')
            continue

        if append_lines:
            wsl_hosts_lines.extend(['', '', '# Added by host-monitor'])
            wsl_hosts_lines.extend(append_lines)
            wsl_hosts_lines.append('# End of section')

        hosts_content = '\n'.join(wsl_hosts_lines) + '\n'
        try:
            run_command([
                'wsl', '-u', 'root', '-d', wsl_name, 'bash', '-c', 'cat > /etc/hosts'
            ], input=hosts_content, text=True, check=True, encoding='utf-8')
            log_message(f"已将更改同步到 {wsl_name} 的 hosts 文件")
        except subprocess.CalledProcessError as exc:
            log_message(f"写入 {wsl_name} 的 hosts 文件失败: {exc.stderr.strip() if exc.stderr else exc}", level='ERROR')
        except Exception as exc:
            log_message(f"同步到 {wsl_name} 时出现未知错误: {exc}", level='ERROR')
def check_ip_change():
    current_ip = get_current_ip()
    if current_ip:
        update_hosts_file(current_ip)
    else:
        log_message('无法获取当前 IP 地址，等待下一次重试。')

    global running
    while running:
        time.sleep(interval)
        new_ip = get_current_ip()
        if not new_ip:
            log_message('无法获取 IP 地址，保持上一次结果。')
            continue
        if new_ip != current_ip:
            update_hosts_file(new_ip)
            current_ip = new_ip
        #else:
            # log_message('IP 未发生变更，忽略更新...')
def toggle_monitoring():
    if running:
        stop_monitoring()
    else:
        start_monitoring()

def refresh():
    ip = get_current_ip()
    if ip:
        update_hosts_file(ip)
    else:
        log_message('无法手动刷新 IP：未获取到有效地址。', level='WARNING')


def manual_refresh():
    try:
        refresh_thread = threading.Thread(target=refresh)
        refresh_thread.daemon = True
        refresh_thread.start()
    except Exception as e:
        log_message(f"启动刷新线程时出错: {e}", level='ERROR')

def add_wsl():
    available = [d for d in get_available_wsl_distros() if d not in wsl_names]
    selections = show_selection_dialog(
        "选择 WSL 分发版",
        available,
        multi=True,
        empty_message='未发现可添加的 WSL 分发版，可手动输入。'
    )

    if not selections:
        return

    for name in selections:
        if name in wsl_names:
            continue
        wsl_names.append(name)
        wsl_listbox.insert(tk.END, name)
        log_message(f'已添加 WSL: {name}')

def add_wsl_manual():
    wsl_name = simpledialog.askstring("手动添加 WSL", "请输入 WSL 名称:", parent=root)
    if wsl_name:
        wsl_names.append(wsl_name)
        wsl_listbox.insert(tk.END, wsl_name)
        log_message(f'已添加自定义 WSL: {wsl_name}')

def remove_wsl():
    selected_index = wsl_listbox.curselection()
    if selected_index:
        index = selected_index[0]
        wsl_names.pop(index)
        wsl_listbox.delete(index)

def modify_wsl():
    selected_index = wsl_listbox.curselection()
    if selected_index:
        index = selected_index[0]
        new_name = simpledialog.askstring("修改 WSL", "请输入新的 WSL 名称:", initialvalue=wsl_names[index], parent=root)
        if new_name:
            wsl_names[index] = new_name
            wsl_listbox.delete(index)
            wsl_listbox.insert(index, new_name)

def add_domain():
    domain = simpledialog.askstring("添加域名", "请输入需要更新的域名:", parent=root)
    if domain:
        domains.append(domain)
        domain_listbox.insert(tk.END, domain)

def remove_domain():
    selected_index = domain_listbox.curselection()
    if selected_index:
        index = selected_index[0]
        domains.pop(index)
        domain_listbox.delete(index)

def modify_domain():
    selected_index = domain_listbox.curselection()
    if selected_index:
        index = selected_index[0]
        new_domain = simpledialog.askstring("修改域名", "请输入新的域名:", initialvalue=domains[index], parent=root)
        if new_domain:
            domains[index] = new_domain
            domain_listbox.delete(index)
            domain_listbox.insert(index, new_domain)


def import_domains_from_hosts():
    candidates = gather_domain_candidates()
    if not candidates:
        log_message('未能从 hosts 文件中获取到可用域名。')
        return

    existing = set(domains)
    option_map = []
    option_labels = []
    for entry in candidates:
        if entry['domain'] in existing:
            continue
        label = f"[{entry['source']}] {entry['domain']} ({entry['ip']})"
        option_labels.append(label)
        option_map.append(entry)

    if not option_labels:
        log_message('所有可用域名已在列表中，无需导入。')
        return

    selections = show_selection_dialog(
        "从 hosts 导入域名",
        option_labels,
        multi=True,
        empty_message='暂无可导入的域名。'
    )

    if not selections:
        return

    label_to_entry = {label: entry for label, entry in zip(option_labels, option_map)}
    for label in selections:
        entry = label_to_entry.get(label)
        if not entry:
            continue
        domain = entry['domain']
        if domain in domains:
            continue
        domains.append(domain)
        domain_listbox.insert(tk.END, domain)
        log_message(f"已导入域名 {domain} 来自 {entry['source']}")

def persist_lists():
    try:
        with open(WSL_FILE, 'w', encoding='utf-8') as f:
            for wsl in wsl_names:
                f.write(wsl + '\n')
        with open(DOMAIN_FILE, 'w', encoding='utf-8') as f:
            for domain in domains:
                f.write(domain + '\n')
    except OSError as exc:
        log_message(f'保存配置列表失败: {exc}', level='ERROR')


def show_window():
    if root:
        root.deiconify()
        root.state('normal')
        root.lift()
        root.focus_force()


def hide_window_to_tray():
    create_tray_icon()
    if root:
        root.withdraw()
        log_message('窗口已最小化到系统托盘，右键图标可退出。')


def handle_close_request():
    hide_window_to_tray()


def on_window_state_change(event):
    if root and root.state() == 'iconic':
        hide_window_to_tray()


def destroy_tray_icon():
    global tray_icon_created, nid, hwnd
    if tray_icon_created and nid:
        win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
    tray_icon_created = False
    nid = None
    if hwnd:
        try:
            win32gui.DestroyWindow(hwnd)
        except Exception:
            pass


def load_icon_handle(hinst, path: str | None, flags: int) -> int | None:
    if not path:
        return None
    try:
        return win32gui.LoadImage(hinst, path, win32con.IMAGE_ICON, 0, 0, flags)
    except Exception:
        return None


def resolve_icon_variant(filename: str) -> str | None:
    return locate_icon_file(filename)


def prepare_tray_icon_handles(hinst):
    global tray_icon_handles
    handles = {'idle': None, 'running': None, 'error': None}

    icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
    base_icon = resolve_icon_path()
    running_icon = locate_icon_file('icon-running.ico')
    handles['running'] = load_icon_handle(hinst, running_icon, icon_flags)
    if not handles['running']:
        handles['running'] = load_icon_handle(hinst, base_icon, icon_flags)

    idle_icon = resolve_icon_variant('icon-idle.ico') or resolve_icon_variant('icon_inactive.ico')
    handles['idle'] = load_icon_handle(hinst, idle_icon, icon_flags)

    error_icon = resolve_icon_variant('icon-error.ico') or resolve_icon_variant('icon_alert.ico')
    handles['error'] = load_icon_handle(hinst, error_icon, icon_flags)

    if not handles['running']:
        handles['running'] = win32gui.LoadIcon(0, win32con.IDI_INFORMATION)
    if not handles['idle']:
        handles['idle'] = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
    if not handles['error']:
        handles['error'] = win32gui.LoadIcon(0, win32con.IDI_WARNING)

    tray_icon_handles = handles


def exit_application():
    log_message('正在退出 IP 监控工具...')
    persist_lists()
    save_config()
    destroy_tray_icon()
    if single_instance_mutex:
        try:
            win32event.ReleaseMutex(single_instance_mutex)
        except Exception:
            pass
    global monitor_health_job
    if root and monitor_health_job:
        try:
            root.after_cancel(monitor_health_job)
        except Exception:
            pass
    if root:
        root.quit()
        root.destroy()


def create_tray_icon():
    global hwnd, nid, tray_icon_created, tray_window_class_atom
    if tray_icon_created:
        return

    hinst = win32api.GetModuleHandle(None)
    prepare_tray_icon_handles(hinst)
    initial_icon = tray_icon_handles.get(tray_icon_state) or tray_icon_handles.get('idle') or tray_icon_handles.get('running')
    if not initial_icon:
        initial_icon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def tray_wnd_proc(hWnd, msg, wParam, lParam):
        if msg == TRAY_MESSAGE_ID:
            if lParam == win32con.WM_LBUTTONDBLCLK:
                show_window()
            elif lParam == win32con.WM_RBUTTONUP:
                menu = win32gui.CreatePopupMenu()
                win32gui.AppendMenu(menu, win32con.MF_STRING, 1, "显示窗口")
                win32gui.AppendMenu(menu, win32con.MF_STRING, 2, "退出")
                pos = win32gui.GetCursorPos()
                win32gui.SetForegroundWindow(hWnd)
                win32gui.TrackPopupMenu(menu, win32con.TPM_LEFTALIGN, pos[0], pos[1], 0, hWnd, None)
                win32gui.PostMessage(hWnd, win32con.WM_NULL, 0, 0)
        elif msg == win32con.WM_COMMAND:
            if wParam == 1:
                show_window()
            elif wParam == 2:
                exit_application()
        elif msg == win32con.WM_DESTROY:
            if nid:
                win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hWnd, msg, wParam, lParam)

    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = tray_wnd_proc
    wc.hInstance = hinst
    wc.lpszClassName = "IPMonitorTray"

    try:
        if tray_window_class_atom is None:
            tray_window_class_atom = win32gui.RegisterClass(wc)
    except pywintypes.error as exc:
        log_message(f"窗口类注册失败: {exc}", level='ERROR')
        return

    try:
        hwnd = win32gui.CreateWindow(tray_window_class_atom, "IP 监控工具", 0, 0, 0, 0, 0, 0, 0, hinst, None)
    except pywintypes.error as exc:
        log_message(f"窗口创建失败: {exc}", level='ERROR')
        return

    nid = (hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, TRAY_MESSAGE_ID, initial_icon, TRAY_TOOLTIP)
    try:
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
        tray_icon_created = True
    except pywintypes.error as exc:
        log_message(f"系统托盘图标添加失败: {exc}", level='ERROR')
        return

    update_tray_icon_state(tray_icon_state, monitor_status_var.get() if monitor_status_var else None)

# 读取 WSL 列表和域名列表文件
def read_lists():
    global wsl_names, domains
    if os.path.exists(WSL_FILE):
        with open(WSL_FILE, 'r', encoding='utf-8') as f:
            wsl_names = [line.strip() for line in f.readlines() if line.strip()]
    if os.path.exists(DOMAIN_FILE):
        with open(DOMAIN_FILE, 'r', encoding='utf-8') as f:
            domains = [line.strip() for line in f.readlines() if line.strip()]


load_config()
sync_interval_from_config()
enforce_single_instance()
read_lists()

# 创建主窗口
root = tk.Tk()
root.title("IP 监控工具")
root.resizable(True, True)
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

def apply_window_icon(window: tk.Tk):
    global WINDOW_ICON_IMAGE
    icon_file = resolve_icon_path()
    if not icon_file:
        return
    try:
        window.iconbitmap(icon_file)
    except Exception:
        try:
            WINDOW_ICON_IMAGE = tk.PhotoImage(file=icon_file)
            window.iconphoto(True, WINDOW_ICON_IMAGE)
        except Exception:
            pass


apply_window_icon(root)

style = ttk.Style()
configure_theme(style, root)

main_frame = ttk.Frame(root, style='Surface.TFrame')
main_frame.grid(row=0, column=0, sticky="nsew", padx=24, pady=24)
for col in range(2):
    main_frame.columnconfigure(col, weight=1)
main_frame.rowconfigure(0, weight=0)
main_frame.rowconfigure(1, weight=0)
main_frame.rowconfigure(2, weight=1)
main_frame.rowconfigure(3, weight=1)

monitor_status_var = tk.StringVar(value='已暂停')

# 监控控制
control_frame = ttk.LabelFrame(main_frame, text="监控控制", style='Card.TLabelframe')
control_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
control_frame.columnconfigure(0, weight=1)
control_frame.columnconfigure(1, weight=1)

monitor_status_var = tk.StringVar(value='已暂停')
monitor_status_label = ttk.Label(control_frame, textvariable=monitor_status_var, style='StatusIdle.TLabel')
monitor_status_label.grid(row=0, column=0, columnspan=2, sticky='w', padx=12, pady=(10, 6))

button_row = ttk.Frame(control_frame, style='Card.TFrame')
button_row.grid(row=1, column=0, columnspan=2, sticky='ew', padx=12, pady=(0, 12))
button_row.columnconfigure(0, weight=1)
button_row.columnconfigure(1, weight=1)

monitor_button = ttk.Button(button_row, text="开启定时监测", command=toggle_monitoring, style='Primary.TButton')
monitor_button.grid(row=0, column=0, padx=(0, 6), sticky='ew')

refresh_button = ttk.Button(button_row, text="手动刷新", command=manual_refresh, style='Secondary.TButton')
refresh_button.grid(row=0, column=1, padx=(6, 0), sticky='ew')

# 常规设置
settings_frame = ttk.LabelFrame(main_frame, text="常规设置", style='Card.TLabelframe')
settings_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 18))

single_instance_var = tk.BooleanVar(value=config.get("enforce_single_instance", True))


def on_single_instance_toggle():
    config["enforce_single_instance"] = single_instance_var.get()
    save_config()
    log_message('单实例限制将在下次启动时生效。')


single_instance_check = ttk.Checkbutton(
    settings_frame,
    text="仅允许运行一个实例",
    variable=single_instance_var,
    command=on_single_instance_toggle,
    style='Settings.TCheckbutton'
)
single_instance_check.pack(anchor='w', pady=4, padx=12)

close_hint_label = ttk.Label(
    settings_frame,
    text="关闭按钮会最小化到托盘，右键托盘图标可退出程序。",
    style='Muted.TLabel'
)
close_hint_label.pack(anchor='w', pady=(0, 6), padx=12)

ttk.Separator(settings_frame, orient='horizontal').pack(fill=tk.X, padx=12, pady=(8, 8))

advanced_frame = ttk.Frame(settings_frame, style='Card.TFrame')
advanced_frame.pack(fill=tk.X, padx=12, pady=(0, 8))

auto_start_var = tk.BooleanVar(value=config.get("auto_start_monitor", False))
auto_start_check = ttk.Checkbutton(
    advanced_frame,
    text="启动后自动开始监测",
    variable=auto_start_var,
    command=on_auto_start_toggle,
    style='Settings.TCheckbutton'
)
auto_start_check.pack(anchor='w', pady=(0, 6))

interval_row = ttk.Frame(advanced_frame, style='Card.TFrame')
interval_row.pack(fill=tk.X, pady=4)
ttk.Label(interval_row, text="扫描间隔 (秒)", style='Muted.TLabel').pack(side=tk.LEFT)
interval_var = tk.IntVar(value=interval)
interval_spinbox = ttk.Spinbox(
    interval_row,
    from_=5,
    to=3600,
    increment=5,
    width=10,
    textvariable=interval_var,
    justify='center',
    command=on_interval_change
)
interval_spinbox.pack(side=tk.LEFT, padx=(12, 0))
interval_spinbox.bind('<FocusOut>', on_interval_change)
interval_spinbox.bind('<Return>', on_interval_change)

log_level_row = ttk.Frame(advanced_frame, style='Card.TFrame')
log_level_row.pack(fill=tk.X, pady=4)
ttk.Label(log_level_row, text="日志级别", style='Muted.TLabel').pack(side=tk.LEFT)
log_level_var = tk.StringVar(value=normalize_log_level(config.get('log_level', 'INFO')))
log_level_combo = ttk.Combobox(log_level_row, textvariable=log_level_var, values=LOG_LEVELS, state='readonly', width=10)
log_level_combo.pack(side=tk.LEFT, padx=(12, 0))
log_level_combo.bind('<<ComboboxSelected>>', on_log_level_change)

ip_strategy_row = ttk.Frame(advanced_frame, style='Card.TFrame')
ip_strategy_row.pack(fill=tk.X, pady=4)
ttk.Label(ip_strategy_row, text="IP 获取策略", style='Muted.TLabel').pack(side=tk.LEFT)
ip_strategy_var = tk.StringVar(value=strategy_label_for_key(config.get('ip_lookup_strategy', 'auto')))
ip_strategy_combo = ttk.Combobox(
    ip_strategy_row,
    textvariable=ip_strategy_var,
    values=list(IP_STRATEGIES.values()),
    state='readonly',
    width=22
)
ip_strategy_combo.pack(side=tk.LEFT, padx=(12, 0))
ip_strategy_combo.bind('<<ComboboxSelected>>', on_ip_strategy_change)

adapter_row = ttk.Frame(advanced_frame, style='Card.TFrame')
adapter_row.pack(fill=tk.X, pady=4)
ttk.Label(adapter_row, text="首选网卡", style='Muted.TLabel').pack(side=tk.LEFT)
adapter_var = tk.StringVar(value=config.get('preferred_adapter', ''))
adapter_combo = ttk.Combobox(adapter_row, textvariable=adapter_var, width=28, state='disabled')
adapter_combo.pack(side=tk.LEFT, padx=(12, 6))
adapter_combo.bind('<<ComboboxSelected>>', on_adapter_selected)
ttk.Button(adapter_row, text="刷新", command=update_adapter_combobox_state, style='Secondary.TButton').pack(side=tk.LEFT)
update_adapter_combobox_state()

lists_container = ttk.Frame(main_frame, style='Surface.TFrame')
lists_container.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 18))
lists_container.columnconfigure(0, weight=1)
lists_container.columnconfigure(1, weight=1)
lists_container.rowconfigure(0, weight=1)

# WSL 管理
wsl_frame = ttk.LabelFrame(lists_container, text="WSL 列表", style='Card.TLabelframe')
wsl_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
wsl_frame.columnconfigure(0, weight=1)
wsl_frame.columnconfigure(1, weight=0)
wsl_frame.rowconfigure(0, weight=1)

wsl_list_container = ttk.Frame(wsl_frame, style='Card.TFrame')
wsl_list_container.grid(row=0, column=0, sticky="nsew")
wsl_listbox = Listbox(wsl_list_container)
wsl_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=12)
wsl_scrollbar = ttk.Scrollbar(wsl_list_container, orient="vertical", command=wsl_listbox.yview)
wsl_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 12), pady=12)
wsl_listbox.config(yscrollcommand=wsl_scrollbar.set)

for wsl in wsl_names:
    wsl_listbox.insert(tk.END, wsl)
apply_listbox_theme(wsl_listbox)

wsl_button_frame = ttk.Frame(wsl_frame, style='Card.TFrame')
wsl_button_frame.grid(row=0, column=1, sticky="ns", padx=16, pady=12)

auto_add_wsl_button = ttk.Button(wsl_button_frame, text="自动发现", command=add_wsl, style='Action.TButton')
auto_add_wsl_button.pack(pady=4, fill=tk.X)
manual_add_wsl_button = ttk.Button(wsl_button_frame, text="手动添加", command=add_wsl_manual, style='Action.TButton')
manual_add_wsl_button.pack(pady=4, fill=tk.X)
remove_wsl_button = ttk.Button(wsl_button_frame, text="删除", command=remove_wsl, style='Action.TButton')
remove_wsl_button.pack(pady=4, fill=tk.X)
modify_wsl_button = ttk.Button(wsl_button_frame, text="修改", command=modify_wsl, style='Action.TButton')
modify_wsl_button.pack(pady=4, fill=tk.X)

# 域名管理
domain_frame = ttk.LabelFrame(lists_container, text="域名列表", style='Card.TLabelframe')
domain_frame.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
domain_frame.columnconfigure(0, weight=1)
domain_frame.columnconfigure(1, weight=0)
domain_frame.rowconfigure(0, weight=1)

domain_list_container = ttk.Frame(domain_frame, style='Card.TFrame')
domain_list_container.grid(row=0, column=0, sticky="nsew")
domain_listbox = Listbox(domain_list_container)
domain_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0), pady=12)
domain_scrollbar = ttk.Scrollbar(domain_list_container, orient="vertical", command=domain_listbox.yview)
domain_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 12), pady=12)
domain_listbox.config(yscrollcommand=domain_scrollbar.set)

for domain in domains:
    domain_listbox.insert(tk.END, domain)
apply_listbox_theme(domain_listbox)

domain_button_frame = ttk.Frame(domain_frame, style='Card.TFrame')
domain_button_frame.grid(row=0, column=1, sticky="ns", padx=16, pady=12)

import_domain_button = ttk.Button(domain_button_frame, text="从 hosts 导入", command=import_domains_from_hosts, style='Action.TButton')
import_domain_button.pack(pady=4, fill=tk.X)
add_domain_button = ttk.Button(domain_button_frame, text="手动添加", command=add_domain, style='Action.TButton')
add_domain_button.pack(pady=4, fill=tk.X)
remove_domain_button = ttk.Button(domain_button_frame, text="删除", command=remove_domain, style='Action.TButton')
remove_domain_button.pack(pady=4, fill=tk.X)
modify_domain_button = ttk.Button(domain_button_frame, text="修改", command=modify_domain, style='Action.TButton')
modify_domain_button.pack(pady=4, fill=tk.X)

# 消息区域
message_frame = ttk.LabelFrame(main_frame, text="运行日志", style='Card.TLabelframe')
message_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
message_frame.columnconfigure(0, weight=1)
message_frame.rowconfigure(0, weight=1)

message_display = tk.Text(message_frame, height=6, state='disabled')
message_display.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
message_scrollbar = ttk.Scrollbar(message_frame, orient="vertical", command=message_display.yview)
message_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
message_display.config(yscrollcommand=message_scrollbar.set)
apply_text_theme(message_display)
render_log_buffer()

update_monitor_status_indicator('idle')
monitor_health_tick()

if config.get('auto_start_monitor'):
    root.after(600, start_monitoring)

log_message('应用已启动，等待操作。')

create_tray_icon()
root.protocol("WM_DELETE_WINDOW", handle_close_request)
root.bind("<Unmap>", on_window_state_change)

screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()
window_width = 1024
window_height = 800
x = (screen_width - window_width) // 2
y = (screen_height - window_height) // 2
root.geometry(f"{window_width}x{window_height}+{x}+{y}")

root.mainloop()