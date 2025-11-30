from __future__ import annotations

from .management_sections_base import *


class CurrencyBackpackSection(BaseManagementSection):
    """货币与背包管理 Section（对应 `ManagementData.currency_backpack` 单配置字段）。

    设计约定：
    - `management.currency_backpack` 为单一配置体字典，内部字段结构与
      `CurrencyBackpackConfig` 保持兼容；
    - 列表行：
      - 第一行展示整体“背包配置”摘要（容量 / 堆叠上限 / 默认掉落规则等）；
      - 其余行逐条展示 `currencies` 列表中的货币记录。
    - 新建/编辑：
      - “新建”始终用于添加货币记录；
      - 双击“背包配置”行或在该行上点击“编辑”则编辑整体背包参数。
    """

    section_key = "currency_backpack"
    tree_label = "💰 货币与背包"
    type_name = "货币与背包"

    _BACKPACK_ITEM_ID = "__BACKPACK__"

    @staticmethod
    def _ensure_config(package: ManagementPackage) -> Dict[str, Any]:
        config_data = package.management.currency_backpack
        if not isinstance(config_data, dict):
            config_data = {}
            package.management.currency_backpack = config_data
        if "currencies" not in config_data or not isinstance(config_data["currencies"], list):
            config_data["currencies"] = []
        return config_data

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        config_data = self._ensure_config(package)

        backpack_capacity = int(config_data.get("backpack_capacity", 30))
        max_stack_size = int(config_data.get("max_stack_size", 99))
        drop_form = str(config_data.get("backpack_drop_form", "应用道具掉落规则"))
        loot_form = str(config_data.get("loot_form", "全员一份"))

        yield ManagementRowData(
            name="背包配置",
            type_name="背包",
            attr1=f"容量: {backpack_capacity} 格",
            attr2=f"最大堆叠: {max_stack_size}",
            attr3=f"销毁: {drop_form} / 掉落: {loot_form}",
            description=str(config_data.get("description", "")),
            last_modified="",
            user_data=(self.section_key, self._BACKPACK_ITEM_ID),
        )

        currencies_value = config_data.get("currencies", [])
        if not isinstance(currencies_value, list):
            return

        for currency_payload in currencies_value:
            if not isinstance(currency_payload, dict):
                continue
            currency_id_value = str(currency_payload.get("currency_id", "")).strip()
            if not currency_id_value:
                currency_id_value = generate_prefixed_id("currency")
                currency_payload["currency_id"] = currency_id_value

            name_value = str(currency_payload.get("currency_name", "")) or currency_id_value
            initial_amount = int(currency_payload.get("initial_amount", 0))
            max_amount = int(currency_payload.get("max_amount", 999999))
            drop_form_value = str(currency_payload.get("drop_form", "掉落"))
            loot_form_value = str(currency_payload.get("loot_form", "全员一份"))
            description_text = str(currency_payload.get("description", ""))

            yield ManagementRowData(
                name=name_value,
                type_name="货币",
                attr1=f"配置ID: {currency_id_value}",
                attr2=f"初始数量: {initial_amount} / 最大值: {max_amount}",
                attr3=f"销毁: {drop_form_value} / 掉落: {loot_form_value}",
                description=description_text,
                last_modified="",
                user_data=(self.section_key, currency_id_value),
            )

    def _build_backpack_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "backpack_capacity": 30,
            "max_stack_size": 99,
            "backpack_drop_form": "应用道具掉落规则",
            "loot_form": "全员一份",
            "description": "",
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(420, 320))

        capacity_spin = builder.add_spin_box(
            "背包格数量:",
            minimum=1,
            maximum=100,
            value=int(initial_values.get("backpack_capacity", 30)),
        )
        max_stack_spin = builder.add_spin_box(
            "最大堆叠数:",
            minimum=1,
            maximum=999,
            value=int(initial_values.get("max_stack_size", 99)),
        )
        drop_combo = builder.add_combo_box(
            "销毁时掉落形态:",
            ["应用道具掉落规则", "掉落", "销毁", "保留"],
            current_text=str(initial_values.get("backpack_drop_form", "应用道具掉落规则")),
        )
        loot_combo = builder.add_combo_box(
            "战利品掉落形式:",
            ["全员一份", "每人一份"],
            current_text=str(initial_values.get("loot_form", "全员一份")),
        )
        description_edit = builder.add_plain_text_edit(
            "描述:",
            str(initial_values.get("description", "")),
            min_height=80,
            max_height=200,
        )

        if not builder.exec():
            return None

        return {
            "backpack_capacity": int(capacity_spin.value()),
            "max_stack_size": int(max_stack_spin.value()),
            "backpack_drop_form": str(drop_combo.currentText()),
            "loot_form": str(loot_combo.currentText()),
            "description": description_edit.toPlainText().strip(),
        }

    def _build_currency_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
        existing_ids: Optional[Sequence[str]] = None,
        editable_id: bool,
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "currency_id": "",
            "currency_name": "",
            "icon": "",
            "initial_amount": 0,
            "max_amount": 999999,
            "drop_form": "掉落",
            "loot_form": "全员一份",
        }
        if initial:
            initial_values.update(initial)

        existing_id_set: set[str] = set()
        if existing_ids is not None:
            existing_id_set = {str(value) for value in existing_ids if isinstance(value, str)}

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(420, 360))
        currency_id_edit = builder.add_line_edit(
            "配置ID:",
            str(initial_values.get("currency_id", "")),
            "用于在节点图或系统中引用该货币",
            read_only=not editable_id,
        )
        if not editable_id:
            currency_id_edit.setStyleSheet(ThemeManager.readonly_input_style())

        name_edit = builder.add_line_edit(
            "货币名称:",
            str(initial_values.get("currency_name", "")),
        )
        icon_edit = builder.add_line_edit(
            "图标:",
            str(initial_values.get("icon", "")),
            "图标路径（可选）",
        )
        initial_spin = builder.add_spin_box(
            "初始数量:",
            minimum=0,
            maximum=999999,
            value=int(initial_values.get("initial_amount", 0)),
        )
        max_spin = builder.add_spin_box(
            "最大值:",
            minimum=1,
            maximum=999999,
            value=int(initial_values.get("max_amount", 999999)),
        )
        drop_combo = builder.add_combo_box(
            "销毁时掉落形态:",
            ["掉落", "销毁", "保留"],
            current_text=str(initial_values.get("drop_form", "掉落")),
        )
        loot_combo = builder.add_combo_box(
            "战利品掉落形式:",
            ["全员一份", "每人一份"],
            current_text=str(initial_values.get("loot_form", "全员一份")),
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            from ui.foundation import dialog_utils

            currency_id_text = currency_id_edit.text().strip()
            if not currency_id_text:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入配置ID",
                )
                return False
            if editable_id and currency_id_text in existing_id_set:
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "该配置ID已存在，请使用其他标识",
                )
                return False
            if not name_edit.text().strip():
                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入货币名称",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "currency_id": currency_id_edit.text().strip(),
            "currency_name": name_edit.text().strip(),
            "icon": icon_edit.text().strip(),
            "initial_amount": int(initial_spin.value()),
            "max_amount": int(max_spin.value()),
            "drop_form": str(drop_combo.currentText()),
            "loot_form": str(loot_combo.currentText()),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        config_data = self._ensure_config(package)
        currencies_list = config_data.get("currencies", [])
        if not isinstance(currencies_list, list):
            currencies_list = []
            config_data["currencies"] = currencies_list

        existing_ids: set[str] = set()
        for entry in currencies_list:
            if isinstance(entry, dict):
                existing_id_text = str(entry.get("currency_id", "")).strip()
                if existing_id_text:
                    existing_ids.add(existing_id_text)

        index = len(currencies_list) + 1
        currency_id_value = f"currency_{index}"
        while currency_id_value in existing_ids:
            index += 1
            currency_id_value = f"currency_{index}"

        name_value = f"货币{index}"

        payload: Dict[str, Any] = {
            "currency_id": currency_id_value,
            "currency_name": name_value,
            "icon": "",
            "initial_amount": 0,
            "max_amount": 999999,
            "drop_form": "掉落",
            "loot_form": "全员一份",
            "description": "",
        }

        currencies_list.append(payload)
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        config_data = self._ensure_config(package)
        if item_id == self._BACKPACK_ITEM_ID:
            form_values = self._build_backpack_form(
                parent_widget,
                title="编辑背包配置",
                initial=config_data,
            )
            if form_values is None:
                return False
            config_data.update(form_values)
            return True

        currencies = config_data.get("currencies", [])
        if not isinstance(currencies, list):
            return False

        target_entry: Optional[Dict[str, Any]] = None
        for entry in currencies:
            if not isinstance(entry, dict):
                continue
            current_id = str(entry.get("currency_id", "")).strip()
            if current_id == item_id:
                target_entry = entry
                break
        if target_entry is None:
            return False

        dialog_data = self._build_currency_form(
            parent_widget,
            title="编辑货币",
            initial=dict(target_entry),
            existing_ids=None,
            editable_id=False,
        )
        if dialog_data is None:
            return False

        target_entry["currency_name"] = dialog_data["currency_name"]
        target_entry["icon"] = dialog_data["icon"]
        target_entry["initial_amount"] = dialog_data["initial_amount"]
        target_entry["max_amount"] = dialog_data["max_amount"]
        target_entry["drop_form"] = dialog_data["drop_form"]
        target_entry["loot_form"] = dialog_data["loot_form"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id == self._BACKPACK_ITEM_ID:
            return False
        config_data = self._ensure_config(package)
        currencies = config_data.get("currencies", [])
        if not isinstance(currencies, list):
            return False

        for index, entry in enumerate(currencies):
            if not isinstance(entry, dict):
                continue
            current_id = str(entry.get("currency_id", "")).strip()
            if current_id == item_id:
                del currencies[index]
                return True
        return False

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑货币与背包的全部主要字段。"""
        config_data = self._ensure_config(package)

        if item_id == self._BACKPACK_ITEM_ID:
            def build_form(form_layout: QtWidgets.QFormLayout) -> None:
                backpack_capacity_any = config_data.get("backpack_capacity", 30)
                backpack_capacity_value = int(
                    backpack_capacity_any if isinstance(backpack_capacity_any, int) else 30
                )
                max_stack_any = config_data.get("max_stack_size", 99)
                max_stack_value = int(max_stack_any if isinstance(max_stack_any, int) else 99)
                backpack_drop_form_value = str(
                    config_data.get("backpack_drop_form", "应用道具掉落规则"),
                )
                loot_form_value = str(config_data.get("loot_form", "全员一份"))
                description_value = str(config_data.get("description", ""))

                capacity_spin = QtWidgets.QSpinBox()
                capacity_spin.setRange(1, 100)
                capacity_spin.setValue(backpack_capacity_value)
                max_stack_spin = QtWidgets.QSpinBox()
                max_stack_spin.setRange(1, 999)
                max_stack_spin.setValue(max_stack_value)

                drop_combo = QtWidgets.QComboBox()
                drop_combo.addItems(["应用道具掉落规则", "掉落", "销毁", "保留"])
                if backpack_drop_form_value:
                    drop_combo.setCurrentText(backpack_drop_form_value)

                loot_combo = QtWidgets.QComboBox()
                loot_combo.addItems(["全员一份", "每人一份"])
                if loot_form_value:
                    loot_combo.setCurrentText(loot_form_value)

                description_edit = QtWidgets.QTextEdit()
                description_edit.setPlainText(description_value)
                description_edit.setMinimumHeight(80)
                description_edit.setMaximumHeight(200)

                def apply_changes() -> None:
                    config_data["backpack_capacity"] = int(capacity_spin.value())
                    config_data["max_stack_size"] = int(max_stack_spin.value())
                    config_data["backpack_drop_form"] = str(drop_combo.currentText())
                    config_data["loot_form"] = str(loot_combo.currentText())
                    config_data["description"] = description_edit.toPlainText().strip()
                    on_changed()

                capacity_spin.editingFinished.connect(apply_changes)
                max_stack_spin.editingFinished.connect(apply_changes)
                drop_combo.currentIndexChanged.connect(lambda _index: apply_changes())
                loot_combo.currentIndexChanged.connect(lambda _index: apply_changes())
                description_edit.textChanged.connect(lambda: apply_changes())

                form_layout.addRow("背包格数量", capacity_spin)
                form_layout.addRow("最大堆叠数", max_stack_spin)
                form_layout.addRow("销毁时掉落形态", drop_combo)
                form_layout.addRow("战利品掉落形式", loot_combo)
                form_layout.addRow("描述", description_edit)

            title = "背包配置"
            description = "在右侧直接调整背包容量、最大堆叠数与说明，修改会立即保存到当前视图。"
            return title, description, build_form

        currencies = config_data.get("currencies", [])
        if not isinstance(currencies, list):
            return None

        target_entry: Dict[str, Any] | None = None
        for entry in currencies:
            if not isinstance(entry, dict):
                continue
            current_id_value = str(entry.get("currency_id", "")).strip()
            if current_id_value == item_id:
                target_entry = entry
                break

        if target_entry is None:
            return None

        currency_payload = target_entry

        def build_currency_form(form_layout: QtWidgets.QFormLayout) -> None:
            currency_name_value = str(currency_payload.get("currency_name", ""))
            icon_value = str(currency_payload.get("icon", ""))
            initial_amount_any = currency_payload.get("initial_amount", 0)
            if isinstance(initial_amount_any, int):
                initial_amount_value = initial_amount_any
            else:
                initial_amount_value = 0
            max_amount_any = currency_payload.get("max_amount", 999999)
            if isinstance(max_amount_any, int):
                max_amount_value = max_amount_any
            else:
                max_amount_value = 999999
            drop_form_value = str(currency_payload.get("drop_form", "掉落"))
            loot_form_value = str(currency_payload.get("loot_form", "全员一份"))
            description_value = str(currency_payload.get("description", ""))

            name_edit = QtWidgets.QLineEdit(currency_name_value)
            icon_edit = QtWidgets.QLineEdit(icon_value)

            initial_spin = QtWidgets.QSpinBox()
            initial_spin.setRange(0, 999999)
            initial_spin.setValue(initial_amount_value)

            max_spin = QtWidgets.QSpinBox()
            max_spin.setRange(1, 999999)
            max_spin.setValue(max_amount_value)

            drop_combo = QtWidgets.QComboBox()
            drop_combo.addItems(["掉落", "销毁", "保留"])
            if drop_form_value:
                drop_combo.setCurrentText(drop_form_value)

            loot_combo = QtWidgets.QComboBox()
            loot_combo.addItems(["全员一份", "每人一份"])
            if loot_form_value:
                loot_combo.setCurrentText(loot_form_value)

            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(80)
            description_edit.setMaximumHeight(200)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    currency_payload["currency_name"] = normalized_name
                else:
                    currency_payload["currency_name"] = item_id
                currency_payload["icon"] = icon_edit.text().strip()
                currency_payload["initial_amount"] = int(initial_spin.value())
                currency_payload["max_amount"] = int(max_spin.value())
                currency_payload["drop_form"] = str(drop_combo.currentText())
                currency_payload["loot_form"] = str(loot_combo.currentText())
                currency_payload["description"] = description_edit.toPlainText().strip()
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            icon_edit.editingFinished.connect(apply_changes)
            initial_spin.editingFinished.connect(apply_changes)
            max_spin.editingFinished.connect(apply_changes)
            drop_combo.currentIndexChanged.connect(lambda _index: apply_changes())
            loot_combo.currentIndexChanged.connect(lambda _index: apply_changes())
            description_edit.textChanged.connect(lambda: apply_changes())

            form_layout.addRow("配置ID", QtWidgets.QLabel(item_id))
            form_layout.addRow("货币名称", name_edit)
            form_layout.addRow("图标", icon_edit)
            form_layout.addRow("初始数量", initial_spin)
            form_layout.addRow("最大值", max_spin)
            form_layout.addRow("销毁时掉落形态", drop_combo)
            form_layout.addRow("战利品掉落形式", loot_combo)
            form_layout.addRow("描述", description_edit)

        display_name_value = str(currency_payload.get("currency_name", "")).strip()
        display_name = display_name_value or item_id

        title = f"货币详情：{display_name}"
        description = "在右侧直接修改货币名称与描述，修改会立即保存到当前视图。"
        return title, description, build_currency_form



