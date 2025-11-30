from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from app.common.graph_data_cache import resolve_graph_data, store_graph_data
from app.models import TodoItem
from app.models.todo_node_type_helper import NodeTypeHelper
from engine.graph.models.graph_model import GraphModel
from engine.graph.models.graph_config import GraphConfig
from engine.resources.resource_manager import ResourceType
from app.automation.ports.port_type_inference import infer_dict_key_value_types_for_input

from ui.todo.graph_model_cache_service import get_or_build_graph_model
from ui.todo.port_type_inference_adapter import (
    PortTypeExecutorAdapter,
    infer_concrete_port_type_for_step,
)
from ui.todo.todo_config import TodoStyles, StepTypeColors, StepTypeRules
from ui.todo.todo_rich_text_renderer import build_rich_tokens_for_todo
from ui.foundation.theme_manager import Colors as ThemeColors


class TodoTreeGraphSupport:
    """封装 Todo 树中与图模型/类型推断/富文本相关的辅助逻辑。

    该类不感知运行时状态或业务执行，仅依赖：
    - QTreeWidget（用于查找顶层窗口与资源管理器）
    - rich_segments_role（用于在树项上挂载富文本 tokens）
    - 内部 GraphModel/节点定义缓存与端口类型推断工具
    """

    def __init__(
        self,
        tree: QtWidgets.QTreeWidget,
        rich_segments_role: int,
    ) -> None:
        self._tree = tree
        self._rich_segments_role = rich_segments_role
        self._graph_model_cache: Dict[str, GraphModel] = {}
        self._type_helper = NodeTypeHelper()
        self._type_helper_executor = PortTypeExecutorAdapter(self._type_helper)

    # === BasicBlock / 事件流分组 ===

    # === 配置/类型步骤的虚拟子项 ===

    def rebuild_virtual_detail_children(
        self,
        item: QtWidgets.QTreeWidgetItem,
        todo: TodoItem,
        todo_map: Dict[str, TodoItem],
    ) -> None:
        """根据 Todo 详情为配置/类型步骤附加只读子项。

        这些子项仅用于展示“配置什么→为什么/类型”，不可勾选，也不会参与执行与完成度统计。
        """
        info = todo.detail_info or {}
        detail_type = str(info.get("type", ""))
        if not StepTypeRules.should_have_virtual_detail_children(detail_type):
            # 移除不再符合规则的虚拟子项（避免类型变更后残留）
            self.clear_virtual_detail_children(item)
            return

        # 先清空当前挂在该项下的虚拟子项
        self.clear_virtual_detail_children(item)

        params = info.get("params") or []
        if not isinstance(params, list) or not params:
            # 无明细参数时不生成子项
            return

        # 参数配置步骤保持原有“配置「参数名」为「值」”的简单列表展示。
        if StepTypeRules.is_config_step(detail_type):
            for param in params:
                if not isinstance(param, dict):
                    continue
                param_name = str(param.get("param_name") or "")
                if not param_name:
                    continue
                raw_value = param.get("param_value", "")
                value_text = str(raw_value) if raw_value is not None else ""

                child = QtWidgets.QTreeWidgetItem()
                child.setData(0, Qt.ItemDataRole.UserRole + 1, "virtual_detail_child")

                flags = child.flags()
                flags &= ~Qt.ItemFlag.ItemIsUserCheckable
                child.setFlags(flags)

                display_value = value_text if value_text != "" else "(空)"
                child.setText(0, f"配置「{param_name}」为「{display_value}」")

                color = ThemeColors.TEXT_SECONDARY
                child.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
                child.setData(0, Qt.ItemDataRole.UserRole, "")
                item.addChild(child)
            return

        # 端口类型设置步骤：为每个端口生成一条更细粒度的子步骤，
        # 文案中包含“侧（左/右）+ 端口序号 + 端口名 + 推断类型”，并按“左侧优先、端口序号升序”排序。
        graph_model, _graph_id = self.get_graph_model_for_item(
            item, todo.todo_id, todo_map
        )
        node_identifier = str(info.get("node_id", "") or "")
        node_model = graph_model.nodes.get(node_identifier) if (
            graph_model is not None and node_identifier in graph_model.nodes
        ) else None

        ordered_entries: List[Dict[str, Any]] = []
        for param in params:
            if not isinstance(param, dict):
                continue
            param_name = str(param.get("param_name") or "")
            if not param_name:
                continue
            raw_value = param.get("param_value", "")

            concrete_type = infer_concrete_port_type_for_step(
                param_name=param_name,
                raw_value=raw_value,
                todo=todo,
                graph_model=graph_model,
                type_helper=self._type_helper,
                type_helper_executor=self._type_helper_executor,
            )
            if not isinstance(concrete_type, str) or not concrete_type.strip():
                concrete_type = "字符串"

            # 字典端口：结合图模型推断键/值类型，并在文案中写清楚两侧类型；
            # 若无法从图中推断，则不为该端口生成类型明细子项，避免误导为“字符串/字符串”。
            if (
                param_name == "字典"
                and graph_model is not None
                and node_model is not None
            ):
                dict_types = infer_dict_key_value_types_for_input(
                    node_model,
                    param_name,
                    graph_model,
                    None,
                    None,
                    None,
                )
                if dict_types is None:
                    # 无法从图变量推断出键/值类型：跳过该端口的类型明细。
                    continue
                key_type, value_type = dict_types
                key_display = (
                    key_type
                    if isinstance(key_type, str) and key_type.strip()
                    else "字符串"
                )
                value_display = (
                    value_type
                    if isinstance(value_type, str) and value_type.strip()
                    else "字符串"
                )
                concrete_type = f"键类型：{key_display}，值类型：{value_display}"

            port_side: str = ""
            port_index: int = -1

            if node_model is not None:
                for input_index, input_port in enumerate(getattr(node_model, "inputs", []) or []):
                    port_name = getattr(input_port, "name", "")
                    if isinstance(port_name, str) and port_name == param_name:
                        port_side = "left"
                        port_index = int(input_index)
                        break

                if not port_side:
                    for output_index, output_port in enumerate(getattr(node_model, "outputs", []) or []):
                        port_name = getattr(output_port, "name", "")
                        if isinstance(port_name, str) and port_name == param_name:
                            port_side = "right"
                            port_index = int(output_index)
                            break

            ordered_entries.append(
                {
                    "param_name": param_name,
                    "concrete_type": concrete_type,
                    "port_side": port_side,
                    "port_index": port_index,
                }
            )

        def _side_sort_key(port_side: str) -> int:
            if port_side == "left":
                return 0
            if port_side == "right":
                return 1
            return 2

        ordered_entries.sort(
            key=lambda entry: (
                _side_sort_key(entry.get("port_side", "")),
                entry.get("port_index", -1) if int(entry.get("port_index", -1)) >= 0 else 9999,
                entry.get("param_name", ""),
            )
        )

        for entry in ordered_entries:
            param_name = entry["param_name"]
            concrete_type = entry["concrete_type"]
            port_side = entry["port_side"]
            port_index = entry["port_index"]

            child = QtWidgets.QTreeWidgetItem()
            child.setData(0, Qt.ItemDataRole.UserRole + 1, "virtual_detail_child")

            flags = child.flags()
            flags &= ~Qt.ItemFlag.ItemIsUserCheckable
            child.setFlags(flags)

            if isinstance(port_side, str) and port_side:
                side_label = "左侧" if port_side == "left" else "右侧"
                display_index = int(port_index) + 1 if isinstance(port_index, int) and port_index >= 0 else 0
                if display_index > 0:
                    child.setText(
                        0,
                        f"设置{side_label}的端口{display_index}【{param_name}】为【{concrete_type}】",
                    )
                else:
                    child.setText(
                        0,
                        f"设置{side_label}的端口【{param_name}】为【{concrete_type}】",
                    )
            else:
                # 当无法从图模型解析端口侧或序号时，退回到不包含侧/序号的文案
                child.setText(0, f"设置端口【{param_name}】为【{concrete_type}】")

            color = ThemeColors.TEXT_SECONDARY
            child.setForeground(0, QtGui.QBrush(QtGui.QColor(color)))
            child.setData(0, Qt.ItemDataRole.UserRole, "")
            item.addChild(child)

    def clear_virtual_detail_children(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """移除挂在指定树项下的所有虚拟明细子项。"""
        # 反向遍历以安全删除
        for index in range(item.childCount() - 1, -1, -1):
            child = item.child(index)
            marker = child.data(0, Qt.ItemDataRole.UserRole + 1)
            if marker == "virtual_detail_child":
                item.takeChild(index)

    # === 节点类别颜色与富文本 tokens ===

    def get_node_category_color(
        self,
        item: QtWidgets.QTreeWidgetItem,
        todo: TodoItem,
        todo_map: Dict[str, TodoItem],
    ) -> str:
        info = todo.detail_info or {}
        detail_type = info.get("type", "")
        if not StepTypeRules.is_graph_step(detail_type):
            return ""

        node_id = (
            info.get("node_id")
            or info.get("dst_node")
            or info.get("src_node")
            or info.get("target_node_id")
            or info.get("data_node_id")
            or info.get("prev_node_id")
            or info.get("node1_id")
            or info.get("node2_id")
            or info.get("branch_node_id")
        )
        node_title = info.get("node_title", "")
        if isinstance(node_title, str) and node_title == "多分支":
            return StepTypeColors.get_node_category_color("流程控制节点")
        if not node_id:
            return ""

        graph_model, _graph_id = self.get_graph_model_for_item(
            item, todo.todo_id, todo_map
        )
        if graph_model is None:
            return ""

        node_obj = graph_model.nodes.get(node_id)
        if not node_obj:
            return ""
        category = getattr(node_obj, "category", "") or ""
        return StepTypeColors.get_node_category_color(category)

    def update_item_rich_tokens(
        self,
        item: QtWidgets.QTreeWidgetItem,
        todo: TodoItem,
        todo_map: Dict[str, TodoItem],
        get_task_icon,
    ) -> None:
        graph_model, _graph_id = self.get_graph_model_for_item(
            item, todo.todo_id, todo_map
        )
        tokens = build_rich_tokens_for_todo(
            todo,
            graph_model=graph_model,
            get_task_icon=get_task_icon,
        )
        if tokens is None:
            item.setData(0, self._rich_segments_role, None)
        else:
            item.setData(0, self._rich_segments_role, tokens)

    # === GraphModel 加载与节点标题查询 ===

    def get_graph_model_for_item(
        self,
        item: QtWidgets.QTreeWidgetItem,
        todo_id: Optional[str],
        todo_map: Dict[str, TodoItem],
    ) -> Tuple[Optional[GraphModel], str]:
        root_todo = self.find_template_graph_root_for_item(item, todo_map)
        if not root_todo and todo_id:
            root_todo = self.find_template_graph_root_for_todo_id(todo_id, todo_map)
        if not root_todo:
            return (None, "")
        root_info = root_todo.detail_info or {}
        graph_identifier = str(root_info.get("graph_id", "") or "")
        graph_data = resolve_graph_data(root_info)
        if graph_data is None:
            graph_data = self.load_graph_data_for_root(root_todo)
        if not graph_identifier or not isinstance(graph_data, dict):
            return (None, "")
        model = get_or_build_graph_model(
            graph_identifier,
            graph_data=graph_data,
            cache=self._graph_model_cache,
        )
        return (model, graph_identifier)

    def load_graph_data_for_root(self, root_todo: TodoItem) -> Optional[dict]:
        info = root_todo.detail_info or {}
        cached = resolve_graph_data(info)
        if isinstance(cached, dict) and ("nodes" in cached or "edges" in cached):
            return cached
        graph_id = str(info.get("graph_id", "") or "")
        if not graph_id:
            return None
        resource_manager = self._resolve_resource_manager()
        if resource_manager is None:
            return None
        data = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
        if not data:
            return None
        graph_config = GraphConfig.deserialize(data)
        graph_data = graph_config.data
        new_info = dict(info)
        cache_key = store_graph_data(root_todo.todo_id, graph_id, graph_data)
        new_info["graph_data_key"] = cache_key
        new_info.pop("graph_data", None)
        root_todo.detail_info = new_info
        return graph_data

    def _resolve_resource_manager(self):
        top_widget = self._tree.window()
        if top_widget is None:
            return None
        return getattr(top_widget, "resource_manager", None)

    # === 图根定位 ===

    def find_template_graph_root_for_item(
        self,
        start_item: QtWidgets.QTreeWidgetItem,
        todo_map: Dict[str, TodoItem],
    ) -> Optional[TodoItem]:
        current_item = start_item
        while current_item is not None:
            tid = current_item.data(0, Qt.ItemDataRole.UserRole)
            t = todo_map.get(tid)
            if t and StepTypeRules.is_template_graph_root((t.detail_info or {}).get("type")):
                return t
            current_item = current_item.parent()
        return None

    def find_template_graph_root_for_todo_id(
        self,
        start_todo_id: str,
        todo_map: Dict[str, TodoItem],
    ) -> Optional[TodoItem]:
        current_id = start_todo_id
        visited: set[str] = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            todo = todo_map.get(current_id)
            if not todo:
                break
            if StepTypeRules.is_template_graph_root((todo.detail_info or {}).get("type")):
                return todo
            current_id = todo.parent_id or ""
        return None

    def find_template_graph_root_for_todo(
        self,
        start_todo_id: str,
        todo_map: Dict[str, TodoItem],
        item_map: Dict[str, QtWidgets.QTreeWidgetItem],
    ) -> Optional[TodoItem]:
        if not start_todo_id:
            return None
        item = item_map.get(start_todo_id)
        if item is not None:
            root = self.find_template_graph_root_for_item(item, todo_map)
            if root is not None:
                return root
        return self.find_template_graph_root_for_todo_id(start_todo_id, todo_map)

    def find_event_flow_root_for_todo(
        self,
        start_todo_id: str,
        todo_map: Dict[str, TodoItem],
    ) -> Optional[TodoItem]:
        current_id = start_todo_id
        visited: set[str] = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            t = todo_map.get(current_id)
            if not t:
                break
            info = t.detail_info or {}
            if StepTypeRules.is_event_flow_root(info.get("type")):
                return t
            current_id = t.parent_id
        return None


