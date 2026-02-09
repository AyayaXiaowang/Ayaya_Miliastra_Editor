"""验证、设置与更新检查相关的事件处理 Mixin。"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets

from app.models.view_modes import ViewMode
from app.ui.controllers.validation_graph_code_service import (
    GraphCodeValidationOptions,
    GraphCodeValidationService,
)
from app.ui.dialogs.settings_dialog import SettingsDialog
from engine.validate.comprehensive_validator import ComprehensiveValidator


class ValidationAndSettingsMixin:
    """封装验证触发、设置对话框、资源库手动刷新与更新/环境检查入口。"""

    def _get_graph_code_validation_service(self) -> GraphCodeValidationService:
        service = getattr(self, "_graph_code_validation_service", None)
        if service is None:
            service = GraphCodeValidationService()
            setattr(self, "_graph_code_validation_service", service)
        return service

    def _trigger_validation_full(self) -> None:
        """触发“存档综合 + 节点图源码”全量验证（默认按当前存档范围）。"""
        self._trigger_validation()
        validation_panel = getattr(self, "validation_panel", None)
        if validation_panel is None or not hasattr(validation_panel, "get_graph_code_validation_options"):
            self._trigger_graph_code_validation(
                scope="package",
                strict_entity_wire_only=False,
                disable_cache=False,
                enable_composite_struct_check=True,
            )
            return
        strict_entity_wire_only, disable_cache, enable_composite_struct_check = (
            validation_panel.get_graph_code_validation_options()
        )
        self._trigger_graph_code_validation(
            scope="package",
            strict_entity_wire_only=bool(strict_entity_wire_only),
            disable_cache=bool(disable_cache),
            enable_composite_struct_check=bool(enable_composite_struct_check),
        )

    def _trigger_validation(self) -> None:
        """触发当前存档的验证流程"""
        package = self.package_controller.current_package
        if not package:
            self.validation_panel.clear()
            return

        validator = ComprehensiveValidator(package, self.app_state.resource_manager, verbose=False)
        issues = validator.validate_all()
        if hasattr(self.validation_panel, "update_package_issues"):
            self.validation_panel.update_package_issues(issues)
        else:
            self.validation_panel.update_issues(issues)

    def _trigger_graph_code_validation(
        self,
        *,
        scope: str,
        strict_entity_wire_only: bool,
        disable_cache: bool,
        enable_composite_struct_check: bool,
    ) -> None:
        """触发节点图源码校验，并把结果刷新到验证页面。"""
        validation_panel = getattr(self, "validation_panel", None)
        if validation_panel is None:
            return

        package = getattr(self.package_controller, "current_package", None)
        if scope == "package" and not package:
            validation_panel.clear()
            return

        service = self._get_graph_code_validation_service()
        options = GraphCodeValidationOptions(
            scope=str(scope or ""),
            strict_entity_wire_only=bool(strict_entity_wire_only),
            disable_cache=bool(disable_cache),
            enable_composite_struct_check=bool(enable_composite_struct_check),
        )
        issues = service.validate_for_ui(
            resource_manager=self.app_state.resource_manager,
            current_package=package if scope == "package" else None,
            options=options,
        )
        if hasattr(validation_panel, "update_graph_code_issues"):
            validation_panel.update_graph_code_issues(issues)
        else:
            # 兼容：若旧面板不支持区分来源，则直接合并展示
            validation_panel.update_issues(list(issues))

    def _open_settings_dialog(self) -> None:
        """打开设置对话框并在需要时刷新任务清单"""
        dialog = SettingsDialog(self)
        dialog.exec()

        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode == ViewMode.TODO:
            self._refresh_todo_list(force=True)
            self._show_toast("已根据新设置刷新任务清单", "success")

    def _open_local_graph_sim_dialog(self) -> None:
        """打开“节点图 + UI 本地测试”面板（浏览器预览入口）。"""
        from app.ui.dialogs.local_graph_sim_dialog import LocalGraphSimDialog

        dialog = getattr(self, "_local_graph_sim_dialog", None)
        package_id = getattr(self.package_controller, "current_package_id", None)
        if dialog is None:
            dialog = LocalGraphSimDialog(
                workspace_root=self.app_state.workspace_path,
                active_package_id=package_id,
                resource_manager=self.app_state.resource_manager,
                package_index_manager=self.app_state.package_index_manager,
                parent=self,
            )
            setattr(self, "_local_graph_sim_dialog", dialog)

            def _clear_dialog(*_args) -> None:
                setattr(self, "_local_graph_sim_dialog", None)

            dialog.finished.connect(_clear_dialog)
        else:
            # 对话框复用时同步当前项目存档作用域，确保可见列表始终与“当前项目”一致。
            if hasattr(dialog, "set_active_package_id"):
                dialog.set_active_package_id(package_id)

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _on_manual_refresh_resource_library(self) -> None:
        """手动刷新资源库（顶部工具栏“刷新”按钮）。

        当选择“手动更新”模式或希望立刻查看外部工具对资源库的改动时，
        通过此入口重建资源索引并刷新各资源库相关视图。
        """
        if hasattr(self, "refresh_resource_library"):
            self.refresh_resource_library()
        # 刷新后台化：开始/完成提示由主窗口的资源刷新协调器统一发出。

    def _on_check_for_updates(self) -> None:
        """检查 GitHub 更新并提示对比结果。"""
        from app.app_info import APP_REPO_FULL_NAME, APP_REPO_URL, APP_UPDATE_CHECK_MODE, APP_VERSION
        from app.common.github_update_checker import check_for_updates
        from app.ui.foundation import dialog_utils

        workspace_path = self.app_state.workspace_path
        report = check_for_updates(
            workspace_path=workspace_path,
            repo_full_name=APP_REPO_FULL_NAME,
            local_version=APP_VERSION,
            mode=APP_UPDATE_CHECK_MODE,
        )

        remote_kind = report.remote.kind
        remote_ref = report.remote.ref
        remote_published_at = report.remote.published_at
        remote_overview_url = report.remote.overview_url.strip() if report.remote.overview_url.strip() else APP_REPO_URL
        remote_title = report.remote.title

        message_lines: list[str] = []
        if remote_kind == "latest_release":
            message_lines.append(f"更新来源：GitHub 最新 Release（tag={remote_ref}）")
        else:
            message_lines.append(f"更新来源：GitHub（ref={remote_ref}）")

        if remote_published_at:
            message_lines.append(f"发布时间：{remote_published_at}")
        if remote_title:
            message_lines.append(f"标题：{remote_title}")
        message_lines.append(f"本地版本：{report.local_version}")
        message_lines.append(f"Release 页面：{remote_overview_url}")
        message_lines.append("")

        if report.status == "up_to_date":
            message_lines.append("结果：已是最新版本")
            dialog_utils.show_info_dialog(self, "检查更新", "\n".join(message_lines))
            return

        if report.status == "update_available":
            message_lines.append("结果：发现新版本")

            action_key = dialog_utils.ask_choice_dialog(
                self,
                "检查更新",
                "\n".join(message_lines),
                icon="information",
                choices=[
                    ("download", "下载最新版（Windows 便携版）", "action"),
                    ("open_release_page", "打开 Release 页面", "action"),
                    ("cancel", "取消", "reject"),
                ],
                default_choice_key="download",
                escape_choice_key="cancel",
            )
            if action_key == "download":
                self._download_latest_windows_portable_release(
                    repo_full_name=APP_REPO_FULL_NAME,
                    expected_tag=remote_ref,
                    fallback_open_url=remote_overview_url,
                )
                return
            if action_key == "open_release_page":
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(remote_overview_url))
                return
            return
        elif report.status == "ahead_of_remote":
            message_lines.append("结果：本地版本号高于远端 Release（通常是开发态或版本号未同步）")
        elif report.status == "diverged":
            message_lines.append("结果：本地与远端出现分叉（需要手动处理合并/重置）")
        else:
            message_lines.append("结果：无法判断是否为最新（本地版本号/Release tag 不是语义版本）")

        should_open_github_page = dialog_utils.ask_yes_no_dialog(
            self,
            "检查更新",
            "\n".join(message_lines) + "\n\n是否打开 Release 页面？",
        )
        if should_open_github_page:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(remote_overview_url))

    def _on_check_environment(self) -> None:
        """检查当前使用环境（显示设置 / 千星沙箱窗口 / 管理员权限 / 程序版本）。"""
        from app.app_info import APP_DISPLAY_NAME, APP_VERSION
        from app.common.environment_checker import build_environment_diagnostics_report
        from app.ui.foundation import dialog_utils

        report = build_environment_diagnostics_report(
            app_display_name=APP_DISPLAY_NAME,
            app_version=APP_VERSION,
            sandbox_window_title="千星沙箱",
        )
        dialog_utils.show_info_dialog(self, "环境检查", report.to_text())

    def _download_latest_windows_portable_release(
        self,
        *,
        repo_full_name: str,
        expected_tag: str,
        fallback_open_url: str,
    ) -> None:
        """下载并解压最新 Release 的 Windows 便携版 zip（不覆盖当前程序）。"""
        from app.common.github_update_checker import (
            download_url_to_file,
            extract_zip_file,
            fetch_latest_release_with_assets,
            select_windows_portable_zip_asset,
        )
        from app.ui.foundation import dialog_utils

        workspace_path = self.app_state.workspace_path
        release = fetch_latest_release_with_assets(repo_full_name)
        tag_name = str(release.tag_name or "").strip()
        if tag_name == "":
            raise ValueError("Release tag 为空，无法下载更新")

        # 若 release 在用户点击后已滚动更新，提示用户以新 tag 为准（仍允许继续下载最新）。
        resolved_expected = str(expected_tag or "").strip()
        if resolved_expected and resolved_expected != tag_name:
            dialog_utils.show_warning_dialog(
                self,
                "下载更新",
                f"检测到 Release 已更新：\n"
                f"- 你看到的版本：{resolved_expected}\n"
                f"- 当前最新版本：{tag_name}\n\n"
                f"将按“当前最新版本”下载。",
            )

        asset = select_windows_portable_zip_asset(release.assets)

        updates_root = workspace_path / "updates" / tag_name
        zip_path = updates_root / asset.name
        extract_dir = updates_root / "extracted"

        progress = QtWidgets.QProgressDialog(self)
        progress.setWindowTitle("下载更新")
        progress.setLabelText(f"正在下载：{asset.name}")
        progress.setCancelButtonText("取消")
        progress.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.show()

        def _format_size(num_bytes: int) -> str:
            value = float(num_bytes)
            for unit in ["B", "KB", "MB", "GB"]:
                if value < 1024 or unit == "GB":
                    return f"{value:.1f}{unit}"
                value /= 1024
            return f"{value:.1f}GB"

        def _on_progress(downloaded: int, total: int | None) -> None:
            if total is not None and total > 0:
                percent = int(downloaded * 100 / total)
                progress.setRange(0, 100)
                progress.setValue(max(0, min(percent, 100)))
                progress.setLabelText(
                    f"正在下载：{asset.name}\n"
                    f"{_format_size(downloaded)} / {_format_size(total)}"
                )
            else:
                progress.setRange(0, 0)  # 不确定大小：展示忙碌条
                progress.setLabelText(f"正在下载：{asset.name}\n已下载：{_format_size(downloaded)}")
            QtWidgets.QApplication.processEvents()

        completed = download_url_to_file(
            asset.browser_download_url,
            zip_path,
            timeout_seconds=60.0,
            progress_callback=_on_progress,
            should_cancel=progress.wasCanceled,
        )
        progress.close()

        if not completed:
            dialog_utils.show_info_dialog(self, "下载更新", "已取消下载。")
            return

        # 解压
        extracting = QtWidgets.QProgressDialog(self)
        extracting.setWindowTitle("下载更新")
        extracting.setLabelText("下载完成，正在解压...")
        extracting.setCancelButton(None)
        extracting.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        extracting.setMinimumDuration(0)
        extracting.setRange(0, 0)
        extracting.show()
        QtWidgets.QApplication.processEvents()

        extract_zip_file(zip_path, extract_dir)

        extracting.close()

        exe_candidates = list(extract_dir.rglob("Ayaya_Miliastra_Editor.exe"))
        exe_path_text = str(exe_candidates[0]) if exe_candidates else ""
        open_target = exe_candidates[0].parent if exe_candidates else extract_dir

        message = (
            "✅ 已下载并解压完成。\n\n"
            f"- 版本：{tag_name}\n"
            f"- 下载包：{zip_path}\n"
            f"- 解压目录：{extract_dir}\n"
        )
        if exe_path_text:
            message += f"- 新版入口：{exe_path_text}\n"
        message += "\n注意：为了避免覆盖正在运行的程序，本功能不会自动替换当前目录。"

        should_open_folder = dialog_utils.ask_yes_no_dialog(
            self,
            "下载更新",
            message + "\n\n是否打开解压目录？",
            default_yes=True,
        )
        if should_open_folder:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(open_target)))
            return

        should_open_release_page = dialog_utils.ask_yes_no_dialog(
            self,
            "下载更新",
            f"是否打开 Release 页面（用于查看更新说明/其它资产）？\n{fallback_open_url}",
        )
        if should_open_release_page:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(str(fallback_open_url)))


