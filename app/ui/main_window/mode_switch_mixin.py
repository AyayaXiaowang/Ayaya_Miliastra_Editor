"""模式切换 Mixin - 负责视图模式切换和右侧面板管理"""
from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.models.view_modes import ViewMode, RIGHT_PANEL_TABS
from ui.graph.library_pages.library_scaffold import LibrarySelection
from engine.nodes.node_registry import get_node_registry


class ModeSwitchMixin:
    """模式切换相关方法的Mixin"""

    def _tab_title_for_id(self, tab_id: str) -> str:
        """根据tab_id返回标签标题"""
        if tab_id == "graph_property":
            return "图属性"
        if tab_id == "composite_property":
            return "复合节点属性"
        if tab_id == "composite_pins":
            return "虚拟引脚"
        if tab_id == "ui_settings":
            return "界面控件设置"
        if tab_id == "execution_monitor":
            return "执行监控"
        if tab_id == "player_editor":
            return "玩家模板"
        if tab_id == "player_class_editor":
            return "职业"
        if tab_id == "skill_editor":
            return "技能"
        if tab_id == "item_editor":
            return "道具"
        if tab_id == "validation_detail":
            return "详细信息"
        return tab_id

    def _is_dynamic_tab_allowed_in_mode(self, tab_id: str, view_mode: ViewMode) -> bool:
        """判断动态右侧编辑面板在当前视图模式下是否允许保留。

        仅用于在模式切换时统一收起不属于当前模式的“上下文驱动”标签，
        避免管理/战斗预设等专用面板在切换到其它页面后仍然残留。
        """
        if tab_id == "property":
            # 基础属性面板：元件库 / 实体摆放 / 存档库 / 任务清单 中按需使用
            return view_mode in (
                ViewMode.TEMPLATE,
                ViewMode.PLACEMENT,
                ViewMode.PACKAGES,
                ViewMode.TODO,
            )
        if tab_id == "management_property":
            # 管理配置通用“属性”标签在管理模式与存档库模式下使用
            return view_mode in (ViewMode.MANAGEMENT, ViewMode.PACKAGES)
        if tab_id in (
            "signal_editor",
            "struct_editor",
            "main_camera_editor",
            "peripheral_system_editor",
            "equipment_entry_editor",
            "equipment_tag_editor",
            "equipment_type_editor",
        ):
            # 信号 / 结构体 / 主镜头 / 外围系统等专用编辑面板仅在管理模式下使用
            return view_mode == ViewMode.MANAGEMENT
        if tab_id in (
            "player_editor",
            "player_class_editor",
            "skill_editor",
            "item_editor",
        ):
            # 战斗预设相关详情面板在战斗预设模式下使用，
            # 同时允许在存档库模式下通过选中战斗预设条目临时拉起。
            return view_mode in (ViewMode.COMBAT, ViewMode.PACKAGES)
        # 其余标签默认不做额外模式限制
        return True

    def _apply_right_tabs_for_mode(self, view_mode: ViewMode) -> None:
        """根据集中配置统一设置右侧标签页（不包含基础"属性"面板）。"""
        if not hasattr(self, 'side_tab'):
            return
        desired = set(RIGHT_PANEL_TABS.get(view_mode, tuple()))
        tab_map = {
            "graph_property": getattr(self, 'graph_property_panel', None),
            "composite_property": getattr(self, 'composite_property_panel', None),
            "composite_pins": getattr(self, 'composite_pin_panel', None),
            "ui_settings": getattr(self, 'ui_control_settings_panel', None),
            "execution_monitor": getattr(self, 'execution_monitor_panel', None),
            "player_editor": getattr(self, 'player_editor_panel', None),
            "player_class_editor": getattr(self, 'player_class_panel', None),
            "skill_editor": getattr(self, 'skill_panel', None),
            "item_editor": getattr(self, 'item_panel', None),
            "validation_detail": getattr(self, 'validation_detail_panel', None),
        }
        # 管理模式下，“界面控件设置”标签由 `_update_ui_settings_tab_for_management` 单独控制，这里不参与集中配置管理
        if view_mode == ViewMode.MANAGEMENT:
            tab_map.pop("ui_settings", None)
        # 添加需要的标签
        for tab_id, widget in tab_map.items():
            if widget is None:
                continue
            idx = self.side_tab.indexOf(widget)
            if tab_id in desired:
                if idx == -1:
                    self.side_tab.addTab(widget, self._tab_title_for_id(tab_id))
            else:
                if idx != -1:
                    if self.side_tab.currentWidget() is widget and self.side_tab.count() > 1:
                        self.side_tab.setCurrentIndex(0)
                    self.side_tab.removeTab(idx)

        # 统一收起当前模式下不应保留的动态右侧编辑面板（管理/战斗预设/基础属性等），
        # 避免从管理页面或战斗预设切换到其它页面后仍然残留旧的编辑标签。
        dynamic_tab_map = {
            "property": getattr(self, "property_panel", None),
            "management_property": getattr(self, "management_property_panel", None),
            "signal_editor": getattr(self, "signal_management_panel", None),
            "struct_editor": getattr(self, "struct_definition_panel", None),
            "main_camera_editor": getattr(self, "main_camera_panel", None),
            "peripheral_system_editor": getattr(self, "peripheral_system_panel", None),
            "equipment_entry_editor": getattr(self, "equipment_entry_panel", None),
            "equipment_tag_editor": getattr(self, "equipment_tag_panel", None),
            "equipment_type_editor": getattr(self, "equipment_type_panel", None),
            "player_editor": getattr(self, "player_editor_panel", None),
            "player_class_editor": getattr(self, "player_class_panel", None),
            "skill_editor": getattr(self, "skill_panel", None),
            "item_editor": getattr(self, "item_panel", None),
        }
        for tab_id, widget in dynamic_tab_map.items():
            if widget is None:
                continue
            if not self._is_dynamic_tab_allowed_in_mode(tab_id, view_mode):
                idx = self.side_tab.indexOf(widget)
                if idx != -1:
                    if self.side_tab.currentWidget() is widget and self.side_tab.count() > 1:
                        self.side_tab.setCurrentIndex(0)
                    self.side_tab.removeTab(idx)

        self._update_right_panel_visibility()

    def ensure_execution_monitor_panel_visible(self, *, visible: bool, switch_to: bool = False) -> None:
        """按需在右侧标签中挂载/移除执行监控面板。

        供任务清单/执行桥等调用，避免这些模块直接操作 `side_tab` 结构或依赖私有的可见性更新方法。
        不触发视图模式切换，只负责标签的存在性与选中状态。
        """
        if not hasattr(self, "side_tab") or not hasattr(self, "execution_monitor_panel"):
            return
        panel = self.execution_monitor_panel
        index = self.side_tab.indexOf(panel)
        if visible:
            if index == -1:
                tab_title = self._tab_title_for_id("execution_monitor")
                self.side_tab.addTab(panel, tab_title)
            if switch_to:
                self.side_tab.setCurrentWidget(panel)
        else:
            if index != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(index)
        self._update_right_panel_visibility()

    def _update_right_panel_visibility(self) -> None:
        """根据右侧标签页数量动态显示/隐藏右侧面板"""
        if not hasattr(self, 'right_panel_container') or not hasattr(self, 'side_tab'):
            return

        if self.side_tab.count() == 0:
            self.right_panel_container.hide()
        else:
            self.right_panel_container.show()

    def _enforce_right_panel_contract(self, view_mode: ViewMode) -> None:
        """强制右侧标签集与当前模式允许的集合一致，清理越权残留标签。"""
        if not hasattr(self, "side_tab"):
            return

        allowed_tab_ids = set(RIGHT_PANEL_TABS.get(view_mode, tuple()))
        dynamic_candidates = (
            "property",
            "management_property",
            "signal_editor",
            "struct_editor",
            "main_camera_editor",
            "peripheral_system_editor",
            "equipment_entry_editor",
            "equipment_tag_editor",
            "equipment_type_editor",
            "player_editor",
            "player_class_editor",
            "skill_editor",
            "item_editor",
        )
        for tab_id in dynamic_candidates:
            if self._is_dynamic_tab_allowed_in_mode(tab_id, view_mode):
                allowed_tab_ids.add(tab_id)

        widget_to_tab_id: dict[QtWidgets.QWidget, str] = {}

        def _add(widget: QtWidgets.QWidget | None, tab_id: str) -> None:
            if widget is not None:
                widget_to_tab_id[widget] = tab_id

        _add(getattr(self, "graph_property_panel", None), "graph_property")
        _add(getattr(self, "composite_property_panel", None), "composite_property")
        _add(getattr(self, "composite_pin_panel", None), "composite_pins")
        _add(getattr(self, "ui_control_settings_panel", None), "ui_settings")
        _add(getattr(self, "execution_monitor_panel", None), "execution_monitor")
        _add(getattr(self, "player_editor_panel", None), "player_editor")
        _add(getattr(self, "player_class_panel", None), "player_class_editor")
        _add(getattr(self, "skill_panel", None), "skill_editor")
        _add(getattr(self, "item_panel", None), "item_editor")
        _add(getattr(self, "validation_detail_panel", None), "validation_detail")
        _add(getattr(self, "property_panel", None), "property")
        _add(getattr(self, "management_property_panel", None), "management_property")
        _add(getattr(self, "signal_management_panel", None), "signal_editor")
        _add(getattr(self, "struct_definition_panel", None), "struct_editor")
        _add(getattr(self, "main_camera_panel", None), "main_camera_editor")
        _add(getattr(self, "peripheral_system_panel", None), "peripheral_system_editor")
        _add(getattr(self, "equipment_entry_panel", None), "equipment_entry_editor")
        _add(getattr(self, "equipment_tag_panel", None), "equipment_tag_editor")
        _add(getattr(self, "equipment_type_panel", None), "equipment_type_editor")

        # 倒序移除，避免索引移动影响后续位置
        for index in range(self.side_tab.count() - 1, -1, -1):
            widget = self.side_tab.widget(index)
            tab_id = widget_to_tab_id.get(widget)
            if tab_id is None:
                continue
            if tab_id not in allowed_tab_ids:
                if self.side_tab.currentWidget() is widget and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(index)

        self._update_right_panel_visibility()

    def _switch_to_first_visible_tab(self) -> None:
        """切换到第一个可见且启用的标签"""
        if not hasattr(self, 'side_tab') or not self.side_tab:
            return

        current_widget = self.side_tab.currentWidget()
        if current_widget and current_widget.isVisible() and current_widget.isEnabled():
            return

        for i in range(self.side_tab.count()):
            widget = self.side_tab.widget(i)
            if widget and widget.isVisible() and widget.isEnabled():
                self.side_tab.setCurrentIndex(i)
                return

    def _ensure_ui_settings_tab(self) -> None:
        """确保右侧出现"界面控件设置"标签（仅管理模式），并绑定管理器。"""
        if not hasattr(self, 'side_tab'):
            return
        idx = self.side_tab.indexOf(self.ui_control_settings_panel)
        if idx == -1:
            self.side_tab.addTab(self.ui_control_settings_panel, "界面控件设置")
        if hasattr(self, 'management_widget') and hasattr(self.management_widget, 'ui_control_group_manager'):
            self.ui_control_settings_panel.bind_manager(self.management_widget.ui_control_group_manager)
        self._update_right_panel_visibility()

    def _remove_ui_settings_tab(self) -> None:
        """移除界面控件设置标签"""
        if not hasattr(self, 'side_tab'):
            return
        idx = self.side_tab.indexOf(self.ui_control_settings_panel)
        if idx != -1:
            if self.side_tab.currentWidget() is self.ui_control_settings_panel and self.side_tab.count() > 1:
                self.side_tab.setCurrentIndex(0)
            self.side_tab.removeTab(idx)
            self._update_right_panel_visibility()

    def _update_ui_settings_tab_for_management(self, section_key: str | None = None) -> None:
        """根据管理面板当前选中的 section，更新“界面控件设置”标签可见性。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            # 非管理模式下确保不显示界面控件设置
            self._remove_ui_settings_tab()
            return

        if section_key is None:
            management_widget = getattr(self, "management_widget", None)
            if management_widget is not None:
                get_key = getattr(management_widget, "get_current_section_key", None)
                if callable(get_key):
                    section_key = get_key()
                else:
                    section_key = getattr(
                        management_widget,
                        "_last_selected_section_key",
                        None,
                    )

        if section_key == "ui_control_groups":
            self._ensure_ui_settings_tab()
        else:
            self._remove_ui_settings_tab()

    def _ensure_main_camera_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“主镜头”编辑标签（管理模式下 `main_cameras` 页面专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "main_camera_panel"):
            return
        panel = self.main_camera_panel
        panel_idx = self.side_tab.indexOf(panel)
        if should_show:
            if panel_idx == -1:
                self.side_tab.addTab(panel, "主镜头")
        else:
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_peripheral_system_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“外围系统”编辑标签（管理模式下 `peripheral_systems` 页面专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "peripheral_system_panel"):
            return
        panel = self.peripheral_system_panel
        panel_idx = self.side_tab.indexOf(panel)
        if should_show:
            if panel_idx == -1:
                self.side_tab.addTab(panel, "外围系统")
        else:
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_equipment_entry_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“装备词条”编辑标签。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "equipment_entry_panel"):
            return
        panel = self.equipment_entry_panel
        idx = self.side_tab.indexOf(panel)
        if should_show:
            if idx == -1:
                self.side_tab.addTab(panel, "装备词条")
        else:
            if idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(idx)
        self._update_right_panel_visibility()

    def _ensure_equipment_tag_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“装备标签”编辑标签。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "equipment_tag_panel"):
            return
        panel = self.equipment_tag_panel
        idx = self.side_tab.indexOf(panel)
        if should_show:
            if idx == -1:
                self.side_tab.addTab(panel, "装备标签")
        else:
            if idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(idx)
        self._update_right_panel_visibility()

    def _ensure_equipment_type_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“装备类型”编辑标签。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "equipment_type_panel"):
            return
        panel = self.equipment_type_panel
        idx = self.side_tab.indexOf(panel)
        if should_show:
            if idx == -1:
                self.side_tab.addTab(panel, "装备类型")
        else:
            if idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(idx)
        self._update_right_panel_visibility()

    def _hide_all_management_edit_pages(self, except_key: str | None = None) -> None:
        """在右侧标签中移除除 except_key 外的所有管理编辑页标签。"""
        if not hasattr(self, "side_tab"):
            return
        pages = getattr(self, "management_edit_pages", None)
        if not isinstance(pages, dict):
            return
        for key, panel in pages.items():
            if key == except_key:
                continue
            panel_idx = self.side_tab.indexOf(panel)
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_struct_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“结构体”编辑标签（管理模式下 `struct_definitions` 页面专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "struct_definition_panel"):
            return
        panel = self.struct_definition_panel
        panel_idx = self.side_tab.indexOf(panel)
        if should_show:
            if panel_idx == -1:
                self.side_tab.addTab(panel, "结构体")
        else:
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_signal_editor_tab_for_management(self, section_key: str | None = None) -> None:
        """根据管理面板当前选中的 section，更新“信号”编辑标签可见性。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            if hasattr(self, "_ensure_signal_editor_tab_visible"):
                self._ensure_signal_editor_tab_visible(False)
            return

        if section_key is None:
            management_widget = getattr(self, "management_widget", None)
            if management_widget is not None:
                get_key = getattr(management_widget, "get_current_section_key", None)
                if callable(get_key):
                    section_key = get_key()
                else:
                    section_key = getattr(management_widget, "_last_selected_section_key", None)

        if section_key == "signals":
            self._ensure_signal_editor_tab_visible(True)
        else:
            self._ensure_signal_editor_tab_visible(False)

    def _ensure_struct_editor_tab_for_management(self, section_key: str | None = None) -> None:
        """根据管理面板当前选中的 section，更新“结构体”编辑标签可见性。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            if hasattr(self, "_ensure_struct_editor_tab_visible"):
                self._ensure_struct_editor_tab_visible(False)
            return

        if section_key is None:
            management_widget = getattr(self, "management_widget", None)
            if management_widget is not None:
                get_key = getattr(management_widget, "get_current_section_key", None)
                if callable(get_key):
                    section_key = get_key()
                else:
                    section_key = getattr(
                        management_widget,
                        "_last_selected_section_key",
                        None,
                    )

        if section_key in ("struct_definitions", "ingame_struct_definitions"):
            self._ensure_struct_editor_tab_visible(True)
        else:
            self._ensure_struct_editor_tab_visible(False)

    def _ensure_main_camera_editor_tab_for_management(self, section_key: str | None = None) -> None:
        """根据管理面板当前选中的 section，更新“主镜头”编辑标签可见性。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            if hasattr(self, "_ensure_main_camera_editor_tab_visible"):
                self._ensure_main_camera_editor_tab_visible(False)
            return

        if section_key is None:
            management_widget = getattr(self, "management_widget", None)
            if management_widget is not None:
                get_key = getattr(management_widget, "get_current_section_key", None)
                if callable(get_key):
                    section_key = get_key()
                else:
                    section_key = getattr(
                        management_widget,
                        "_last_selected_section_key",
                        None,
                    )

        if section_key == "main_cameras":
            self._ensure_main_camera_editor_tab_visible(True)
        else:
            self._ensure_main_camera_editor_tab_visible(False)

    def _ensure_peripheral_system_editor_tab_for_management(self, section_key: str | None = None) -> None:
        """根据管理面板当前选中的 section，更新“外围系统”编辑标签可见性。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            if hasattr(self, "_ensure_peripheral_system_editor_tab_visible"):
                self._ensure_peripheral_system_editor_tab_visible(False)
            return

        if section_key is None:
            management_widget = getattr(self, "management_widget", None)
            if management_widget is not None:
                get_key = getattr(management_widget, "get_current_section_key", None)
                if callable(get_key):
                    section_key = get_key()
                else:
                    section_key = getattr(
                        management_widget,
                        "_last_selected_section_key",
                        None,
                    )

        if section_key == "peripheral_systems":
            self._ensure_peripheral_system_editor_tab_visible(True)
        else:
            self._ensure_peripheral_system_editor_tab_visible(False)

    def _ensure_equipment_entry_editor_tab_for_management(self, section_key: str | None = None) -> None:
        """根据管理面板当前选中的 section，更新“装备词条”编辑标签可见性。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            if hasattr(self, "_ensure_equipment_entry_editor_tab_visible"):
                self._ensure_equipment_entry_editor_tab_visible(False)
            return

        if section_key is None:
            management_widget = getattr(self, "management_widget", None)
            if management_widget is not None:
                getter = getattr(management_widget, "get_current_section_key", None)
                if callable(getter):
                    section_key = getter()
                else:
                    section_key = getattr(management_widget, "_last_selected_section_key", None)

        if section_key == "equipment_entries":
            self._ensure_equipment_entry_editor_tab_visible(True)
        else:
            self._ensure_equipment_entry_editor_tab_visible(False)

    def _ensure_equipment_tag_editor_tab_for_management(self, section_key: str | None = None) -> None:
        """根据管理面板当前选中的 section，更新“装备标签”编辑标签可见性。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            if hasattr(self, "_ensure_equipment_tag_editor_tab_visible"):
                self._ensure_equipment_tag_editor_tab_visible(False)
            return

        if section_key is None:
            management_widget = getattr(self, "management_widget", None)
            if management_widget is not None:
                getter = getattr(management_widget, "get_current_section_key", None)
                if callable(getter):
                    section_key = getter()
                else:
                    section_key = getattr(management_widget, "_last_selected_section_key", None)

        if section_key == "equipment_tags":
            self._ensure_equipment_tag_editor_tab_visible(True)
        else:
            self._ensure_equipment_tag_editor_tab_visible(False)

    def _ensure_equipment_type_editor_tab_for_management(self, section_key: str | None = None) -> None:
        """根据管理面板当前选中的 section，更新“装备类型”编辑标签可见性。"""
        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_mode != ViewMode.MANAGEMENT:
            if hasattr(self, "_ensure_equipment_type_editor_tab_visible"):
                self._ensure_equipment_type_editor_tab_visible(False)
            return

        if section_key is None:
            management_widget = getattr(self, "management_widget", None)
            if management_widget is not None:
                getter = getattr(management_widget, "get_current_section_key", None)
                if callable(getter):
                    section_key = getter()
                else:
                    section_key = getattr(management_widget, "_last_selected_section_key", None)

        if section_key == "equipment_types":
            self._ensure_equipment_type_editor_tab_visible(True)
        else:
            self._ensure_equipment_type_editor_tab_visible(False)

    def _ensure_management_edit_page_for_section(self, section_key: str | None = None) -> None:
        """管理模式下为指定 section 清理旧编辑页占位，并依赖统一的列表与右侧面板体系。

        当前行为：
        - 信号、结构体与主镜头使用各自的专用右侧面板；
        - 计时器等基础管理类型使用 `ManagementPropertyPanel` 构建可编辑或只读表单；
        - 其余管理类型仅依赖中央列表与必要的对话框完成编辑，不再在右侧挂载单独管理页面。
        """
        _ = (section_key,)
        self._hide_all_management_edit_pages(None)

    def _ensure_player_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“玩家模板”标签（战斗预设专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "player_editor_panel"):
            return
        player_idx = self.side_tab.indexOf(self.player_editor_panel)
        if should_show:
            if player_idx == -1:
                self.side_tab.addTab(self.player_editor_panel, self._tab_title_for_id("player_editor"))
        else:
            if player_idx != -1:
                if self.side_tab.currentWidget() is self.player_editor_panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(player_idx)
        self._update_right_panel_visibility()

    def _ensure_player_class_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“职业”标签（战斗预设-职业详情面板专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "player_class_panel"):
            return
        panel = self.player_class_panel
        panel_idx = self.side_tab.indexOf(panel)
        if should_show:
            if panel_idx == -1:
                self.side_tab.addTab(panel, self._tab_title_for_id("player_class_editor"))
        else:
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_skill_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“技能”标签（战斗预设-技能详情面板专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "skill_panel"):
            return
        panel = self.skill_panel
        panel_idx = self.side_tab.indexOf(panel)
        if should_show:
            if panel_idx == -1:
                self.side_tab.addTab(panel, self._tab_title_for_id("skill_editor"))
        else:
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_item_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“道具”标签（战斗预设-道具详情面板专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "item_panel"):
            return
        panel = self.item_panel
        panel_idx = self.side_tab.indexOf(panel)
        if should_show:
            if panel_idx == -1:
                self.side_tab.addTab(panel, self._tab_title_for_id("item_editor"))
        else:
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_management_property_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏管理配置通用“属性”标签（管理模式专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "management_property_panel"):
            return
        panel = self.management_property_panel
        panel_idx = self.side_tab.indexOf(panel)
        if should_show:
            if panel_idx == -1:
                self.side_tab.addTab(panel, "属性")
        else:
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_signal_editor_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏“信号”编辑标签（管理模式下 `signals` 页面专用）。"""
        if not hasattr(self, "side_tab") or not hasattr(self, "signal_management_panel"):
            return
        panel = self.signal_management_panel
        panel_idx = self.side_tab.indexOf(panel)
        if should_show:
            if panel_idx == -1:
                self.side_tab.addTab(panel, "信号")
        else:
            if panel_idx != -1:
                if self.side_tab.currentWidget() is panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(panel_idx)
        self._update_right_panel_visibility()

    def _ensure_property_tab_visible(self, should_show: bool) -> None:
        """按需显示/隐藏"属性"标签（模板/实例）。"""
        if not hasattr(self, 'side_tab'):
            return
        prop_idx = self.side_tab.indexOf(self.property_panel)
        if should_show:
            if prop_idx == -1:
                self.side_tab.addTab(self.property_panel, "属性")
        else:
            if prop_idx != -1:
                if self.side_tab.currentWidget() is self.property_panel and self.side_tab.count() > 1:
                    self.side_tab.setCurrentIndex(0)
                self.side_tab.removeTab(prop_idx)
        self._update_right_panel_visibility()

    def _remove_property_in_other_modes(self) -> None:
        """在其他模式下移除属性面板"""
        self._ensure_property_tab_visible(False)

    def _sync_nav_highlight_for_mode(self, view_mode: ViewMode) -> None:
        """根据当前视图模式同步左侧导航高亮状态。"""
        if not hasattr(self, "nav_bar"):
            return
        nav_mode = view_mode.to_string()
        # 图编辑器没有独立导航按钮，使用“节点图库”作为高亮锚点，保持体验一致
        if view_mode == ViewMode.GRAPH_EDITOR:
            nav_mode = "graph_library"
        self.nav_bar.set_current_mode(nav_mode)

    def _switch_to_validation_and_validate(self) -> None:
        """切换到验证页面（F5快捷键）。

        实际的验证逻辑在进入验证模式时由 `_on_mode_changed` 统一触发，
        以便与通过导航栏切换到验证页面的行为保持一致。
        """
        self.nav_bar.set_current_mode("validation")
        self._on_mode_changed("validation")

    def _on_mode_changed(self, mode: str) -> None:
        """模式切换主方法"""
        print(f"\n[模式切换] 从当前模式切换到: {mode}")
        print(f"[模式切换] current_graph_id: {self.graph_controller.current_graph_id}")
        print(f"[模式切换] current_graph_container: {self.graph_controller.current_graph_container}")

        current_mode = ViewMode.from_index(self.central_stack.currentIndex())
        print(f"[模式切换] 当前模式: {current_mode}")

        if current_mode == ViewMode.COMPOSITE:
            composite_mgr = getattr(self, 'composite_widget', None)
            current_comp_id = getattr(composite_mgr, 'current_composite_id', None) if composite_mgr else None
            if current_comp_id:
                print(f"[模式切换] 保存复合节点: {current_comp_id}")
                composite_mgr._save_current_composite()

        if self.graph_controller.current_graph_id:
            # 仅在节点图有未保存修改时才触发保存，避免无谓的 I/O 操作
            if self.graph_controller.is_dirty:
                print(f"[模式切换] 检测到未保存修改，触发保存节点图...")
                self.graph_controller.save_current_graph()
            else:
                print(f"[模式切换] 节点图无修改，跳过保存")
        else:
            print(f"[模式切换] 跳过保存（无current_graph_id）")

        view_mode = ViewMode.from_string(mode)
        if view_mode is None:
            print(f"[模式切换] 警告：未知模式 {mode}")
            return

        # 确保左侧导航高亮与当前模式保持同步，避免程序内跳转导致高亮状态丢失
        self._sync_nav_highlight_for_mode(view_mode)

        self.central_stack.setCurrentIndex(view_mode.value)

        # 根据模式微调主分割器左右比例：
        # - 默认保持较宽的右侧属性面板，便于大多数配置/管理页面使用；
        # - 在任务清单模式下收窄右侧属性/执行面板宽度，为中间任务详情与图预览留出更多空间。
        if hasattr(self, "main_splitter"):
            if view_mode == ViewMode.TODO:
                self.main_splitter.setSizes([1600, 400])
            else:
                self.main_splitter.setSizes([1200, 800])

        def _ensure_switch_if_removed(removed_widget: QtWidgets.QWidget) -> None:
            if self.side_tab.currentWidget() is removed_widget:
                if self.side_tab.count() > 0:
                    self.side_tab.setCurrentIndex(0)

        def _sync_graph_library_selection() -> None:
            """在切换到节点图库模式后，确保右侧图属性面板与当前选中图同步。

            行为约定：
            - 若节点图库中已存在有效选中图，则直接以该图刷新右侧图属性面板；
            - 若当前无选中图但列表非空，则回退为默认选中首个节点图；
            - 若列表为空，则保持图属性面板为空状态。
            """
            if not hasattr(self, "graph_library_widget") or not hasattr(self, "graph_property_panel"):
                return
            selected_graph_id = self.graph_library_widget.get_selected_graph_id()
            if selected_graph_id:
                # 复用图库选中回调，保证行为与手动点击一致
                self._on_graph_library_selected(selected_graph_id)
                return
            self.graph_library_widget.ensure_default_selection()

        if view_mode == ViewMode.GRAPH_LIBRARY:
            graph_prop_idx = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_idx == -1:
                self.side_tab.addTab(self.graph_property_panel, "图属性")
            composite_prop_idx = self.side_tab.indexOf(self.composite_property_panel)
            if composite_prop_idx != -1:
                _ensure_switch_if_removed(self.composite_property_panel)
                self.side_tab.removeTab(composite_prop_idx)
            composite_pin_idx = self.side_tab.indexOf(self.composite_pin_panel)
            if composite_pin_idx != -1:
                _ensure_switch_if_removed(self.composite_pin_panel)
                self.side_tab.removeTab(composite_pin_idx)

            self.property_panel.clear()
            self.graph_property_panel.set_empty_state()
            self.graph_library_widget.refresh()
            QtCore.QTimer.singleShot(0, _sync_graph_library_selection)
            self.side_tab.setCurrentWidget(self.graph_property_panel)
            self._remove_property_in_other_modes()
            self._remove_ui_settings_tab()
        elif view_mode == ViewMode.COMPOSITE:
            if self.composite_widget is None:
                from ui.composite.composite_node_manager_widget import (
                    CompositeNodeManagerWidget as _CompositeNodeManagerWidget,
                )
                self.composite_widget = _CompositeNodeManagerWidget(
                    self.workspace_path, self.library, resource_manager=self.resource_manager
                )
                self.composite_widget.composite_library_updated.connect(self._on_composite_library_updated)
                self.composite_widget.composite_selected.connect(self._on_composite_selected)
                idx = ViewMode.COMPOSITE.value
                self.central_stack.removeWidget(self._composite_placeholder)
                self.central_stack.insertWidget(idx, self.composite_widget)
                self.central_stack.setCurrentIndex(ViewMode.COMPOSITE.value)
                if hasattr(self, 'composite_property_panel'):
                    self.composite_property_panel.set_composite_widget(self.composite_widget)
                if hasattr(self, 'composite_pin_panel'):
                    self.composite_pin_panel.set_composite_widget(self.composite_widget)

            graph_prop_idx = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_idx != -1:
                _ensure_switch_if_removed(self.graph_property_panel)
                self.side_tab.removeTab(graph_prop_idx)
            composite_pin_idx = self.side_tab.indexOf(self.composite_pin_panel)
            if composite_pin_idx == -1:
                self.side_tab.addTab(self.composite_pin_panel, "虚拟引脚")
            composite_prop_idx = self.side_tab.indexOf(self.composite_property_panel)
            if composite_prop_idx == -1:
                self.side_tab.addTab(self.composite_property_panel, "复合节点属性")

            self.property_panel.clear()

            current_composite = self.composite_widget.get_current_composite()
            if current_composite:
                print(f"[模式切换] 加载当前复合节点: {current_composite.node_name}")
                self.composite_property_panel.load_composite(current_composite)
                self.composite_pin_panel.load_composite(current_composite)
            else:
                print(f"[模式切换] 无当前复合节点，清空面板")
                self.composite_property_panel.clear()
                self.composite_pin_panel.clear()

            self.side_tab.setCurrentWidget(self.composite_pin_panel)
            self._remove_property_in_other_modes()
            self._remove_ui_settings_tab()
        elif view_mode == ViewMode.GRAPH_EDITOR:
            # 图编辑器：应显示图属性面板，移除复合相关面板
            graph_prop_idx = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_idx == -1:
                self.side_tab.addTab(self.graph_property_panel, "图属性")
            composite_prop_idx = self.side_tab.indexOf(self.composite_property_panel)
            if composite_prop_idx != -1:
                _ensure_switch_if_removed(self.composite_property_panel)
                self.side_tab.removeTab(composite_prop_idx)
            composite_pin_idx = self.side_tab.indexOf(self.composite_pin_panel)
            if composite_pin_idx != -1:
                _ensure_switch_if_removed(self.composite_pin_panel)
                self.side_tab.removeTab(composite_pin_idx)

            # 同步图属性面板的当前图信息
            if self.graph_controller.current_graph_id:
                self.graph_property_panel.set_graph(self.graph_controller.current_graph_id)
            else:
                self.graph_property_panel.set_empty_state()

            self.side_tab.setCurrentWidget(self.graph_property_panel)
            self._remove_property_in_other_modes()
            self._remove_ui_settings_tab()
        elif view_mode == ViewMode.VALIDATION:
            graph_prop_idx = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_idx != -1:
                _ensure_switch_if_removed(self.graph_property_panel)
                self.side_tab.removeTab(graph_prop_idx)
            composite_prop_idx = self.side_tab.indexOf(self.composite_property_panel)
            if composite_prop_idx != -1:
                _ensure_switch_if_removed(self.composite_property_panel)
                self.side_tab.removeTab(composite_prop_idx)
            composite_pin_idx = self.side_tab.indexOf(self.composite_pin_panel)
            if composite_pin_idx != -1:
                _ensure_switch_if_removed(self.composite_pin_panel)
                self.side_tab.removeTab(composite_pin_idx)

            self.property_panel.clear()
            self._remove_property_in_other_modes()
            self._remove_ui_settings_tab()
            if hasattr(self, "_trigger_validation"):
                self._trigger_validation()
        elif view_mode == ViewMode.PACKAGES:
            # 存档页面：不显示右侧任何标签
            graph_prop_idx = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_idx != -1:
                _ensure_switch_if_removed(self.graph_property_panel)
                self.side_tab.removeTab(graph_prop_idx)
            composite_prop_idx = self.side_tab.indexOf(self.composite_property_panel)
            if composite_prop_idx != -1:
                _ensure_switch_if_removed(self.composite_property_panel)
                self.side_tab.removeTab(composite_prop_idx)
            composite_pin_idx = self.side_tab.indexOf(self.composite_pin_panel)
            if composite_pin_idx != -1:
                _ensure_switch_if_removed(self.composite_pin_panel)
                self.side_tab.removeTab(composite_pin_idx)

            self.property_panel.clear()
            self._remove_property_in_other_modes()
            self._remove_ui_settings_tab()
            # 刷新包列表
            if hasattr(self, 'package_library_widget'):
                self.package_library_widget.refresh()
        elif view_mode in (ViewMode.TODO, ViewMode.MANAGEMENT):
            graph_prop_idx = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_idx != -1:
                _ensure_switch_if_removed(self.graph_property_panel)
                self.side_tab.removeTab(graph_prop_idx)
            composite_prop_idx = self.side_tab.indexOf(self.composite_property_panel)
            if composite_prop_idx != -1:
                _ensure_switch_if_removed(self.composite_property_panel)
                self.side_tab.removeTab(composite_prop_idx)
            composite_pin_idx = self.side_tab.indexOf(self.composite_pin_panel)
            if composite_pin_idx != -1:
                _ensure_switch_if_removed(self.composite_pin_panel)
                self.side_tab.removeTab(composite_pin_idx)

            self.property_panel.clear()

            if view_mode == ViewMode.MANAGEMENT:
                self._remove_property_in_other_modes()
                self._update_ui_settings_tab_for_management()
                if hasattr(self, "_ensure_signal_editor_tab_for_management"):
                    self._ensure_signal_editor_tab_for_management()
                if hasattr(self, "_ensure_struct_editor_tab_for_management"):
                    self._ensure_struct_editor_tab_for_management()
                if hasattr(self, "_ensure_main_camera_editor_tab_for_management"):
                    self._ensure_main_camera_editor_tab_for_management()
                if hasattr(self, "_ensure_peripheral_system_editor_tab_for_management"):
                    self._ensure_peripheral_system_editor_tab_for_management()
                if hasattr(self, "_ensure_equipment_entry_editor_tab_for_management"):
                    self._ensure_equipment_entry_editor_tab_for_management()
                if hasattr(self, "_ensure_equipment_tag_editor_tab_for_management"):
                    self._ensure_equipment_tag_editor_tab_for_management()
                if hasattr(self, "_ensure_equipment_type_editor_tab_for_management"):
                    self._ensure_equipment_type_editor_tab_for_management()
                # 初次进入管理模式时，根据当前列表选中项同步信号/结构体编辑面板
                get_selection = getattr(self, "_get_management_current_selection", None)
                if callable(get_selection):
                    selection = get_selection()
                    has_selection = bool(selection and selection[1])
                    if hasattr(self, "_update_signal_property_panel_for_selection"):
                        self._update_signal_property_panel_for_selection(has_selection)  # type: ignore[attr-defined]
                    if hasattr(self, "_update_struct_property_panel_for_selection"):
                        self._update_struct_property_panel_for_selection(has_selection)  # type: ignore[attr-defined]
            else:
                self._remove_property_in_other_modes()
                self._remove_ui_settings_tab()
            if view_mode == ViewMode.TODO:
                self._refresh_todo_list()
        else:
            graph_prop_idx = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_idx != -1:
                _ensure_switch_if_removed(self.graph_property_panel)
                self.side_tab.removeTab(graph_prop_idx)
            composite_prop_idx = self.side_tab.indexOf(self.composite_property_panel)
            if composite_prop_idx != -1:
                _ensure_switch_if_removed(self.composite_property_panel)
                self.side_tab.removeTab(composite_prop_idx)
            composite_pin_idx = self.side_tab.indexOf(self.composite_pin_panel)
            if composite_pin_idx != -1:
                _ensure_switch_if_removed(self.composite_pin_panel)
                self.side_tab.removeTab(composite_pin_idx)

            self.property_panel.clear()

            if view_mode in (ViewMode.TEMPLATE, ViewMode.PLACEMENT):
                # 进入元件库/实体摆放模式时显式恢复属性面板为可编辑状态
                if hasattr(self, "property_panel") and hasattr(self.property_panel, "set_read_only"):
                    self.property_panel.set_read_only(False)
                if view_mode == ViewMode.TEMPLATE:
                    self.template_widget.refresh_templates()
                elif view_mode == ViewMode.PLACEMENT:
                    self.placement_widget._rebuild_instances()
                self._ensure_property_tab_visible(self.property_panel.isEnabled())
            else:
                self._remove_property_in_other_modes()
            self._remove_ui_settings_tab()

        # 按集中配置统一应用右侧标签（含执行监控）
        self._apply_right_tabs_for_mode(view_mode)

        # 战斗预设模式：在应用静态标签后，根据当前战斗预设列表选中条目同步右侧详情面板。
        if view_mode == ViewMode.COMBAT and hasattr(self, "combat_widget"):
            # 优先恢复在非战斗模式下记录的待处理选中，避免后台立即加载面板带来的卡顿
            existing_selection = None
            get_selection_before = getattr(self.combat_widget, "get_current_selection", None)
            if callable(get_selection_before):
                existing_selection = get_selection_before()
            consume_pending = getattr(self, "_consume_pending_combat_selection", None)
            if callable(consume_pending):
                pending_selection = consume_pending()
                if pending_selection is not None:
                    section_key, item_id = pending_selection
                    if section_key and item_id:
                        if not existing_selection or not existing_selection[1]:
                            selection = LibrarySelection(
                                kind="combat",
                                id=item_id,
                                context={"section_key": section_key},
                            )
                            set_selection = getattr(self.combat_widget, "set_selection", None)
                            if callable(set_selection):
                                set_selection(selection)

            ensure_default_selection = getattr(self.combat_widget, "ensure_default_selection", None)
            if callable(ensure_default_selection):
                ensure_default_selection()
            get_selection = getattr(self.combat_widget, "get_current_selection", None)
            if callable(get_selection):
                current_selection = get_selection()
                if current_selection is not None:
                    section_key, item_id = current_selection
                    if section_key == "player_template" and hasattr(self, "_on_player_template_selected"):
                        self._on_player_template_selected(item_id)
                    elif section_key == "player_class" and hasattr(self, "_on_player_class_selected"):
                        self._on_player_class_selected(item_id)
                    elif section_key == "skill" and hasattr(self, "_on_skill_selected"):
                        self._on_skill_selected(item_id)
                    elif section_key == "item" and hasattr(self, "_on_item_selected"):
                        self._on_item_selected(item_id)

        # 防御性校验：确保右侧标签与当前模式允许集合一致，避免残留。
        self._enforce_right_panel_contract(view_mode)
        self._switch_to_first_visible_tab()
        self._update_right_panel_visibility()

        # === 调试：输出当前左右与中央实际状态 ===
        # 中央区域：当前索引与是否为编辑器视图
        central_index = self.central_stack.currentIndex()
        from app.models.view_modes import ViewMode as _VM
        central_mode = _VM.from_index(central_index)
        central_is_graph_view = (self.central_stack.currentWidget() is self.view)

        # 左侧导航：当前高亮模式
        nav_current = None
        if hasattr(self, 'nav_bar') and hasattr(self.nav_bar, 'buttons'):
            for _mode, _btn in self.nav_bar.buttons.items():
                if _btn.isChecked():
                    nav_current = _mode
                    break

        # 右侧面板：当前标签与所有标签
        if hasattr(self, 'side_tab'):
            side_count = self.side_tab.count()
            side_titles = [self.side_tab.tabText(i) for i in range(side_count)]
            current_side_title = self.side_tab.tabText(self.side_tab.currentIndex()) if side_count > 0 else "<none>"
        else:
            side_count = 0
            side_titles = []
            current_side_title = "<none>"

        print(
            f"[MODE-STATE] nav={nav_current} | central={{index:{central_index}, mode:{central_mode}, is_graph_view:{central_is_graph_view}}} | "
            f"side={{count:{side_count}, current:'{current_side_title}', tabs:{side_titles}}}"
        )

        # 根据模式刷新右上角保存状态提示（例如节点图库/复合节点下显示“当前页面不允许修改”）
        if hasattr(self, "_refresh_save_status_label_for_mode"):
            self._refresh_save_status_label_for_mode(view_mode)

        # 视图模式变化时，按需保存一次 UI 会话状态，兼容非常规退出场景。
        if hasattr(self, "_schedule_ui_session_state_save"):
            self._schedule_ui_session_state_save()

