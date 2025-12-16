from __future__ import annotations

from .management_sections_base import *
from app.ui.forms.schema_dialog import FormDialogBuilder


class BackgroundMusicSection(BaseManagementSection):
    """背景音乐管理 Section（对应 `ManagementData.background_music`）。"""

    section_key = "background_music"
    tree_label = "🎵 背景音乐管理"
    type_name = "背景音乐"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        music_map = package.management.background_music
        if not isinstance(music_map, dict):
            return

        for music_id, music_payload in music_map.items():
            if not isinstance(music_payload, dict):
                continue

            music_name_value = str(music_payload.get("music_name", "")) or music_id
            audio_file_value = str(music_payload.get("audio_file", ""))
            volume_value = float(music_payload.get("volume", 1.0))
            loop_enabled = bool(music_payload.get("loop", True))
            description_value = str(music_payload.get("description", ""))

            attr1_text = (
                f"音频: {audio_file_value}" if audio_file_value else "音频: 未设置"
            )
            attr2_text = f"音量: {volume_value:.2f}"
            attr3_text = f"循环: {'是' if loop_enabled else '否'}"

            yield ManagementRowData(
                name=music_name_value,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_value,
                last_modified=self._get_last_modified_text(music_payload),
                user_data=(self.section_key, music_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
        is_edit: bool,
        existing_ids: Sequence[str],
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "music_id": "",
            "music_name": "",
            "audio_file": "",
            "volume": 1.0,
            "loop": True,
            "fade_in_duration": 0.0,
            "fade_out_duration": 0.0,
            "trigger_condition": "",
            "description": "",
        }
        if initial:
            initial_values.update(initial)

        existing_id_set = {str(value) for value in existing_ids}

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(480, 520))

        music_id_edit = builder.add_line_edit(
            "音乐ID:",
            str(initial_values.get("music_id", "")),
            "用于在系统中引用该背景音乐",
            read_only=is_edit,
        )
        if is_edit:
            music_id_edit.setStyleSheet(ThemeManager.readonly_input_style())

        name_edit = builder.add_line_edit(
            "音乐名称:",
            str(initial_values.get("music_name", "")),
            "请输入显示名称",
        )
        file_edit = builder.add_line_edit(
            "音频文件路径:",
            str(initial_values.get("audio_file", "")),
            "例如: audio/theme.wav",
        )
        volume_spin = builder.add_double_spin_box(
            "音量(0-1):",
            minimum=0.0,
            maximum=1.0,
            value=float(initial_values.get("volume", 1.0)),
            decimals=2,
            single_step=0.1,
        )
        loop_check = builder.add_check_box(
            "循环播放",
            bool(initial_values.get("loop", True)),
        )
        fade_in_spin = builder.add_double_spin_box(
            "淡入时长(秒):",
            minimum=0.0,
            maximum=10.0,
            value=float(initial_values.get("fade_in_duration", 0.0)),
            decimals=2,
            single_step=0.1,
        )
        fade_out_spin = builder.add_double_spin_box(
            "淡出时长(秒):",
            minimum=0.0,
            maximum=10.0,
            value=float(initial_values.get("fade_out_duration", 0.0)),
            decimals=2,
            single_step=0.1,
        )
        trigger_edit = builder.add_line_edit(
            "触发条件:",
            str(initial_values.get("trigger_condition", "")),
            "可选: 填写触发条件说明",
        )
        description_edit = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=100,
            max_height=220,
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from app.ui.foundation import dialog_utils

            music_id_text = music_id_edit.text().strip()
            if not music_id_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "音乐ID 不能为空",
                )
                return False
            if not is_edit and music_id_text in existing_id_set:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "该音乐ID 已存在",
                )
                return False
            if not name_edit.text().strip():
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入音乐名称",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "music_id": music_id_edit.text().strip(),
            "music_name": name_edit.text().strip(),
            "audio_file": file_edit.text().strip(),
            "volume": float(volume_spin.value()),
            "loop": bool(loop_check.isChecked()),
            "fade_in_duration": float(fade_in_spin.value()),
            "fade_out_duration": float(fade_out_spin.value()),
            "trigger_condition": trigger_edit.text().strip(),
            "description": description_edit.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        music_map = package.management.background_music
        if not isinstance(music_map, dict):
            music_map = {}
            package.management.background_music = music_map

        existing_ids = set(music_map.keys())
        music_id_value = generate_prefixed_id("music")
        while music_id_value in existing_ids:
            music_id_value = generate_prefixed_id("music")

        default_index = len(music_map) + 1
        music_name_value = f"背景音乐{default_index}"

        music_config = BackgroundMusicConfig(
            music_id=music_id_value,
            music_name=music_name_value,
        )
        music_map[music_config.music_id] = music_config.serialize()
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        music_map = package.management.background_music
        if not isinstance(music_map, dict):
            return False

        music_payload = music_map.get(item_id)
        if not isinstance(music_payload, dict):
            return False

        initial_values = dict(music_payload)
        initial_values["music_id"] = item_id
        existing_ids: Sequence[str] = list(music_map.keys())

        dialog_data = self._build_form(
            parent_widget,
            title="编辑背景音乐",
            initial=initial_values,
            is_edit=True,
            existing_ids=existing_ids,
        )
        if dialog_data is None:
            return False

        target = music_map[item_id]
        target["music_name"] = dialog_data["music_name"]
        target["audio_file"] = dialog_data["audio_file"]
        target["volume"] = dialog_data["volume"]
        target["loop"] = dialog_data["loop"]
        target["fade_in_duration"] = dialog_data["fade_in_duration"]
        target["fade_out_duration"] = dialog_data["fade_out_duration"]
        target["trigger_condition"] = dialog_data["trigger_condition"]
        target["description"] = dialog_data["description"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        music_map = package.management.background_music
        if not isinstance(music_map, dict):
            return False
        if item_id not in music_map:
            return False
        del music_map[item_id]
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑背景音乐的全部主要字段。"""
        music_map = getattr(package.management, "background_music", None)
        if not isinstance(music_map, dict):
            return None
        music_payload_any = music_map.get(item_id)
        if not isinstance(music_payload_any, dict):
            return None

        music_payload = music_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            music_name_value = str(music_payload.get("music_name", ""))
            audio_file_value = str(music_payload.get("audio_file", ""))
            volume_any = music_payload.get("volume", 1.0)
            if isinstance(volume_any, (int, float)):
                volume_value = float(volume_any)
            else:
                volume_value = 1.0
            loop_enabled = bool(music_payload.get("loop", True))
            fade_in_any = music_payload.get("fade_in_duration", 0.0)
            fade_in_value = float(fade_in_any if isinstance(fade_in_any, (int, float)) else 0.0)
            fade_out_any = music_payload.get("fade_out_duration", 0.0)
            fade_out_value = float(fade_out_any if isinstance(fade_out_any, (int, float)) else 0.0)
            trigger_condition_value = str(music_payload.get("trigger_condition", ""))
            description_value = str(music_payload.get("description", ""))

            name_edit = QtWidgets.QLineEdit(music_name_value)
            file_edit = QtWidgets.QLineEdit(audio_file_value)

            volume_spin = QtWidgets.QDoubleSpinBox()
            volume_spin.setRange(0.0, 1.0)
            volume_spin.setDecimals(2)
            volume_spin.setSingleStep(0.1)
            volume_spin.setValue(volume_value)

            loop_check = QtWidgets.QCheckBox("循环播放")
            loop_check.setChecked(loop_enabled)

            fade_in_spin = QtWidgets.QDoubleSpinBox()
            fade_in_spin.setRange(0.0, 10.0)
            fade_in_spin.setDecimals(2)
            fade_in_spin.setSingleStep(0.1)
            fade_in_spin.setValue(fade_in_value)

            fade_out_spin = QtWidgets.QDoubleSpinBox()
            fade_out_spin.setRange(0.0, 10.0)
            fade_out_spin.setDecimals(2)
            fade_out_spin.setSingleStep(0.1)
            fade_out_spin.setValue(fade_out_value)

            trigger_edit = QtWidgets.QLineEdit(trigger_condition_value)

            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(80)
            description_edit.setMaximumHeight(200)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    music_payload["music_name"] = normalized_name
                else:
                    music_payload["music_name"] = item_id
                music_payload["audio_file"] = file_edit.text().strip()
                music_payload["volume"] = float(volume_spin.value())
                music_payload["loop"] = bool(loop_check.isChecked())
                music_payload["fade_in_duration"] = float(fade_in_spin.value())
                music_payload["fade_out_duration"] = float(fade_out_spin.value())
                music_payload["trigger_condition"] = trigger_edit.text().strip()
                music_payload["description"] = description_edit.toPlainText().strip()
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            file_edit.editingFinished.connect(apply_changes)
            volume_spin.editingFinished.connect(apply_changes)
            loop_check.stateChanged.connect(lambda _state: apply_changes())
            fade_in_spin.editingFinished.connect(apply_changes)
            fade_out_spin.editingFinished.connect(apply_changes)
            trigger_edit.editingFinished.connect(apply_changes)
            description_edit.textChanged.connect(lambda: apply_changes())

            form_layout.addRow("音乐ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("音乐名称", name_edit)
            form_layout.addRow("音频文件", file_edit)
            form_layout.addRow("音量(0-1)", volume_spin)
            form_layout.addRow("循环播放", loop_check)
            form_layout.addRow("淡入时长(秒)", fade_in_spin)
            form_layout.addRow("淡出时长(秒)", fade_out_spin)
            form_layout.addRow("触发条件", trigger_edit)
            form_layout.addRow("描述", description_edit)

        display_name_value = str(music_payload.get("music_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"背景音乐详情：{display_name}"
        description = "在右侧直接修改音乐名称、音频文件路径与描述，修改会立即保存到当前视图。"
        return title, description, build_form



