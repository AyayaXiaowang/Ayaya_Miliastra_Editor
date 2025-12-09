"""存档与资源索引相关的事件处理 Mixin"""
from __future__ import annotations

from typing import Any, Dict

from PyQt6 import QtCore, QtWidgets, QtGui

from app.models.view_modes import ViewMode
from engine.resources.global_resource_view import GlobalResourceView
from ui.graph.library_pages.library_scaffold import LibraryChangeEvent
from ui.graph.library_pages.management_sections import get_management_section_by_key
from ui.management.section_registry import (
    MANAGEMENT_RESOURCE_BINDINGS,
    MANAGEMENT_RESOURCE_TITLES,
    MANAGEMENT_SECTIONS,
    ManagementSectionSpec,
    ManagementResourceBinding,
)


class PackageEventsMixin:
    """负责存档加载/保存、下拉框刷新以及资源归属变更等事件处理逻辑。"""

    def _set_pending_combat_selection(self, section_key: str, item_id: str) -> None:
        """记录战斗预设待处理的选中项，等进入战斗模式后再加载面板。"""
        if section_key and item_id:
            setattr(self, "_pending_combat_selection", (section_key, item_id))
        else:
            setattr(self, "_pending_combat_selection", None)

    def _consume_pending_combat_selection(self) -> tuple[str, str] | None:
        """取出并清空待处理的战斗预设选中项。"""
        pending = getattr(self, "_pending_combat_selection", None)
        setattr(self, "_pending_combat_selection", None)
        return pending

    # === 存档加载/保存 ===

    def _on_package_loaded(self, package_id: str) -> None:
        """存档加载完成"""
        package = self.package_controller.current_package

        self.template_widget.set_package(package)
        self.placement_widget.set_package(package)
        self.combat_widget.set_package(package)
        self.management_widget.set_package(package)
        self.graph_library_widget.set_package(package)

        # 管理编辑页（按 section 拆分的旧管理页面）同样绑定到当前视图，
        # 确保右侧编辑内容与管理库列表的数据来源一致。
        management_edit_pages = getattr(self, "management_edit_pages", None)
        if isinstance(management_edit_pages, dict):
            for editor in management_edit_pages.values():
                set_package = getattr(editor, "set_package", None)
                if callable(set_package) and package is not None:
                    set_package(package)

        self._refresh_package_list()

        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_view_mode == ViewMode.TODO:
            self._refresh_todo_list()

    def _on_package_saved(self) -> None:
        """存档保存完成"""
        self._trigger_validation()
        # 存档落盘后刷新存档库页面，确保 GUID / 挂载节点图等汇总信息与最新落盘状态保持一致。
        if hasattr(self, "package_library_widget"):
            self.package_library_widget.refresh()

    # === 存档下拉框 ===

    def _refresh_package_list(self) -> None:
        """刷新存档列表"""
        self.package_combo.blockSignals(True)
        self.package_combo.clear()

        self.package_combo.addItem("<全部资源>", "global_view")
        self.package_combo.addItem("<未分类资源>", "unclassified_view")

        packages = self.package_controller.get_package_list()
        for pkg_info in packages:
            self.package_combo.addItem(pkg_info["name"], pkg_info["package_id"])

        current_package_id = self.package_controller.current_package_id
        if current_package_id:
            for i in range(self.package_combo.count()):
                if self.package_combo.itemData(i) == current_package_id:
                    self.package_combo.setCurrentIndex(i)
                    break

        self.package_combo.blockSignals(False)

    def _on_package_combo_changed(self, index: int) -> None:
        """存档下拉框改变"""
        if index < 0:
            return

        package_id = self.package_combo.itemData(index)
        if package_id != self.package_controller.current_package_id:
            self.package_controller.load_package(package_id)

    # === 模板 / 实例 / 关卡实体 ===
    def _on_library_selection_state_changed(
        self,
        has_selection: bool,
        context: Dict[str, Any] | None = None,
    ) -> None:
        """库页统一的选中状态回调，用于收起右侧容器。"""
        selection_context = context or {}
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        source = selection_context.get("source")
        section_key_any = selection_context.get("section_key")
        section_key = section_key_any if isinstance(section_key_any, str) else None

        if has_selection:
            return

        if current_view_mode == ViewMode.TEMPLATE or source == "template":
            if hasattr(self, "property_panel"):
                self.property_panel.clear()
            if hasattr(self, "_ensure_property_tab_visible"):
                self._ensure_property_tab_visible(False)
            if hasattr(self, "_update_right_panel_visibility"):
                self._update_right_panel_visibility()
            return

        if current_view_mode == ViewMode.PLACEMENT or source == "instance":
            if hasattr(self, "property_panel"):
                self.property_panel.clear()
            if hasattr(self, "_ensure_property_tab_visible"):
                self._ensure_property_tab_visible(False)
            if hasattr(self, "_update_right_panel_visibility"):
                self._update_right_panel_visibility()
            return

        is_combat_event = source == "combat" or section_key in (
            "player_template",
            "player_class",
            "skill",
            "item",
        )
        if current_view_mode == ViewMode.COMBAT or is_combat_event:
            self._reset_combat_detail_panels()
            return

        if current_view_mode == ViewMode.MANAGEMENT or source == "management":
            self._reset_management_panels_for_empty_selection(section_key)
            return

        if hasattr(self, "_update_right_panel_visibility"):
            self._update_right_panel_visibility()

    def _reset_combat_detail_panels(self) -> None:
        """清空战斗预设模式下的右侧详情标签与上下文。"""
        panel_pairs = (
            ("player_editor_panel", "_ensure_player_editor_tab_visible"),
            ("player_class_panel", "_ensure_player_class_editor_tab_visible"),
            ("skill_panel", "_ensure_skill_editor_tab_visible"),
            ("item_panel", "_ensure_item_editor_tab_visible"),
        )
        for panel_attr, ensure_method_name in panel_pairs:
            panel = getattr(self, panel_attr, None)
            ensure_method = getattr(self, ensure_method_name, None)
            if panel is not None and hasattr(panel, "set_context"):
                panel.set_context(None, None)  # type: ignore[arg-type]
            if callable(ensure_method):
                ensure_method(False)  # type: ignore[misc]
        if hasattr(self, "_update_right_panel_visibility"):
            self._update_right_panel_visibility()

    def _reset_management_panels_for_empty_selection(self, section_key: str | None) -> None:
        """清空管理模式下的属性与专用编辑标签。"""
        if hasattr(self, "management_property_panel"):
            self.management_property_panel.clear()
        if hasattr(self, "_ensure_management_property_tab_visible"):
            self._ensure_management_property_tab_visible(False)

        if section_key == "signals":
            if hasattr(self, "_update_signal_property_panel_for_selection"):
                self._update_signal_property_panel_for_selection(False)
        elif section_key in ("struct_definitions", "ingame_struct_definitions"):
            if hasattr(self, "_update_struct_property_panel_for_selection"):
                self._update_struct_property_panel_for_selection(False)
        elif section_key == "main_cameras":
            if hasattr(self, "_update_main_camera_panel_for_selection"):
                self._update_main_camera_panel_for_selection(False)
        elif section_key == "peripheral_systems":
            if hasattr(self, "_update_peripheral_system_panel_for_selection"):
                self._update_peripheral_system_panel_for_selection(False)
        elif section_key == "equipment_entries":
            if hasattr(self, "_update_equipment_entry_panel_for_selection"):
                self._update_equipment_entry_panel_for_selection(False)
        elif section_key == "equipment_tags":
            if hasattr(self, "_update_equipment_tag_panel_for_selection"):
                self._update_equipment_tag_panel_for_selection(False)
        elif section_key == "equipment_types":
            if hasattr(self, "_update_equipment_type_panel_for_selection"):
                self._update_equipment_type_panel_for_selection(False)

        if hasattr(self, "_hide_all_management_edit_pages"):
            self._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]
        if hasattr(self, "_update_right_panel_visibility"):
            self._update_right_panel_visibility()
    
    def _on_template_selected(self, template_id: str) -> None:
        """模板选中"""
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        # 空 ID 表示当前上下文中已不再存在原先选中的模板：
        # - 例如切换到不包含该模板的分类/存档；
        # - 或刷新后该模板已被删除。
        # 在元件库模式下收到空 ID 时，应视为“无有效选中对象”，
        # 主动清空右侧属性面板并移除“属性”标签，避免继续展示已失效的元件属性。
        if not template_id:
            self._on_library_selection_state_changed(False, {"source": "template"})
            return

        # 仅在元件库模式下响应该信号，避免在管理/任务清单等模式中因后台刷新
        # 元件库导致右侧属性面板意外弹出或上下文被抢占。
        if current_view_mode != ViewMode.TEMPLATE:
            return

        if self.package_controller.current_package:
            self.property_panel.set_template(
                self.package_controller.current_package,
                template_id,
            )
            self._ensure_property_tab_visible(True)
            if hasattr(self, "_schedule_ui_session_state_save"):
                self._schedule_ui_session_state_save()
    
    def _on_instance_selected(self, instance_id: str) -> None:
        """实例选中"""
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())

        # 空 ID 表示当前上下文中已不再存在原先选中的实体
        # （例如切换到不包含该实体的分类/存档）。
        # 在实体摆放模式下收到空 ID 时，应视为“无有效选中对象”，
        # 主动清空右侧属性面板并移除“属性”标签，避免继续展示已失效的实体属性。
        if not instance_id:
            self._on_library_selection_state_changed(False, {"source": "instance"})
            return

        # 仅在实体摆放模式下响应该信号，避免在管理/任务清单等模式中因后台刷新
        # 实体列表导致右侧属性面板意外弹出或上下文被抢占。
        if current_view_mode != ViewMode.PLACEMENT:
            return

        if self.package_controller.current_package:
            self.property_panel.set_instance(
                self.package_controller.current_package,
                instance_id,
            )
            self._ensure_property_tab_visible(True)
            if hasattr(self, "_schedule_ui_session_state_save"):
                self._schedule_ui_session_state_save()
    
    def _on_level_entity_selected(self) -> None:
        """关卡实体选中"""
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        # 关卡实体属性同样只应在实体摆放模式下展示。
        if current_view_mode != ViewMode.PLACEMENT:
            return

        package = self.package_controller.current_package
        if package and package.level_entity:
            self.property_panel.set_level_entity(package)
            self._ensure_property_tab_visible(True)
            if hasattr(self, "_schedule_ui_session_state_save"):
                self._schedule_ui_session_state_save()
    
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
            if not hasattr(self, "graph_property_panel") or not hasattr(self, "side_tab"):
                return
            self.graph_property_panel.set_graph(resource_id)
            graph_prop_index = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_index == -1:
                self.side_tab.addTab(self.graph_property_panel, "图属性")
            self.side_tab.setCurrentWidget(self.graph_property_panel)
            if hasattr(self, "_update_right_panel_visibility"):
                self._update_right_panel_visibility()
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
                if hasattr(self, "_ensure_player_editor_tab_visible"):
                    self._ensure_player_editor_tab_visible(True)
                self.side_tab.setCurrentWidget(self.player_editor_panel)
            elif kind == "combat_player_class":
                if not hasattr(self, "player_class_panel"):
                    return
                self.player_class_panel.set_context(global_view, resource_id)
                if hasattr(self, "_ensure_player_class_editor_tab_visible"):
                    self._ensure_player_class_editor_tab_visible(True)
                self.side_tab.setCurrentWidget(self.player_class_panel)
            elif kind == "combat_skill":
                if not hasattr(self, "skill_panel"):
                    return
                self.skill_panel.set_context(global_view, resource_id)
                if hasattr(self, "_ensure_skill_editor_tab_visible"):
                    self._ensure_skill_editor_tab_visible(True)
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
    
    def _on_player_template_selected(self, template_id: str) -> None:
        """战斗预设-玩家模板选中"""
        package = self.package_controller.current_package
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        print(
            "[COMBAT-PRESETS] _on_player_template_selected:",
            f"template_id={template_id!r}, current_view_mode={current_view_mode}, "
            f"has_package={bool(package)}",
        )
        if current_view_mode != ViewMode.COMBAT:
            self._set_pending_combat_selection("player_template", template_id)
            return
        if not hasattr(self, "player_editor_panel"):
            return
        has_valid_context = bool(package) and bool(template_id)

        if not has_valid_context:
            self._on_library_selection_state_changed(False, {"section_key": "player_template"})
            return
        self.player_editor_panel.set_context(package, template_id)
        if current_view_mode == ViewMode.COMBAT and hasattr(self, "_ensure_player_editor_tab_visible"):
            self._ensure_player_editor_tab_visible(True)

    def _on_skill_selected(self, skill_id: str) -> None:
        """战斗预设-技能选中"""
        package = self.package_controller.current_package
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        print(
            "[COMBAT-PRESETS] _on_skill_selected:",
            f"skill_id={skill_id!r}, current_view_mode={current_view_mode}, "
            f"has_package={bool(package)}",
        )
        if current_view_mode != ViewMode.COMBAT:
            self._set_pending_combat_selection("skill", skill_id)
            return
        if not hasattr(self, "skill_panel"):
            return
        has_valid_context = bool(package) and bool(skill_id)

        if not has_valid_context:
            self._on_library_selection_state_changed(False, {"section_key": "skill"})
            return
        self.skill_panel.set_context(package, skill_id)
        # 在战斗预设模式下选中技能时，自动切到“技能”标签，并按需插入对应标签页
        if current_view_mode == ViewMode.COMBAT:
            if hasattr(self, "_ensure_skill_editor_tab_visible"):
                self._ensure_skill_editor_tab_visible(True)
            if hasattr(self, "side_tab"):
                index = self.side_tab.indexOf(self.skill_panel)
                if index != -1:
                    self.side_tab.setCurrentWidget(self.skill_panel)

    def _on_item_selected(self, item_id: str) -> None:
        """战斗预设-道具选中"""
        package = self.package_controller.current_package
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        print(
            "[COMBAT-PRESETS] _on_item_selected:",
            f"item_id={item_id!r}, current_view_mode={current_view_mode}, "
            f"has_package={bool(package)}",
        )
        if current_view_mode != ViewMode.COMBAT:
            self._set_pending_combat_selection("item", item_id)
            return
        if not hasattr(self, "item_panel"):
            return
        has_valid_context = bool(package) and bool(item_id)

        if not has_valid_context:
            self._on_library_selection_state_changed(False, {"section_key": "item"})
            return
        self.item_panel.set_context(package, item_id)
        if current_view_mode == ViewMode.COMBAT:
            if hasattr(self, "_ensure_item_editor_tab_visible"):
                self._ensure_item_editor_tab_visible(True)
            if hasattr(self, "side_tab"):
                index = self.side_tab.indexOf(self.item_panel)
                if index != -1:
                    self.side_tab.setCurrentWidget(self.item_panel)

    def _on_player_class_selected(self, class_id: str) -> None:
        """战斗预设-职业选中"""
        package = self.package_controller.current_package
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        print(
            "[COMBAT-PRESETS] _on_player_class_selected:",
            f"class_id={class_id!r}, current_view_mode={current_view_mode}, "
            f"has_package={bool(package)}",
        )
        if current_view_mode != ViewMode.COMBAT:
            self._set_pending_combat_selection("player_class", class_id)
            return
        if not hasattr(self, "player_class_panel"):
            return
        has_valid_context = bool(package) and bool(class_id)

        if not has_valid_context:
            self._on_library_selection_state_changed(False, {"section_key": "player_class"})
            return
        self.player_class_panel.set_context(package, class_id)
        # 在战斗预设模式下选中职业时，将右侧当前标签切换到“职业”详情，并按需插入对应标签页
        if current_view_mode == ViewMode.COMBAT:
            if hasattr(self, "_ensure_player_class_editor_tab_visible"):
                self._ensure_player_class_editor_tab_visible(True)
            if hasattr(self, "side_tab"):
                index = self.side_tab.indexOf(self.player_class_panel)
                if index != -1:
                    self.side_tab.setCurrentWidget(self.player_class_panel)

    # === 管理页面右侧属性与编辑面板 ===

    def _get_management_current_selection(self) -> tuple[str, str] | None:
        """从管理库页面获取当前选中的 (section_key, item_id)。"""
        management_widget = getattr(self, "management_widget", None)
        if management_widget is None:
            return None
        get_selection = getattr(management_widget, "get_current_selection", None)
        if callable(get_selection):
            return get_selection()
        # 兼容：如未提供显式方法，可退化为仅使用当前 section，视为“无具体记录选中”
        current_key_getter = getattr(management_widget, "get_current_section_key", None)
        if callable(current_key_getter):
            section_key = current_key_getter()
            if section_key:
                return section_key, ""
        return None

    def _get_current_management_package(self) -> object | None:
        """获取当前管理视图的包上下文（优先使用 PackageController，回退管理库自身）。"""
        package = getattr(self.package_controller, "current_package", None)
        if package is not None:
            return package
        management_widget = getattr(self, "management_widget", None)
        if management_widget is not None:
            return getattr(management_widget, "current_package", None)
        return None

    def _update_signal_property_panel_for_selection(self, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新信号编辑面板。"""
        if not hasattr(self, "signal_management_panel"):
            return
        from ui.graph.library_pages.management_section_signals import SignalSection

        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            self.signal_management_panel.reset()
            if hasattr(self, "_ensure_signal_editor_tab_visible"):
                self._ensure_signal_editor_tab_visible(False)
            return

        section_key, signal_id = selection
        if section_key != "signals" or not signal_id:
            self.signal_management_panel.reset()
            if hasattr(self, "_ensure_signal_editor_tab_visible"):
                self._ensure_signal_editor_tab_visible(False)
            return

        package = getattr(self.package_controller, "current_package", None)
        if package is None:
            self.signal_management_panel.reset()
            if hasattr(self, "_ensure_signal_editor_tab_visible"):
                self._ensure_signal_editor_tab_visible(False)
            return

        signals_dict = SignalSection._get_signal_dict_from_package(package)
        if signal_id not in signals_dict:
            self.signal_management_panel.reset()
            if hasattr(self, "_ensure_signal_editor_tab_visible"):
                self._ensure_signal_editor_tab_visible(False)
            return

        config = signals_dict[signal_id]
        self.signal_management_panel.editor.load_from_config(config)

        display_name = config.signal_name or signal_id
        self.signal_management_panel.set_title(f"编辑信号：{display_name}")
        self.signal_management_panel.set_description(
            "信号定义当前为代码级只读视图：右侧内容仅供查看与校验，实际修改请在 Python 模块中完成。"
        )

        usage_stats = SignalSection._build_signal_usage_stats(package)
        usage_entry = usage_stats.get(signal_id)
        if usage_entry:
            graph_count = int(usage_entry.get("graph_count", 0))
            node_count = int(usage_entry.get("node_count", 0))
            if graph_count > 0 or node_count > 0:
                usage_text = f"已在 {graph_count} 个图 / {node_count} 个节点中使用"
            else:
                usage_text = "未在任何服务器节点图中使用"
        else:
            usage_text = "未在任何服务器节点图中使用"
        self.signal_management_panel.set_usage_text(usage_text)

        packages = self.package_index_manager.list_packages()
        membership_index = self._build_signal_membership_index()
        membership = membership_index.get(signal_id, set())
        self.signal_management_panel.set_current_signal_id(signal_id)
        self.signal_management_panel.set_signal_membership(packages, membership)

        if hasattr(self, "_ensure_signal_editor_tab_visible"):
            self._ensure_signal_editor_tab_visible(True)

    def _update_struct_property_panel_for_selection(self, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新结构体编辑面板。"""
        if not hasattr(self, "struct_definition_panel"):
            return
        from engine.configs.resource_types import ResourceType
        from engine.configs.specialized.node_graph_configs import (
            STRUCT_TYPE_BASIC,
            STRUCT_TYPE_INGAME_SAVE,
        )
        from engine.resources.resource_manager import ResourceManager
        from ui.graph.library_pages.management_section_struct_definitions import (
            StructDefinitionSection,
        )

        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            self.struct_definition_panel.reset()
            if hasattr(self, "_ensure_struct_editor_tab_visible"):
                self._ensure_struct_editor_tab_visible(False)
            return

        section_key, struct_id = selection
        if section_key not in ("struct_definitions", "ingame_struct_definitions") or not struct_id:
            self.struct_definition_panel.reset()
            if hasattr(self, "_ensure_struct_editor_tab_visible"):
                self._ensure_struct_editor_tab_visible(False)
            return

        package = getattr(self.package_controller, "current_package", None)
        if package is None:
            self.struct_definition_panel.reset()
            if hasattr(self, "_ensure_struct_editor_tab_visible"):
                self._ensure_struct_editor_tab_visible(False)
            return

        resource_manager_candidate = getattr(package, "resource_manager", None)
        if not isinstance(resource_manager_candidate, ResourceManager):
            self.struct_definition_panel.reset()
            if hasattr(self, "_ensure_struct_editor_tab_visible"):
                self._ensure_struct_editor_tab_visible(False)
            return

        from engine.configs.specialized.struct_definitions_data import get_struct_payload

        payload = get_struct_payload(struct_id)
        if not isinstance(payload, dict):
            self.struct_definition_panel.reset()
            if hasattr(self, "_ensure_struct_editor_tab_visible"):
                self._ensure_struct_editor_tab_visible(False)
            return

        # 根据当前 section 确定结构体类型标识，确保后续保存时写回正确的 struct_ype。
        struct_type_value = (
            STRUCT_TYPE_INGAME_SAVE if section_key == "ingame_struct_definitions" else STRUCT_TYPE_BASIC
        )

        _, initial_fields = StructDefinitionSection._extract_initial_fields_from_struct_data(
            payload
        )
        display_name = StructDefinitionSection._get_struct_display_name(struct_id, payload)

        # 在加载编辑内容前，先更新编辑器中的结构体类型标识，避免后续保存时误写为基础结构体。
        editor_widget = getattr(self.struct_definition_panel, "editor", None)
        if editor_widget is None:
            self.struct_definition_panel.reset()
            if hasattr(self, "_ensure_struct_editor_tab_visible"):
                self._ensure_struct_editor_tab_visible(False)
            return

        setattr(editor_widget, "_struct_type", struct_type_value)

        editor_widget.load_struct(
            struct_name=display_name,
            fields=initial_fields,
            allow_edit_name=False,
        )

        # 管理模式下结构体详情面板仅作为只读视图使用，防止在 UI 中直接修改定义本体。
        if hasattr(editor_widget, "set_read_only"):
            editor_widget.set_read_only(True)  # type: ignore[attr-defined]

        # 记录当前编辑器中的结构体定义快照，用于后续在写回时区分真实内容变更
        # 与仅涉及列表/字典折叠状态等纯 UI 交互，避免无数据变更的操作触发
        # 不必要的保存与列表刷新。
        self._struct_editor_snapshot = editor_widget.build_struct_data()
        self._struct_editor_snapshot_id = struct_id

        field_count = StructDefinitionSection._calculate_field_count(payload)
        self.struct_definition_panel.set_field_count(field_count)
        self.struct_definition_panel.set_title(f"编辑结构体：{display_name}")
        self.struct_definition_panel.set_description(
            "结构体定义当前为代码级只读视图：右侧内容仅供查看与校验，实际修改请在 Python 模块中完成。"
        )

        packages = self.package_index_manager.list_packages()
        membership_index = self._build_struct_membership_index()
        membership = membership_index.get(struct_id, set())
        self.struct_definition_panel.set_current_struct_id(struct_id)
        self.struct_definition_panel.set_packages_and_membership(packages, membership)

        if hasattr(self, "_ensure_struct_editor_tab_visible"):
            self._ensure_struct_editor_tab_visible(True)

    def _update_timer_property_panel_for_selection(self, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新计时器编辑面板（复用通用管理属性面板）。"""
        if not hasattr(self, "management_property_panel"):
            return

        management_panel = self.management_property_panel

        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        section_key, timer_id = selection
        if section_key != "timer" or not timer_id:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        current_package = getattr(self.package_controller, "current_package", None)
        if current_package is None:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        management_view = getattr(current_package, "management", None)
        timers_mapping = getattr(management_view, "timers", None)
        if not isinstance(timers_mapping, dict):
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        timer_payload_any = timers_mapping.get(timer_id)
        if not isinstance(timer_payload_any, dict):
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

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

                if hasattr(self, "management_widget"):
                    self.management_widget._refresh_items()  # type: ignore[attr-defined]
                self._on_immediate_persist_requested(management_keys={"timers"})

            name_edit.editingFinished.connect(apply_changes)
            initial_time_spin.editingFinished.connect(apply_changes)
            loop_checkbox.stateChanged.connect(lambda _state: apply_changes())
            auto_start_checkbox.stateChanged.connect(lambda _state: apply_changes())

            form_layout.addRow("计时器名", name_edit)
            form_layout.addRow("初始时间(秒)", initial_time_spin)
            form_layout.addRow("循环", loop_checkbox)
            form_layout.addRow("自动开始", auto_start_checkbox)

        management_panel.build_edit_form(
            title="计时器详情",
            description="直接在右侧修改计时器名称与运行属性，修改会立即保存到当前视图。",
            build_form=build_form,
        )

        if hasattr(self, "_ensure_management_property_tab_visible"):
            self._ensure_management_property_tab_visible(True)
        if hasattr(self, "_hide_all_management_edit_pages"):
            self._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]

    def _update_unit_tag_property_panel_for_selection(self, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新单位标签编辑表单。"""
        if not hasattr(self, "management_property_panel"):
            return

        # 旧实现已由 `UnitTagSection.build_inline_edit_form` 取代。
        # 为保持向后兼容，当前方法仅在被显式调用时构建一个精简版表单：
        # 仅包含“标签名称”和“索引ID”两个字段。
        management_panel = self.management_property_panel

        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        section_key, tag_id = selection
        if section_key != "unit_tags" or not tag_id:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        current_package = getattr(self.package_controller, "current_package", None)
        if current_package is None:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        management_view = getattr(current_package, "management", None)
        unit_tags_mapping = getattr(management_view, "unit_tags", None)
        if not isinstance(unit_tags_mapping, dict):
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        tag_payload_any = unit_tags_mapping.get(tag_id)
        if not isinstance(tag_payload_any, dict):
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        tag_payload = tag_payload_any

        # 与 UnitTagSection._get_effective_tag_index 保持一致的索引解析逻辑
        raw_index = tag_payload.get("tag_index")
        if isinstance(raw_index, int):
            index_value = raw_index
        elif isinstance(raw_index, str) and raw_index.isdigit():
            index_value = int(raw_index)
        else:
            tag_id_source_any = tag_payload.get("tag_id", tag_id)
            tag_id_text = str(tag_id_source_any)
            if tag_id_text.isdigit():
                index_value = int(tag_id_text)
            else:
                index_value = None

        if index_value is not None:
            index_text = str(index_value)
        else:
            index_text = ""

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            tag_name_value = str(tag_payload.get("tag_name", ""))

            name_edit = QtWidgets.QLineEdit(tag_name_value)
            index_edit = QtWidgets.QLineEdit(index_text)
            index_edit.setPlaceholderText("可选，仅输入数字，例如 1073741825")

            last_valid_index_text = index_text

            def apply_changes() -> None:
                nonlocal last_valid_index_text

                normalized_name = name_edit.text().strip()
                if normalized_name:
                    tag_payload["tag_name"] = normalized_name
                else:
                    tag_payload["tag_name"] = tag_id

                index_text_after = index_edit.text().strip()
                if index_text_after and not index_text_after.isdigit():
                    index_edit.setText(last_valid_index_text)
                    if hasattr(self, "management_widget"):
                        self.management_widget._refresh_items()  # type: ignore[attr-defined]
                    self._on_immediate_persist_requested(management_keys={"unit_tags"})
                    return

                if index_text_after:
                    tag_payload["tag_index"] = int(index_text_after)
                    last_valid_index_text = index_text_after
                else:
                    tag_payload.pop("tag_index", None)
                    last_valid_index_text = ""

                if hasattr(self, "management_widget"):
                    self.management_widget._refresh_items()  # type: ignore[attr-defined]
                self._on_immediate_persist_requested(management_keys={"unit_tags"})

            name_edit.editingFinished.connect(apply_changes)
            index_edit.editingFinished.connect(apply_changes)

            form_layout.addRow("标签ID", QtWidgets.QLabel(tag_id))
            form_layout.addRow("标签名称", name_edit)
            form_layout.addRow("索引ID", index_edit)

        display_name_value = str(tag_payload.get("tag_name", "")).strip()
        display_name = display_name_value or tag_id

        management_panel.build_edit_form(
            title=f"单位标签详情：{display_name}",
            description="在右侧直接修改单位标签的名称与索引ID（可选、纯数字），修改会立即保存到当前视图。",
            build_form=build_form,
        )

        if hasattr(self, "_ensure_management_property_tab_visible"):
            self._ensure_management_property_tab_visible(True)
        if hasattr(self, "_hide_all_management_edit_pages"):
            self._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]

    def _update_save_points_property_panel_for_selection(self, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新局内存档模板编辑表单。"""
        if not hasattr(self, "management_property_panel"):
            return

        management_panel = self.management_property_panel

        from ui.graph.library_pages.management_section_save_points import SavePointsSection

        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        section_key, template_id = selection
        if section_key != "save_points" or not template_id:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        current_package = getattr(self.package_controller, "current_package", None)
        if current_package is None:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        # 通过 SavePointsSection 的辅助方法确保配置结构完整并找到当前模板。
        config_data = SavePointsSection._ensure_config(current_package)  # type: ignore[arg-type]
        template_payload = SavePointsSection._find_template_by_id(config_data, template_id)
        if template_payload is None:
            management_panel.clear()
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        def build_form(form_layout: QtWidgets.QFormLayout) -> None:
            template_name_value = str(template_payload.get("template_name", ""))
            description_value = str(template_payload.get("description", ""))

            entries_value = template_payload.get("entries", [])
            entry_count = 0
            if isinstance(entries_value, list):
                for entry in entries_value:
                    if isinstance(entry, dict):
                        entry_count += 1

            name_edit = QtWidgets.QLineEdit(template_name_value)
            description_edit = QtWidgets.QTextEdit()
            description_edit.setPlainText(description_value)
            description_edit.setMinimumHeight(60)
            description_edit.setMaximumHeight(120)

            active_checkbox = QtWidgets.QCheckBox("将该模板设为当前启用模板")
            enabled_flag_local = bool(config_data.get("enabled", False))
            active_template_id = str(config_data.get("active_template_id", "")).strip()
            is_active_template_local = enabled_flag_local and active_template_id == template_id
            active_checkbox.setChecked(is_active_template_local)

            template_id_label = QtWidgets.QLabel(template_id)

            def build_summary_text() -> str:
                status_text = "已启用" if bool(config_data.get("enabled", False)) else "未启用"
                return f"条目数：{entry_count}    当前状态：{status_text}"

            summary_label = QtWidgets.QLabel(build_summary_text())
            summary_label.setWordWrap(True)

            def apply_changes() -> None:
                normalized_name = name_edit.text().strip()
                template_payload["template_name"] = normalized_name or template_id
                template_payload["description"] = description_edit.toPlainText().strip()

                is_currently_active = bool(config_data.get("enabled", False)) and str(
                    config_data.get("active_template_id", "")
                ).strip() == template_id

                if active_checkbox.isChecked():
                    config_data["enabled"] = True
                    config_data["active_template_id"] = template_id
                else:
                    # 若当前模板原本为启用模板且被取消勾选，则关闭局内存档功能。
                    if is_currently_active:
                        config_data["enabled"] = False
                        config_data["active_template_id"] = ""

                summary_label.setText(build_summary_text())

                if hasattr(self, "management_widget"):
                    self.management_widget._refresh_items()  # type: ignore[attr-defined]
                self._on_immediate_persist_requested(management_keys={"save_points"})

            name_edit.editingFinished.connect(apply_changes)
            description_edit.textChanged.connect(lambda: apply_changes())
            active_checkbox.stateChanged.connect(lambda _state: apply_changes())

            form_layout.addRow("模板名称", name_edit)
            form_layout.addRow("模板 ID", template_id_label)
            form_layout.addRow("概要", summary_label)
            form_layout.addRow("", active_checkbox)
            form_layout.addRow("描述", description_edit)

        management_panel.build_edit_form(
            title="局内存档模板详情",
            description="在右侧直接编辑局内存档模板名称、描述与启用状态，修改会立即保存到当前视图。",
            build_form=build_form,
        )

        if hasattr(self, "_ensure_management_property_tab_visible"):
            self._ensure_management_property_tab_visible(True)
        if hasattr(self, "_hide_all_management_edit_pages"):
            self._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]

    def _update_main_camera_panel_for_selection(self, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新主镜头编辑面板。"""
        if not hasattr(self, "main_camera_panel"):
            return

        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            self.main_camera_panel.clear()
            if hasattr(self, "_ensure_main_camera_editor_tab_visible"):
                self._ensure_main_camera_editor_tab_visible(False)
            return

        section_key, camera_id = selection
        if section_key != "main_cameras" or not camera_id:
            self.main_camera_panel.clear()
            if hasattr(self, "_ensure_main_camera_editor_tab_visible"):
                self._ensure_main_camera_editor_tab_visible(False)
            return

        package = getattr(self.package_controller, "current_package", None)
        if package is None:
            self.main_camera_panel.clear()
            if hasattr(self, "_ensure_main_camera_editor_tab_visible"):
                self._ensure_main_camera_editor_tab_visible(False)
            return

        self.main_camera_panel.set_context(package, camera_id)
        if hasattr(self, "_ensure_main_camera_editor_tab_visible"):
            self._ensure_main_camera_editor_tab_visible(True)

    def _update_peripheral_system_panel_for_selection(self, has_selection: bool) -> None:
        """根据当前管理库选中记录刷新外围系统编辑面板。"""
        if not hasattr(self, "peripheral_system_panel"):
            return

        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            self.peripheral_system_panel.clear()
            if hasattr(self, "_ensure_peripheral_system_editor_tab_visible"):
                self._ensure_peripheral_system_editor_tab_visible(False)
            return

        section_key, system_id = selection
        if section_key != "peripheral_systems" or not system_id:
            self.peripheral_system_panel.clear()
            if hasattr(self, "_ensure_peripheral_system_editor_tab_visible"):
                self._ensure_peripheral_system_editor_tab_visible(False)
            return

        package = getattr(self.package_controller, "current_package", None)
        if package is None:
            self.peripheral_system_panel.clear()
            if hasattr(self, "_ensure_peripheral_system_editor_tab_visible"):
                self._ensure_peripheral_system_editor_tab_visible(False)
            return

        self.peripheral_system_panel.set_context(package, system_id)

        # 同步外围系统模板的“所属存档”多选行
        packages, membership = self._get_management_packages_and_membership("peripheral_systems", system_id)
        if hasattr(self.peripheral_system_panel, "set_current_system_id"):
            self.peripheral_system_panel.set_current_system_id(system_id)  # type: ignore[attr-defined]
        if hasattr(self.peripheral_system_panel, "set_packages_and_membership"):
            self.peripheral_system_panel.set_packages_and_membership(  # type: ignore[attr-defined]
                packages,
                membership,
            )
        if hasattr(self, "_ensure_peripheral_system_editor_tab_visible"):
            self._ensure_peripheral_system_editor_tab_visible(True)

    # --- 装备词条/标签/类型 专用面板 -----------------------------------------

    @staticmethod
    def _is_equipment_entry_payload(payload: object) -> bool:
        return isinstance(payload, dict) and (
            ("entry_name" in payload) or ("entry_type" in payload)
        )

    @staticmethod
    def _is_equipment_tag_payload(payload: object) -> bool:
        return isinstance(payload, dict) and ("tag_name" in payload)

    @staticmethod
    def _is_equipment_type_payload(payload: object) -> bool:
        return isinstance(payload, dict) and (("type_name" in payload) or ("allowed_slots" in payload))

    def _get_equipment_payload(
        self, package: object, storage_id: str
    ) -> Optional[Dict[str, Any]]:
        management_view = getattr(package, "management", None)
        equipment_map = getattr(management_view, "equipment_data", None)
        if not isinstance(equipment_map, dict):
            return None
        payload_any = equipment_map.get(storage_id)
        return payload_any if isinstance(payload_any, dict) else None

    def _update_equipment_entry_panel_for_selection(self, has_selection: bool) -> None:
        if not hasattr(self, "equipment_entry_panel"):
            return

        panel = self.equipment_entry_panel

        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            panel.clear()
            if hasattr(self, "_ensure_equipment_entry_editor_tab_visible"):
                self._ensure_equipment_entry_editor_tab_visible(False)
            return

        section_key, storage_id = selection
        if section_key != "equipment_entries" or not storage_id:
            panel.clear()
            if hasattr(self, "_ensure_equipment_entry_editor_tab_visible"):
                self._ensure_equipment_entry_editor_tab_visible(False)
            return

        package = self._get_current_management_package()
        if package is None:
            panel.clear()
            if hasattr(self, "_ensure_equipment_entry_editor_tab_visible"):
                self._ensure_equipment_entry_editor_tab_visible(False)
            return

        payload = self._get_equipment_payload(package, storage_id)
        if not self._is_equipment_entry_payload(payload):
            panel.clear()
            if hasattr(self, "_ensure_equipment_entry_editor_tab_visible"):
                self._ensure_equipment_entry_editor_tab_visible(False)
            return

        # 绑定上下文与表单
        panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]

        packages, membership = self._get_management_packages_and_membership("equipment_data", storage_id)
        panel.set_packages_and_membership(packages, membership)

        if hasattr(self, "_ensure_equipment_entry_editor_tab_visible"):
            self._ensure_equipment_entry_editor_tab_visible(True)
        if hasattr(self, "_hide_all_management_edit_pages"):
            self._hide_all_management_edit_pages("equipment_entries")  # type: ignore[attr-defined]

    def _update_equipment_tag_panel_for_selection(self, has_selection: bool) -> None:
        if not hasattr(self, "equipment_tag_panel"):
            return

        panel = self.equipment_tag_panel
        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            panel.clear()
            if hasattr(self, "_ensure_equipment_tag_editor_tab_visible"):
                self._ensure_equipment_tag_editor_tab_visible(False)
            return

        section_key, storage_id = selection
        if section_key != "equipment_tags" or not storage_id:
            panel.clear()
            if hasattr(self, "_ensure_equipment_tag_editor_tab_visible"):
                self._ensure_equipment_tag_editor_tab_visible(False)
            return

        package = self._get_current_management_package()
        if package is None:
            panel.clear()
            if hasattr(self, "_ensure_equipment_tag_editor_tab_visible"):
                self._ensure_equipment_tag_editor_tab_visible(False)
            return

        payload = self._get_equipment_payload(package, storage_id)
        if not self._is_equipment_tag_payload(payload):
            panel.clear()
            if hasattr(self, "_ensure_equipment_tag_editor_tab_visible"):
                self._ensure_equipment_tag_editor_tab_visible(False)
            return

        panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]
        packages, membership = self._get_management_packages_and_membership("equipment_data", storage_id)
        panel.set_packages_and_membership(packages, membership)

        if hasattr(self, "_ensure_equipment_tag_editor_tab_visible"):
            self._ensure_equipment_tag_editor_tab_visible(True)
        if hasattr(self, "_hide_all_management_edit_pages"):
            self._hide_all_management_edit_pages("equipment_tags")  # type: ignore[attr-defined]

    def _update_equipment_type_panel_for_selection(self, has_selection: bool) -> None:
        if not hasattr(self, "equipment_type_panel"):
            return

        panel = self.equipment_type_panel
        selection = self._get_management_current_selection()
        if not has_selection or selection is None:
            panel.clear()
            if hasattr(self, "_ensure_equipment_type_editor_tab_visible"):
                self._ensure_equipment_type_editor_tab_visible(False)
            return

        section_key, storage_id = selection
        if section_key != "equipment_types" or not storage_id:
            panel.clear()
            if hasattr(self, "_ensure_equipment_type_editor_tab_visible"):
                self._ensure_equipment_type_editor_tab_visible(False)
            return

        package = self._get_current_management_package()
        if package is None:
            panel.clear()
            if hasattr(self, "_ensure_equipment_type_editor_tab_visible"):
                self._ensure_equipment_type_editor_tab_visible(False)
            return

        payload = self._get_equipment_payload(package, storage_id)
        if not self._is_equipment_type_payload(payload):
            panel.clear()
            if hasattr(self, "_ensure_equipment_type_editor_tab_visible"):
                self._ensure_equipment_type_editor_tab_visible(False)
            return

        panel._set_context_internal(package, storage_id, payload)  # type: ignore[attr-defined]
        packages, membership = self._get_management_packages_and_membership("equipment_data", storage_id)
        panel.set_packages_and_membership(packages, membership)

        if hasattr(self, "_ensure_equipment_type_editor_tab_visible"):
            self._ensure_equipment_type_editor_tab_visible(True)
        if hasattr(self, "_hide_all_management_edit_pages"):
            self._hide_all_management_edit_pages("equipment_types")  # type: ignore[attr-defined]

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
            struct_ids_value = package_index.resources.management.get(
                "struct_definitions", []
            )
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
        if not isinstance(manager, PackageIndexManager) or not isinstance(
            resource_manager, ResourceManager
        ):
            return

        config: Optional[SignalConfig] = None
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
        from engine.configs.resource_types import ResourceType
        from engine.resources.package_index_manager import PackageIndexManager
        from engine.resources.resource_manager import ResourceManager

        manager = getattr(self, "package_index_manager", None)
        resource_manager = getattr(self, "resource_manager", None)
        if not isinstance(manager, PackageIndexManager) or not isinstance(
            resource_manager, ResourceManager
        ):
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
        from engine.configs.resource_types import ResourceType
        from engine.configs.specialized.node_graph_configs import (
            STRUCT_TYPE_BASIC,
            STRUCT_TYPE_INGAME_SAVE,
        )
        from engine.resources.resource_manager import ResourceManager
        from ui.graph.library_pages.management_section_struct_definitions import (
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
        if not isinstance(value_entries, list) or not any(
            isinstance(entry, dict) for entry in value_entries
        ):
            return

        section_helper = StructDefinitionSection()
        all_records = section_helper._load_struct_records(resource_manager)  # type: ignore[attr-defined]

        for existing_id, existing_data in all_records:
            if existing_id == struct_id:
                continue
            existing_name = existing_data.get("name") or existing_data.get("struct_name")
            if isinstance(existing_name, str) and existing_name == struct_name:
                from ui.foundation import dialog_utils

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

    def _resolve_management_resource_binding_for_section(
        self,
        section_key: str,
    ) -> ManagementResourceBinding | None:
        """根据 section_key 查找唯一的管理资源绑定信息。

        仅当该 Section 精确绑定到一类管理资源时返回对应绑定；
        对于聚合视图（如局内存档、外围系统等）或界面控件组等特殊 Section，
        返回 None，交由调用方自行处理。
        """
        for spec in MANAGEMENT_SECTIONS:
            if spec.key != section_key:
                continue
            if len(spec.resources) != 1:
                return None
            return spec.resources[0]
        return None

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
        from ui.graph.library_pages.management_section_variable import VariableSection

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

    def _on_management_edit_page_data_updated(self) -> None:
        """右侧管理编辑页数据更新后，刷新管理库列表并立即持久化。"""
        if hasattr(self, "management_widget"):
            self.management_widget._refresh_items()  # type: ignore[attr-defined]
        selection = self._get_management_current_selection()
        management_keys: set[str] = set()
        if selection is not None:
            section_key = selection[0]
            if isinstance(section_key, str) and section_key:
                management_keys.add(section_key)
        self._on_immediate_persist_requested(
            management_keys=management_keys if management_keys else None
        )

    def _on_management_selection_changed(
        self,
        has_selection: bool,
        title: str,
        description: str,
        rows: list[tuple[str, str]],
    ) -> None:
        """管理页面选中记录变化时，同步到主窗口右侧属性与编辑面板。"""
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if not hasattr(self, "management_property_panel"):
            return

        selection = self._get_management_current_selection()
        section_key = selection[0] if selection is not None else None
        item_id = selection[1] if selection is not None else ""
        print(
            "[MANAGEMENT-LIB] _on_management_selection_changed:",
            f"has_selection={has_selection!r}, section_key={section_key!r}, "
            f"item_id={item_id!r}, current_view_mode={current_view_mode}",
        )

        if current_view_mode != ViewMode.MANAGEMENT:
            return

        if not has_selection:
            self._on_library_selection_state_changed(False, {"section_key": section_key})
            return

        # 信号管理与结构体定义：仅保留各自的专用编辑面板，不再展示通用“属性”标签
        if section_key == "signals":
            self._update_signal_property_panel_for_selection(True)
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        if section_key in ("struct_definitions", "ingame_struct_definitions"):
            self._update_struct_property_panel_for_selection(True)
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            return

        if section_key == "main_cameras":
            if hasattr(self, "_update_main_camera_panel_for_selection"):
                self._update_main_camera_panel_for_selection(True)
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            # 主镜头使用专用编辑面板，不再保留通用编辑页
            if hasattr(self, "_hide_all_management_edit_pages"):
                self._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]
            return

        if section_key == "peripheral_systems":
            if hasattr(self, "_update_peripheral_system_panel_for_selection"):
                self._update_peripheral_system_panel_for_selection(True)
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            if hasattr(self, "_hide_all_management_edit_pages"):
                self._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]
            return
        if section_key == "equipment_entries":
            if hasattr(self, "_update_equipment_entry_panel_for_selection"):
                self._update_equipment_entry_panel_for_selection(True)
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            if hasattr(self, "_hide_all_management_edit_pages"):
                self._hide_all_management_edit_pages("equipment_entries")  # type: ignore[attr-defined]
            return
        if section_key == "equipment_tags":
            if hasattr(self, "_update_equipment_tag_panel_for_selection"):
                self._update_equipment_tag_panel_for_selection(True)
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            if hasattr(self, "_hide_all_management_edit_pages"):
                self._hide_all_management_edit_pages("equipment_tags")  # type: ignore[attr-defined]
            return
        if section_key == "equipment_types":
            if hasattr(self, "_update_equipment_type_panel_for_selection"):
                self._update_equipment_type_panel_for_selection(True)
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(False)
            if hasattr(self, "_hide_all_management_edit_pages"):
                self._hide_all_management_edit_pages("equipment_types")  # type: ignore[attr-defined]
            return

        # 其余管理类型：优先尝试使用 Section 提供的右侧就地编辑表单；
        # 若 Section 未实现内联表单，则退化为只读摘要展示。
        inline_handled = False
        binding: ManagementResourceBinding | None = None
        section_obj = None
        if section_key:
            binding = self._resolve_management_resource_binding_for_section(section_key)
            section_obj = get_management_section_by_key(section_key)

        # 所属存档多选行启用规则：
        # - 默认仅对按 ID 列表管理的资源类型启用（aggregation_mode == "id_list"）；
        # - 对于局内存档模板（save_points）、货币与背包（currency_backpack）和关卡设置
        #   （level_settings），即便采用单配置聚合语义，仍允许在属性面板顶部按“配置体 ID”
        #   维护包级归属关系，使其行为与战斗预设模板保持一致。
        membership_supported = False
        if section_key == "variable":
            membership_supported = True
        elif binding is not None:
            if binding.key in {"save_points", "currency_backpack", "level_settings"}:
                membership_supported = True
            else:
                membership_supported = getattr(binding, "aggregation_mode", "id_list") == "id_list"

        if hasattr(self, "management_property_panel") and membership_supported and item_id and binding is not None:
            if section_key == "variable":
                packages, membership, variable_ids = self._get_packages_and_membership_for_level_variable_group(item_id)
                if section_obj is not None and hasattr(section_obj, "set_usage_text"):
                    usage_names = [pkg.get("name", pkg.get("package_id", "")) for pkg in packages if pkg.get("package_id") in membership]
                    if usage_names:
                        section_obj.set_usage_text("，".join(usage_names))
                    else:
                        section_obj.set_usage_text("未被任何存档引用")
                self.management_property_panel.set_membership_context(  # type: ignore[attr-defined]
                    section_key,
                    binding.key,
                    item_id,
                    packages,
                    membership,
                )
            else:
                packages, membership = self._get_management_packages_and_membership(binding.key, item_id)
                self.management_property_panel.set_membership_context(  # type: ignore[attr-defined]
                    section_key,
                    binding.key,
                    item_id,
                    packages,
                    membership,
                )
        elif hasattr(self, "management_property_panel"):
            # 无法解析到明确的管理资源，或当前 Section 使用聚合配置体语义（单配置/聚合视图），
            # 清空所属存档上下文但仍保留下方表单区域。
            self.management_property_panel._clear_membership_context()  # type: ignore[attr-defined]

        if hasattr(self, "_update_right_panel_visibility"):
            self._update_right_panel_visibility()

        if section_key and item_id:
            current_package = getattr(self.package_controller, "current_package", None)
            management_panel = self.management_property_panel

            if current_package is not None and section_obj is not None:
                def _on_inline_changed() -> None:
                    if hasattr(self, "management_widget"):
                        self.management_widget._refresh_items()  # type: ignore[attr-defined]
                    key_set = {section_key} if isinstance(section_key, str) and section_key else None
                    self._on_immediate_persist_requested(management_keys=key_set)

                inline_result = section_obj.build_inline_edit_form(
                    parent=management_panel,
                    package=current_package,
                    item_id=item_id,
                    on_changed=_on_inline_changed,
                )
                if inline_result is not None:
                    inline_title, inline_description, build_form = inline_result
                    management_panel.build_edit_form(
                        title=inline_title,
                        description=inline_description,
                        build_form=build_form,
                    )
                    if hasattr(self, "_ensure_management_property_tab_visible"):
                        self._ensure_management_property_tab_visible(True)
                    if hasattr(self, "_hide_all_management_edit_pages"):
                        self._hide_all_management_edit_pages(None)  # type: ignore[attr-defined]
                    inline_handled = True

        if not inline_handled:
            # 使用只读摘要表单展示
            if hasattr(self, "management_property_panel"):
                self.management_property_panel.set_header(title, description)
                self.management_property_panel.set_rows(rows)
            if hasattr(self, "_ensure_management_property_tab_visible"):
                self._ensure_management_property_tab_visible(True)

    # === 数据更新与持久化 ===

    def _on_library_page_data_changed(self, event: LibraryChangeEvent) -> None:
        """统一处理库/列表页发出的 LibraryChangeEvent。

        当前实现仅关心“有真实数据变更”这一事实，具体的变更内容与范围
        仍由各库页自身与控制器协同处理；后续如需按资源类型做差异化处理，
        可在此方法中根据 event.kind / event.operation / event.context 分派逻辑。
        """
        template_id: str | None = None
        instance_id: str | None = None
        management_keys: set[str] | None = None
        combat_dirty = False
        signals_dirty = False
        graph_dirty = False
        index_dirty = False

        kind = getattr(event, "kind", "") or ""
        operation = getattr(event, "operation", "") or ""
        context = getattr(event, "context", None)

        if kind == "template":
            template_id = event.id
        elif kind == "instance":
            instance_id = event.id
        elif kind == "graph":
            graph_dirty = True
        elif kind == "combat":
            combat_dirty = True
            index_dirty = True
        elif kind == "management":
            combat_dirty = False
            section_key = None
            if isinstance(context, dict):
                section_key = context.get("section_key")
            if isinstance(section_key, str) and section_key:
                management_keys = {section_key}
            index_dirty = True
        elif kind == "signal":
            signals_dirty = True
            index_dirty = True

        if operation in {"create", "delete"}:
            index_dirty = True

        self._on_immediate_persist_requested(
            graph_dirty=graph_dirty,
            template_id=template_id,
            instance_id=instance_id,
            management_keys=management_keys,
            combat_dirty=combat_dirty,
            signals_dirty=signals_dirty,
            index_dirty=index_dirty,
        )

    def _on_data_updated(self) -> None:
        """右侧属性面板的数据更新"""
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())

        # 模板/实例/关卡实体属性面板共用同一条“数据更新”链路，但不同模式下的
        # 刷新需求并不相同：
        # - 在元件库或其它以模板为主的视图中，仍需要刷新元件列表以反映名称/描述等改动；
        # - 在实体摆放视图中，编辑的是实体实例（object_type == "instance"）时，
        #   不应触发元件库的选中事件去抢占右侧属性上下文，否则会出现
        #   “修改实体 GUID → 右侧突然切回某个元件属性”的错觉。
        if current_view_mode != ViewMode.PLACEMENT:
            # 非实体摆放模式下，保持原有行为：始终刷新元件库列表。
            self.template_widget.refresh_templates()
        else:
            # 实体摆放模式中，仅当当前属性面板上下文不是实体实例时，才刷新元件库。
            # 例如：通过任务清单或节点图库在此模式下只读查看某个元件。
            if getattr(self.property_panel, "object_type", "") != "instance":
                self.template_widget.refresh_templates()

        if (
            current_view_mode == ViewMode.PLACEMENT
            and getattr(self.property_panel, "object_type", "") == "instance"
        ):
            self.placement_widget.refresh_instances()

        # 右侧属性面板的任何改动都应立即持久化到资源库与存档索引，
        # 避免仅停留在 UI 模型或内存视图中。
        obj = getattr(self.property_panel, "current_object", None)
        object_type = getattr(self.property_panel, "object_type", None)
        template_id: str | None = None
        instance_id: str | None = None
        if object_type == "template" and hasattr(obj, "template_id"):
            template_id = getattr(obj, "template_id")
        elif object_type in ("instance", "level_entity") and hasattr(obj, "instance_id"):
            instance_id = getattr(obj, "instance_id")
        self._on_immediate_persist_requested(
            template_id=template_id,
            instance_id=instance_id,
        )

    def _on_immediate_persist_requested(
        self,
        *,
        graph_dirty: bool = False,
        template_id: str | None = None,
        instance_id: str | None = None,
        management_keys: set[str] | None = None,
        combat_dirty: bool = False,
        signals_dirty: bool = False,
        index_dirty: bool = False,
    ) -> None:
        """要求立即将当前存档的增删改写入本地资源与索引（按脏块增量落盘）。

        为避免在短时间内因多次属性变更触发频繁落盘，这里使用单次定时器做轻量去抖：
        在最近一次请求后的短暂间隔内合并为一次实际保存。
        """
        if not hasattr(self, "package_controller"):
            return

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if not current_package_id:
            return

        controller = getattr(self, "package_controller")
        if controller is not None:
            if graph_dirty:
                controller.mark_graph_dirty()
            if template_id:
                controller.mark_template_dirty(template_id)
            if instance_id:
                controller.mark_instance_dirty(instance_id)
            if management_keys:
                controller.mark_management_dirty(management_keys)
            if combat_dirty:
                controller.mark_combat_dirty()
            if signals_dirty:
                controller.mark_signals_dirty()
            if index_dirty:
                controller.mark_index_dirty()

        # 懒初始化去抖定时器
        timer = getattr(self, "_immediate_persist_timer", None)
        if timer is None or not isinstance(timer, QtCore.QTimer):
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)

            def _do_persist() -> None:
                # 定时器触发时再次确认仍存在有效存档ID
                controller = getattr(self, "package_controller", None)
                if controller is None:
                    return
                package_id = getattr(controller, "current_package_id", None)
                if not package_id:
                    return
                if hasattr(controller, "save_dirty_blocks"):
                    controller.save_dirty_blocks()
                else:
                    controller.save_package()

            timer.timeout.connect(_do_persist)
            setattr(self, "_immediate_persist_timer", timer)

        # 短暂合并多次请求（例如快速编辑/识别联动等场景）
        # 200ms 通常足以合并一批连续 UI 事件，又不会让用户感觉到明显延迟。
        timer.start(200)

    # === 资源归属（存档 <-> 图/复合节点/模板） ===

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