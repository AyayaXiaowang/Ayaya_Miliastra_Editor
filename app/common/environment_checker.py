"""运行环境检查（纯 Python，无 PyQt 依赖）。

目标：
- 给 UI 提供一个“一键环境自检”的信息源；
- 聚焦自动化执行链路最常见的环境问题：显示器分辨率/缩放、千星沙箱窗口是否打开、管理员权限是否匹配。

约定：
- 不使用 try/except；若底层 WinAPI 缺失或调用失败，直接让错误暴露或在报告中标记为未知。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
import ctypes
from ctypes import wintypes
import sys

from app.automation.input.window_finder import find_window_handle


_SUPPORTED_RESOLUTIONS: tuple[tuple[int, int], ...] = (
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
)
_SUPPORTED_SCALE_PERCENTS: tuple[int, ...] = (100, 125)


@dataclass(frozen=True, slots=True)
class MonitorDiagnostics:
    device_name: str
    is_primary: bool
    width_px: int
    height_px: int
    dpi_x: int | None
    dpi_y: int | None
    scale_percent: int | None

    @property
    def is_supported_resolution(self) -> bool:
        return (int(self.width_px), int(self.height_px)) in _SUPPORTED_RESOLUTIONS

    @property
    def is_supported_scale(self) -> bool:
        if self.scale_percent is None:
            return False
        return int(self.scale_percent) in _SUPPORTED_SCALE_PERCENTS

    @property
    def is_supported_combo(self) -> bool:
        return self.is_supported_resolution and self.is_supported_scale


@dataclass(frozen=True, slots=True)
class SandboxDiagnostics:
    hwnd: int
    title: str
    process_id: int | None
    is_elevated: bool | None
    monitor_device_name: str | None


@dataclass(frozen=True, slots=True)
class EnvironmentDiagnosticsReport:
    generated_at: datetime
    app_display_name: str
    app_version: str
    python_version: str
    is_running_as_admin: bool
    sandbox: SandboxDiagnostics | None
    monitors: tuple[MonitorDiagnostics, ...]

    def to_text(self) -> str:
        lines: list[str] = []
        lines.append(f"环境检查（生成时间：{self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}）")
        lines.append("")
        lines.append(f"- 程序：{self.app_display_name}（版本：{self.app_version}）")
        lines.append(f"- Python：{self.python_version}")
        lines.append(f"- 管理员权限（本程序）：{'是' if self.is_running_as_admin else '否'}")
        lines.append("")

        if self.sandbox is None:
            lines.append("- 千星沙箱：未检测到窗口（请先打开“千星沙箱”，再点击检查）")
        else:
            lines.append("- 千星沙箱：已检测到")
            if self.sandbox.title:
                lines.append(f"  - 窗口标题：{self.sandbox.title}")
            if self.sandbox.process_id is not None:
                lines.append(f"  - 进程 PID：{self.sandbox.process_id}")
            if self.sandbox.is_elevated is None:
                lines.append("  - 管理员权限（沙箱进程）：未知（无法读取进程权限信息）")
            else:
                lines.append(f"  - 管理员权限（沙箱进程）：{'是' if self.sandbox.is_elevated else '否'}")
            if self.sandbox.monitor_device_name:
                lines.append(f"  - 所在屏幕：{self.sandbox.monitor_device_name}")
            lines.append("")

        if self.monitors:
            lines.append("显示器检测：")
            for monitor in self.monitors:
                primary_mark = "（主屏）" if monitor.is_primary else ""
                scale_text = "未知"
                if monitor.scale_percent is not None:
                    dpi_suffix = f"（DPI={monitor.dpi_x}）" if monitor.dpi_x is not None else ""
                    scale_text = f"{monitor.scale_percent}%{dpi_suffix}"
                support_mark = "✅" if monitor.is_supported_combo else "❌"
                sandbox_mark = ""
                if self.sandbox is not None and self.sandbox.monitor_device_name == monitor.device_name:
                    sandbox_mark = " [沙箱所在屏幕]"
                lines.append(
                    f"- {monitor.device_name}{primary_mark}: {monitor.width_px}×{monitor.height_px}, 缩放={scale_text} {support_mark}{sandbox_mark}"
                )
            lines.append("")

        lines.append("支持范围（来自 README）：")
        lines.append("- 分辨率：1920×1080 / 2560×1440 / 3840×2160")
        lines.append("- 缩放：100% / 125%")
        lines.append("")

        conclusion_ok, conclusion_reason = _evaluate_conclusion(
            is_running_as_admin=self.is_running_as_admin,
            sandbox=self.sandbox,
            monitors=self.monitors,
        )
        lines.append(f"结论：{'通过' if conclusion_ok else '不通过'}")
        if conclusion_reason:
            lines.append(conclusion_reason)
        return "\n".join(lines)


def build_environment_diagnostics_report(
    *,
    app_display_name: str,
    app_version: str,
    sandbox_window_title: str = "千星沙箱",
) -> EnvironmentDiagnosticsReport:
    """构建一份完整的环境诊断报告（可用于 UI 展示）。"""
    sandbox_hwnd = int(find_window_handle(str(sandbox_window_title or "").strip(), case_sensitive=False))
    sandbox: SandboxDiagnostics | None = None
    if sandbox_hwnd != 0:
        sandbox_title = _get_window_title(sandbox_hwnd)
        sandbox_pid = _get_window_process_id(sandbox_hwnd)
        sandbox_is_elevated: bool | None = None
        if sandbox_pid is not None:
            sandbox_is_elevated = _is_process_elevated(sandbox_pid)
        sandbox_monitor = _get_monitor_device_name_for_window(sandbox_hwnd)
        sandbox = SandboxDiagnostics(
            hwnd=sandbox_hwnd,
            title=sandbox_title,
            process_id=sandbox_pid,
            is_elevated=sandbox_is_elevated,
            monitor_device_name=sandbox_monitor,
        )

    return EnvironmentDiagnosticsReport(
        generated_at=datetime.now(),
        app_display_name=str(app_display_name),
        app_version=str(app_version),
        python_version=_format_python_version(),
        is_running_as_admin=_is_running_as_admin(),
        sandbox=sandbox,
        monitors=tuple(_enumerate_monitors()),
    )


def _format_python_version() -> str:
    version = ".".join(str(part) for part in sys.version_info[:3])
    return f"{version} ({sys.platform})"


def _is_running_as_admin() -> bool:
    if sys.platform != "win32":
        return False
    shell32 = ctypes.windll.shell32
    shell32.IsUserAnAdmin.argtypes = []
    shell32.IsUserAnAdmin.restype = wintypes.BOOL
    return bool(shell32.IsUserAnAdmin())


def _get_window_title(hwnd: int) -> str:
    if sys.platform != "win32":
        return ""
    user32 = ctypes.windll.user32
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int

    length = int(user32.GetWindowTextLengthW(wintypes.HWND(int(hwnd))))
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(wintypes.HWND(int(hwnd)), buffer, int(length) + 1)
    return str(buffer.value or "").strip()


def _get_window_process_id(hwnd: int) -> int | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    process_id = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(wintypes.HWND(int(hwnd)), ctypes.byref(process_id))
    if int(process_id.value) <= 0:
        return None
    return int(process_id.value)


def _is_process_elevated(process_id: int) -> bool | None:
    """返回目标进程是否提升（管理员）运行；无法读取时返回 None。"""
    if sys.platform != "win32":
        return None
    pid = int(process_id)
    if pid <= 0:
        return None

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    TOKEN_QUERY = 0x0008
    TOKEN_ELEVATION_CLASS = 20  # TokenElevation

    class TOKEN_ELEVATION(ctypes.Structure):
        _fields_ = [("TokenIsElevated", wintypes.DWORD)]

    kernel32 = ctypes.windll.kernel32
    advapi32 = ctypes.windll.advapi32

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL

    process_handle = kernel32.OpenProcess(
        wintypes.DWORD(PROCESS_QUERY_LIMITED_INFORMATION),
        wintypes.BOOL(False),
        wintypes.DWORD(pid),
    )
    if not process_handle:
        return None

    token_handle = wintypes.HANDLE(0)
    opened = advapi32.OpenProcessToken(
        process_handle,
        wintypes.DWORD(TOKEN_QUERY),
        ctypes.byref(token_handle),
    )
    if not opened:
        kernel32.CloseHandle(process_handle)
        return None

    elevation = TOKEN_ELEVATION()
    returned_size = wintypes.DWORD(0)
    ok = advapi32.GetTokenInformation(
        token_handle,
        wintypes.DWORD(TOKEN_ELEVATION_CLASS),
        ctypes.byref(elevation),
        wintypes.DWORD(ctypes.sizeof(elevation)),
        ctypes.byref(returned_size),
    )

    kernel32.CloseHandle(token_handle)
    kernel32.CloseHandle(process_handle)
    if not ok:
        return None
    return bool(int(elevation.TokenIsElevated) != 0)


def _get_monitor_device_name_for_window(hwnd: int) -> str | None:
    if sys.platform != "win32":
        return None
    monitor_info = _get_monitor_info_for_window(hwnd)
    if monitor_info is None:
        return None
    return monitor_info.device_name


@dataclass(frozen=True, slots=True)
class _MonitorInfo:
    device_name: str
    is_primary: bool
    monitor_rect: tuple[int, int, int, int]


def _get_monitor_info_for_window(hwnd: int) -> _MonitorInfo | None:
    if sys.platform != "win32":
        return None

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    MONITOR_DEFAULTTONEAREST = 2
    MONITORINFOF_PRIMARY = 1

    user32 = ctypes.windll.user32
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    hmonitor = user32.MonitorFromWindow(wintypes.HWND(int(hwnd)), wintypes.DWORD(MONITOR_DEFAULTTONEAREST))
    if not hmonitor:
        return None

    info = MONITORINFOEXW()
    info.cbSize = wintypes.DWORD(ctypes.sizeof(MONITORINFOEXW))
    ok = user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
    if not ok:
        return None

    device_name = str(info.szDevice).strip()
    rect = info.rcMonitor
    monitor_rect = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
    is_primary = bool(int(info.dwFlags) & int(MONITORINFOF_PRIMARY))
    return _MonitorInfo(device_name=device_name, is_primary=is_primary, monitor_rect=monitor_rect)


def _enumerate_monitors() -> Iterable[MonitorDiagnostics]:
    """枚举当前系统所有显示器并返回诊断信息（Windows only）。"""
    if sys.platform != "win32":
        return ()

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        ]

    MONITORINFOF_PRIMARY = 1

    user32 = ctypes.windll.user32
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(RECT),
        ctypes.c_void_p,
        wintypes.LPARAM,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL

    monitors: list[wintypes.HMONITOR] = []

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    @MONITORENUMPROC
    def _enum_proc(hmonitor: wintypes.HMONITOR, _hdc: wintypes.HDC, _rect: ctypes.POINTER(RECT), _lparam: wintypes.LPARAM):
        monitors.append(hmonitor)
        return True

    user32.EnumDisplayMonitors(wintypes.HDC(0), None, _enum_proc, wintypes.LPARAM(0))

    for hmonitor in monitors:
        info = MONITORINFOEXW()
        info.cbSize = wintypes.DWORD(ctypes.sizeof(MONITORINFOEXW))
        ok = user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        if not ok:
            continue

        device_name = str(info.szDevice).strip()
        is_primary = bool(int(info.dwFlags) & int(MONITORINFOF_PRIMARY))

        width_px, height_px = _get_display_resolution(device_name)
        dpi_x, dpi_y = _get_monitor_dpi(hmonitor)
        scale_percent = _dpi_to_scale_percent(dpi_x)

        yield MonitorDiagnostics(
            device_name=device_name,
            is_primary=is_primary,
            width_px=width_px,
            height_px=height_px,
            dpi_x=dpi_x,
            dpi_y=dpi_y,
            scale_percent=scale_percent,
        )


def _get_display_resolution(device_name: str) -> tuple[int, int]:
    """返回指定 display device 的当前分辨率（物理像素）。"""
    CCHDEVICENAME = 32
    CCHFORMNAME = 32

    class DEVMODEW(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", wintypes.WCHAR * CCHDEVICENAME),
            ("dmSpecVersion", wintypes.WORD),
            ("dmDriverVersion", wintypes.WORD),
            ("dmSize", wintypes.WORD),
            ("dmDriverExtra", wintypes.WORD),
            ("dmFields", wintypes.DWORD),
            ("dmOrientation", wintypes.SHORT),
            ("dmPaperSize", wintypes.SHORT),
            ("dmPaperLength", wintypes.SHORT),
            ("dmPaperWidth", wintypes.SHORT),
            ("dmScale", wintypes.SHORT),
            ("dmCopies", wintypes.SHORT),
            ("dmDefaultSource", wintypes.SHORT),
            ("dmPrintQuality", wintypes.SHORT),
            ("dmColor", wintypes.SHORT),
            ("dmDuplex", wintypes.SHORT),
            ("dmYResolution", wintypes.SHORT),
            ("dmTTOption", wintypes.SHORT),
            ("dmCollate", wintypes.SHORT),
            ("dmFormName", wintypes.WCHAR * CCHFORMNAME),
            ("dmLogPixels", wintypes.WORD),
            ("dmBitsPerPel", wintypes.DWORD),
            ("dmPelsWidth", wintypes.DWORD),
            ("dmPelsHeight", wintypes.DWORD),
            ("dmDisplayFlags", wintypes.DWORD),
            ("dmDisplayFrequency", wintypes.DWORD),
            ("dmICMMethod", wintypes.DWORD),
            ("dmICMIntent", wintypes.DWORD),
            ("dmMediaType", wintypes.DWORD),
            ("dmDitherType", wintypes.DWORD),
            ("dmReserved1", wintypes.DWORD),
            ("dmReserved2", wintypes.DWORD),
            ("dmPanningWidth", wintypes.DWORD),
            ("dmPanningHeight", wintypes.DWORD),
        ]

    ENUM_CURRENT_SETTINGS = 0xFFFFFFFF

    user32 = ctypes.windll.user32
    user32.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DEVMODEW)]
    user32.EnumDisplaySettingsW.restype = wintypes.BOOL

    devmode = DEVMODEW()
    devmode.dmSize = wintypes.WORD(ctypes.sizeof(DEVMODEW))
    ok = user32.EnumDisplaySettingsW(str(device_name), wintypes.DWORD(ENUM_CURRENT_SETTINGS), ctypes.byref(devmode))
    if not ok:
        # 若读取失败，回退为 0，交给上层展示（比抛异常更适合诊断报告）。
        return 0, 0

    return int(devmode.dmPelsWidth), int(devmode.dmPelsHeight)


def _get_monitor_dpi(hmonitor: wintypes.HMONITOR) -> tuple[int | None, int | None]:
    """返回指定 monitor 的 DPI（优先 effective DPI）。"""
    shcore = getattr(ctypes.windll, "shcore", None)
    if shcore is None:
        return None, None

    get_dpi_for_monitor = getattr(shcore, "GetDpiForMonitor", None)
    if get_dpi_for_monitor is None:
        return None, None

    MDT_EFFECTIVE_DPI = 0
    get_dpi_for_monitor.argtypes = [
        wintypes.HMONITOR,
        ctypes.c_int,
        ctypes.POINTER(wintypes.UINT),
        ctypes.POINTER(wintypes.UINT),
    ]
    get_dpi_for_monitor.restype = ctypes.c_int

    dpi_x = wintypes.UINT(0)
    dpi_y = wintypes.UINT(0)
    hr = int(get_dpi_for_monitor(hmonitor, int(MDT_EFFECTIVE_DPI), ctypes.byref(dpi_x), ctypes.byref(dpi_y)))
    if hr != 0:
        return None, None
    return int(dpi_x.value), int(dpi_y.value)


def _dpi_to_scale_percent(dpi_x: int | None) -> int | None:
    if dpi_x is None:
        return None
    if int(dpi_x) <= 0:
        return None
    return int(round((float(dpi_x) / 96.0) * 100.0))


def _evaluate_conclusion(
    *,
    is_running_as_admin: bool,
    sandbox: SandboxDiagnostics | None,
    monitors: tuple[MonitorDiagnostics, ...],
) -> tuple[bool, str]:
    """返回（是否通过，原因说明）。"""
    if sandbox is None:
        return False, "原因：未检测到“千星沙箱”窗口。"

    if sandbox.monitor_device_name:
        target = next(
            (m for m in monitors if m.device_name == sandbox.monitor_device_name),
            None,
        )
        if target is None:
            return False, "原因：已检测到沙箱窗口，但无法解析其所在显示器信息。"
        if not target.is_supported_combo:
            return (
                False,
                f"原因：沙箱所在屏幕配置不在支持范围（当前 {target.width_px}×{target.height_px}，缩放 {target.scale_percent}%）。",
            )

    if sandbox.is_elevated is True and not is_running_as_admin:
        return (
            False,
            "原因：千星沙箱以管理员权限运行，但本程序未以管理员权限运行（将无法向沙箱注入键鼠操作）。",
        )

    return True, ""


__all__ = [
    "EnvironmentDiagnosticsReport",
    "MonitorDiagnostics",
    "SandboxDiagnostics",
    "build_environment_diagnostics_report",
]


