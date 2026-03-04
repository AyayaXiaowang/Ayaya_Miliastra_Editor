from __future__ import annotations


class _UiWorkbenchBridgeImportUiPagesMixin:
    # --------------------------------------------------------------------- import: html bundle -> management (ui_pages)
    def import_ui_page_from_bundle_payload(
        self,
        *,
        source_rel_path: str,
        bundle_payload: dict,
        layout_name: str | None = None,
    ) -> "object":
        """将 Workbench 导出的 bundle 导入到当前项目存档，并同步维护 management.ui_pages。

        约定：
        - source_rel_path 必须为项目存档 `管理配置/UI源码/` 下的文件名（不允许子目录）。
        - 不做自动派生：仅在 Workbench 显式触发导入时执行。
        """
        main_window = self._main_window
        if main_window is None:
            raise RuntimeError("主窗口未绑定，无法导入 UI bundle")
        package_controller = getattr(main_window, "package_controller", None)
        if package_controller is None:
            raise RuntimeError("主窗口缺少 package_controller，无法导入 UI bundle")

        current_package_id = str(getattr(package_controller, "current_package_id", "") or "").strip()
        if not current_package_id or current_package_id in {"global_view", "unclassified_view"}:
            raise RuntimeError("请先切换到某个【项目存档】再导入（当前为 <共享资源>/未选择）。")

        rel_name = str(source_rel_path or "").strip().replace("\\", "/")
        if not rel_name or "/" in rel_name or rel_name.startswith("."):
            raise RuntimeError(f"非法 UI 源码路径：{rel_name!r}（仅允许文件名，不允许子目录）。")
        if not rel_name.lower().endswith((".html", ".htm")):
            raise RuntimeError(f"UI 源码仅允许 .html/.htm：{rel_name!r}")

        source_abs = (
            self._workspace_root
            / "assets"
            / "资源库"
            / "项目存档"
            / current_package_id
            / "管理配置"
            / "UI源码"
            / rel_name
        ).resolve()
        if not source_abs.is_file():
            raise RuntimeError(f"未找到项目 UI 源码文件：{source_abs}")

        from app.ui.controllers.ui_html_bundle_importer import apply_ui_html_bundle_to_current_package

        summary = apply_ui_html_bundle_to_current_package(
            package_controller=package_controller,
            source_html_file=source_abs,
            bundle_payload=bundle_payload,
            layout_name=(str(layout_name).strip() if layout_name is not None else None),
        )

        # UI 刷新：尽力刷新管理页的 UIControlGroupManager
        package = getattr(package_controller, "current_package", None)
        if package is not None:
            self._refresh_ui_control_group_manager(package=package)

        return summary

