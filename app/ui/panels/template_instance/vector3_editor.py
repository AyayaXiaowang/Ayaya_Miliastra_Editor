"""Vector3 输入控件（模板/实体属性面板复用）。

该模块从 `basic_info_tab.py` 抽出通用的 Vector3 编辑控件，避免在多个编辑器/对话框中复制
同样的 X/Y/Z 三轴输入样式与交互细节。
"""

from __future__ import annotations

from typing import Optional, Sequence, Any

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager


def safe_float_list3(value: object, default: Sequence[float]) -> list[float]:
    """将任意值安全归一化为 3 个 float。

    - value 为长度=3 的 list 时按元素取 float；否则回退 default
    - 非数值元素回退对应 default
    """
    if isinstance(value, list) and len(value) == 3:
        out: list[float] = []
        for item, fallback in zip(value, default):
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                out.append(float(item))
            else:
                out.append(float(fallback))
        return out
    return [float(default[0]), float(default[1]), float(default[2])]


class _AxisDragLabel(QtWidgets.QLabel):
    """支持左右拖拽调节数值的轴标签。"""

    def __init__(
        self,
        axis_text: str,
        *,
        background_color: str,
        target_spin: QtWidgets.QDoubleSpinBox,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(axis_text, parent)
        self._spin = target_spin
        self._dragging = False
        self._start_global_x: float = 0.0
        self._start_value: float = 0.0

        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.setFixedWidth(18)
        self.setStyleSheet(
            f"""
            QLabel {{
                background-color: {background_color};
                color: {Colors.TEXT_ON_PRIMARY};
                border-radius: 4px;
                padding: 1px 2px;
                font-weight: bold;
            }}
            """
        )

    def mousePressEvent(self, event: QtGui.QMouseEvent | None) -> None:  # type: ignore[override]
        if event is None:
            return
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if not self._spin.isEnabled():
            return
        self._dragging = True
        self._start_global_x = float(event.globalPosition().x())
        self._start_value = float(self._spin.value())
        event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent | None) -> None:  # type: ignore[override]
        if event is None:
            return
        if not self._dragging:
            super().mouseMoveEvent(event)
            return
        if not self._spin.isEnabled():
            return

        delta_x = float(event.globalPosition().x()) - self._start_global_x
        # 拖拽步进：默认 0.1 / px，按住 Shift 更细
        step = 0.01 if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier else 0.1
        next_value = self._start_value + delta_x * step
        self._spin.setValue(next_value)
        event.accept()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent | None) -> None:  # type: ignore[override]
        if event is None:
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class Vector3Editor(QtWidgets.QWidget):
    """Vector3 输入控件：X/Y/Z 彩色标签 + 三个浮点 SpinBox。"""

    value_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        *,
        minimum: float,
        maximum: float,
        decimals: int,
        single_step: float,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_SMALL)

        self._spins: list[QtWidgets.QDoubleSpinBox] = []

        axis_specs = (
            ("X", Colors.ERROR),
            ("Y", Colors.SUCCESS),
            ("Z", Colors.PRIMARY),
        )
        for axis_text, axis_color in axis_specs:
            axis_container = QtWidgets.QWidget(self)
            axis_layout = QtWidgets.QHBoxLayout(axis_container)
            axis_layout.setContentsMargins(0, 0, 0, 0)
            axis_layout.setSpacing(4)

            spin = QtWidgets.QDoubleSpinBox(axis_container)
            spin.setStyleSheet(ThemeManager.spin_box_style())
            spin.setRange(minimum, maximum)
            spin.setDecimals(decimals)
            spin.setSingleStep(single_step)
            spin.valueChanged.connect(self.value_changed.emit)

            axis_label = _AxisDragLabel(
                axis_text,
                background_color=axis_color,
                target_spin=spin,
                parent=axis_container,
            )
            axis_layout.addWidget(axis_label)
            axis_layout.addWidget(spin, 1)

            layout.addWidget(axis_container, 1)
            self._spins.append(spin)

    def set_values(self, values: Sequence[float]) -> None:
        defaults = safe_float_list3(list(values), [0.0, 0.0, 0.0])
        for spin, value in zip(self._spins, defaults):
            spin.setValue(float(value))

    def get_values(self) -> list[float]:
        return [float(spin.value()) for spin in self._spins]

    def set_editable(self, editable: bool) -> None:
        for spin in self._spins:
            spin.setEnabled(bool(editable))


__all__ = ["Vector3Editor", "safe_float_list3"]


