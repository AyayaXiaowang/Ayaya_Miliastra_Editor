from __future__ import annotations

from .management_sections_base import *


class UnitTagSection(BaseManagementSection):
    """单位标签管理 Section（对应 `ManagementData.unit_tags`）。"""

    section_key = "unit_tags"
    tree_label = "🏷️ 单位标签管理"
    type_name = "单位标签"

    @staticmethod
    def _get_effective_tag_index(tag_id: str, tag_payload: Dict[str, Any]) -> Optional[int]:
        """从单位标签配置中提取当前生效的索引ID（兼容旧字段）。

        优先使用 `tag_index`（int 或数字字符串），
        若不存在则在 `tag_id` 字段或字典 key 为纯数字时作为回退。
        """
        raw_index = tag_payload.get("tag_index")
        if isinstance(raw_index, int):
            return raw_index
        if isinstance(raw_index, str) and raw_index.isdigit():
            return int(raw_index)

        tag_id_source_any = tag_payload.get("tag_id", tag_id)
        tag_id_text = str(tag_id_source_any)
        if tag_id_text.isdigit():
            return int(tag_id_text)

        return None

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for tag_id, tag_payload in package.management.unit_tags.items():
            if not isinstance(tag_payload, dict):
                continue
            tag_name_value = str(tag_payload.get("tag_name", ""))
            tag_index_value = self._get_effective_tag_index(tag_id, tag_payload)
            if tag_index_value is not None:
                index_text = str(tag_index_value)
            else:
                index_text = ""
            description_text = str(tag_payload.get("description", ""))

            yield ManagementRowData(
                name=tag_name_value or tag_id,
                type_name=self.type_name,
                attr1=f"索引ID: {index_text or '（未设置）'}",
                attr2="",
                attr3="",
                description=description_text,
                last_modified=self._get_last_modified_text(tag_payload),
                user_data=(self.section_key, tag_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
        is_edit: bool,
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "tag_name": "",
            "tag_index": None,
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(420, 220))

        tag_name_edit = builder.add_line_edit(
            "标签名称*:",
            str(initial_values.get("tag_name", "")),
            "请输入单位标签名称",
        )
        raw_index = initial_values.get("tag_index")
        if isinstance(raw_index, int):
            default_index_text = str(raw_index)
        elif isinstance(raw_index, str):
            default_index_text = raw_index
        else:
            default_index_text = ""
        tag_index_edit = builder.add_line_edit(
            "索引ID:",
            default_index_text,
            "可选，仅输入数字，例如 1073741825",
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from ui.foundation import dialog_utils

            if not tag_name_edit.text().strip():
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入标签名称",
                )
                return False

            index_text_value = tag_index_edit.text().strip()
            if index_text_value and not index_text_value.isdigit():
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "索引ID只能包含数字（可留空）。",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        index_text_value = tag_index_edit.text().strip()
        if index_text_value:
            tag_index_value: Optional[int] = int(index_text_value)
        else:
            tag_index_value = None

        return {
            "tag_name": tag_name_edit.text().strip(),
            "tag_index": tag_index_value,
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        existing_tags = package.management.unit_tags
        if not isinstance(existing_tags, dict):
            existing_tags = {}
            package.management.unit_tags = existing_tags

        tag_id = generate_prefixed_id("unit_tag")
        while tag_id in existing_tags:
            tag_id = generate_prefixed_id("unit_tag")

        default_index = len(existing_tags) + 1
        tag_name = f"单位标签{default_index}"

        payload: Dict[str, Any] = {
            "tag_name": tag_name,
        }
        existing_tags[tag_id] = payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        tag_payload = package.management.unit_tags.get(item_id)
        if tag_payload is None:
            return False

        initial_values = {
            "tag_name": tag_payload.get("tag_name", ""),
            "tag_index": self._get_effective_tag_index(item_id, tag_payload),
        }
        dialog_data = self._build_form(
            parent_widget,
            title="编辑单位标签",
            initial=initial_values,
            is_edit=True,
        )
        if dialog_data is None:
            return False

        tag_payload["tag_name"] = dialog_data["tag_name"]

        edited_index_value = dialog_data.get("tag_index")
        if edited_index_value is None:
            tag_payload.pop("tag_index", None)
        else:
            tag_payload["tag_index"] = int(edited_index_value)
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id not in package.management.unit_tags:
            return False
        package.management.unit_tags.pop(item_id, None)
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑单位标签的基础字段。"""
        unit_tags_mapping = getattr(package.management, "unit_tags", None)
        if not isinstance(unit_tags_mapping, dict):
            return None
        tag_payload_any = unit_tags_mapping.get(item_id)
        if not isinstance(tag_payload_any, dict):
            return None

        tag_payload = tag_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            tag_name_value = str(tag_payload.get("tag_name", ""))
            tag_index_value = self._get_effective_tag_index(item_id, tag_payload)
            if tag_index_value is not None:
                index_text = str(tag_index_value)
            else:
                index_text = ""

            name_edit = QtWidgets.QLineEdit(tag_name_value)
            index_edit = QtWidgets.QLineEdit(index_text)
            index_edit.setPlaceholderText("可选，仅输入数字，例如 1073741825")

            last_valid_index_text = index_text

            def apply_changes() -> None:
                nonlocal last_valid_index_text

                normalized_name = name_edit.text().strip()
                if normalized_name:
                    tag_payload["tag_name"] = normalized_name
                else:
                    tag_payload["tag_name"] = item_id

                index_text_after = index_edit.text().strip()
                if index_text_after and not index_text_after.isdigit():
                    index_edit.setText(last_valid_index_text)
                    on_changed()
                    return

                if index_text_after:
                    tag_payload["tag_index"] = int(index_text_after)
                    last_valid_index_text = index_text_after
                else:
                    tag_payload.pop("tag_index", None)
                    last_valid_index_text = ""
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            index_edit.editingFinished.connect(apply_changes)

            form_layout.addRow("标签ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("标签名称", name_edit)
            form_layout.addRow("索引ID", index_edit)

        display_name_value = str(tag_payload.get("tag_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"单位标签详情：{display_name}"
        description = "在右侧直接修改单位标签的名称与索引ID（可选、纯数字），修改会立即保存到当前视图。"
        return title, description, build_form