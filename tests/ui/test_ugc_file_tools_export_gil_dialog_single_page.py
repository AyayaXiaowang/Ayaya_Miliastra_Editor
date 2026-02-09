from __future__ import annotations

from pathlib import Path

import pytest


def test_ugc_file_tools_export_dialog_single_page_checkbox_ui(tmp_path: Path, monkeypatch) -> None:
    """回归：ugc_file_tools 的“导出 .gil”应为单对话框勾选式配置，而非串行弹窗。

    说明：
    - ugc_file_tools 属于私有扩展；若当前工作区未包含该扩展目录，本用例跳过。
    - 本用例只覆盖“对话框 UI 结构/联动/必填校验入口是否可达”，不跑真实写回管线。
    """
    from tests._helpers.project_paths import get_repo_root

    repo_root = get_repo_root()
    private_extensions_root = repo_root / "private_extensions"
    ugc_tools_root = private_extensions_root / "ugc_file_tools"
    if not ugc_tools_root.is_dir():
        pytest.skip("ugc_file_tools 私有扩展不在当前工作区中，跳过 UI 用例。")

    monkeypatch.syspath_prepend(str(private_extensions_root))

    from PyQt6 import QtCore, QtWidgets

    from ugc_file_tools.ui_integration import export_gil as export_ui

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # 构造一个最小“临时工作区”，用于 on_export_clicked 的路径探测
    workspace_root = tmp_path / "ws"
    package_id = "pkgA"
    project_root = workspace_root / "assets" / "资源库" / "项目存档" / package_id

    # 只制造“元件库 + 节点图”两类可导出数据，其余保持为空，用于验证：
    # - 勾选项可用/禁用
    # - 全选仅影响可用项
    (project_root / "元件库").mkdir(parents=True, exist_ok=True)
    (project_root / "元件库" / "template_1.json").write_text("{}", encoding="utf-8")
    (project_root / "节点图").mkdir(parents=True, exist_ok=True)
    (project_root / "节点图" / "foo.py").write_text("# stub graph\n", encoding="utf-8")

    class _DummySelection:
        def __init__(self, package_id: str) -> None:
            self.id = str(package_id)

    class _DummyPackageLibraryWidget(QtWidgets.QWidget):
        def __init__(self, parent: QtWidgets.QWidget, package_id: str) -> None:
            super().__init__(parent)
            self._package_id = str(package_id)

        def get_selection(self) -> _DummySelection:
            return _DummySelection(self._package_id)

    class _DummyPackageController:
        def save_now(self) -> None:
            return

    class _DummyAppState:
        def __init__(self, workspace_path: Path) -> None:
            self.workspace_path = str(workspace_path)

    main_window = QtWidgets.QMainWindow()
    main_window.app_state = _DummyAppState(workspace_root)
    main_window.package_controller = _DummyPackageController()
    main_window.package_library_widget = _DummyPackageLibraryWidget(main_window, package_id=package_id)

    # 通过定时器在 dialog.exec() 的事件循环中抓取并检查对话框，然后主动关闭，避免阻塞测试。
    results: dict[str, object] = {}

    def _find_checkbox(widget: QtWidgets.QWidget, *, prefix: str) -> QtWidgets.QCheckBox | None:
        for cb in widget.findChildren(QtWidgets.QCheckBox):
            if str(cb.text() or "").startswith(prefix):
                return cb
        return None

    def _find_combo(widget: QtWidgets.QWidget, *, first_item_prefix: str) -> QtWidgets.QComboBox | None:
        for combo in widget.findChildren(QtWidgets.QComboBox):
            if combo.count() <= 0:
                continue
            if str(combo.itemText(0) or "").startswith(first_item_prefix):
                return combo
        return None

    def _inspect_and_close_dialog() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        results["dialog_found"] = bool(dialog is not None)
        if dialog is None or not isinstance(dialog, QtWidgets.QDialog):
            return

        # 核心：勾选 + 全选
        select_all = _find_checkbox(dialog, prefix="全选（仅对可用项生效）")
        templates_cb = _find_checkbox(dialog, prefix="元件库模板")
        graphs_cb = _find_checkbox(dialog, prefix="节点图")
        structs_cb = _find_checkbox(dialog, prefix="结构体定义")

        results["has_select_all"] = bool(select_all is not None)
        results["templates_cb_enabled"] = bool(templates_cb is not None and templates_cb.isEnabled())
        results["graphs_cb_enabled"] = bool(graphs_cb is not None and graphs_cb.isEnabled())
        results["structs_cb_disabled"] = bool(structs_cb is not None and (not structs_cb.isEnabled()))
        results["structs_cb_text_has_empty_hint"] = bool(structs_cb is not None and "（无数据）" in str(structs_cb.text()))

        ok_btn = getattr(dialog, "button_box", None)
        ok_button = None
        if ok_btn is not None and hasattr(ok_btn, "button"):
            ok_button = ok_btn.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        results["ok_button_found"] = bool(ok_button is not None)
        results["ok_button_enabled_initial"] = bool(ok_button is not None and ok_button.isEnabled())

        # 联动：取消全部可用项 -> OK disabled；再全选 -> OK enabled
        if templates_cb is not None and graphs_cb is not None:
            templates_cb.setChecked(False)
            graphs_cb.setChecked(False)
            QtWidgets.QApplication.processEvents()
            results["ok_button_enabled_after_uncheck_all"] = bool(ok_button is not None and ok_button.isEnabled())

            if select_all is not None:
                select_all.setChecked(True)
                QtWidgets.QApplication.processEvents()
                results["ok_button_enabled_after_select_all"] = bool(ok_button is not None and ok_button.isEnabled())

        # 联动：元件库选项应随“元件库模板”勾选启用/禁用
        templates_mode_combo = _find_combo(dialog, first_item_prefix="overwrite（覆盖名称")
        results["templates_mode_combo_found"] = bool(templates_mode_combo is not None)
        if templates_mode_combo is not None:
            results["templates_mode_combo_enabled_initial"] = bool(templates_mode_combo.isEnabled())
            if templates_cb is not None:
                templates_cb.setChecked(False)
                QtWidgets.QApplication.processEvents()
                results["templates_mode_combo_enabled_after_uncheck"] = bool(templates_mode_combo.isEnabled())

        dialog.reject()

    def _force_close_dialog() -> None:
        dialog = QtWidgets.QApplication.activeModalWidget()
        if dialog is not None and isinstance(dialog, QtWidgets.QDialog):
            dialog.reject()

    QtCore.QTimer.singleShot(50, _inspect_and_close_dialog)
    QtCore.QTimer.singleShot(300, _force_close_dialog)

    export_ui.on_export_clicked(main_window)

    assert results.get("dialog_found") is True
    assert results.get("has_select_all") is True
    assert results.get("templates_cb_enabled") is True
    assert results.get("graphs_cb_enabled") is True
    assert results.get("structs_cb_disabled") is True
    assert results.get("structs_cb_text_has_empty_hint") is True
    assert results.get("ok_button_found") is True
    assert results.get("ok_button_enabled_initial") is True
    # 取消全部可用项后 OK 应不可点
    assert results.get("ok_button_enabled_after_uncheck_all") is False
    # 再点全选 OK 应恢复可点
    assert results.get("ok_button_enabled_after_select_all") is True
    assert results.get("templates_mode_combo_found") is True
    assert results.get("templates_mode_combo_enabled_initial") is True
    assert results.get("templates_mode_combo_enabled_after_uncheck") is False

    _ = app  # keep reference


