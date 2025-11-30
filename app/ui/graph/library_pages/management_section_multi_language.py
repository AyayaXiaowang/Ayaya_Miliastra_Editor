from __future__ import annotations

from .management_sections_base import *
from ui.forms.schema_dialog import FormDialogBuilder


class MultiLanguageSection(BaseManagementSection):
    """多语言文本管理 Section（对应 `ManagementData.multi_language`）。"""

    section_key = "multi_language"
    tree_label = "🌐 多语言文本管理"
    type_name = "多语言文本"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for text_id, record_payload in package.management.multi_language.items():
            original_text_value = str(record_payload.get("original_text", ""))
            source_value = str(record_payload.get("source", ""))
            needs_translation_value = bool(record_payload.get("needs_translation", True))
            translations_mapping = record_payload.get("translations", {}) or {}
            translation_count = len(translations_mapping)
            description_value = str(record_payload.get("description", ""))

            attr1_text = f"ID: {text_id}"
            attr2_text = f"来源: {source_value}" if source_value else "来源: 未标记"
            attr3_text = (
                f"语言数: {translation_count}，需要翻译: "
                f"{'是' if needs_translation_value else '否'}"
            )

            yield ManagementRowData(
                name=original_text_value or text_id,
                type_name=self.type_name,
                attr1=attr1_text,
                attr2=attr2_text,
                attr3=attr3_text,
                description=description_value,
                last_modified=self._get_last_modified_text(record_payload),
                user_data=(self.section_key, text_id),
            )

    @staticmethod
    def _default_record() -> Dict[str, Any]:
        return {
            "original_text": "",
            "source": "",
            "needs_translation": True,
            "translations": {},
            "description": "",
            "metadata": {},
        }

    @staticmethod
    def _build_translations_text(translations: Optional[Dict[str, Any]]) -> str:
        if not translations:
            return ""
        lines: List[str] = []
        for language_code, translated_text in translations.items():
            if not language_code:
                continue
            lines.append(f"{language_code}={translated_text}")
        return "\n".join(lines)

    @staticmethod
    def _parse_translations(text_value: str) -> Dict[str, str]:
        translations: Dict[str, str] = {}
        for line_text in text_value.splitlines():
            stripped_line = line_text.strip()
            if not stripped_line or "=" not in stripped_line:
                continue
            key_text, value_text = stripped_line.split("=", 1)
            language_code = key_text.strip()
            translated_text = value_text.strip()
            if not language_code or not translated_text:
                continue
            translations[language_code] = translated_text
        return translations

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
            "text_id": "",
            "original_text": "",
            "source": "",
            "needs_translation": True,
            "translations_text": "",
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(560, 520))

        text_id_widget = builder.add_line_edit(
            "文本ID:",
            str(initial_values.get("text_id", "")),
            None,
            read_only=is_edit,
        )
        original_text_widget = builder.add_plain_text_edit(
            "原文:",
            str(initial_values.get("original_text", "")),
            min_height=80,
            max_height=200,
        )
        source_widget = builder.add_line_edit(
            "来源:",
            str(initial_values.get("source", "")),
        )
        needs_translation_widget = builder.add_check_box(
            "需要翻译",
            bool(initial_values.get("needs_translation", True)),
        )
        translations_widget = builder.add_plain_text_edit(
            "翻译（语言=文本，每行一条）",
            str(initial_values.get("translations_text", "")),
            min_height=120,
            max_height=220,
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from ui.foundation import dialog_utils

            text_id_text = text_id_widget.text().strip()
            if not text_id_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "文本 ID 不能为空",
                )
                return False
            if (not is_edit) and text_id_text in existing_ids:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "该文本 ID 已存在",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "text_id": text_id_widget.text().strip(),
            "original_text": original_text_widget.toPlainText().strip(),
            "source": source_widget.text().strip(),
            "needs_translation": bool(needs_translation_widget.isChecked()),
            "translations_text": translations_widget.toPlainText().strip(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        records_mapping = package.management.multi_language
        if not isinstance(records_mapping, dict):
            records_mapping = {}
            package.management.multi_language = records_mapping

        index = len(records_mapping) + 1
        text_id_value = f"text_{index}"
        while text_id_value in records_mapping:
            index += 1
            text_id_value = f"text_{index}"

        record_payload = self._default_record()
        record_payload["original_text"] = f"新文本{index}"
        records_mapping[text_id_value] = record_payload
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        record_payload = package.management.multi_language.get(item_id)
        if record_payload is None:
            return False

        translations_mapping = record_payload.get("translations", {}) or {}

        initial_values = {
            "text_id": item_id,
            "original_text": record_payload.get("original_text", ""),
            "source": record_payload.get("source", ""),
            "needs_translation": record_payload.get("needs_translation", True),
            "translations_text": self._build_translations_text(translations_mapping),
        }
        existing_ids = list(package.management.multi_language.keys())
        dialog_data = self._build_form(
            parent_widget,
            title="编辑多语言文本",
            is_edit=True,
            existing_ids=existing_ids,
            initial=initial_values,
        )
        if dialog_data is None:
            return False

        record_payload["original_text"] = dialog_data["original_text"]
        record_payload["source"] = dialog_data["source"]
        record_payload["needs_translation"] = dialog_data["needs_translation"]
        record_payload["translations"] = self._parse_translations(
            dialog_data["translations_text"],
        )
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id not in package.management.multi_language:
            return False
        package.management.multi_language.pop(item_id, None)
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑多语言文本的全部主要字段（含翻译文本）。"""
        record_payload_any = getattr(package.management, "multi_language", {}).get(item_id)
        if not isinstance(record_payload_any, dict):
            return None

        record_payload = record_payload_any

        def _configure_auto_growing_text_edit(
            text_edit: QtWidgets.QTextEdit,
            *,
            minimum_visible_lines: int = 2,
            maximum_height: int | None = None,
        ) -> None:
            """根据文本内容自动调整 QTextEdit 的可见高度。

            - 使用文档内容高度 + 边距作为基础高度；
            - 保证至少显示 `minimum_visible_lines` 行；
            - 如提供 `maximum_height`，则在该高度处封顶，避免极端长文本撑爆右侧面板。
            """

            font_metrics = text_edit.fontMetrics()
            line_spacing = font_metrics.lineSpacing()

            def update_height() -> None:
                document = text_edit.document()
                document_size = document.size()
                document_height = document_size.height()

                contents_margins = text_edit.contentsMargins()
                top_margin = contents_margins.top()
                bottom_margin = contents_margins.bottom()
                frame_width = text_edit.frameWidth() * 2

                minimum_height = int(
                    line_spacing * minimum_visible_lines
                    + top_margin
                    + bottom_margin
                    + frame_width
                )
                target_height = int(
                    document_height + top_margin + bottom_margin + frame_width
                )
                if target_height < minimum_height:
                    target_height = minimum_height
                if maximum_height is not None and target_height > maximum_height:
                    target_height = maximum_height

                text_edit.setMinimumHeight(target_height)
                text_edit.setMaximumHeight(target_height)
                text_edit.updateGeometry()

            text_edit.textChanged.connect(update_height)
            update_height()

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            original_text_value = str(record_payload.get("original_text", ""))
            source_value = str(record_payload.get("source", ""))
            needs_translation_value = bool(record_payload.get("needs_translation", True))
            translations_mapping = record_payload.get("translations", {}) or {}
            translations_text_value = self._build_translations_text(translations_mapping)
            description_value = str(record_payload.get("description", ""))

            original_text_edit = QtWidgets.QTextEdit()
            original_text_edit.setPlainText(original_text_value)
            _configure_auto_growing_text_edit(
                original_text_edit,
                minimum_visible_lines=3,
                maximum_height=260,
            )
            source_edit = QtWidgets.QLineEdit(source_value)
            needs_translation_checkbox = QtWidgets.QCheckBox("需要翻译")
            needs_translation_checkbox.setChecked(needs_translation_value)

            translations_edit = QtWidgets.QTextEdit()
            translations_edit.setPlainText(translations_text_value)
            _configure_auto_growing_text_edit(
                translations_edit,
                minimum_visible_lines=4,
                maximum_height=320,
            )

            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            _configure_auto_growing_text_edit(
                description_edit,
                minimum_visible_lines=2,
                maximum_height=220,
            )

            def apply_changes() -> None:
                record_payload["original_text"] = original_text_edit.toPlainText().strip()
                record_payload["source"] = source_edit.text().strip()
                record_payload["needs_translation"] = bool(needs_translation_checkbox.isChecked())
                record_payload["translations"] = self._parse_translations(
                    translations_edit.toPlainText().strip(),
                )
                record_payload["description"] = description_edit.toPlainText().strip()
                on_changed()

            original_text_edit.textChanged.connect(lambda: apply_changes())
            source_edit.editingFinished.connect(apply_changes)
            needs_translation_checkbox.stateChanged.connect(lambda _state: apply_changes())
            translations_edit.textChanged.connect(lambda: apply_changes())
            description_edit.textChanged.connect(lambda: apply_changes())

            form_layout.addRow("文本ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("原文", original_text_edit)
            form_layout.addRow("来源", source_edit)
            form_layout.addRow("", needs_translation_checkbox)
            form_layout.addRow("翻译（语言=文本，每行一条）", translations_edit)
            form_layout.addRow("说明", description_edit)

        display_name_value = str(record_payload.get("original_text", "")).strip()
        display_name = display_name_value or item_id

        title = f"多语言文本详情：{display_name}"
        description = "在右侧直接修改原文、来源、是否需要翻译以及各语言翻译内容和说明，修改会立即保存到当前视图。"
        return title, description, build_form



