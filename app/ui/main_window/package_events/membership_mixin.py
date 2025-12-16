"""资源“所属存档”归属计算与写回逻辑（信号/结构体/管理资源/关卡变量等）。"""

from __future__ import annotations

from typing import Any, Dict


class MembershipMixin:
    """集中处理多种资源的归属集合计算与写回。"""

    def _build_signal_membership_index(self) -> Dict[str, set[str]]:
        """扫描所有存档索引，构建 {signal_id: {package_id,...}} 归属索引。"""
        membership: Dict[str, set[str]] = {}
        manager = getattr(self, "package_index_manager", None)
        if manager is None:
            return membership
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
                bucket = membership.setdefault(signal_id, set())
                bucket.add(package_id)
        return membership

    def _build_struct_membership_index(self) -> Dict[str, set[str]]:
        """扫描所有存档索引，构建 {struct_id: {package_id,...}} 归属索引。"""
        membership: Dict[str, set[str]] = {}
        manager = getattr(self, "package_index_manager", None)
        if manager is None:
            return membership
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
                bucket = membership.setdefault(struct_id, set())
                bucket.add(package_id)
        return membership

    def _apply_signal_membership_for_property_panel(
        self,
        signal_id: str,
        desired_members: set[str],
    ) -> None:
        """将指定信号的归属写回到各存档索引中（不再写入聚合信号资源）。"""
        from engine.graph.models.package_model import SignalConfig
        from engine.resources.global_resource_view import GlobalResourceView
        from engine.resources.package_index_manager import PackageIndexManager
        from engine.resources.resource_manager import ResourceManager
        from engine.validate.comprehensive_rules.helpers import iter_all_package_graphs  # noqa: F401
        from engine.resources.signal_index_helpers import (
            sync_package_signals_to_index_and_aggregate,
        )

        manager = getattr(self, "package_index_manager", None)
        resource_manager = getattr(self, "resource_manager", None)
        if not isinstance(manager, PackageIndexManager) or not isinstance(resource_manager, ResourceManager):
            return

        config: "Optional[SignalConfig]" = None
        current_package = getattr(self.package_controller, "current_package", None)
        if current_package is not None:
            value = getattr(current_package, "signals", None)
            if isinstance(value, dict):
                candidate = value.get(signal_id)
                if isinstance(candidate, SignalConfig):
                    config = candidate
        if config is None:
            global_view = GlobalResourceView(resource_manager)
            global_signals = getattr(global_view, "signals", {})
            candidate = global_signals.get(signal_id)
            if isinstance(candidate, SignalConfig):
                config = candidate
        if config is None:
            return

        packages = manager.list_packages()
        for pkg in packages:
            package_id_value = pkg.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value:
                continue
            package_id = package_id_value
            package_index = manager.load_package_index(package_id)
            if not package_index:
                continue

            should_have = package_id in desired_members

            existing_signals: Dict[str, Dict] = {}
            if isinstance(package_index.signals, dict):
                for existing_signal_id, existing_payload in package_index.signals.items():
                    if not isinstance(existing_signal_id, str) or not existing_signal_id:
                        continue
                    if not isinstance(existing_payload, dict):
                        continue
                    existing_signals[existing_signal_id] = dict(existing_payload)

            if should_have:
                existing_signals[signal_id] = {}
            else:
                existing_signals.pop(signal_id, None)

            sync_package_signals_to_index_and_aggregate(
                resource_manager,
                package_index,
                existing_signals,
            )
            manager.save_package_index(package_index)

    def _sync_struct_membership_for_property_panel(
        self,
        struct_id: str,
        desired_members: set[str],
    ) -> None:
        """同步结构体与各存档之间的归属关系。"""
        from engine.resources.package_index_manager import PackageIndexManager
        from engine.resources.resource_manager import ResourceManager

        manager = getattr(self, "package_index_manager", None)
        resource_manager = getattr(self, "resource_manager", None)
        if not isinstance(manager, PackageIndexManager) or not isinstance(resource_manager, ResourceManager):
            return

        current_membership_index = self._build_struct_membership_index()
        current_members = current_membership_index.get(struct_id, set())

        to_add = desired_members - current_members
        to_remove = current_members - desired_members

        for package_id in to_add:
            manager.add_resource_to_package(
                package_id,
                "management_struct_definitions",
                struct_id,
            )
            resource_manager.add_reference(struct_id, package_id)

        for package_id in to_remove:
            manager.remove_resource_from_package(
                package_id,
                "management_struct_definitions",
                struct_id,
            )
            resource_manager.remove_reference(struct_id, package_id)

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
        """右侧信号面板中“所属存档”勾选变化时更新归属。"""
        print(
            f"[SIGNAL-MEMBERSHIP] changed: signal_id={signal_id!r}, "
            f"package_id={package_id!r}, is_checked={is_checked!r}"
        )
        if not signal_id or not package_id:
            return
        membership_index = self._build_signal_membership_index()
        current_members = membership_index.get(signal_id, set())
        if is_checked:
            current_members.add(package_id)
        else:
            current_members.discard(package_id)

        self._apply_signal_membership_for_property_panel(signal_id, current_members)

        # 在全局视图/未分类视图下，仅通过 PackageIndexManager 即时写回各存档索引，
        # 不再触发当前视图的整包保存逻辑。
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id in ("global_view", "unclassified_view"):
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
        """右侧结构体面板中“所属存档”勾选变化时更新归属。"""
        print(
            f"[STRUCT-MEMBERSHIP] changed: struct_id={struct_id!r}, "
            f"package_id={package_id!r}, is_checked={is_checked!r}"
        )
        if not struct_id or not package_id:
            return

        membership_index = self._build_struct_membership_index()
        current_members = membership_index.get(struct_id, set())
        if is_checked:
            current_members.add(package_id)
        else:
            current_members.discard(package_id)
        self._sync_struct_membership_for_property_panel(struct_id, current_members)

        # 在全局视图/未分类视图下，仅通过 PackageIndexManager 即时写回各存档索引，
        # 不再触发当前视图的整包保存逻辑。
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id in ("global_view", "unclassified_view"):
            return
        self._on_immediate_persist_requested(index_dirty=True)

    def _get_management_packages_and_membership(
        self,
        resource_key: str,
        resource_id: str,
    ) -> tuple[list[dict], set[str]]:
        """返回给定管理资源在各存档中的归属集合以及完整包列表。"""
        manager = getattr(self, "package_index_manager", None)
        if manager is None:
            return [], set()
        packages = manager.list_packages()
        membership: set[str] = set()
        for package_info in packages:
            package_id_value = package_info.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value:
                continue
            package_id = package_id_value
            package_index = manager.load_package_index(package_id)
            if not package_index:
                continue
            management_lists = package_index.resources.management
            if not isinstance(management_lists, dict):
                continue
            ids_value = management_lists.get(resource_key, [])
            if not isinstance(ids_value, list):
                continue
            if resource_id in ids_value:
                membership.add(package_id)
        return packages, membership

    def _get_level_variable_ids_for_source(self, source_key: str) -> list[str]:
        from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view
        from app.ui.graph.library_pages.management_section_variable import VariableSection

        schema_view = get_default_level_variable_schema_view()
        all_variables = schema_view.get_all_variables()
        matched: list[str] = []
        for variable_id, payload in all_variables.items():
            if not isinstance(payload, dict):
                continue
            resolved_source = VariableSection._get_source_key(payload)
            if resolved_source == source_key:
                matched.append(variable_id)
        return matched

    def _get_packages_and_membership_for_level_variable_group(
        self,
        source_key: str,
    ) -> tuple[list[dict], set[str], list[str]]:
        manager = getattr(self, "package_index_manager", None)
        if manager is None:
            return [], set(), []
        variable_ids = self._get_level_variable_ids_for_source(source_key)
        packages = manager.list_packages()
        membership: set[str] = set()
        for package_info in packages:
            package_id_value = package_info.get("package_id")
            if not isinstance(package_id_value, str) or not package_id_value:
                continue
            package_id = package_id_value
            package_index = manager.load_package_index(package_id)
            if not package_index:
                continue
            ids_value = package_index.resources.management.get("level_variables", [])
            if not isinstance(ids_value, list):
                continue
            if variable_ids and all(var_id in ids_value for var_id in variable_ids):
                membership.add(package_id)
        return packages, membership, variable_ids

    def _apply_level_variable_membership_change(
        self,
        variable_ids: list[str],
        package_id: str,
        is_checked: bool,
    ) -> None:
        from engine.resources.package_index_manager import PackageIndexManager

        manager = getattr(self, "package_index_manager", None)
        if not isinstance(manager, PackageIndexManager):
            return

        for variable_id in variable_ids:
            if is_checked:
                manager.add_resource_to_package(
                    package_id,
                    "management_level_variables",
                    variable_id,
                )
            else:
                manager.remove_resource_from_package(
                    package_id,
                    "management_level_variables",
                    variable_id,
                )

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id == package_id:
            current_package = getattr(self.package_controller, "current_package", None)
            if current_package is not None:
                current_package.clear_cache()

    def _apply_management_membership_for_property_panel(
        self,
        resource_key: str,
        resource_id: str,
        desired_members: set[str],
    ) -> None:
        """同步通用管理资源与各存档之间的归属关系。"""
        from engine.resources.package_index_manager import PackageIndexManager

        manager = getattr(self, "package_index_manager", None)
        if not isinstance(manager, PackageIndexManager):
            return

        _, current_members = self._get_management_packages_and_membership(resource_key, resource_id)

        to_add = desired_members - current_members
        to_remove = current_members - desired_members

        for package_id in to_add:
            manager.add_resource_to_package(
                package_id,
                f"management_{resource_key}",
                resource_id,
            )

        for package_id in to_remove:
            manager.remove_resource_from_package(
                package_id,
                f"management_{resource_key}",
                resource_id,
            )

    def _on_main_camera_panel_package_membership_changed(
        self,
        camera_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """主镜头编辑面板中“所属存档”勾选变化时更新归属。"""
        print(
            f"[CAMERA-MEMBERSHIP] changed: camera_id={camera_id!r}, "
            f"package_id={package_id!r}, is_checked={is_checked!r}"
        )
        if not camera_id or not package_id:
            return

        packages, membership = self._get_management_packages_and_membership("main_cameras", camera_id)
        _ = packages  # 包列表在此处仅用于保持接口一致性
        if is_checked:
            membership.add(package_id)
        else:
            membership.discard(package_id)

        self._apply_management_membership_for_property_panel("main_cameras", camera_id, membership)

        # 在全局视图/未分类视图下，仅通过 PackageIndexManager 即时写回各存档索引，
        # 不再触发当前视图的整包保存逻辑。
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id in ("global_view", "unclassified_view"):
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

        packages, membership = self._get_management_packages_and_membership("peripheral_systems", system_id)
        _ = packages
        if is_checked:
            membership.add(package_id)
        else:
            membership.discard(package_id)

        self._apply_management_membership_for_property_panel("peripheral_systems", system_id, membership)

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id in ("global_view", "unclassified_view"):
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
        packages, membership = self._get_management_packages_and_membership("equipment_data", storage_id)
        _ = packages
        if is_checked:
            membership.add(package_id)
        else:
            membership.discard(package_id)
        self._apply_management_membership_for_property_panel("equipment_data", storage_id, membership)
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id in ("global_view", "unclassified_view"):
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
        packages, membership = self._get_management_packages_and_membership("equipment_data", storage_id)
        _ = packages
        if is_checked:
            membership.add(package_id)
        else:
            membership.discard(package_id)
        self._apply_management_membership_for_property_panel("equipment_data", storage_id, membership)
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id in ("global_view", "unclassified_view"):
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
        packages, membership = self._get_management_packages_and_membership("equipment_data", storage_id)
        _ = packages
        if is_checked:
            membership.add(package_id)
        else:
            membership.discard(package_id)
        self._apply_management_membership_for_property_panel("equipment_data", storage_id, membership)
        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id in ("global_view", "unclassified_view"):
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
        print(
            f"[MGMT-MEMBERSHIP] changed: resource_key={resource_key!r}, "
            f"resource_id={resource_id!r}, package_id={package_id!r}, "
            f"is_checked={is_checked!r}"
        )
        if not resource_key or not resource_id or not package_id:
            return

        if resource_key == "level_variables":
            variable_ids = self._get_level_variable_ids_for_source(resource_id)
            target_ids = variable_ids if variable_ids else [resource_id]
            self._apply_level_variable_membership_change(target_ids, package_id, is_checked)
        else:
            packages, membership = self._get_management_packages_and_membership(resource_key, resource_id)
            _ = packages
            if is_checked:
                membership.add(package_id)
            else:
                membership.discard(package_id)

            self._apply_management_membership_for_property_panel(resource_key, resource_id, membership)

            self._sync_current_package_index_for_membership(
                package_id,
                f"management_{resource_key}",
                resource_id,
                is_checked,
            )

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id in ("global_view", "unclassified_view"):
            return
        self._on_immediate_persist_requested(index_dirty=True)


