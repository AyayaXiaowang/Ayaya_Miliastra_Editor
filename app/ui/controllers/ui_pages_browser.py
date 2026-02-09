from __future__ import annotations

"""UI 页面转换编排（缓存派生 + 私有 Workbench 预览）。

目标体验（像节点图一样）：
- UI源码（HTML）是源文件；
- 进入 UI 相关页面时：
  - 自动扫描当前项目存档的 `管理配置/UI源码/*.html`
  - 若已注册 HTML->bundle 转换器：批量转换并将 bundle 写入运行时缓存（不落资源库）
  - 转换成功后，由用户显式选择是否打开“私有工具浏览器”（UI控件组预览页）。

说明：
- 私有预览页由 `private_extensions/千星沙箱网页处理工具/plugin.py` 提供服务端 `/api/ui_converter/*`，
  并通过 `ui_app_ui_preview.html` 拉取当前项目存档的 UI 资源进行预览（仅显示）。

约束：
- 不使用 try/except 吞错，失败直接抛出，便于定位问题；
- 本模块不直接弹窗，返回结构化结果由 UI 层决定如何提示用户。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
import sys
import os
import webbrowser
import json

from engine.utils.resource_library_layout import get_packages_root_dir
from engine.utils.cache.cache_paths import get_ui_html_bundle_cache_dir

from app.common.private_extension_registry import get_ui_html_bundle_converter
from app.ui.controllers.ui_html_bundle_importer import apply_ui_html_bundle_to_resource_manager, UiHtmlImportSummary
from app.ui.controllers.ui_html_debug_label_normalizer import normalize_ui_html_bundle_cli_flattened_outputs


@dataclass(frozen=True, slots=True)
class UiPagesConversionSummary:
    package_id: str
    ui_source_dir: Path
    html_count: int
    converted_count: int
    converter_enabled: bool
    warning_count: int
    warning_lines: tuple[str, ...]
    failed_count: int
    failure_lines: tuple[str, ...]


def _iter_html_files(ui_source_dir: Path) -> list[Path]:
    if not ui_source_dir.exists() or not ui_source_dir.is_dir():
        return []
    html_files = sorted(
        [
            p
            for p in ui_source_dir.rglob("*.html")
            if p.is_file() and (not p.name.endswith(".flattened.html"))
        ],
        key=lambda p: p.as_posix().casefold(),
    )
    return html_files


def convert_ui_pages_for_package(
    *,
    resource_manager: object,
    package_id: str,
    progress_callback: Callable[[str], None] | None = None,
) -> UiPagesConversionSummary:
    """批量转换当前项目存档的 UI源码/*.html，并将产物写入运行时缓存（不落资源库）。

    - progress_callback: 可选的进度回调（用于 UI 侧在页面内展示当前阶段/错误明细）。
      回调会在本函数所在线程中被调用（可能是后台线程），由调用方负责线程安全的 UI 更新策略。
    """
    package_id_text = str(package_id or "").strip()
    if not package_id_text or package_id_text in {"global_view", "unclassified_view"}:
        raise ValueError("package_id 无效，无法转换 UI页面")

    resource_library_dir = getattr(resource_manager, "resource_library_dir", None)
    if not isinstance(resource_library_dir, Path):
        raise RuntimeError("resource_manager.resource_library_dir 缺失或不是 Path")

    packages_root = get_packages_root_dir(resource_library_dir)
    package_root_dir = (packages_root / package_id_text).resolve()
    ui_source_dir = (package_root_dir / "管理配置" / "UI源码").resolve()

    html_files = _iter_html_files(ui_source_dir)

    converter = get_ui_html_bundle_converter()
    converter_enabled = converter is not None

    workspace_root = getattr(resource_manager, "workspace_path", None)
    if not isinstance(workspace_root, Path):
        raise RuntimeError("resource_manager.workspace_path 缺失或不是 Path")

    converted_summaries: dict[str, UiHtmlImportSummary] = {}
    failure_lines: list[str] = []
    warning_lines: list[str] = []

    if html_files and converter is None:
        # 设计变更：允许“仅 Web 手动刷新/导入”工作流，不再把未注册 converter 视为失败。
        warning_lines.append("未启用 HTML→UI bundle 自动转换：当前不会自动派生 UI布局/UI控件模板/UI页面。")
        warning_lines.append("请在主程序中打开「UI转换器 / UI控件组预览（Web）」后，在网页里手动导出并导入/刷新。")
        if progress_callback is not None:
            progress_callback("未启用 HTML→UI bundle 自动转换：当前不会自动派生 UI页面。")
            progress_callback("请打开「UI控件组预览（Web）」并在网页里手动导入/刷新。")

    if converter is not None:
        total = len(html_files)
        for idx, html_file in enumerate(html_files):
            relpath = html_file.relative_to(package_root_dir).as_posix()
            if progress_callback is not None:
                progress_callback(f"[{idx + 1}/{total}] 开始转换：{relpath}")

            # 若 UIPage 已记录源文件 mtime 且未变化：跳过（避免每次进入都重新生成）
            current_mtime = float(html_file.stat().st_mtime)
            existing_mtime = _try_get_existing_ui_bundle_source_mtime(
                resource_manager=resource_manager,
                package_id=package_id_text,
                source_html_relpath=relpath,
            )
            if existing_mtime is not None and abs(float(existing_mtime) - current_mtime) < 0.001:
                if progress_callback is not None:
                    progress_callback(f"[{idx + 1}/{total}] 跳过：{relpath}（未变更）")
                continue

            result = converter(workspace_root, package_id_text, html_file)
            if not isinstance(result, dict):
                failure_lines.append(f"- {relpath}: 转换器返回值不是 dict（无法解析）")
                if progress_callback is not None:
                    progress_callback(f"[{idx + 1}/{total}] 失败：{relpath}（转换器返回值不是 dict）")
                continue
            ok = bool(result.get("ok", False))
            if not ok:
                err = result.get("error", None)
                err_text = str(err) if err is not None else "未知错误（ok=False 且缺少 error 字段）"
                failure_lines.append(f"- {relpath}: 转换失败：{err_text}")
                if progress_callback is not None:
                    progress_callback(f"[{idx + 1}/{total}] 失败：{relpath}\n  - {err_text}")
                continue
            bundle = result.get("bundle", None)
            if not isinstance(bundle, dict):
                failure_lines.append(f"- {relpath}: 转换成功但缺少 bundle 或 bundle 不是对象")
                if progress_callback is not None:
                    progress_callback(f"[{idx + 1}/{total}] 失败：{relpath}（缺少 bundle 或 bundle 不是对象）")
                continue

            # 后处理：修复扁平化预览 HTML 内 `data-debug-label` 重复导致的“点击定位失效”。
            normalize_ui_html_bundle_cli_flattened_outputs(
                workspace_root=workspace_root,
                package_id=package_id_text,
                source_html_file=html_file,
            )

            warnings_value = result.get("warnings", [])
            warnings = warnings_value if isinstance(warnings_value, list) else []
            warning_text = "\n".join(str(x) for x in warnings if str(x).strip()) if warnings else ""
            if warning_text:
                warning_lines.append(f"- {relpath}: 警告（校验未通过，但已放行导入）：\n{warning_text}")
                if progress_callback is not None:
                    progress_callback(f"[{idx + 1}/{total}] 警告：{relpath}\n{warning_text}")

            layout_name = result.get("layout_name")
            layout_name_text = str(layout_name).strip() if isinstance(layout_name, str) else None
            summary = apply_ui_html_bundle_to_resource_manager(
                resource_manager=resource_manager,
                package_id=package_id_text,
                source_html_file=html_file,
                bundle_payload=bundle,
                layout_name=layout_name_text,
            )
            converted_summaries[summary.source_html_relpath] = summary
            if progress_callback is not None:
                progress_callback(
                    f"[{idx + 1}/{total}] 成功：{relpath}\n"
                    f"  - layout_id: {summary.layout_id}\n"
                    f"  - templates: {summary.template_count}  widgets: {summary.widget_count}"
                )

    return UiPagesConversionSummary(
        package_id=package_id_text,
        ui_source_dir=ui_source_dir,
        html_count=len(html_files),
        converted_count=len(converted_summaries),
        converter_enabled=bool(converter_enabled),
        warning_count=len(warning_lines),
        warning_lines=tuple(warning_lines),
        failed_count=len(failure_lines),
        failure_lines=tuple(failure_lines),
    )


def _try_get_existing_ui_bundle_source_mtime(
    *,
    resource_manager: object,
    package_id: str,
    source_html_relpath: str,
) -> float | None:
    """尝试从运行时缓存的 ui_bundle 中读取 __source_html_mtime，用于判断是否需要重新生成。"""

    rel = str(source_html_relpath or "").strip()
    if not rel:
        return None

    workspace_root = getattr(resource_manager, "workspace_path", None)
    if not isinstance(workspace_root, Path):
        return None

    cache_dir = get_ui_html_bundle_cache_dir(workspace_root, str(package_id or "").strip()).resolve()
    if not cache_dir.is_dir():
        return None

    for p in sorted([x for x in cache_dir.glob("*.ui_bundle.json") if x.is_file()], key=lambda x: x.as_posix().casefold()):
        payload = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        if str(payload.get("source_html") or "").strip() != rel:
            continue
        extra_value = payload.get("extra", {})
        extra = extra_value if isinstance(extra_value, dict) else {}
        mtime_value = extra.get("__source_html_mtime")
        if isinstance(mtime_value, (int, float)):
            return float(mtime_value)
    return None


def open_private_ui_preview_browser_or_raise() -> None:
    """打开私有“UI控件组预览（Web）”页面（由私有扩展提供服务端）。"""
    module_name = "private_extensions.千星沙箱网页处理工具"
    module = sys.modules.get(module_name)
    if module is None:
        raise RuntimeError("未加载私有扩展：千星沙箱网页处理工具。")
    bridge = getattr(module, "_BRIDGE", None)
    if bridge is None:
        raise RuntimeError("私有扩展已加载，但 _BRIDGE 尚未初始化（主窗口 hook 未运行？）")
    open_preview = getattr(bridge, "open_ui_preview_in_browser", None)
    if not callable(open_preview):
        raise RuntimeError("私有扩展 _BRIDGE 缺少 open_ui_preview_in_browser()，无法打开预览页")
    open_preview()


def open_private_ui_workbench_browser_or_raise() -> None:
    """打开私有 Web 页面入口（WorkBench 已下线，统一导向预览页）。"""
    module_name = "private_extensions.千星沙箱网页处理工具"
    module = sys.modules.get(module_name)
    if module is None:
        raise RuntimeError("未加载私有扩展：千星沙箱网页处理工具。")
    bridge = getattr(module, "_BRIDGE", None)
    if bridge is None:
        raise RuntimeError("私有扩展已加载，但 _BRIDGE 尚未初始化（主窗口 hook 未运行？）")
    open_preview = getattr(bridge, "open_ui_preview_in_browser", None)
    if not callable(open_preview):
        raise RuntimeError("私有扩展 _BRIDGE 缺少 open_ui_preview_in_browser()，无法打开预览页")
    open_preview()


def _open_url_or_raise(*, url: str, purpose: str) -> None:
    """打开 URL（Windows 下避免 webbrowser 静默失败）。"""
    url_text = str(url or "").strip()
    purpose_text = str(purpose or "").strip() or "open_url"
    if not url_text:
        raise ValueError(f"URL 为空，无法打开：purpose={purpose_text}")

    opened = webbrowser.open(url_text, new=2)
    if opened:
        return

    # 兼容：webbrowser.open 在部分 Windows 环境会返回 False 且无异常
    if hasattr(os, "startfile"):
        os.startfile(url_text)  # type: ignore[attr-defined]
        return
    raise RuntimeError(f"webbrowser.open returned False and os.startfile unavailable: {url_text}")


def _get_builtin_workbench_dir_or_raise(*, workspace_root: Path) -> Path:
    workbench_dir = (workspace_root / "assets" / "ui_workbench").resolve()
    if not workbench_dir.is_dir():
        raise RuntimeError(f"内置 UI Workbench 静态目录不存在：{workbench_dir}")
    preview_html = workbench_dir / "ui_app_ui_preview.html"
    if not preview_html.is_file():
        raise RuntimeError(f"内置 UI 预览页面缺失：{preview_html}")
    return workbench_dir


def _get_or_create_builtin_ui_workbench_bridge(*, main_window: object) -> object:
    """获取/创建内置 UiWorkbenchBridge（挂到 main_window 上复用）。"""
    from app.ui.ui_workbench_bridge import UiWorkbenchBridge

    existing = getattr(main_window, "_builtin_ui_workbench_bridge", None)
    if isinstance(existing, UiWorkbenchBridge):
        return existing

    package_controller = getattr(main_window, "package_controller", None)
    if package_controller is None:
        raise RuntimeError("主窗口缺少 package_controller，无法打开 UI 预览页")
    resource_manager = getattr(package_controller, "resource_manager", None)
    if resource_manager is None:
        raise RuntimeError("package_controller 缺少 resource_manager，无法打开 UI 预览页")
    workspace_root = getattr(resource_manager, "workspace_path", None)
    if not isinstance(workspace_root, Path):
        raise RuntimeError("resource_manager.workspace_path 缺失或不是 Path")

    workbench_dir = _get_builtin_workbench_dir_or_raise(workspace_root=workspace_root)
    bridge = UiWorkbenchBridge(workspace_root=workspace_root, workbench_dir=workbench_dir)
    bridge.attach_main_window(main_window)
    setattr(main_window, "_builtin_ui_workbench_bridge", bridge)
    return bridge


def open_ui_preview_browser_or_raise(*, main_window: object) -> None:
    """打开 UI控件组预览页（优先私有扩展，否则使用内置 Workbench）。"""
    module = sys.modules.get("private_extensions.千星沙箱网页处理工具")
    if module is not None:
        bridge = getattr(module, "_BRIDGE", None)
        open_preview = getattr(bridge, "open_ui_preview_in_browser", None) if bridge is not None else None
        if callable(open_preview):
            open_preview()
            return

    bridge_any = _get_or_create_builtin_ui_workbench_bridge(main_window=main_window)
    url = getattr(bridge_any, "get_ui_preview_url")()
    _open_url_or_raise(url=str(url), purpose="ui_preview")


def open_ui_workbench_browser_or_raise(*, main_window: object) -> None:
    """打开 Web 页面入口（Workbench 已下线，统一导向预览页）。"""
    module = sys.modules.get("private_extensions.千星沙箱网页处理工具")
    if module is not None:
        bridge = getattr(module, "_BRIDGE", None)
        open_preview = getattr(bridge, "open_ui_preview_in_browser", None) if bridge is not None else None
        if callable(open_preview):
            open_preview()
            return

    bridge_any = _get_or_create_builtin_ui_workbench_bridge(main_window=main_window)
    url = getattr(bridge_any, "get_workbench_url")()
    _open_url_or_raise(url=str(url), purpose="ui_preview")


__all__ = [
    "convert_ui_pages_for_package",
    "open_private_ui_preview_browser_or_raise",
    "open_private_ui_workbench_browser_or_raise",
    "open_ui_preview_browser_or_raise",
    "open_ui_workbench_browser_or_raise",
    "UiPagesConversionSummary",
]

