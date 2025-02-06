'''
Copyright (C) 2023-2025 by tinbox.wu, All Rights Reserved. 

FilePath     : host-updater.py
Author       : tinbox.wu tinboxwu@gmail.com

Date         : 2025-02-05 16:41:34
LastEditors  : tinbox.wu tinboxwu@gmail.com
LastEditTime : 2025-02-06 10:19:43
Description  : 

'''
import socket
import time
import re
import os
import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog, Listbox, Button
import psutil
import threading
import win32gui
import win32con
import win32api
import win32com.client
import subprocess
import shlex
import tempfile


# Windows 系统 hosts 文件路径
WINDOWS_HOSTS_FILE = r'C:\Windows\System32\drivers\etc\hosts'
# 全局变量
running = False
interval = 60  # 检查间隔时间（秒）
wsl_names = []  # 存储 WSL 名称
domains = []  # 存储需要更新的域名

# 保存 WSL 列表和域名列表的文件路径
WSL_FILE = 'wsl_list.txt'
DOMAIN_FILE = 'domain_list.txt'

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
        print(f"获取 IP 地址时出错: {e}")
        return None

def update_hosts_file(new_ip):
    if len(domains) > 0:
        update_windows_hosts(new_ip)
        update_wsl_hosts(new_ip)

        print(f'更新完成...')
        message_display.insert(tk.END, f'更新完成...\n')
    else:
        print(f'未指定域名，忽略更新...')
        message_display.insert(tk.END, f'未指定域名，忽略更新...\n')

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
            print(f'Windows Hosts 文件不需要更新，新 IP 地址为: {new_ip}')
            message_display.insert(tk.END, f'Windows Hosts 文件不需要更新，新 IP 地址为: {new_ip}\n')
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

        print(f'Windows Hosts 文件已更新，新 IP 地址为: {new_ip}')
        message_display.insert(tk.END, f"Windows Hosts 文件已更新，新 IP 地址为: {new_ip}\n")

    except Exception as e:
        print(f'更新 Windows Hosts 文件时出错: {e}')
        message_display.insert(tk.END, f"更新 Windows Hosts 文件时出错: {e}\n")

def update_wsl_hosts(new_ip):
    for wsl_name in wsl_names:
        try:
            # 读取 WSL 中 hosts 文件内容
            read_command = f'wsl -d {wsl_name} cat /etc/hosts'
            result = subprocess.run(read_command, shell=True, capture_output=True, text=True, encoding='utf-8')
            if result.returncode == 0:
                # 命令执行成功，处理标准输出
                wsl_hosts_lines = result.stdout.splitlines()
                #print(wsl_hosts_lines)
            else:
                # 命令执行失败，打印错误信息
                print(f"同步到 {wsl_name} 的 hosts 文件时出现错误: {result.stderr}")
                message_display.insert(tk.END, f"同步到 {wsl_name} 的 hosts 文件时出现错误: {result.stderr}\n")
                return

            new_wsl_hosts_lines = []
            append_lines = []
            changed = False
            for domain in domains:
                domain_found = False
                for i, line in enumerate(wsl_hosts_lines):
                    if domain in line:
                        new_line = f'{new_ip}\t{domain}'
                        if wsl_hosts_lines[i] == new_line:
                            changed = True
                            wsl_hosts_lines[i] = new_line
                        domain_found = True
                if not domain_found:
                    changed = True
                    append_lines.append(f'{new_ip}\t{domain}')

            if changed == False:
                print(f'WSL 中的 hosts 文件不需要更新，新 IP 地址为: {new_ip}')
                message_display.insert(tk.END, f'WSL 中的 hosts 文件不需要更新，新 IP 地址为: {new_ip}\n')
                return 

            new_wsl_hosts_lines.extend(wsl_hosts_lines)

            if len(append_lines) > 0:
                new_wsl_hosts_lines.append(f'')
                new_wsl_hosts_lines.append(f'')
                new_wsl_hosts_lines.append(f'# Added by host-updater')
                new_wsl_hosts_lines.extend(append_lines)
                new_wsl_hosts_lines.append(f'# End of section')

            for line in new_wsl_hosts_lines:
                write_one_line = f'wsl -d {wsl_name}'

            # 将更新后的内容写入 WSL 的 hosts 文件
            echo_cmd = f'bash -c "echo -e \\"{chr(10).join(new_wsl_hosts_lines)}\\" > /etc/hosts"'
            # 替换换行符，这里将换行符替换为 \n 字符串
            echo_cmd = echo_cmd.replace('\n', '\\n')
            write_command = f'wsl -u root -d {wsl_name} {echo_cmd}'
            subprocess.run(write_command, shell=True, check=True)

            print(f"已将更改同步到 {wsl_name} 的 hosts 文件\n")
            message_display.insert(tk.END, f"已将更改同步到 {wsl_name} 的 hosts 文件\n")
        except subprocess.CalledProcessError as e:
            print(f"同步到 {wsl_name} 的 hosts 文件时出错: {e}")
            message_display.insert(tk.END, f"同步到 {wsl_name} 的 hosts 文件时出错: {e}\n")
        except Exception as e:
            print(f"同步到 {wsl_name} 的 hosts 文件时出现未知错误: {e}")
            message_display.insert(tk.END, f"同步到 {wsl_name} 的 hosts 文件时出现未知错误: {e}\n")
def check_ip_change():
    current_ip = get_current_ip()
    if current_ip:
        update_hosts_file(current_ip)

    global running
    while running:
        time.sleep(interval)
        new_ip = get_current_ip()
        if new_ip and new_ip != current_ip:
            update_hosts_file(new_ip)
            current_ip = new_ip
        else:
            print(f'ip未发生变更，忽略更新...')
            message_display.insert(tk.END, f"ip未发生变更，忽略更新...\n")

def start_monitoring():
    global running
    # 首先检查是否已经有监测在运行，如果是则不重复启动
    if running:
        print("监测已经在运行中，无需重复启动。")
        return

    running = True
    try:
        # 创建一个新的线程来执行 check_ip_change 函数
        monitor_thread = threading.Thread(target=check_ip_change)
        # 将线程设置为守护线程，这样当主线程退出时，该线程也会自动退出
        monitor_thread.daemon = True
        # 启动线程
        monitor_thread.start()
        monitor_button.config(text="关闭定时监测")
        print("IP 监测已启动。")
    except Exception as e:
        # 若线程创建失败，打印错误信息并重置状态
        print(f"启动监测线程时出错: {e}")
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

def manual_refresh():
    try:
        # 创建一个新的线程来执行 refresh 函数
        refresh_thread = threading.Thread(target=refresh)
        # 将线程设置为守护线程，这样当主线程退出时，该线程也会自动退出
        refresh_thread.daemon = True
        # 启动线程
        refresh_thread.start()
    except Exception as e:
        # 若线程创建失败，打印错误信息并重置状态
        print(f"启动监测线程时出错: {e}")

def add_wsl():
    wsl_name = simpledialog.askstring("添加 WSL", "请输入 WSL 名称:")
    if wsl_name:
        wsl_names.append(wsl_name)
        wsl_listbox.insert(tk.END, wsl_name)

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
        new_name = simpledialog.askstring("修改 WSL", "请输入新的 WSL 名称:", initialvalue=wsl_names[index])
        if new_name:
            wsl_names[index] = new_name
            wsl_listbox.delete(index)
            wsl_listbox.insert(index, new_name)

def add_domain():
    domain = simpledialog.askstring("添加域名", "请输入需要更新的域名:")
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
        new_domain = simpledialog.askstring("修改域名", "请输入新的域名:", initialvalue=domains[index])
        if new_domain:
            domains[index] = new_domain
            domain_listbox.delete(index)
            domain_listbox.insert(index, new_domain)

def set_interval():
    global interval
    new_interval = simpledialog.askinteger("设置扫描间隔", "请输入扫描间隔（秒）:", initialvalue=interval)
    if new_interval:
        interval = new_interval

def on_closing():
    #if messagebox.askokcancel("退出", "确定要退出吗？"):
    # 保存 WSL 列表和域名列表到文件
    with open(WSL_FILE, 'w', encoding='utf-8') as f:
        for wsl in wsl_names:
            f.write(wsl + '\n')
    with open(DOMAIN_FILE, 'w', encoding='utf-8') as f:
        for domain in domains:
            f.write(domain + '\n')

    root.destroy()
    # 移除系统托盘图标
    win32gui.DestroyWindow(hwnd)

def show_window():
    root.deiconify()
    root.lift()
    root.focus_force()

def create_tray_icon():
    global hwnd
    hinst = win32api.GetModuleHandle(None)
    try:
        # 尝试加载自定义图标
        icon_path = "icon.ico"
        icon_flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        hicon = win32gui.LoadImage(hinst, icon_path, win32con.IMAGE_ICON, 0, 0, icon_flags)
    except Exception:
        # 若加载失败，使用系统默认图标
        hicon = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    class GUID:
        def __init__(self, s):
            self.s = s

    def WndProc(hWnd, msg, wParam, lParam):
        if msg == win32con.WM_USER + 20:
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
        elif msg == win32con.WM_DESTROY:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, nid)
            win32gui.PostQuitMessage(0)
        return win32gui.DefWindowProc(hWnd, msg, wParam, lParam)

    wc = win32gui.WNDCLASS()
    wc.lpfnWndProc = WndProc
    wc.hInstance = hinst
    wc.lpszClassName = "IPMonitorTray"
    try:
        class_atom = win32gui.RegisterClass(wc)
        print(f"窗口类注册成功，类原子: {class_atom}")
    except Exception as e:
        print(f"窗口类注册失败: {e}")
        return

    try:
        hwnd = win32gui.CreateWindow(class_atom, "IP 监控工具", 0, 0, 0, 0, 0, 0, 0, hinst, None)
        print(f"窗口创建成功，窗口句柄: {hwnd}")
    except Exception as e:
        print(f"窗口创建失败: {e}")
        return

    nid = (hwnd, 0, win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP, win32con.WM_USER + 20, hicon, "IP 监控工具")
    try:
        win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
        print("系统托盘图标添加成功")
    except Exception as e:
        print(f"系统托盘图标添加失败: {e}")

# 读取 WSL 列表和域名列表文件
def read_lists():
    global wsl_names, domains
    if os.path.exists(WSL_FILE):
        with open(WSL_FILE, 'r', encoding='utf-8') as f:
            wsl_names = [line.strip() for line in f.readlines()]
    if os.path.exists(DOMAIN_FILE):
        with open(DOMAIN_FILE, 'r', encoding='utf-8') as f:
            domains = [line.strip() for line in f.readlines()]

# 创建主窗口
root = tk.Tk()
root.title("IP 监控工具")
# 使窗口可缩放
root.resizable(True, True)

# 设置行和列的权重，使组件可以随着窗口大小改变而自适应
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

style = ttk.Style()
style.theme_use('clam')  # 使用 'clam' 主题

# 读取 WSL 列表和域名列表
read_lists()

# 主框架，用于容纳所有的控件
main_frame = tk.Frame(root)
main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

# 设置主框架的行和列的权重
main_frame.columnconfigure(0, weight=1)
main_frame.rowconfigure(0, weight=1)
main_frame.rowconfigure(1, weight=1)
main_frame.rowconfigure(2, weight=1)

# 按钮框架，用于放置监控和刷新按钮
button_frame = tk.Frame(main_frame)
button_frame.grid(row=0, column=0, sticky="ew", pady=10)

# 监控按钮
monitor_button = tk.Button(button_frame, text="开启定时监测", command=toggle_monitoring)
monitor_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

# 手动刷新按钮
refresh_button = tk.Button(button_frame, text="手动刷新", command=manual_refresh)
refresh_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

# 设置扫描间隔按钮
set_interval_button = tk.Button(button_frame, text="设置扫描间隔", command=set_interval)
set_interval_button.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

# WSL 管理框架
wsl_frame = tk.Frame(main_frame)
wsl_frame.grid(row=1, column=0, sticky="nsew", pady=20)

# 设置 WSL 管理框架的行和列的权重
wsl_frame.columnconfigure(0, weight=1)
wsl_frame.columnconfigure(1, weight=0)
wsl_frame.rowconfigure(0, weight=0)
wsl_frame.rowconfigure(1, weight=1)

# WSL 标签
wsl_label = tk.Label(wsl_frame, text="WSL 列表:")
wsl_label.grid(row=0, column=0, sticky="w")

# WSL 列表框
wsl_listbox = Listbox(wsl_frame)
# 插入 WSL 列表数据
for wsl in wsl_names:
    wsl_listbox.insert(tk.END, wsl)
wsl_listbox.grid(row=1, column=0, sticky="nsew")

# WSL 按钮框架
wsl_button_frame = tk.Frame(wsl_frame)
wsl_button_frame.grid(row=1, column=1, sticky="ns", padx=10)

# WSL 管理按钮
add_wsl_button = Button(wsl_button_frame, text="添加", command=add_wsl)
add_wsl_button.pack(pady=5, fill=tk.X)
remove_wsl_button = Button(wsl_button_frame, text="删除", command=remove_wsl)
remove_wsl_button.pack(pady=5, fill=tk.X)
modify_wsl_button = Button(wsl_button_frame, text="修改", command=modify_wsl)
modify_wsl_button.pack(pady=5, fill=tk.X)

# 域名管理框架
domain_frame = tk.Frame(main_frame)
domain_frame.grid(row=2, column=0, sticky="nsew", pady=20)

# 设置域名管理框架的行和列的权重
domain_frame.columnconfigure(0, weight=1)
domain_frame.columnconfigure(1, weight=0)
domain_frame.rowconfigure(0, weight=0)
domain_frame.rowconfigure(1, weight=1)

# 域名标签
domain_label = tk.Label(domain_frame, text="域名列表:")
domain_label.grid(row=0, column=0, sticky="w")

# 域名列表框
domain_listbox = Listbox(domain_frame)
# 插入域名列表数据
for domain in domains:
    domain_listbox.insert(tk.END, domain)
domain_listbox.grid(row=1, column=0, sticky="nsew")

# 域名按钮框架
domain_button_frame = tk.Frame(domain_frame)
domain_button_frame.grid(row=1, column=1, sticky="ns", padx=10)

# 域名管理按钮
add_domain_button = Button(domain_button_frame, text="添加", command=add_domain)
add_domain_button.pack(pady=5, fill=tk.X)
remove_domain_button = Button(domain_button_frame, text="删除", command=remove_domain)
remove_domain_button.pack(pady=5, fill=tk.X)
modify_domain_button = Button(domain_button_frame, text="修改", command=modify_domain)
modify_domain_button.pack(pady=5, fill=tk.X)

# 添加消息显示区域
message_display = tk.Text(main_frame, height=5)
message_display.grid(row=3, column=0, sticky="nsew", pady=10)

# 创建系统托盘图标
hwnd = None
create_tray_icon()

# 处理窗口关闭事件
root.protocol("WM_DELETE_WINDOW", on_closing)

# 处理窗口缩小事件，将窗口隐藏并放入系统托盘
def on_minimize(event):
    root.withdraw()

root.bind("<Unmap>", on_minimize)

# 获取屏幕的宽度和高度
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

# 获取窗口的宽度和高度
window_width = 500
window_height = 700

# 计算窗口的位置
x = (screen_width - window_width) // 2
y = (screen_height - window_height) // 2

# 设置窗口的位置
root.geometry(f"{window_width}x{window_height}+{x}+{y}")

# 运行主循环
root.mainloop()