from __future__ import annotations

"""UI HTML 自动转换协调器（监听 UI源码 目录变化 -> 调用私有扩展转换 -> 写入运行时缓存）。

定位：
- 触发源：QFileSystemWatcher.directoryChanged（资源库目录事件）
- 监听范围：仅当前项目存档的 `管理配置/UI源码/` 子树
- 转换实现：必须由私有扩展通过 `app.common.private_extension_registry.register_ui_html_bundle_converter(...)` 注册
- 落盘：写入运行时缓存（`app/runtime/cache/ui_artifacts/...`），不写入资源库

约束：
- 不引入私有实现；不使用 try/except 吞错。
"""

import time
import stat as stat_module
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt6 import QtCore

from engine.utils.logging.logger import log_debug, log_warn
from engine.utils.path_utils import normalize_slash
from engine.utils.resource_library_layout import get_packages_root_dir

from app.common.private_extension_registry import get_ui_html_bundle_converter
from app.ui.controllers.ui_html_bundle_importer import apply_ui_html_bundle_to_current_package
from app.ui.controllers.ui_html_debug_label_normalizer import normalize_ui_html_bundle_cli_flattened_outputs


@dataclass(slots=True)
class _HtmlFileState:
    last_seen_mtime: float = 0.0
    last_imported_mtime: float = 0.0


class UiHtmlAutoConvertCoordinator(QtCore.QObject):
    def __init__(
        self,
        *,
        resource_manager: object,
        main_window_provider: Callable[[], object | None],
        emit_toast: Callable[[str, str], None] | None = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._resource_manager = resource_manager
        self._main_window_provider = main_window_provider
        self._emit_toast = emit_toast

        self._active_package_id: str | None = None
        self._debounce_timer: QtCore.QTimer | None = None
        self._pending_trigger_dir: Path | None = None
        self._trigger_seq: int = 0

        # HTML mtime 缓存：避免在目录事件风暴下重复转换同一文件
        self._html_state: dict[str, _HtmlFileState] = {}
        # UI源码 目录缓存：notify_directory_changed 是高频入口，避免频繁 resolve 与目录拼装。
        self._ui_source_dir_cache_package_id: str | None = None
        self._ui_source_dir_cache_dir: Path | None = None
        self._ui_source_dir_cache_text: str | None = None

    def set_active_package_id(self, package_id: str | None) -> None:
        normalized = str(package_id or "").strip() or None
        if normalized in {"global_view", "unclassified_view"}:
            normalized = None
        if normalized != self._active_package_id:
            self._ui_source_dir_cache_package_id = None
            self._ui_source_dir_cache_dir = None
            self._ui_source_dir_cache_text = None
        self._active_package_id = normalized

    def notify_directory_changed(self, changed_dir: Path) -> None:
        """入口：由 FileWatcherManager 在 directoryChanged 事件中调用。"""
        active_package_id = str(self._active_package_id or "").strip()
        if not active_package_id:
            return

        ui_source_dir = self._get_ui_source_dir_cached(active_package_id)
        if ui_source_dir is None:
            return

        # 仅关心 UI源码 子树（性能：避免 Path.resolve() 触发文件系统 IO）
        ui_source_text = str(self._ui_source_dir_cache_text or "")
        if ui_source_text == "":
            return
        changed_text = self._normalize_path_text(changed_dir)
        if changed_text != ui_source_text and (not changed_text.startswith(ui_source_text + "/")):
            return

        converter = get_ui_html_bundle_converter()
        if converter is None:
            return

        self._pending_trigger_dir = Path(changed_dir)
        self._trigger_seq += 1
        self._schedule_debounced_convert()

    def _schedule_debounced_convert(self) -> None:
        timer = self._ensure_debounce_timer()
        timer.stop()
        # HTML 保存经常是“多次写入 + rename 覆盖”，用稍长去抖合并一轮
        timer.start(600)

    def _ensure_debounce_timer(self) -> QtCore.QTimer:
        if self._debounce_timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_debounce_fired)
            self._debounce_timer = timer
        return self._debounce_timer

    def _on_debounce_fired(self) -> None:
        active_package_id = str(self._active_package_id or "").strip()
        if not active_package_id:
            return

        converter = get_ui_html_bundle_converter()
        if converter is None:
            return

        ui_source_dir = self._get_ui_source_dir(active_package_id)
        if ui_source_dir is None or (not ui_source_dir.exists()):
            return

        main_window = self._main_window_provider()
        package_controller = getattr(main_window, "package_controller", None) if main_window is not None else None
        if package_controller is None:
            return
        file_watcher_manager = getattr(main_window, "file_watcher_manager", None) if main_window is not None else None
        _ = file_watcher_manager

        workspace_root = Path(getattr(self._resource_manager, "workspace_path")).resolve()

        html_files = sorted(
            [p for p in ui_source_dir.rglob("*.html")],
            key=lambda p: p.as_posix().casefold(),
        )
        if not html_files:
            return

        converted_any = False
        for html_file in html_files:
            st = html_file.stat()
            if not stat_module.S_ISREG(int(st.st_mode)):
                continue
            mtime = float(st.st_mtime)
            state = self._html_state.get(str(html_file))
            if state is None:
                state = _HtmlFileState()
                self._html_state[str(html_file)] = state
            state.last_seen_mtime = mtime

            # mtime 未变化且已成功导入过：跳过
            if state.last_imported_mtime > 0.0 and abs(state.last_imported_mtime - mtime) < 0.001:
                continue

            # 私有扩展转换：约定返回 dict（允许 warnings，ok=True 视为可导入）
            result = converter(workspace_root, active_package_id, html_file)
            if not isinstance(result, dict):
                continue
            ok = bool(result.get("ok", False))
            bundle = result.get("bundle", None)
            if not ok or not isinstance(bundle, dict):
                continue

            # 后处理：修复扁平化预览 HTML 内 `data-debug-label` 重复导致的“点了没反应/无法定位”问题。
            normalize_ui_html_bundle_cli_flattened_outputs(
                workspace_root=workspace_root,
                package_id=active_package_id,
                source_html_file=html_file,
            )

            layout_name = result.get("layout_name")
            layout_name_text = str(layout_name).strip() if isinstance(layout_name, str) else None

            summary = apply_ui_html_bundle_to_current_package(
                package_controller=package_controller,
                source_html_file=html_file,
                bundle_payload=bundle,
                layout_name=layout_name_text,
            )
            state.last_imported_mtime = mtime
            converted_any = True

            log_warn(
                "[UI-HTML] 自动转换完成：package_id={}, html={}, layout_id={}, templates={}, widgets={}",
                active_package_id,
                str(html_file),
                str(summary.layout_id),
                int(summary.template_count),
                int(summary.widget_count),
            )

        if converted_any and self._emit_toast is not None:
            self._emit_toast("HTML UI 已自动转换并写入运行时缓存（不落资源库）", "info")

    def _get_ui_source_dir(self, package_id: str) -> Path | None:
        resource_library_dir = Path(getattr(self._resource_manager, "resource_library_dir")).resolve()
        packages_root = get_packages_root_dir(resource_library_dir)
        package_root_dir = (packages_root / str(package_id)).resolve()
        # 约定：UI 源码放在 管理配置/UI源码
        return (package_root_dir / "管理配置" / "UI源码").resolve()

    def _get_ui_source_dir_cached(self, package_id: str) -> Path | None:
        normalized = str(package_id or "").strip() or None
        if not normalized:
            return None
        if normalized == self._ui_source_dir_cache_package_id and self._ui_source_dir_cache_dir is not None:
            return self._ui_source_dir_cache_dir

        ui_source_dir = self._get_ui_source_dir(normalized)
        if ui_source_dir is None:
            self._ui_source_dir_cache_package_id = normalized
            self._ui_source_dir_cache_dir = None
            self._ui_source_dir_cache_text = None
            return None

        self._ui_source_dir_cache_package_id = normalized
        self._ui_source_dir_cache_dir = ui_source_dir
        self._ui_source_dir_cache_text = self._normalize_path_text(ui_source_dir)
        return ui_source_dir

    @staticmethod
    def _normalize_path_text(path: Path) -> str:
        return normalize_slash(str(path)).rstrip("/").casefold()

