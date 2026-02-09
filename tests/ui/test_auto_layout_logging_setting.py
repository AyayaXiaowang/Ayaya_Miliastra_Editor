from __future__ import annotations

from types import SimpleNamespace

from PyQt6 import QtWidgets

from app.ui.dialogs.settings_dialog import SettingsDialog
from engine.configs.settings import settings
from app.ui.graph.graph_view.auto_layout.auto_layout_controller import AutoLayoutController


def test_graph_ui_verbose_setting_updates_settings_object() -> None:
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])

    previous_verbose = settings.GRAPH_UI_VERBOSE
    previous_save = settings.save

    def _dummy_save() -> bool:
        return True

    settings.GRAPH_UI_VERBOSE = False
    settings.save = _dummy_save

    dialog = SettingsDialog(parent=None)
    assert dialog.graph_ui_verbose_checkbox.isChecked() is False

    dialog.graph_ui_verbose_checkbox.setChecked(True)
    dialog._save_and_close()

    assert settings.GRAPH_UI_VERBOSE is True

    settings.GRAPH_UI_VERBOSE = previous_verbose
    settings.save = previous_save
    dialog.close()


def test_layout_node_spacing_percent_updates_settings_object() -> None:
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])

    previous_x_percent = settings.LAYOUT_NODE_SPACING_X_PERCENT
    previous_y_percent = settings.LAYOUT_NODE_SPACING_Y_PERCENT
    previous_save = settings.save

    def _dummy_save() -> bool:
        return True

    settings.LAYOUT_NODE_SPACING_X_PERCENT = 100
    settings.LAYOUT_NODE_SPACING_Y_PERCENT = 100
    settings.save = _dummy_save

    dialog = SettingsDialog(parent=None)
    assert dialog.layout_spacing_x_slider.minimum() == 10
    assert dialog.layout_spacing_x_slider.maximum() == 200
    assert dialog.layout_spacing_y_slider.minimum() == 10
    assert dialog.layout_spacing_y_slider.maximum() == 200
    assert dialog.layout_spacing_x_spinbox.minimum() == 10
    assert dialog.layout_spacing_x_spinbox.maximum() == 200
    assert dialog.layout_spacing_y_spinbox.minimum() == 10
    assert dialog.layout_spacing_y_spinbox.maximum() == 200
    assert dialog.layout_spacing_x_slider.value() == 100
    assert dialog.layout_spacing_y_slider.value() == 100
    assert dialog.layout_spacing_x_spinbox.value() == 100
    assert dialog.layout_spacing_y_spinbox.value() == 100

    # 既支持拖拽（slider），也支持文本输入（spinbox）
    dialog.layout_spacing_x_spinbox.setValue(150)
    dialog.layout_spacing_y_slider.setValue(200)
    dialog._save_and_close()

    assert settings.LAYOUT_NODE_SPACING_X_PERCENT == 150
    assert settings.LAYOUT_NODE_SPACING_Y_PERCENT == 200

    settings.LAYOUT_NODE_SPACING_X_PERCENT = previous_x_percent
    settings.LAYOUT_NODE_SPACING_Y_PERCENT = previous_y_percent
    settings.save = previous_save
    dialog.close()


def test_auto_layout_prints_errors_when_verbose(monkeypatch, capsys) -> None:
    class DummyView:
        def __init__(self) -> None:
            self._scene = object()
            self._auto_layout_generation = 1

        def scene(self):
            return self._scene

    monkeypatch.setattr(settings, "GRAPH_UI_VERBOSE", True)
    view = DummyView()
    thread = SimpleNamespace(
        result=SimpleNamespace(errors=["mock-error"], layout_result=None),
    )
    AutoLayoutController._on_compute_thread_finished(
        view=view,
        expected_scene=view.scene(),
        generation=1,
        thread=thread,
    )

    captured = capsys.readouterr()
    assert "【自动布局】节点图存在错误" in captured.out
    assert "mock-error" in captured.out

