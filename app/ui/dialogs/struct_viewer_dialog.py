"""只读结构体查看对话框。

为只读的结构体字段提供"查看"入口，以只读模式展示结构体定义的详细字段列表。
"""
from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence

from PyQt6 import QtWidgets

from engine.graph.models.entity_templates import get_all_variable_types
from ui.dialogs.struct_definition_dialog_impl import StructDefinitionEditorWidget
from ui.dialogs.struct_definition_types import param_type_to_canonical
from ui.foundation.base_widgets import BaseDialog
from ui.foundation.theme_manager import Sizes, ThemeManager


class StructViewerDialog(BaseDialog):
    """只读结构体查看对话框。

    以只读模式展示结构体定义的详细字段列表，
    用于"玩家模板自定义变量"等不可编辑场景下查看结构体详情。
    """

    def __init__(
        self,
        *,
        struct_id: str,
        struct_payload: Optional[Mapping[str, object]],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        self._struct_id = struct_id
        self._struct_payload = struct_payload

        super().__init__(
            title=f"查看结构体：{struct_id}",
            width=640,
            height=480,
            parent=parent,
        )
        self._build_content()

    def _build_content(self) -> None:
        layout = self.content_layout
        layout.setContentsMargins(
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
            Sizes.PADDING_MEDIUM,
        )
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        # 提示信息
        info_label = QtWidgets.QLabel(
            f"结构体 ID：{self._struct_id}\n"
            "以下为该结构体的字段定义，仅供查看。"
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(info_label)

        # 使用只读模式的结构体编辑器组件
        supported_types = list(get_all_variable_types())
        self._editor = StructDefinitionEditorWidget(
            parent=self,
            supported_types=supported_types,
        )
        self._editor.set_read_only(True)
        layout.addWidget(self._editor, 1)

        # 加载结构体数据
        self._load_struct_data()

    def _load_struct_data(self) -> None:
        """加载并展示结构体数据。"""
        if not self._struct_payload:
            self._editor.load_struct(
                struct_name="（未找到结构体定义）",
                fields=[],
                allow_edit_name=False,
            )
            return

        # 提取结构体名称
        struct_name_value = self._struct_payload.get("name")
        struct_name = (
            str(struct_name_value).strip()
            if isinstance(struct_name_value, str)
            else self._struct_id
        )

        # 提取字段列表
        fields: List[Dict[str, object]] = []
        value_entries = self._struct_payload.get("value")
        if isinstance(value_entries, Sequence):
            for entry in value_entries:
                if not isinstance(entry, Mapping):
                    continue
                raw_key = entry.get("key")
                raw_param_type = entry.get("param_type")
                raw_value = entry.get("value")

                field_name = (
                    str(raw_key).strip() if isinstance(raw_key, str) else ""
                )
                param_type = (
                    str(raw_param_type).strip()
                    if isinstance(raw_param_type, str)
                    else ""
                )

                if not field_name or not param_type:
                    continue

                canonical_type = param_type_to_canonical(param_type)
                fields.append({
                    "name": field_name,
                    "type_name": canonical_type,
                    "value_node": raw_value,
                })

        self._editor.load_struct(
            struct_name=struct_name,
            fields=fields,
            allow_edit_name=False,
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            ThemeManager.dialog_surface_style(
                include_inputs=True,
                include_tables=True,
                include_scrollbars=True,
            )
        )

    def _create_buttons(self) -> None:
        """只提供"关闭"按钮，不提供"确定/取消"。"""
        close_button = QtWidgets.QPushButton("关闭", self)
        close_button.setFixedHeight(Sizes.BUTTON_HEIGHT)
        close_button.setMinimumWidth(80)
        close_button.clicked.connect(self.reject)
        self.button_layout.addStretch()
        self.button_layout.addWidget(close_button)


__all__ = ["StructViewerDialog"]

