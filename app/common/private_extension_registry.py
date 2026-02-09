from __future__ import annotations

"""私有扩展注册表（公开仓库只提供扩展点，私有实现不入库）。

定位：
- 本模块只提供“注册/触发”机制，不负责加载私有代码；
- 私有代码应通过 `app.common.private_extension_loader` 动态导入后，在导入时/安装时调用本模块注册钩子。

约束：
- 保持纯 Python、无 PyQt 依赖（参数类型用 object/Path 表示），避免引入启动顺序问题。
"""

from pathlib import Path
from typing import Callable, List, Optional, Protocol, Any

from engine.utils.logging.logger import log_info

BootstrapHook = Callable[[Path], None]
MainWindowHook = Callable[[object], None]

_bootstrap_hooks: List[BootstrapHook] = []
_main_window_hooks: List[MainWindowHook] = []


class UiHtmlBundleConverter(Protocol):
    """HTML -> UI bundle 转换器（由私有扩展实现并注册）。

    设计目标：
    - 主程序只提供“自动转换的触发点 + 导入落盘链路”，不内置私有转换实现；
    - 私有扩展可以用任意方式实现转换（浏览器端/外部进程/自研解析器），只要满足该协议；
    - 为满足“稍微有点报错也没关系，能转化就行”，建议转换器将可恢复问题写入 warnings，
      而不是抛异常（异常用于不可恢复的硬失败）。

    返回值约定（dict）：
    - ok: bool
    - bundle: dict | None   # Workbench 风格的 {layout, templates} bundle
    - layout_name: str | None
    - warnings: list[str]   # 可选
    - error: str | None     # ok=False 时可选
    """

    def __call__(self, workspace_root: Path, package_id: str, html_file: Path) -> dict: ...


_ui_html_bundle_converter: Optional[UiHtmlBundleConverter] = None

# UI Web 工具插件（私有扩展）启用标记：
# - 与“是否注册 HTML->bundle 自动转换器”解耦
# - 用于 UI 侧门禁（展示 UI 相关分类、打开 Web 预览入口等）
_ui_tools_plugin_enabled: bool = False


def register_bootstrap_hook(hook: BootstrapHook) -> BootstrapHook:
    """注册启动期钩子：在 UI QApplication 创建前执行（OCR 已预热）。"""
    _bootstrap_hooks.append(hook)
    return hook


def register_main_window_hook(hook: MainWindowHook) -> MainWindowHook:
    """注册主窗口钩子：在主窗口创建后、show() 前执行。"""
    _main_window_hooks.append(hook)
    return hook


def register_ui_html_bundle_converter(converter: UiHtmlBundleConverter) -> UiHtmlBundleConverter:
    """注册 UI HTML 自动转换器（私有扩展使用）。

    约定：同一进程仅允许注册一个转换器；重复注册会覆盖旧值（后注册者生效）。
    """
    global _ui_html_bundle_converter
    _ui_html_bundle_converter = converter
    return converter


def get_ui_html_bundle_converter() -> Optional[UiHtmlBundleConverter]:
    """获取已注册的 UI HTML 自动转换器（未注册则返回 None）。"""
    return _ui_html_bundle_converter


def register_ui_tools_plugin_enabled() -> None:
    """标记：私有 UI Web 工具插件已启用。

    设计目的：
    - UI 侧“是否展示 UI 相关分类/入口”的门禁不应依赖 Playwright/自动转换能力；
    - 插件仍可只提供 Web 预览/手动导入导出，而不注册自动转换器。
    """
    global _ui_tools_plugin_enabled
    _ui_tools_plugin_enabled = True


def is_ui_tools_plugin_enabled() -> bool:
    """是否启用了私有 UI Web 工具插件（与自动转换器注册解耦）。"""
    return bool(_ui_tools_plugin_enabled)


def run_bootstrap_hooks(*, workspace_root: Path) -> None:
    hooks = list(_bootstrap_hooks)
    if not hooks:
        return
    log_info("[EXT] 执行私有启动钩子: count={}", len(hooks))
    for hook in hooks:
        hook(workspace_root)


def run_main_window_hooks(*, main_window: object) -> None:
    hooks = list(_main_window_hooks)
    if not hooks:
        return
    log_info("[EXT] 执行私有主窗口钩子: count={}", len(hooks))
    for hook in hooks:
        hook(main_window)


