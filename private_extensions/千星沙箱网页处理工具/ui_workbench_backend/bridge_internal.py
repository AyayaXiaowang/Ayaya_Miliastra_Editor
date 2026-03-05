from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from .http_server import _WorkbenchHttpServer


class _UiWorkbenchBridgeInternalMixin:
    # --------------------------------------------------------------------- internal: server
    def _ensure_server_running(self) -> None:
        if self._server is not None:
            return
        # 静态前端统一从 assets/ui_workbench 提供（避免与测试/离线预览漂移）
        static_dir = getattr(self, "get_workbench_static_dir")()
        self._server = _WorkbenchHttpServer(workbench_dir=static_dir, bridge=self)
        self._server.start()

    def _get_workbench_url(self) -> str:
        self._ensure_server_running()
        if self._server is None:
            raise RuntimeError("Workbench server 未启动")
        # Workbench 页面已下线，所有入口统一导向预览页。
        return f"http://127.0.0.1:{self._server.port}/ui_app_ui_preview.html"

    def _get_ui_preview_url(self) -> str:
        self._ensure_server_running()
        if self._server is None:
            raise RuntimeError("Workbench server 未启动")
        return f"http://127.0.0.1:{self._server.port}/ui_app_ui_preview.html"

    # --------------------------------------------------------------------- internal: UI injection
    def _inject_left_nav_button(self) -> None:
        main_window = self._main_window
        if main_window is None:
            return
        nav_bar = getattr(main_window, "nav_bar", None)
        if nav_bar is None:
            return

        ensure_extension_button = getattr(nav_bar, "ensure_extension_button", None)
        if callable(ensure_extension_button):
            ensure_extension_button(
                key="ui_converter",
                icon_text="🧰",
                label="UI预览",
                on_click=lambda: self.open_ui_preview_in_browser(),
                tooltip="打开 UI预览（Web）",
            )
            return

        # 兼容旧版：当主程序尚未提供正式扩展点时，回退为直接插入按钮
        # 延迟导入 PyQt6：确保不影响启动阶段顺序约束
        from PyQt6 import QtWidgets

        buttons_dict = getattr(nav_bar, "buttons", None)
        if isinstance(buttons_dict, dict) and "ui_converter" in buttons_dict:
            return

        nav_module = __import__(nav_bar.__class__.__module__, fromlist=["NavigationButton"])
        NavigationButton = getattr(nav_module, "NavigationButton", None)
        if NavigationButton is None:
            return

        btn = NavigationButton("🧰", "UI预览", "ui_converter", nav_bar)
        btn.setCheckable(False)
        btn.clicked.connect(lambda: self.open_ui_preview_in_browser())

        layout = nav_bar.layout()
        if isinstance(layout, QtWidgets.QVBoxLayout):
            insert_index = max(0, layout.count() - 1)  # 放在 stretch 前
            layout.insertWidget(insert_index, btn)

        if isinstance(buttons_dict, dict):
            buttons_dict["ui_converter"] = btn

    def _inject_management_ui_button(self) -> None:
        main_window = self._main_window
        if main_window is None:
            return
        management_widget = getattr(main_window, "management_widget", None)
        if management_widget is None:
            return
        ui_control_group_manager = getattr(management_widget, "ui_control_group_manager", None)
        if ui_control_group_manager is None:
            return

        from PyQt6 import QtWidgets

        # 避免重复注入
        if getattr(ui_control_group_manager, "_ui_converter_toolbar_installed", False):
            return

        container = QtWidgets.QWidget(ui_control_group_manager)
        bar = QtWidgets.QHBoxLayout(container)
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(8)

        btn_preview = QtWidgets.QPushButton("打开 UI预览（Web）", container)
        btn_preview.clicked.connect(lambda: self.open_ui_preview_in_browser())
        bar.addWidget(btn_preview)

        bar.addStretch()

        ui_control_group_manager_layout = ui_control_group_manager.layout()
        if isinstance(ui_control_group_manager_layout, QtWidgets.QVBoxLayout):
            ui_control_group_manager_layout.insertWidget(0, container)

        setattr(ui_control_group_manager, "_ui_converter_toolbar_installed", True)

    def _refresh_ui_control_group_manager(self, *, package: object) -> None:
        main_window = self._main_window
        if main_window is None:
            return
        management_widget = getattr(main_window, "management_widget", None)
        ui_manager = getattr(management_widget, "ui_control_group_manager", None) if management_widget is not None else None
        set_package = getattr(ui_manager, "set_package", None) if ui_manager is not None else None
        if callable(set_package):
            set_package(package)

    # --------------------------------------------------------------------- internal: helpers
    @staticmethod
    def _generate_unique_id(*, prefix: str, existing: set[str]) -> str:
        while True:
            candidate = f"{prefix}_{uuid4().hex[:8]}"
            if candidate not in existing:
                return candidate

    @staticmethod
    def _ensure_unique_name(*, desired: str, existing_names: set[str]) -> str:
        base = str(desired or "").strip() or "未命名"
        if base not in existing_names:
            return base
        index = 2
        while True:
            candidate = f"{base}_{index}"
            if candidate not in existing_names:
                return candidate
            index += 1

    @staticmethod
    def _collect_existing_names(container: object, field_name: str) -> set[str]:
        out: set[str] = set()
        if not isinstance(container, dict):
            return out
        for _rid, payload in container.items():
            if not isinstance(payload, dict):
                continue
            value = payload.get(field_name) or payload.get("name") or ""
            if isinstance(value, str) and value.strip():
                out.add(value.strip())
        return out

