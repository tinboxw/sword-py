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
status_sync_job = None
WINDOW_ICON_IMAGE = None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, '_MEIPASS', BASE_DIR)
    return os.path.join(base_path, relative_path)

# 保存 WSL 列表和域名列表的文件路径
WSL_FILE = os.path.join(BASE_DIR, 'wsl_list.txt')
DOMAIN_FILE = os.path.join(BASE_DIR, 'domain_list.txt')
CONFIG_FILE = os.path.join(BASE_DIR, 'host_monitor_config.json')

DEFAULT_CONFIG = {
    "enforce_single_instance": True
}

config = {}
single_instance_mutex = None

LOG_CAPACITY = 500
log_buffer = deque(maxlen=LOG_CAPACITY)

TRAY_MESSAGE_ID = win32con.WM_USER + 20
TRAY_TOOLTIP = "IP 监控工具"
hwnd = None
nid = None
tray_icon_created = False
tray_window_class_atom = None

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


def save_config():
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as file:
            json.dump(config, file, ensure_ascii=False, indent=2)
    except OSError as exc:
        print(f"保存配置文件失败: {exc}")


def show_system_alert(message, title="IP 监控工具"):
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        print(message)


def enforce_single_instance():
    global single_instance_mutex
    if not config.get("enforce_single_instance", True):
        return
    mutex_name = "HostMonitorMutex"
    try:
        single_instance_mutex = win32event.CreateMutex(None, False, mutex_name)
        last_error = win32api.GetLastError()
        if last_error == winerror.ERROR_ALREADY_EXISTS:
            show_system_alert("检测到已有实例在运行，已阻止重复启动。")
            raise SystemExit(0)
    except pywintypes.error as exc:
        print(f"创建单实例互斥量失败: {exc}")


def render_log_buffer():
    if not (message_display and message_display.winfo_exists()):
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

    message_display.after(0, refresh)


def log_message(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    text = f'[{timestamp}] {message}'
    print(text)
    log_buffer.appendleft(text)
    render_log_buffer()


def update_monitor_status_indicator(is_running: bool):
    if not monitor_status_var or not monitor_status_label:
        return

    text = '监控运行中' if is_running else '已暂停'
    style_name = 'StatusRunning.TLabel' if is_running else 'StatusIdle.TLabel'
    monitor_status_var.set(text)
    monitor_status_label.configure(style=style_name)


def schedule_status_indicator_refresh():
    global status_sync_job
    if not root:
        return

    update_monitor_status_indicator(running)
    status_sync_job = root.after(1000, schedule_status_indicator_refresh)


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
        result = subprocess.run(['wsl', '-l', '-q'], capture_output=True, check=True)
        raw_bytes = result.stdout
        try:
            decoded = raw_bytes.decode('utf-16')
        except UnicodeDecodeError:
            decoded = raw_bytes.decode('utf-8', errors='ignore')
        distros = [line.strip() for line in decoded.splitlines() if line.strip()]
        return distros
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        log_message(f"获取 WSL 列表失败: {exc}")
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
        log_message(f'读取 Windows hosts 文件失败: {exc}')
        return []


def fetch_wsl_hosts_entries(wsl_name):
    try:
        result = subprocess.run([
            'wsl', '-d', wsl_name, 'cat', '/etc/hosts'
        ], capture_output=True, text=True, check=True, encoding='utf-8')
        lines = result.stdout.splitlines()
        return parse_hosts_lines(lines)
    except subprocess.CalledProcessError as exc:
        log_message(f"读取 {wsl_name} hosts 文件失败: {exc.stderr.strip() if exc.stderr else exc}")
    except Exception as exc:
        log_message(f"访问 {wsl_name} hosts 文件出错: {exc}")
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


def get_current_ip():
    try:
        # 尝试创建一个 UDP 套接字并连接到一个公网服务器
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        # 获取本地绑定的 IP 地址
        local_ip = s.getsockname()[0]
        s.close()

        # 遍历所有网络接口，找到匹配的 IP 地址对应的接口
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and addr.address == local_ip:
                    return addr.address
        return None
    except Exception as e:
        log_message(f"获取 IP 地址时出错: {e}")
        return None

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
        log_message(f'更新 Windows Hosts 文件时出错: {e}')

def update_wsl_hosts(new_ip):
    for wsl_name in wsl_names:
        try:
            result = subprocess.run([
                'wsl', '-d', wsl_name, 'cat', '/etc/hosts'
            ], capture_output=True, text=True, check=True, encoding='utf-8')
            wsl_hosts_lines = result.stdout.splitlines()
        except subprocess.CalledProcessError as exc:
            log_message(f"读取 {wsl_name} 的 hosts 文件失败: {exc.stderr.strip() if exc.stderr else exc}")
            continue
        except Exception as exc:
            log_message(f"访问 WSL {wsl_name} 时出现未知错误: {exc}")
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
            subprocess.run([
                'wsl', '-u', 'root', '-d', wsl_name, 'bash', '-c', 'cat > /etc/hosts'
            ], input=hosts_content, text=True, check=True, encoding='utf-8')
            log_message(f"已将更改同步到 {wsl_name} 的 hosts 文件")
        except subprocess.CalledProcessError as exc:
            log_message(f"写入 {wsl_name} 的 hosts 文件失败: {exc.stderr.strip() if exc.stderr else exc}")
        except Exception as exc:
            log_message(f"同步到 {wsl_name} 时出现未知错误: {exc}")
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
        else:
            log_message('IP 未发生变更，忽略更新...')

def start_monitoring():
    global running
    # 首先检查是否已经有监测在运行，如果是则不重复启动
    global monitor_button
    if running:
        log_message("监测已经在运行中，无需重复启动。")
        return

    running = True
    try:
        monitor_thread = threading.Thread(target=check_ip_change)
        monitor_thread.daemon = True
        monitor_thread.start()
        monitor_button.config(text="关闭定时监测")
        log_message("IP 监测已启动。")
    except Exception as e:
        log_message(f"启动监测线程时出错: {e}")
        running = False

def stop_monitoring():
    global running
    running = False
    monitor_button.config(text="开启定时监测")

def toggle_monitoring():
    global running
    if running:
        stop_monitoring()
    else:
        start_monitoring()

def refresh():
    ip = get_current_ip()
    if ip:
        update_hosts_file(ip)
    else:
        log_message('无法手动刷新 IP：未获取到有效地址。')

def manual_refresh():
    try:
        # 创建一个新的线程来执行 refresh 函数
        refresh_thread = threading.Thread(target=refresh)
        update_monitor_status_indicator(True)
        # 将线程设置为守护线程，这样当主线程退出时，该线程也会自动退出
        refresh_thread.daemon = True
        # 启动线程
        update_monitor_status_indicator(False)
        refresh_thread.start()
    except Exception as e:
        # 若线程创建失败，打印错误信息并重置状态
        log_message(f"启动刷新线程时出错: {e}")

def add_wsl():
    update_monitor_status_indicator(False)
    log_message("IP 监测已停止。")
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

def set_interval():
    global interval
    new_interval = simpledialog.askinteger("设置扫描间隔", "请输入扫描间隔（秒）:", initialvalue=interval, parent=root)
    if new_interval:
        interval = new_interval
        log_message(f'扫描间隔已更新为 {interval} 秒')

def persist_lists():
    try:
        with open(WSL_FILE, 'w', encoding='utf-8') as f:
            for wsl in wsl_names:
                f.write(wsl + '\n')
        with open(DOMAIN_FILE, 'w', encoding='utf-8') as f:
            for domain in domains:
                f.write(domain + '\n')
    except OSError as exc:
        log_message(f'保存配置列表失败: {exc}')


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
    global status_sync_job
    if root and status_sync_job:
        try:
            root.after_cancel(status_sync_job)
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
    icon_path = resource_path('icon.ico')
    try:
        icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        hicon = win32gui.LoadImage(hinst, icon_path, win32con.IMAGE_ICON, 0, 0, icon_flags)
    except Exception:
        hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

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
        log_message(f"窗口类注册失败: {exc}")
        return

    try:
        hwnd = win32gui.CreateWindow(tray_window_class_atom, "IP 监控工具", 0, 0, 0, 0, 0, 0, 0, hinst, None)
    except pywintypes.error as exc:
        log_message(f"窗口创建失败: {exc}")
        return

    nid = (hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, TRAY_MESSAGE_ID, hicon, TRAY_TOOLTIP)
    try:
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
        tray_icon_created = True
    except pywintypes.error as exc:
        log_message(f"系统托盘图标添加失败: {exc}")

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
    icon_file = resource_path('icon.ico')
    if not os.path.exists(icon_file):
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
main_frame.columnconfigure(0, weight=1)
main_frame.rowconfigure(0, weight=0)
main_frame.rowconfigure(1, weight=0)
main_frame.rowconfigure(2, weight=1)
main_frame.rowconfigure(3, weight=1)
main_frame.rowconfigure(4, weight=1)

# 顶部按钮
button_frame = ttk.Frame(main_frame, style='Toolbar.TFrame', padding=10)
button_frame.grid(row=0, column=0, sticky="ew", pady=(0, 14))

toolbar_button_container = ttk.Frame(button_frame, style='Toolbar.TFrame')
toolbar_button_container.pack(side=tk.LEFT, fill=tk.X, expand=True)

monitor_button = ttk.Button(toolbar_button_container, text="开启定时监测", command=toggle_monitoring, style='Primary.TButton')
monitor_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

refresh_button = ttk.Button(toolbar_button_container, text="手动刷新", command=manual_refresh, style='Secondary.TButton')
refresh_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

set_interval_button = ttk.Button(toolbar_button_container, text="设置扫描间隔", command=set_interval, style='Secondary.TButton')
set_interval_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

monitor_status_var = tk.StringVar(value='已暂停')
monitor_status_label = ttk.Label(button_frame, textvariable=monitor_status_var, style='StatusIdle.TLabel')
monitor_status_label.pack(side=tk.RIGHT, padx=(12, 0))
schedule_status_indicator_refresh()

# 常规设置
settings_frame = ttk.LabelFrame(main_frame, text="常规设置", style='Card.TLabelframe')
settings_frame.grid(row=1, column=0, sticky="ew", pady=(0, 18))

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

# WSL 管理
wsl_frame = ttk.LabelFrame(main_frame, text="WSL 列表", style='Card.TLabelframe')
wsl_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 18))
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
domain_frame = ttk.LabelFrame(main_frame, text="域名列表", style='Card.TLabelframe')
domain_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 18))
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
message_frame.grid(row=4, column=0, sticky="nsew")
message_frame.columnconfigure(0, weight=1)
message_frame.rowconfigure(0, weight=1)

message_display = tk.Text(message_frame, height=6, state='disabled')
message_display.grid(row=0, column=0, sticky="nsew", padx=(12, 0), pady=12)
message_scrollbar = ttk.Scrollbar(message_frame, orient="vertical", command=message_display.yview)
message_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 12), pady=12)
message_display.config(yscrollcommand=message_scrollbar.set)
apply_text_theme(message_display)
render_log_buffer()

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