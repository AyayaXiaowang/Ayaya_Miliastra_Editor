"""存档库（PACKAGES）页面的右侧详情展示与跳转逻辑。"""

from __future__ import annotations

from typing import Any, Dict

from app.models.view_modes import ViewMode
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.package_view import PackageView
from engine.utils.logging.logger import log_info
from app.ui.management.section_registry import (
    MANAGEMENT_RESOURCE_BINDINGS,
    MANAGEMENT_RESOURCE_TITLES,
)
from app.ui.main_window.right_panel_contracts import (
    CONTRACT_HIDE_ALL,
    CONTRACT_SHOW_GRAPH_PROPERTY,
    CONTRACT_SHOW_MANAGEMENT_PROPERTY,
    CONTRACT_SHOW_PROPERTY,
    CONTRACT_SHOW_ITEM_EDITOR,
    CONTRACT_SHOW_PLAYER_CLASS_EDITOR,
    CONTRACT_SHOW_PLAYER_EDITOR,
    CONTRACT_SHOW_SKILL_EDITOR,
)


class PackagesViewMixin:
    """处理存档库页面的资源激活事件与右侧面板互斥逻辑。"""

    def _on_packages_page_package_load_requested(self, package_id: str) -> None:
        """存档库页面点击左侧存档条目时，请求切换主窗口当前存档上下文。

        设计约定：
        - 仅在 ViewMode.PACKAGES 下生效，避免后台刷新/会话恢复等程序性选中导致意外切包；
        - 允许切换到 "global_view"。
        """
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_view_mode != ViewMode.PACKAGES:
            return
        if not isinstance(package_id, str) or not package_id:
            return
        if not hasattr(self, "package_controller"):
            return

        current_package_id = getattr(self.package_controller, "current_package_id", None)
        if package_id != current_package_id:
            request_method = getattr(self, "_request_load_package", None)
            if callable(request_method):
                request_method(package_id)
            else:
                self.package_controller.load_package(package_id)

    def _get_global_resource_view(self) -> GlobalResourceView:
        """获取（懒加载）共享资源视图，用于在存档库/任务清单等上下文中只读预览资源。

        设计约定：
        - 不依赖当前项目存档选择，直接基于 ResourceManager 聚合共享资源；
        - 仅在需要只读预览模板/实例/关卡实体时使用，写入仍通过控制器与 PackageView 完成。
        """
        if not hasattr(self, "_global_resource_view") or self._global_resource_view is None:
            self._global_resource_view = GlobalResourceView(self.app_state.resource_manager)
        return self._global_resource_view

    def _get_packages_page_selected_package_id(self) -> str:
        """返回存档库页面当前选中的 package_id（来自 PackageLibraryWidget）。"""
        package_library_widget = getattr(self, "package_library_widget", None)
        raw_value = getattr(package_library_widget, "_current_package_id", "")
        return raw_value if isinstance(raw_value, str) else ""

    def _get_packages_scoped_resource_view(self) -> PackageView | GlobalResourceView:
        """在存档库（PACKAGES）页面中，为“点击某个资源条目”提供最合适的资源视图。

        设计动机：
        - 在具体存档被选中时，应优先使用 `PackageView`，避免 `GlobalResourceView` 为获取单条资源
          而全量加载全部模板/实例导致 UI 卡顿；
        - 在“共享资源（global_view）”视图或无法判定包上下文时，回退使用 `GlobalResourceView`。
        """
        package_id = self._get_packages_page_selected_package_id()
        if not package_id or package_id == "global_view":
            return self._get_global_resource_view()

        cached_id = getattr(self, "_packages_scoped_view_package_id", "")
        cached_view = getattr(self, "_packages_scoped_view", None)
        if isinstance(cached_id, str) and cached_id == package_id and isinstance(cached_view, PackageView):
            return cached_view

        package_index_manager = self.app_state.package_index_manager
        resource_manager = self.app_state.resource_manager
        package_index = package_index_manager.load_package_index(package_id)
        if package_index is None:
            return self._get_global_resource_view()

        view = PackageView(package_index, resource_manager)
        self._packages_scoped_view_package_id = package_id
        self._packages_scoped_view = view
        return view

    def _on_package_resource_activated(self, kind: str, resource_id: str) -> None:
        """存档库页面中点击资源条目时，在右侧属性或图属性面板中展示详情。

        kind:
            - "template"     → 元件
            - "instance"     → 实例
            - "level_entity" → 关卡实体
            - "graph"        → 节点图
        """
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        log_info(
            "[PACKAGES] resource_activated: kind={} resource_id={} current_view_mode={}",
            kind,
            resource_id,
            current_view_mode,
        )
        if current_view_mode != ViewMode.PACKAGES:
            return
        if not kind or not resource_id:
            return

        # 模板 / 实例 / 关卡实体：使用 TemplateInstancePanel 展示，并允许直接编辑属性。
        if kind in ("template", "instance", "level_entity"):
            if not hasattr(self, "property_panel"):
                return
            resource_view = self._get_packages_scoped_resource_view()

            if kind == "template":
                if not resource_view.get_template(resource_id):
                    return
                self.property_panel.set_template(resource_view, resource_id)
            elif kind == "instance":
                if not resource_view.get_instance(resource_id):
                    return
                self.property_panel.set_instance(resource_view, resource_id)
            else:
                # 关卡实体：在具体存档视图下应直接取该存档的 level_entity。
                if not resource_view.level_entity:
                    return
                self.property_panel.set_level_entity(resource_view)

            if hasattr(self.property_panel, "set_read_only"):
                # 存档库页面作为“预览与跳转”入口：默认只读，避免在未切包时编辑导致脏标记串包。
                self.property_panel.set_read_only(True)
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PROPERTY)
            return

        # 节点图：使用图属性面板，允许在此页面管理“所属存档”，其它字段保持只读展示。
        if kind == "graph":
            if not hasattr(self, "graph_property_panel"):
                return
            # 存档库页面左侧“选中”仅用于预览：当用户在“预览存档 B”时点击节点图，
            # 不能直接用“当前存档 A”的 ResourceManager 作用域去加载（会误报“不存在”）。
            selected_package_id = self._get_packages_page_selected_package_id()
            current_package_id = str(getattr(self.package_controller, "current_package_id", "") or "")

            should_preview_only = (
                isinstance(selected_package_id, str)
                and bool(selected_package_id)
                and selected_package_id != "global_view"
                and bool(current_package_id)
                and selected_package_id != current_package_id
            )

            if should_preview_only:
                set_preview = getattr(self.graph_property_panel, "set_graph_preview", None)
                if callable(set_preview):
                    set_preview(
                        resource_id,
                        preview_package_id=selected_package_id,
                        current_package_id=current_package_id,
                    )
                else:
                    self.graph_property_panel.set_graph(resource_id)
            else:
                self.graph_property_panel.set_graph(resource_id)
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_GRAPH_PROPERTY)
            return

        if hasattr(self, "_schedule_ui_session_state_save"):
            self.schedule_ui_session_state_save()

        # 战斗预设：在存档视图下复用战斗详情面板浏览玩家模板/职业/技能。
        if kind.startswith("combat_"):
            global_view = self._get_global_resource_view()

            if kind == "combat_player_template":
                if not hasattr(self, "player_editor_panel"):
                    return
                self.player_editor_panel.set_context(global_view, resource_id)
                self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PLAYER_EDITOR)
            elif kind == "combat_player_class":
                if not hasattr(self, "player_class_panel"):
                    return
                self.player_class_panel.set_context(global_view, resource_id)
                self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PLAYER_CLASS_EDITOR)
            elif kind == "combat_skill":
                if not hasattr(self, "skill_panel"):
                    return
                self.skill_panel.set_context(global_view, resource_id)
                self.right_panel.apply_visibility_contract(CONTRACT_SHOW_SKILL_EDITOR)
            elif kind == "combat_item":
                if not hasattr(self, "item_panel"):
                    return
                self.item_panel.set_context(global_view, resource_id)
                self.right_panel.apply_visibility_contract(CONTRACT_SHOW_ITEM_EDITOR)
            else:
                return
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
        log_info(
            "[PACKAGES] management_resource_activated: resource_key={} resource_id={} current_view_mode={}",
            resource_key,
            resource_id,
            current_view_mode,
        )
        if current_view_mode != ViewMode.PACKAGES:
            return
        if not hasattr(self, "management_property_panel"):
            return

        # 分类节点或上下文不完整时，视为“无有效选中对象”，清空并收起属性标签。
        if not resource_key or not resource_id:
            self.management_property_panel.clear()
            self.right_panel.apply_visibility_contract(CONTRACT_HIDE_ALL)
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
        resource_manager = self.app_state.resource_manager
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

        self.right_panel.apply_visibility_contract(CONTRACT_SHOW_MANAGEMENT_PROPERTY)

        self.schedule_ui_session_state_save()

    def _on_package_management_item_requested(
        self,
        section_key: str,
        item_id: str,
        package_id: str,
    ) -> None:
        """存档库页面中双击管理配置条目时，跳转到对应管理页面并选中记录。

        - section_key: 管理页面内部 key（如 "equipment_data" / "save_points" / "signals"）。
        - item_id    : 管理记录 ID；为空字符串时仅切换到对应 section。
        - package_id : 目标视图使用的存档 ID 或特殊视图 ID（"global_view"）。
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


