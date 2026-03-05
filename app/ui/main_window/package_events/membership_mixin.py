"""资源“所属存档”归属计算与写回逻辑（信号/结构体/管理资源/关卡变量等）。"""

from __future__ import annotations

from typing import Any, Dict

from engine.utils.logging.logger import log_info


class MembershipMixin:
    """集中处理多种资源的归属集合计算与写回。"""

    def _build_signal_membership_index(self) -> Dict[str, set[str]]:
        """兼容入口：返回 {signal_id: {owner_root_id}}。

        说明：目录即存档模式下，信号归属由其物理文件所在根目录决定（共享/某存档）。
        """
        membership: Dict[str, set[str]] = {}
        manager = self.app_state.package_index_manager
        packages = manager.list_packages()
        for pkg in packages:
            package_id_value = pkg.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value:
                continue
            package_id = package_id_value
            package_index = manager.load_package_index(package_id)
            if not package_index:
                continue
            signals_field = getattr(package_index, "signals", {})
            if not isinstance(signals_field, dict):
                continue
            for signal_id in signals_field.keys():
                if not isinstance(signal_id, str) or not signal_id:
                    continue
                membership.setdefault(signal_id, set()).add(package_id)
        return membership

    def _build_struct_membership_index(self) -> Dict[str, set[str]]:
        """兼容入口：返回 {struct_id: {owner_root_id}}（单选归属根目录）。"""
        membership: Dict[str, set[str]] = {}
        manager = self.app_state.package_index_manager
        packages = manager.list_packages()
        for pkg in packages:
            package_id_value = pkg.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value:
                continue
            package_id = package_id_value
            package_index = manager.load_package_index(package_id)
            if not package_index:
                continue
            struct_ids_value = package_index.resources.management.get("struct_definitions", [])
            if not isinstance(struct_ids_value, list):
                continue
            for struct_id in struct_ids_value:
                if not isinstance(struct_id, str) or not struct_id:
                    continue
                membership.setdefault(struct_id, set()).add(package_id)
        return membership

    def _apply_signal_membership_for_property_panel(
        self,
        signal_id: str,
        desired_members: set[str],
    ) -> None:
        """兼容入口：信号归属已收敛为“单选归属根目录”，此处不再支持多对多写回。"""
        _ = signal_id, desired_members
        return

    def _sync_struct_membership_for_property_panel(
        self,
        struct_id: str,
        desired_members: set[str],
    ) -> None:
        """兼容入口：结构体归属已收敛为“单选归属根目录”，此处不再支持多对多写回。"""
        _ = struct_id, desired_members
        return

    def _on_signal_property_panel_changed(self) -> None:
        """右侧信号编辑面板内容变化时的响应。

        当前版本下信号定义已迁移为代码级常量，管理面板中的编辑区仅用于预览与校验，
        不再直接写回信号定义本体，实际修改需在 Python 模块中完成。该方法现为静默
        空实现，不再弹出提示对话框或执行任何写回操作。
        """
        return

    def _on_signal_property_panel_package_membership_changed(
        self,
        signal_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """右侧信号面板中“所属存档”选择变化：移动信号定义文件到目标根目录。"""
        log_info(
            "[SIGNAL-MEMBERSHIP] changed: signal_id={} package_id={} is_checked={}",
            signal_id,
            package_id,
            is_checked,
        )
        if not signal_id or not package_id:
            return
        if not bool(is_checked):
            return

        manager = self.app_state.package_index_manager
        previous_owner = manager.get_resource_owner_root_id(
            resource_type="management_signals",
            resource_id=signal_id,
        )
        moved = manager.move_resource_to_root(package_id, "management_signals", signal_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                "management_signals",
                signal_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                package_id,
                "management_signals",
                signal_id,
                True,
            )

        # 在全局视图下，仅通过 PackageIndexManager 即时写回各存档索引，
        # 不再触发当前视图的整包保存逻辑。
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == "global_view":
            return
        self._on_immediate_persist_requested(index_dirty=True, signals_dirty=True)

    def _on_struct_property_panel_struct_changed(self) -> None:
        """右侧结构体面板内容变化时，写回当前结构体定义。"""
        from engine.configs.specialized.node_graph_configs import (
            STRUCT_TYPE_BASIC,
            STRUCT_TYPE_INGAME_SAVE,
        )
        from engine.resources.resource_manager import ResourceManager
        from app.ui.foundation import dialog_utils
        from app.ui.graph.library_pages.management_section_struct_definitions import (
            StructDefinitionSection,
        )

        current_package = getattr(self.package_controller, "current_package", None)
        if current_package is None:
            return
        resource_manager_candidate = getattr(current_package, "resource_manager", None)
        if not isinstance(resource_manager_candidate, ResourceManager):
            return
        resource_manager = resource_manager_candidate

        selection = self._get_management_current_selection()
        if selection is None:
            return
        section_key, struct_id = selection
        if section_key not in ("struct_definitions", "ingame_struct_definitions") or not struct_id:
            return

        # 根据当前 section 决定写回时使用的结构体类型标识，保证 struct_ype 与页面语义一致。
        struct_type_value = (
            STRUCT_TYPE_INGAME_SAVE if section_key == "ingame_struct_definitions" else STRUCT_TYPE_BASIC
        )
        if hasattr(self, "struct_definition_panel") and hasattr(self.struct_definition_panel, "editor"):
            editor_widget = self.struct_definition_panel.editor
            setattr(editor_widget, "_struct_type", struct_type_value)
        else:
            return

        struct_data = editor_widget.build_struct_data()

        # 若当前构建出的结构体定义与最近一次快照完全一致，则视为仅发生了
        # 折叠/展开等纯 UI 交互，不执行落盘与列表刷新，避免界面闪烁与滚动位置重置。
        last_struct_id = getattr(self, "_struct_editor_snapshot_id", None)
        last_snapshot = getattr(self, "_struct_editor_snapshot", None)
        if last_struct_id == struct_id and isinstance(last_snapshot, dict):
            if struct_data == last_snapshot:
                return
        struct_name_value = struct_data.get("name")
        struct_name = struct_name_value if isinstance(struct_name_value, str) else ""
        if not struct_name:
            return

        value_entries = struct_data.get("value")
        if not isinstance(value_entries, list) or not any(isinstance(entry, dict) for entry in value_entries):
            return

        section_helper = StructDefinitionSection()
        all_records = section_helper._load_struct_records(resource_manager)  # type: ignore[attr-defined]

        for existing_id, existing_data in all_records:
            if existing_id == struct_id:
                continue
            existing_name = existing_data.get("name") or existing_data.get("struct_name")
            if isinstance(existing_name, str) and existing_name == struct_name:
                dialog_utils.show_warning_dialog(
                    self.struct_definition_panel,
                    "警告",
                    f"已存在名为 '{struct_name}' 的结构体",
                )
                return

        # 当前版本下结构体定义已迁移为代码级常量，属性面板不再直接写回定义本体，
        # 仅用于预览与校验，实际修改需在 Python 模块中完成。
        dialog_utils.show_warning_dialog(
            self.struct_definition_panel,
            "提示",
            (
                "结构体定义已迁移为代码级常量，当前面板仅用于预览与检查，"
                "不再支持将编辑结果写回资源库，请在 Python 模块中修改结构体。"
            ),
        )

    def _on_struct_property_panel_membership_changed(
        self,
        struct_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """右侧结构体面板中“所属存档”选择变化：移动结构体定义文件到目标根目录。"""
        log_info(
            "[STRUCT-MEMBERSHIP] changed: struct_id={} package_id={} is_checked={}",
            struct_id,
            package_id,
            is_checked,
        )
        if not struct_id or not package_id:
            return

        if not bool(is_checked):
            return

        manager = self.app_state.package_index_manager
        previous_owner = manager.get_resource_owner_root_id(
            resource_type="management_struct_definitions",
            resource_id=struct_id,
        )
        moved = manager.move_resource_to_root(package_id, "management_struct_definitions", struct_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                "management_struct_definitions",
                struct_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                package_id,
                "management_struct_definitions",
                struct_id,
                True,
            )

        # 在全局视图下，仅通过 PackageIndexManager 即时写回各存档索引，
        # 不再触发当前视图的整包保存逻辑。
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == "global_view":
            return
        self._on_immediate_persist_requested(index_dirty=True)

    def _get_management_packages_and_membership(
        self,
        resource_key: str,
        resource_id: str,
    ) -> tuple[list[dict], set[str]]:
        """返回给定管理资源的“归属根目录”集合（单选）以及完整包列表。"""
        manager = self.app_state.package_index_manager
        packages = manager.list_packages()
        owner_id = manager.get_resource_owner_root_id(
            resource_type=f"management_{resource_key}",
            resource_id=resource_id,
        )
        membership: set[str] = {owner_id} if owner_id else set()
        return packages, membership

    def _get_level_variable_reference_ids_for_source(self, source_key: str) -> tuple[list[str], list[str]]:
        """按源文件 key 收敛出“变量文件 ID”与“变量 ID”两套引用键。

        约定：
        - 现行语义：PackageIndex.resources.management.level_variables 存储 VARIABLE_FILE_ID（变量文件 ID）。
        - 兼容旧语义：该列表也可能存储 variable_id（逐条变量 ID）。
        """
        from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view
        from app.ui.graph.library_pages.management_section_variable import VariableSection

        schema_view = get_default_level_variable_schema_view()
        all_variables = schema_view.get_all_variables()
        matched_variable_ids: list[str] = []
        matched_file_id_set: set[str] = set()

        for variable_id, payload in all_variables.items():
            if not isinstance(payload, dict):
                continue
            resolved_source = VariableSection._get_source_key(payload)
            if resolved_source != source_key:
                continue

            matched_variable_ids.append(variable_id)
            file_id_value = payload.get("variable_file_id")
            if isinstance(file_id_value, str) and file_id_value.strip():
                matched_file_id_set.add(file_id_value.strip())

        return sorted(matched_file_id_set), matched_variable_ids

    def _get_level_variable_reference_ids_for_group_id(
        self, group_id: str
    ) -> tuple[list[str], list[str]]:
        """按关卡变量分组 ID 获取引用键集合。

        兼容两种分组键：
        - 现行 UI：group_id = VARIABLE_FILE_ID（变量文件 ID）
        - 兼容旧 UI：group_id = source_path / source_file 等“源文件 key”
        """
        from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

        group_id_text = str(group_id or "").strip()
        if not group_id_text:
            return [], []

        schema_view = get_default_level_variable_schema_view()
        file_info = schema_view.get_variable_file(group_id_text)
        if file_info is not None:
            variable_ids: list[str] = []
            for payload in file_info.variables:
                if not isinstance(payload, dict):
                    continue
                variable_id_value = payload.get("variable_id")
                if isinstance(variable_id_value, str) and variable_id_value.strip():
                    variable_ids.append(variable_id_value.strip())
            return [group_id_text], variable_ids

        return self._get_level_variable_reference_ids_for_source(group_id_text)

    def _get_packages_and_membership_for_level_variable_group(
        self,
        source_key: str,
    ) -> tuple[list[dict], set[str], list[str]]:
        manager = self.app_state.package_index_manager
        file_ids, variable_ids = self._get_level_variable_reference_ids_for_group_id(source_key)
        packages = manager.list_packages()
        reference_ids = file_ids or variable_ids
        if not reference_ids:
            return packages, set(), []

        reference_id = str(reference_ids[0] or "").strip()
        owner_id = ""
        if reference_id:
            owner_id = manager.get_resource_owner_root_id(
                resource_type="management_level_variables",
                resource_id=reference_id,
            )
        membership: set[str] = {owner_id} if owner_id else set()
        return packages, membership, reference_ids

    def _apply_level_variable_membership_change(
        self,
        reference_ids: list[str],
        package_id: str,
        is_checked: bool,
    ) -> None:
        from engine.resources.package_index_manager import PackageIndexManager

        manager = self.app_state.package_index_manager
        if not isinstance(manager, PackageIndexManager):
            return

        _ = is_checked
        target_root_id = str(package_id or "").strip()
        if not target_root_id:
            return
        if not reference_ids:
            return

        # 单选语义：变量文件（VARIABLE_FILE_ID）应只归属一个根目录。
        # 对于旧数据（variable_id）不再支持“跨包归属”，这里仍尝试移动其所属文件（若可解析）。
        reference_id = str(reference_ids[0] or "").strip()
        if not reference_id:
            return

        previous_owner = manager.get_resource_owner_root_id(
            resource_type="management_level_variables",
            resource_id=reference_id,
        )
        moved = manager.move_resource_to_root(target_root_id, "management_level_variables", reference_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                "management_level_variables",
                reference_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                target_root_id,
                "management_level_variables",
                reference_id,
                True,
            )

    def _apply_management_membership_for_property_panel(
        self,
        resource_key: str,
        resource_id: str,
        desired_members: set[str],
    ) -> None:
        """兼容入口：管理资源归属已收敛为“单选归属根目录”，此处不再支持多对多写回。"""
        _ = resource_key, resource_id, desired_members
        return

    def _on_main_camera_panel_package_membership_changed(
        self,
        camera_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """主镜头编辑面板中“所属存档”勾选变化时更新归属。"""
        log_info(
            "[CAMERA-MEMBERSHIP] changed: camera_id={} package_id={} is_checked={}",
            camera_id,
            package_id,
            is_checked,
        )
        if not camera_id or not package_id:
            return
        if not bool(is_checked):
            return
        manager = self.app_state.package_index_manager
        previous_owner = manager.get_resource_owner_root_id(
            resource_type="management_main_cameras",
            resource_id=camera_id,
        )
        moved = manager.move_resource_to_root(package_id, "management_main_cameras", camera_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                "management_main_cameras",
                camera_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                package_id,
                "management_main_cameras",
                camera_id,
                True,
            )

        # 在全局视图下，仅通过 PackageIndexManager 即时写回各存档索引，
        # 不再触发当前视图的整包保存逻辑。
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == "global_view":
            return
        self._on_immediate_persist_requested(index_dirty=True)

    def _on_peripheral_system_panel_package_membership_changed(
        self,
        system_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """外围系统编辑面板中“所属存档”勾选变化时更新归属。"""
        if not system_id or not package_id:
            return
        if not bool(is_checked):
            return
        manager = self.app_state.package_index_manager
        previous_owner = manager.get_resource_owner_root_id(
            resource_type="management_peripheral_systems",
            resource_id=system_id,
        )
        moved = manager.move_resource_to_root(package_id, "management_peripheral_systems", system_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                "management_peripheral_systems",
                system_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                package_id,
                "management_peripheral_systems",
                system_id,
                True,
            )

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == "global_view":
            return
        self._on_immediate_persist_requested(index_dirty=True)

    def _on_equipment_entry_package_membership_changed(
        self,
        storage_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        if not storage_id or not package_id:
            return
        if not bool(is_checked):
            return
        manager = self.app_state.package_index_manager
        previous_owner = manager.get_resource_owner_root_id(
            resource_type="management_equipment_data",
            resource_id=storage_id,
        )
        moved = manager.move_resource_to_root(package_id, "management_equipment_data", storage_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                "management_equipment_data",
                storage_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                package_id,
                "management_equipment_data",
                storage_id,
                True,
            )
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == "global_view":
            return
        self._on_immediate_persist_requested(index_dirty=True)

    def _on_equipment_tag_package_membership_changed(
        self,
        storage_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        if not storage_id or not package_id:
            return
        if not bool(is_checked):
            return
        manager = self.app_state.package_index_manager
        previous_owner = manager.get_resource_owner_root_id(
            resource_type="management_equipment_data",
            resource_id=storage_id,
        )
        moved = manager.move_resource_to_root(package_id, "management_equipment_data", storage_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                "management_equipment_data",
                storage_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                package_id,
                "management_equipment_data",
                storage_id,
                True,
            )
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == "global_view":
            return
        self._on_immediate_persist_requested(index_dirty=True)

    def _on_equipment_type_package_membership_changed(
        self,
        storage_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        if not storage_id or not package_id:
            return
        if not bool(is_checked):
            return
        manager = self.app_state.package_index_manager
        previous_owner = manager.get_resource_owner_root_id(
            resource_type="management_equipment_data",
            resource_id=storage_id,
        )
        moved = manager.move_resource_to_root(package_id, "management_equipment_data", storage_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                "management_equipment_data",
                storage_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                package_id,
                "management_equipment_data",
                storage_id,
                True,
            )
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == "global_view":
            return
        self._on_immediate_persist_requested(index_dirty=True)

    def _on_management_property_panel_membership_changed(
        self,
        resource_key: str,
        resource_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """通用管理属性面板中“所属存档”勾选变化时更新归属。"""
        log_info(
            "[MGMT-MEMBERSHIP] changed: resource_key={} resource_id={} package_id={} is_checked={}",
            resource_key,
            resource_id,
            package_id,
            is_checked,
        )
        if not resource_key or not resource_id or not package_id:
            return
        if not bool(is_checked):
            return

        manager = self.app_state.package_index_manager
        resource_type = f"management_{resource_key}"
        previous_owner = manager.get_resource_owner_root_id(
            resource_type=resource_type,
            resource_id=resource_id,
        )
        moved = manager.move_resource_to_root(package_id, resource_type, resource_id)
        if moved and previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                resource_type,
                resource_id,
                False,
            )
        if moved:
            self._sync_current_package_index_for_membership(
                package_id,
                resource_type,
                resource_id,
                True,
            )

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == "global_view":
            return
        self._on_immediate_persist_requested(index_dirty=True)


