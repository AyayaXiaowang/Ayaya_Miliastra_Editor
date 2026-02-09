from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt6 import QtGui, QtWidgets, sip
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.models.todo_detail_info_accessors import get_detail_type
from app.ui.foundation.theme_manager import Colors as ThemeColors
from app.ui.todo.todo_config import (
    DetailTypeIcons,
    StepTypeColors,
    StepTypeRules,
    TaskTypeMetadata,
)
from app.ui.todo.todo_event_flow_blocks import build_event_flow_block_groups, create_block_header_item
from app.ui.todo.tree_check_helpers import apply_leaf_state, apply_parent_progress
from engine.configs.settings import settings


class TodoTreeBuildMixin:
    """TodoTreeManager 的树构建、节点图分组与样式/富文本生成 mixin。"""

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
            # 图根 / 事件流根：即使尚未创建子树项，也应展示展开箭头（children UI 懒加载）
            if StepTypeRules.is_event_flow_root(detail_type):
                item.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            elif not todo.children and StepTypeRules.is_template_graph_root(detail_type):
                item.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
        else:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # 叶子图步骤的“虚拟明细子项”默认不在整树构建时生成（避免大图卡顿），
            # 但仍需展示展开箭头，以便用户按需展开查看明细。
            if StepTypeRules.should_have_virtual_detail_children(detail_type):
                item.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)

        if todo.children:
            apply_parent_progress(item, todo, self.todo_states, self._get_task_icon)
            self._apply_parent_style(item, todo)
        else:
            apply_leaf_state(item, todo, self.todo_states, self._get_task_icon, self._apply_item_style)
        return item

    def _try_get_resource_manager(self) -> Optional[Any]:
        """从树懒加载依赖 getter 中获取 ResourceManager（若可用）。"""
        dependency_getter = getattr(self, "_graph_expand_dependency_getter", None)
        if not callable(dependency_getter):
            return None
        dependencies = dependency_getter()
        if not isinstance(dependencies, tuple):
            return None
        if len(dependencies) < 2:
            return None
        return dependencies[1]

    @staticmethod
    def _infer_graph_type_from_graph_id(graph_id: str) -> str:
        """兜底：无法读取元数据时，根据 graph_id 字符串做轻量推断。"""
        normalized = str(graph_id or "").strip().lower()
        if not normalized:
            return "server"
        if normalized.startswith("client_") or normalized.startswith("client-") or normalized.startswith("client/"):
            return "client"
        if normalized.startswith("server_") or normalized.startswith("server-") or normalized.startswith("server/"):
            return "server"
        if "client" in normalized and "server" not in normalized:
            return "client"
        return "server"

    def _resolve_graph_type_for_graph_id(
        self,
        graph_id: str,
        *,
        resource_manager: Optional[Any],
    ) -> str:
        """优先使用轻量元数据中的 graph_type，其次用 graph_id 兜底推断。"""
        normalized_graph_id = str(graph_id or "")
        if not normalized_graph_id:
            return "server"
        if resource_manager is not None and hasattr(resource_manager, "load_graph_metadata"):
            metadata = resource_manager.load_graph_metadata(normalized_graph_id)  # type: ignore[attr-defined]
            if isinstance(metadata, dict):
                graph_type_value = metadata.get("graph_type")
                graph_type_text = str(graph_type_value or "").strip().lower()
                if graph_type_text in ["client", "server"]:
                    return graph_type_text
        return self._infer_graph_type_from_graph_id(normalized_graph_id)

    def _create_graph_type_group_item(
        self,
        *,
        title: str,
        graph_type: str,
    ) -> QtWidgets.QTreeWidgetItem:
        """创建“客户端/服务器节点图”分组项（非 Todo 树项）。"""
        group_item = QtWidgets.QTreeWidgetItem()
        group_item.setData(0, Qt.ItemDataRole.UserRole, "")
        group_item.setData(0, self.MARKER_ROLE, f"graph_type_group:{graph_type}")

        flags = group_item.flags()
        flags &= ~Qt.ItemFlag.ItemIsUserCheckable
        flags &= ~Qt.ItemFlag.ItemIsSelectable
        group_item.setFlags(flags)

        group_item.setText(0, str(title))
        group_item.setForeground(0, QtGui.QBrush(QtGui.QColor(ThemeColors.TEXT_SECONDARY)))
        return group_item

    def _build_standalone_graphs_category_grouped(
        self,
        category_todo: TodoItem,
        category_item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """将“节点图”分类在根上按 client/server 分组展示，避免同名混淆。"""
        resource_manager = self._try_get_resource_manager()
        graphs_by_type: dict[str, list[TodoItem]] = {"client": [], "server": []}

        for child_id in category_todo.children:
            graph_root_todo = self.todo_map.get(child_id)
            if graph_root_todo is None:
                continue
            graph_id = str((graph_root_todo.detail_info or {}).get("graph_id", "") or graph_root_todo.target_id or "")
            graph_type = self._resolve_graph_type_for_graph_id(
                graph_id,
                resource_manager=resource_manager,
            )
            if graph_type not in graphs_by_type:
                graph_type = "server"
            graphs_by_type[graph_type].append(graph_root_todo)

        # 无论是否同时存在 client/server，都按类型创建根分组，
        # 让用户在树的“第一层”就能区分客户端/服务器节点图。
        for graph_type in ["client", "server"]:
            graph_roots = graphs_by_type.get(graph_type) or []
            if not graph_roots:
                continue
            group_title = "客户端节点图" if graph_type == "client" else "服务器节点图"
            group_item = self._create_graph_type_group_item(
                title=group_title,
                graph_type=graph_type,
            )
            category_item.addChild(group_item)
            for graph_root_todo in graph_roots:
                self._build_single_todo_subtree(group_item, graph_root_todo)

    def _build_tree_recursive(self, todo: TodoItem, parent_item: QtWidgets.QTreeWidgetItem) -> None:
        """根据 Todo 结构递归构建树节点。

        对事件流根（event_flow_root）增加按 BasicBlock 分组的显示：
        - 按当前顺序扫描其直接子步骤；
        - 基于节点所在 BasicBlock 构造“块分组”头节点；
        - 将同一块内的步骤挂在对应分组下，其它步骤保持原有扁平结构。
        """
        detail_type = (todo.detail_info or {}).get("type", "")
        if detail_type == "category":
            category_key = str((todo.detail_info or {}).get("category", "") or "")
            if category_key == "standalone_graphs":
                self._build_standalone_graphs_category_grouped(todo, parent_item)
                return
        if StepTypeRules.is_event_flow_root(detail_type):
            flow_root_id = str(todo.todo_id or "")

            enable_lazy_load = bool(getattr(settings, "TODO_EVENT_FLOW_LAZY_LOAD_ENABLED", True))
            if enable_lazy_load:
                # 事件流根：默认不立即创建其大量子步骤，避免大图时 UI 卡顿；
                # 子步骤在用户展开该事件流根时按需分批挂载。
                if flow_root_id:
                    self._event_flow_children_pending.add(flow_root_id)
                return

            # 非懒加载模式：在构建树阶段一次性创建事件流根的全部子步骤。
            # 注意：超大事件流可能明显卡顿；该策略应由设置开关明确控制。
            if flow_root_id:
                self._event_flow_children_pending.discard(flow_root_id)

            total_children = len(todo.children or [])
            enable_block_grouping = total_children <= 800
            if enable_block_grouping:
                self._build_event_flow_tree_with_blocks(todo, parent_item)
            else:
                for child_id in todo.children:
                    child_todo = self.todo_map.get(child_id)
                    if child_todo:
                        self._build_single_todo_subtree(parent_item, child_todo)
            if flow_root_id:
                self._event_flow_children_built.add(flow_root_id)
            return

        for child_id in todo.children:
            child_todo = self.todo_map.get(child_id)
            if child_todo:
                self._build_single_todo_subtree(parent_item, child_todo)

    def _build_single_todo_subtree(
        self,
        parent_item: QtWidgets.QTreeWidgetItem,
        child_todo: TodoItem,
        *,
        insert_before: Optional[QtWidgets.QTreeWidgetItem] = None,
    ) -> None:
        """为给定 Todo 构建一个树节点及其子树。"""
        # 兜底：同一个 todo_id 只能在树中出现一次。若出现重复引用，跳过后续重复项，
        # 否则会导致 _item_map 覆盖、懒加载状态错乱以及“展开为空”的假死体验。
        existing_item = self._item_map.get(child_todo.todo_id)
        if existing_item is not None and not sip.isdeleted(existing_item):
            return

        child_item = self._create_tree_item(child_todo)
        if (
            insert_before is not None
            and insert_before.parent() is parent_item
            and parent_item.indexOfChild(insert_before) >= 0
        ):
            parent_item.insertChild(parent_item.indexOfChild(insert_before), child_item)
        else:
            parent_item.addChild(child_item)
        # 注意：图步骤的“虚拟明细子项”可能触发图模型加载与类型推断，
        # 对超大图会造成明显卡顿。默认不在整树构建时生成，必要时由选中/局部交互按需生成。
        if child_todo.children:
            self._build_tree_recursive(child_todo, child_item)
            # 首次进入任务清单页：除根目录外，所有目录默认折叠。
            child_item.setExpanded(False)

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
            if isinstance(group.block_index, int) and 0 <= group.block_index < len(basic_blocks):
                basic_block = basic_blocks[group.block_index]
                color_value = getattr(basic_block, "color", "")
                if isinstance(color_value, str) and color_value:
                    block_color_hex = color_value

            header_item = create_block_header_item(
                group.block_index,
                group_index,
                block_color_hex,
                rich_segments_role=self.RICH_SEGMENTS_ROLE,
                marker_role=self.MARKER_ROLE,
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
            tokens.append({"text": f" ({completed}/{total})", "color": neutral_color})

        item.setData(0, self.RICH_SEGMENTS_ROLE, tokens)

    def _apply_item_style(self, item: QtWidgets.QTreeWidgetItem, todo: TodoItem, is_completed: bool = False) -> None:
        color = TaskTypeMetadata.get_color(todo.task_type)
        detail_type = get_detail_type(todo)

        if not todo.children:
            if StepTypeRules.is_graph_step(detail_type):
                color = StepTypeColors.get_step_color(str(detail_type))

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
            # Tooltip 与富文本 tokens 对超大图属于“重操作”：
            # - tooltip（源码定位）仅在真正显示 tooltip 时再计算；
            # - 图步骤的富文本 tokens 默认使用“轻量 tokens”（不加载 GraphModel），保证初次渲染即有彩色样式；
            #   当用户选中步骤需要更精确的节点类别配色时，再由 ensure_tokens_for_todo 触发 GraphModel 版 tokens。
            item.setToolTip(0, "")
            if StepTypeRules.is_graph_step(detail_type):
                # 不在这里清空已生成的 tokens：选中时可能已生成 GraphModel 版富文本，高频刷新不应导致反复重算/闪烁。
                existing_tokens = item.data(0, self.RICH_SEGMENTS_ROLE)
                if not isinstance(existing_tokens, list):
                    self._graph_support.update_item_rich_tokens_lightweight(
                        item=item,
                        todo=todo,
                        get_task_icon=self._get_task_icon,
                    )
            else:
                self._graph_support.update_item_rich_tokens(
                    item=item,
                    todo=todo,
                    todo_map=self.todo_map,
                    get_task_icon=self._get_task_icon,
                )

    def _get_task_icon(self, todo: TodoItem) -> str:
        return DetailTypeIcons.get_icon(todo.task_type, todo.detail_info)



