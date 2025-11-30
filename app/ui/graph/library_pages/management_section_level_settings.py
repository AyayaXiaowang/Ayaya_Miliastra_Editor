from __future__ import annotations

from .management_sections_base import *


class LevelSettingsSection(BaseManagementSection):
    """关卡设置管理 Section（对应 `ManagementData.level_settings` 单配置字段）。

    设计约定：
    - 每个存档仅存在一个关卡设置配置体（字典），不再区分多条记录；
    - 右侧列表始终至多展示一行，用于摘要展示当前关卡设置的关键字段；
    - “新建/编辑”当前仅支持通过简单对话框维护少量关键字段，其余高级设置保留为只读；
      后续若需要完整替代旧页面，可在本 Section 内增量扩展表单字段。
    """

    section_key = "level_settings"
    tree_label = "⚙️ 关卡设置"
    type_name = "关卡设置"

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        settings_payload = package.management.level_settings
        if not isinstance(settings_payload, dict) or not settings_payload:
            return

        settings = LevelSettingsConfig.deserialize(settings_payload)
        level_name = settings.level_name or "关卡设置"
        description_text = settings.level_description or ""

        scene_range_text = settings.scene_range or "未设置"
        environment_level_value = settings.environment_level
        settlement_type_text = settings.settlement_type or "个人结算"

        yield ManagementRowData(
            name=level_name,
            type_name=self.type_name,
            attr1=f"场景范围: {scene_range_text}",
            attr2=f"环境等级: {environment_level_value}",
            attr3=f"结算界面: {settlement_type_text}",
            description=description_text,
            last_modified="",
            user_data=(self.section_key, settings.config_id or "default"),
        )

    def _build_basic_form(
        self,
        parent_widget: QtWidgets.QWidget,
        initial: dict[str, object],
    ) -> dict[str, object] | None:
        """使用 FormDialogBuilder 构建一个简化版关卡设置表单。"""
        builder = FormDialogBuilder(parent_widget, "编辑关卡设置", fixed_size=(520, 360))

        level_name_edit = builder.add_line_edit(
            "关卡名称",
            str(initial.get("level_name", "")),
            "用于在工具与 UI 中标识本关卡",
        )
        scene_range_edit = builder.add_line_edit(
            "场景范围",
            str(initial.get("scene_range", "")),
            "示例：全图 / 起始区域 / Boss 房间",
        )

        environment_level_spin = builder.add_spin_box(
            "环境等级",
            minimum=0,
            maximum=999,
            value=int(initial.get("environment_level", 0)),
        )

        settlement_type_edit = builder.add_line_edit(
            "结算界面",
            str(initial.get("settlement_type", "")),
            "示例：个人结算 / 队伍结算",
        )

        description_edit = builder.add_plain_text_edit(
            "说明",
            str(initial.get("level_description", "")),
            min_height=80,
            max_height=200,
        )

        if not builder.exec():
            return None

        return {
            "level_name": level_name_edit.text().strip(),
            "scene_range": scene_range_edit.text().strip(),
            "environment_level": int(environment_level_spin.value()),
            "settlement_type": settlement_type_edit.text().strip(),
            "level_description": description_edit.toPlainText().strip(),
        }

    def _ensure_settings_dict(self, package: ManagementPackage) -> dict[str, object]:
        settings_payload = package.management.level_settings
        if not isinstance(settings_payload, dict):
            settings_payload = {}
            package.management.level_settings = settings_payload  # type: ignore[assignment]
        return settings_payload

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        """创建或初始化关卡设置为一份带默认值的配置体，不弹出对话框。"""
        _ = parent_widget
        settings_payload = self._ensure_settings_dict(package)
        if "level_name" not in settings_payload:
            settings_payload["level_name"] = "关卡设置"
        settings_payload.setdefault("scene_range", "")
        settings_payload.setdefault("environment_level", 0)
        settings_payload.setdefault("settlement_type", "")
        settings_payload.setdefault("level_description", "")
        return True

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        """编辑当前关卡设置（简化表单）。"""
        _ = item_id
        settings_payload = self._ensure_settings_dict(package)
        dialog_result = self._build_basic_form(parent_widget, dict(settings_payload))
        if dialog_result is None:
            return False

        settings_payload.update(dialog_result)
        return True

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        """删除当前关卡设置（将配置体清空）。"""
        _ = item_id
        settings_payload = package.management.level_settings
        if not isinstance(settings_payload, dict) or not settings_payload:
            return False
        package.management.level_settings = {}
        return True

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中编辑关卡设置的基础字段。"""
        _ = (parent, item_id)
        settings_payload = self._ensure_settings_dict(package)

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            level_name_value = str(settings_payload.get("level_name", ""))
            scene_range_value = str(settings_payload.get("scene_range", ""))
            environment_level_raw = settings_payload.get("environment_level", 0)
            if isinstance(environment_level_raw, int):
                environment_level_value = environment_level_raw
            else:
                environment_level_value = 0
            settlement_type_value = str(settings_payload.get("settlement_type", ""))
            description_value = str(settings_payload.get("level_description", ""))

            level_name_edit = QtWidgets.QLineEdit(level_name_value)
            scene_range_edit = QtWidgets.QLineEdit(scene_range_value)
            environment_level_spin = QtWidgets.QSpinBox()
            environment_level_spin.setRange(0, 999)
            environment_level_spin.setValue(environment_level_value)
            settlement_type_edit = QtWidgets.QLineEdit(settlement_type_value)
            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(80)
            description_edit.setMaximumHeight(200)

            def apply_changes() -> None:
                settings_payload["level_name"] = level_name_edit.text().strip()
                settings_payload["scene_range"] = scene_range_edit.text().strip()
                settings_payload["environment_level"] = int(environment_level_spin.value())
                settings_payload["settlement_type"] = settlement_type_edit.text().strip()
                settings_payload["level_description"] = description_edit.toPlainText().strip()
                on_changed()

            level_name_edit.editingFinished.connect(apply_changes)
            scene_range_edit.editingFinished.connect(apply_changes)
            environment_level_spin.editingFinished.connect(apply_changes)
            settlement_type_edit.editingFinished.connect(apply_changes)
            description_edit.textChanged.connect(lambda: apply_changes())

            form_layout.addRow("关卡名称", level_name_edit)
            form_layout.addRow("场景范围", scene_range_edit)
            form_layout.addRow("环境等级", environment_level_spin)
            form_layout.addRow("结算界面", settlement_type_edit)
            form_layout.addRow("说明", description_edit)

        title = "关卡设置"
        description = "在右侧直接修改关卡名称、场景范围、环境等级与说明，修改会立即保存到当前视图。"
        return title, description, build_form



