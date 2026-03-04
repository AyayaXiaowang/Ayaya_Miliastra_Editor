from __future__ import annotations

from typing import List

from app.models.todo_item import TodoItem
from app.ui.todo.detail.todo_detail_builder_registry import (
    TodoDetailBuildContext,
    register_detail_type,
)
from app.ui.todo.detail.builders.shared_builders import (
    DetailDocument,
    DetailSection,
    ParagraphBlock,
    ParagraphStyle,
    TableBlock,
    build_collapsible_raw_section,
    format_value_preview,
)


@register_detail_type("graph_create_node")
def build_graph_create_node_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    if todo.description:
        section.blocks.append(ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL))

    node_title = str(info.get("node_title") or "")
    if node_title:
        section.blocks.append(ParagraphBlock(text=f"节点：{node_title}", style=ParagraphStyle.EMPHASIS))
    _append_graph_context_table(section, info)
    section.blocks.append(build_collapsible_raw_section(title="原始数据（detail_info）", payload=info))
    document.sections.append(section)
    return document


@register_detail_type("graph_create_and_connect")
@register_detail_type("graph_create_and_connect_reverse")
def build_graph_create_and_connect_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    if todo.description:
        section.blocks.append(ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL))

    prev_title = str(info.get("prev_node_title") or "")
    node_title = str(info.get("node_title") or "")
    arrow = "←" if detail_type == "graph_create_and_connect_reverse" else "→"
    if prev_title or node_title:
        section.blocks.append(
            ParagraphBlock(
                text=f"{prev_title} {arrow} {node_title}",
                style=ParagraphStyle.EMPHASIS,
            )
        )
    edge_id = str(info.get("edge_id") or "")
    if edge_id:
        section.blocks.append(
            ParagraphBlock(text=f"edge_id：{edge_id}", style=ParagraphStyle.HINT)
        )
    _append_graph_context_table(section, info)
    section.blocks.append(build_collapsible_raw_section(title="原始数据（detail_info）", payload=info))
    document.sections.append(section)
    return document


def _append_graph_context_table(section: DetailSection, info: dict) -> None:
    rows: List[List[str]] = []
    graph_id = str(info.get("graph_id") or "")
    if graph_id:
        rows.append(["节点图ID", graph_id])

    graph_name = str(info.get("graph_name") or "")
    if graph_name:
        rows.append(["节点图名", graph_name])

    node_title = str(info.get("node_title") or "")
    if node_title:
        rows.append(["节点", node_title])
    node_id = str(info.get("node_id") or "")
    if node_id:
        rows.append(["节点ID", node_id])

    template_id = str(info.get("template_id") or "")
    if template_id:
        rows.append(["模板上下文", template_id])
    instance_id = str(info.get("instance_id") or "")
    if instance_id:
        rows.append(["实例上下文", instance_id])

    if rows:
        section.blocks.append(TableBlock(headers=["字段", "值"], rows=rows))


@register_detail_type("template_graph_root")
def build_template_graph_root_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    if todo.description:
        section.blocks.append(ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL))

    rows: List[List[str]] = []
    graph_name = str(info.get("graph_name") or "")
    if graph_name:
        rows.append(["节点图", graph_name])
    graph_id = str(info.get("graph_id") or "")
    if graph_id:
        rows.append(["graph_id", graph_id])
    task_type = str(info.get("task_type") or "")
    if task_type:
        rows.append(["任务类型", task_type])
    graph_data_key = str(info.get("graph_data_key") or "")
    if graph_data_key:
        rows.append(["graph_data_key", graph_data_key])
    if rows:
        section.blocks.append(TableBlock(headers=["字段", "值"], rows=rows))

    section.blocks.append(
        ParagraphBlock(
            text="提示：该节点图下的具体步骤会在左侧树中展开；右侧预览可用于对照节点与连线。",
            style=ParagraphStyle.HINT,
        )
    )
    section.blocks.append(build_collapsible_raw_section(title="原始数据（detail_info）", payload=info))
    document.sections.append(section)
    return document


@register_detail_type("event_flow_root")
def build_event_flow_root_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    if todo.description:
        section.blocks.append(ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL))

    rows: List[List[str]] = []
    rows.append(["节点图ID", str(info.get("graph_id") or "")])
    rows.append(["事件节点", str(info.get("event_node_title") or "")])
    rows.append(["事件节点ID", str(info.get("event_node_id") or "")])
    root_id = str(info.get("graph_root_todo_id") or "")
    if root_id:
        rows.append(["图根Todo", root_id])
    task_type = str(info.get("task_type") or "")
    if task_type:
        rows.append(["任务类型", task_type])
    section.blocks.append(TableBlock(headers=["字段", "值"], rows=rows))
    section.blocks.append(
        ParagraphBlock(
            text="该事件流下的子步骤按顺序执行：创建节点 →（动态端口/类型/参数）→ 连线。",
            style=ParagraphStyle.HINT,
        )
    )
    document.sections.append(section)
    return document


@register_detail_type("graph_create_and_connect_data")
def build_graph_create_and_connect_data_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    if todo.description:
        section.blocks.append(ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL))

    target_title = str(info.get("target_node_title") or "")
    data_title = str(info.get("data_node_title") or "")
    if target_title or data_title:
        section.blocks.append(
            ParagraphBlock(
                text=f"{target_title} ← {data_title}",
                style=ParagraphStyle.EMPHASIS,
            )
        )

    rows: List[List[str]] = []
    rows.append(["目标节点ID", str(info.get("target_node_id") or "")])
    rows.append(["数据节点ID", str(info.get("data_node_id") or "")])
    rows.append(["edge_id", str(info.get("edge_id") or "")])
    is_copy = bool(info.get("is_copy", False))
    rows.append(["是否副本", "是" if is_copy else "否"])
    original = str(info.get("original_node_id") or "")
    if original:
        rows.append(["原始节点ID", original])
    section.blocks.append(TableBlock(headers=["字段", "值"], rows=rows))
    _append_graph_context_table(section, info)
    document.sections.append(section)
    return document


@register_detail_type("graph_connect")
def build_graph_connect_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    if todo.description:
        section.blocks.append(ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL))

    rows: List[List[str]] = []
    rows.append(["源节点ID", str(info.get("src_node") or "")])
    rows.append(["目标节点ID", str(info.get("dst_node") or "")])
    rows.append(["源端口", str(info.get("src_port") or "")])
    rows.append(["目标端口", str(info.get("dst_port") or "")])
    rows.append(["edge_id", str(info.get("edge_id") or "")])
    section.blocks.append(TableBlock(headers=["字段", "值"], rows=rows))
    _append_graph_context_table(section, info)
    document.sections.append(section)
    return document


@register_detail_type("graph_set_port_types_merged")
def build_graph_set_port_types_merged_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)

    node_title = str(info.get("node_title", ""))
    section.blocks.append(
        ParagraphBlock(text=f"节点：{node_title}", style=ParagraphStyle.EMPHASIS)
    )

    params = info.get("params", []) or []
    if isinstance(params, list) and params:
        headers = ["端口/参数", "示例值（用于推断）"]
        rows: List[List[str]] = []
        for entry in params:
            if not isinstance(entry, dict):
                rows.append([format_value_preview(entry), "-"])
                continue
            name = str(entry.get("param_name") or "")
            value = entry.get("param_value")
            rows.append([name, format_value_preview(value)])
        section.blocks.append(TableBlock(headers=headers, rows=rows))
        section.blocks.append(
            ParagraphBlock(
                text="说明：该步骤用于为泛型端口选择具体类型；示例值仅用于推断提示，不一定需要在本步输入。",
                style=ParagraphStyle.HINT,
            )
        )
    else:
        section.blocks.append(
            ParagraphBlock(
                text="该节点需要为输出侧泛型端口补齐类型（当前无示例值）。",
                style=ParagraphStyle.HINT,
            )
        )

    _append_graph_context_table(section, info)
    document.sections.append(section)
    return document


@register_detail_type("graph_add_variadic_inputs")
@register_detail_type("graph_add_dict_pairs")
@register_detail_type("graph_add_branch_outputs")
def build_graph_add_dynamic_ports_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)
    if todo.description:
        section.blocks.append(ParagraphBlock(text=str(todo.description), style=ParagraphStyle.NORMAL))

    node_title = str(info.get("node_title") or "")
    if node_title:
        section.blocks.append(ParagraphBlock(text=f"节点：{node_title}", style=ParagraphStyle.EMPHASIS))

    add_count = int(info.get("add_count", 0) or 0)
    section.blocks.append(
        ParagraphBlock(text=f"需要新增端口：{add_count} 个", style=ParagraphStyle.NORMAL)
    )
    tokens = info.get("port_tokens") or []
    if isinstance(tokens, list) and tokens:
        max_show = 30
        rows: List[List[str]] = []
        for token in tokens[:max_show]:
            rows.append([format_value_preview(token, max_len=80)])
        section.blocks.append(TableBlock(headers=["端口标记（预览）"], rows=rows))
        if len(tokens) > max_show:
            section.blocks.append(
                ParagraphBlock(
                    text="更多端口标记已省略（见下方“原始数据”折叠区）。",
                    style=ParagraphStyle.HINT,
                )
            )
    section.blocks.append(build_collapsible_raw_section(title=f"原始数据（{detail_type}）", payload=info))
    _append_graph_context_table(section, info)
    document.sections.append(section)
    return document


@register_detail_type("graph_config_node_merged")
def build_graph_config_node_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)

    node_title = str(info.get("node_title", ""))
    section.blocks.append(
        ParagraphBlock(text=f"节点：{node_title}", style=ParagraphStyle.EMPHASIS)
    )

    parameters = info.get("params", [])
    if parameters:
        headers = ["参数", "值"]
        rows: List[List[str]] = []
        for parameter_information in parameters:
            rows.append(
                [
                    str(parameter_information.get("param_name", "")),
                    format_value_preview(parameter_information.get("param_value")),
                ]
            )
        section.blocks.append(TableBlock(headers=headers, rows=rows))
        section.blocks.append(build_collapsible_raw_section(title="原始数据（params）", payload=parameters))

    document.sections.append(section)
    return document


@register_detail_type("graph_config_branch_outputs")
def build_graph_config_branch_outputs_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)

    node_title = str(info.get("node_title", ""))
    section.blocks.append(
        ParagraphBlock(text=f"节点：{node_title}", style=ParagraphStyle.EMPHASIS)
    )

    branch_list = info.get("branches", [])
    if branch_list:
        headers = ["分支端口", "匹配值"]
        rows: List[List[str]] = []
        for branch in branch_list:
            rows.append([str(branch.get("port_name", "")), str(branch.get("value", ""))])
        section.blocks.append(TableBlock(headers=headers, rows=rows))

    document.sections.append(section)
    return document


@register_detail_type("graph_connect_merged")
def build_graph_connect_merged_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)

    node_title_one = str(info.get("node1_title", ""))
    node_title_two = str(info.get("node2_title", ""))
    if node_title_one or node_title_two:
        section.blocks.append(
            ParagraphBlock(
                text=f"{node_title_one} → {node_title_two}",
                style=ParagraphStyle.EMPHASIS,
            )
        )

    edge_list = info.get("edges", [])
    if edge_list:
        headers = ["源端口", "目标端口"]
        rows: List[List[str]] = []
        for edge in edge_list:
            rows.append([str(edge.get("src_port", "")), str(edge.get("dst_port", ""))])
        section.blocks.append(TableBlock(headers=headers, rows=rows))

    document.sections.append(section)
    return document


@register_detail_type("graph_signals_overview")
def build_graph_signals_overview_document(
    _context: TodoDetailBuildContext,
    _todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title="本图信号概览", level=3)

    graph_name = str(info.get("graph_name", "") or "")
    if graph_name:
        section.blocks.append(
            ParagraphBlock(
                text=f"节点图：{graph_name}",
                style=ParagraphStyle.EMPHASIS,
            )
        )

    signal_entries = info.get("signals", []) or []
    if signal_entries:
        headers = ["信号名", "信号ID", "使用节点数", "是否在当前存档定义"]
        rows: List[List[str]] = []
        for entry in signal_entries:
            signal_name = entry.get("signal_name") or "(未命名信号)"
            signal_identifier = entry.get("signal_id") or ""
            node_count = int(entry.get("node_count", 0))
            defined = bool(entry.get("defined_in_package", False))
            defined_text = "是" if defined else "否"
            rows.append(
                [
                    str(signal_name),
                    str(signal_identifier),
                    str(node_count),
                    defined_text,
                ]
            )
        section.blocks.append(TableBlock(headers=headers, rows=rows))
        section.blocks.append(
            ParagraphBlock(
                text="双击任务或使用右上角按钮可在编辑器中查看并调整这些信号节点。",
                style=ParagraphStyle.HINT,
            )
        )

    document.sections.append(section)
    return document


@register_detail_type("graph_bind_signal")
def build_graph_bind_signal_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)

    node_title = str(info.get("node_title", ""))
    node_identifier = str(info.get("node_id", ""))
    if node_title or node_identifier:
        target_text_parts: List[str] = []
        if node_title:
            target_text_parts.append(node_title)
        if node_identifier:
            target_text_parts.append(f"({node_identifier})")
        section.blocks.append(
            ParagraphBlock(
                text="目标节点：" + " ".join(target_text_parts),
                style=ParagraphStyle.EMPHASIS,
            )
        )

    signal_name = str(info.get("signal_name") or "")
    signal_identifier = str(info.get("signal_id") or "")
    if signal_name or signal_identifier:
        signal_text_parts: List[str] = []
        if signal_name:
            signal_text_parts.append(signal_name)
        if signal_identifier:
            signal_text_parts.append(f"({signal_identifier})")
        section.blocks.append(
            ParagraphBlock(
                text="当前绑定信号：" + " ".join(signal_text_parts),
                style=ParagraphStyle.NORMAL,
            )
        )
    else:
        section.blocks.append(
            ParagraphBlock(
                text="当前绑定信号：未选择",
                style=ParagraphStyle.HINT,
            )
        )

    section.blocks.append(
        ParagraphBlock(
            text=(
                "在节点图中右键该节点，可通过“选择信号…”绑定信号，"
                "或通过“打开信号管理器…”调整信号定义。"
            ),
            style=ParagraphStyle.HINT,
        )
    )

    document.sections.append(section)
    return document


@register_detail_type("graph_bind_struct")
def build_graph_bind_struct_document(
    _context: TodoDetailBuildContext,
    todo: TodoItem,
    info: dict,
    _detail_type: str,
) -> DetailDocument:
    document = DetailDocument()
    section = DetailSection(title=str(todo.title), level=3)

    node_title = str(info.get("node_title", ""))
    node_identifier = str(info.get("node_id", ""))
    if node_title or node_identifier:
        target_text_parts: List[str] = []
        if node_title:
            target_text_parts.append(node_title)
        if node_identifier:
            target_text_parts.append(f"({node_identifier})")
        section.blocks.append(
            ParagraphBlock(
                text="目标节点：" + " ".join(target_text_parts),
                style=ParagraphStyle.EMPHASIS,
            )
        )

    struct_name = str(info.get("struct_name") or "")
    struct_identifier = str(info.get("struct_id") or "")
    if struct_name or struct_identifier:
        struct_text_parts: List[str] = []
        if struct_name:
            struct_text_parts.append(struct_name)
        if struct_identifier:
            struct_text_parts.append(f"({struct_identifier})")
        section.blocks.append(
            ParagraphBlock(
                text="当前绑定结构体：" + " ".join(struct_text_parts),
                style=ParagraphStyle.NORMAL,
            )
        )
    else:
        section.blocks.append(
            ParagraphBlock(
                text="当前绑定结构体：未选择",
                style=ParagraphStyle.HINT,
            )
        )

    field_names = info.get("field_names") or []
    if isinstance(field_names, list) and field_names:
        field_names_text = "、".join(str(name) for name in field_names)
        section.blocks.append(
            ParagraphBlock(
                text=f"已选字段：{field_names_text}",
                style=ParagraphStyle.NORMAL,
            )
        )

    section.blocks.append(
        ParagraphBlock(
            text=(
                "在节点图中右键该节点，通过“配置结构体…”对话框选择结构体与字段；"
                "结构体名输入端口只作展示，不参与连线。"
            ),
            style=ParagraphStyle.HINT,
        )
    )

    document.sections.append(section)
    return document


