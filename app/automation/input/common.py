# -*- coding: utf-8 -*-
"""
automation 公共底座：时间/等待、前景窗口、坐标换算、统一日志。

约束：
- 不新增三方依赖；不做异常吞噬；变量命名具备语义。
- Windows10/PowerShell 环境；与上层 UI/运行时保持解耦。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple
import ctypes
import time

from engine.configs.settings import settings
from engine.utils.logging.console_sanitizer import ascii_safe_print
from .window_finder import find_window_handle

# 统一常量（避免魔数分散）
DEFAULT_DRAG_MOUSE_DOWN_MS: int = 200
DEFAULT_DRAG_MOUSE_UP_MS: int = 200
DEFAULT_TYPE_SELECT_WAIT_SECONDS: float = 3.0
OCR_EXCLUDE_TOP_PIXELS_DEFAULT: int = 150
WARNING_FALLBACK_OFFSET_XY: Tuple[int, int] = (50, 25)
DEFAULT_WAIT_INTERVAL_SECONDS: float = 0.1
DEFAULT_WAIT_POLL_INTERVAL_SECONDS: float = 0.3
# OCR / 候选列表相关的统一重试次数，来自全局设置，避免各处硬编码不同的数字。
DEFAULT_VERIFY_MAX_ATTEMPTS: int = int(getattr(settings, "REAL_EXEC_MAX_VERIFY_ATTEMPTS", 3) or 3)


@dataclass(frozen=True)
class ExecutionOptions:
    """统一的执行选项。

    - timeout_seconds: 超时时长（秒）。
    - retry_count: 重试次数（非负整数）。
    - working_directory: 工作目录（可为 None）。
    - environment: 进程环境变量字典（可为 None）。
    - stdout_encoding: 标准输出/错误的解码编码（用于 text/capture）。
    - log_prefix: 日志前缀（模块或调用方名）。
    """

    timeout_seconds: Optional[float] = None
    retry_count: int = 0
    working_directory: Optional[str] = None
    environment: Optional[dict[str, str]] = None
    stdout_encoding: str = "utf-8"
    log_prefix: Optional[str] = None


def sleep_seconds(seconds: float) -> None:
    """简单 sleep，单位秒。"""
    time.sleep(float(seconds))


def sleep_ui_settle() -> None:
    """统一的 UI 稳定等待（默认 0.5s）。"""
    sleep_seconds(0.5)


def sleep_mouse_up(duration_ms: int = DEFAULT_DRAG_MOUSE_UP_MS) -> None:
    """鼠标抬起后的统一等待（毫秒）。"""
    sleep_seconds(float(duration_ms) / 1000.0)


def compute_position_thresholds(scale: float) -> Tuple[int, int]:
    """根据缩放估算节点位置允许误差阈值 (posX, posY)。

    约定：以程序节点尺寸 200x100 为基准，取 60% 边长并设下限（横向≥120，纵向≥60）。
    """
    s = float(scale)
    pos_x_pixels = int(max(120.0, 0.6 * 200.0 * s))
    pos_y_pixels = int(max(60.0, 0.6 * 100.0 * s))
    return int(pos_x_pixels), int(pos_y_pixels)


def wait_until(
    predicate: Callable[[], bool],
    timeout_seconds: float,
    interval_seconds: float = 0.2,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> bool:
    """轮询等待直到谓词返回 True 或超时。

    使用单调时钟，避免系统时间变化影响。
    
    Args:
        predicate: 判定条件函数
        timeout_seconds: 超时时长（秒）
        interval_seconds: 轮询间隔（秒）
        pause_hook: 暂停钩子（每次轮询前调用）
        allow_continue: 终止检查钩子（返回False则立即终止）
        
    Returns:
        True 表示谓词成立，False 表示超时或被终止
    """
    start = time.monotonic()
    deadline = start + float(timeout_seconds)
    interval = float(interval_seconds)
    while True:
        if pause_hook is not None:
            pause_hook()
        if allow_continue is not None and not allow_continue():
            return False
        if predicate():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def ensure_foreground(window_title_hint: Optional[str]) -> bool:
    """将匹配给定标题提示的顶层窗口置为前景。

    仅在 Windows 上工作；若未找到窗口则返回 False。
    """
    if not window_title_hint:
        return False

    hwnd = find_window_handle(str(window_title_hint), case_sensitive=False)
    if int(hwnd) == 0:
        return False

    return bool(ctypes.windll.user32.SetForegroundWindow(int(hwnd)))


def to_screen_coordinates(point: Tuple[float, float], dpi_scale: float) -> Tuple[int, int]:
    """将逻辑坐标按 DPI 缩放为屏幕整数坐标。"""
    x, y = point
    sx = int(round(float(x) * float(dpi_scale)))
    sy = int(round(float(y) * float(dpi_scale)))
    return sx, sy


def inflate_rect(rect: Tuple[int, int, int, int], dx: int, dy: int) -> Tuple[int, int, int, int]:
    """按水平方向 dx、垂直方向 dy 放大矩形尺寸，中心不变。

    rect: (x, y, w, h)
    """
    x, y, w, h = rect
    nx = int(x - dx)
    ny = int(y - dy)
    nw = int(w + dx * 2)
    nh = int(h + dy * 2)
    return nx, ny, nw, nh


def _now_ms() -> int:
    return int(time.time() * 1000)


def safe_print(message: str) -> None:
    """统一日志输出门面：依赖 console_sanitizer 进行 ASCII 降级。"""
    ascii_safe_print(message, flush=True)


def log_start(module_and_function: str, **key_args) -> int:
    """打印统一开始日志并返回时间戳（毫秒）。"""
    parts = [f"{module_and_function} | start"]
    if key_args:
        kv = ", ".join(f"{k}={v}" for k, v in key_args.items())
        parts.append(kv)
    safe_print(" | ".join(parts))
    return _now_ms()


def log_ok(module_and_function: str, start_ms: int, **key_args) -> None:
    """打印统一成功日志。"""
    cost = _now_ms() - int(start_ms)
    parts = [f"{module_and_function} | ok", f"cost={cost}ms"]
    if key_args:
        kv = ", ".join(f"{k}={v}" for k, v in key_args.items())
        parts.append(kv)
    safe_print(" | ".join(parts))


def log_fail(module_and_function: str, start_ms: int, **key_args) -> None:
    """打印统一失败日志（不吞异常，调用方应直接抛出或返回错误）。"""
    cost = _now_ms() - int(start_ms)
    parts = [f"{module_and_function} | fail", f"cost={cost}ms"]
    if key_args:
        kv = ", ".join(f"{k}={v}" for k, v in key_args.items())
        parts.append(kv)
    safe_print(" | ".join(parts))


# === 全局可视化/日志汇聚（监控面板强制接入点） ===
# 目的：从源头统一拦截 OCR/模板匹配等识别动作，只要发生识别，就能将“带叠加标注的图片”与文本日志
#       推送到执行监控面板。运行期间由 UI 在开始监控时注册回调，在结束监控时清除回调。

_VISUAL_SINK: Optional[Callable[[object, Optional[object]], None]] = None
_LOG_SINK: Optional[Callable[[str], None]] = None


def set_visual_sink(callback: Callable[[object, Optional[object]], None]) -> None:
    """注册全局可视化接收器：签名与 monitor.update_visual(image, overlays) 一致。"""
    global _VISUAL_SINK
    _VISUAL_SINK = callback


def clear_visual_sink() -> None:
    """清空全局可视化接收器。"""
    global _VISUAL_SINK
    _VISUAL_SINK = None


def get_visual_sink() -> Optional[Callable[[object, Optional[object]], None]]:
    return _VISUAL_SINK


def set_log_sink(callback: Callable[[str], None]) -> None:
    """注册全局文本日志接收器（通常为 monitor.log）。"""
    global _LOG_SINK
    _LOG_SINK = callback


def clear_log_sink() -> None:
    global _LOG_SINK
    _LOG_SINK = None


def get_log_sink() -> Optional[Callable[[str], None]]:
    return _LOG_SINK


# === 可视化辅助工具 ===

def build_graph_region_overlay(current_image, region_name: str = "节点图布置区域") -> dict:
    """构建节点图区域叠加层（统一样式，避免重复）。
    
    Args:
        current_image: PIL Image 对象
        region_name: 区域名称，默认为"节点图布置区域"
        
    Returns:
        包含 rects 列表的字典，用于可视化叠加
        
    注意：
        需要在调用处导入 editor_capture，这里为避免循环依赖不在此直接导入
    """
    from app.automation import capture as editor_capture
    
    region_left, region_top, region_width, region_height = editor_capture.get_region_rect(
        current_image, region_name
    )
    return {
        'rects': [
            {
                'bbox': (int(region_left), int(region_top), int(region_width), int(region_height)),
                'color': (120, 180, 255),
                'label': region_name
            }
        ]
    }


