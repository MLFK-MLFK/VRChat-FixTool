#!/usr/bin/env python3
"""
VRChat 便捷工具助手
以 explorer.exe 为父进程启动 start_protected_game.exe
"""

import os
import sys
import shutil
import webbrowser
import configparser
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import ctypes
from ctypes import wintypes, Structure, sizeof, byref
import subprocess


# ============================================================
# 常量
# ============================================================
APP_NAME = "VRC-Fix"
VERSION = "1.2"
CFG_FILE = "cfg.ini"
TARGET_EXE = "start_protected_game.exe"
TARGET_EXE_LOCAL = "VRChat.exe"

# ReShade 相关文件/文件夹
RESHADE_INSTALL_ITEMS = ["dxgi.dll", "reshade-shaders"]
RESHADE_REMOVE_ITEMS = [
    "dxgi.dll", "reshade-shaders", "ReShade.ini", "ReShade.log",
    "ShaderCache", "ShaderFixes", "Presets","ReShadePreset.ini","ReShadeVR.ini",
]

# 获取程序所在目录（兼容 PyInstaller 打包）
def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

APP_DIR = get_app_dir()
CFG_PATH = os.path.join(APP_DIR, CFG_FILE)

# ℹ 信息窗口内容（从 info.txt 加载）
def _load_info_content():
    path = os.path.join(APP_DIR, "info.txt")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "info.txt 未找到"

INFO_CONTENT = _load_info_content()


# ============================================================
# 配置文件管理
# ============================================================
class ConfigManager:
    """管理 cfg.ini 配置文件"""

    SECTION = "VRChat"

    @staticmethod
    def exists():
        return os.path.isfile(CFG_PATH)

    @staticmethod
    def load():
        """读取配置，返回 (path, found, affinity, auto_exit)"""
        config = configparser.ConfigParser()
        config.read(CFG_PATH, encoding="utf-8")
        try:
            path = config.get(ConfigManager.SECTION, "install_path")
            if not path or not os.path.isdir(path):
                return "", False, False, False
            affinity = config.getboolean(ConfigManager.SECTION, "affinity", fallback=False)
            auto_exit = config.getboolean(ConfigManager.SECTION, "auto_exit", fallback=False)
            return path, True, affinity, auto_exit
        except (configparser.NoSectionError, configparser.NoOptionError):
            pass
        return "", False, False, False

    @staticmethod
    def save(install_path, affinity_enabled=False, auto_exit_enabled=False):
        """保存配置（安装路径 + CPU 亲和力 + 自动退出）"""
        config = configparser.ConfigParser()
        config[ConfigManager.SECTION] = {
            "install_path": install_path,
            "affinity": str(affinity_enabled),
            "auto_exit": str(auto_exit_enabled),
        }
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            config.write(f)


# ============================================================
# Windows API 结构体（模块级别定义，供 Win32ParentLaunch 使用）
# ============================================================

class _STARTUPINFOW(Structure):
    _fields_ = [
        ("cb",              wintypes.DWORD),
        ("lpReserved",      wintypes.LPWSTR),
        ("lpDesktop",       wintypes.LPWSTR),
        ("lpTitle",         wintypes.LPWSTR),
        ("dwX",             wintypes.DWORD),
        ("dwY",             wintypes.DWORD),
        ("dwXSize",         wintypes.DWORD),
        ("dwYSize",         wintypes.DWORD),
        ("dwXCountChars",   wintypes.DWORD),
        ("dwYCountChars",   wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags",         wintypes.DWORD),
        ("wShowWindow",     wintypes.WORD),
        ("cbReserved2",     wintypes.WORD),
        ("lpReserved2",     ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput",       wintypes.HANDLE),
        ("hStdOutput",      wintypes.HANDLE),
        ("hStdError",       wintypes.HANDLE),
    ]


class _STARTUPINFOEXW(Structure):
    _fields_ = [
        ("StartupInfo",     _STARTUPINFOW),
        ("lpAttributeList", ctypes.c_void_p),
    ]


class _PROCESS_INFORMATION(Structure):
    _fields_ = [
        ("hProcess",    wintypes.HANDLE),
        ("hThread",     wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId",  wintypes.DWORD),
    ]


# ============================================================
# Windows API — 以 explorer.exe 为父进程启动程序
# ============================================================
class Win32ParentLaunch:
    """
    使用 Win32 API 将目标程序以 explorer.exe 为父进程启动。
    实现原理：
      1. 找到 explorer.exe 的 PID
      2. OpenProcess 获取句柄
      3. 通过 PROC_THREAD_ATTRIBUTE_PARENT_PROCESS 属性列表
      4. CreateProcessW 创建进程，父进程为 explorer.exe
    """

    # Win32 常量
    CREATE_NEW_CONSOLE          = 0x00000010
    CREATE_NO_WINDOW            = 0x08000000
    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    PROC_THREAD_ATTRIBUTE_PARENT_PROCESS = 0x00020000
    PROCESS_CREATE_PROCESS      = 0x0080
    PROCESS_QUERY_INFORMATION   = 0x0400
    PROCESS_DUP_HANDLE          = 0x0040

    @staticmethod
    def _find_explorer_pid():
        """定位 shell explorer.exe 的 PID"""
        # 方法一：通过 Shell 窗口
        shell_hwnd = ctypes.windll.user32.GetShellWindow()
        if shell_hwnd:
            pid = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(shell_hwnd, byref(pid))
            if pid.value:
                return pid.value

        # 方法二：tasklist 备用
        try:
            result = subprocess.run(
                ['tasklist', '/FI', 'IMAGENAME eq explorer.exe', '/FO', 'CSV', '/NH'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in result.stdout.strip().split('\n'):
                parts = line.replace('"', '').split(',')
                if len(parts) >= 2 and parts[0].strip().lower() == 'explorer.exe':
                    pid = int(parts[1].strip())
                    if pid > 0:
                        return pid
        except Exception:
            pass

        return None

    @staticmethod
    def launch(exe_path, args=None, working_dir=None):
        """
        以 explorer.exe 为父进程启动目标程序。
        args: 附加命令行参数（如 "--no-vr"），可以是字符串或字符串列表。
        返回新进程的 PID；失败抛 RuntimeError。
        """
        full_path = os.path.abspath(exe_path)
        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"目标文件不存在: {full_path}")

        if working_dir is None:
            working_dir = os.path.dirname(full_path)

        explorer_pid = Win32ParentLaunch._find_explorer_pid()
        if explorer_pid is None:
            raise RuntimeError("无法定位 explorer.exe 进程，请确认资源管理器正在运行")

        kernel32 = ctypes.windll.kernel32

        # 打开 explorer.exe 进程句柄（需要 PROCESS_CREATE_PROCESS 权限）
        desired_access = (Win32ParentLaunch.PROCESS_CREATE_PROCESS |
                          Win32ParentLaunch.PROCESS_QUERY_INFORMATION |
                          Win32ParentLaunch.PROCESS_DUP_HANDLE)
        h_parent = kernel32.OpenProcess(desired_access, False, explorer_pid)
        if not h_parent:
            err = kernel32.GetLastError()
            raise RuntimeError(
                f"无法打开 explorer.exe 进程句柄 (PID={explorer_pid}, 错误码={err})\n"
                f"请确认本程序未以管理员身份运行（explorer.exe 通常以普通用户运行）。"
            )

        try:
            # 第一步：查询属性列表所需大小
            size_needed = ctypes.c_size_t(0)
            INITIALIZE_FLAGS = 0
            kernel32.InitializeProcThreadAttributeList(
                None, 1, INITIALIZE_FLAGS, byref(size_needed)
            )
            # size_needed 现在是实际需要的字节数

            # 第二步：分配并初始化属性列表
            attr_list_buf = ctypes.create_string_buffer(size_needed.value)
            if not kernel32.InitializeProcThreadAttributeList(
                attr_list_buf, 1, INITIALIZE_FLAGS, byref(size_needed)
            ):
                err = kernel32.GetLastError()
                raise RuntimeError(f"InitializeProcThreadAttributeList 失败 (错误码={err})")

            try:
                # 第三步：设置父进程属性
                parent_handle_val = ctypes.c_uint64(h_parent)
                if not kernel32.UpdateProcThreadAttribute(
                    attr_list_buf,
                    0,
                    Win32ParentLaunch.PROC_THREAD_ATTRIBUTE_PARENT_PROCESS,
                    byref(parent_handle_val),
                    ctypes.sizeof(parent_handle_val),
                    None,
                    None,
                ):
                    err = kernel32.GetLastError()
                    raise RuntimeError(f"UpdateProcThreadAttribute 失败 (错误码={err})")

                # 第四步：构建 STARTUPINFOEX
                si = _STARTUPINFOEXW()
                si.StartupInfo.cb = sizeof(_STARTUPINFOEXW)
                si.StartupInfo.dwFlags = 0
                si.lpAttributeList = ctypes.cast(attr_list_buf, ctypes.c_void_p)

                pi = _PROCESS_INFORMATION()

                # 第五步：创建进程
                cmd_line = f'"{full_path}"'
                if args:
                    if isinstance(args, str):
                        cmd_line += f" {args}"
                    else:
                        cmd_line += " " + " ".join(args)
                success = kernel32.CreateProcessW(
                    None,                           # lpApplicationName
                    cmd_line,                       # lpCommandLine
                    None,                           # lpProcessAttributes
                    None,                           # lpThreadAttributes
                    False,                          # bInheritHandles
                    Win32ParentLaunch.EXTENDED_STARTUPINFO_PRESENT,  # dwCreationFlags
                    None,                           # lpEnvironment
                    working_dir,                    # lpCurrentDirectory
                    byref(si.StartupInfo),          # lpStartupInfo
                    byref(pi),                      # lpProcessInformation
                )

                if not success:
                    err = kernel32.GetLastError()
                    raise RuntimeError(f"CreateProcessW 失败 (错误码={err})")

                # 关闭返回的句柄（进程已创建，不需要持有）
                kernel32.CloseHandle(pi.hThread)
                kernel32.CloseHandle(pi.hProcess)

                return pi.dwProcessId

            finally:
                kernel32.DeleteProcThreadAttributeList(attr_list_buf)

        finally:
            kernel32.CloseHandle(h_parent)


# ============================================================
# 主界面
# ============================================================
class VRChatHelperApp:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("540x680")
        self.root.resizable(True, True)
        self.root.minsize(460, 700)

        # 窗口图标
        ico_path = os.path.join(APP_DIR, "icon.ico")
        if os.path.isfile(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception:
                pass

        # 窗口居中
        self._center_window()

        # 状态变量
        self.install_path = tk.StringVar()
        self.exe_status = tk.StringVar(value="检测中...")
        self.exe_exists = False
        self.affinity_enabled = tk.BooleanVar(value=False)
        self.auto_exit_enabled = tk.BooleanVar(value=False)
        self.reshade_disable = tk.BooleanVar(value=False)

        # 加载配置
        self._load_or_setup_config()

        # 构建界面
        self._build_ui()

        # 检测目标程序
        self._check_target_exe()

        # 检测 ReShade 状态
        self._detect_reshade_status()

        self.root.lift()
        self.root.focus_force()

        # 主窗口关闭时清理附属窗口
        self.root.protocol("WM_DELETE_WINDOW", self._on_main_close)

    # ---- 配置 ----

    def _load_or_setup_config(self):
        """加载 cfg.ini，若不存在则引导用户选择路径"""
        if ConfigManager.exists():
            path, ok, affinity, auto_exit = ConfigManager.load()
            if ok:
                self.install_path.set(path)
                self.affinity_enabled.set(affinity)
                self.auto_exit_enabled.set(auto_exit)
                return

        # 首次运行 / 配置无效 —— 弹出路径选择
        self._first_run_dialog()

    def _first_run_dialog(self):
        """首次运行：弹出文件夹选择对话框"""
        # 先隐藏主窗口
        self.root.withdraw()

        answer = messagebox.askyesno(
            f"{APP_NAME} — 首次运行",
            "未找到配置文件 cfg.ini。\n\n"
            "请选择 VRChat 安装目录（包含 start_protected_game.exe 的文件夹）。\n\n"
            "是否立即选择？\n\n"
            '（选择"否"将退出程序）'
        )
        if not answer:
            self.root.destroy()
            sys.exit(0)

        folder = filedialog.askdirectory(
            title="请选择 VRChat 安装目录，如果不知道在哪，可从Steam库中右键VRChat -> 管理 -> 浏览本地文件",
        )
        if not folder:
            messagebox.showwarning("未选择", "未选择任何目录，程序将退出。")
            self.root.destroy()
            sys.exit(0)

        # 规范化路径
        folder = os.path.abspath(folder)
        ConfigManager.save(folder, self.affinity_enabled.get(), self.auto_exit_enabled.get())
        self.install_path.set(folder)

        # 显示主窗口
        self.root.deiconify()

    # ---- UI 构建 ----

    def _build_ui(self):
        """构建界面组件 — CustomTkinter 现代化风格"""

        # 主容器
        main_frame = ctk.CTkFrame(self.root, corner_radius=12, fg_color="transparent")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=18, pady=(12, 8))

        # --- 标题行 ---
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill=tk.X, pady=(4, 12))

        ctk.CTkLabel(
            title_frame,
            text=f"🎮  {APP_NAME}",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=18, weight="bold"),
        ).pack(side=tk.LEFT)

        ctk.CTkLabel(
            title_frame,
            text=f"v{VERSION}",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(side=tk.LEFT, padx=(8, 0), pady=(5, 0))

        # --- 分隔线 ---
        sep = ctk.CTkFrame(main_frame, height=2, corner_radius=1, fg_color=("gray75", "gray30"))
        sep.pack(fill=tk.X, pady=(0, 14))

        # --- 路径显示区 ---
        path_section = ctk.CTkFrame(main_frame, corner_radius=10)
        path_section.pack(fill=tk.X, pady=(0, 12))

        ctk.CTkLabel(
            path_section,
            text="📁  VRChat 安装路径",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(10, 6))

        path_row = ctk.CTkFrame(path_section, fg_color="transparent")
        path_row.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.path_entry = ctk.CTkEntry(
            path_row,
            textvariable=self.install_path,
            state="disabled",
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=6,
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ctk.CTkButton(
            path_row,
            text="更改...",
            command=self._on_change_path,
            width=70,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
        ).pack(side=tk.LEFT, padx=(8, 0))

        # --- 目标文件状态 ---
        status_section = ctk.CTkFrame(main_frame, corner_radius=10)
        status_section.pack(fill=tk.X, pady=(0, 14))

        ctk.CTkLabel(
            status_section,
            text="🔍  目标程序状态",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(10, 6))

        status_row = ctk.CTkFrame(status_section, fg_color="transparent")
        status_row.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.status_label = ctk.CTkLabel(
            status_row,
            textvariable=self.exe_status,
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ctk.CTkButton(
            status_row,
            text="🔄 刷新",
            command=self._check_target_exe,
            width=70,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=12),
        ).pack(side=tk.RIGHT)

        # --- 操作按钮区 ---
        button_section = ctk.CTkFrame(main_frame, corner_radius=10)
        button_section.pack(fill=tk.X, pady=(0, 8))

        ctk.CTkLabel(
            button_section,
            text="🚀  启动模式",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(10, 6))

        btn_inner = ctk.CTkFrame(button_section, fg_color="transparent")
        btn_inner.pack(fill=tk.X, padx=10, pady=(0, 6))

        self.launch_pc_btn = ctk.CTkButton(
            btn_inner,
            text="🖥 PC模式启动（帧率优化）/支持一键多开",
            command=self._on_launch_pc,
            height=42,
            corner_radius=8,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.launch_pc_btn.pack(fill=tk.X, pady=(0, 6))

        self.launch_vr_btn = ctk.CTkButton(
            btn_inner,
            text="🥽 VR模式启动（帧率优化）",
            command=self._on_launch_vr_highfps,
            height=42,
            corner_radius=8,
            fg_color="#2B7A4B",
            hover_color="#1F5C36",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.launch_vr_btn.pack(fill=tk.X)

        self.launch_local_btn = ctk.CTkButton(
            btn_inner,
            text="🔧 本地测试模式启动",
            command=self._on_launch_local,
            height=42,
            corner_radius=8,
            fg_color="#6B5B2F",
            hover_color="#4A3D1F",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.launch_local_btn.pack(fill=tk.X, pady=(6, 0))

        # 自定义高级启动
        custom_frame = ctk.CTkFrame(button_section, fg_color="transparent")
        custom_frame.pack(fill=tk.X, padx=10, pady=(6, 6))

        self.custom_args_entry = ctk.CTkEntry(
            custom_frame,
            placeholder_text="输入自定义启动参数，例如: --no-vr --affinity=FF",
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
        )
        self.custom_args_entry.pack(fill=tk.X, pady=(0, 4))

        # 自定义按钮 + 信息小按钮 同行
        custom_btn_row = ctk.CTkFrame(custom_frame, fg_color="transparent")
        custom_btn_row.pack(fill=tk.X)

        self.launch_custom_btn = ctk.CTkButton(
            custom_btn_row,
            text="⚙ 自定义高级启动模式",
            command=self._on_launch_custom,
            height=32,
            corner_radius=6,
            fg_color="#3A5F6B",
            hover_color="#284550",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.launch_custom_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.info_btn = ctk.CTkButton(
            custom_btn_row,
            text="ℹ",
            command=self._on_show_info,
            width=32,
            height=32,
            corner_radius=6,
            font=ctk.CTkFont(size=14),
        )
        self.info_btn.pack(side=tk.RIGHT)

        # CPU 亲和力开关
        affinity_frame = ctk.CTkFrame(button_section, fg_color="transparent")
        affinity_frame.pack(fill=tk.X, padx=10, pady=(6, 10))

        self.affinity_switch = ctk.CTkSwitch(
            affinity_frame,
            text="AMD CPU 双CCD亲和力优化（如果负优化卡顿请关闭）",
            variable=self.affinity_enabled,
            onvalue=True,
            offvalue=False,
            command=self._on_affinity_changed,
            font=ctk.CTkFont(size=11),
        )
        self.affinity_switch.pack(side=tk.LEFT)

        # ReShade 注入 + 卸载
        reshade_frame = ctk.CTkFrame(button_section, fg_color="transparent")
        reshade_frame.pack(fill=tk.X, padx=10, pady=(2, 10))

        self.install_reshade_btn = ctk.CTkButton(
            reshade_frame,
            text="注入 ReShade/PC拍照滤镜，VR模式请禁用",
            command=self._on_install_reshade,
            height=30,
            corner_radius=6,
            font=ctk.CTkFont(size=11),
        )
        self.install_reshade_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.reshade_disable_switch = ctk.CTkSwitch(
            reshade_frame,
            text="禁用 Reshade",
            variable=self.reshade_disable,
            onvalue=True,
            offvalue=False,
            command=self._on_reshade_disable_toggle,
            font=ctk.CTkFont(size=11),
            switch_width=36,
            switch_height=18,
        )
        self.reshade_disable_switch.pack(side=tk.LEFT, padx=(0, 8))

        self.uninstall_reshade_btn = ctk.CTkButton(
            reshade_frame,
            text="彻底卸载 ReShade",
            command=self._on_uninstall_reshade,
            width=110,
            height=30,
            corner_radius=6,
            fg_color="#8B3A3A",
            hover_color="#6B2A2A",
            text_color="white",
            font=ctk.CTkFont(size=11),
        )
        self.uninstall_reshade_btn.pack(side=tk.RIGHT)

        # --- 底部 ---
        bottom_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(6, 0))

        self.auto_exit_switch = ctk.CTkSwitch(
            bottom_frame,
            text="启动完后自动退出本程序",
            variable=self.auto_exit_enabled,
            onvalue=True,
            offvalue=False,
            command=self._on_auto_exit_changed,
            font=ctk.CTkFont(size=10),
            switch_width=36,
            switch_height=18,
        )
        self.auto_exit_switch.pack(side=tk.BOTTOM, anchor="w")

        ctk.CTkLabel(
            bottom_frame,
            text="提示：所有运行均默认以explorer为父进程启动，不受本程序约束。",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).pack(side=tk.LEFT)

        self.about_btn = ctk.CTkButton(
            bottom_frame,
            text="关于",
            command=self._on_about,
            width=50,
            height=24,
            corner_radius=4,
            fg_color="transparent",
            hover_color=("gray80", "gray30"),
            text_color="gray",
            font=ctk.CTkFont(size=10),
        )
        self.about_btn.pack(side=tk.RIGHT)

    # ---- 功能 ----

    def _check_target_exe(self):
        """检测目标程序是否存在，更新 UI 状态"""
        path = self.install_path.get()
        if not path:
            self.exe_status.set("⚠ 未设置安装路径")
            self.exe_exists = False
            self._set_launch_state(False)
            return

        target = os.path.join(path, TARGET_EXE)
        if os.path.isfile(target):
            self.exe_status.set(f"✅ 已找到 — {target}")
            self.exe_exists = True
            self._set_launch_state(True)
        else:
            self.exe_status.set(f"❌ 未找到 {TARGET_EXE}\n   路径: {path}")
            self.exe_exists = False
            self._set_launch_state(False)

    def _set_launch_state(self, enabled):
        """启用 / 禁用启动按钮"""
        state = "normal" if enabled else "disabled"
        self.launch_pc_btn.configure(state=state)
        self.launch_vr_btn.configure(state=state)
        self.launch_local_btn.configure(state=state)
        self.launch_custom_btn.configure(state=state)

    def _on_launch_pc(self):
        """PC模式启动按钮回调（附加 --no-vr）"""
        self._do_launch("--no-vr --process-priority=2 --main-thread-priority=1", "PC模式启动（帧率优化）")

    def _on_launch_vr_highfps(self):
        """VR模式启动按钮回调 — 高帧优化"""
        self._do_launch(
            "--process-priority=2 --main-thread-priority=1 -screen-width 300 -screen-height 300",
            "VR模式启动（帧率优化）",
        )

    def _on_launch_local(self):
        """本地测试模式 — 启动 VRChat.exe 附加 --no-vr"""
        self._do_launch("--no-vr", "本地测试模式启动", target_exe=TARGET_EXE_LOCAL)

    def _on_launch_custom(self):
        """自定义高级启动 — 使用用户输入的参数"""
        custom_args = self.custom_args_entry.get().strip()
        if not custom_args:
            messagebox.showwarning("未输入参数", "请在文本框中输入启动参数。")
            return
        self._do_launch(custom_args, "自定义高级启动模式")

    def _on_show_info(self):
        """弹出信息窗口 — 紧贴主窗口右侧，等高"""
        if hasattr(self, '_info_win') and self._info_win.winfo_exists():
            self._info_win.lift()
            self._info_win.focus()
            return

        self._info_win = ctk.CTkToplevel(self.root)
        self._info_win.title("信息")
        self._info_win.resizable(True, True)

        # 尺寸与主窗口对齐
        self.root.update_idletasks()
        mw = self.root.winfo_width()
        mh = self.root.winfo_height()
        mx = self.root.winfo_x()
        my = self.root.winfo_y()

        self._info_win.geometry(f"{mw}x{mh}+{mx + mw}+{my}")

        # 可复制文本框
        info_text = ctk.CTkTextbox(self._info_win, corner_radius=8, font=ctk.CTkFont(size=12))
        info_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        info_text.insert("1.0", INFO_CONTENT)
        info_text.configure(state="disabled")

        # 主窗口移动时联动
        def _sync_position():
            if self._info_win.winfo_exists():
                try:
                    nx = self.root.winfo_x() + self.root.winfo_width()
                    ny = self.root.winfo_y()
                    self._info_win.geometry(f"+{nx}+{ny}")
                except Exception:
                    pass
            else:
                self.root.after_cancel(self._sync_id)

        def _schedule_sync():
            if hasattr(self, '_info_win') and self._info_win.winfo_exists():
                _sync_position()
                self._sync_id = self.root.after(200, _schedule_sync)

        _schedule_sync()

        self._info_win.protocol("WM_DELETE_WINDOW", lambda: self._info_win.destroy())

    def _on_main_close(self):
        """主窗口关闭时清理"""
        # 取消信息窗口位置同步定时器
        if hasattr(self, '_sync_id'):
            self.root.after_cancel(self._sync_id)
        if hasattr(self, '_info_win') and self._info_win.winfo_exists():
            self._info_win.destroy()
        self.root.destroy()
        sys.exit(0)

    def _on_about(self):
        """关于按钮 — 打开项目页面"""
        webbrowser.open("https://space.bilibili.com/308857431")

    def _on_affinity_changed(self):
        """亲和力开关切换时自动保存"""
        if self.install_path.get():
            ConfigManager.save(self.install_path.get(), self.affinity_enabled.get(), self.auto_exit_enabled.get())

    def _on_auto_exit_changed(self):
        """自动退出开关切换时保存"""
        if self.install_path.get():
            ConfigManager.save(self.install_path.get(), self.affinity_enabled.get(), self.auto_exit_enabled.get())

    def _detect_reshade_status(self):
        """启动时检测 VRChat 目录中的 ReShade 文件状态"""
        path = self.install_path.get()
        if not path or not os.path.isdir(path):
            return
        dll_path = os.path.join(path, "dxgi.dll")
        mlfk_path = os.path.join(path, "dxgi.MLFK")
        if os.path.isfile(mlfk_path):
            self.reshade_disable.set(True)
        elif os.path.isfile(dll_path):
            self.reshade_disable.set(False)
        else:
            self.reshade_disable.set(False)

    def _on_reshade_disable_toggle(self):
        """切换 ReShade 禁用状态 — 重命名 dxgi.dll ↔ dxgi.MLFK"""
        path = self.install_path.get()
        if not path or not os.path.isdir(path):
            messagebox.showwarning("未设置路径", "请先设置 VRChat 安装路径。")
            self.reshade_disable.set(not self.reshade_disable.get())
            return
        dll_path = os.path.join(path, "dxgi.dll")
        mlfk_path = os.path.join(path, "dxgi.MLFK")
        try:
            if self.reshade_disable.get():
                # 开启禁用: dxgi.dll → dxgi.MLFK
                if os.path.isfile(dll_path):
                    os.rename(dll_path, mlfk_path)
                elif not os.path.isfile(mlfk_path):
                    messagebox.showwarning("未安装 ReShade", "未找到 dxgi.dll，请先安装 ReShade。")
                    self.reshade_disable.set(False)
            else:
                # 关闭禁用: dxgi.MLFK → dxgi.dll
                if os.path.isfile(mlfk_path):
                    os.rename(mlfk_path, dll_path)
                elif not os.path.isfile(dll_path):
                    messagebox.showwarning("未安装 ReShade", "未找到 dxgi.MLFK，请先安装 ReShade。")
                    self.reshade_disable.set(True)
        except Exception as e:
            messagebox.showerror("操作失败", str(e))
            self.reshade_disable.set(not self.reshade_disable.get())

    def _on_install_reshade(self):
        """注入 ReShade — 复制 dxgi.dll 和 reshade-shaders 到 VRChat 目录"""
        path = self.install_path.get()
        if not path or not os.path.isdir(path):
            messagebox.showwarning("未设置路径", "请先设置 VRChat 安装路径。")
            return

        try:
            self._install_reshade_files(path)
            messagebox.showinfo("注入完成", "ReShade 文件已复制到 VRChat 目录。")
        except Exception as e:
            messagebox.showerror("注入失败", str(e))

    def _install_reshade_files(self, target_dir):
        """将 dxgi.dll 和 reshade-shaders 复制到目标目录"""
        for item in RESHADE_INSTALL_ITEMS:
            src = os.path.join(APP_DIR, item)
            dst = os.path.join(target_dir, item)
            if not os.path.exists(src):
                raise FileNotFoundError(f"ReShade 资源未找到: {src}\n请将 {item} 放置在本程序同目录下。")
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    def _on_uninstall_reshade(self):
        """卸载 ReShade — 删除 VRChat 目录中的相关文件"""
        path = self.install_path.get()
        if not path or not os.path.isdir(path):
            messagebox.showwarning("未设置路径", "请先设置 VRChat 安装路径。")
            return

        ok = messagebox.askyesno(
            "确认卸载 ReShade",
            f"将删除 VRChat 目录下的 ReShade 相关文件：\n\n"
            + "\n".join(f"  • {item}" for item in RESHADE_REMOVE_ITEMS)
            + f"\n\n目标目录:\n{path}"
        )
        if not ok:
            return

        removed = []
        failed = []
        for item in RESHADE_REMOVE_ITEMS:
            target = os.path.join(path, item)
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target)
                elif os.path.isfile(target):
                    os.remove(target)
                else:
                    continue
                removed.append(item)
            except Exception as e:
                failed.append(f"{item}: {e}")

        msg = f"已删除: {', '.join(removed)}" if removed else "未找到可删除的文件。"
        if failed:
            msg += f"\n\n删除失败:\n" + "\n".join(failed)
        messagebox.showinfo("卸载完成", msg)

    def _do_launch(self, extra_args, mode_name, target_exe=None):
        """通用启动逻辑"""
        path = self.install_path.get()
        exe = target_exe if target_exe else TARGET_EXE
        target = os.path.join(path, exe)

        if not os.path.isfile(target):
            messagebox.showerror(
                "启动失败",
                f"目标文件不存在:\n{target}\n\n请确认 VRChat 安装路径是否正确。"
            )
            self._check_target_exe()
            return

        # 拼接 affinity 参数
        args = extra_args
        if self.affinity_enabled.get():
            args = f"{extra_args} --affinity=FF" if extra_args else "--affinity=FF"

        try:
            pid = Win32ParentLaunch.launch(target, args=args)
            if self.auto_exit_enabled.get():
                self.root.destroy()
                sys.exit(0)
        except Exception as e:
            fallback = messagebox.askyesno(
                "高级启动失败",
                f"以 explorer.exe 为父进程启动失败:\n\n{str(e)[:300]}\n\n"
                "是否改用普通方式启动？\n"
                "（父进程将是本程序，而非 explorer.exe）"
            )
            if fallback:
                self._fallback_launch(target, args)
                if self.auto_exit_enabled.get():
                    self.root.destroy()
                    sys.exit(0)

    def _fallback_launch(self, target, launch_args=None):
        """备用方案：普通方式启动"""
        try:
            working_dir = os.path.dirname(target)
            cmd = [target]
            if launch_args:
                cmd.extend(launch_args.split())
            subprocess.Popen(
                cmd,
                cwd=working_dir,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception as e:
            messagebox.showerror("启动失败", f"备用方案也失败:\n{e}")

    def _on_change_path(self):
        """更改 VRChat 安装路径"""
        current = self.install_path.get()
        folder = filedialog.askdirectory(
            title="请选择 VRChat 安装目录，如果不知道在哪，可从Steam库中右键VRChat -> 管理 -> 浏览本地文件",
            initialdir=current if current and os.path.isdir(current) else None,
        )
        if not folder:
            return

        folder = os.path.abspath(folder)

        # 检查目标程序
        target = os.path.join(folder, TARGET_EXE)
        if not os.path.isfile(target):
            ok = messagebox.askyesno(
                "未找到目标程序",
                f"在所选目录中未找到 {TARGET_EXE}:\n\n{folder}\n\n"
                "是否仍然保存此路径？"
            )
            if not ok:
                return

        self.install_path.set(folder)
        ConfigManager.save(folder, self.affinity_enabled.get(), self.auto_exit_enabled.get())
        self._check_target_exe()
        messagebox.showinfo("已保存", f"VRChat 安装路径已更新为:\n{folder}")

    def _center_window(self):
        """将窗口置于屏幕中央"""
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def run(self):
        """启动主循环"""
        self.root.mainloop()


# ============================================================
# 入口
# ============================================================
def main():
    ctk.set_appearance_mode("Dark")     # 夜间模式
    ctk.set_default_color_theme("blue") # blue / dark-blue / green
    ctk.set_widget_scaling(1.0)
    ctk.set_window_scaling(1.0)
    app = VRChatHelperApp()
    app.run()


if __name__ == "__main__":
    main()
