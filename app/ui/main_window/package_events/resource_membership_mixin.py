"""图/复合节点/模板/实体摆放等资源的“所属存档”变更与当前包索引内存同步。"""

from __future__ import annotations


class ResourceMembershipMixin:
    """处理资源归属变更，并在命中当前包时同步内存索引与视图缓存。"""

    def _move_resource_to_owner_root_and_sync_current(
        self,
        *,
        resource_type: str,
        resource_id: str,
        target_owner_root_id: str,
    ) -> bool:
        """将资源移动到目标归属根目录，并同步“当前包”的内存索引快照。

        约定：
        - target_owner_root_id == "shared" 表示移动到共享根目录；
        - 其它值视为项目存档目录名。
        """
        manager = getattr(self.app_state, "package_index_manager", None)
        if manager is None:
            return False

        previous_owner = manager.get_resource_owner_root_id(
            resource_type=resource_type,
            resource_id=resource_id,
        )
        target_owner_text = str(target_owner_root_id or "").strip()
        if not target_owner_text:
            return False

        if previous_owner and previous_owner == target_owner_text:
            return True

        moved = manager.move_resource_to_root(target_owner_text, resource_type, resource_id)
        if not moved:
            return False

        if previous_owner:
            self._sync_current_package_index_for_membership(
                previous_owner,
                resource_type,
                resource_id,
                False,
            )
        self._sync_current_package_index_for_membership(
            target_owner_text,
            resource_type,
            resource_id,
            True,
        )

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if current_package_id and current_package_id != "global_view":
            if current_package_id in {previous_owner, target_owner_text}:
                self._on_immediate_persist_requested(index_dirty=True)
        return True

    def _sync_current_package_index_for_membership(
        self,
        package_id: str,
        resource_type: str,
        resource_id: str,
        is_checked: bool,
    ) -> None:
        """在当前存档上下文中同步内存 PackageIndex 与 PackageView 缓存。

        设计约定：
        - PackageController.current_package_index 视为“当前存档索引”的权威内存副本；
        - 命中当前存档的“所属存档”变更优先更新内存索引与视图缓存，再通过脏块保存链路落盘；
        - 其它存档仍通过 PackageIndexManager.add/remove_resource_from_package 即时落盘。
        """
        if not hasattr(self, "package_controller"):
            return

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if not current_package_id or current_package_id != package_id:
            return

        current_index = getattr(self.package_controller, "current_package_index", None)
        if current_index is None:
            return

        # 1. 更新当前存档索引中的资源引用列表
        if resource_type == "graph":
            if is_checked:
                current_index.add_graph(resource_id)
            else:
                current_index.remove_graph(resource_id)
        elif resource_type == "composite":
            if is_checked:
                current_index.add_composite(resource_id)
            else:
                current_index.remove_composite(resource_id)
        elif resource_type == "template":
            if is_checked:
                current_index.add_template(resource_id)
            else:
                current_index.remove_template(resource_id)
        elif resource_type == "instance":
            if is_checked:
                current_index.add_instance(resource_id)
            else:
                current_index.remove_instance(resource_id)
        elif resource_type.startswith("combat_"):
            # 战斗预设：维护 PackageIndex.resources.combat_presets 下的对应 bucket 列表
            bucket_key = resource_type[len("combat_") :]
            preset_ids = current_index.resources.combat_presets.setdefault(bucket_key, [])
            if is_checked:
                if resource_id not in preset_ids:
                    preset_ids.append(resource_id)
            else:
                if resource_id in preset_ids:
                    preset_ids.remove(resource_id)
        elif resource_type == "management_struct_definitions":
            # 结构体定义：仅维护索引层的 ID 列表
            struct_ids = current_index.resources.management.setdefault("struct_definitions", [])
            if is_checked:
                if resource_id not in struct_ids:
                    struct_ids.append(resource_id)
            else:
                if resource_id in struct_ids:
                    struct_ids.remove(resource_id)
        elif resource_type.startswith("management_"):
            # 其他管理配置：泛化维护 management 下的 ID 列表
            management_key = resource_type[len("management_") :]
            members = current_index.resources.management.setdefault(management_key, [])
            if is_checked:
                if resource_id not in members:
                    members.append(resource_id)
            else:
                if resource_id in members:
                    members.remove(resource_id)

        # 2. 同步当前 PackageView 的缓存（仅在其为 PackageView 时才需要）
        from engine.resources.package_view import PackageView  # 局部导入以避免循环依赖

        current_package = getattr(self.package_controller, "current_package", None)
        if isinstance(current_package, PackageView):
            if resource_type == "template":
                # 下次访问 templates 时基于最新索引重新构建
                current_package._templates_cache = None  # type: ignore[attr-defined]
            elif resource_type == "instance":
                current_package._instances_cache = None  # type: ignore[attr-defined]

    def _on_graph_package_membership_changed(
        self,
        graph_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """节点图所属存档变更（单选归属根目录）。"""
        if not graph_id or not package_id:
            return
        if not bool(is_checked):
            return

        self._move_resource_to_owner_root_and_sync_current(
            resource_type="graph",
            resource_id=graph_id,
            target_owner_root_id=package_id,
        )

        self.graph_property_panel.graph_updated.emit(graph_id)

    def _on_composite_package_membership_changed(
        self,
        composite_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """复合节点所属存档变更（单选归属根目录）。"""
        if not composite_id or not package_id:
            return
        if not bool(is_checked):
            return

        self._move_resource_to_owner_root_and_sync_current(
            resource_type="composite",
            resource_id=composite_id,
            target_owner_root_id=package_id,
        )

    def _on_template_package_membership_changed(
        self,
        template_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """模板（含掉落物）所属存档变更（单选归属根目录）。"""
        if not template_id or not package_id:
            return
        if not bool(is_checked):
            return

        moved = self._move_resource_to_owner_root_and_sync_current(
            resource_type="template",
            resource_id=template_id,
            target_owner_root_id=package_id,
        )
        if moved:
            self._refresh_library_pages_after_property_panel_update()

    def _on_instance_package_membership_changed(
        self,
        instance_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """实体摆放所属存档变更（单选归属根目录）。"""
        if not instance_id or not package_id:
            return
        if not bool(is_checked):
            return

        moved = self._move_resource_to_owner_root_and_sync_current(
            resource_type="instance",
            resource_id=instance_id,
            target_owner_root_id=package_id,
        )
        if moved:
            self._refresh_library_pages_after_property_panel_update()


