from __future__ import annotations

import sys
from pathlib import Path


def test_private_extension_injected_button_click_smoke(tmp_path: Path, monkeypatch) -> None:
    """回归：按文件路径加载的扩展模块注入按钮后，点击按钮不应因 sys.modules 缺失而崩溃。

    背景：
    - 私有扩展按文件路径加载时，若 loader 未将模块写入 sys.modules，
      dataclasses/typing 等在运行期（按钮点击触发）可能访问 sys.modules[__module__] 而报错。
    - 本用例以“注入一个按钮 + 点击触发 dataclass”的最小链路覆盖该风险点。
    """
    from PyQt6 import QtWidgets

    from app.common import private_extension_loader as extension_loader
    from app.common import private_extension_registry as extension_registry

    app_instance = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # 隔离：清空主窗口钩子列表，避免受其它测试注册的钩子影响
    monkeypatch.setattr(extension_registry, "_main_window_hooks", [], raising=False)

    # 隔离：避免 loader 复用旧缓存模块（本用例使用临时文件路径，仍显式清空更稳）
    monkeypatch.setattr(extension_loader, "_cached_workspace_plugin_modules", {}, raising=False)

    module_id = "tests._tmp_private_extension_button_smoke"
    monkeypatch.delitem(sys.modules, module_id, raising=False)

    plugin_py = tmp_path / "plugin.py"
    plugin_py.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "from app.common.private_extension_registry import register_main_window_hook",
                "",
                "@register_main_window_hook",
                "def _install_button(main_window: object) -> None:",
                "    from dataclasses import dataclass",
                "    from PyQt6 import QtWidgets",
                "",
                "    if not isinstance(main_window, QtWidgets.QMainWindow):",
                "        raise TypeError('main_window must be QMainWindow')",
                "",
                "    widget = getattr(main_window, 'package_library_widget', None)",
                "    if widget is None:",
                "        raise RuntimeError('missing package_library_widget')",
                "",
                "    ensure_btn = getattr(widget, 'ensure_extension_toolbar_button', None)",
                "    if not callable(ensure_btn):",
                "        raise RuntimeError('missing ensure_extension_toolbar_button')",
                "",
                "    def _on_click() -> None:",
                "        @dataclass(frozen=True)",
                "        class Payload:",
                "            value: str",
                "        setattr(main_window, '_clicked_marker', Payload('ok').value)",
                "",
                "    ensure_btn('test.read', '读取', tooltip='smoke', on_clicked=_on_click, enabled=True)",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # 按文件路径加载模块（核心：必须写入 sys.modules，dataclass 才能稳定工作）
    _module = extension_loader._load_module_from_path(module_id=module_id, file_path=plugin_py)
    assert module_id in sys.modules

    class _DummyPackageLibraryWidget(QtWidgets.QWidget):
        def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
            super().__init__(parent)
            self._extension_toolbar_buttons: dict[str, QtWidgets.QPushButton] = {}

        def ensure_extension_toolbar_button(
            self,
            key: str,
            text: str,
            *,
            tooltip: str = "",
            on_clicked=None,
            enabled: bool = True,
        ) -> QtWidgets.QPushButton:
            button = QtWidgets.QPushButton(str(text), self)
            button.setEnabled(bool(enabled))
            if tooltip:
                button.setToolTip(str(tooltip))
            if on_clicked is not None:
                button.clicked.connect(on_clicked)
            self._extension_toolbar_buttons[str(key)] = button
            return button

    main_window = QtWidgets.QMainWindow()
    main_window.package_library_widget = _DummyPackageLibraryWidget(main_window)

    # 执行钩子 → 注入按钮
    extension_registry.run_main_window_hooks(main_window=main_window)

    buttons = getattr(main_window.package_library_widget, "_extension_toolbar_buttons")
    assert "test.read" in buttons

    # 点击按钮：触发运行期 dataclass（若 sys.modules 未注册，会在这里报错）
    buttons["test.read"].click()
    QtWidgets.QApplication.processEvents()

    assert getattr(main_window, "_clicked_marker", "") == "ok"
    _ = app_instance  # keep reference


