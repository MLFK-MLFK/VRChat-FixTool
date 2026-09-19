#!/usr/bin/env python3
"""
VRChat 便捷工具助手
以 explorer.exe 为父进程启动 start_protected_game.exe
"""

import os
import sys
import json
import shutil
import webbrowser
import configparser
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from customtkinter.windows.widgets.core_rendering.draw_engine import DrawEngine
import ctypes
from ctypes import wintypes, Structure, sizeof, byref
import subprocess
import threading
import time
import queue
from pythonosc import udp_client, dispatcher, osc_server


# ============================================================
# 全局字体：统一使用微软雅黑
# ============================================================
# CustomTkinter 主题默认字体为 Roboto，而 Roboto 在 Windows 上通常未安装，
# 会被 Tk 替换成未知回退字体（中英文风格不一致）。
# 这里改写主题默认值，使所有未显式指定字体的控件统一为微软雅黑。
# 注意：系统字体名为 "Microsoft YaHei UI"，"Microsoft YaHei" 在 Tk 中查不到。
UI_FONT_FAMILY = "Microsoft YaHei UI"


def apply_global_font():
    """把主题默认字体改为微软雅黑。

    必须在 set_default_color_theme() 之后调用：
    该函数会重新加载主题文件，把 CTkFont.family 重置回 Roboto。
    """
    ctk.ThemeManager.theme["CTkFont"]["family"] = UI_FONT_FAMILY


# ============================================================
# 科技感深色配色（参考 ImGui Dark 面板风格）
# ============================================================
# 设计取向：低饱和深灰底 + 单一蓝色强调 + 1px 细描边 + 小圆角。
# 只覆盖颜色 / 圆角 / 描边三类主题键，不涉及控件结构、文字与业务逻辑。
C_BG_ROOT      = "#0B0E12"   # 窗口底色
C_BG_PANEL     = "#141920"   # 分区卡片
C_BG_PANEL_2   = "#1A212A"   # 次级面板 / 悬浮窗口
C_BG_INPUT     = "#0D1116"   # 输入框 / 滚动区
C_BTN          = "#1E2734"   # 普通按钮底
C_BTN_HOVER    = "#2A3646"
C_BG_HOVER     = "#212A35"   # 透明按钮悬停底
C_BORDER       = "#28313D"   # 常规描边
C_BORDER_ACC   = "#1F4E8C"   # 强调描边 / 分隔线
C_ACCENT       = "#3D8BFD"   # 主强调色（ImGui 蓝 0.26/0.59/0.98）
C_ACCENT_HOVER = "#5EA0FF"
C_TEXT         = "#CED6E0"   # 正文
C_TEXT_DIM     = "#7C8794"   # 次要说明
C_TEXT_DIS     = "#4A535E"   # 禁用态
C_SWITCH_OFF   = "#333C48"   # 开关滑道 / 滚动条
C_GREEN        = "#2E9E63"   # VR 模式
C_GREEN_HOVER  = "#23804F"
C_OLIVE        = "#8A7233"   # 本地测试模式
C_OLIVE_HOVER  = "#6A5726"
C_TEAL         = "#2E6E84"   # 自定义启动
C_TEAL_HOVER   = "#245767"
C_RED          = "#B2453F"   # 卸载 / 危险操作
C_RED_HOVER    = "#8C332E"

# ------------------------------------------------------------
# 圆角渲染方式（只影响观感与缩放流畅度，不影响任何功能）
# ------------------------------------------------------------
# CustomTkinter 画圆角有三种画法，可切换：
#   "font_shapes"    圆角最平滑（有抗锯齿）。代价：每个圆角都是一个「字形图元」，
#                    本程序主窗口就有 282 个，窗口每次缩放都要把它们重设一遍。
#   "polygon_shapes" 实测最快（主窗口缩放约 -25%），canvas 图元从 282 降到 0，
#                    但圆角是硬边、没有抗锯齿，凑近看会有锯齿。
#   "circle_shapes"  介于两者之间。
# 保持 "font_shapes" 即维持当前外观；嫌拖窗口卡就改成 "polygon_shapes" 试试，
# 不喜欢随时改回来。
DRAWING_METHOD = "font_shapes"


def _c(color):
    """把单色展开成 [浅色模式, 深色模式]。

    本程序固定使用 Dark 模式，两套给同一值即可，
    避免切到 Light 模式时露出不协调的内置配色。
    """
    return [color, color]


def apply_tech_theme():
    """套用科技感深色主题。

    必须在 set_default_color_theme() 之后调用：
    该函数会重新加载主题 json，把 ThemeManager.theme 整体重置回内置配色。
    这里只覆写配色 / 圆角 / 描边三类键，控件在实例化时读取，
    因此对已经显式指定颜色的控件不产生任何影响。
    """
    t = ctk.ThemeManager.theme

    # 渲染方式必须在任何控件创建之前设好：控件实例化时会读这个类属性
    DrawEngine.preferred_drawing_method = DRAWING_METHOD

    t["CTk"]["fg_color"] = _c(C_BG_ROOT)
    t["CTkToplevel"]["fg_color"] = _c(C_BG_ROOT)

    # 默认圆角为 0：所有没显式传 corner_radius 的 CTkFrame 都是纯布局容器
    # （fg_color="transparent"，画了圆角也看不见），在 font_shapes 渲染方式下
    # 却会照样生成字体圆角图元，窗口每次缩放都要重设一遍。
    # 可见的卡片 / 底栏 / 侧栏 / 滚动区都显式传了自己的 corner_radius，不受影响。
    t["CTkFrame"].update({
        "corner_radius": 0,
        "border_width": 0,
        "fg_color": _c(C_BG_PANEL),
        "top_fg_color": _c(C_BG_PANEL_2),
        "border_color": _c(C_BORDER),
    })

    # 普通按钮走中性底 + 细描边，强调色留给各自主操作按钮单独指定
    t["CTkButton"].update({
        "corner_radius": 4,
        "border_width": 1,
        "fg_color": _c(C_BTN),
        "hover_color": _c(C_BTN_HOVER),
        "border_color": _c(C_BORDER),
        "text_color": _c(C_TEXT),
        "text_color_disabled": _c(C_TEXT_DIS),
    })

    t["CTkLabel"].update({
        "text_color": _c(C_TEXT),
    })

    t["CTkEntry"].update({
        "corner_radius": 4,
        "border_width": 1,
        "fg_color": _c(C_BG_INPUT),
        "border_color": _c(C_BORDER),
        "text_color": _c(C_TEXT),
        "placeholder_text_color": _c(C_TEXT_DIM),
    })

    t["CTkSwitch"].update({
        "fg_color": _c(C_SWITCH_OFF),
        "progress_color": _c(C_ACCENT),
        "button_color": _c("#D5DCE4"),
        "button_hover_color": _c("#FFFFFF"),
        "text_color": _c(C_TEXT),
        "text_color_disabled": _c(C_TEXT_DIS),
    })

    t["CTkTextbox"].update({
        "corner_radius": 4,
        "border_width": 1,
        "fg_color": _c(C_BG_INPUT),
        "border_color": _c(C_BORDER),
        "text_color": _c(C_TEXT),
        "scrollbar_button_color": _c(C_SWITCH_OFF),
        "scrollbar_button_hover_color": _c(C_ACCENT),
    })

    t["CTkScrollbar"].update({
        "button_color": _c(C_SWITCH_OFF),
        "button_hover_color": _c(C_ACCENT),
    })

    t["CTkScrollableFrame"].update({
        "label_fg_color": _c(C_BG_PANEL_2),
    })


# ============================================================
# 常量
# ============================================================
APP_NAME = "VRC-Tool"
VERSION = "1.4"
CFG_FILE = "cfg.ini"
TARGET_EXE = "start_protected_game.exe"
TARGET_EXE_LOCAL = "VRChat.exe"

# 主窗口尺寸（原 1050x700，去掉右侧栏后宽度收窄一半）
# 高度取 760：收窄后内容需要约 715px，700 会把最底下的自动退出开关和「关于」按钮压没
WIN_WIDTH = 525
WIN_HEIGHT = 800

# 底部扩展菜单 / 右侧子菜单面板
EXT_PANEL_TITLE = " 扩展菜单  (进阶操作)"
EXT_PANEL_COLLAPSED_TEXT = f"{EXT_PANEL_TITLE}　（点击展开）---------->"
EXT_PANEL_EXPANDED_TEXT = f"{EXT_PANEL_TITLE}　（点击收起）----------<"
EXT_PANEL_WIDTH = 190   # 右侧子菜单面板宽度
EXT_PANEL_PAD = 12      # 面板左右外边距合计（与下面 pack 的 padx=(4, 8) 对应）

# ReShade 相关文件/文件夹
RESHADE_INSTALL_ITEMS = ["dxgi.dll", "reshade-shaders"]
RESHADE_REMOVE_ITEMS = [
    "dxgi.dll", "reshade-shaders", "ReShade.ini", "ReShade.log",
    "ShaderCache", "ShaderFixes", "Presets","ReShadePreset.ini","ReShadeVR.ini",
]

# VRChat OSC 调试（自 OSC-Debug.py 移植，逻辑保持原样）
OSC_DEFAULT_IP = "127.0.0.1"        # VRChat 默认在本机
OSC_SEND_PORT_DEFAULT = "9000"      # VRChat 接收 OSC 的默认端口
OSC_RECV_PORT = 9001                # 本工具监听 VRChat 回传 OSC 的端口
OSC_LOOP_INTERVAL_MS = 100          # 循环发送默认间隔（毫秒）
OSC_MAX_RECV_LINES = 1000           # 接收窗口最多保留的行数
OSC_RECV_QUEUE_MAX = 5000           # 接收缓冲队列上限
OSC_RECV_FLUSH_MS = 50              # 接收队列刷到界面的间隔
OSC_RECV_BATCH = 200                # 单次最多从队列取多少条
OSC_WIN_W, OSC_WIN_H = 1000, 600    # OSC 调试窗口尺寸
OSC_DOC_W = 400                     # 文档窗口宽度
OSC_MACRO_TIME = "time"             # 宏指令：time X —— 等待 X 毫秒后继续
OSC_SEND_BTN_TEXT = "发送 OSC"      # 空闲态按钮文字
OSC_STOP_BTN_TEXT = "停止发送"      # 执行中按钮文字
OSC_RECV_START_TEXT = f"开始接收 {OSC_RECV_PORT}"   # 接收按钮：未监听
OSC_RECV_STOP_TEXT = f"停止接收 {OSC_RECV_PORT}"    # 接收按钮：监听中（红色）

# 文档窗口的默认内容放在同目录的 osc_doc.txt 里（记事本直接改即可，不用动代码）。
# 加载代码在下面 APP_DIR 之后的 _load_osc_doc_content()。

# 获取程序所在目录（兼容 PyInstaller 打包）
def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

APP_DIR = get_app_dir()
CFG_PATH = os.path.join(APP_DIR, CFG_FILE)

# VRChat 游戏配置 JSON 路径（通用路径，不依赖用户名）
_VRC_CONFIG_DIR = os.path.join(os.environ.get("USERPROFILE", ""),
                                "AppData", "LocalLow", "VRChat", "VRChat")
VRC_CONFIG_PATH = os.path.join(_VRC_CONFIG_DIR, "config.json")

# 游戏参数汉化对照表
CONFIG_TRANSLATIONS = {
    # —— 原有条目（原样保留）——
    "fpv_steadycam_fov": "FPV无人机的FOV视野大小",
    "cache_directory": "缓存文件夹位置[确保有30GB以上的空间]",
    "camera_spout_res_height": "直播相机分辨率-高",
    "camera_spout_res_width": "直播相机分辨率-宽",
    "camera_res_height": "相机分辨率-高",
    "camera_res_width": "相机分辨率-宽",
    "screenshot_res_height": "截图分辨率-高",
    "screenshot_res_width": "截图分辨率-宽",
    "cache_size": "游戏缓存大小[GB]-最低30G",
    "cache_expiry_delay": "缓存保存时间[天]-最低30天",
    # —— 依据官方文档补充的条目 ——
    "disableRichPresence": "关闭 Steam / Discord 状态同步（Rich Presence）",
    "picture_output_folder": "VR 相机拍的照片保存到哪个文件夹",
    "picture_output_split_by_date": "false 时照片不按 YYYY-MM 分子文件夹（默认 true）",
    "betas": 'Beta 功能开关（数组；含 "particle_system_limiter" 才启用粒子限制系统）',
    "ps_max_particles": "单个粒子系统最多能生成多少粒子",
    "ps_max_systems": "粒子系统数量上限（官方默认配置里有，文档表格未列出说明）",
    "ps_max_emission": "单个粒子系统允许的最大发射率",
    "ps_max_total_emission": "整个头像所有粒子系统合计的最大发射率",
    "ps_mesh_particle_divider": "Mesh 粒子惩罚除数（取最高多边形数 ÷ 此值）",
    "ps_mesh_particle_poly_limit": "粒子系统上单个 Mesh 的最大多边形数",
    "ps_collision_penalty_high": "高质量碰撞的惩罚除数",
    "ps_collision_penalty_med": "中等质量碰撞的惩罚除数",
    "ps_collision_penalty_low": "低质量碰撞的惩罚除数",
    "ps_trails_penalty": "开启拖尾（Trails）的惩罚除数",
    "dynamic_bone_max_affected_transform_count":
        "Dynamic Bone 最大影响变换数（PhysBones 已取代它，基本过时）",
    "dynamic_bone_max_collider_check_count":
        "Dynamic Bone 最大碰撞体检查数（PhysBones 已取代它，基本过时）",
}

# ============================================================
# VRChat config.json 官方词条目录
# ============================================================
# 依据官方文档整理：
#   https://docs.vrchat.com/docs/configuration-file
#   https://docs.vrchat.com/docs/avatar-particle-system-limits
#
# 结构：分组(group) -> 可选子分组(sub) -> 词条(item)
# 子分组体现的是文档里的父子关系，例如「VR 相机照片分辨率」下的宽/高是一对；
# 「头像粒子系统限制」下的 ps_* 都依附于 betas 里是否有 particle_system_limiter。
#
# item 字段：
#   key      词条名
#   desc     中文说明（干什么用的）
#   kind     int / bool / path / array —— 决定用什么控件编辑
#   default  装配时写入的初值
#   hint     范围或备注，显示在输入框下方
#   legacy   True 表示官方已不推荐（Dynamic Bone）
CONFIG_CATALOG = [
    {
        "group": "状态同步（Rich Presence）",
        "items": [
            {"key": "disableRichPresence", "kind": "bool", "default": False,
             "desc": "关闭 Steam / Discord 状态同步",
             "hint": "开着会让好友看到你在 VRChat 里做什么；想隐藏就设为 true"},
        ],
    },
    {
        "group": "缓存设置",
        "items": [
            {"key": "cache_directory", "kind": "path",
             "default": os.path.join(os.path.expanduser("~"), "VRCCache"),
             "desc": "缓存文件夹位置",
             "hint": "建议放在有 30GB 以上空间的磁盘；路径里的 \\ 会自动转义"},
            {"key": "cache_size", "kind": "int", "default": 30,
             "desc": "游戏缓存大小（GB）",
             "hint": "官方下限 30，不能低于默认值"},
            {"key": "cache_expiry_delay", "kind": "int", "default": 30,
             "desc": "缓存保存时间（天）",
             "hint": "官方下限 30，文件超过这个天数没被访问就会被清掉"},
        ],
    },
    {
        "group": "相机与截图",
        "items": [
            {"key": "camera_res_width", "kind": "int", "default": 1920,
             "sub": "VR 相机照片分辨率",
             "desc": "VR 相机拍照宽度",
             "hint": "1280 ~ 7680（成对设置）；只有相机分辨率选「Config File」时才生效"},
            {"key": "camera_res_height", "kind": "int", "default": 1080,
             "sub": "VR 相机照片分辨率",
             "desc": "VR 相机拍照高度",
             "hint": "720 ~ 4320（成对设置）"},
            {"key": "screenshot_res_width", "kind": "int", "default": 1920,
             "sub": "F12 截图分辨率",
             "desc": "F12 截图宽度",
             "hint": "1280 ~ 3840（成对设置）"},
            {"key": "screenshot_res_height", "kind": "int", "default": 1080,
             "sub": "F12 截图分辨率",
             "desc": "F12 截图高度",
             "hint": "720 ~ 2160（成对设置）"},
            {"key": "camera_spout_res_width", "kind": "int", "default": 1920,
             "sub": "直播相机 Spout2 输出",
             "desc": "直播相机 Spout2 输出宽度",
             "hint": "720p ~ 4K 之间任意像素值（成对设置）"},
            {"key": "camera_spout_res_height", "kind": "int", "default": 1080,
             "sub": "直播相机 Spout2 输出",
             "desc": "直播相机 Spout2 输出高度",
             "hint": "720p ~ 4K 之间任意像素值（成对设置）"},
            {"key": "picture_output_folder", "kind": "path",
             "default": os.path.join(os.path.expanduser("~"), "Pictures", "VRChat"),
             "sub": "照片输出",
             "desc": "VR 相机照片保存目录",
             "hint": "留空则用游戏默认位置"},
            {"key": "picture_output_split_by_date", "kind": "bool", "default": True,
             "sub": "照片输出",
             "desc": "照片是否按年月分文件夹",
             "hint": "false = 全部直接丢进输出目录，不再建 YYYY-MM 子文件夹"},
            {"key": "fpv_steadycam_fov", "kind": "int", "default": 60,
             "sub": "第一人称稳定器",
             "desc": "FPV 稳定器的垂直视野（FOV）",
             "hint": "30 ~ 110；多数头显默认 50~55，想给观众更大视野可试 65~70"},
        ],
    },
    {
        "group": "头像粒子系统限制",
        "items": [
            {"key": "betas", "kind": "array", "default": ["particle_system_limiter"],
             "desc": "Beta 功能开关（整个粒子限制的总开关）",
             "hint": '数组。含 "particle_system_limiter" 才会启用下面的 ps_* 限制；'
                     '去掉它就等于关掉这个系统。多个值用英文逗号分隔'},
            {"key": "ps_max_particles", "kind": "int", "default": 50000,
             "sub": "数量上限",
             "desc": "单个粒子系统最多生成的粒子数", "hint": "官方默认 50000"},
            {"key": "ps_max_systems", "kind": "int", "default": 200,
             "sub": "数量上限",
             "desc": "粒子系统数量上限",
             "hint": "官方默认配置里有（200），但文档表格未给出说明"},
            {"key": "ps_max_emission", "kind": "int", "default": 5000,
             "sub": "数量上限",
             "desc": "单个粒子系统允许的最大发射率", "hint": "官方默认 5000"},
            {"key": "ps_max_total_emission", "kind": "int", "default": 40000,
             "sub": "数量上限",
             "desc": "整个头像所有粒子系统合计的最大发射率", "hint": "官方默认 40000"},
            {"key": "ps_mesh_particle_divider", "kind": "int", "default": 60,
             "sub": "Mesh 粒子惩罚",
             "desc": "Mesh 粒子惩罚除数",
             "hint": "用最高多边形数 ÷ 此值，结果再去除该系统的粒子配额。默认 60"},
            {"key": "ps_mesh_particle_poly_limit", "kind": "int", "default": 50000,
             "sub": "Mesh 粒子惩罚",
             "desc": "Mesh 最大多边形数", "hint": "官方默认 50000"},
            {"key": "ps_collision_penalty_high", "kind": "int", "default": 50,
             "sub": "碰撞惩罚",
             "desc": "高质量碰撞的惩罚除数", "hint": "官方默认 50"},
            {"key": "ps_collision_penalty_med", "kind": "int", "default": 30,
             "sub": "碰撞惩罚",
             "desc": "中等质量碰撞的惩罚除数", "hint": "官方默认 30"},
            {"key": "ps_collision_penalty_low", "kind": "int", "default": 10,
             "sub": "碰撞惩罚",
             "desc": "低质量碰撞的惩罚除数", "hint": "官方默认 10"},
            {"key": "ps_trails_penalty", "kind": "int", "default": 10,
             "sub": "拖尾惩罚",
             "desc": "开启拖尾（Trails）的惩罚除数", "hint": "官方默认 10"},
        ],
    },
    {
        "group": "Dynamic Bone（官方已不推荐）",
        "items": [
            {"key": "dynamic_bone_max_affected_transform_count", "kind": "int",
             "default": 32, "legacy": True,
             "desc": "Dynamic Bone 最大影响变换数",
             "hint": "Dynamic Bones 已被 PhysBones 取代，官方说明「这个设置已经不太相关了」"},
            {"key": "dynamic_bone_max_collider_check_count", "kind": "int",
             "default": 8, "legacy": True,
             "desc": "Dynamic Bone 最大碰撞体检查数",
             "hint": "同上，属于过时设置"},
        ],
    },
]

CONFIG_EXTRA_BTN_SHOW = "添加额外限制"
CONFIG_EXTRA_BTN_HIDE = "收起额外限制"
CONFIG_EXTRA_HEIGHT = 300          # 额外限制区展开后的高度
CONFIG_UNINSTALL_WARN = (
    "确定吗？删除词条不等于禁用，而是恢复到VRChat默认设置，"
    "如果你不知道这个是干什么的，那么默认就是最好的选择"
)

# ℹ 信息窗口内容（从 info.txt 加载）
def _load_info_content():
    path = os.path.join(APP_DIR, "info.txt")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "info.txt 未找到"

INFO_CONTENT = _load_info_content()


# OSC 文档窗口内容（从 osc_doc.txt 加载，方便直接改文件而不动代码）
def _load_osc_doc_content():
    path = os.path.join(APP_DIR, "osc_doc.txt")
    if os.path.isfile(path):
        # utf-8-sig：带不带 BOM 都能读，记事本另存也不会出问题
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()
    return "osc_doc.txt 未找到"

OSC_DOC_TEXT = _load_osc_doc_content()


# ============================================================
# config.json 宽容读取
# ============================================================
# VRChat 偶尔会写出「最后一个键后面还多一个逗号」的 config.json，
# 例如：
#     { "cache_size": 50, }
# 这是非法 JSON，严格解析器会直接抛
#     Expecting property name enclosed in double quotes
# 结果整个配置面板只剩一行报错。
# 下面这套读取流程先按标准解析，失败再宽容化重试，尽量把能读的都读出来。

def _strip_dangling_commas(text):
    """去掉对象 / 数组最后一项后面多余的逗号。

    只在字符串字面量之外动手，因此不会误伤值里自带的逗号
    （例如 "I:\\\\VRC_Teams" 或 "a,b" 这类内容）。
    """
    out = []
    in_str = False
    escaped = False
    for i, ch in enumerate(text):
        if in_str:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            out.append(ch)
            continue

        if ch == ",":
            # 向后跳过空白，紧跟 } 或 ] 说明这个逗号是多余的
            j = i + 1
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j < len(text) and text[j] in "}]":
                continue
        out.append(ch)
    return "".join(out)


def load_json_lenient(path):
    """尽量宽容地读取 JSON 文件，返回 (数据, 错误)。

    宽容点：
    - 自动忽略 UTF-8 BOM（用 utf-8-sig 解码）；
    - 空文件直接给出明确原因，而不是甩一个 JSON 异常；
    - 严格解析失败时，先去掉对象 / 数组末尾多余的逗号再试一次。

    成功返回 (data, None)；彻底失败返回 (None, 异常对象)。
    不修改传入的文件，只读。
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = f.read()
    except Exception as e:
        return None, e

    if not raw.strip():
        return None, ValueError("文件内容为空")

    try:
        return json.loads(raw), None
    except Exception as strict_err:
        cleaned = _strip_dangling_commas(raw)
        if cleaned != raw:
            try:
                return json.loads(cleaned), None
            except Exception as lenient_err:
                strict_err = lenient_err
        return None, strict_err


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
        self.root.geometry(f"{WIN_WIDTH}x{WIN_HEIGHT}")
        self.root.resizable(True, True)
        self.root.minsize(480, 500)

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

        # OSC 调试模块状态：窗口没打开时也必须存在，供主窗口关闭流程调用
        self.osc_win = None
        self.osc_doc_win = None
        self.osc_doc_text = None
        self.osc_status_var = None
        self._osc_loop_after_id = None
        self._osc_recv_after_id = None
        self._osc_server = None
        self._osc_server_thread = None
        self._osc_server_running = False
        self._osc_queue = queue.Queue(maxsize=OSC_RECV_QUEUE_MAX)

        # OSC 发送序列（宏）执行状态
        self._osc_active = False        # 是否有序列 / 循环正在跑
        self._osc_run_after_id = None   # 宏 time 延时的定时任务
        self._osc_run_steps = []        # 本轮步骤表
        self._osc_run_index = 0
        self._osc_run_client = None
        self._osc_run_sent = 0
        self._osc_run_errors = []
        self._osc_run_ip = ""
        self._osc_run_port = 0
        self._osc_error_dialog_open = False   # 防循环模式下错误框叠罗汉

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
        """构建界面组件 — 底部扩展菜单按钮 + 右侧子菜单面板 + 主控件区"""

        # ========== 底部大按钮 + 右侧子菜单面板 ==========
        # 底部按钮先 pack（占用固定高度）；右侧面板默认不 pack，
        # 展开时用 pack(before=top_frame) 插队，详见 _build_ext_side_panel。
        self._build_ext_bar()
        self._build_ext_side_panel()

        # 顶层容器：单列布局
        self.top_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.top_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(6, 4))
        self.top_frame.columnconfigure(0, weight=1)
        self.top_frame.rowconfigure(0, weight=1)

        # ========== 主区域 ==========
        main_frame = ctk.CTkFrame(self.top_frame, corner_radius=0, fg_color="transparent")
        main_frame.grid(row=0, column=0, sticky="nsew")

        # --- 标题行 ---
        title_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        title_frame.pack(fill=tk.X, pady=(4, 12))

        ctk.CTkLabel(
            title_frame,
            text=f"{APP_NAME}",
            font=ctk.CTkFont(family=UI_FONT_FAMILY, size=18, weight="bold"),
        ).pack(side=tk.LEFT)

        ctk.CTkLabel(
            title_frame,
            text=f"v{VERSION}",
            font=ctk.CTkFont(size=11),
            text_color=C_TEXT_DIM,
        ).pack(side=tk.LEFT, padx=(8, 0), pady=(5, 0))

        # --- 分隔线（深蓝细线，取代原来的灰线）---
        sep = ctk.CTkFrame(main_frame, height=2, corner_radius=1, fg_color=C_BORDER_ACC)
        sep.pack(fill=tk.X, pady=(0, 14))

        # --- 路径显示区 ---
        path_section = ctk.CTkFrame(main_frame, corner_radius=8,
                                    border_width=1, border_color=C_BORDER)
        path_section.pack(fill=tk.X, pady=(0, 12))

        ctk.CTkLabel(
            path_section,
            text="VRChat 安装路径",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(10, 6))

        path_row = ctk.CTkFrame(path_section, fg_color="transparent")
        path_row.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.path_entry = ctk.CTkEntry(
            path_row,
            textvariable=self.install_path,
            state="disabled",
            font=ctk.CTkFont(family=UI_FONT_FAMILY, size=11),
            corner_radius=4,
            text_color=C_TEXT_DIM,          # 禁用态用暗色，避免和可编辑框混淆
            border_color=C_BORDER,
        )
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        ctk.CTkButton(
            path_row,
            text="更改...",
            command=self._on_change_path,
            width=70,
            height=32,
            corner_radius=4,
            font=ctk.CTkFont(size=12),
        ).pack(side=tk.LEFT, padx=(8, 0))

        # --- 目标文件状态 ---
        status_section = ctk.CTkFrame(main_frame, corner_radius=8,
                                      border_width=1, border_color=C_BORDER)
        status_section.pack(fill=tk.X, pady=(0, 14))

        ctk.CTkLabel(
            status_section,
            text="目标程序状态",
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
            text="刷新",
            command=self._check_target_exe,
            width=70,
            height=32,
            corner_radius=4,
            font=ctk.CTkFont(size=12),
        ).pack(side=tk.RIGHT)

        # --- 操作按钮区 ---
        button_section = ctk.CTkFrame(main_frame, corner_radius=8,
                                      border_width=1, border_color=C_BORDER)
        button_section.pack(fill=tk.X, pady=(0, 8))

        ctk.CTkLabel(
            button_section,
            text="启动模式",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=14, pady=(10, 6))

        btn_inner = ctk.CTkFrame(button_section, fg_color="transparent")
        btn_inner.pack(fill=tk.X, padx=10, pady=(0, 6))

        self.launch_pc_btn = ctk.CTkButton(
            btn_inner,
            text="PC模式启动（帧率优化）/ 支持一键多开",
            command=self._on_launch_pc,
            height=42,
            corner_radius=6,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            border_width=0,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.launch_pc_btn.pack(fill=tk.X, pady=(0, 6))

        self.launch_vr_btn = ctk.CTkButton(
            btn_inner,
            text="VR模式启动（帧率优化）",
            command=self._on_launch_vr_highfps,
            height=42,
            corner_radius=6,
            fg_color=C_GREEN,
            hover_color=C_GREEN_HOVER,
            border_width=0,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.launch_vr_btn.pack(fill=tk.X)

        self.launch_local_btn = ctk.CTkButton(
            btn_inner,
            text="本地测试模式启动 / NoEAC",
            command=self._on_launch_local,
            height=42,
            corner_radius=6,
            fg_color=C_OLIVE,
            hover_color=C_OLIVE_HOVER,
            border_width=0,
            text_color="#FFFFFF",
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
            corner_radius=4,
            font=ctk.CTkFont(size=11),
        )
        self.custom_args_entry.pack(fill=tk.X, pady=(0, 4))

        # 自定义按钮 + 信息小按钮 同行
        custom_btn_row = ctk.CTkFrame(custom_frame, fg_color="transparent")
        custom_btn_row.pack(fill=tk.X)

        self.launch_custom_btn = ctk.CTkButton(
            custom_btn_row,
            text="自定义高级启动模式",
            command=self._on_launch_custom,
            height=32,
            corner_radius=4,
            fg_color=C_TEAL,
            hover_color=C_TEAL_HOVER,
            border_width=0,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.launch_custom_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.info_btn = ctk.CTkButton(
            custom_btn_row,
            text="ℹ",
            command=self._on_show_info,
            width=32,
            height=32,
            corner_radius=4,
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

        # ReShade 注入 + 卸载（分两行：窗口收窄后三个控件并排放不下）
        reshade_frame = ctk.CTkFrame(button_section, fg_color="transparent")
        reshade_frame.pack(fill=tk.X, padx=10, pady=(2, 10))

        self.install_reshade_btn = ctk.CTkButton(
            reshade_frame,
            text="注入 ReShade/PC拍照滤镜，VR模式有帧率损耗请禁用",
            command=self._on_install_reshade,
            height=30,
            corner_radius=4,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            border_width=0,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11),
        )
        self.install_reshade_btn.pack(fill=tk.X)

        reshade_row2 = ctk.CTkFrame(reshade_frame, fg_color="transparent")
        reshade_row2.pack(fill=tk.X, pady=(6, 0))

        self.reshade_disable_switch = ctk.CTkSwitch(
            reshade_row2,
            text="禁用 Reshade",
            variable=self.reshade_disable,
            onvalue=True,
            offvalue=False,
            command=self._on_reshade_disable_toggle,
            font=ctk.CTkFont(size=11),
            switch_width=36,
            switch_height=18,
        )
        self.reshade_disable_switch.pack(side=tk.LEFT)

        self.uninstall_reshade_btn = ctk.CTkButton(
            reshade_row2,
            text="彻底卸载 ReShade",
            command=self._on_uninstall_reshade,
            height=30,  # 不写死宽度：固定 110 会让文字被截断，实际需要 140
            corner_radius=4,
            fg_color=C_RED,
            hover_color=C_RED_HOVER,
            border_width=0,
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
            text_color=C_TEXT_DIM,
        ).pack(side=tk.LEFT)

        self.about_btn = ctk.CTkButton(
            bottom_frame,
            text="关于",
            command=self._on_about,
            width=50,
            height=24,
            corner_radius=4,
            fg_color="transparent",
            hover_color=C_BG_HOVER,
            border_width=0,                 # 透明底按钮不画描边
            text_color=C_TEXT_DIM,
            font=ctk.CTkFont(size=10),
        )
        self.about_btn.pack(side=tk.RIGHT)

        # 配置面板的状态容器：面板本身在悬浮窗口里，打开时才创建，这里只备好状态
        self._config_entries = {}      # key -> StringVar
        self._config_readonly = set()  # 只读键（对象 / 数组）
        self._config_data = {}
        self._root_is_dict = True      # config.json 顶层是否为键值对象
        self.config_win = None         # 悬浮的「VRChat配置文件修改」窗口

    # ---- 底部扩展菜单 ----

    def _build_ext_bar(self):
        """窗口最底部的大按钮，点击展开 / 收起右侧的子菜单面板。"""
        self.ext_bar = ctk.CTkFrame(self.root, corner_radius=8,
                                    border_width=1, border_color=C_BORDER)
        self.ext_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 6))

        self.ext_toggle_btn = ctk.CTkButton(
            self.ext_bar,
            text=EXT_PANEL_COLLAPSED_TEXT,
            command=self._on_toggle_ext_menu,
            height=38,
            corner_radius=4,
            anchor="w",
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            border_width=0,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.ext_toggle_btn.pack(fill=tk.X, padx=6, pady=6)

    def _build_ext_side_panel(self):
        """右侧子菜单面板。

        默认不 pack（即隐藏）。展开时用 pack(before=self.top_frame) 插到主区域
        前面 —— Tk 的 packer 按打包顺序分配空间，不这样做面板会被主区域挤扁。
        """
        self.ext_side_panel = ctk.CTkFrame(
            self.root,
            corner_radius=8,
            width=EXT_PANEL_WIDTH,
            fg_color=C_BG_PANEL_2,          # 面板比主区域亮一档，形成层次
            border_width=1,
            border_color=C_BORDER,
        )
        self.ext_side_panel.pack_propagate(False)  # 保持固定宽度

        ctk.CTkLabel(
            self.ext_side_panel,
            text="子菜单",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(fill=tk.X, padx=12, pady=(10, 6))

        # ---- 子菜单按钮清单 ----
        # 以后新增功能，往这个列表里加一条 (按钮文字, 点击回调) 即可，
        # 面板会自动多出一个按钮。
        sub_menus = [
            ("VRChat配置文件修改", self._open_config_window),
            ("VRChat OSC 调试", self._open_osc_window),
        ]
        for text, command in sub_menus:
            ctk.CTkButton(
                self.ext_side_panel,
                text=text,
                command=command,
                height=32,
                corner_radius=4,
                anchor="w",
                font=ctk.CTkFont(size=11),
            ).pack(fill=tk.X, padx=8, pady=3)

        self.ext_expanded = False
        self._pre_expand_width = None

    def _build_config_panel(self, parent):
        """VRChat config.json 编辑面板（放在独立的悬浮窗口里）"""
        # 顶栏：左边是 config.json 完整路径，右边是「打开文件位置」按钮
        path_row = ctk.CTkFrame(parent, fg_color="transparent")
        path_row.pack(fill=tk.X, padx=10, pady=(6, 4))

        ctk.CTkLabel(
            path_row,
            text=VRC_CONFIG_PATH,
            font=ctk.CTkFont(size=9),
            text_color=C_TEXT_DIM,
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ctk.CTkButton(
            path_row,
            text="打开文件位置",
            command=self._on_open_config_dir,
            width=100,
            height=24,
            corner_radius=4,
            font=ctk.CTkFont(size=10),
        ).pack(side=tk.RIGHT, padx=(6, 0))

        # 可滚动的参数列表
        self.config_scroll = ctk.CTkScrollableFrame(parent, corner_radius=6,
                                                    border_width=1,
                                                    border_color=C_BORDER)
        self.config_scroll.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0, 4))

        # 底部按钮行：左边「添加额外限制」，右边「保存配置」
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill=tk.X, padx=6, pady=(0, 6))

        self.config_save_btn = ctk.CTkButton(
            btn_row,
            text="保存配置",
            command=self._on_save_config,
            height=28,
            corner_radius=4,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_HOVER,
            border_width=0,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.config_save_btn.pack(side=tk.RIGHT)

        self.config_extra_btn = ctk.CTkButton(
            btn_row,
            text=CONFIG_EXTRA_BTN_SHOW,
            command=self._toggle_config_extra,
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11),
        )
        self.config_extra_btn.pack(side=tk.LEFT)

        # 「额外限制」区域：固定高度的外框 + 内部滚动区。
        # 外框默认不 pack（即隐藏），点按钮才展开。
        self.config_extra_holder = ctk.CTkFrame(
            parent, fg_color="transparent", corner_radius=0,
            height=CONFIG_EXTRA_HEIGHT)
        self.config_extra_holder.pack_propagate(False)   # 保持固定高度，不被内容撑开

        self.config_extra_scroll = ctk.CTkScrollableFrame(
            self.config_extra_holder, corner_radius=6,
            border_width=1, border_color=C_BORDER)
        self.config_extra_scroll.pack(fill=tk.BOTH, expand=True)

        # 展开状态
        self._config_extra_expanded = False
        self._config_pre_height = None
        self._config_add_vars = {}      # key -> {"checked","value","item"}
        self._config_removed = set()    # 主列表里标记为「待卸载」的键
        self._config_rows = {}          # key -> 行内控件引用（用于切待卸载外观）

    def _open_config_window(self):
        """悬浮弹出 VRChat 配置文件修改窗口"""
        if getattr(self, "config_win", None) is not None and self.config_win.winfo_exists():
            self.config_win.lift()
            self.config_win.focus()
            return

        self.config_win = ctk.CTkToplevel(self.root)
        self.config_win.title("VRChat配置文件修改")
        self.config_win.resizable(True, True)

        # 弹在主窗口右侧；主窗口带右侧面板时让开面板的位置
        self.root.update_idletasks()
        mw = self.root.winfo_width()
        mx = self.root.winfo_x()
        my = self.root.winfo_y()
        if self.ext_expanded:
            mw += EXT_PANEL_WIDTH + EXT_PANEL_PAD
        self.config_win.geometry(f"720x520+{mx + mw}+{my}")

        self._build_config_panel(self.config_win)
        self._load_config_json()   # 每次打开都重新读盘，拿到最新内容

        self.config_win.protocol("WM_DELETE_WINDOW", self._close_config_window)

    def _close_config_window(self):
        """关闭悬浮窗口，置空引用以便下次重新创建"""
        if getattr(self, "config_win", None) is not None:
            try:
                self.config_win.destroy()
            except Exception:
                pass
            self.config_win = None

    # ============================================================
    # VRChat OSC 调试（自 OSC-Debug.py 移植）
    # ------------------------------------------------------------
    # 发送 / 接收 / 循环发送 / 文档 四块功能与原版一一对应，
    # 只是把模块级的全局控件引用改成了 self.xxx，并把窗口生命周期
    # 挂到主窗口上（关闭窗口时停服务器、取消定时任务）。
    # ============================================================

    @staticmethod
    def _place_on_screen(win, width, height, want_x, want_y):
        """把窗口摆到 (want_x, want_y)，并保证整个窗口留在屏幕内。

        OSC 窗口宽 1000、又要弹在主窗口右侧，在 1920 这类屏幕上算出来的
        坐标会越界，交给 Windows 自动挪动就会跑到屏幕左上角，所以这里先夹紧。
        """
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, min(want_x, sw - width - 12))
        y = max(0, min(want_y, sh - height - 48))
        win.geometry(f"{width}x{height}+{x}+{y}")

    def _open_osc_window(self):
        """悬浮弹出 VRChat OSC 调试窗口"""
        if getattr(self, "osc_win", None) is not None and self.osc_win.winfo_exists():
            self.osc_win.lift()
            self.osc_win.focus()
            return

        # 每次打开都重置运行时状态，避免残留上一轮的接收数据
        self._osc_loop_after_id = None
        self._osc_recv_after_id = None
        self._osc_server = None
        self._osc_server_thread = None
        self._osc_server_running = False
        self._osc_queue = queue.Queue(maxsize=OSC_RECV_QUEUE_MAX)
        self._osc_active = False
        self._osc_run_after_id = None
        self._osc_run_steps = []
        self._osc_run_index = 0
        self._osc_run_client = None
        self._osc_run_sent = 0
        self._osc_run_errors = []
        self._osc_error_dialog_open = False
        self.osc_doc_win = None
        self.osc_doc_text = None

        self.osc_win = ctk.CTkToplevel(self.root)
        self.osc_win.title("VRChat OSC 调试 请先确保游戏的OSC处于开启状态")
        self.osc_win.resizable(True, True)

        # 弹在主窗口右侧；主窗口带右侧面板时让开面板的位置
        self.root.update_idletasks()
        mw = self.root.winfo_width()
        mx = self.root.winfo_x()
        my = self.root.winfo_y()
        if self.ext_expanded:
            mw += EXT_PANEL_WIDTH + EXT_PANEL_PAD
        self._place_on_screen(self.osc_win, OSC_WIN_W, OSC_WIN_H, mx + mw, my)

        self._build_osc_panel(self.osc_win)

        self.osc_win.protocol("WM_DELETE_WINDOW", self._close_osc_window)
        self._osc_process_recv_queue()   # 启动接收队列刷新循环
        self.osc_win.lift()
        self.osc_win.focus()

    def _build_osc_panel(self, parent):
        """OSC 调试面板：设置区 / 发送区 + 接收区 / 状态栏"""
        # ---------------- 设置区 ----------------
        top = ctk.CTkFrame(parent, corner_radius=8,
                           border_width=1, border_color=C_BORDER)
        top.pack(fill=tk.X, padx=10, pady=(10, 6))

        row1 = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
        row1.pack(fill=tk.X, padx=10, pady=(8, 4))

        ctk.CTkLabel(row1, text="目标 IP:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT)
        self.osc_ip_entry = ctk.CTkEntry(row1, width=110, height=28, corner_radius=4,
                                         font=ctk.CTkFont(size=11))
        self.osc_ip_entry.pack(side=tk.LEFT, padx=(5, 14))
        self.osc_ip_entry.insert(0, OSC_DEFAULT_IP)

        ctk.CTkLabel(row1, text="端口:", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT)
        self.osc_port_entry = ctk.CTkEntry(row1, width=70, height=28, corner_radius=4,
                                           font=ctk.CTkFont(size=11))
        self.osc_port_entry.pack(side=tk.LEFT, padx=(5, 14))
        self.osc_port_entry.insert(0, OSC_SEND_PORT_DEFAULT)

        self.osc_loop_var = tk.BooleanVar(value=False)
        self.osc_loop_switch = ctk.CTkSwitch(
            row1, text="循环发送（取消勾选停止）",
            variable=self.osc_loop_var, onvalue=True, offvalue=False,
            command=self._osc_loop_check_changed,
            font=ctk.CTkFont(size=11), switch_width=36, switch_height=18)
        self.osc_loop_switch.pack(side=tk.LEFT, padx=(0, 14))

        ctk.CTkLabel(row1, text="间隔(ms):", font=ctk.CTkFont(size=11)).pack(side=tk.LEFT)
        self.osc_interval_entry = ctk.CTkEntry(row1, width=60, height=28, corner_radius=4,
                                               font=ctk.CTkFont(size=11))
        self.osc_interval_entry.pack(side=tk.LEFT, padx=(5, 0))
        self.osc_interval_entry.insert(0, str(OSC_LOOP_INTERVAL_MS))

        row2 = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
        row2.pack(fill=tk.X, padx=10, pady=(0, 8))

        self.osc_doc_btn = ctk.CTkButton(
            row2, text="文档", command=self._osc_open_doc_window,
            width=70, height=30, corner_radius=4, font=ctk.CTkFont(size=11))
        self.osc_doc_btn.pack(side=tk.RIGHT)

        self.osc_send_btn = ctk.CTkButton(
            row2, text=OSC_SEND_BTN_TEXT, command=self._osc_on_send_button,
            width=90, height=30, corner_radius=4,
            fg_color=C_ACCENT, hover_color=C_ACCENT_HOVER, border_width=0,
            text_color="#FFFFFF", font=ctk.CTkFont(size=11, weight="bold"))
        self.osc_send_btn.pack(side=tk.RIGHT, padx=(0, 6))

        # 接收开关：未监听时是「开始接收」，监听中变红并显示「停止接收」
        self.osc_recv_btn = ctk.CTkButton(
            row2, text=OSC_RECV_START_TEXT, command=self._osc_toggle_server,
            height=30, corner_radius=4, font=ctk.CTkFont(size=11))
        self.osc_recv_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.osc_clear_btn = ctk.CTkButton(
            row2, text="清空接收数据", command=self._osc_clear_received,
            height=30, corner_radius=4, font=ctk.CTkFont(size=11))
        self.osc_clear_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        # ---------------- 左发送 / 右接收 ----------------
        mid = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 6))

        left = ctk.CTkFrame(mid, corner_radius=8, border_width=1, border_color=C_BORDER)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        right = ctk.CTkFrame(mid, corner_radius=8, border_width=1, border_color=C_BORDER)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        ctk.CTkLabel(left, text="在下面输入 OSC 消息，每行一条（支持宏，执行顺序从上到下）：", anchor="w",
                     font=ctk.CTkFont(size=11)).pack(fill=tk.X, padx=12, pady=(8, 4))
        self.osc_send_text = ctk.CTkTextbox(left, corner_radius=4, wrap="word",
                                            font=ctk.CTkFont(size=11))
        self.osc_send_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        ctk.CTkLabel(right, text=f"显示从 {OSC_RECV_PORT} 端口接收到的 OSC 数据：",
                     anchor="w", font=ctk.CTkFont(size=11)
                     ).pack(fill=tk.X, padx=12, pady=(8, 4))

        self.osc_pause_var = tk.BooleanVar(value=False)
        ctk.CTkSwitch(right, text="暂停显示（仍然接收，只是不刷到界面）",
                      variable=self.osc_pause_var, onvalue=True, offvalue=False,
                      font=ctk.CTkFont(size=11),
                      switch_width=36, switch_height=18
                      ).pack(fill=tk.X, padx=12, pady=(0, 4))

        self.osc_recv_text = ctk.CTkTextbox(right, corner_radius=4, wrap="word",
                                            font=ctk.CTkFont(size=11))
        self.osc_recv_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # ---------------- 状态栏 ----------------
        self.osc_status_var = tk.StringVar(
            value=f"就绪（当前未接收 {OSC_RECV_PORT} 端口数据）")
        ctk.CTkLabel(parent, textvariable=self.osc_status_var, anchor="w",
                     font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM
                     ).pack(fill=tk.X, padx=12, pady=(0, 8))

    def _close_osc_window(self):
        """关闭 OSC 调试窗口：停服务器、取消定时任务、关掉文档窗口"""
        if self._osc_loop_after_id is not None:
            try:
                self.root.after_cancel(self._osc_loop_after_id)
            except Exception:
                pass
            self._osc_loop_after_id = None

        # 宏 time 延时也可能正挂着，一并取消
        if self._osc_run_after_id is not None:
            try:
                self.root.after_cancel(self._osc_run_after_id)
            except Exception:
                pass
            self._osc_run_after_id = None
        self._osc_active = False

        if self._osc_recv_after_id is not None:
            try:
                self.root.after_cancel(self._osc_recv_after_id)
            except Exception:
                pass
            self._osc_recv_after_id = None

        self._osc_stop_server()

        if getattr(self, "osc_doc_win", None) is not None:
            try:
                self.osc_doc_win.destroy()
            except Exception:
                pass
            self.osc_doc_win = None
            self.osc_doc_text = None

        if getattr(self, "osc_win", None) is not None:
            try:
                self.osc_win.destroy()
            except Exception:
                pass
            self.osc_win = None

    # ---- 发送 ----

    @staticmethod
    def _osc_parse_arg(token):
        """把字符串 token 转成合适的 Python 类型（int/float/bool/str）"""
        t = token.strip()

        # 布尔值
        if t.lower() == "true":
            return True
        if t.lower() == "false":
            return False

        # 带引号的字符串
        if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
            return t[1:-1]

        # 整数
        try:
            return int(t)
        except ValueError:
            pass

        # 浮点数
        try:
            return float(t)
        except ValueError:
            pass

        # 其余当字符串
        return t

    def _osc_parse_script(self, raw_text):
        """把文本框内容解析成「步骤表」。

        每行三种情况：
          - 空行 / # 开头   -> 跳过
          - time X          -> 宏指令，等待 X 毫秒后继续（不作为 OSC 发出）
          - / 开头          -> 一条 OSC 消息

        返回 (steps, error_lines)：
          steps 里每条是 ("delay", 毫秒) 或 ("send", 行号, 原文, 地址, 参数列表)
          error_lines 每条是 (行号, 原文, 原因)
        """
        steps = []
        error_lines = []

        for idx, line in enumerate(raw_text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue

            parts = line.split()
            head = parts[0]

            # ---- 宏指令：time X ----
            if head.lower() == OSC_MACRO_TIME:
                # 支持行尾注释：time 500  # 等半秒 —— 遇到 # 就截断
                rest = []
                for t in parts[1:]:
                    if t.startswith("#"):
                        break
                    rest.append(t)
                if not rest:
                    error_lines.append((idx, line, "time 后面要跟毫秒数，例如 time 500"))
                    continue
                if len(rest) > 1:
                    error_lines.append((idx, line, "time 后面只能跟一个毫秒数"))
                    continue
                try:
                    ms = int(rest[0])
                except ValueError:
                    error_lines.append((idx, line, f"time 的毫秒数必须是整数：{rest[0]}"))
                    continue
                if ms < 0:
                    error_lines.append((idx, line, "time 的毫秒数不能是负数"))
                    continue
                steps.append(("delay", ms))
                continue

            # ---- 普通 OSC 消息 ----
            if not head.startswith("/"):
                error_lines.append((idx, line, "地址必须以 / 开头（宏指令目前只支持 time）"))
                continue

            args = [self._osc_parse_arg(t) for t in parts[1:]]
            steps.append(("send", idx, line, head, args))

        return steps, error_lines

    def _osc_set_send_button_running(self, running):
        """执行期间把「发送 OSC」按钮切换成「停止发送」"""
        btn = getattr(self, "osc_send_btn", None)
        if btn is None:
            return
        try:
            if running:
                btn.configure(text=OSC_STOP_BTN_TEXT, fg_color=C_RED,
                              hover_color=C_RED_HOVER)
            else:
                btn.configure(text=OSC_SEND_BTN_TEXT, fg_color=C_ACCENT,
                              hover_color=C_ACCENT_HOVER)
        except Exception:
            pass

    def _osc_set_recv_button_running(self, running):
        """监听期间把接收按钮切到「停止接收」并转为红色"""
        btn = getattr(self, "osc_recv_btn", None)
        if btn is None:
            return
        try:
            if running:
                btn.configure(text=OSC_RECV_STOP_TEXT, fg_color=C_RED,
                              hover_color=C_RED_HOVER, border_width=0,
                              text_color="#FFFFFF")
            else:
                # 还原成主题里的普通按钮样式（中性底 + 细描边）
                btn.configure(text=OSC_RECV_START_TEXT, fg_color=C_BTN,
                              hover_color=C_BTN_HOVER, border_width=1,
                              border_color=C_BORDER, text_color=C_TEXT)
        except Exception:
            pass

    def _osc_start_run(self):
        """解析文本框，开始执行整个序列（循环模式下每轮都会重新解析）"""
        try:
            ip = self.osc_ip_entry.get().strip() or OSC_DEFAULT_IP
            port_str = self.osc_port_entry.get().strip() or OSC_SEND_PORT_DEFAULT
            port = int(port_str)
        except ValueError:
            messagebox.showerror("错误", "端口必须是数字。")
            return

        raw_text = self.osc_send_text.get("1.0", tk.END).strip()
        if not raw_text:
            messagebox.showwarning("提示", "请输入至少一行 OSC 消息。")
            return

        steps, errors = self._osc_parse_script(raw_text)
        if not steps and not errors:
            self.osc_status_var.set("没有可发送的内容。")
            return

        self._osc_run_ip = ip
        self._osc_run_port = port
        self._osc_run_client = udp_client.SimpleUDPClient(ip, port)
        self._osc_run_steps = steps
        self._osc_run_index = 0
        self._osc_run_sent = 0
        self._osc_run_errors = list(errors)
        self._osc_active = True
        self._osc_set_send_button_running(True)

        n_delay = sum(1 for s in steps if s[0] == "delay")
        if n_delay:
            self.osc_status_var.set(
                f"开始执行：{len(steps) - n_delay} 条消息 / {n_delay} 处延时 …")
        else:
            self.osc_status_var.set(f"开始发送到 {ip}:{port} …")

        self._osc_step()

    def _osc_step(self):
        """执行步骤表。

        连续的发送步骤一口气发完（和以前一样是瞬时的）；
        遇到 time 延时就让出，用 after 排下一次，避免界面卡住。
        """
        while self._osc_run_index < len(self._osc_run_steps):
            step = self._osc_run_steps[self._osc_run_index]
            self._osc_run_index += 1

            if step[0] == "send":
                _, lineno, raw_line, address, args = step
                try:
                    if len(args) == 0:
                        # 没有参数时，发送一个空列表
                        self._osc_run_client.send_message(address, [])
                    elif len(args) == 1:
                        # 一个参数可以直接传单值
                        self._osc_run_client.send_message(address, args[0])
                    else:
                        self._osc_run_client.send_message(address, args)
                    self._osc_run_sent += 1
                except Exception as e:
                    self._osc_run_errors.append((lineno, raw_line, str(e)))
                continue

            # step[0] == "delay"
            ms = step[1]
            self.osc_status_var.set(f"宏延时 {ms} ms（已发 {self._osc_run_sent} 条）…")
            self._osc_run_after_id = self.root.after(ms, self._osc_step)
            return

        self._osc_finish_run()

    def _osc_finish_run(self):
        """一串跑完：报状态 / 报错；勾选了循环就等「间隔」毫秒后开下一串"""
        self._osc_run_after_id = None

        sent = self._osc_run_sent
        if sent > 0:
            self.osc_status_var.set(
                f"已发送 {sent} 条消息到 {self._osc_run_ip}:{self._osc_run_port}")
        else:
            self.osc_status_var.set("未发送任何消息。")

        errors = self._osc_run_errors
        # 循环模式下出错会每轮都走到这里，加个闸避免模态框叠罗汉
        if errors and not self._osc_error_dialog_open:
            msg = "以下行未能发送：\n\n"
            for lineno, content, reason in errors:
                msg += f"第 {lineno} 行: {content}\n原因: {reason}\n\n"
            self._osc_error_dialog_open = True
            try:
                messagebox.showerror("发送错误", msg)
            finally:
                self._osc_error_dialog_open = False

        if self.osc_loop_var.get():
            self._osc_loop_after_id = self.root.after(
                self._osc_get_loop_interval_ms(), self._osc_loop_run)
        else:
            self._osc_active = False
            self._osc_set_send_button_running(False)

    def _osc_loop_run(self):
        """循环模式：等间隔到点后开始下一串"""
        self._osc_loop_after_id = None
        if not self.osc_loop_var.get():
            self._osc_active = False
            self._osc_set_send_button_running(False)
            return
        self._osc_start_run()

    def _osc_stop_run(self):
        """中断当前执行：取消待执行的定时任务，没跑到的行不再发"""
        for attr in ("_osc_run_after_id", "_osc_loop_after_id"):
            aid = getattr(self, attr, None)
            if aid is not None:
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
                setattr(self, attr, None)

        was_active = self._osc_active
        self._osc_active = False
        self._osc_set_send_button_running(False)

        if was_active:
            self.osc_status_var.set(
                f"已停止发送（本次共发出 {self._osc_run_sent} 条）")

    def _osc_get_loop_interval_ms(self):
        """从间隔输入框取毫秒数；无效输入回退到默认值"""
        try:
            text = self.osc_interval_entry.get().strip()
            if not text:
                return OSC_LOOP_INTERVAL_MS
            value = int(text)
            if value <= 0:
                raise ValueError
            return value
        except Exception:
            return OSC_LOOP_INTERVAL_MS

    def _osc_on_send_button(self):
        """发送按钮：空闲时开始执行；执行期间再点一次即中断"""
        if self._osc_active:
            self._osc_stop_run()
        else:
            self._osc_start_run()

    def _osc_loop_check_changed(self):
        """取消勾选循环：不再安排下一串（已在跑的这一串仍会跑完）"""
        if not self.osc_loop_var.get() and self._osc_loop_after_id is not None:
            try:
                self.root.after_cancel(self._osc_loop_after_id)
            except Exception:
                pass
            self._osc_loop_after_id = None
            if not self._osc_active:
                self._osc_set_send_button_running(False)

    # ---- 接收 ----

    def _osc_receive_handler(self, address, *args):
        """OSC 接收回调（在服务器线程里执行，只负责往队列里塞）"""
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        line = f"[{timestamp}] {address} {list(args)}\n"
        try:
            # 放入队列，由主线程定时批量刷新 UI
            self._osc_queue.put_nowait(line)
        except queue.Full:
            # 队列满了就丢弃本条，避免阻塞
            pass

    def _osc_toggle_server(self):
        """接收按钮：未监听时开始监听，监听中则停止"""
        if self._osc_server_running:
            self._osc_stop_server()
        else:
            self._osc_start_server()

    def _osc_start_server(self):
        """在 9001 端口启动 OSC 接收服务器"""
        if self._osc_server_running:
            return  # 已经在运行，避免重复启动

        disp = dispatcher.Dispatcher()
        disp.set_default_handler(self._osc_receive_handler)

        # BlockingOSCUDPServer：不为每条消息新建线程
        try:
            self._osc_server = osc_server.BlockingOSCUDPServer(
                ("0.0.0.0", OSC_RECV_PORT), disp)
        except OSError as e:
            self._osc_server = None
            self.osc_status_var.set(f"启动失败：{OSC_RECV_PORT} 端口不可用")
            self._osc_set_recv_button_running(False)   # 没起来就不该变红
            messagebox.showerror(
                "无法监听",
                f"在 {OSC_RECV_PORT} 端口启动接收失败：\n\n{e}\n\n"
                "常见原因：已有别的 OSC 工具（例如原版 OSC-Debug）占着这个端口。",
            )
            return

        self._osc_server_thread = threading.Thread(
            target=self._osc_server.serve_forever, daemon=True)
        self._osc_server_thread.start()
        self._osc_server_running = True
        self._osc_set_recv_button_running(True)

        # 直接覆盖：之前这里是追加写，导致「已停止监听… | 已开始监听…」越滚越长
        self.osc_status_var.set(f"已开始监听 {OSC_RECV_PORT} 端口接收 OSC")

    def _osc_stop_server(self):
        """停止 OSC 接收服务器"""
        if self._osc_server_running and self._osc_server is not None:
            try:
                self._osc_server.shutdown()
                self._osc_server.server_close()
            except Exception:
                pass

            self._osc_server = None
            self._osc_server_thread = None
            self._osc_server_running = False

            if self.osc_status_var is not None:
                self.osc_status_var.set(f"已停止监听 {OSC_RECV_PORT} 端口接收 OSC")

        # 不管刚才在不在跑，按钮都同步回未监听态
        self._osc_set_recv_button_running(False)

    def _osc_append_received_text(self, texts):
        """批量往接收文本框追加内容，并限制最大行数"""
        if not texts:
            return

        for t in texts:
            self.osc_recv_text.insert(tk.END, t)

        # 保证滚动到最底部
        self.osc_recv_text.see(tk.END)

        # 限制最大行数，避免行数无限增长导致卡顿
        total_lines = int(float(self.osc_recv_text.index("end-1c").split(".")[0]))
        if total_lines > OSC_MAX_RECV_LINES:
            start_line_to_keep = total_lines - OSC_MAX_RECV_LINES + 1
            self.osc_recv_text.delete("1.0", f"{start_line_to_keep}.0")

    def _osc_process_recv_queue(self):
        """定时从队列取数据批量刷到界面，减少 UI 更新频率"""
        # 窗口已关就停掉这个循环（连同定时任务本身）
        if getattr(self, "osc_win", None) is None or not self.osc_win.winfo_exists():
            self._osc_recv_after_id = None
            return

        # 暂停显示时，清空队列但不写 UI
        if self.osc_pause_var.get():
            try:
                while True:
                    self._osc_queue.get_nowait()
            except queue.Empty:
                pass
        else:
            batch = []
            try:
                # 一次最多取一批，避免单次处理太久
                for _ in range(OSC_RECV_BATCH):
                    batch.append(self._osc_queue.get_nowait())
            except queue.Empty:
                pass

            if batch:
                self._osc_append_received_text(batch)

        self._osc_recv_after_id = self.root.after(OSC_RECV_FLUSH_MS,
                                                  self._osc_process_recv_queue)

    def _osc_clear_received(self):
        """清空接收数据文本框"""
        self.osc_recv_text.delete("1.0", tk.END)

    # ---- 文档 ----

    def _osc_open_doc_window(self):
        """打开或激活 OSC 文档窗口（只读可复制，内容来自 osc_doc.txt）"""
        if self.osc_doc_win is not None and self.osc_doc_win.winfo_exists():
            self.osc_doc_win.deiconify()
            self.osc_doc_win.lift()
            return

        self.osc_doc_win = ctk.CTkToplevel(self.root)
        self.osc_doc_win.title("文档")
        self.osc_doc_win.resizable(True, True)

        # 紧贴 OSC 调试窗口右侧弹出，高度与其一致；右边放不下就改放左侧
        ref = self.osc_win if (self.osc_win is not None and self.osc_win.winfo_exists()) \
            else self.root
        ref.update_idletasks()
        ref_x = ref.winfo_x()
        ref_y = ref.winfo_y()
        ref_w = ref.winfo_width()
        ref_h = ref.winfo_height()

        doc_height = ref_h if ref_h > 0 else 500
        want_x = ref_x + ref_w
        if want_x + OSC_DOC_W > self.root.winfo_screenwidth():
            want_x = ref_x - OSC_DOC_W
        self._place_on_screen(self.osc_doc_win, OSC_DOC_W, doc_height, want_x, ref_y)

        self.osc_doc_text = ctk.CTkTextbox(self.osc_doc_win, corner_radius=4,
                                           wrap="word", font=ctk.CTkFont(size=11))
        self.osc_doc_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.osc_doc_text.insert("1.0", OSC_DOC_TEXT)
        # 和 ℹ 信息窗口一样：只读（仍可选中复制），内容一律以 osc_doc.txt 为准
        self.osc_doc_text.configure(state="disabled")

    def _on_open_config_dir(self):
        """打开 config.json 所在的文件夹。

        只打开文件夹本身，不打开 / 不选中 config.json 文件。
        """
        folder = os.path.dirname(VRC_CONFIG_PATH)
        if not os.path.isdir(folder):
            messagebox.showwarning(
                "文件夹不存在",
                f"未找到 config.json 所在目录：\n\n{folder}\n\n"
                "请先运行一次 VRChat，让游戏自动生成该目录。",
            )
            return
        try:
            os.startfile(folder)
        except Exception as e:
            messagebox.showerror("打开失败", f"{folder}\n\n{e}")

    def _window_size(self):
        """当前窗口尺寸；尚未映射时退回请求尺寸，避免拿到 1x1。"""
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        if w <= 1:
            w = self.root.winfo_reqwidth()
        if h <= 1:
            h = self.root.winfo_reqheight()
        return w, h

    def _on_toggle_ext_menu(self):
        """展开 / 收起右侧子菜单面板。

        展开时把窗口同步加宽，避免面板挤占主界面。
        """
        w, h = self._window_size()
        if self.ext_expanded:
            self.ext_side_panel.pack_forget()
            self.ext_expanded = False
            self.ext_toggle_btn.configure(text=EXT_PANEL_COLLAPSED_TEXT)
            if self._pre_expand_width:
                self.root.geometry(f"{self._pre_expand_width}x{h}")
                self._pre_expand_width = None
        else:
            # 记下加宽前的窗口宽度，收起时还原
            self._pre_expand_width = w

            # before=... 把面板插到主区域之前，保证它先拿到宽度
            self.ext_side_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 8), before=self.top_frame)
            self.ext_expanded = True
            self.ext_toggle_btn.configure(text=EXT_PANEL_EXPANDED_TEXT)

            self.root.geometry(f"{w + EXT_PANEL_WIDTH + EXT_PANEL_PAD}x{h}")

    # ---- 功能 ----

    def _show_config_hint(self, text, color=C_TEXT_DIM):
        """在配置区显示一条提示信息"""
        ctk.CTkLabel(
            self.config_scroll,
            text=text,
            font=ctk.CTkFont(size=11),
            text_color=color,
            justify="left",
            anchor="w",
        ).pack(fill=tk.X, padx=6, pady=20)

    def _load_config_json(self):
        """读取 VRChat config.json 并生成可编辑控件。

        对文件内容不做任何预设，完全按「读到什么显示什么」处理：
        - 键多了：没有汉化条目的直接显示英文键名本身，照样可编辑；
        - 键少了：没有的键就不显示，不会占位、不会报错；
        - 值的类型变了：按新值的类型显示（int / float / bool / null 都认）；
        - 单个条目出错不影响其它条目，也不会影响整个窗口。
        解析上尽量宽容，见 load_json_lenient()。
        """
        # 清空旧条目
        for w in self.config_scroll.winfo_children():
            w.destroy()
        self._config_entries.clear()
        self._config_readonly.clear()
        self._config_data = {}
        self._root_is_dict = True

        # 重置「额外限制」的待装配 / 待卸载标记
        self._config_removed.clear()
        self._config_rows.clear()
        self._config_add_vars.clear()
        self._refresh_config_extra()

        if not os.path.isfile(VRC_CONFIG_PATH):
            self._show_config_hint("config.json 未找到\n请先运行一次 VRChat")
            return

        data, err = load_json_lenient(VRC_CONFIG_PATH)
        if err is not None:
            # 彻底读不了也别让面板空着：报出真正原因，并把原文只读展示出来。
            # _config_data 保持为空，保存时会被「未加载到配置数据」挡住，不会覆盖坏文件。
            self._show_config_hint(
                "config.json 内容无法解析，仅作只读展示。\n"
                f"原因：{err}\n"
                "（多为游戏退出时写坏了文件，重新登录一次 VRChat 通常会自动恢复\n如果多次出现这个提示，可能软件还没适配新参数的传递，暂时不可用等待更新即可）",
                color="#ff6b6b",
            )
            try:
                with open(VRC_CONFIG_PATH, "r", encoding="utf-8-sig",
                          errors="replace") as f:
                    box = ctk.CTkTextbox(self.config_scroll, corner_radius=6,
                                         font=ctk.CTkFont(size=11))
                    box.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 6))
                    box.insert("1.0", f.read())
                    box.configure(state="disabled")
            except Exception:
                pass
            return

        # 顶层不是键值对象（少见格式）：整份只读展示，保存时原样保留不覆盖
        if not isinstance(data, dict):
            self._root_is_dict = False
            self._config_data = data
            self._show_config_hint("config.json 顶层不是键值对象，仅作只读展示")
            try:
                box = ctk.CTkTextbox(self.config_scroll, corner_radius=6,
                                     font=ctk.CTkFont(size=11))
                box.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 6))
                box.insert("1.0", json.dumps(data, indent=4, ensure_ascii=False))
                box.configure(state="disabled")
            except Exception:
                pass
            return

        self._config_data = data

        # 为每个顶层键生成输入行；单个键出错不影响其它键
        for key, value in data.items():
            try:
                self._add_config_row(key, value)
            except Exception as e:
                ctk.CTkLabel(
                    self.config_scroll,
                    text=f"{key}: 无法显示 ({e})",
                    font=ctk.CTkFont(size=11),
                    text_color="#ff6b6b",
                    anchor="w",
                ).pack(fill=tk.X, padx=6, pady=2)

        # 数据就绪后重新生成「额外限制」区域（只列还没装配的）
        self._refresh_config_extra()

    def _add_config_row(self, key, value):
        """在滚动区域中添加一行：键名 + 输入框 + 卸载按钮，附中文翻译。

        值为对象 / 数组时无法用单行文本框编辑，改为只读展示并原样保留。
        """
        wrapper = ctk.CTkFrame(self.config_scroll, fg_color="transparent")
        wrapper.pack(fill=tk.X, padx=4, pady=(3, 0))

        # 上行：键名 + 右侧固定按钮 + 编辑框
        row_top = ctk.CTkFrame(wrapper, fg_color="transparent")
        row_top.pack(fill=tk.X)

        display_key = key if len(key) <= 24 else key[:21] + "..."
        key_label = ctk.CTkLabel(
            row_top,
            text=display_key,
            font=ctk.CTkFont(size=12),
            width=140,
            anchor="w",
        )
        key_label.pack(side=tk.LEFT, padx=(0, 4))

        # 对象 / 数组 -> 只读；其它类型 -> 可编辑
        readonly = isinstance(value, (dict, list))
        if readonly:
            try:
                text = json.dumps(value, ensure_ascii=False)
            except Exception:
                text = str(value)
            self._config_readonly.add(key)
        elif value is None:
            text = "null"
        else:
            text = str(value)

        orig_state = "readonly" if readonly else "normal"

        # 右侧固定按钮先 pack（先 pack 的靠最右），输入框最后占满剩余宽度
        uninstall_btn = ctk.CTkButton(
            row_top,
            text="卸载",
            command=lambda k=key: self._on_uninstall_key(k),
            width=50,
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=11),
        )
        uninstall_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # cache_directory 特殊处理：右侧加"更改"按钮（排在卸载左侧）
        if key == "cache_directory" and not readonly:
            ctk.CTkButton(
                row_top,
                text="更改",
                command=lambda k=key, v=None: self._on_change_cache_dir(
                    self._config_entries[k]),
                width=50,
                height=28,
                corner_radius=4,
                font=ctk.CTkFont(size=11),
            ).pack(side=tk.RIGHT, padx=(4, 0))

        var = tk.StringVar(value=text)
        self._config_entries[key] = var
        entry = ctk.CTkEntry(
            row_top,
            textvariable=var,
            height=28,
            corner_radius=4,
            font=ctk.CTkFont(size=12),
            state=orig_state,
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 下行：中文翻译（没有汉化就不加这一行，键名本身就是英文）
        cn = CONFIG_TRANSLATIONS.get(key, "")
        if cn:
            ctk.CTkLabel(
                wrapper,
                text=f"    {cn}",
                font=ctk.CTkFont(size=11),
                text_color=C_TEXT_DIM,
                anchor="w",
            ).pack(fill=tk.X, padx=(4, 0))

        # 记下控件引用，卸载 / 撤销时用来切换外观
        self._config_rows[key] = {
            "label": key_label, "btn": uninstall_btn,
            "entry": entry, "display": display_key, "state": orig_state,
        }

    # ---- 词条的卸载 / 撤销 ----

    def _on_uninstall_key(self, key):
        """点某一行的「卸载」：弹确认后再标记（不是立刻写盘）"""
        if key in self._config_removed:
            return  # 已经是待卸载状态，忽略（此时按钮显示的是「撤销」）
        if not messagebox.askyesno(f"确认卸载「{key}」", CONFIG_UNINSTALL_WARN):
            return
        self._config_removed.add(key)
        self._apply_row_removed_state(key)

    def _on_undo_uninstall(self, key):
        """撤销待卸载标记"""
        self._config_removed.discard(key)
        self._apply_row_removed_state(key)

    def _apply_row_removed_state(self, key):
        """把某一行切成 / 切回「待卸载」外观"""
        row = self._config_rows.get(key)
        if not row:
            return
        try:
            if key in self._config_removed:
                row["label"].configure(text=f"✕ {row['display']}", text_color=C_RED)
                row["entry"].configure(state="disabled")
                row["btn"].configure(
                    text="撤销", command=lambda k=key: self._on_undo_uninstall(k),
                    fg_color=C_RED, hover_color=C_RED_HOVER,
                    border_width=0, text_color="#FFFFFF")
            else:
                row["label"].configure(text=row["display"], text_color=C_TEXT)
                row["entry"].configure(state=row["state"])
                row["btn"].configure(
                    text="卸载", command=lambda k=key: self._on_uninstall_key(k),
                    fg_color=C_BTN, hover_color=C_BTN_HOVER,
                    border_width=1, border_color=C_BORDER, text_color=C_TEXT)
        except Exception:
            pass

    # ---- 「添加额外限制」 ----

    def _toggle_config_extra(self):
        """展开 / 收起「额外限制」区域（同时把悬浮窗加高）"""
        win = getattr(self, "config_win", None)
        if win is None or not win.winfo_exists():
            return

        if self._config_extra_expanded:
            self.config_extra_holder.pack_forget()
            self._config_extra_expanded = False
            self.config_extra_btn.configure(text=CONFIG_EXTRA_BTN_SHOW)
            if self._config_pre_height:
                win.geometry(f"{win.winfo_width()}x{self._config_pre_height}")
                self._config_pre_height = None
            return

        win.update_idletasks()
        self._config_pre_height = win.winfo_height()
        self.config_extra_holder.pack(fill=tk.X, padx=6, pady=(0, 6))
        self._config_extra_expanded = True
        self.config_extra_btn.configure(text=CONFIG_EXTRA_BTN_HIDE)
        self._refresh_config_extra()

        target = self._config_pre_height + CONFIG_EXTRA_HEIGHT + 14
        max_h = win.winfo_screenheight() - 80
        win.geometry(f"{win.winfo_width()}x{min(target, max_h)}")

    def _missing_catalog_items(self):
        """官方有、而当前 config.json 里没有的词条（保留分组结构）"""
        have = set(self._config_data) if isinstance(self._config_data, dict) else set()
        out = []
        for g in CONFIG_CATALOG:
            items = [i for i in g["items"] if i["key"] not in have]
            if items:
                out.append({"group": g["group"], "items": items})
        return out

    def _refresh_config_extra(self):
        """（重新）生成「额外限制」区域"""
        if not getattr(self, "_config_extra_expanded", False):
            return
        scroll = self.config_extra_scroll
        for w in scroll.winfo_children():
            w.destroy()
        self._config_add_vars = {}

        if not self._root_is_dict or not isinstance(self._config_data, dict) \
                or not self._config_data:
            ctk.CTkLabel(
                scroll,
                text="当前没有可用的配置数据，暂时不能装配额外词条。\n"
                     "（config.json 未找到或无法解析时一律不写入，避免把文件写坏）",
                font=ctk.CTkFont(size=11), text_color="#ff6b6b",
                justify="left", anchor="w",
            ).pack(fill=tk.X, padx=8, pady=12)
            return

        groups = self._missing_catalog_items()
        total = sum(len(g["items"]) for g in groups)
        if not groups:
            ctk.CTkLabel(
                scroll,
                text="官方文档里的词条都已经在你的配置里了，没有可添加的。",
                font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM, anchor="w",
            ).pack(fill=tk.X, padx=8, pady=12)
            return

        ctk.CTkLabel(
            scroll,
            text=f"以下 {total} 个词条官方支持、但你的 config.json 里还没有。\n"
                 "勾选 = 装配（点右下角「保存配置」才真正写进文件），参数可以顺便改。",
            font=ctk.CTkFont(size=11), text_color=C_TEXT_DIM,
            justify="left", anchor="w",
        ).pack(fill=tk.X, padx=8, pady=(8, 2))

        for g in groups:
            self._build_extra_group(scroll, g)

    def _build_extra_group(self, parent, group):
        """一个分组：可折叠标题 + 词条（带子分组小标题）"""
        box = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        box.pack(fill=tk.X, padx=4, pady=(4, 0))

        body = ctk.CTkFrame(box, fg_color="transparent", corner_radius=0)
        state = {"open": True}

        def toggle(_box=box, _body=body, _state=state, _g=group):
            if _state["open"]:
                _body.pack_forget()
                head.configure(text=f"▸ {_g['group']}  （{len(_g['items'])}）")
            else:
                _body.pack(fill=tk.X, padx=(6, 0), pady=(2, 0))
                head.configure(text=f"▾ {_g['group']}  （{len(_g['items'])}）")
            _state["open"] = not _state["open"]

        head = ctk.CTkButton(
            box, text=f"▾ {group['group']}  （{len(group['items'])}）",
            command=toggle, height=26, corner_radius=4, anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"))
        head.pack(fill=tk.X)
        body.pack(fill=tk.X, padx=(6, 0), pady=(2, 0))

        last_sub = None
        for item in group["items"]:
            sub = item.get("sub", "")
            if sub and sub != last_sub:
                ctk.CTkLabel(
                    body, text=f"· {sub}", font=ctk.CTkFont(size=10),
                    text_color=C_TEXT_DIM, anchor="w",
                ).pack(fill=tk.X, pady=(6, 0))
                last_sub = sub
            self._build_extra_item(body, item)

    def _build_extra_item(self, parent, item):
        """一个词条：勾选框 + 键名 + 参数控件 + 说明"""
        key = item["key"]
        kind = item["kind"]

        wrap = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        wrap.pack(fill=tk.X, pady=(2, 0))

        top = ctk.CTkFrame(wrap, fg_color="transparent", corner_radius=0)
        top.pack(fill=tk.X)

        checked = tk.BooleanVar(value=False)
        if kind == "bool":
            value_var = tk.BooleanVar(value=bool(item["default"]))
        else:
            if kind == "array":
                init = ", ".join(str(x) for x in item["default"])
            else:
                init = str(item["default"])
            value_var = tk.StringVar(value=init)

        widgets = []          # 勾选后需要解禁的控件
        extra_btn = [None]    # path 的「选择」按钮

        def on_toggle():
            editable = checked.get()
            for w in widgets:
                try:
                    w.configure(state="normal" if editable else "disabled")
                except Exception:
                    pass
            if extra_btn[0] is not None:
                try:
                    extra_btn[0].configure(state="normal" if editable else "disabled")
                except Exception:
                    pass

        ctk.CTkCheckBox(
            top, text="", variable=checked, command=on_toggle,
            width=22, checkbox_width=18, checkbox_height=18,
            font=ctk.CTkFont(size=11),
        ).pack(side=tk.LEFT, padx=(0, 4))

        tag = "  [过时]" if item.get("legacy") else ""
        ctk.CTkLabel(
            top, text=key + tag, font=ctk.CTkFont(size=11),
            text_color=C_TEXT_DIM if item.get("legacy") else C_TEXT,
            width=300, anchor="w",
        ).pack(side=tk.LEFT)

        if kind == "bool":
            sw = ctk.CTkSwitch(
                top, text="开", variable=value_var,
                onvalue=True, offvalue=False, state="disabled",
                font=ctk.CTkFont(size=10), switch_width=36, switch_height=18)
            sw.pack(side=tk.LEFT, padx=(6, 0))
            widgets.append(sw)
        else:
            ent = ctk.CTkEntry(
                top, textvariable=value_var, height=26, corner_radius=4,
                width=140, font=ctk.CTkFont(size=11), state="disabled")
            ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
            widgets.append(ent)

            if kind == "path":
                btn = ctk.CTkButton(
                    top, text="选择", width=50, height=26, corner_radius=4,
                    state="disabled", font=ctk.CTkFont(size=11),
                    command=lambda v=value_var: self._on_pick_folder_into(v))
                btn.pack(side=tk.LEFT, padx=(4, 0))
                extra_btn[0] = btn

        ctk.CTkLabel(
            wrap, text=f"    {item['desc']}\n    {item['hint']}",
            font=ctk.CTkFont(size=10), text_color=C_TEXT_DIM,
            justify="left", anchor="w",
        ).pack(fill=tk.X, padx=(26, 0))

        self._config_add_vars[key] = {
            "checked": checked, "value": value_var, "item": item,
        }

    def _on_pick_folder_into(self, var):
        """给额外限制区里的路径词条选文件夹"""
        folder = filedialog.askdirectory(title="选择文件夹")
        if folder:
            var.set(folder.replace("/", "\\"))

    @staticmethod
    def _pending_value(st):
        """把额外限制区里某个词条的控件值转成要写进 JSON 的值"""
        item = st["item"]
        kind = item["kind"]
        if kind == "bool":
            return bool(st["value"].get())
        raw = st["value"].get().strip()
        if kind == "int":
            return int(raw)
        if kind == "array":
            return [x.strip() for x in raw.split(",") if x.strip()]
        return raw

    def _on_change_cache_dir(self, var):
        """更改缓存文件夹 — 弹出目录选择，写入双反斜杠路径"""
        folder = filedialog.askdirectory(title="选择缓存文件夹 [请确保文件夹所在的磁盘有30GB以上空间]")
        if not folder:
            return
        var.set(folder.replace("/", "\\"))

    @staticmethod
    def _coerce(raw, original):
        """把文本框里的字符串还原成原始类型，尽量保持 JSON 结构不变。"""
        if isinstance(original, bool):
            return raw.strip().lower() in ("true", "1", "yes", "on")
        if original is None:
            return None if raw.strip().lower() in ("", "null", "none") else raw
        if isinstance(original, int):
            try:
                return int(raw)
            except ValueError:
                try:
                    return float(raw)
                except ValueError:
                    return raw
        if isinstance(original, float):
            try:
                return float(raw)
            except ValueError:
                return raw
        return raw

    def _on_save_config(self):
        """保存配置 — 将编辑值写回 config.json"""
        if not self._root_is_dict:
            messagebox.showwarning(
                "无法保存",
                "config.json 顶层不是键值对象，为避免破坏内容，本次不做写入。",
            )
            return
        if not isinstance(self._config_data, dict) or not self._config_data:
            messagebox.showwarning("无数据", "未加载到配置数据。")
            return

        # 类型保持：按原始值的类型还原；
        # 只读条目（对象 / 数组）跳过，_config_data 里保留原值不动。
        failed = []
        for key, var in self._config_entries.items():
            if key in self._config_readonly:
                continue
            if key in self._config_removed:
                continue      # 已标记待卸载的，不再写回
            try:
                self._config_data[key] = self._coerce(var.get(), self._config_data.get(key))
            except Exception as e:
                # 单个键转换失败就保留原值，不影响其它键；但要如实报出来，不静默吞掉
                failed.append(f"{key}: {e}")

        # 「额外限制」里勾选的词条 -> 装配进配置
        added = []
        for key, st in self._config_add_vars.items():
            if not st["checked"].get():
                continue
            try:
                self._config_data[key] = self._pending_value(st)
                added.append(key)
            except Exception as e:
                failed.append(f"{key}: 无法装配（e={e}）")

        # 主列表里标记的词条 -> 从配置里删掉（等于恢复 VRChat 默认设置）
        removed = [k for k in self._config_removed if k in self._config_data]
        for key in removed:
            self._config_data.pop(key, None)

        try:
            with open(VRC_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return

        # 写盘成功后重新读一遍，让主列表和额外限制区都跟着刷新
        self._load_config_json()

        tip = ""
        if added:
            tip += f"\n\n新装配 {len(added)} 个：{', '.join(added)}"
        if removed:
            tip += f"\n\n已卸载 {len(removed)} 个：{', '.join(removed)}"

        if failed:
            messagebox.showwarning(
                "保存成功（部分未生效）",
                "以下条目格式无法识别，已保留原值：\n\n" + "\n".join(failed[:10]) + tip,
            )
        else:
            messagebox.showinfo("保存成功", "部分功能会在重启游戏后生效" + tip)

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
        """弹出信息窗口 — 首次弹出时贴在主窗口右侧并等高，之后独立不再跟随。"""
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

        # 信息窗口独立存在：只在弹出时贴一次主窗口右侧，之后不再跟随主窗口移动
        self._info_win.protocol("WM_DELETE_WINDOW", lambda: self._info_win.destroy())

    def _on_main_close(self):
        """主窗口关闭时清理"""
        if hasattr(self, '_info_win') and self._info_win.winfo_exists():
            self._info_win.destroy()
        self._close_config_window()
        self._close_osc_window()     # 停 OSC 接收服务器 + 取消失效的定时任务
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
            messagebox.showinfo("注入完成")
        except Exception as e:
            messagebox.showerror("注入失败，请检查是否有足够的权限或同行文件夹是否存在", str(e))

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
    apply_global_font()                 # 必须放在主题设置之后，否则会被重置
    apply_tech_theme()                  # 科技感配色，同样必须在主题设置之后
    app = VRChatHelperApp()
    app.run()


if __name__ == "__main__":
    main()
