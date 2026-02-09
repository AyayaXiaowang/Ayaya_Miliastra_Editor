"""常量编辑控件模块

包含用于节点输入端口的常量值编辑控件（文本、布尔值、向量3）。
"""
from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Any, TYPE_CHECKING, Optional, Union, cast

from app.ui.graph.graph_palette import GraphPalette
from app.ui.graph import graph_component_styles as graph_styles
from app.ui.foundation import dialog_utils
from app.ui.foundation import input_dialogs
from app.ui.foundation import fonts as ui_fonts

if TYPE_CHECKING:
    from app.ui.graph.items.node_item import NodeGraphicsItem

from engine.graph.common import VARIABLE_NAME_PORT_NAME


def _safe_strip_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _extract_level_variable_id_candidate(text_value: object) -> str:
    """从常见展示/存储格式中提取“候选 variable_id”。

    兼容：
    - `name (variable_id)`
    - `name | variable_id | ...`
    - 直接为 `variable_id`
    """
    raw_text = _safe_strip_text(text_value)
    if not raw_text:
        return ""

    candidate = raw_text

    # 1) name (variable_id)
    if candidate.endswith(")") and "(" in candidate:
        inside = candidate.rsplit("(", 1)[-1].rstrip(")").strip()
        if inside:
            candidate = inside

    # 2) name | variable_id | ...
    if "|" in candidate:
        parts = [part.strip() for part in candidate.split("|")]
        if len(parts) >= 2 and parts[1]:
            candidate = parts[1]

    return candidate or raw_text


def _get_package_level_variables_from_node_item(
    node_item: "NodeGraphicsItem",
) -> dict[str, dict[str, Any]] | None:
    """从 GraphScene 的 signal_edit_context 中获取“当前包引用过滤后的关卡变量集合”。

    返回字典形态：{variable_id: payload}
    """
    scene = node_item.scene()
    scene_any = cast(Any, scene)
    edit_context = getattr(scene_any, "signal_edit_context", None)
    if not isinstance(edit_context, dict):
        return None

    get_current_package = edit_context.get("get_current_package")
    current_package = get_current_package() if callable(get_current_package) else None
    management = getattr(current_package, "management", None) if current_package is not None else None
    package_level_variables = getattr(management, "level_variables", None) if management is not None else None
    if isinstance(package_level_variables, dict) and package_level_variables:
        return package_level_variables
    return None


def _is_inline_constant_virtualization_active_for_node_item(node_item: object) -> bool:
    """判断当前 NodeGraphicsItem 是否启用了“行内常量控件虚拟化”。

    说明：
    - 优先调用 NodeGraphicsItem 自身的判定方法（避免在此处复制 fast_preview_mode 等细节）；
    - 若宿主未提供该方法，则回退到 settings 开关（不抛异常）。
    """
    fn = getattr(node_item, "_is_inline_constant_virtualization_active", None)
    if callable(fn):
        return bool(fn())
    from engine.configs.settings import settings as _settings

    return bool(getattr(_settings, "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED", True))


def _try_resolve_level_variable_name_from_id(
    variable_id: str,
    *,
    node_item: "NodeGraphicsItem",
) -> str:
    """把 variable_id 映射为可展示的 variable_name（用于 UI 显示）。"""
    variable_id_text = _safe_strip_text(variable_id)
    if not variable_id_text:
        return ""

    # 1) 优先使用“当前包过滤后的变量集合”（更贴近用户正在看的存档上下文）
    package_level_variables = _get_package_level_variables_from_node_item(node_item)
    if isinstance(package_level_variables, dict):
        payload = package_level_variables.get(variable_id_text)
        if isinstance(payload, dict):
            display_name = _safe_strip_text(payload.get("variable_name")) or _safe_strip_text(payload.get("name"))
            if display_name:
                return display_name

    # 2) 回退到全局 Schema（ID 设计上全局唯一）
    if not variable_id_text.startswith("var_"):
        return ""
    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    global_payload = get_default_level_variable_schema_view().get_all_variables().get(variable_id_text)
    if not isinstance(global_payload, dict):
        return ""
    return _safe_strip_text(global_payload.get("variable_name")) or _safe_strip_text(global_payload.get("name"))


def _try_resolve_level_variable_id_from_name(
    variable_name: str,
    *,
    node_item: "NodeGraphicsItem",
) -> str:
    """把 variable_name 映射回稳定 variable_id（仅在可唯一解析时返回）。"""
    variable_name_text = _safe_strip_text(variable_name)
    if not variable_name_text:
        return ""

    # 1) 优先在“当前包过滤后的变量集合”内做名称→ID 匹配
    package_level_variables = _get_package_level_variables_from_node_item(node_item)
    if isinstance(package_level_variables, dict):
        matched_ids: list[str] = []
        for candidate_id, payload in package_level_variables.items():
            if not isinstance(payload, dict):
                continue
            name_text = _safe_strip_text(payload.get("variable_name")) or _safe_strip_text(payload.get("name"))
            if name_text == variable_name_text:
                matched_ids.append(str(candidate_id))
                if len(matched_ids) > 1:
                    return ""  # 包内重名：不做不确定映射
        return matched_ids[0] if len(matched_ids) == 1 else ""

    # 2) 无包上下文时：仅在“全局唯一”时映射
    from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view

    all_variables = get_default_level_variable_schema_view().get_all_variables()
    if not isinstance(all_variables, dict) or not all_variables:
        return ""

    matched_global_ids: list[str] = []
    for candidate_id, payload in all_variables.items():
        if not isinstance(payload, dict):
            continue
        name_text = _safe_strip_text(payload.get("variable_name")) or _safe_strip_text(payload.get("name"))
        if name_text == variable_name_text:
            matched_global_ids.append(str(candidate_id))
            if len(matched_global_ids) > 1:
                return ""  # 全局重名：不做不确定映射
    return matched_global_ids[0] if len(matched_global_ids) == 1 else ""


def resolve_constant_display_for_port(
    node_item: "NodeGraphicsItem",
    port_name: str,
    port_type: str,
) -> tuple[str, str]:
    """将 node.input_constants 的原始值解析为“画布展示文本”。

    目的：
    - 供节点图在“未创建真实编辑控件（虚拟化）”时绘制占位文本；
    - 与 `ConstantTextEdit._sync_display_from_node_constant` 保持一致的语义化展示口径：
      - 关卡变量引用：var_xxx → 中文 variable_name（tooltip 保留 var_xxx）
      - self.owner_entity → 获取自身实体（tooltip 保留原文）
      - 字符串 "None" 视为未填写 → 空文本

    Returns:
        (display_text, tooltip_text)
    """
    port_name_text = str(port_name or "").strip()
    port_type_text = str(port_type or "").strip()

    tooltip_text = ""

    # 1) 布尔值：与 ConstantBoolComboBox 的判定口径一致
    if port_type_text == "布尔值":
        raw_value = getattr(getattr(node_item, "node", None), "input_constants", {}).get(port_name_text, False)
        is_true: bool = False
        if isinstance(raw_value, bool):
            is_true = bool(raw_value)
        elif isinstance(raw_value, (int, float)):
            is_true = bool(raw_value)
        elif isinstance(raw_value, str):
            text = raw_value.strip().lower()
            is_true = text in {"true", "是", "1", "yes", "y", "on"}
        return ("是" if is_true else "否", tooltip_text)

    # 2) 三维向量：统一为 "x, y, z" 字符串展示
    if port_type_text == "三维向量":
        raw_value = getattr(getattr(node_item, "node", None), "input_constants", {}).get(port_name_text, "0, 0, 0")
        if isinstance(raw_value, (list, tuple)) and len(raw_value) == 3:
            values = [str(v).strip() for v in raw_value]
        else:
            text_value = _safe_strip_text(raw_value)
            if (len(text_value) >= 2) and (
                (text_value[0] == "(" and text_value[-1] == ")") or (text_value[0] == "[" and text_value[-1] == "]")
            ):
                text_value = text_value[1:-1].strip()
            values = [v.strip() for v in text_value.split(",")]
        if len(values) != 3:
            values = ["0", "0", "0"]
        return (f"{values[0]}, {values[1]}, {values[2]}", tooltip_text)

    # 3) 其它类型：按文本展示 + 特殊语义化映射
    raw_value = getattr(getattr(node_item, "node", None), "input_constants", {}).get(port_name_text, "")
    raw_text = _safe_strip_text(raw_value)

    # 将值为字符串 "None" 的常量视为“未填写”
    if isinstance(raw_value, str) and raw_text.lower() == "none":
        raw_text = ""

    display_text = raw_text

    # 关卡变量（自定义变量）端口：var_xxx → 中文 variable_name
    node_title = str(getattr(getattr(node_item, "node", None), "title", "") or "").strip()
    if raw_text and (port_name_text == VARIABLE_NAME_PORT_NAME) and node_title and ("自定义变量" in node_title):
        candidate_id = _extract_level_variable_id_candidate(raw_text)
        resolved_name = _try_resolve_level_variable_name_from_id(candidate_id, node_item=node_item)
        if resolved_name:
            display_text = resolved_name
            tooltip_text = candidate_id

    # 图所属实体：self.owner_entity（语义化展示为“获取自身实体”）
    if raw_text == "self.owner_entity" and display_text == raw_text:
        display_text = "获取自身实体"
        tooltip_text = "self.owner_entity"

    return display_text, tooltip_text


class ConstantTextEdit(QtWidgets.QGraphicsTextItem):
    """可编辑的常量值文本框（默认泛型类型）"""
    def __init__(self, node_item: 'NodeGraphicsItem', port_name: str, port_type: str = "泛型", parent=None):
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
        
        # 根据端口类型限制输入
        if self.port_type == "整数":
            # 只允许数字和负号
            text = event.text()
            if text and not (text.isdigit() or text == '-'):
                event.accept()
                return
        elif self.port_type == "浮点数":
            # 只允许数字、小数点和负号
            text = event.text()
            if text and not (text.isdigit() or text in '.-'):
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
        edited_text = edited_text.replace('\n', '').replace('\r', '')
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


class ConstantBoolComboBox(QtWidgets.QGraphicsProxyWidget):
    """布尔值下拉选择框"""
    def __init__(self, node_item: 'NodeGraphicsItem', port_name: str, parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name
        
        # 创建QComboBox
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems(["否", "是"])
        self.combo.setFont(ui_fonts.ui_font(8))
        self.combo.setStyleSheet(graph_styles.graph_inline_bool_combo_box_style())
        # 节点图行内的布尔下拉需要紧凑，但不能“写死高度”：
        # - Win10/DPI 缩放、字体回退（中日韩）时 sizeHint 会变化；
        # - QSS 生效后控件的真实绘制高度也可能变化。
        # 因此用 minimumSizeHint() + 字体度量兜底取最大值，避免出现“被裁断”，同时保持紧凑。
        self.combo.ensurePolished()
        combo_font_metrics = QtGui.QFontMetrics(self.combo.font())
        font_based_height = combo_font_metrics.height() + graph_styles.GRAPH_INLINE_BOOL_COMBO_HEIGHT_EXTRA_PX
        hint_height = self.combo.minimumSizeHint().height()
        target_height = int(
            max(
                graph_styles.GRAPH_INLINE_BOOL_COMBO_MIN_HEIGHT_PX,
                font_based_height,
                hint_height,
            )
        )
        self.combo.setFixedSize(graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX, target_height)
        self.combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        # QGraphicsProxyWidget 自己也锁定尺寸，避免代理尺寸与 QWidget 尺寸不同步引起的裁剪。
        self.setMinimumSize(graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX, target_height)
        self.setMaximumSize(graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX, target_height)
        
        # 设置初始值
        current_value = node_item.node.input_constants.get(port_name, False)
        
        # 如果没有保存过值，立即保存默认值
        if port_name not in node_item.node.input_constants:
            node_item.node.input_constants[port_name] = current_value

        is_true: bool = False
        if isinstance(current_value, bool):
            is_true = bool(current_value)
        elif isinstance(current_value, (int, float)):
            is_true = bool(current_value)
        elif isinstance(current_value, str):
            text = current_value.strip().lower()
            is_true = text in {"true", "是", "1", "yes", "y", "on"}

        if is_true:
            self.combo.setCurrentIndex(1)
        else:
            self.combo.setCurrentIndex(0)
        
        # 连接信号
        self.combo.currentIndexChanged.connect(self._on_value_changed)
        
        self.setWidget(self.combo)
        self.resize(graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX, target_height)
        self.setZValue(25)
    
    def _on_value_changed(self, index):
        """值改变时保存"""
        value = bool(index == 1)
        self.node_item.node.input_constants[self.port_name] = value
        # 只更新显示，不重新布局（布尔值控件大小固定，不需要重新布局）
        self.node_item.update()
        
        # 触发自动保存
        scene = self.scene()
        if scene is not None:
            scene_any = cast(Any, scene)
            on_data_changed = getattr(scene_any, "on_data_changed", None)
            if on_data_changed:
                on_data_changed()

        # 虚拟化开启：提交后释放控件（避免大量 QGraphicsProxyWidget 常驻）
        if _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            release_fn = getattr(self.node_item, "release_inline_constant_editor", None)
            if callable(release_fn):
                QtCore.QTimer.singleShot(0, lambda: release_fn(self.port_name))

    def focusOutEvent(self, event: QtGui.QFocusEvent | None) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        if _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            release_fn = getattr(self.node_item, "release_inline_constant_editor", None)
            if callable(release_fn):
                QtCore.QTimer.singleShot(0, lambda: release_fn(self.port_name))


class ConstantVector3Edit(QtWidgets.QGraphicsProxyWidget):
    """向量3输入框（X, Y, Z三个输入框）"""
    def __init__(self, node_item: 'NodeGraphicsItem', port_name: str, parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name
        
        # 创建容器widget
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(graph_styles.GRAPH_INLINE_VECTOR3_CONTAINER_LAYOUT_SPACING_PX)
        container.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        
        # 解析当前值
        current_value = node_item.node.input_constants.get(port_name, "0, 0, 0")
        # 兼容以 Python 元组/列表字面量形式存储的三维向量，如 "(0, 0, 0)" 或 "[0, 0, 0]"
        text = current_value.strip()
        if (len(text) >= 2) and ((text[0] == '(' and text[-1] == ')') or (text[0] == '[' and text[-1] == ']')):
            current_value = text[1:-1].strip()
        
        # 如果没有保存过值，立即保存默认值
        if port_name not in node_item.node.input_constants:
            node_item.node.input_constants[port_name] = current_value
        
        values = [v.strip() for v in current_value.split(',')]
        if len(values) != 3:
            values = ["0", "0", "0"]
        
        # 创建三个输入框
        self.x_edit = self._create_axis_edit("X:", values[0])
        self.y_edit = self._create_axis_edit("Y:", values[1])
        self.z_edit = self._create_axis_edit("Z:", values[2])
        
        layout.addWidget(self.x_edit)
        layout.addWidget(self.y_edit)
        layout.addWidget(self.z_edit)
        
        # 高度缩小30%：通过 max-height 限制控件高度
        container.setFixedHeight(graph_styles.GRAPH_INLINE_VECTOR3_CONTAINER_HEIGHT_PX)
        # 固定宽度避免容器默认尺寸过大时，内部 QLabel 被拉伸把数值输入框挤到右侧（看起来像“靠近下一个轴”）。
        container.setFixedWidth(graph_styles.GRAPH_INLINE_VECTOR3_CONTAINER_WIDTH_PX)
        container.setStyleSheet(graph_styles.graph_inline_vector3_container_style())
        
        self.setWidget(container)
        self.setZValue(25)
    
    def _create_axis_edit(self, label: str, value: str):
        """创建单个轴的输入框"""
        widget = QtWidgets.QWidget()
        widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(graph_styles.GRAPH_INLINE_VECTOR3_AXIS_LAYOUT_SPACING_PX)
        
        # 标签（不可编辑）
        label_widget = QtWidgets.QLabel(label)
        label_widget.setFont(ui_fonts.monospace_font(7))
        label_widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        layout.addWidget(label_widget)
        
        # 输入框（只能输入数字和小数点）
        edit = QtWidgets.QLineEdit(value)
        edit.setFont(ui_fonts.monospace_font(8))
        edit.setFixedWidth(graph_styles.GRAPH_INLINE_VECTOR3_LINE_EDIT_WIDTH_PX)
        edit.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        # 使用正则表达式验证器，只允许数字、小数点和负号
        validator = QtGui.QRegularExpressionValidator(QtCore.QRegularExpression(r"^-?\d*\.?\d*$"))
        edit.setValidator(validator)
        edit.textChanged.connect(self._on_value_changed)
        edit.editingFinished.connect(self._on_any_axis_editing_finished)
        layout.addWidget(edit)
        
        widget.setFixedWidth(widget.sizeHint().width())
        return widget

    def _on_any_axis_editing_finished(self) -> None:
        """任意轴输入框结束编辑（失焦）时：若整个向量控件已不再聚焦则释放。"""
        if not _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            return
        QtCore.QTimer.singleShot(0, self._maybe_release_after_focus_check)

    def _maybe_release_after_focus_check(self) -> None:
        # 若焦点仍在该控件的任意轴输入框内，则不释放（支持 X→Y→Z 连续编辑）
        for axis_container in (getattr(self, "x_edit", None), getattr(self, "y_edit", None), getattr(self, "z_edit", None)):
            if not isinstance(axis_container, QtWidgets.QWidget):
                continue
            axis_line = axis_container.findChild(QtWidgets.QLineEdit)
            if isinstance(axis_line, QtWidgets.QLineEdit) and axis_line.hasFocus():
                return
        release_fn = getattr(self.node_item, "release_inline_constant_editor", None)
        if callable(release_fn):
            release_fn(self.port_name)
    
    def _on_value_changed(self):
        """任意输入框值改变时保存"""
        # 获取X、Y、Z输入框
        x_edit = self.x_edit.findChild(QtWidgets.QLineEdit)
        y_edit = self.y_edit.findChild(QtWidgets.QLineEdit)
        z_edit = self.z_edit.findChild(QtWidgets.QLineEdit)
        
        x_val = x_edit.text() or "0"
        y_val = y_edit.text() or "0"
        z_val = z_edit.text() or "0"
        
        # 保存为逗号分隔的字符串
        value = f"{x_val}, {y_val}, {z_val}"
        self.node_item.node.input_constants[self.port_name] = value
        # 只更新显示，不重新布局（向量控件大小固定，不需要重新布局）
        
        # 触发自动保存
        scene = self.scene()
        if scene is not None:
            scene_any = cast(Any, scene)
            on_data_changed = getattr(scene_any, "on_data_changed", None)
            if on_data_changed:
                on_data_changed()
        self.node_item.update()

    def focusOutEvent(self, event: QtGui.QFocusEvent | None) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        if _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            QtCore.QTimer.singleShot(0, self._maybe_release_after_focus_check)


def create_constant_editor_for_port(
    node_item: "NodeGraphicsItem",
    port_name: str,
    port_type: str,
    parent: Optional[QtWidgets.QGraphicsItem] = None,
) -> Optional[QtWidgets.QGraphicsItem]:
    """根据端口类型创建对应的常量编辑控件。

    约定：
    - 实体类型（\"实体\"）不在节点内联显示常量编辑控件，返回 None；
    - \"布尔值\" 使用下拉框；
    - \"三维向量\" 使用三轴输入控件；
    - 其他类型统一使用文本编辑框，并将 `port_type` 透传给文本框用于输入约束。
    """
    port_type_text = str(port_type or "")
    # “实体/结构体”属于引用/复合数据：只允许连线，不提供行内常量编辑（避免误把结构体当作字符串填值）。
    if port_type_text == "实体" or port_type_text.startswith("结构体"):
        return None
    if port_type_text == "布尔值":
        return ConstantBoolComboBox(node_item, port_name, parent)
    if port_type_text == "三维向量":
        return ConstantVector3Edit(node_item, port_name, parent)
    return ConstantTextEdit(node_item, port_name, port_type_text, parent)

