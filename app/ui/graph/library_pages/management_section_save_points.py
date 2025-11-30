from __future__ import annotations

from engine.configs.specialized.node_graph_configs import STRUCT_TYPE_INGAME_SAVE
from engine.resources.definition_schema_view import (
    get_default_definition_schema_view,
)
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from PyQt6 import QtGui, QtWidgets

from .management_sections_base import *
from ui.forms.schema_dialog import FormDialogBuilder
from ui.foundation.theme_manager import Sizes
from ui.widgets.inline_table_editor_widget import (
    InlineTableColumnSpec,
    InlineTableEditorWidget,
)


class SavePointsSection(BaseManagementSection):
    """局内存档管理 Section（对应 `ManagementData.save_points` 单配置字段）。

    数据结构与 `SavePointsPage` 保持一致：

    ```python
    management.save_points = {
        "enabled": bool,
        "active_template_id": str,
        "templates": [
            {
                "template_id": str,
                "template_name": str,
                "description": str,
                "entries": [
                    {"struct_id": str, "max_length": int},
                    ...
                ],
            },
            ...
        ],
    }
    ```

    在“管理配置库”右侧列表中，每一行代表一个“局内存档模板”。

    资源语义补充：
    - 每个局内存档模板以代码级资源形式存在于
      `assets/资源库/管理配置/局内存档管理/` 目录下的 Python 模块中，
      模块导出 `SAVE_POINT_ID` 与 `SAVE_POINT_PAYLOAD`，由引擎层
      `IngameSaveTemplateSchemaView` 聚合为 `{template_id: payload}` 视图；
    - 功能包/存档只通过 `PackageIndex.resources.management["save_points"]` 里的 ID 列表
      引用这些模板 ID，充当“索引/标签”，不会改变模板本身的生命周期；
    - 在 `<全部资源>` (`GlobalResourceView`) 与 `<未分类资源>` (`UnclassifiedResourceView`) 中，
      `management.save_points` 提供的是“全局聚合视图”：组合所有代码级模板与
      全局元配置 `global_view_save_points`（enabled/active_template_id/updated_at），
      在这些视图下仅允许切换“当前启用模板”和启用状态，不再直接编辑模板结构；
    - 在具体存档视图 (`PackageView`) 下，本 Section 仅使用上述全局聚合配置按
      `PackageIndex.resources.management["save_points"]` 过滤后的结果进行展示，
      不直接写回模板定义本体；包级“所属存档”关系仍通过管理属性面板顶部的多选行
      与 `PackageIndexManager` 维护。
    """

    section_key = "save_points"
    tree_label = "💾 局内存档管理"
    type_name = "局内存档模板"

    @staticmethod
    def _ensure_config(package: ManagementPackage) -> Dict[str, Any]:
        """确保 package.management.save_points 具备标准结构（聚合视图语义）。

        仅用于 `<全部资源>` / `<未分类资源>` 等聚合视图下的 `management.save_points`，
        在具体存档视图 (`PackageView`) 中不会直接修改底层 SAVE_POINT 资源。
        """
        raw_value: Any = package.management.save_points
        if not isinstance(raw_value, dict):
            raw_value = {}
            package.management.save_points = raw_value

        config_data: Dict[str, Any] = raw_value
        if "templates" not in config_data or not isinstance(config_data["templates"], list):
            config_data["templates"] = []
        if "enabled" not in config_data:
            config_data["enabled"] = False
        if "active_template_id" not in config_data:
            config_data["active_template_id"] = ""
        return config_data

    @staticmethod
    def _build_config_for_package_view(package: ManagementPackage) -> Dict[str, Any]:
        """基于全局聚合配置构造“按所属存档过滤”的局内存档视图。

        - 在 `<全部资源>` / `<未分类资源>` 视图下，直接返回聚合配置；
        - 在具体存档视图 (`PackageView`) 下，仅保留
          `PackageIndex.resources.management["save_points"]` 中引用的模板。
        """
        if not isinstance(package, PackageView):
            return SavePointsSection._ensure_config(package)

        resource_manager_candidate = getattr(package, "resource_manager", None)
        if not isinstance(resource_manager_candidate, ResourceManager):
            return {
                "templates": [],
                "enabled": False,
                "active_template_id": "",
            }

        global_view = GlobalResourceView(resource_manager_candidate)
        global_config = SavePointsSection._ensure_config(global_view)

        templates_value = global_config.get("templates", [])
        if not isinstance(templates_value, list):
            templates_value = []

        membership_ids: List[str] = []
        package_index = getattr(package, "package_index", None)
        resources_value = getattr(package_index, "resources", None)
        management_lists = getattr(resources_value, "management", None)
        if isinstance(management_lists, dict):
            ids_value = management_lists.get("save_points", [])
            if isinstance(ids_value, list):
                for raw_id in ids_value:
                    if isinstance(raw_id, str) and raw_id.strip():
                        membership_ids.append(raw_id.strip())

        membership_set = set(membership_ids)
        filtered_templates: List[Dict[str, Any]] = []
        for entry in templates_value:
            if not isinstance(entry, Mapping):
                continue
            raw_template_id = entry.get("template_id", "")
            template_id_text = str(raw_template_id).strip()
            if not template_id_text:
                continue
            if template_id_text not in membership_set:
                continue
            # 使用浅拷贝，避免在包视图中意外修改聚合视图内部结构
            filtered_templates.append(dict(entry))

        enabled_flag = bool(global_config.get("enabled", False))
        active_template_id = str(global_config.get("active_template_id", "")).strip()

        return {
            "templates": filtered_templates,
            "enabled": enabled_flag,
            "active_template_id": active_template_id,
        }

    @staticmethod
    def _load_ingame_struct_choices(package: ManagementPackage) -> Dict[str, str]:
        """加载所有 struct_ype == \"ingame_save\" 的结构体定义，返回 {struct_id: name}。"""
        result: Dict[str, str] = {}
        schema_view = get_default_definition_schema_view()
        all_structs = schema_view.get_all_struct_definitions()

        for struct_id, payload in all_structs.items():
            if not isinstance(payload, Mapping):
                continue
            struct_type_value = payload.get("struct_ype")
            if not isinstance(struct_type_value, str):
                continue
            if struct_type_value.strip() != STRUCT_TYPE_INGAME_SAVE:
                continue
            name_value = payload.get("name") or payload.get("struct_name") or struct_id
            result[str(struct_id)] = str(name_value)
        return result

    @staticmethod
    def _find_template_by_id(config_data: Dict[str, Any], template_id: str) -> Optional[Dict[str, Any]]:
        templates_value = config_data.get("templates", [])
        if not isinstance(templates_value, list):
            return None
        for template_payload in templates_value:
            if not isinstance(template_payload, dict):
                continue
            current_id = str(template_payload.get("template_id", "")).strip()
            if current_id == template_id:
                return template_payload
        return None

    def iter_rows(self, package: ManagementPackage) -> Iterable[ManagementRowData]:
        """枚举当前视图下的所有局内存档模板。

        - 在 `<全部资源>` / `<未分类资源>` 视图下：列出聚合视图中的所有局内存档模板；
        - 在具体存档视图 (`PackageView`) 下：仅列出当前存档
          `resources.management["save_points"]` 中引用的模板，实现按“所属存档”过滤后的展示。
        """
        config_data = self._build_config_for_package_view(package)

        enabled_flag = bool(config_data.get("enabled", False))
        active_template_id = str(config_data.get("active_template_id", "")).strip()

        templates_value = config_data.get("templates", [])
        if not isinstance(templates_value, list):
            return

        for template_payload in templates_value:
            if not isinstance(template_payload, dict):
                continue

            template_id = str(template_payload.get("template_id", "")).strip()
            if not template_id:
                template_id = generate_prefixed_id("ingame_template")
                template_payload["template_id"] = template_id

            raw_name = template_payload.get("template_name")
            template_name = str(raw_name) if raw_name is not None else ""
            display_name = template_name or template_id

            entries_value = template_payload.get("entries", [])
            entry_count = 0
            if isinstance(entries_value, list):
                for entry in entries_value:
                    if isinstance(entry, Mapping):
                        entry_count += 1

            is_active_template = enabled_flag and (active_template_id == template_id)
            status_text = "已启用" if is_active_template else "未启用"

            description_text = str(template_payload.get("description", ""))
            last_modified_text = self._get_last_modified_text(template_payload)

            yield ManagementRowData(
                name=display_name,
                type_name=self.type_name,
                attr1=f"条目数: {entry_count}",
                attr2=f"状态: {status_text}",
                attr3="",
                description=description_text,
                last_modified=last_modified_text,
                user_data=(self.section_key, template_id),
            )

    def create_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
    ) -> bool:
        """新建局内存档模板的入口（已废弃为只读提示）。

        局内存档模板现已迁移为代码级资源：每个模板对应
        `assets/资源库/管理配置/局内存档管理/` 下的一份 Python 模块，
        管理页面不再直接创建或修改模板本体，仅用于浏览与维护“所属存档”关系。
        """
        from ui.foundation import dialog_utils

        dialog_utils.show_info_dialog(
            parent_widget,
            "提示",
            (
                "局内存档模板已迁移为代码级资源，不能在管理页面直接新建。\n"
                "请在 `assets/资源库/管理配置/局内存档管理/` 目录中新建 Python 模块，"
                "或使用配套生成脚本创建模板；管理页面仅用于浏览与维护所属存档。"
            ),
        )
        _ = package
        return False

    def edit_item(
        self,
        parent_widget: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
    ) -> bool:
        """编辑指定模板的基础属性入口（已改为只读提示）。

        模板名称、描述与条目结构均由代码模块中的 `SAVE_POINT_PAYLOAD` 维护，
        管理页面不再直接修改这些字段，仅允许在内联表单中调整全局启用状态。
        """
        from ui.foundation import dialog_utils

        dialog_utils.show_info_dialog(
            parent_widget,
            "提示",
            (
                "局内存档模板的名称、描述与条目配置已迁移为代码级常量，"
                "请直接编辑对应的 Python 模块；管理页面仅用于浏览模板与选择启用模板。"
            ),
        )
        _ = (package, item_id)
        return False

    def delete_item(self, package: ManagementPackage, item_id: str) -> bool:
        """删除指定局内存档模板。

        在具体存档视图下，删除模板应通过全局/未分类视图完成，这里仅支持在聚合视图中
        删除模板本体；对单个存档移除某模板的引用应通过“所属存档”多选行完成。
        """
        from ui.foundation import dialog_utils

        dialog_utils.show_info_dialog(
            None,
            "提示",
            (
                "局内存档模板本体现由代码模块维护，不能在管理页面直接删除。\n"
                "如需让某个存档不再使用该模板，请在右侧属性面板顶部的“所属存档”多选行中"
                "取消勾选对应存档，而不是删除模板定义。"
            ),
        )
        _ = (package, item_id)
        return False

    def build_inline_edit_form(
        self,
        *,
        parent: QtWidgets.QWidget,
        package: ManagementPackage,
        item_id: str,
        on_changed: Callable[[], None],
    ) -> Optional[Tuple[str, str, Callable[[QtWidgets.QFormLayout], None]]]:
        """在右侧属性面板中提供局内存档模板的只读预览与启用开关。

        设计目标：
        - 模板结构与条目列表由代码资源中的 `SAVE_POINT_PAYLOAD` 维护，此处仅做只读展示；
        - 允许在 `<全部资源>` / `<未分类资源>` 视图中切换“当前启用模板”，
          即维护全局元配置中的 enabled/active_template_id；
        - 在具体存档视图 (`PackageView`) 下不提供内联编辑表单，仅通过“所属存档”多选行
          维护本存档对模板的引用关系。
        """
        if isinstance(package, PackageView):
            return None

        config_data = self._ensure_config(package)
        template_payload = self._find_template_by_id(config_data, item_id)
        if template_payload is None:
            return None

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            enabled_flag_value = bool(config_data.get("enabled", False))
            active_template_id_value = str(config_data.get("active_template_id", "")).strip()
            is_active_template = enabled_flag_value and (active_template_id_value == item_id)

            raw_name_value = template_payload.get("template_name")
            template_name_text = str(raw_name_value) if raw_name_value is not None else ""
            if not template_name_text:
                template_name_text = item_id
            name_label = QtWidgets.QLabel(template_name_text)
            name_label.setTextInteractionFlags(
                QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            )

            enabled_checkbox = QtWidgets.QCheckBox("启用局内存档（使用当前模板）")
            enabled_checkbox.setChecked(is_active_template)

            summary_label = QtWidgets.QLabel("")
            summary_label.setWordWrap(True)

            def build_summary_text() -> str:
                entries_for_summary = template_payload.get("entries", [])
                entry_count_local = 0
                if isinstance(entries_for_summary, list):
                    for entry_payload in entries_for_summary:
                        if isinstance(entry_payload, Mapping):
                            entry_count_local += 1

                enabled_flag_local = bool(config_data.get("enabled", False))
                active_template_id_local = str(config_data.get("active_template_id", "")).strip()
                is_template_active_local = enabled_flag_local and active_template_id_local == item_id

                status_text = "当前模板已启用" if is_template_active_local else "当前模板未启用"
                return f"条目数：{entry_count_local}    {status_text}"

            summary_label.setText(build_summary_text())

            description_text = str(template_payload.get("description", "")).strip()
            description_label = QtWidgets.QLabel(description_text or "（无描述）")
            description_label.setWordWrap(True)

            form_layout.addRow("模板名称", name_label)
            form_layout.addRow("描述", description_label)
            form_layout.addRow("是否启用局内存档", enabled_checkbox)
            form_layout.addRow("概要", summary_label)
            def apply_changes() -> None:
                """将启用状态合并回配置，并在确有变化时触发持久化。"""
                enabled_flag_before = bool(config_data.get("enabled", False))
                active_template_id_before = str(config_data.get("active_template_id", "")).strip()
                is_currently_active_template = (
                    enabled_flag_before and active_template_id_before == item_id
                )

                if enabled_checkbox.isChecked():
                    enabled_after = True
                    active_template_id_after = item_id
                elif is_currently_active_template:
                    # 取消当前启用模板的勾选：关闭整体验证功能。
                    enabled_after = False
                    active_template_id_after = ""
                else:
                    # 其他模板的启用开关关闭时，不改变全局启用状态与当前激活模板 ID。
                    enabled_after = enabled_flag_before
                    active_template_id_after = active_template_id_before

                # 若前后状态完全一致，则视为无实际变更，不触发写回与保存。
                if (
                    enabled_after == enabled_flag_before
                    and active_template_id_after == active_template_id_before
                ):
                    return

                config_data["enabled"] = enabled_after
                config_data["active_template_id"] = active_template_id_after

                summary_label.setText(build_summary_text())
                # 使用异步调度避免在下拉框信号栈内立即刷新列表与保存存档，
                # 减少在重建右侧表单时对当前表格控件的重入操作。
                QtCore.QTimer.singleShot(0, on_changed)

            summary_label.setText(build_summary_text())

        display_name_raw = str(template_payload.get("template_name", "")).strip()
        display_name = display_name_raw or item_id

        title = f"局内存档模板详情：{display_name}"
        description = (
            "局内存档模板的结构与条目配置由代码资源维护，本面板仅用于查看概要并切换当前启用模板。"
        )
        return title, description, build_form