"""常量编辑器：文本输入控件（ConstantTextEdit）。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING, cast

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.graph.graph_palette import GraphPalette
from app.ui.foundation import dialog_utils
from app.ui.foundation import input_dialogs
from app.ui.foundation import fonts as ui_fonts

from engine.graph.common import VARIABLE_NAME_PORT_NAME

from app.ui.widgets.constant_editors_helpers import (
    _extract_level_variable_id_candidate,
    _is_inline_constant_virtualization_active_for_node_item,
    _safe_strip_text,
    _try_resolve_level_variable_id_from_name,
    _try_resolve_level_variable_name_from_id,
)

if TYPE_CHECKING:
    from app.ui.graph.items.node_item import NodeGraphicsItem


class ConstantTextEdit(QtWidgets.QGraphicsTextItem):
    """可编辑的常量值文本框（默认泛型类型）"""

    def __init__(self, node_item: "NodeGraphicsItem", port_name: str, port_type: str = "泛型", parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name
        self.port_type = port_type
        self._layout_timer = None  # 兼容保留（将使用 Debouncer）
        self._layout_debouncer = None
        # “显示文本≠真实存储值”的场景（例如关卡变量的 variable_id → variable_name 显示）：
        # - _display_override_raw_value: 实际写入 node.input_constants 的原始值
        # - _display_override_text: UI 展示给用户的文本（通常为中文 variable_name）
        self._display_override_raw_value: str = ""
        self._display_override_text: str = ""
        self.setDefaultTextColor(QtGui.QColor(GraphPalette.TEXT_LABEL))  # 使用更亮的颜色，与端口标签一致
        self.setFont(ui_fonts.monospace_font(8))
        self.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)

        self._sync_display_from_node_constant()

        # 设置文本框样式和交互
        # Z-order: 必须高于端口(20)，才能接收鼠标事件
        self.setZValue(25)
        # 设置可聚焦，允许用户点击进行编辑
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        # 不要设置为可选中，避免与文本选择冲突
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def keyPressEvent(self, event: QtGui.QKeyEvent | None) -> None:
        """处理按键事件，阻止换行并根据类型限制输入"""
        if event is None:
            return
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            # 回车时失去焦点，触发保存
            self.clearFocus()
            event.accept()
            return

        # 标准编辑快捷键必须放行（尤其是 Ctrl+C），否则会被下方“数值字符白名单”误拦截。
        if any(
            event.matches(standard_key)
            for standard_key in (
                QtGui.QKeySequence.StandardKey.Copy,
                QtGui.QKeySequence.StandardKey.Paste,
                QtGui.QKeySequence.StandardKey.Cut,
                QtGui.QKeySequence.StandardKey.Undo,
                QtGui.QKeySequence.StandardKey.Redo,
                QtGui.QKeySequence.StandardKey.SelectAll,
            )
        ):
            super().keyPressEvent(event)
            return

        # 根据端口类型限制输入
        if self.port_type == "整数":
            # 只允许数字和负号
            text = event.text()
            if text and not (text.isdigit() or text == "-"):
                event.accept()
                return
        elif self.port_type == "浮点数":
            # 只允许数字、小数点和负号
            text = event.text()
            if text and not (text.isdigit() or text in ".-"):
                event.accept()
                return

        super().keyPressEvent(event)
        # 不要在输入时重新布局，会导致失去焦点，只在失去焦点时布局

    def focusOutEvent(self, event: QtGui.QFocusEvent | None) -> None:
        """失去焦点时保存"""
        if event is None:
            return
        # 清除任何残留的文本选择并恢复默认前景色，避免选区导致的永久变白
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            self.setTextCursor(cursor)
        doc_cursor = self.textCursor()
        doc_cursor.select(QtGui.QTextCursor.SelectionType.Document)
        fmt = QtGui.QTextCharFormat()
        fmt.setForeground(QtGui.QBrush(QtGui.QColor(GraphPalette.TEXT_LABEL)))
        doc_cursor.mergeCharFormat(fmt)
        doc_cursor.clearSelection()
        self.setTextCursor(doc_cursor)
        edited_text = self.toPlainText().strip()
        edited_text = edited_text.replace("\n", "").replace("\r", "")
        old_raw_value = self.node_item.node.input_constants.get(self.port_name, "")

        new_raw_value = edited_text

        # 若当前控件展示的是“映射后的显示名”，且用户未修改显示文本，则保留原始存储值，避免把中文名写回覆盖 ID。
        if self._display_override_text and (edited_text == self._display_override_text):
            new_raw_value = self._display_override_raw_value

        # 关卡变量（自定义变量）端口：尝试将用户输入归一为 stable variable_id（仅在可唯一解析时）。
        if self._is_level_variable_name_port():
            new_raw_value = self._normalize_level_variable_ref_for_storage(new_raw_value)

        # 检查值是否改变
        value_changed = False
        if new_raw_value:
            if old_raw_value != new_raw_value:
                self.node_item.node.input_constants[self.port_name] = new_raw_value
                value_changed = True
        else:
            if self.port_name in self.node_item.node.input_constants:
                del self.node_item.node.input_constants[self.port_name]
                value_changed = True

        # 无论是否写回变更，都尽量把 UI 显示同步为“用户可读”形式（例如 var_xxx → 中文 variable_name）。
        self._sync_display_from_node_constant()

        # 延迟布局操作，让焦点切换先完成，避免界面跳转
        if value_changed:
            from app.ui.foundation.debounce import Debouncer

            if self._layout_debouncer is None:
                self._layout_debouncer = Debouncer(self)
            self._layout_debouncer.debounce(50, self._delayed_layout_and_save)

        super().focusOutEvent(event)

        # 虚拟化开启：退出编辑后立即释放真实控件，回退为占位绘制（观感不变但显著降低大图开销）
        if _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            release_fn = getattr(self.node_item, "release_inline_constant_editor", None)
            if callable(release_fn):
                release_fn(self.port_name)

    def contextMenuEvent(self, event: QtWidgets.QGraphicsSceneContextMenuEvent | None) -> None:
        """为特定端口提供快捷选择入口（包内唯一性由校验保证）。"""
        if event is None:
            return

        scene = self.scene()
        is_read_only_scene = bool(scene is not None and getattr(scene, "read_only", False))
        if is_read_only_scene:
            return

        # 1) GUID：右键选择 GUID
        if self.port_type == "GUID":
            menu = QtWidgets.QMenu()
            pick_action = menu.addAction("选择 GUID...")
            clear_action = menu.addAction("清空")

            chosen = menu.exec(event.screenPos())
            if chosen is None:
                return
            if chosen == clear_action:
                self._apply_constant_text("")
                return
            if chosen == pick_action:
                self._prompt_guid_from_current_package()
                return
            return

        # 2) 自定义变量：在常见端口名“变量名”上提供快捷选择
        #
        # 注意：并非所有“变量名”都指向实体自定义变量（例如【设置/获取节点图变量】与部分【局部变量】节点
        # 的“变量名”是纯运行时标识），因此需要排除这些节点，避免误写入外部变量名。
        if self.port_type == "字符串" and self.port_name == VARIABLE_NAME_PORT_NAME:
            node_title = str(getattr(self.node_item.node, "title", "") or "").strip()
            excluded_titles = {
                "设置节点图变量",
                "获取节点图变量",
                "设置局部变量",
                "获取局部变量",
            }
            if node_title in excluded_titles:
                super().contextMenuEvent(event)
                return

            menu = QtWidgets.QMenu()
            pick_action = menu.addAction("选择自定义变量...")
            clear_action = menu.addAction("清空")

            chosen = menu.exec(event.screenPos())
            if chosen is None:
                return
            if chosen == clear_action:
                self._apply_constant_text("")
                return
            if chosen == pick_action:
                self._prompt_custom_variable_name_from_current_package()
                return
            return

        super().contextMenuEvent(event)

    def _apply_constant_text(self, text_value: str) -> None:
        """写回 node.input_constants 并触发重排/自动保存（不依赖焦点事件）。"""
        cleaned_text = str(text_value or "").strip()

        if cleaned_text:
            raw_value_to_store = (
                self._normalize_level_variable_ref_for_storage(cleaned_text)
                if self._is_level_variable_name_port()
                else cleaned_text
            )
            self.node_item.node.input_constants[self.port_name] = raw_value_to_store
        else:
            if self.port_name in self.node_item.node.input_constants:
                del self.node_item.node.input_constants[self.port_name]

        self._sync_display_from_node_constant()

        from app.ui.foundation.debounce import Debouncer

        if self._layout_debouncer is None:
            self._layout_debouncer = Debouncer(self)
        self._layout_debouncer.debounce(50, self._delayed_layout_and_save)

    def _is_level_variable_name_port(self) -> bool:
        """判定当前端口是否应按“关卡变量（自定义变量）引用”显示/归一化。"""
        if str(self.port_name or "").strip() != VARIABLE_NAME_PORT_NAME:
            return False
        node_title = str(getattr(self.node_item.node, "title", "") or "").strip()
        return bool(node_title) and ("自定义变量" in node_title)

    def _normalize_level_variable_ref_for_storage(self, raw_value: str) -> str:
        """将用户输入尽量归一为 stable variable_id（仅在可唯一解析时）。"""
        raw_text = _safe_strip_text(raw_value)
        if not raw_text:
            return ""

        candidate_id = _extract_level_variable_id_candidate(raw_text)
        if candidate_id.startswith("var_"):
            # 即使 schema 未收录，该输入也“看起来像 stable id”，优先保留。
            return candidate_id

        resolved_id = _try_resolve_level_variable_id_from_name(raw_text, node_item=self.node_item)
        return resolved_id or raw_text

    def _sync_display_from_node_constant(self) -> None:
        """根据 node.input_constants 中的真实值刷新 UI 展示文本（并维护 tooltip）。"""
        raw_value = self.node_item.node.input_constants.get(self.port_name, "")
        raw_text = _safe_strip_text(raw_value)

        # 将值为字符串 "None" 的常量视为“未填写”
        if isinstance(raw_value, str) and raw_text.lower() == "none":
            raw_text = ""

        display_text = raw_text
        tooltip_text = ""
        self._display_override_raw_value = ""
        self._display_override_text = ""

        if raw_text and self._is_level_variable_name_port():
            candidate_id = _extract_level_variable_id_candidate(raw_text)
            resolved_name = _try_resolve_level_variable_name_from_id(candidate_id, node_item=self.node_item)
            if resolved_name:
                display_text = resolved_name
                tooltip_text = candidate_id
                if display_text != raw_text:
                    # 记录“显示名→原始值”的映射，避免 focusOut 时把显示名写回覆盖 ID。
                    self._display_override_raw_value = raw_text
                    self._display_override_text = display_text

        # 图所属实体：self.owner_entity（语义化展示为“获取自身实体”，避免用户误以为是普通字符串常量）
        if raw_text == "self.owner_entity" and display_text == raw_text:
            display_text = "获取自身实体"
            tooltip_text = "self.owner_entity"
            self._display_override_raw_value = raw_text
            self._display_override_text = display_text

        self.setPlainText(display_text)
        self.setToolTip(tooltip_text)

    def _prompt_guid_from_current_package(self) -> None:
        """从项目存档的 GUID 索引中选择一个 GUID，写回到当前端口。

        约定：
        - 在普通存档视图下：直接使用当前项目存档（隐式 package_id）。
        - 在全局视图下：必须先显式选择一个项目存档（避免跨包重复 GUID 误选）。
        """
        scene = self.scene()
        scene_any = cast(Any, scene)
        edit_context = getattr(scene_any, "signal_edit_context", None)
        context_mapping = edit_context if isinstance(edit_context, dict) else {}

        get_current_package = context_mapping.get("get_current_package")
        current_package = get_current_package() if callable(get_current_package) else None
        parent_window = context_mapping.get("main_window")
        parent = parent_window if isinstance(parent_window, QtWidgets.QWidget) else None

        from engine.resources import RefResolver

        main_window_any = parent_window
        app_state = getattr(main_window_any, "app_state", None)
        package_index_manager = getattr(app_state, "package_index_manager", None)
        resource_manager = getattr(app_state, "resource_manager", None)
        if resource_manager is None and current_package is not None:
            resource_manager = getattr(current_package, "resource_manager", None)

        if package_index_manager is None or resource_manager is None:
            dialog_utils.show_error_dialog(
                parent,
                "选择 GUID",
                "无法构建 Resolver（resource_manager/package_index_manager 缺失）。",
            )
            return

        def prompt_package_id_for_scope() -> str:
            packages = package_index_manager.list_packages()
            items: list[str] = []
            for info in packages:
                if not isinstance(info, dict):
                    continue
                package_id_value = info.get("package_id")
                if not isinstance(package_id_value, str) or not package_id_value.strip():
                    continue
                package_id_text = package_id_value.strip()
                package_name = str(info.get("name", "") or "").strip() or package_id_text
                items.append(f"{package_name} | {package_id_text}")

            items.sort(key=lambda text: text.lower())
            if not items:
                dialog_utils.show_info_dialog(
                    parent,
                    "选择 GUID",
                    "当前工程未发现任何可用的项目存档（无法为 GUID 选择提供包上下文）。",
                )
                return ""

            selected_pkg = input_dialogs.prompt_item(
                parent,
                "选择 GUID 所属项目存档",
                "项目存档:",
                items,
                current_index=0,
                editable=False,
            )
            if selected_pkg is None:
                return ""
            parts = [part.strip() for part in selected_pkg.split("|")]
            return parts[1] if len(parts) >= 2 else ""

        package_id_to_use = ""
        package_index_to_use = None
        if current_package is not None:
            package_id_value = getattr(current_package, "package_id", None)
            package_index_value = getattr(current_package, "package_index", None)
            package_id_candidate = str(package_id_value or "").strip() if isinstance(package_id_value, str) else ""
            if (
                package_id_candidate
                and package_id_candidate != "global_view"
                and package_index_value is not None
            ):
                package_id_to_use = package_id_candidate
                package_index_to_use = package_index_value

        if not package_id_to_use or package_index_to_use is None:
            chosen_package_id = prompt_package_id_for_scope()
            if not chosen_package_id:
                return
            loaded_index = package_index_manager.load_package_index(chosen_package_id)
            if loaded_index is None:
                dialog_utils.show_error_dialog(parent, "选择 GUID", f"未找到项目存档索引：{chosen_package_id}")
                return
            package_id_to_use = chosen_package_id
            package_index_to_use = loaded_index

        resolver = RefResolver(
            resource_manager=resource_manager,
            package_index_manager=package_index_manager,
        )
        guid_index = resolver.build_package_guid_index_snapshot(
            package_id_to_use,
            package_index_to_use,
        )

        duplicate_guids = {collision.guid for collision in guid_index.collisions}
        guid_items: list[str] = []
        for guid, resource_ref in sorted(guid_index.guid_to_ref.items(), key=lambda kv: kv[0]):
            if guid in duplicate_guids:
                continue
            metadata = resource_manager.get_resource_metadata(
                resource_ref.resource_type, resource_ref.resource_id
            )
            display_name = ""
            if isinstance(metadata, dict):
                raw_name = metadata.get("name")
                if isinstance(raw_name, str) and raw_name.strip():
                    display_name = raw_name.strip()
            if not display_name:
                display_name = resource_ref.resource_id
            guid_items.append(
                f"{guid} | {display_name} | {resource_ref.resource_type.value}:{resource_ref.resource_id} | {package_id_to_use}"
            )

        if not guid_items:
            if duplicate_guids:
                dialog_utils.show_warning_dialog(
                    parent,
                    "选择 GUID",
                    "当前项目存档内存在重复 GUID，且没有可供选择的唯一 GUID。\n"
                    "请先运行项目存档校验并修复重复 GUID 后再选择。",
                )
            else:
                dialog_utils.show_info_dialog(
                    parent,
                    "选择 GUID",
                    "当前项目存档内没有可供选择的 GUID（模板/实体摆放的 metadata.guid 为空）。",
                )
            return

        current_text = str(self.toPlainText() or "").strip()
        default_index = 0
        for index, entry in enumerate(guid_items):
            if entry.startswith(f"{current_text} |"):
                default_index = index
                break

        selected = input_dialogs.prompt_item(
            parent,
            "选择 GUID",
            "GUID:",
            guid_items,
            current_index=default_index,
            editable=False,
        )
        if selected is None:
            return

        guid_text = selected.split("|", 1)[0].strip()
        if not guid_text:
            return
        self._apply_constant_text(guid_text)

    def _prompt_custom_variable_name_from_current_package(self) -> None:
        """从项目存档的关卡变量聚合视图中选择一个变量显示名（variable_name），写回到当前端口。

        约定：
        - 在普通存档视图下：按当前项目存档引用过滤（可用变量集合=该包引用的变量文件集合）。
        - 在全局视图下：必须先显式选择一个项目存档，再列举该包可用变量。
        """
        scene = self.scene()
        scene_any = cast(Any, scene)
        edit_context = getattr(scene_any, "signal_edit_context", None)
        context_mapping = edit_context if isinstance(edit_context, dict) else {}

        get_current_package = context_mapping.get("get_current_package")
        current_package = get_current_package() if callable(get_current_package) else None
        parent_window = context_mapping.get("main_window")
        parent = parent_window if isinstance(parent_window, QtWidgets.QWidget) else None

        main_window_any = parent_window
        app_state = getattr(main_window_any, "app_state", None)
        package_index_manager = getattr(app_state, "package_index_manager", None)
        resource_manager = getattr(app_state, "resource_manager", None)
        if resource_manager is None and current_package is not None:
            resource_manager = getattr(current_package, "resource_manager", None)

        def prompt_package_id_for_scope() -> str:
            if package_index_manager is None:
                dialog_utils.show_error_dialog(parent, "选择自定义变量", "无法获取 PackageIndexManager（app_state.package_index_manager 缺失）。")
                return ""
            packages = package_index_manager.list_packages()
            items: list[str] = []
            for info in packages:
                if not isinstance(info, dict):
                    continue
                package_id_value = info.get("package_id")
                if not isinstance(package_id_value, str) or not package_id_value.strip():
                    continue
                package_id_text = package_id_value.strip()
                package_name = str(info.get("name", "") or "").strip() or package_id_text
                items.append(f"{package_name} | {package_id_text}")
            items.sort(key=lambda text: text.lower())
            if not items:
                dialog_utils.show_info_dialog(
                    parent,
                    "选择自定义变量",
                    "当前工程未发现任何可用的项目存档（无法为变量选择提供包上下文）。",
                )
                return ""
            selected_pkg = input_dialogs.prompt_item(
                parent,
                "选择自定义变量所属项目存档",
                "项目存档:",
                items,
                current_index=0,
                editable=False,
            )
            if selected_pkg is None:
                return ""
            parts = [part.strip() for part in selected_pkg.split("|")]
            return parts[1] if len(parts) >= 2 else ""

        level_variables: dict | None = None
        if current_package is not None:
            package_id_value = getattr(current_package, "package_id", None)
            package_id_text = str(package_id_value or "").strip() if isinstance(package_id_value, str) else ""
            management = getattr(current_package, "management", None)
            candidate = getattr(management, "level_variables", None) if management is not None else None
            if isinstance(candidate, dict) and candidate and package_id_text != "global_view":
                level_variables = candidate

        selected_package_id = ""
        if level_variables is None:
            selected_package_id = prompt_package_id_for_scope()
            if not selected_package_id:
                return
            if package_index_manager is None or resource_manager is None:
                dialog_utils.show_error_dialog(
                    parent,
                    "选择自定义变量",
                    "无法加载项目存档视图（resource_manager/package_index_manager 缺失）。",
                )
                return
            package_index = package_index_manager.load_package_index(selected_package_id)
            if package_index is None:
                dialog_utils.show_error_dialog(parent, "选择自定义变量", f"未找到项目存档索引：{selected_package_id}")
                return
            from engine.resources import PackageView

            package_view = PackageView(package_index=package_index, resource_manager=resource_manager)
            management_view = getattr(package_view, "management", None)
            loaded = getattr(management_view, "level_variables", None) if management_view is not None else None
            if isinstance(loaded, dict) and loaded:
                level_variables = loaded

        if not isinstance(level_variables, dict) or not level_variables:
            dialog_utils.show_info_dialog(
                parent,
                "选择自定义变量",
                "当前项目存档未引用任何关卡变量文件，因此没有可选变量。\n"
                "请先在 管理配置 > 关卡变量 中将变量文件加入项目存档引用。",
            )
            return

        items: list[str] = []
        for variable_id, payload in level_variables.items():
            if not isinstance(payload, dict):
                continue
            variable_name = str(payload.get("variable_name") or payload.get("name") or "").strip()
            if not variable_name:
                continue
            variable_type = str(payload.get("variable_type") or "").strip()
            source_stem = str(payload.get("source_stem") or "").strip()
            source_display = source_stem or str(payload.get("source_file") or "").strip() or "<unknown>"
            items.append(f"{variable_name} | {variable_type} | {source_display}")

        items.sort(key=lambda text: text.lower())
        if not items:
            dialog_utils.show_info_dialog(parent, "选择自定义变量", "当前项目存档引用的关卡变量文件中未声明任何变量。")
            return

        current_text = str(self.toPlainText() or "").strip()
        default_index = 0
        for index, entry in enumerate(items):
            if current_text and entry.startswith(f"{current_text} |"):
                default_index = index
                break

        selected = input_dialogs.prompt_item(
            parent,
            "选择自定义变量",
            "变量:",
            items,
            current_index=default_index,
            editable=False,
        )
        if selected is None:
            return

        parts = [part.strip() for part in selected.split("|")]
        variable_name_text = parts[0] if parts else ""
        if not variable_name_text:
            return
        self._apply_constant_text(variable_name_text)

    def _delayed_layout_and_save(self):
        """延迟执行的布局和保存操作"""
        # 重新布局以确保节点宽度正确
        self.node_item._layout_ports()
        self.node_item.update()

        # 触发自动保存
        scene = self.scene()
        if scene is not None:
            scene_any = cast(Any, scene)
            on_data_changed = getattr(scene_any, "on_data_changed", None)
            if on_data_changed:
                on_data_changed()

        # 清理兼容字段
        self._layout_timer = None

