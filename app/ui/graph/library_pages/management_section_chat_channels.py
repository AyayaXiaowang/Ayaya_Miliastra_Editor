from __future__ import annotations

from .management_sections_base import *


class ChatChannelsSection(BaseManagementSection):
    """文字聊天管理 Section（对应 `ManagementData.chat_channels`）。"""

    section_key = "chat_channels"
    tree_label = "💬 文字聊天管理"
    type_name = "聊天频道"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for channel_id, channel_payload in package.management.chat_channels.items():
            channel_name_value = str(channel_payload.get("channel_name", ""))
            color_value = str(
                channel_payload.get("color", ThemeManager.Colors.TEXT_ON_PRIMARY)
            )
            apply_mode_value = str(channel_payload.get("apply_mode", "all_players"))
            priority_value = channel_payload.get("priority", 0)
            description_value = str(channel_payload.get("description", ""))

            _ = color_value

            attr1_text = f"频道ID: {channel_id}"
            attr2_text = f"应用方式: {apply_mode_value}"
            attr3_text = f"显示优先级: {priority_value}"

            yield ManagementRowData(
                name=channel_name_value or channel_id,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_value,
                last_modified=self._get_last_modified_text(channel_payload),
                user_data=(self.section_key, channel_id),
            )

    @staticmethod
    def _build_quick_messages_text(raw_value: Any) -> str:
        if not isinstance(raw_value, list):
            return ""
        messages: List[str] = []
        for message in raw_value:
            if not message:
                continue
            messages.append(str(message))
        return "\n".join(messages)

    @staticmethod
    def _parse_quick_messages(text_value: str) -> List[str]:
        if not isinstance(text_value, str):
            return []
        stripped_text = text_value.strip()
        if not stripped_text:
            return []
        messages: List[str] = []
        for line_text in stripped_text.splitlines():
            message_text = line_text.strip()
            if not message_text:
                continue
            messages.append(message_text)
        return messages

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        is_edit: bool,
        existing_ids: Sequence[str],
        initial: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "channel_id": "",
            "channel_name": "",
            "color": ThemeManager.Colors.TEXT_ON_PRIMARY,
            "apply_mode": "all_players",
            "priority": 0,
            "icon": "",
            "quick_messages_text": "",
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(460, 420))

        channel_id_widget = builder.add_line_edit(
            "频道ID:",
            str(initial_values.get("channel_id", "")),
            None,
            read_only=is_edit,
        )
        name_widget = builder.add_line_edit(
            "频道名称:",
            str(initial_values.get("channel_name", "")),
        )
        color_widget = builder.add_color_picker(
            "颜色:",
            str(initial_values.get("color", ThemeManager.Colors.TEXT_ON_PRIMARY)),
        )
        apply_mode_widget = builder.add_combo_box(
            "应用方式:",
            ["all_players", "by_team", "by_faction", "custom"],
            current_text=str(initial_values.get("apply_mode", "all_players")),
        )
        priority_widget = builder.add_spin_box(
            "显示优先级:",
            minimum=0,
            maximum=100,
            value=int(initial_values.get("priority", 0)),
            single_step=1,
        )
        icon_widget = builder.add_line_edit(
            "图标:",
            str(initial_values.get("icon", "")),
        )
        quick_messages_widget = builder.add_plain_text_edit(
            "快捷消息:",
            str(initial_values.get("quick_messages_text", "")),
            min_height=100,
            max_height=140,
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from app.ui.foundation import dialog_utils

            channel_id_text = channel_id_widget.text().strip()
            if not channel_id_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "频道 ID 不能为空",
                )
                return False
            if (not is_edit) and channel_id_text in existing_ids:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "该频道 ID 已存在",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "channel_id": channel_id_widget.text().strip(),
            "channel_name": name_widget.text().strip(),
            "color": color_widget.text().strip(),
            "apply_mode": str(apply_mode_widget.currentText()),
            "priority": int(priority_widget.value()),
            "icon": icon_widget.text().strip(),
            "quick_messages_text": quick_messages_widget.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        channels_mapping = package.management.chat_channels
        if not isinstance(channels_mapping, dict):
            channels_mapping = {}
            package.management.chat_channels = channels_mapping

        existing_ids = set(channels_mapping.keys())
        channel_id_value = generate_prefixed_id("chat_channel")
        while channel_id_value in existing_ids:
            channel_id_value = generate_prefixed_id("chat_channel")

        default_index = len(channels_mapping) + 1
        channel_name = f"聊天频道{default_index}"

        channel_config = ChatChannelConfig(
            channel_id=channel_id_value,
            channel_name=channel_name,
        )
        payload = channel_config.serialize()
        payload["color"] = ThemeManager.Colors.TEXT_ON_PRIMARY
        payload["apply_mode"] = "all_players"
        payload["priority"] = 0
        payload["icon"] = ""
        payload["quick_messages"] = []

        channels_mapping[channel_id_value] = payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        channel_payload = package.management.chat_channels.get(item_id)
        if channel_payload is None:
            return False

        quick_messages_text = self._build_quick_messages_text(
            channel_payload.get("quick_messages", [])
        )

        initial_values = {
            "channel_id": item_id,
            "channel_name": channel_payload.get("channel_name", ""),
            "color": channel_payload.get("color", ThemeManager.Colors.TEXT_ON_PRIMARY),
            "apply_mode": channel_payload.get("apply_mode", "all_players"),
            "priority": channel_payload.get("priority", 0),
            "icon": channel_payload.get("icon", ""),
            "quick_messages_text": quick_messages_text,
        }
        existing_ids = list(package.management.chat_channels.keys())
        dialog_data = self._build_form(
            parent_widget,
            title="编辑聊天频道",
            is_edit=True,
            existing_ids=existing_ids,
            initial=initial_values,
        )
        if dialog_data is None:
            return False

        channel_payload["channel_name"] = dialog_data["channel_name"]
        channel_payload["color"] = dialog_data["color"]
        channel_payload["apply_mode"] = dialog_data["apply_mode"]
        channel_payload["priority"] = dialog_data["priority"]
        channel_payload["icon"] = dialog_data["icon"]
        channel_payload["quick_messages"] = self._parse_quick_messages(
            dialog_data["quick_messages_text"]
        )
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id not in package.management.chat_channels:
            return False
        package.management.chat_channels.pop(item_id, None)
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑聊天频道的全部主要字段。"""
        channels_mapping = getattr(package.management, "chat_channels", None)
        if not isinstance(channels_mapping, dict):
            return None
        channel_payload_any = channels_mapping.get(item_id)
        if not isinstance(channel_payload_any, dict):
            return None

        channel_payload = channel_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            channel_name_value = str(channel_payload.get("channel_name", ""))
            color_value = str(
                channel_payload.get("color", ThemeManager.Colors.TEXT_ON_PRIMARY)
            )
            apply_mode_value = str(channel_payload.get("apply_mode", "all_players"))
            priority_any = channel_payload.get("priority", 0)
            if isinstance(priority_any, int):
                priority_value = priority_any
            else:
                priority_value = 0
            icon_value = str(channel_payload.get("icon", ""))
            quick_messages_text = self._build_quick_messages_text(
                channel_payload.get("quick_messages", []),
            )
            description_value = str(channel_payload.get("description", ""))

            name_edit = QtWidgets.QLineEdit(channel_name_value)
            color_edit = QtWidgets.QLineEdit(color_value)

            apply_mode_widget = QtWidgets.QComboBox()
            apply_mode_widget.addItems(["all_players", "by_team", "by_faction", "custom"])
            if apply_mode_value:
                apply_mode_widget.setCurrentText(apply_mode_value)

            priority_widget = QtWidgets.QSpinBox()
            priority_widget.setRange(0, 100)
            priority_widget.setValue(priority_value)

            icon_edit = QtWidgets.QLineEdit(icon_value)

            quick_messages_edit = QtWidgets.QTextEdit()
            quick_messages_edit.setPlainText(quick_messages_text)
            quick_messages_edit.setMinimumHeight(100)
            quick_messages_edit.setMaximumHeight(140)

            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(80)
            description_edit.setMaximumHeight(200)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    channel_payload["channel_name"] = normalized_name
                else:
                    channel_payload["channel_name"] = item_id
                channel_payload["color"] = (
                    color_edit.text().strip() or ThemeManager.Colors.TEXT_ON_PRIMARY
                )
                channel_payload["apply_mode"] = str(apply_mode_widget.currentText())
                channel_payload["priority"] = int(priority_widget.value())
                channel_payload["icon"] = icon_edit.text().strip()
                channel_payload["quick_messages"] = self._parse_quick_messages(
                    quick_messages_edit.toPlainText().strip(),
                )
                channel_payload["description"] = description_edit.toPlainText().strip()
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            color_edit.editingFinished.connect(apply_changes)
            apply_mode_widget.currentIndexChanged.connect(lambda _index: apply_changes())
            priority_widget.editingFinished.connect(apply_changes)
            icon_edit.editingFinished.connect(apply_changes)
            quick_messages_edit.textChanged.connect(lambda: apply_changes())
            description_edit.textChanged.connect(lambda: apply_changes())

            form_layout.addRow("频道ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("频道名称", name_edit)
            form_layout.addRow("颜色", color_edit)
            form_layout.addRow("应用方式", apply_mode_widget)
            form_layout.addRow("显示优先级", priority_widget)
            form_layout.addRow("图标", icon_edit)
            form_layout.addRow("快捷消息", quick_messages_edit)
            form_layout.addRow("描述", description_edit)

        display_name_value = str(channel_payload.get("channel_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"聊天频道详情：{display_name}"
        description = "在右侧直接修改频道名称、颜色、应用方式、优先级、图标、快捷消息与描述，修改会立即保存到当前视图。"
        return title, description, build_form



