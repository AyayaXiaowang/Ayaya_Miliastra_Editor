"""存档库（PACKAGES）页面的右侧详情展示与跳转逻辑。"""

from __future__ import annotations

from typing import Any, Dict

from app.models.view_modes import ViewMode
from engine.resources.global_resource_view import GlobalResourceView
from app.ui.management.section_registry import (
    MANAGEMENT_RESOURCE_BINDINGS,
    MANAGEMENT_RESOURCE_TITLES,
)


class PackagesViewMixin:
    """处理存档库页面的资源激活事件与右侧面板互斥逻辑。"""

    def _get_global_resource_view(self) -> GlobalResourceView:
        """获取（懒加载）全局资源视图，用于在存档库/任务清单等上下文中只读预览资源。

        设计约定：
        - 不依赖当前存档选择，直接基于 ResourceManager 聚合全部资源；
        - 仅在需要只读预览模板/实例/关卡实体时使用，写入仍通过控制器与 PackageView 完成。
        """
        if not hasattr(self, "_global_resource_view") or self._global_resource_view is None:
            self._global_resource_view = GlobalResourceView(self.resource_manager)
        return self._global_resource_view

    def _hide_packages_basic_property_panel(self) -> None:
        """在存档库模式下收起模板/实例/关卡实体通用属性标签。

        仅在 ViewMode.PACKAGES 下生效，避免影响元件库/实体摆放等模式中
        正常使用的属性面板与标签状态。
        """
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_view_mode != ViewMode.PACKAGES:
            return
        if not hasattr(self, "side_tab"):
            return

        property_panel = getattr(self, "property_panel", None)
        if property_panel is not None:
            clear_method = getattr(property_panel, "clear", None)
            if callable(clear_method):
                clear_method()
        ensure_method = getattr(self, "_ensure_property_tab_visible", None)
        if callable(ensure_method):
            ensure_method(False)

    def _hide_packages_management_property_panel(self) -> None:
        """在存档库模式下收起管理配置通用属性标签。

        用于在“信号/其它管理配置”与“模板/实例”等资源类型之间切换时，
        确保右侧不会同时保留两套属性视图，避免用户误以为仍在编辑之前
        的管理资源。
        """
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_view_mode != ViewMode.PACKAGES:
            return
        if not hasattr(self, "side_tab"):
            return

        management_panel = getattr(self, "management_property_panel", None)
        if management_panel is not None:
            clear_method = getattr(management_panel, "clear", None)
            if callable(clear_method):
                clear_method()
        ensure_method = getattr(self, "_ensure_management_property_tab_visible", None)
        if callable(ensure_method):
            ensure_method(False)

    def _on_package_resource_activated(self, kind: str, resource_id: str) -> None:
        """存档库页面中点击资源条目时，在右侧属性或图属性面板中展示详情。

        kind:
            - "template"     → 元件
            - "instance"     → 实例
            - "level_entity" → 关卡实体
            - "graph"        → 节点图
        """
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        print(
            "[PACKAGES] _on_package_resource_activated:",
            f"kind={kind!r}, resource_id={resource_id!r}, current_view_mode={current_view_mode}",
        )
        if current_view_mode != ViewMode.PACKAGES:
            return
        if not kind or not resource_id:
            return

        # 模板 / 实例 / 关卡实体：使用 TemplateInstancePanel 展示，并允许直接编辑属性。
        if kind in ("template", "instance", "level_entity"):
            # 从“信号/其它管理配置”等管理类详情切换到模板/实例/关卡实体时，
            # 主动收起管理属性标签，避免右侧同时残留两套属性视图。
            self._hide_packages_management_property_panel()

            if not hasattr(self, "property_panel"):
                return
            global_view = self._get_global_resource_view()

            if kind == "template":
                if not global_view.get_template(resource_id):
                    return
                self.property_panel.set_template(global_view, resource_id)
            elif kind == "instance":
                if not global_view.get_instance(resource_id):
                    return
                self.property_panel.set_instance(global_view, resource_id)
            else:
                # 关卡实体只要全局视图中存在即可；resource_id 仅用于过滤展示。
                if not global_view.level_entity:
                    return
                self.property_panel.set_level_entity(global_view)

            if hasattr(self.property_panel, "set_read_only"):
                # 存档库页面现在允许直接编辑属性，因此显式切换为可编辑模式。
                self.property_panel.set_read_only(False)
            if hasattr(self, "_ensure_property_tab_visible"):
                self._ensure_property_tab_visible(True)
            if hasattr(self, "side_tab"):
                self.side_tab.setCurrentWidget(self.property_panel)
            return

        # 节点图：使用图属性面板，允许在此页面管理“所属存档”，其它字段保持只读展示。
        if kind == "graph":
            if not hasattr(self, "graph_property_panel"):
                return
            self.graph_property_panel.set_graph(resource_id)
            self.right_panel_registry.ensure_visible("graph_property", visible=True, switch_to=True)
            return

        if hasattr(self, "_schedule_ui_session_state_save"):
            self._schedule_ui_session_state_save()

        # 战斗预设：在存档视图下复用战斗详情面板浏览玩家模板/职业/技能。
        if kind.startswith("combat_"):
            if not hasattr(self, "side_tab"):
                return
            global_view = self._get_global_resource_view()

            if kind == "combat_player_template":
                if not hasattr(self, "player_editor_panel"):
                    return
                self.player_editor_panel.set_context(global_view, resource_id)
                policy = getattr(self, "right_panel_policy", None)
                set_method = getattr(policy, "set_combat_detail_tabs_visible", None)
                if callable(set_method):
                    set_method(player_template=True)
                self.side_tab.setCurrentWidget(self.player_editor_panel)
            elif kind == "combat_player_class":
                if not hasattr(self, "player_class_panel"):
                    return
                self.player_class_panel.set_context(global_view, resource_id)
                policy = getattr(self, "right_panel_policy", None)
                set_method = getattr(policy, "set_combat_detail_tabs_visible", None)
                if callable(set_method):
                    set_method(player_class=True)
                self.side_tab.setCurrentWidget(self.player_class_panel)
            elif kind == "combat_skill":
                if not hasattr(self, "skill_panel"):
                    return
                self.skill_panel.set_context(global_view, resource_id)
                policy = getattr(self, "right_panel_policy", None)
                set_method = getattr(policy, "set_combat_detail_tabs_visible", None)
                if callable(set_method):
                    set_method(skill=True)
                self.side_tab.setCurrentWidget(self.skill_panel)
            else:
                return

            if hasattr(self, "_update_right_panel_visibility"):
                self._update_right_panel_visibility()
            return

    def _on_package_management_resource_activated(
        self,
        resource_key: str,
        resource_id: str,
    ) -> None:
        """存档库页面中点击管理配置条目时，在右侧管理属性面板中展示摘要。

        - resource_key: PackageIndex.resources.management 中的键
        - resource_id : 聚合资源 ID；为空字符串时仅表示选中了分类节点
        """
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        print(
            "[PACKAGES] _on_package_management_resource_activated:",
            f"resource_key={resource_key!r}, resource_id={resource_id!r}, "
            f"current_view_mode={current_view_mode}",
        )
        if current_view_mode != ViewMode.PACKAGES:
            return
        if not hasattr(self, "management_property_panel"):
            return

        # 从模板/实例/图/战斗预设等资源切换到管理配置（含信号）时，
        # 收起通用属性面板，保证右侧仅展示当前管理资源的属性摘要。
        self._hide_packages_basic_property_panel()

        # 分类节点或上下文不完整时，视为“无有效选中对象”，清空并收起属性标签。
        if not resource_key or not resource_id:
            self.management_property_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        # 构建“所属存档”多选行上下文。
        packages, membership = self._get_management_packages_and_membership(resource_key, resource_id)
        if packages:
            self.management_property_panel.set_membership_context(  # type: ignore[attr-defined]
                resource_key,
                resource_key,
                resource_id,
                packages,
                membership,
            )
        else:
            self.management_property_panel._clear_membership_context()  # type: ignore[attr-defined]

        # 基础标题与说明。
        title = MANAGEMENT_RESOURCE_TITLES.get(resource_key, "管理配置详情")
        description = "在存档库中只读查看管理配置摘要，并按需调整其所属存档。"

        rows: list[tuple[str, str]] = [
            ("资源键", resource_key),
            ("资源ID", resource_id),
        ]

        # 基于资源元数据补充名称 / GUID / 挂载节点图信息（如存在）。
        resource_manager = getattr(self, "resource_manager", None)
        if resource_manager is not None:
            resource_type = MANAGEMENT_RESOURCE_BINDINGS.get(resource_key)
            if resource_type is not None:
                metadata = resource_manager.get_resource_metadata(resource_type, resource_id)
                if isinstance(metadata, dict):
                    name_value = metadata.get("name")
                    if isinstance(name_value, str) and name_value.strip():
                        rows.append(("名称", name_value.strip()))
                    guid_value = metadata.get("guid")
                    if isinstance(guid_value, str) and guid_value:
                        rows.append(("GUID", guid_value))
                    graph_ids_value = metadata.get("graph_ids") or []
                    if isinstance(graph_ids_value, list) and graph_ids_value:
                        graph_ids = [str(graph_id) for graph_id in graph_ids_value if isinstance(graph_id, str)]
                        if graph_ids:
                            rows.append(("挂载节点图", ", ".join(graph_ids)))

        self.management_property_panel.set_header(title, description)
        self.management_property_panel.set_rows(rows)

        if hasattr(self, "_ensure_management_property_tab_visible"):
            self._ensure_management_property_tab_visible(True)
        if hasattr(self, "side_tab"):
            self.side_tab.setCurrentWidget(self.management_property_panel)
        if hasattr(self, "_update_right_panel_visibility"):
            self._update_right_panel_visibility()

        if hasattr(self, "_schedule_ui_session_state_save"):
            self._schedule_ui_session_state_save()

    def _on_package_management_item_requested(
        self,
        section_key: str,
        item_id: str,
        package_id: str,
    ) -> None:
        """存档库页面中双击管理配置条目时，跳转到对应管理页面并选中记录。

        - section_key: 管理页面内部 key（如 "equipment_data" / "save_points" / "signals"）。
        - item_id    : 管理记录 ID；为空字符串时仅切换到对应 section。
        - package_id : 目标视图使用的存档 ID 或特殊视图 ID（"global_view" / "unclassified_view"）。
        """
        if not section_key or not package_id:
            return
        if not hasattr(self, "package_controller"):
            return

        current_package_id = self.package_controller.current_package_id
        if package_id != current_package_id:
            self.package_controller.load_package(package_id)

        if hasattr(self, "_navigate_to_mode"):
            self._navigate_to_mode("management")

        management_widget = getattr(self, "management_widget", None)
        if management_widget is None:
            return
        focus_method = getattr(management_widget, "focus_section_and_item", None)
        if callable(focus_method):
            focus_method(section_key, item_id or "")


