"""库页选中状态与右侧面板联动（模板/实例/关卡实体/战斗预设）。"""

from __future__ import annotations

from typing import Any, Dict

from app.models.view_modes import ViewMode
from engine.utils.logging.logger import log_info
from app.ui.graph.library_pages.library_scaffold import LibrarySelection
from app.ui.main_window.right_panel_contracts import (
    CONTRACT_SHOW_ITEM_EDITOR,
    CONTRACT_SHOW_PLAYER_CLASS_EDITOR,
    CONTRACT_SHOW_PLAYER_EDITOR,
    CONTRACT_SHOW_PROPERTY,
    CONTRACT_SHOW_SKILL_EDITOR,
)


class LibrarySelectionMixin:
    """处理库页选中/取消选中与右侧面板收起/展示。"""

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
            view_state = getattr(self, "view_state", None)
            clear_method = getattr(view_state, "clear_template_selection", None)
            if callable(clear_method):
                clear_method()
            if hasattr(self, "property_panel"):
                self.property_panel.clear()
            self.right_panel.ensure_visible("property", visible=False)
            self.right_panel.update_visibility()
            return

        if current_view_mode == ViewMode.PLACEMENT or source == "instance":
            view_state = getattr(self, "view_state", None)
            clear_method = getattr(view_state, "clear_placement_selection", None)
            if callable(clear_method):
                clear_method()
            if hasattr(self, "property_panel"):
                self.property_panel.clear()
            self.right_panel.ensure_visible("property", visible=False)
            self.right_panel.update_visibility()
            return

        is_combat_event = source == "combat" or section_key in (
            "player_template",
            "player_class",
            "skill",
            "item",
        )
        if current_view_mode == ViewMode.COMBAT or is_combat_event:
            view_state = getattr(self, "view_state", None)
            clear_method = getattr(view_state, "clear_combat_selection", None)
            if callable(clear_method):
                clear_method()
            self._reset_combat_detail_panels()
            return

        if current_view_mode == ViewMode.MANAGEMENT or source == "management":
            view_state = getattr(self, "view_state", None)
            clear_method = getattr(view_state, "clear_management_selection", None)
            if callable(clear_method):
                clear_method()
            self._reset_management_panels_for_empty_selection(section_key)
            return

        self.right_panel.update_visibility()

    def _on_library_page_selection_changed(self, selection: object) -> None:
        """统一处理库页 selection_changed(LibrarySelection | None)。

        页面侧仍负责在“无选中”时调用 notify_selection_state(False, context=...) 触发右侧收起；
        此方法只负责在“有选中”时将其分发到既有的 *_selected 处理链路，复用原有
        ViewMode 限制与右侧面板策略，避免行为漂移。
        """
        if selection is None:
            return
        if not isinstance(selection, LibrarySelection):
            return

        if selection.kind == "template":
            self._on_template_selected(selection.id)
            return

        if selection.kind == "instance":
            self._on_instance_selected(selection.id)
            return

        if selection.kind == "level_entity":
            self._on_level_entity_selected()
            return

        if selection.kind == "combat":
            section_key = ""
            if isinstance(selection.context, dict):
                raw = selection.context.get("section_key")
                if isinstance(raw, str):
                    section_key = raw
            if section_key == "player_template":
                self._on_player_template_selected(selection.id)
            elif section_key == "player_class":
                self._on_player_class_selected(selection.id)
            elif section_key == "skill":
                self._on_skill_selected(selection.id)
            elif section_key == "item":
                self._on_item_selected(selection.id)
            return

    def _reset_combat_detail_panels(self) -> None:
        """清空战斗预设模式下的右侧详情标签与上下文。"""
        panel_attrs = ("player_editor_panel", "player_class_panel", "skill_panel", "item_panel")
        for panel_attr in panel_attrs:
            panel = getattr(self, panel_attr, None)
            if panel is not None and hasattr(panel, "set_context"):
                panel.set_context(None, None)  # type: ignore[arg-type]

        self.right_panel.reset_combat_detail_tabs()
        self.right_panel.update_visibility()

    def _reset_management_panels_for_empty_selection(self, section_key: str | None) -> None:
        """清空管理模式下的属性与专用编辑标签。"""
        if hasattr(self, "management_property_panel"):
            self.management_property_panel.clear()
        self.right_panel.ensure_visible("management_property", visible=False)
        self.right_panel.apply_management_selection(section_key, has_selection=False)

        get_coordinator = getattr(self, "_get_management_panels_coordinator", None)
        if callable(get_coordinator):
            coordinator = get_coordinator()
            reset_method = getattr(coordinator, "reset_special_panels", None)
            if callable(reset_method):
                reset_method(self)

        self.right_panel.update_visibility()

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
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PROPERTY)
            view_state = getattr(self, "view_state", None)
            template_state = getattr(view_state, "template", None)
            if template_state is not None:
                setattr(template_state, "template_id", str(template_id))
            self.schedule_ui_session_state_save()

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
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PROPERTY)
            view_state = getattr(self, "view_state", None)
            placement_state = getattr(view_state, "placement", None)
            if placement_state is not None:
                setattr(placement_state, "instance_id", str(instance_id))
                setattr(placement_state, "has_level_entity_selected", False)
            self.schedule_ui_session_state_save()

    def _on_level_entity_selected(self) -> None:
        """关卡实体选中"""
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        # 关卡实体属性同样只应在实体摆放模式下展示。
        if current_view_mode != ViewMode.PLACEMENT:
            return

        package = self.package_controller.current_package
        if package and package.level_entity:
            self.property_panel.set_level_entity(package)
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PROPERTY)
            view_state = getattr(self, "view_state", None)
            placement_state = getattr(view_state, "placement", None)
            if placement_state is not None:
                setattr(placement_state, "has_level_entity_selected", True)
            self.schedule_ui_session_state_save()

    # === 战斗预设 ===

    def _on_player_template_selected(self, template_id: str) -> None:
        """战斗预设-玩家模板选中"""
        package = self.package_controller.current_package
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        log_info(
            "[COMBAT-PRESETS] player_template_selected: template_id={} current_view_mode={} has_package={}",
            template_id,
            current_view_mode,
            bool(package),
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
        view_state = getattr(self, "view_state", None)
        combat_state = getattr(view_state, "combat", None)
        if combat_state is not None:
            setattr(combat_state, "current_section_key", "player_template")
            setattr(combat_state, "current_item_id", str(template_id))
        if current_view_mode == ViewMode.COMBAT:
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PLAYER_EDITOR)

    def _on_skill_selected(self, skill_id: str) -> None:
        """战斗预设-技能选中"""
        package = self.package_controller.current_package
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        log_info(
            "[COMBAT-PRESETS] skill_selected: skill_id={} current_view_mode={} has_package={}",
            skill_id,
            current_view_mode,
            bool(package),
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
        view_state = getattr(self, "view_state", None)
        combat_state = getattr(view_state, "combat", None)
        if combat_state is not None:
            setattr(combat_state, "current_section_key", "skill")
            setattr(combat_state, "current_item_id", str(skill_id))
        # 在战斗预设模式下选中技能时，自动切到“技能”标签，并按需插入对应标签页
        if current_view_mode == ViewMode.COMBAT:
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_SKILL_EDITOR)

    def _on_item_selected(self, item_id: str) -> None:
        """战斗预设-道具选中"""
        package = self.package_controller.current_package
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        log_info(
            "[COMBAT-PRESETS] item_selected: item_id={} current_view_mode={} has_package={}",
            item_id,
            current_view_mode,
            bool(package),
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
        view_state = getattr(self, "view_state", None)
        combat_state = getattr(view_state, "combat", None)
        if combat_state is not None:
            setattr(combat_state, "current_section_key", "item")
            setattr(combat_state, "current_item_id", str(item_id))
        if current_view_mode == ViewMode.COMBAT:
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_ITEM_EDITOR)

    def _on_player_class_selected(self, class_id: str) -> None:
        """战斗预设-职业选中"""
        package = self.package_controller.current_package
        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        log_info(
            "[COMBAT-PRESETS] player_class_selected: class_id={} current_view_mode={} has_package={}",
            class_id,
            current_view_mode,
            bool(package),
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
            self.right_panel.apply_visibility_contract(CONTRACT_SHOW_PLAYER_CLASS_EDITOR)


