"""Pin card widget for displaying and editing virtual pin metadata."""

from __future__ import annotations

from PyQt6 import QtCore, QtWidgets, QtGui

from engine.nodes.advanced_node_features import VirtualPinConfig
from engine.configs.rules.datatype_rules import BASE_TYPES, LIST_TYPES
from app.ui.foundation.context_menu_builder import ContextMenuBuilder


class PinCardWidget(QtWidgets.QWidget):
    """虚拟引脚卡片组件，负责编号、类型与名称编辑。"""

    name_changed = QtCore.pyqtSignal(VirtualPinConfig, str)
    type_changed = QtCore.pyqtSignal(VirtualPinConfig, str)
    delete_requested = QtCore.pyqtSignal(VirtualPinConfig)
    merge_requested = QtCore.pyqtSignal(VirtualPinConfig)

    def __init__(
        self,
        pin_config: VirtualPinConfig,
        composite_id: str,
        parent: QtWidgets.QWidget | None = None,
        *,
        type_editable: bool = True,
    ):
        super().__init__(parent)
        self.pin_config = pin_config
        self.composite_id = composite_id
        self._type_editable: bool = bool(type_editable)
        self.name_edit: QtWidgets.QLineEdit | None = None
        self.name_label: QtWidgets.QLabel | None = None
        self.copy_button: QtWidgets.QToolButton | None = None
        self.is_editing = False
        self._event_filter_target: QtWidgets.QWidget | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        # 通过 objectName 让全局主题样式精确命中，避免在组件内拼接 QSS 字符串
        self.setObjectName("pinCard")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        number = self._resolve_pin_number()

        number_label = QtWidgets.QLabel(str(number))
        number_label.setFixedSize(28, 28)
        number_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        number_label.setObjectName("pinNumberBadge")
        number_label.setProperty("pinKind", "flow" if self.pin_config.is_flow else "data")
        layout.addWidget(number_label)

        type_icon = "▭" if self.pin_config.is_flow else "●"
        type_label = QtWidgets.QLabel(type_icon)
        type_label.setObjectName("pinTypeIcon")
        layout.addWidget(type_label)

        self.name_label = QtWidgets.QLabel(self.pin_config.pin_name)
        self.name_label.setObjectName("pinNameLabel")
        # 支持选中文本复制（双击仍用于进入重命名编辑）
        self.name_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.name_label.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.name_label.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.IBeamCursor))
        self.name_label.mouseDoubleClickEvent = self._start_edit  # type: ignore[assignment]
        layout.addWidget(self.name_label)

        # 一键复制引脚名称（避免双击进入编辑导致不便选中文本）
        self.copy_button = QtWidgets.QToolButton(self)
        self.copy_button.setObjectName("pinCopyButton")
        self.copy_button.setText("📋")
        self.copy_button.setToolTip("复制引脚名称")
        self.copy_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.copy_button.setFixedSize(24, 24)
        self.copy_button.clicked.connect(self._copy_pin_name)
        layout.addWidget(self.copy_button)

        layout.addStretch()

        mapping_label = QtWidgets.QLabel(f"映射: {len(self.pin_config.mapped_ports)}")
        mapping_label.setObjectName("pinMappingLabel")
        layout.addWidget(mapping_label)

        layout.addWidget(self._build_type_editor())

        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _build_type_editor(self) -> QtWidgets.QWidget:
        """构建类型显示/选择控件。

        策略：
        - 流程引脚：类型固定为“流程”，不提供下拉；
        - 数据引脚：提供下拉选择具体类型，但不提供“泛型/泛型列表/泛型字典/列表”等占位项；
        - 当前值为“泛型”时显示为“未设置”（但底层仍保留 pin_type="泛型" 作为占位）。
        """
        if self.pin_config.is_flow:
            flow_tag = QtWidgets.QLabel("流程")
            flow_tag.setObjectName("pinTypeTag")
            flow_tag.setProperty("isUnset", False)
            return flow_tag

        # 当前页面不可保存：禁止修改类型（只展示）
        if not bool(getattr(self, "_type_editable", True)):
            current_type = str(self.pin_config.pin_type or "").strip()
            is_unset = current_type in ("", "泛型")
            display_text = "未设置" if is_unset else current_type
            type_tag = QtWidgets.QLabel(display_text)
            type_tag.setObjectName("pinTypeTag")
            type_tag.setProperty("isUnset", bool(is_unset))
            type_tag.setToolTip("只读：当前页面不可保存，引脚类型不允许修改。")
            return type_tag

        combo = QtWidgets.QComboBox(self)
        combo.setObjectName("pinTypeCombo")
        combo.setMinimumHeight(22)

        allowed_types: list[str] = []
        allowed_types.extend(list(BASE_TYPES.keys()))
        allowed_types.extend(list(LIST_TYPES.keys()))
        allowed_types.append("字典")

        current_type = str(self.pin_config.pin_type or "").strip()
        is_unset = current_type in ("", "泛型")

        combo.blockSignals(True)
        combo.clear()
        combo.addItem("未设置", "泛型")
        for type_name in allowed_types:
            combo.addItem(type_name, type_name)
        combo.blockSignals(False)

        # 禁止用户主动选回“未设置”：只能在初始占位状态显示
        model = combo.model()
        if hasattr(model, "item"):
            placeholder_item = model.item(0)
            if placeholder_item is not None:
                placeholder_item.setEnabled(False)

        if is_unset:
            combo.setCurrentIndex(0)
        else:
            index = combo.findData(current_type)
            combo.setCurrentIndex(index if index >= 0 else 0)

        combo.currentIndexChanged.connect(lambda _: self._on_type_changed(combo))
        combo.setToolTip("选择对外引脚的具体类型；保存/校验阶段不允许保留“泛型”占位。")
        return combo

    def _on_type_changed(self, combo: QtWidgets.QComboBox) -> None:
        if not bool(getattr(self, "_type_editable", True)):
            return
        selected = combo.currentData()
        selected_type = str(selected or "").strip()
        if not selected_type:
            return
        if selected_type == self.pin_config.pin_type:
            return
        self.pin_config.pin_type = selected_type
        self.type_changed.emit(self.pin_config, selected_type)

    def _copy_pin_name(self) -> None:
        """复制引脚名称到剪贴板。"""
        clipboard = QtWidgets.QApplication.clipboard()
        text = ""
        if self.is_editing and self.name_edit is not None:
            text = str(self.name_edit.text() or "")
        else:
            text = str(self.pin_config.pin_name or "")
        clipboard.setText(text)

    def _resolve_pin_number(self) -> str:
        from engine.nodes.composite_node_manager import get_composite_node_manager

        manager = get_composite_node_manager()
        if not manager:
            return "?"
        _, number = manager.get_pin_display_number(self.composite_id, self.pin_config)
        return str(number)

    def _start_edit(self, event) -> None:  # type: ignore[override]
        if self.is_editing:
            return
        self.is_editing = True
        self.name_edit = QtWidgets.QLineEdit(self.pin_config.pin_name)
        self.name_edit.setObjectName("pinNameEdit")
        layout = self.layout()
        if self.name_label and layout:
            layout.replaceWidget(self.name_label, self.name_edit)
            self.name_label.hide()
        self.name_edit.selectAll()
        self.name_edit.setFocus()
        self.name_edit.editingFinished.connect(self._finish_edit)

        # 在卡片所在窗口级别安装事件过滤器，监听点击列表其它区域时自动结束编辑
        top_level = self.window()
        if isinstance(top_level, QtWidgets.QWidget):
            self._event_filter_target = top_level
            top_level.installEventFilter(self)

    def _finish_edit(self) -> None:
        if not self.is_editing or not self.name_edit or not self.name_label:
            return

        if self._event_filter_target is not None:
            self._event_filter_target.removeEventFilter(self)
            self._event_filter_target = None

        new_name = self.name_edit.text().strip()
        if new_name and new_name != self.pin_config.pin_name:
            self.name_changed.emit(self.pin_config, new_name)
            self.name_label.setText(new_name)
        layout = self.layout()
        if layout:
            layout.replaceWidget(self.name_edit, self.name_label)
        self.name_label.show()
        self.name_edit.deleteLater()
        self.name_edit = None
        self.is_editing = False

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:  # type: ignore[override]
        # 若当前处于编辑状态，且用户在窗口内任意位置点击了鼠标（不包含编辑框本身），则结束编辑
        if (
            self.is_editing
            and self.name_edit is not None
            and event.type() == QtCore.QEvent.Type.MouseButtonPress
        ):
            if isinstance(event, QtGui.QMouseEvent):
                global_pos = event.globalPosition().toPoint()
                local_pos = self.name_edit.mapFromGlobal(global_pos)
                if not self.name_edit.rect().contains(local_pos):
                    self._finish_edit()
        return super().eventFilter(watched, event)

    def _show_context_menu(self, pos: QtCore.QPoint) -> None:
        builder = ContextMenuBuilder(self)
        builder.add_action("🔗 开启合并模式", lambda: self.merge_requested.emit(self.pin_config))
        builder.add_action("🗑️ 删除引脚", lambda: self.delete_requested.emit(self.pin_config))
        builder.exec_for(self, pos)


