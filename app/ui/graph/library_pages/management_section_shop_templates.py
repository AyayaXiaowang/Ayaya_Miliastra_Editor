from __future__ import annotations

from .management_sections_base import *
from app.ui.forms.schema_dialog import FormDialogBuilder


class ShopTemplatesSection(BaseManagementSection):
    """商店模板管理 Section（对应 `ManagementData.shop_templates`）。"""

    section_key = "shop_templates"
    tree_label = "🏪 商店模板管理"
    type_name = "商店模板"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        templates_mapping = package.management.shop_templates
        if not isinstance(templates_mapping, dict):
            return

        for shop_identifier, shop_payload in templates_mapping.items():
            if not isinstance(shop_payload, dict):
                continue

            shop_name_text = str(shop_payload.get("shop_name", ""))
            shop_type_value = str(shop_payload.get("shop_type", "general"))
            currency_type_value = str(shop_payload.get("currency_type", "gold"))
            available_items_value = shop_payload.get("available_items", [])
            if isinstance(available_items_value, list):
                item_count_value = len(available_items_value)
            else:
                item_count_value = 0
            description_text = str(shop_payload.get("description", ""))

            yield ManagementRowData(
                name=shop_name_text or str(shop_identifier),
                type_name=self.type_name,
                attr1=f"类型: {shop_type_value}",
                attr2=f"货币: {currency_type_value}",
                attr3=f"商品数量: {item_count_value}",
                description=description_text,
                last_modified=self._get_last_modified_text(shop_payload),
                user_data=(self.section_key, str(shop_identifier)),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
        existing_ids: Optional[Iterable[str]] = None,
        is_edit: bool = False,
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "shop_id": "",
            "shop_name": "",
            "shop_type": "general",
            "currency_type": "gold",
            "refresh_interval": 0.0,
            "available_items_text": "",
            "description": "",
        }
        if initial:
            initial_values.update(initial)

        existing_identifier_set: set[str] = set()
        if existing_ids is not None:
            existing_identifier_set = {
                str(identifier)
                for identifier in existing_ids
                if isinstance(identifier, str)
            }

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(480, 420))

        if is_edit:
            shop_identifier_line_edit = builder.add_line_edit(
                "商店ID:",
                str(initial_values.get("shop_id", "")),
                read_only=True,
            )
        else:
            shop_identifier_line_edit = builder.add_line_edit(
                "商店ID*:",
                str(initial_values.get("shop_id", "")),
                "请输入唯一的商店ID",
            )

        shop_name_line_edit = builder.add_line_edit(
            "商店名称*:",
            str(initial_values.get("shop_name", "")),
            "请输入商店名称",
        )
        shop_type_combo_box = builder.add_combo_box(
            "商店类型:",
            ["general", "equipment", "consumable", "special"],
            str(initial_values.get("shop_type", "general")),
        )
        currency_type_line_edit = builder.add_line_edit(
            "货币类型:",
            str(initial_values.get("currency_type", "gold")),
            "示例：gold / gem / ticket",
        )
        refresh_interval_spin_box = builder.add_double_spin_box(
            "刷新间隔(秒):",
            minimum=0.0,
            maximum=86400.0,
            value=float(initial_values.get("refresh_interval", 0.0)),
            decimals=1,
            single_step=1.0,
            suffix=" 秒",
        )
        available_items_text_edit = builder.add_plain_text_edit(
            "可用商品:",
            str(initial_values.get("available_items_text", "")),
            min_height=80,
            max_height=160,
        )
        available_items_text_edit.setPlaceholderText("每行一个商品ID")

        description_text_edit = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=80,
            max_height=200,
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from app.ui.foundation import dialog_utils

            shop_identifier_value = shop_identifier_line_edit.text().strip()
            if not shop_identifier_value:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入商店ID",
                )
                return False
            if not is_edit and shop_identifier_value in existing_identifier_set:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "该商店ID已存在",
                )
                return False
            if not shop_name_line_edit.text().strip():
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入商店名称",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        shop_identifier_value = shop_identifier_line_edit.text().strip()
        available_items_text = available_items_text_edit.toPlainText().strip()
        available_items_list = [
            line.strip()
            for line in available_items_text.splitlines()
            if line.strip()
        ]

        return {
            "shop_id": shop_identifier_value,
            "shop_name": shop_name_line_edit.text().strip(),
            "shop_type": str(shop_type_combo_box.currentText()),
            "currency_type": currency_type_line_edit.text().strip() or "gold",
            "refresh_interval": float(refresh_interval_spin_box.value()),
            "available_items": available_items_list,
            "description": description_text_edit.toPlainText(),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        templates_mapping = package.management.shop_templates
        if not isinstance(templates_mapping, dict):
            templates_mapping = {}
            package.management.shop_templates = templates_mapping

        existing_ids = set(templates_mapping.keys())
        index = len(existing_ids) + 1
        shop_id_value = f"shop_{index}"
        while shop_id_value in existing_ids:
            index += 1
            shop_id_value = f"shop_{index}"

        shop_template_config = ShopTemplateConfig(
            shop_id=shop_id_value,
            shop_name=f"商店{index}",
        )
        templates_mapping[shop_template_config.shop_id] = shop_template_config.serialize()
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        templates_mapping = package.management.shop_templates
        if not isinstance(templates_mapping, dict):
            return False

        shop_payload = templates_mapping.get(item_id)
        if not isinstance(shop_payload, dict):
            return False

        available_items_value = shop_payload.get("available_items", [])
        if isinstance(available_items_value, list):
            available_items_text = "\n".join(str(entry) for entry in available_items_value)
        else:
            available_items_text = ""

        initial_values = {
            "shop_id": item_id,
            "shop_name": shop_payload.get("shop_name", ""),
            "shop_type": shop_payload.get("shop_type", "general"),
            "currency_type": shop_payload.get("currency_type", "gold"),
            "refresh_interval": shop_payload.get("refresh_interval", 0.0),
            "available_items_text": available_items_text,
            "description": shop_payload.get("description", ""),
        }

        dialog_data = self._build_form(
            parent_widget,
            title="编辑商店模板",
            initial=initial_values,
            existing_ids=None,
            is_edit=True,
        )
        if dialog_data is None:
            return False

        shop_payload["shop_name"] = dialog_data["shop_name"]
        shop_payload["shop_type"] = dialog_data["shop_type"]
        shop_payload["currency_type"] = dialog_data["currency_type"]
        shop_payload["refresh_interval"] = dialog_data["refresh_interval"]
        shop_payload["available_items"] = dialog_data["available_items"]
        shop_payload["description"] = dialog_data["description"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        templates_mapping = package.management.shop_templates
        if not isinstance(templates_mapping, dict):
            return False
        if item_id not in templates_mapping:
            return False
        del templates_mapping[item_id]
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑商店模板的全部主要字段。"""
        templates_mapping = getattr(package.management, "shop_templates", None)
        if not isinstance(templates_mapping, dict):
            return None
        shop_payload_any = templates_mapping.get(item_id)
        if not isinstance(shop_payload_any, dict):
            return None

        shop_payload = shop_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            shop_name_value = str(shop_payload.get("shop_name", ""))
            shop_type_value = str(shop_payload.get("shop_type", "general"))
            currency_type_value = str(shop_payload.get("currency_type", "gold"))
            refresh_interval_any = shop_payload.get("refresh_interval", 0.0)
            if isinstance(refresh_interval_any, (int, float)):
                refresh_interval_value = float(refresh_interval_any)
            else:
                refresh_interval_value = 0.0
            available_items_value = shop_payload.get("available_items", [])
            if isinstance(available_items_value, list):
                available_items_text = "\n".join(str(entry) for entry in available_items_value)
            else:
                available_items_text = ""
            description_value = str(shop_payload.get("description", ""))

            name_edit = QtWidgets.QLineEdit(shop_name_value)

            shop_type_combo_box = QtWidgets.QComboBox()
            shop_type_combo_box.addItems(["general", "equipment", "consumable", "special"])
            if shop_type_value:
                shop_type_combo_box.setCurrentText(shop_type_value)

            currency_type_line_edit = QtWidgets.QLineEdit(currency_type_value)
            currency_type_line_edit.setPlaceholderText("示例：gold / gem / ticket")

            refresh_interval_spin_box = QtWidgets.QDoubleSpinBox()
            refresh_interval_spin_box.setRange(0.0, 86400.0)
            refresh_interval_spin_box.setDecimals(1)
            refresh_interval_spin_box.setSingleStep(1.0)
            refresh_interval_spin_box.setValue(refresh_interval_value)

            available_items_text_edit = QtWidgets.QTextEdit()
            available_items_text_edit.setPlainText(available_items_text)
            available_items_text_edit.setMinimumHeight(80)
            available_items_text_edit.setMaximumHeight(160)
            available_items_text_edit.setPlaceholderText("每行一个商品ID")

            description_text_edit = QtWidgets.QTextEdit()
            description_text_edit.setPlainText(description_value)
            description_text_edit.setMinimumHeight(80)
            description_text_edit.setMaximumHeight(200)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    shop_payload["shop_name"] = normalized_name
                else:
                    shop_payload["shop_name"] = item_id
                shop_payload["shop_type"] = str(shop_type_combo_box.currentText())
                shop_payload["currency_type"] = (
                    currency_type_line_edit.text().strip() or "gold"
                )
                shop_payload["refresh_interval"] = float(
                    refresh_interval_spin_box.value(),
                )
                items_text = available_items_text_edit.toPlainText().strip()
                items_list = [
                    line.strip() for line in items_text.splitlines() if line.strip()
                ]
                shop_payload["available_items"] = items_list
                shop_payload["description"] = description_text_edit.toPlainText()
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            shop_type_combo_box.currentIndexChanged.connect(lambda _index: apply_changes())
            currency_type_line_edit.editingFinished.connect(apply_changes)
            refresh_interval_spin_box.editingFinished.connect(apply_changes)
            available_items_text_edit.textChanged.connect(lambda: apply_changes())
            description_text_edit.textChanged.connect(lambda: apply_changes())

            form_layout.addRow("商店ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("商店名称", name_edit)
            form_layout.addRow("商店类型", shop_type_combo_box)
            form_layout.addRow("货币类型", currency_type_line_edit)
            form_layout.addRow("刷新间隔(秒)", refresh_interval_spin_box)
            form_layout.addRow("可用商品", available_items_text_edit)
            form_layout.addRow("描述", description_text_edit)

        display_name_value = str(shop_payload.get("shop_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"商店模板详情：{display_name}"
        description = "在右侧直接修改商店名称、类型、货币类型、刷新间隔、商品列表与描述，修改会立即保存到当前视图。"
        return title, description, build_form



