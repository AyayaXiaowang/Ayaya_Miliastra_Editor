"""全局搜索 / 命令面板相关的事件处理 Mixin。"""

from __future__ import annotations

from engine.configs.resource_types import ResourceType


class CommandPaletteMixin:
    """提供“命令面板/全局搜索”与“快捷键面板”的数据构建与打开入口。"""

    def _open_command_palette(self) -> None:
        """打开“全局搜索/命令面板”（Ctrl+K / Ctrl+Shift+P）。"""
        from app.ui.widgets.command_palette_dialog import CommandPaletteDialog

        dialog = CommandPaletteDialog(self)
        dialog.set_entries(self._build_command_palette_entries())
        dialog.exec()

    def _open_keymap_settings_dialog(self) -> None:
        """打开“快捷键设置”（可自定义并保存快捷键绑定）。"""
        from PyQt6 import QtWidgets
        from app.ui.widgets.keymap_settings_dialog import KeymapSettingsDialog

        keymap_store = getattr(self.app_state, "keymap_store", None)
        if keymap_store is None:
            return
        dialog = KeymapSettingsDialog(keymap_store, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            apply_method = getattr(self, "_apply_keymap_shortcuts", None)
            if callable(apply_method):
                apply_method()

    def _open_shortcut_help_panel(self) -> None:
        """打开“快捷键面板”（顶部工具栏入口）。"""
        from app.ui.widgets.shortcut_help_dialog import ShortcutHelpDialog

        dialog = ShortcutHelpDialog(self)
        dialog.set_items(self._build_shortcut_help_items())
        dialog.exec()

    def _toggle_app_perf_overlay_action(self) -> None:
        """切换“性能悬浮面板”动作（用于命令面板条目触发）。"""
        from PyQt6 import QtGui

        action = getattr(self, "app_perf_overlay_action", None)
        if isinstance(action, QtGui.QAction):
            action.trigger()

    def _locate_issues_for_resource_id(self, resource_id: str) -> None:
        """打开验证页面并尽量定位到与给定资源 ID 相关的第一条问题。"""
        target_id = str(resource_id or "").strip()
        if not target_id:
            self._switch_to_validation_and_validate()
            return

        validation_panel = getattr(self, "validation_panel", None)
        focus_method = (
            getattr(validation_panel, "request_focus_for_resource_id", None) if validation_panel is not None else None
        )
        if callable(focus_method):
            focus_method(target_id)
        self._switch_to_validation_and_validate()

    def _build_shortcut_help_items(self) -> list[object]:
        """构建快捷键面板的数据（返回 ShortcutHelpItem 列表）。"""
        from app.ui.widgets.shortcut_help_dialog import ShortcutHelpItem

        items: list[ShortcutHelpItem] = []
        keymap_store = getattr(self.app_state, "keymap_store", None)
        format_shortcuts = getattr(keymap_store, "format_shortcuts_for_display", None) if keymap_store is not None else None

        def _fmt(action_id: str, fallback: str) -> str:
            if callable(format_shortcuts):
                value = str(format_shortcuts(action_id) or "").strip()
                return value if value else fallback
            return fallback

        # -------- 全局：命令面板 / 验证 / 导航 / 全局热键
        items.extend(
            [
                ShortcutHelpItem(
                    scope="全局",
                    action="全局搜索 / 命令面板",
                    shortcut=_fmt("global.command_palette", "Ctrl+K / Ctrl+Shift+P / Ctrl+E"),
                    description="打开可搜索的命令面板，支持跳转元件/实体/预设/节点图/管理项/项目存档。",
                ),
                ShortcutHelpItem(
                    scope="全局",
                    action="快捷键设置",
                    shortcut="（命令面板/快捷键面板入口）",
                    description="自定义并保存快捷键绑定（立即生效，无需重启）。",
                ),
                ShortcutHelpItem(
                    scope="全局",
                    action="快捷键面板",
                    shortcut="（顶部工具栏）",
                    description="查看当前程序主要快捷键（本面板）。",
                ),
                ShortcutHelpItem(
                    scope="全局",
                    action="验证项目存档",
                    shortcut=_fmt("global.validate", "F5"),
                    description="切换到验证页面并触发一次校验。",
                ),
                ShortcutHelpItem(
                    scope="全局",
                    action="开发者工具（悬停显示控件信息）",
                    shortcut=_fmt("global.dev_tools_toggle", "F12"),
                    description="开启/关闭 UI 悬停检查器。",
                ),
                ShortcutHelpItem(
                    scope="全局",
                    action="性能悬浮面板（卡顿定位）",
                    shortcut=_fmt("global.app_perf_overlay_toggle", "F11"),
                    description="显示/隐藏全局性能悬浮面板（点击悬浮面板可打开详情）。",
                ),
                ShortcutHelpItem(
                    scope="全局",
                    action="后退 / 前进",
                    shortcut=f"{_fmt('global.nav_back', 'Alt+Left')} / {_fmt('global.nav_forward', 'Alt+Right')}",
                    description="回放主窗口导航历史。",
                ),
                ShortcutHelpItem(
                    scope="全局热键（系统级）",
                    action="上一个任务 / 下一个任务",
                    shortcut="Ctrl+[ / Ctrl+]",
                    description="任务清单导航（即使程序未聚焦也生效）。",
                ),
                ShortcutHelpItem(
                    scope="全局热键（系统级）",
                    action="暂停执行",
                    shortcut="Ctrl+P",
                    description="执行监控面板运行中暂停（即使程序未聚焦也生效）。",
                ),
            ]
        )

        # -------- 库页通用：元件/实体/战斗/节点图库（列表操作一致）
        items.extend(
            [
                ShortcutHelpItem(
                    scope="库页通用（元件/实体/战斗/节点图库）",
                    action="新建",
                    shortcut=_fmt("library.new", "Ctrl+N"),
                    description="新建条目（节点图库：新建节点图）。",
                ),
                ShortcutHelpItem(
                    scope="库页通用（元件/实体/战斗/节点图库）",
                    action="复制",
                    shortcut=_fmt("library.duplicate", "Ctrl+D"),
                    description="复制当前选中条目。",
                ),
                ShortcutHelpItem(
                    scope="库页通用（元件/实体/战斗/节点图库）",
                    action="重命名",
                    shortcut=_fmt("library.rename", "F2"),
                    description="重命名当前选中条目。",
                ),
                ShortcutHelpItem(
                    scope="库页通用（元件/实体/战斗/节点图库）",
                    action="删除",
                    shortcut=_fmt("library.delete", "Delete"),
                    description="删除当前选中条目（按页面语义为“移出/物理删除”）。",
                ),
                ShortcutHelpItem(
                    scope="库页通用（元件/实体/战斗/节点图库）",
                    action="移动",
                    shortcut=_fmt("library.move", "Ctrl+M"),
                    description="元件/实体/战斗预设：移动归属；节点图：移动到文件夹。",
                ),
                ShortcutHelpItem(
                    scope="库页通用（元件/实体/战斗/节点图库）",
                    action="定位问题",
                    shortcut=_fmt("library.locate_issues", "Ctrl+I"),
                    description="跳转到验证页面并尽量定位到相关问题。",
                ),
            ]
        )

        # -------- 画布：节点图编辑器
        items.append(
            ShortcutHelpItem(
                scope="节点图画布",
                action="画布内搜索",
                shortcut=_fmt("graph_view.find", "Ctrl+F"),
                description="在画布内搜索节点/连线/变量/注释等（呼出搜索浮层）。",
            )
        )

        return items

    def _build_command_palette_entries(self) -> list[object]:
        """构建命令面板条目列表。

        返回类型刻意写成 object：避免在本 Mixin 的顶部引入更多 UI 依赖；
        实际返回的是 `CommandPaletteEntry` 列表。
        """
        from app.models import UiNavigationRequest
        from app.ui.widgets.command_palette_dialog import CommandPaletteEntry
        from app.ui.graph.library_pages.management_sections import MANAGEMENT_LIBRARY_SECTIONS

        entries: list[CommandPaletteEntry] = []

        # ---------- 基础命令：模式跳转
        entries.extend(
            [
                CommandPaletteEntry(
                    title="打开：元件库",
                    subtitle="跳转到元件库页面",
                    keywords="template 元件 模板",
                    action=lambda: self._navigate_to_mode("template"),
                ),
                CommandPaletteEntry(
                    title="打开：实体摆放",
                    subtitle="跳转到实体摆放页面",
                    keywords="instance placement 实体 摆放",
                    action=lambda: self._navigate_to_mode("placement"),
                ),
                CommandPaletteEntry(
                    title="打开：战斗预设",
                    subtitle="跳转到战斗预设页面",
                    keywords="combat 战斗 预设",
                    action=lambda: self._navigate_to_mode("combat"),
                ),
                CommandPaletteEntry(
                    title="打开：节点图库",
                    subtitle="跳转到节点图库页面",
                    keywords="graph library 节点 图库",
                    action=lambda: self._navigate_to_mode("graph_library"),
                ),
                CommandPaletteEntry(
                    title="打开：管理配置",
                    subtitle="跳转到管理配置页面",
                    keywords="management 管理 配置",
                    action=lambda: self._navigate_to_mode("management"),
                ),
                CommandPaletteEntry(
                    title="打开：项目存档",
                    subtitle="跳转到项目存档（PACKAGES）页面",
                    keywords="packages 项目存档 存档",
                    action=lambda: self._navigate_to_mode("packages"),
                ),
                CommandPaletteEntry(
                    title="验证：重新验证（F5）",
                    subtitle="切换到验证页面并触发校验",
                    keywords="validate 校验 验证 F5",
                    action=self._switch_to_validation_and_validate,
                ),
                CommandPaletteEntry(
                    title="查看：快捷键面板",
                    subtitle="查看当前程序主要快捷键",
                    keywords="shortcut 快捷键 hotkey",
                    action=self._open_shortcut_help_panel,
                ),
                CommandPaletteEntry(
                    title="打开：快捷键设置",
                    subtitle="自定义并保存快捷键绑定",
                    keywords="keymap 快捷键 设置 shortcut hotkey",
                    action=self._open_keymap_settings_dialog,
                ),
                CommandPaletteEntry(
                    title="切换：性能悬浮面板（F11）",
                    subtitle="显示/隐藏全局性能悬浮面板（卡顿定位）",
                    keywords="perf performance 性能 卡顿 overlay 悬浮 F11",
                    action=self._toggle_app_perf_overlay_action,
                ),
                CommandPaletteEntry(
                    title="打开：性能监控（详情面板）",
                    subtitle="打开可复制的详细报告（卡顿事件/耗时段/堆栈）",
                    keywords="perf performance 性能 卡顿 report 报告 stack 堆栈",
                    action=self.open_performance_monitor_dialog,
                ),
            ]
        )

        # ---------- 当前上下文资源：模板/实体/战斗/节点图/管理项
        package_controller = getattr(self, "package_controller", None)
        current_package = getattr(package_controller, "current_package", None) if package_controller is not None else None
        if current_package is None:
            return entries

        # ---------- 项目存档：快速切包（全局搜索）
        package_index_manager = getattr(self.app_state, "package_index_manager", None)
        request_load = getattr(self, "_request_load_package", None)
        if package_index_manager is not None and callable(request_load):
            for package_summary in package_index_manager.list_packages():
                package_id = package_summary.get("package_id")
                if not isinstance(package_id, str) or not package_id:
                    continue
                display_name = str(package_summary.get("name") or package_id).strip() or package_id
                title = f"项目存档: {display_name}"
                subtitle = f"id={package_id}"
                entries.append(
                    CommandPaletteEntry(
                        title=title,
                        subtitle=subtitle,
                        keywords=f"{display_name} {package_id} 项目存档 package",
                        action=lambda package_id_to_load=package_id: request_load(package_id_to_load),
                    )
                )

        resource_manager = getattr(self.app_state, "resource_manager", None)

        # ===== 元件（模板）
        templates_any = getattr(current_package, "templates", None)
        if isinstance(templates_any, dict):
            for template in templates_any.values():
                template_id = getattr(template, "template_id", None)
                if not isinstance(template_id, str) or not template_id:
                    continue
                template_name = str(getattr(template, "name", "") or "").strip() or template_id
                entity_type = str(getattr(template, "entity_type", "") or "").strip()
                owner_root = (
                    package_index_manager.get_resource_owner_root_id(resource_type="template", resource_id=template_id)
                    if package_index_manager is not None
                    else ""
                )
                owner_label = "🌐 共享" if owner_root == "shared" else (owner_root or "")
                title = f"元件: {template_name}"
                if owner_root == "shared":
                    title = f"元件: 🌐 {template_name}"
                subtitle_parts = [f"id={template_id}"]
                if entity_type:
                    subtitle_parts.append(f"type={entity_type}")
                if owner_label:
                    subtitle_parts.append(f"owner={owner_label}")
                subtitle = " | ".join(subtitle_parts)

                entries.append(
                    CommandPaletteEntry(
                        title=title,
                        subtitle=subtitle,
                        keywords=f"{template_name} {template_id} {entity_type} {owner_label}",
                        action=lambda template_id_to_open=template_id: self.nav_coordinator.handle_request(
                            UiNavigationRequest.for_template(template_id_to_open, origin="command_palette")
                        ),
                    )
                )

        # ===== 实体摆放（实例）
        instances_any = getattr(current_package, "instances", None)
        if isinstance(instances_any, dict):
            for instance in instances_any.values():
                instance_id = getattr(instance, "instance_id", None)
                if not isinstance(instance_id, str) or not instance_id:
                    continue
                instance_name = str(getattr(instance, "name", "") or "").strip() or instance_id
                template_id = str(getattr(instance, "template_id", "") or "").strip()
                owner_root = (
                    package_index_manager.get_resource_owner_root_id(resource_type="instance", resource_id=instance_id)
                    if package_index_manager is not None
                    else ""
                )
                owner_label = "🌐 共享" if owner_root == "shared" else (owner_root or "")
                title = f"实体: {instance_name}"
                if owner_root == "shared":
                    title = f"实体: 🌐 {instance_name}"
                subtitle_parts = [f"id={instance_id}"]
                if template_id:
                    subtitle_parts.append(f"template={template_id}")
                if owner_label:
                    subtitle_parts.append(f"owner={owner_label}")
                subtitle = " | ".join(subtitle_parts)

                entries.append(
                    CommandPaletteEntry(
                        title=title,
                        subtitle=subtitle,
                        keywords=f"{instance_name} {instance_id} {template_id} {owner_label}",
                        action=lambda instance_id_to_open=instance_id: self.nav_coordinator.handle_request(
                            UiNavigationRequest.for_instance(instance_id_to_open, origin="command_palette")
                        ),
                    )
                )

        # ===== 战斗预设
        combat_presets = getattr(current_package, "combat_presets", None)
        section_specs: dict[str, tuple[str, str]] = {
            # section_key: (bucket_attr_name, name_field)
            "player_template": ("player_templates", "template_name"),
            "player_class": ("player_classes", "class_name"),
            "skill": ("skills", "skill_name"),
            "item": ("items", "item_name"),
            "projectile": ("projectiles", "projectile_name"),
            "unit_status": ("unit_statuses", "status_name"),
        }
        if combat_presets is not None:
            for section_key, (bucket_attr, name_field) in section_specs.items():
                bucket_any = getattr(combat_presets, bucket_attr, None)
                if not isinstance(bucket_any, dict):
                    continue
                bucket = bucket_any
                type_label_map = {
                    "player_template": "玩家模板",
                    "player_class": "职业",
                    "skill": "技能",
                    "item": "道具",
                    "projectile": "投射物",
                    "unit_status": "单位状态",
                }
                type_label = type_label_map.get(section_key, section_key)
                for item_id, payload_any in bucket.items():
                    if not isinstance(item_id, str) or not item_id:
                        continue
                    payload = payload_any if isinstance(payload_any, dict) else {}
                    raw_name = payload.get(name_field)
                    item_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
                    if not item_name:
                        item_name = str(payload.get("name") or "").strip()
                    if not item_name:
                        item_name = item_id

                    owner_root = (
                        package_index_manager.get_resource_owner_root_id(
                            resource_type=f"combat_{bucket_attr}",
                            resource_id=item_id,
                        )
                        if package_index_manager is not None
                        else ""
                    )
                    owner_label = "🌐 共享" if owner_root == "shared" else (owner_root or "")
                    title = f"战斗预设/{type_label}: {item_name}"
                    if owner_root == "shared":
                        title = f"战斗预设/{type_label}: 🌐 {item_name}"
                    subtitle = f"id={item_id}" + (f" | owner={owner_label}" if owner_label else "")

                    def _jump_combat(
                        selected_section_key: str = section_key, selected_item_id: str = item_id
                    ) -> None:
                        self._navigate_to_mode("combat")
                        combat_widget = getattr(self, "combat_widget", None)
                        focus = (
                            getattr(combat_widget, "focus_section_and_item", None)
                            if combat_widget is not None
                            else None
                        )
                        if callable(focus):
                            focus(selected_section_key, selected_item_id)

                    entries.append(
                        CommandPaletteEntry(
                            title=title,
                            subtitle=subtitle,
                            keywords=f"{item_name} {item_id} {type_label} {owner_label}",
                            action=_jump_combat,
                        )
                    )

        # ===== 节点图
        if resource_manager is not None:
            for graph_id in resource_manager.list_resources(ResourceType.GRAPH):
                if not isinstance(graph_id, str) or not graph_id:
                    continue
                graph_metadata = resource_manager.load_graph_metadata(graph_id) or {}
                graph_name = str(graph_metadata.get("name") or "").strip() or graph_id
                graph_type = str(graph_metadata.get("graph_type") or "").strip()
                folder_path = str(graph_metadata.get("folder_path") or "").strip()
                owner_root = (
                    package_index_manager.get_resource_owner_root_id(resource_type="graph", resource_id=graph_id)
                    if package_index_manager is not None
                    else ""
                )
                owner_label = "🌐 共享" if owner_root == "shared" else (owner_root or "")
                title = f"节点图: {graph_name}"
                if owner_root == "shared":
                    title = f"节点图: 🌐 {graph_name}"
                subtitle_parts = [f"id={graph_id}"]
                if graph_type:
                    subtitle_parts.append(f"type={graph_type}")
                if folder_path:
                    subtitle_parts.append(f"folder={folder_path}")
                if owner_label:
                    subtitle_parts.append(f"owner={owner_label}")
                subtitle = " | ".join(subtitle_parts)

                def _jump_graph(graph_id_to_select: str = graph_id) -> None:
                    self._navigate_to_mode("graph_library")
                    graph_library_widget = getattr(self, "graph_library_widget", None)
                    select_method = (
                        getattr(graph_library_widget, "select_graph_by_id", None)
                        if graph_library_widget is not None
                        else None
                    )
                    if callable(select_method):
                        select_method(graph_id_to_select, open_editor=False)

                entries.append(
                    CommandPaletteEntry(
                        title=title,
                        subtitle=subtitle,
                        keywords=f"{graph_name} {graph_id} {graph_type} {folder_path} {owner_label}",
                        action=_jump_graph,
                    )
                )

        # ===== 管理项
        for section in MANAGEMENT_LIBRARY_SECTIONS:
            section_key = str(getattr(section, "section_key", "") or "").strip()
            type_name = str(getattr(section, "type_name", "") or "").strip()
            if not section_key:
                continue

            entries.append(
                CommandPaletteEntry(
                    title=f"管理: {type_name or section_key}",
                    subtitle=f"section={section_key}",
                    keywords=f"management 管理 {type_name} {section_key}",
                    action=lambda section_key_to_open=section_key: self.nav_coordinator.handle_request(
                        UiNavigationRequest.for_management_section(section_key_to_open, origin="command_palette")
                    ),
                )
            )

            for row in section.iter_rows(current_package):  # type: ignore[arg-type]
                user_data = getattr(row, "user_data", None)
                if not isinstance(user_data, tuple) or len(user_data) != 2:
                    continue
                row_section_key, item_id = user_data
                if str(row_section_key or "") != section_key:
                    continue
                if not isinstance(item_id, str) or not item_id:
                    continue
                row_name = str(getattr(row, "name", "") or "").strip() or item_id

                entries.append(
                    CommandPaletteEntry(
                        title=f"管理/{type_name or section_key}: {row_name}",
                        subtitle=f"id={item_id}",
                        keywords=f"{row_name} {item_id} {type_name} {section_key}",
                        action=lambda section_key_to_open=section_key, item_id_to_open=item_id: self.nav_coordinator.handle_request(
                            UiNavigationRequest.for_management_section(
                                section_key_to_open,
                                item_id=item_id_to_open,
                                origin="command_palette",
                            )
                        ),
                    )
                )

        return entries


