from __future__ import annotations

from importlib.util import find_spec

import pytest

# 顺序约束：若 OCR 依赖存在，则 RapidOCR 必须先于 PyQt6 导入，避免 DLL 冲突（参照 app.bootstrap.ui_bootstrap）。
if find_spec("rapidocr_onnxruntime") is not None:
    from rapidocr_onnxruntime import RapidOCR  # noqa: F401

from PyQt6 import QtWidgets

_SESSION_QT_APP: QtWidgets.QApplication | None = None


@pytest.fixture(scope="session", autouse=True)
def _ensure_session_qapplication() -> QtWidgets.QApplication:
    """为 tests/ui 下的所有用例提供稳定的 QApplication 单例。

    重要：
    - PyQt6 的 QApplication 若没有被 Python 侧持有引用，可能会被立即销毁，导致后续创建 QWidget/QGraphicsScene
      触发进程级崩溃（Windows 上常见为 access violation / stack buffer overrun）。
    - 因此这里使用 session 级 fixture + 模块全局引用，确保生命周期覆盖整轮 UI 测试。
    """
    global _SESSION_QT_APP
    app_instance = QtWidgets.QApplication.instance()
    if app_instance is None:
        app_instance = QtWidgets.QApplication([])
    _SESSION_QT_APP = app_instance
    return app_instance

