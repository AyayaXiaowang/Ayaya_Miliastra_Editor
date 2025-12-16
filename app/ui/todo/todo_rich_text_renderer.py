from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Callable

from app.models import TodoItem
from engine.graph.models.graph_model import GraphModel

from app.ui.todo.todo_config import StepTypeColors, StepTypeRules
from app.ui.foundation.theme_manager import Colors as ThemeColors


def _lookup_node_title_and_category(
    graph_model: Optional[GraphModel],
    node_identifier: str,
) -> Tuple[str, str]:
    if graph_model is None:
        return ("", "")
    node_model = graph_model.nodes.get(node_identifier)
    if node_model is None:
        return ("", "")
    title = str(getattr(node_model, "title", "") or "")
    category = str(getattr(node_model, "category", "") or "")
    return (title, category)


def build_rich_tokens_for_todo(
    todo: TodoItem,
    *,
    graph_model: Optional[GraphModel],
    get_task_icon: Callable[[TodoItem], str],
) -> Optional[List[Dict[str, Any]]]:
    """为给定 Todo 构建任务树富文本 token 列表。

    - 不依赖 Qt，仅返回结构化 token 数据；
    - 由调用方负责将 tokens 挂载到具体的 QTreeWidgetItem 上。
    """
    detail_info = todo.detail_info or {}
    detail_type = str(detail_info.get("type", ""))

    if todo.children:
        return None
    if not StepTypeRules.supports_rich_tokens(detail_type):
        return None

    action_color = StepTypeColors.get_step_color(detail_type)
    neutral_color = ThemeColors.TEXT_SECONDARY
    hint_color = ThemeColors.TEXT_PLACEHOLDER
    icon_character = get_task_icon(todo)

    tokens: List[Dict[str, Any]] = []

    def tint_background_color(hex_color: str) -> str:
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

    def append_icon_and_action(action_text: str) -> None:
        if isinstance(icon_character, str) and len(icon_character) > 0:
            tokens.append({"text": f"{icon_character} ", "color": neutral_color})
        tokens.append(
            {
                "text": action_text,
                "color": action_color,
                "bg": tint_background_color(action_color),
                "bold": True,
            }
        )
        tokens.append({"text": "：", "color": neutral_color})

    if detail_type == "graph_connect":
        source_node_id = str(detail_info.get("src_node", ""))
        destination_node_id = str(detail_info.get("dst_node", ""))
        source_title, source_category = _lookup_node_title_and_category(
            graph_model, source_node_id
        )
        destination_title, destination_category = _lookup_node_title_and_category(
            graph_model, destination_node_id
        )
        source_color = (
            StepTypeColors.get_node_category_color(source_category) or action_color
        )
        destination_color = (
            StepTypeColors.get_node_category_color(destination_category) or action_color
        )
        append_icon_and_action("连接")
        tokens.append({"text": source_title, "color": source_color})
        tokens.append({"text": " → ", "color": neutral_color})
        tokens.append({"text": destination_title, "color": destination_color})
    elif detail_type == "graph_connect_merged":
        first_node_title = str(detail_info.get("node1_title", ""))
        second_node_title = str(detail_info.get("node2_title", ""))
        first_node_id = str(detail_info.get("node1_id", ""))
        second_node_id = str(detail_info.get("node2_id", ""))
        if not first_node_title or not second_node_title:
            resolved_title_1, _category_1 = _lookup_node_title_and_category(
                graph_model, first_node_id
            )
            resolved_title_2, _category_2 = _lookup_node_title_and_category(
                graph_model, second_node_id
            )
            if not first_node_title:
                first_node_title = resolved_title_1
            if not second_node_title:
                second_node_title = resolved_title_2
        _unused_title_1, category_1 = _lookup_node_title_and_category(
            graph_model, first_node_id
        )
        _unused_title_2, category_2 = _lookup_node_title_and_category(
            graph_model, second_node_id
        )
        category_color_1 = (
            StepTypeColors.get_node_category_color(category_1) or action_color
        )
        category_color_2 = (
            StepTypeColors.get_node_category_color(category_2) or action_color
        )
        edge_list = detail_info.get("edges") or []
        edge_count = len(edge_list) if isinstance(edge_list, list) else 0
        append_icon_and_action("连接")
        tokens.append({"text": first_node_title, "color": category_color_1})
        tokens.append({"text": " → ", "color": neutral_color})
        tokens.append({"text": second_node_title, "color": category_color_2})
        tokens.append({"text": f"（{edge_count}条）", "color": hint_color})
    elif detail_type in {"graph_create_and_connect", "graph_create_and_connect_reverse"}:
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        _unused_title, node_category = _lookup_node_title_and_category(
            graph_model, node_identifier
        )
        node_color = (
            StepTypeColors.get_node_category_color(node_category) or action_color
        )
        append_icon_and_action("连线并创建")
        tokens.append({"text": node_title, "color": node_color})
    elif detail_type == "graph_create_and_connect_data":
        node_identifier = str(detail_info.get("data_node_id", ""))
        node_title = str(detail_info.get("data_node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        _unused_title, node_category = _lookup_node_title_and_category(
            graph_model, node_identifier
        )
        node_color = (
            StepTypeColors.get_node_category_color(node_category) or action_color
        )
        append_icon_and_action("连线并创建")
        tokens.append({"text": node_title, "color": node_color})
    elif detail_type == "graph_set_port_types_merged":
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        _unused_title, node_category = _lookup_node_title_and_category(
            graph_model, node_identifier
        )
        node_color = (
            StepTypeColors.get_node_category_color(node_category) or action_color
        )
        append_icon_and_action("设置类型")
        tokens.append({"text": node_title, "color": node_color})
    elif detail_type == "graph_config_node_merged":
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        _unused_title, node_category = _lookup_node_title_and_category(
            graph_model, node_identifier
        )
        node_color = (
            StepTypeColors.get_node_category_color(node_category) or action_color
        )
        append_icon_and_action("配置参数")
        tokens.append({"text": node_title, "color": node_color})
    elif detail_type == "graph_add_branch_outputs":
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        append_icon_and_action("新增分支端口")
        tokens.append({"text": node_title, "color": action_color})
    elif detail_type == "graph_config_branch_outputs":
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        branch_items = detail_info.get("branches") or []
        branch_count = len(branch_items) if isinstance(branch_items, list) else 0
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        append_icon_and_action("配置分支输出")
        tokens.append({"text": node_title, "color": action_color})
        if branch_count > 0:
            tokens.append({"text": f"（{branch_count}项）", "color": hint_color})
    elif detail_type in {"graph_add_variadic_inputs", "graph_add_dict_pairs"}:
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        label_text = "新增变参" if detail_type == "graph_add_variadic_inputs" else "新增键值端口"
        append_icon_and_action(label_text)
        tokens.append({"text": node_title, "color": action_color})
    elif detail_type == "graph_bind_signal":
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        append_icon_and_action("设置信号")
        tokens.append({"text": node_title, "color": action_color})
    elif detail_type == "graph_bind_struct":
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        append_icon_and_action("配置结构体")
        tokens.append({"text": node_title, "color": action_color})
    elif detail_type == "graph_create_node":
        node_identifier = str(detail_info.get("node_id", ""))
        node_title = str(detail_info.get("node_title", ""))
        if not node_title:
            resolved_title, _category = _lookup_node_title_and_category(
                graph_model, node_identifier
            )
            node_title = resolved_title
        _unused_title, node_category = _lookup_node_title_and_category(
            graph_model, node_identifier
        )
        node_color = (
            StepTypeColors.get_node_category_color(node_category) or action_color
        )
        append_icon_and_action("创建节点")
        tokens.append({"text": node_title, "color": node_color})

    if not tokens:
        return None
    return tokens


