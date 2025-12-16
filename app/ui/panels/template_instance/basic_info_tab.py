"""Basic info tab for template/instance panel."""

from __future__ import annotations

from typing import Optional, Union

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.graph.models.package_model import InstanceConfig, TemplateConfig
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from app.ui.foundation.theme_manager import Colors, Sizes
from app.ui.panels.template_instance.tab_base import TemplateInstanceTabBase, is_drop_template_config


class BasicInfoTab(TemplateInstanceTabBase):
    """基础信息标签页，负责展示名称/描述/类型等。"""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._updating_ui = False
        self._is_read_only = False
        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setInterval(250)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._emit_data_changed)
        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        form_widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(form_widget)
        layout.setVerticalSpacing(8)
        layout.setHorizontalSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)

        # 名称
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.textEdited.connect(self._schedule_emit)
        self._name_label = QtWidgets.QLabel("名称:")

        # 类型
        self.type_label = QtWidgets.QLabel()
        self.type_label.setStyleSheet(
            f"color: {Colors.PRIMARY}; font-weight: bold; padding: {Sizes.PADDING_SMALL}px;"
        )
        self.type_label.setMaximumHeight(40)
        self.type_label.setWordWrap(True)
        type_policy = self.type_label.sizePolicy()
        type_policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Expanding)
        self.type_label.setSizePolicy(type_policy)
        self._type_label = QtWidgets.QLabel("类型:")

        # GUID（可选，模板与实体共用）
        self.guid_edit = QtWidgets.QLineEdit()
        self.guid_edit.setPlaceholderText("仅数字，可留空")
        guid_regex = QtCore.QRegularExpression(r"[0-9]{0,20}")
        self.guid_edit.setValidator(QtGui.QRegularExpressionValidator(guid_regex, self))
        self.guid_edit.textEdited.connect(self._schedule_emit)
        self._guid_label = QtWidgets.QLabel("GUID:")

        # 描述 / 备注
        self.desc_edit = QtWidgets.QPlainTextEdit()
        self.desc_edit.setPlaceholderText("输入描述信息...")
        self.desc_edit.setMinimumHeight(120)
        self.desc_edit.setMaximumHeight(500)
        self.desc_edit.textChanged.connect(self._adjust_desc_height)
        self.desc_edit.textChanged.connect(self._schedule_emit)
        self._desc_label = QtWidgets.QLabel("描述:")

        # 模型ID（仅掉落物显示）
        self.model_id_edit = QtWidgets.QLineEdit()
        self.model_id_edit.setPlaceholderText("仅数字，可留空")
        model_id_regex = QtCore.QRegularExpression(r"[0-9]{0,20}")
        self.model_id_edit.setValidator(QtGui.QRegularExpressionValidator(model_id_regex, self))
        self.model_id_edit.textEdited.connect(self._schedule_emit)
        self._model_id_label = QtWidgets.QLabel("模型ID:")

        self.position_widget = QtWidgets.QWidget()
        pos_layout = QtWidgets.QHBoxLayout(self.position_widget)
        pos_layout.setContentsMargins(0, 0, 0, 0)
        self.pos_label = QtWidgets.QLabel()
        self.pos_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        pos_layout.addWidget(self.pos_label)
        pos_layout.addStretch()
        self.position_widget.setVisible(False)

        layout.addRow(self._name_label, self.name_edit)
        layout.addRow(self._type_label, self.type_label)
        layout.addRow(self._guid_label, self.guid_edit)
        layout.addRow(self._model_id_label, self.model_id_edit)
        layout.addRow(self._desc_label, self.desc_edit)
        layout.addRow("位置:", self.position_widget)

        self._set_drop_specific_widgets_visible(False)

        main_layout.addWidget(form_widget)
        main_layout.addStretch(1)

    def _reset_ui(self) -> None:
        self._updating_ui = True
        self.name_edit.clear()
        self.type_label.setText("-")
        self.desc_edit.clear()
        self.guid_edit.clear()
        self.pos_label.setText("-")
        self.position_widget.setVisible(False)
        self.model_id_edit.clear()
        self._set_drop_specific_widgets_visible(False)
        self._updating_ui = False

    def _refresh_ui(self) -> None:
        self._updating_ui = True
        current_object = self.current_object
        object_type = self.object_type
        package = self.current_package
        if not current_object:
            self._reset_ui()
            self._updating_ui = False
            return

        self.name_edit.setText(current_object.name)
        if hasattr(current_object, "description"):
            self.desc_edit.setPlainText(getattr(current_object, "description"))
        else:
            self.desc_edit.clear()

        # GUID 始终从当前对象 metadata 读取（模板/实例/关卡实体通用）
        self._refresh_guid_from_metadata(getattr(current_object, "metadata", None))

        is_template = object_type == "template"
        is_instance = object_type == "instance"
        is_level_entity = object_type == "level_entity"

        # 掉落物上下文判定
        is_drop_template = False
        template_for_instance: Optional[TemplateConfig] = None
        if is_template and isinstance(current_object, TemplateConfig):
            is_drop_template = is_drop_template_config(current_object)
        elif is_instance and isinstance(current_object, InstanceConfig) and isinstance(
            package, (PackageView, GlobalResourceView)
        ):
            template_for_instance = package.get_template(current_object.template_id)
            if isinstance(template_for_instance, TemplateConfig):
                is_drop_template = is_drop_template_config(template_for_instance)

        # 名称/描述标签文案
        if is_drop_template and is_template:
            self._name_label.setText("掉落物名称:")
            self._desc_label.setText("备注:")
            self.desc_edit.setPlaceholderText("输入备注信息...")
        else:
            self._name_label.setText("名称:")
            self._desc_label.setText("描述:")
            self.desc_edit.setPlaceholderText("输入描述信息...")

        if object_type == "template":
            if is_drop_template:
                self.type_label.setText("掉落物")
            else:
                self.type_label.setText(f"元件 - {current_object.entity_type}")
            self.position_widget.setVisible(False)
        elif object_type == "level_entity":
            self.type_label.setText("关卡实体（唯一，承载关卡逻辑）")
            self.position_widget.setVisible(False)
        else:
            instance = current_object
            template = template_for_instance or (package.get_template(instance.template_id) if package else None)
            if is_drop_template:
                template_type_text = "掉落物"
            else:
                template_type_text = template.entity_type if template else "未知"
            self.type_label.setText(f"实体 - {template_type_text}")
            x, y, z = instance.position
            self.pos_label.setText(f"({x:.1f}, {y:.1f}, {z:.1f})")
            self.position_widget.setVisible(True)

        # 掉落物专用字段（仅模板上下文可编辑，所属存档由面板统一管理）
        if is_template and is_drop_template and isinstance(current_object, TemplateConfig):
            # 掉落物模板：仅在标签页内展示模型ID；“所属存档”由面板级行统一管理
            self._set_drop_specific_widgets_visible(True)
            self._refresh_model_id_from_metadata(current_object.metadata)
        else:
            self._set_drop_specific_widgets_visible(False)
            self.model_id_edit.clear()

        self._updating_ui = False

    def get_basic_payload(self) -> dict:
        payload = {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.toPlainText().strip(),
        }

        # 仅对“掉落物模板”写回模型ID与标记
        drop_metadata: Optional[dict] = None
        if isinstance(self.current_object, TemplateConfig) and is_drop_template_config(self.current_object):
            drop_metadata = {
                "template_category": "掉落物",
                "is_drop_item": True,
            }
            model_id_text = self.model_id_edit.text().strip()
            if model_id_text:
                drop_metadata["drop_model_id"] = int(model_id_text)
            else:
                drop_metadata["drop_model_id"] = None
        payload["drop_metadata"] = drop_metadata

        # GUID：空字符串表示删除
        guid_text = self.guid_edit.text().strip()
        payload["guid"] = guid_text
        return payload

    def _adjust_desc_height(self) -> None:
        doc_height = self.desc_edit.document().size().height()
        new_height = int(doc_height + 20)
        new_height = max(120, min(500, new_height))
        if abs(self.desc_edit.height() - new_height) > 5:
            self.desc_edit.setFixedHeight(new_height)

    def _schedule_emit(self) -> None:
        if self._updating_ui:
            return
        self._debounce_timer.start()

    def _emit_data_changed(self) -> None:
        if self._updating_ui:
            return
        self.data_changed.emit()

    def flush_pending_changes(self) -> None:
        """在保存前显式刷新一次基础信息的去抖变更。

        用途：
        - 用户在名称/描述/GUID/模型ID 等字段中快速输入后立即保存或切换功能包时，
          确保尚未触发的去抖写回逻辑也能同步到当前对象。
        """
        if self._updating_ui:
            return
        if self._debounce_timer.isActive():
            self._debounce_timer.stop()
            self._emit_data_changed()

    # 只读模式 ---------------------------------------------------------------
    def set_read_only(self, read_only: bool) -> None:
        """切换基础信息标签页的只读状态。

        只读模式下：
        - 文本输入与描述编辑框设为 readOnly；
        - GUID / 模型ID 输入禁用；
        - “所属存档”选择器整体禁用，仅保留当前显示值；
        - 位置展示保持可见（本身即为只读标签）。
        """
        self._is_read_only = read_only
        self.name_edit.setReadOnly(read_only)
        self.guid_edit.setReadOnly(read_only)
        self.model_id_edit.setReadOnly(read_only)
        self.desc_edit.setReadOnly(read_only)

    # 掉落物 / 关卡实体辅助 ------------------------------------------------------------
    def _set_drop_specific_widgets_visible(self, visible: bool) -> None:
        """控制掉落物专用字段（模型ID）的显隐。"""
        for widget in (
            self._model_id_label,
            self.model_id_edit,
        ):
            widget.setVisible(visible)

    def _refresh_model_id_from_metadata(self, metadata: object) -> None:
        if not isinstance(metadata, dict):
            self.model_id_edit.setText("")
            return
        value = metadata.get("drop_model_id")
        if value is None:
            self.model_id_edit.setText("")
        else:
            self.model_id_edit.setText(str(value))

    def _refresh_model_id_from_metadata(self, metadata: object) -> None:
        if not isinstance(metadata, dict):
            self.model_id_edit.setText("")
            return
        value = metadata.get("drop_model_id")
        if value is None:
            self.model_id_edit.setText("")
        else:
            self.model_id_edit.setText(str(value))
    def _refresh_guid_from_metadata(self, metadata: object) -> None:
        """从 metadata 中刷新 GUID 输入框的显示值。"""
        if not isinstance(metadata, dict):
            self.guid_edit.setText("")
            return
        value = metadata.get("guid")
        if value is None:
            self.guid_edit.setText("")
        else:
            self.guid_edit.setText(str(value))


