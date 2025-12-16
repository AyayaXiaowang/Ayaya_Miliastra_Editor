"""图/复合节点/模板/实例等资源的“所属存档”变更与当前包索引内存同步。"""

from __future__ import annotations


class ResourceMembershipMixin:
    """处理资源归属变更，并在命中当前包时同步内存索引与视图缓存。"""

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
        - 命中当前存档的“所属存档”变更优先更新该对象，再通过 save_package() 统一落盘；
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
        elif resource_type == "combat_player_templates":
            # 战斗玩家模板：复用 combat_presets.player_templates 列表
            preset_ids = current_index.resources.combat_presets.setdefault("player_templates", [])
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
        """节点图所属存档变更"""
        if not graph_id or not package_id:
            return

        # 非当前存档：立即通过 PackageIndexManager 更新并落盘
        if getattr(self.package_controller, "current_package_id", None) != package_id:
            if is_checked:
                self.package_index_manager.add_resource_to_package(
                    package_id,
                    "graph",
                    graph_id,
                )
            else:
                self.package_index_manager.remove_resource_from_package(
                    package_id,
                    "graph",
                    graph_id,
                )

        # 当前存档：同步内存索引与视图缓存，落盘由 save_package() 统一处理
        self._sync_current_package_index_for_membership(
            package_id,
            "graph",
            graph_id,
            is_checked,
        )

        self.graph_property_panel.graph_updated.emit(graph_id)

    def _on_composite_package_membership_changed(
        self,
        composite_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """复合节点所属存档变更"""
        if not composite_id or not package_id:
            return

        if getattr(self.package_controller, "current_package_id", None) != package_id:
            if is_checked:
                self.package_index_manager.add_resource_to_package(
                    package_id,
                    "composite",
                    composite_id,
                )
            else:
                self.package_index_manager.remove_resource_from_package(
                    package_id,
                    "composite",
                    composite_id,
                )

        self._sync_current_package_index_for_membership(
            package_id,
            "composite",
            composite_id,
            is_checked,
        )

    def _on_template_package_membership_changed(
        self,
        template_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """模板（含掉落物）所属存档变更。"""
        if not template_id or not package_id:
            return

        if getattr(self.package_controller, "current_package_id", None) != package_id:
            if is_checked:
                self.package_index_manager.add_resource_to_package(
                    package_id,
                    "template",
                    template_id,
                )
            else:
                self.package_index_manager.remove_resource_from_package(
                    package_id,
                    "template",
                    template_id,
                )

        self._sync_current_package_index_for_membership(
            package_id,
            "template",
            template_id,
            is_checked,
        )

        # 当前存档元件归属变更：立即刷新元件库列表并触发持久化
        if getattr(self.package_controller, "current_package_id", None) == package_id:
            self._on_data_updated()

    def _on_instance_package_membership_changed(
        self,
        instance_id: str,
        package_id: str,
        is_checked: bool,
    ) -> None:
        """实例所属存档变更。"""
        if not instance_id or not package_id:
            return

        if getattr(self.package_controller, "current_package_id", None) != package_id:
            if is_checked:
                self.package_index_manager.add_resource_to_package(
                    package_id,
                    "instance",
                    instance_id,
                )
            else:
                self.package_index_manager.remove_resource_from_package(
                    package_id,
                    "instance",
                    instance_id,
                )

        self._sync_current_package_index_for_membership(
            package_id,
            "instance",
            instance_id,
            is_checked,
        )

        # 当前存档实体归属变更：刷新实体摆放/元件库并立即持久化
        if getattr(self.package_controller, "current_package_id", None) == package_id:
            self._on_data_updated()


