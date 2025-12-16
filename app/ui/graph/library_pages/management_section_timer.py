from __future__ import annotations

from .management_sections_base import *


class TimerSection(BaseManagementSection):
    """计时器管理 Section（对应 `ManagementData.timers`）。"""

    section_key = "timer"
    tree_label = "⏰ 计时器"
    type_name = "计时器"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        for timer_id, timer_data in package.management.timers.items():
            timer_name = str(timer_data.get("timer_name", ""))
            initial_time_value = timer_data.get("initial_time", 0)
            is_loop_enabled = bool(timer_data.get("is_loop"))
            is_auto_start_enabled = bool(timer_data.get("auto_start"))
            yield ManagementRowData(
                name=timer_name or timer_id,
                type_name=self.type_name,
                attr1=f"初始时间: {initial_time_value}s",
                attr2=f"循环: {'是' if is_loop_enabled else '否'}",
                attr3=f"自动开始: {'是' if is_auto_start_enabled else '否'}",
                description="",
                last_modified=self._get_last_modified_text(timer_data),
                user_data=(self.section_key, timer_id),
            )

    def _build_form(
        self,
        parent_widget: QtWidgets.QWidget,
        *,
        title: str,
        initial: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        initial_values: Dict[str, Any] = {
            "timer_name": "",
            "initial_time": 60.0,
            "is_loop": False,
            "auto_start": False,
        }
        if initial:
            initial_values.update(initial)

        builder = FormDialogBuilder(parent_widget, title, fixed_size=(400, 250))

        name_edit = builder.add_line_edit("计时器名:", str(initial_values.get("timer_name", "")), "请输入计时器名称")
        time_spin = builder.add_double_spin_box(
            "初始时间(秒):",
            minimum=0.0,
            maximum=86400.0,
            value=float(initial_values.get("initial_time", 60.0)),
            decimals=2,
            single_step=1.0,
            suffix=" 秒",
        )
        loop_check = builder.add_check_box(
            "循环",
            bool(initial_values.get("is_loop", False)),
        )
        auto_start_check = builder.add_check_box(
            "自动开始",
            bool(initial_values.get("auto_start", False)),
        )

        def _validate(dialog_self: QtWidgets.QDialog) -> bool:
            if not name_edit.text().strip():
                from app.ui.foundation import dialog_utils

                dialog_utils.show_warning_dialog(
                    dialog_self,
                    "提示",
                    "请输入计时器名称",
                )
                return False
            return True

        builder.dialog.validate = types.MethodType(_validate, builder.dialog)

        if not builder.exec():
            return None

        return {
            "timer_name": name_edit.text().strip(),
            "initial_time": float(time_spin.value()),
            "is_loop": bool(loop_check.isChecked()),
            "auto_start": bool(auto_start_check.isChecked()),
        }

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        _ = parent_widget

        timers_mapping = package.management.timers
        if not isinstance(timers_mapping, dict):
            timers_mapping = {}
            package.management.timers = timers_mapping

        timer_id = generate_prefixed_id("timer")
        while timer_id in timers_mapping:
            timer_id = generate_prefixed_id("timer")

        default_index = len(timers_mapping) + 1
        timer_name = f"计时器{default_index}"

        timer_config = TimerManagementConfig(
            timer_id=timer_id,
            timer_name=timer_name,
            initial_time=60.0,
            is_loop=False,
            auto_start=False,
        )
        timers_mapping[timer_id] = timer_config.serialize()
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        timer_data = package.management.timers.get(item_id)
        if timer_data is None:
            return False

        initial_values = {
            "timer_name": timer_data.get("timer_name", ""),
            "initial_time": timer_data.get("initial_time", 60.0),
            "is_loop": bool(timer_data.get("is_loop", False)),
            "auto_start": bool(timer_data.get("auto_start", False)),
        }
        dialog_data = self._build_form(
            parent_widget,
            title="编辑计时器",
            initial=initial_values,
        )
        if dialog_data is None:
            return False

        timer_data["timer_name"] = dialog_data["timer_name"]
        timer_data["initial_time"] = dialog_data["initial_time"]
        timer_data["is_loop"] = dialog_data["is_loop"]
        timer_data["auto_start"] = dialog_data["auto_start"]
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        if item_id not in package.management.timers:
            return False
        del package.management.timers[item_id]
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑计时器的基础字段。"""
        timers_mapping = getattr(package.management, "timers", None)
        if not isinstance(timers_mapping, dict):
            return None
        timer_payload_any = timers_mapping.get(item_id)
        if not isinstance(timer_payload_any, dict):
            return None

        timer_payload = timer_payload_any

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            timer_name_value = timer_payload.get("timer_name", "")
            initial_time_raw = timer_payload.get("initial_time", 60.0)
            if isinstance(initial_time_raw, (int, float)):
                initial_time_value = float(initial_time_raw)
            else:
                initial_time_value = 60.0

            is_loop_enabled = bool(timer_payload.get("is_loop", False))
            is_auto_start_enabled = bool(timer_payload.get("auto_start", False))

            name_edit = QtWidgets.QLineEdit(str(timer_name_value))
            initial_time_spin = QtWidgets.QDoubleSpinBox()
            initial_time_spin.setRange(0.0, 86400.0)
            initial_time_spin.setDecimals(2)
            initial_time_spin.setSingleStep(1.0)
            initial_time_spin.setValue(initial_time_value)

            loop_checkbox = QtWidgets.QCheckBox()
            loop_checkbox.setChecked(is_loop_enabled)

            auto_start_checkbox = QtWidgets.QCheckBox()
            auto_start_checkbox.setChecked(is_auto_start_enabled)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                if normalized_name:
                    timer_payload["timer_name"] = normalized_name
                timer_payload["initial_time"] = float(initial_time_spin.value())
                timer_payload["is_loop"] = bool(loop_checkbox.isChecked())
                timer_payload["auto_start"] = bool(auto_start_checkbox.isChecked())
                on_changed()

            name_edit.editingFinished.connect(apply_changes)
            initial_time_spin.editingFinished.connect(apply_changes)
            loop_checkbox.stateChanged.connect(lambda _state: apply_changes())
            auto_start_checkbox.stateChanged.connect(lambda _state: apply_changes())

            form_layout.addRow("计时器名", name_edit)
            form_layout.addRow("初始时间(秒)", initial_time_spin)
            form_layout.addRow("循环", loop_checkbox)
            form_layout.addRow("自动开始", auto_start_checkbox)

        title = "计时器详情"
        description = "在右侧直接修改计时器名称与运行属性，修改会立即保存到当前视图。"
        return title, description, build_form



