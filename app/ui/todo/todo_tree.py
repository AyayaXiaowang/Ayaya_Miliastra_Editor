from __future__ import annotations

from typing import List, Dict, Optional, Tuple, Any, Callable

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from app.models import TodoItem
from engine.graph.models.graph_model import GraphModel
from engine.resources.resource_manager import ResourceType

from app.ui.todo.todo_config import TaskTypeMetadata, TodoStyles, StepTypeColors, DetailTypeIcons, StepTypeRules
from app.ui.foundation.theme_manager import Colors as ThemeColors
from app.ui.foundation.refresh_gate import RefreshGate
from app.ui.todo.tree_check_helpers import set_all_children_state, apply_parent_progress, apply_leaf_state
from app.ui.todo.todo_tree_graph_support import TodoTreeGraphSupport
from app.ui.todo.todo_tree_graph_expander import expand_graph_on_demand
from app.ui.todo.todo_event_flow_blocks import (
    build_event_flow_block_groups,
    collect_block_node_ids_for_header_item,
    create_block_header_item,
)

from .todo_runtime_state import TodoRuntimeState


class TodoTreeManager(QtCore.QObject):
    """负责：树构建、懒加载、增量刷新、三态/样式。

    与 UI 解耦：
    - 外部传入 QTreeWidget 与 runtime_state；
    - 对外暴露 `todo_checked` 信号；
    - 仅将“选中变化”回调回宿主，由宿主决定右侧面板切换。
    """

    todo_checked = QtCore.pyqtSignal(str, bool)  # todo_id, checked

    def __init__(
        self,
        tree: QtWidgets.QTreeWidget,
        runtime_state: TodoRuntimeState,
        rich_segments_role: int,
        parent=None,
        graph_expand_dependency_getter: Optional[Callable[[], Optional[Tuple[Any, ...]]]] = None,
    ) -> None:
        super().__init__(parent)
        self.tree = tree
        self.runtime_state = runtime_state
        self.RICH_SEGMENTS_ROLE = rich_segments_role

        # 运行态数据：由上层一次性注入，后续仅在本类内部增量维护。
        # 注意：todos/todo_states 引用外部传入的容器，todo_map 作为集中索引在此处维护。
        self.todos: List[TodoItem] = []
        self.todo_map: Dict[str, TodoItem] = {}
        self.todo_states: Dict[str, bool] = {}

        self._item_map: Dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._refresh_gate = RefreshGate(self.tree)
        self._structure_signature: Optional[tuple] = None
        self._graph_support = TodoTreeGraphSupport(self.tree, self.RICH_SEGMENTS_ROLE)
        # 懒加载图步骤所需的依赖解析器：由宿主注入 (package, resource_manager)，避免直接依赖 MainWindow。
        self._graph_expand_dependency_getter = graph_expand_dependency_getter
        # UI 辅助状态：当前高亮的“块分组”头节点
        self._current_block_header_item: Optional[QtWidgets.QTreeWidgetItem] = None
        # UI 辅助状态：当前因“节点选中”而高亮的 Todo ID 集合
        self._current_node_highlight_ids: set[str] = set()
        # UI 辅助状态：当前是否处于“按节点过滤步骤”的置灰模式
        self._node_filter_active: bool = False
        # 富文本委托使用的“置灰标记”角色：约定为富文本角色之后的一个自定义角色。
        self.DIMMED_ROLE: int = self.RICH_SEGMENTS_ROLE + 1
        # 图源码缓存：graph_id -> 源码行列表
        self._graph_source_lines_cache: Dict[str, List[str]] = {}
        # 步骤源码提示缓存：todo_id -> tooltip 文本
        self._source_tooltip_cache: Dict[str, str] = {}

        # 槽连接
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemExpanded.connect(self._on_tree_item_expanded)
        self.runtime_state.status_changed.connect(self._on_runtime_status_changed)

    # === 公有 API ===

    def set_data(self, todos: List[TodoItem], todo_states: Dict[str, bool]) -> None:
        """注入最新的 Todo 列表与完成状态，作为全局权威数据源。

        - todos / todo_states 直接引用调用方传入的容器，便于与外层状态保持一致；
        - todo_map 作为集中索引，保持字典实例稳定，仅在此处清空并重建内容，
          外部若持有对该 dict 的引用（例如详情面板/右键菜单），可继续复用；
        - 若当前树中仍存在 todo_id 已不在最新 todo_map 中的树项（例如此前懒加载
          生成的图内步骤），则视为结构已发生变化，强制整树重建以避免“残影”
          或重复步骤。
        """
        self.todos = todos
        self.todo_states = todo_states
        self.todo_map.clear()
        for todo in todos:
            self.todo_map[todo.todo_id] = todo

        # 检测当前树中是否存在“孤儿树项”（tree_item 有 todo_id，但 todo_map 中已不存在）
        # 典型场景：此前在旧一轮任务结构下懒加载了图步骤，后续重新生成任务清单后，
        # 这些旧步骤的 todo_id 不再出现在新的 todos 中，但对应的树节点仍然存在。
        # 为保证“树结构与 todo_map 一一对应”的约定，此时需要视为结构已变更，
        # 强制走整树重建逻辑而不是仅做样式刷新。
        has_orphan_tree_items = False
        if self._item_map:
            for mapped_todo_id in self._item_map.keys():
                if mapped_todo_id and mapped_todo_id not in self.todo_map:
                    has_orphan_tree_items = True
                    break

        new_signature = self._compute_structure_signature(todos)
        structure_changed = (new_signature != self._structure_signature) or has_orphan_tree_items
        self._structure_signature = new_signature
        if structure_changed or not self._item_map:
            self.refresh_tree()
        else:
            self.refresh_entire_tree_display()

    def get_item_map(self) -> Dict[str, QtWidgets.QTreeWidgetItem]:
        return self._item_map

    def get_item_by_id(self, todo_id: str) -> Optional[QtWidgets.QTreeWidgetItem]:
        return self._item_map.get(todo_id)

    # === 节点相关步骤查询与高亮 ===

    def get_related_todos_for_node(self, node_id: str) -> List[TodoItem]:
        """返回与给定节点 ID 相关的所有 Todo（创建/配置/连线等）。"""
        if not node_id:
            return []
        normalized = str(node_id)
        related: List[TodoItem] = []
        for todo in self.todos:
            info = todo.detail_info or {}
            detail_type = info.get("type", "")
            if not StepTypeRules.is_graph_step(detail_type):
                continue
            if self._is_todo_related_to_node(info, normalized):
                related.append(todo)
        return related

    def highlight_steps_for_node(self, node_id: str, anchor_todo_id: Optional[str] = None) -> None:
        """根据节点 ID 高亮任务树中与该节点相关的步骤。

        - anchor_todo_id: 主步骤（通常为创建步骤），若提供则使用更醒目的样式。
        """
        if not node_id:
            self.clear_node_highlight()
            return

        normalized = str(node_id)
        # 先清理旧的高亮与置灰效果
        self.clear_node_highlight()

        new_highlight_ids: set[str] = set()
        for todo in self.todos:
            info = todo.detail_info or {}
            detail_type = info.get("type", "")
            if not StepTypeRules.is_graph_step(detail_type):
                continue
            if not self._is_todo_related_to_node(info, normalized):
                continue
            todo_id = todo.todo_id
            item = self._item_map.get(todo_id)
            if item is None:
                continue
            is_anchor = bool(anchor_todo_id and todo_id == anchor_todo_id)
            self._apply_node_highlight_to_item(item, is_anchor=is_anchor)
            new_highlight_ids.add(todo_id)
        self._current_node_highlight_ids = new_highlight_ids

        # 置灰所有与当前节点无关的步骤，突出相关步骤
        if new_highlight_ids:
            self._dim_unrelated_steps(new_highlight_ids)
            self._node_filter_active = True
        else:
            self._node_filter_active = False

    def clear_node_highlight(self) -> None:
        """清除因“节点选中”产生的所有步骤高亮与置灰效果，恢复默认样式。"""
        if not self._current_node_highlight_ids and not self._node_filter_active:
            return

        # 清空内部记录的高亮 ID 集合
        self._current_node_highlight_ids.clear()
        self._node_filter_active = False

        # 清除所有树项上的置灰标记
        self._clear_dimmed_flags()

        # 通过整树样式刷新，恢复所有步骤的基础样式与富文本 tokens
        self.refresh_entire_tree_display()

    def refresh_tree(self) -> None:
        self._refresh_gate.set_refreshing(True)
        self.tree.setUpdatesEnabled(False)

        # 清理依赖于现有树项的 UI 状态，避免在整树重建后访问已删除的 QTreeWidgetItem。
        self._current_block_header_item = None
        self._current_node_highlight_ids.clear()

        self.tree.clear()
        self._item_map.clear()

        root_todos = [t for t in self.todos if t.level == 0]
        for root_todo in root_todos:
            root_item = self._create_tree_item(root_todo)
            self.tree.addTopLevelItem(root_item)
            self._build_tree_recursive(root_todo, root_item)
            detail_type = (root_todo.detail_info or {}).get("type", "")
            root_item.setExpanded(not StepTypeRules.is_event_flow_root(detail_type))

        self._refresh_gate.set_refreshing(False)
        self.tree.setUpdatesEnabled(True)

    def update_item_incrementally(self, item: QtWidgets.QTreeWidgetItem, todo: TodoItem) -> None:
        self._refresh_gate.set_refreshing(True)
        if not todo.children:
            apply_leaf_state(item, todo, self.todo_states, self._get_task_icon, self._apply_item_style)
        self._refresh_gate.set_refreshing(False)
        self._update_ancestor_states(item)

    def refresh_entire_tree_display(self) -> None:
        self._refresh_gate.set_refreshing(True)
        self.tree.setUpdatesEnabled(False)
        root = self.tree.invisibleRootItem()
        if root is not None:
            self._refresh_item_and_children(root)
        self._refresh_gate.set_refreshing(False)
        self.tree.setUpdatesEnabled(True)

    def _refresh_entire_tree_display(self) -> None:
        """兼容旧调用，统一走公开刷新入口。"""
        self.refresh_entire_tree_display()

    def ensure_tokens_for_todo(self, todo_id: str) -> list | None:
        item = self._item_map.get(todo_id)
        todo = self.todo_map.get(todo_id)
        if item is None or todo is None:
            return None

        # 仅对“支持富文本 token 的叶子图步骤”刷新 tokens，避免清空父级步骤或逻辑块
        # 自行设置的富文本（例如父级进度标签、逻辑块标题标签）。
        detail_info = todo.detail_info or {}
        detail_type = detail_info.get("type", "")
        is_leaf = not bool(todo.children)
        if is_leaf and StepTypeRules.supports_rich_tokens(detail_type):
            self._graph_support.update_item_rich_tokens(
                item=item,
                todo=todo,
                todo_map=self.todo_map,
                get_task_icon=self._get_task_icon,
            )
        tokens = item.data(0, self.RICH_SEGMENTS_ROLE)
        return tokens if isinstance(tokens, list) else None

    # === 槽 ===

    def _on_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if self._refresh_gate.is_refreshing:
            return
        if item is None or column != 0:
            return
        todo_id = item.data(0, Qt.ItemDataRole.UserRole)
        todo = self.todo_map.get(todo_id)
        if not todo:
            return

        detail_type = (todo.detail_info or {}).get("type", "")
        is_leaf_like = (not todo.children) and not StepTypeRules.is_graph_root(detail_type)
        if not is_leaf_like:
            # 父节点（模板图根/事件流根/有 children 的 todo）仅作为进度汇总节点，
            # 其三态与文本由内部逻辑驱动，这里忽略 itemChanged 以避免递归调用。
            return

        current_state = item.checkState(0)
        is_checked = current_state == Qt.CheckState.Checked
        self.todo_states[todo_id] = is_checked
        # 清理运行时状态
        self.runtime_state.clear(todo_id)
        # 发出信号
        self.todo_checked.emit(todo_id, is_checked)
        # 增量刷新（包含父级进度更新）
        self.update_item_incrementally(item, todo)

    def _on_tree_item_expanded(self, item: QtWidgets.QTreeWidgetItem) -> None:
        if item is None:
            return
        todo_id = item.data(0, Qt.ItemDataRole.UserRole)
        todo = self.todo_map.get(todo_id)
        if not todo:
            return
        detail_type = (todo.detail_info or {}).get("type", "")
        if StepTypeRules.is_template_graph_root(detail_type) and not todo.children:
            self.expand_graph_on_demand(todo)

    def _on_runtime_status_changed(self, todo_id: str) -> None:
        item = self._item_map.get(todo_id)
        todo = self.todo_map.get(todo_id)
        if item and todo:
            self.update_item_incrementally(item, todo)

    # === 内部：树构建 ===

    def _create_tree_item(self, todo: TodoItem) -> QtWidgets.QTreeWidgetItem:
        item = QtWidgets.QTreeWidgetItem()
        item.setData(0, Qt.ItemDataRole.UserRole, todo.todo_id)
        self._item_map[todo.todo_id] = item

        detail_type = (todo.detail_info or {}).get("type", "")
        is_graph_root = StepTypeRules.is_graph_root(detail_type)
        is_parent_like = bool(todo.children) or is_graph_root
        if is_parent_like:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsAutoTristate)
            if not todo.children and StepTypeRules.is_template_graph_root(detail_type):
                item.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        else:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

        if todo.children:
            apply_parent_progress(item, todo, self.todo_states, self._get_task_icon)
            self._apply_parent_style(item, todo)
        else:
            apply_leaf_state(item, todo, self.todo_states, self._get_task_icon, self._apply_item_style)
        return item
    def _build_tree_recursive(self, todo: TodoItem, parent_item: QtWidgets.QTreeWidgetItem) -> None:
        """根据 Todo 结构递归构建树节点。

        对事件流根（event_flow_root）增加按 BasicBlock 分组的显示：
        - 按当前顺序扫描其直接子步骤；
        - 基于节点所在 BasicBlock 构造“块分组”头节点；
        - 将同一块内的步骤挂在对应分组下，其它步骤保持原有扁平结构。
        """
        detail_type = (todo.detail_info or {}).get("type", "")
        if StepTypeRules.is_event_flow_root(detail_type):
            self._build_event_flow_tree_with_blocks(todo, parent_item)
            return

        for child_id in todo.children:
            child_todo = self.todo_map.get(child_id)
            if child_todo:
                self._build_single_todo_subtree(parent_item, child_todo)

    def _build_single_todo_subtree(
        self,
        parent_item: QtWidgets.QTreeWidgetItem,
        child_todo: TodoItem,
    ) -> None:
        """为给定 Todo 构建一个树节点及其子树。"""
        child_item = self._create_tree_item(child_todo)
        parent_item.addChild(child_item)
        # 为叶子“配置参数/设置类型”步骤附加只读子项（展示端口/参数明细）
        self._graph_support.rebuild_virtual_detail_children(child_item, child_todo, self.todo_map)
        if child_todo.children:
            self._build_tree_recursive(child_todo, child_item)
            child_detail_type = (child_todo.detail_info or {}).get("type", "")
            child_item.setExpanded(not StepTypeRules.is_event_flow_root(child_detail_type))

    def _build_event_flow_tree_with_blocks(
        self,
        flow_root_todo: TodoItem,
        flow_root_item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """为事件流根构建树结构，并按 BasicBlock 分组显示子步骤。

        分组规则由 `todo_event_flow_blocks` 模块统一实现：
        - 先按原顺序为每个子步骤解析其所在 BasicBlock（可能为 None）；
        - 将相邻且 block_index 相同的步骤聚合为一个逻辑分组；
        - 若所有子步骤均无法解析出 block_index（全为 None），则完全退回扁平结构；
        - 否则：
          - block_index 为 None 的分组保持直接挂在事件流根下；
          - 有效 block_index 的分组创建块头节点，并将组内步骤挂在块头下面；
          - 同一 block_index 如果被非连续步骤打断，会拆成多个逻辑分组，分别生成块头。
        """
        groups = build_event_flow_block_groups(
            flow_root_todo,
            flow_root_item,
            self.todo_map,
            graph_support=self._graph_support,
        )
        if not groups:
            # 若无法识别任何块信息，则退回到原有的扁平结构构建逻辑
            for child_id in flow_root_todo.children:
                child_todo = self.todo_map.get(child_id)
                if child_todo:
                    self._build_single_todo_subtree(flow_root_item, child_todo)
            return

        # 尝试从图模型中获取 BasicBlock 列表，以便逻辑块分组头使用与画布一致的块颜色。
        basic_blocks: List[Any] = []
        model, _graph_id = self._graph_support.get_graph_model_for_item(
            item=flow_root_item,
            todo_id=flow_root_todo.todo_id,
            todo_map=self.todo_map,
        )
        if model is not None:
            basic_blocks_raw = getattr(model, "basic_blocks", None)
            if isinstance(basic_blocks_raw, list):
                basic_blocks = list(basic_blocks_raw)

        for group_index, group in enumerate(groups):
            if group.block_index is None:
                # 未归属任何块的步骤仍然直接挂在事件流根下，保持其在整个序列中的相对位置。
                self._add_ungrouped_flow_children(flow_root_item, group.child_ids)
                continue

            block_color_hex = ""
            if (
                isinstance(group.block_index, int)
                and 0 <= group.block_index < len(basic_blocks)
            ):
                basic_block = basic_blocks[group.block_index]
                color_value = getattr(basic_block, "color", "")
                if isinstance(color_value, str) and color_value:
                    block_color_hex = color_value

            header_item = create_block_header_item(
                group.block_index,
                group_index,
                block_color_hex,
            )
            flow_root_item.addChild(header_item)
            # 逻辑块分组默认展开，方便用户一眼看到块内所有步骤
            header_item.setExpanded(True)
            for child_id in group.child_ids:
                child_todo = self.todo_map.get(child_id)
                if not child_todo:
                    continue
                self._build_single_todo_subtree(header_item, child_todo)

    def _add_ungrouped_flow_children(
        self,
        flow_root_item: QtWidgets.QTreeWidgetItem,
        child_ids: List[str],
    ) -> None:
        """将未归属 BasicBlock 的步骤直接挂载到事件流根下。"""
        for child_id in child_ids:
            child_todo = self.todo_map.get(child_id)
            if not child_todo:
                continue
            self._build_single_todo_subtree(flow_root_item, child_todo)

    def _refresh_item_and_children(self, parent_item: QtWidgets.QTreeWidgetItem) -> None:
        for child_index in range(parent_item.childCount()):
            item = parent_item.child(child_index)
            if item is None:
                continue
            todo_id = item.data(0, Qt.ItemDataRole.UserRole)
            todo = self.todo_map.get(todo_id)
            if not todo:
                # 可能是块头分组或虚拟子项，继续向下递归刷新其子节点
                self._refresh_item_and_children(item)
                continue
            if todo.children:
                apply_parent_progress(item, todo, self.todo_states, self._get_task_icon)
                self._apply_parent_style(item, todo)
                self._refresh_item_and_children(item)
            else:
                apply_leaf_state(item, todo, self.todo_states, self._get_task_icon, self._apply_item_style)
            # 结构未变但 detail_info 发生变化时，重建只读子项文本
            self._graph_support.rebuild_virtual_detail_children(item, todo, self.todo_map)

    def _update_ancestor_states(self, item: QtWidgets.QTreeWidgetItem) -> None:
        current_item = item.parent()
        while current_item:
            todo_id = current_item.data(0, Qt.ItemDataRole.UserRole)
            todo = self.todo_map.get(todo_id)
            if todo and todo.children:
                apply_parent_progress(
                    current_item, todo, self.todo_states, self._get_task_icon
                )
                # 重新应用父级样式与富文本 tokens，使进度与颜色保持同步
                self._apply_parent_style(current_item, todo)
            current_item = current_item.parent()
    
    def _compute_structure_signature(self, todos: List[TodoItem]) -> tuple:
        signature = []
        for todo in todos:
            children = tuple(todo.children or [])
            detail_type = str((todo.detail_info or {}).get("type", ""))
            signature.append((todo.todo_id, children, detail_type))
        signature.sort(key=lambda item: item[0])
        return tuple(signature)

    # === 内部：样式与富文本 ===

    @staticmethod
    def _tint_background_color(hex_color: str) -> str:
        """将前景色与白色混合，生成浅色背景，用于父级步骤/逻辑块的淡底色。"""
        if not isinstance(hex_color, str):
            return ""
        if not (len(hex_color) == 7 and hex_color.startswith("#")):
            return ""
        red_value = int(hex_color[1:3], 16)
        green_value = int(hex_color[3:5], 16)
        blue_value = int(hex_color[5:7], 16)
        mix_ratio = 0.82
        mixed_red = int(red_value + (255 - red_value) * mix_ratio)
        mixed_green = int(green_value + (255 - green_value) * mix_ratio)
        mixed_blue = int(blue_value + (255 - blue_value) * mix_ratio)
        if mixed_red > 255:
            mixed_red = 255
        if mixed_green > 255:
            mixed_green = 255
        if mixed_blue > 255:
            mixed_blue = 255
        return f"#{mixed_red:02X}{mixed_green:02X}{mixed_blue:02X}"

    def _apply_parent_style(self, item: QtWidgets.QTreeWidgetItem, todo: TodoItem) -> None:
        """父级/容器节点样式：颜色 + 进度文本 + 富文本 tokens。"""
        detail_type = (todo.detail_info or {}).get("type", "")
        if StepTypeRules.is_graph_root(detail_type):
            # 图根 / 事件流根：使用步骤类型专用颜色，便于与子步骤区分
            base_color = StepTypeColors.get_step_color(str(detail_type))
        else:
            # 其它父级步骤：按任务类型使用分类色（模板/实例/战斗/管理等）
            base_color = TaskTypeMetadata.get_color(todo.task_type)

        item.setForeground(0, QtGui.QBrush(QtGui.QColor(base_color)))

        # 父级节点同样走富文本委托，用“标题色 + 浅底 + 进度”增强可读性。
        completed, total = todo.get_progress(self.todo_states)
        icon_character = self._get_task_icon(todo)
        tokens: List[Dict[str, Any]] = []
        neutral_color = ThemeColors.TEXT_SECONDARY

        if isinstance(icon_character, str) and icon_character:
            tokens.append({"text": f"{icon_character} ", "color": neutral_color})

        background_color = self._tint_background_color(base_color)
        tokens.append(
            {
                "text": todo.title,
                "color": base_color,
                "bg": background_color,
                "bold": True,
            }
        )

        if total > 0:
            tokens.append(
                {
                    "text": f" ({completed}/{total})",
                    "color": neutral_color,
                }
            )

        item.setData(0, self.RICH_SEGMENTS_ROLE, tokens)

    def _apply_item_style(self, item: QtWidgets.QTreeWidgetItem, todo: TodoItem, is_completed: bool = False) -> None:
        color = TaskTypeMetadata.get_color(todo.task_type)
        detail_type = todo.detail_info.get("type", "") if todo.detail_info else ""

        if not todo.children:
            if StepTypeRules.is_graph_step(detail_type):
                color = StepTypeColors.get_step_color(str(detail_type))
                node_color = self._graph_support.get_node_category_color(item, todo, self.todo_map)
                if node_color:
                    color = node_color

        font = item.font(0)
        if todo.task_type == "category":
            font.setBold(True)
        elif todo.task_type in ["template", "instance"] and todo.level == 2:
            font.setBold(True)

        if is_completed and not todo.children:
            font.setStrikeOut(True)
            color = ThemeColors.COMPLETED
        else:
            font.setStrikeOut(False)

        item.setFont(0, font)

        status = self.runtime_state.get_status(todo.todo_id) if not todo.children else ""
        if status == "skipped":
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(ThemeColors.WARNING)))
            item.setText(0, f"⚠ {self._get_task_icon(todo)} {todo.title}")
            item.setToolTip(0, self.runtime_state.get_tooltip(todo.todo_id) or "该步骤因端点距离过远被跳过")
            item.setData(0, self.RICH_SEGMENTS_ROLE, None)
        elif status == "failed":
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(ThemeColors.ERROR)))
            item.setText(0, f"✗ {self._get_task_icon(todo)} {todo.title}")
            item.setToolTip(0, self.runtime_state.get_tooltip(todo.todo_id) or "该步骤执行失败")
            item.setData(0, self.RICH_SEGMENTS_ROLE, None)
        else:
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
            # 图相关步骤：为任务树项附加“源码定位”提示，悬停即可查看对应节点图文件与大致行号。
            if StepTypeRules.is_graph_step(detail_type):
                tooltip_text = self._get_source_tooltip_for_todo(todo)
                item.setToolTip(0, tooltip_text)
            else:
                item.setToolTip(0, "")
            self._graph_support.update_item_rich_tokens(
                item=item,
                todo=todo,
                todo_map=self.todo_map,
                get_task_icon=self._get_task_icon,
            )

    def _get_task_icon(self, todo: TodoItem) -> str:
        return DetailTypeIcons.get_icon(todo.task_type, todo.detail_info)

    # === 内部：源码定位提示 ===

    def _get_source_tooltip_for_todo(self, todo: TodoItem) -> str:
        """为图相关步骤构建源码定位提示（悬停时显示）。

        规则：
        - 依赖 detail_info.graph_id 解析节点图；
        - 根据 detail_info 中的节点 ID 字段抽取关联节点；
        - 对每个节点优先使用 source_lineno/source_end_lineno 限定搜索范围，
          在对应图源码片段内按节点 title 做一次字符串搜索，若命中则以该行作为主行号；
        - 若无法解析图或节点行号，则退回空字符串，不影响正常 tooltip。
        """
        cached = self._source_tooltip_cache.get(todo.todo_id)
        if isinstance(cached, str):
            return cached

        detail_info = todo.detail_info or {}
        graph_id_raw = detail_info.get("graph_id", "")
        graph_id = str(graph_id_raw or "")
        if not graph_id:
            self._source_tooltip_cache[todo.todo_id] = ""
            return ""

        if self._graph_expand_dependency_getter is None:
            self._source_tooltip_cache[todo.todo_id] = ""
            return ""

        dependencies = self._graph_expand_dependency_getter()
        if not isinstance(dependencies, tuple) or len(dependencies) != 2:
            self._source_tooltip_cache[todo.todo_id] = ""
            return ""

        _package, resource_manager = dependencies
        if resource_manager is None:
            self._source_tooltip_cache[todo.todo_id] = ""
            return ""

        graph_payload = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not graph_payload:
            self._source_tooltip_cache[todo.todo_id] = ""
            return ""

        graph_data = graph_payload.get("data", graph_payload)
        model = GraphModel.deserialize(graph_data)

        graph_file_path = resource_manager.get_graph_file_path(graph_id)
        file_display = ""
        if graph_file_path is not None:
            file_display = str(graph_file_path)

        related_node_ids = self._collect_related_node_ids(detail_info)
        if not related_node_ids:
            if not file_display:
                self._source_tooltip_cache[todo.todo_id] = ""
                return ""
            lines: List[str] = []
            if graph_id in self._graph_source_lines_cache:
                lines = self._graph_source_lines_cache[graph_id]
            else:
                if graph_file_path is not None and graph_file_path.exists():
                    text = graph_file_path.read_text(encoding="utf-8")
                    lines = text.splitlines()
                    self._graph_source_lines_cache[graph_id] = lines
            header_lines = [f"节点图文件：{file_display}"]
            if lines:
                header_lines.append("（该步骤未直接关联具体节点，可在文件中按节点名搜索）")
            tooltip_value = "\n".join(header_lines)
            self._source_tooltip_cache[todo.todo_id] = tooltip_value
            return tooltip_value

        lines_for_graph: List[str] = []
        if graph_id in self._graph_source_lines_cache:
            lines_for_graph = self._graph_source_lines_cache[graph_id]
        else:
            if graph_file_path is not None and graph_file_path.exists():
                text = graph_file_path.read_text(encoding="utf-8")
                lines_for_graph = text.splitlines()
                self._graph_source_lines_cache[graph_id] = lines_for_graph

        tooltip_lines: List[str] = []
        if file_display:
            tooltip_lines.append(f"节点图文件：{file_display}")
        tooltip_lines.append("关联节点：")

        for node_identifier in related_node_ids:
            node_object = model.nodes.get(str(node_identifier))
            if node_object is None:
                tooltip_lines.append(f"- 节点 id={node_identifier}（未在当前图中找到）")
                continue

            title_text = str(getattr(node_object, "title", "") or "")
            category_text = str(getattr(node_object, "category", "") or "")
            source_start = int(getattr(node_object, "source_lineno", 0) or 0)
            source_end = int(getattr(node_object, "source_end_lineno", 0) or 0)

            header_parts: List[str] = []
            if title_text:
                header_parts.append(title_text)
            if category_text:
                header_parts.append(f"（{category_text}）")
            header_parts.append(f" id={node_object.id}")
            header_text = "".join(header_parts)

            best_line = source_start if source_start > 0 else 0
            if lines_for_graph:
                search_start = source_start if source_start > 0 else 1
                if search_start < 1:
                    search_start = 1
                search_end = source_end if source_end >= search_start else search_start
                if search_end > len(lines_for_graph):
                    search_end = len(lines_for_graph)
                if search_end < search_start:
                    search_end = search_start
                found_line = 0
                if title_text:
                    for line_number in range(search_start, search_end + 1):
                        line_text = lines_for_graph[line_number - 1]
                        if title_text in line_text:
                            found_line = line_number
                            break
                if found_line > 0:
                    best_line = found_line

            if best_line > 0:
                line_desc = f"第 {best_line} 行"
            else:
                line_desc = "行号未知（节点未携带可用的源代码行信息）"

            tooltip_lines.append(f"- {header_text}")
            tooltip_lines.append(f"  源码行号：{line_desc}")

        tooltip_text = "\n".join(tooltip_lines)
        self._source_tooltip_cache[todo.todo_id] = tooltip_text
        return tooltip_text

    @staticmethod
    def _collect_related_node_ids(detail_info: Dict[str, Any]) -> List[str]:
        """从 detail_info 中提取与当前步骤直接相关的节点 ID 列表。"""
        candidate_keys = [
            "node_id",
            "src_node",
            "dst_node",
            "target_node_id",
            "data_node_id",
            "prev_node_id",
            "node1_id",
            "node2_id",
            "branch_node_id",
        ]
        result: List[str] = []
        for key in candidate_keys:
            if key not in detail_info:
                continue
            raw_value = detail_info.get(key)
            if raw_value is None:
                continue
            value_text = str(raw_value)
            if not value_text:
                continue
            if value_text in result:
                continue
            result.append(value_text)
        return result

    # === 内部：块分组高亮 ===

    def highlight_block_for_item(self, tree_item: QtWidgets.QTreeWidgetItem) -> None:
        """根据当前选中的树节点，高亮其所属的块分组头。"""
        if tree_item is None:
            # 清空高亮
            if self._current_block_header_item is not None:
                self._set_block_header_highlight(self._current_block_header_item, False)
                self._current_block_header_item = None
            return

        block_header_item = self._find_block_header_for_item(tree_item)
        if block_header_item is self._current_block_header_item:
            return

        if self._current_block_header_item is not None:
            self._set_block_header_highlight(self._current_block_header_item, False)

        self._current_block_header_item = block_header_item
        if block_header_item is not None:
            self._set_block_header_highlight(block_header_item, True)

    def _find_block_header_for_item(
        self,
        start_item: Optional[QtWidgets.QTreeWidgetItem],
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """沿父链向上查找最近的块分组头节点。"""
        current_item = start_item
        while current_item is not None:
            marker = current_item.data(0, Qt.ItemDataRole.UserRole + 2)
            if marker == "block_header":
                return current_item
            current_item = current_item.parent()
        return None

    def _set_block_header_highlight(
        self,
        header_item: QtWidgets.QTreeWidgetItem,
        highlighted: bool,
    ) -> None:
        """切换块分组头的高亮样式。"""
        if header_item is None:
            return
        header_font = header_item.font(0)
        header_font.setBold(True)
        header_item.setFont(0, header_font)
        stored_color = header_item.data(0, Qt.ItemDataRole.UserRole + 3)
        if isinstance(stored_color, str) and stored_color:
            color_hex = stored_color
        else:
            color_hex = ThemeColors.TEXT_SECONDARY
        # 选中时使用统一选中背景，但前景色仍保持块颜色，保证与画布中的逻辑块颜色一致
        if highlighted:
            header_item.setBackground(
                0, QtGui.QBrush(QtGui.QColor(ThemeColors.BG_SELECTED))
            )
        else:
            header_item.setBackground(0, QtGui.QBrush())
        header_item.setForeground(0, QtGui.QBrush(QtGui.QColor(color_hex)))

    def _apply_node_highlight_to_item(
        self,
        item: QtWidgets.QTreeWidgetItem,
        *,
        is_anchor: bool,
    ) -> None:
        """为与当前节点相关的步骤应用高亮样式（背景 + 文本前缀）。"""
        if item is None:
            return

        # 1) 行背景高亮
        background_color = ThemeColors.PRIMARY_LIGHT if is_anchor else ThemeColors.BG_SELECTED
        item.setBackground(0, QtGui.QBrush(QtGui.QColor(background_color)))

        # 2) 文本加粗（锚点步骤更醒目）
        font = item.font(0)
        if is_anchor:
            font.setBold(True)
        item.setFont(0, font)

        # 3) 若存在富文本 tokens，则在最前面插入一个前缀标记，避免改动原文案
        tokens = item.data(0, self.RICH_SEGMENTS_ROLE)
        if isinstance(tokens, list):
            new_tokens = []
            if is_anchor:
                new_tokens.append(
                    {
                        "text": "★ ",
                        "color": ThemeColors.PRIMARY,
                        "bold": True,
                    }
                )
            else:
                new_tokens.append(
                    {
                        "text": "• ",
                        "color": ThemeColors.TEXT_SECONDARY,
                    }
                )
            new_tokens.extend(tokens)
            item.setData(0, self.RICH_SEGMENTS_ROLE, new_tokens)

    def _dim_unrelated_steps(self, related_ids: set[str]) -> None:
        """将当前树中除 related_ids 以外的步骤统一置灰，强化节点相关步骤的对比度。"""
        root = self.tree.invisibleRootItem()
        dim_color_hex = ThemeColors.TEXT_DISABLED

        if root is None:
            return

        stack: List[QtWidgets.QTreeWidgetItem] = [root]
        while stack:
            parent_item = stack.pop()
            for index in range(parent_item.childCount()):
                item = parent_item.child(index)
                if item is None:
                    continue
                stack.append(item)

                todo_id = item.data(0, Qt.ItemDataRole.UserRole)
                if not todo_id or todo_id in related_ids:
                    continue
                if todo_id not in self.todo_map:
                    continue

                # 统一使用禁用文本色作为前景色（非富文本项直接生效，富文本项作为兜底）
                item.setForeground(
                    0,
                    QtGui.QBrush(QtGui.QColor(dim_color_hex)),
                )

                # 为富文本委托设置“置灰标记”，在绘制时统一将 token 颜色替换为禁用文本色。
                item.setData(0, self.DIMMED_ROLE, True)

    def _clear_dimmed_flags(self) -> None:
        """清除整棵树上的置灰标记。"""
        root = self.tree.invisibleRootItem()
        if root is None:
            return

        stack: List[QtWidgets.QTreeWidgetItem] = [root]
        while stack:
            parent_item = stack.pop()
            for index in range(parent_item.childCount()):
                item = parent_item.child(index)
                if item is None:
                    continue
                stack.append(item)
                item.setData(0, self.DIMMED_ROLE, None)

    def find_template_graph_root_for_todo(self, start_todo_id: str) -> Optional[TodoItem]:
        """公开定位接口：先尝试沿树项父链，再回退至 todo_id 链路。"""
        if not start_todo_id:
            return None
        return self._graph_support.find_template_graph_root_for_todo(
            start_todo_id,
            self.todo_map,
            self._item_map,
        )

    def load_graph_data_for_root(self, root_todo: TodoItem) -> Optional[dict]:
        """通过 TodoTreeGraphSupport 加载指定图根的 graph_data。

        统一由 `_graph_support` 负责解析缓存与 ResourceManager，
        避免在调用方重复实现图数据加载与缓存更新逻辑。
        """
        if root_todo is None:
            return None
        return self._graph_support.load_graph_data_for_root(root_todo)

    def find_event_flow_root_for_todo(self, start_todo_id: str) -> Optional[TodoItem]:
        return self._graph_support.find_event_flow_root_for_todo(start_todo_id, self.todo_map)

    def collect_block_node_ids_for_header_item(
        self,
        header_item: QtWidgets.QTreeWidgetItem,
    ) -> List[str]:
        """为“逻辑块分组头”推导该块内节点 ID 集合（供预览聚焦）。"""
        return collect_block_node_ids_for_header_item(
            header_item,
            self.todo_map,
            graph_support=self._graph_support,
        )

    @staticmethod
    def _is_todo_related_to_node(detail_info: Dict[str, Any], node_id: str) -> bool:
        """判断给定 detail_info 是否与指定节点 ID 存在直接关联。"""
        if not node_id:
            return False
        normalized = str(node_id)
        candidate_ids = [
            detail_info.get("node_id"),
            detail_info.get("dst_node"),
            detail_info.get("src_node"),
            detail_info.get("target_node_id"),
            detail_info.get("data_node_id"),
            detail_info.get("prev_node_id"),
            detail_info.get("node1_id"),
            detail_info.get("node2_id"),
            detail_info.get("branch_node_id"),
        ]
        for candidate in candidate_ids:
            if candidate is None:
                continue
            if str(candidate) == normalized:
                return True
        return False

    # === 懒加载 ===

    def expand_graph_on_demand(self, graph_root: TodoItem) -> None:
        expand_graph_on_demand(self, graph_root)

    # === 批量操作 ===

    def set_all_children_state(self, todo: TodoItem, is_checked: bool) -> None:
        set_all_children_state(self.todo_map, self.todo_states, todo, is_checked, self.todo_checked.emit)


