from __future__ import annotations

from typing import Dict, Optional

from app.models import TodoItem
from engine.graph.models.graph_model import GraphModel, NodeModel
from app.ui.foundation.theme_manager import Colors as ThemeColors
from app.ui.todo.todo_config import StepTypeColors
from app.ui.todo.todo_detail_model import ParagraphBlock, ParagraphStyle, TableBlock
from app.ui.todo.todo_detail_renderer import TodoDetailBuilder
from app.ui.todo.todo_rich_text_renderer import build_rich_tokens_for_todo


def create_todo_item(
    detail_type: str,
    *,
    title: str = "测试任务",
    description: str = "",
    detail_extra: Optional[Dict[str, object]] = None,
    todo_identifier: str = "todo",
) -> TodoItem:
    detail_information: Dict[str, object] = {"type": detail_type}
    if detail_extra:
        detail_information.update(detail_extra)
    return TodoItem(
        todo_id=todo_identifier,
        parent_id="",
        children=[],
        level=0,
        task_type="template",
        title=title,
        description=description,
        target_id=str(detail_information.get("graph_id", "")),
        detail_info=detail_information,
    )


def compute_tinted_color(hex_color: str) -> str:
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


def test_detail_builder_root_includes_overview() -> None:
    categories_info = {
        "图模板": [("英雄模板", "模板图")],
        "空类别": [],
    }
    builder = TodoDetailBuilder(
        collect_categories_info=lambda todo: categories_info,
        collect_category_items=lambda todo: [],
        collect_template_summary=lambda todo: {},
        collect_instance_summary=lambda todo: {},
    )
    todo = create_todo_item(
        "root",
        title="根任务",
        description="存档概览",
        detail_extra={"package_name": "测试存档"},
        todo_identifier="root",
    )

    document = builder.build_document(todo)

    assert len(document.sections) == 2
    header_section = document.sections[0]
    assert header_section.title == "测试存档"
    assert header_section.level == 3
    assert isinstance(header_section.blocks[0], ParagraphBlock)
    assert header_section.blocks[0].text == "存档概览"
    overview_section = document.sections[1]
    assert overview_section.title == "配置概览"
    assert overview_section.level == 4
    assert isinstance(overview_section.blocks[0], ParagraphBlock)
    assert overview_section.blocks[0].text == "图模板：1 项"
    assert isinstance(overview_section.blocks[1], TableBlock)
    assert overview_section.blocks[1].headers == ["名称", "类型/说明"]
    assert overview_section.blocks[1].rows[0] == ["英雄模板", "模板图"]
    assert isinstance(overview_section.blocks[2], ParagraphBlock)
    assert overview_section.blocks[2].style == ParagraphStyle.EMPHASIS
    assert overview_section.blocks[2].text == "空类别：0 项"


def test_detail_builder_category_templates_table() -> None:
    category_items = [
        {"name": "剑士", "entity_type": "角色", "config_summary": "2 项属性"},
        {"name": "弓手", "entity_type": "角色", "config_summary": "1 项属性"},
    ]
    builder = TodoDetailBuilder(
        collect_categories_info=lambda todo: {},
        collect_category_items=lambda todo: category_items,
        collect_template_summary=lambda todo: {},
        collect_instance_summary=lambda todo: {},
    )
    todo = create_todo_item(
        "category",
        title="模板分类",
        detail_extra={"category": "templates", "count": len(category_items)},
        todo_identifier="category_templates",
    )

    document = builder.build_document(todo)

    assert len(document.sections) == 1
    category_section = document.sections[0]
    assert category_section.title == "模板分类"
    assert isinstance(category_section.blocks[0], ParagraphBlock)
    assert category_section.blocks[0].text == "共 2 项配置任务"
    assert isinstance(category_section.blocks[1], TableBlock)
    assert category_section.blocks[1].headers == ["元件名称", "实体类型", "配置项"]
    assert category_section.blocks[1].rows == [
        ["剑士", "角色", "2 项属性"],
        ["弓手", "角色", "1 项属性"],
    ]


def test_detail_builder_template_summary_with_description() -> None:
    summary = {"基础属性": 2, "组件": 1}
    builder = TodoDetailBuilder(
        collect_categories_info=lambda todo: {},
        collect_category_items=lambda todo: [],
        collect_template_summary=lambda todo: summary,
        collect_instance_summary=lambda todo: {},
    )
    todo = create_todo_item(
        "template",
        title="模板任务",
        description="",
        detail_extra={
            "name": "角色模板",
            "entity_type": "角色",
            "description": "带有基础属性的角色模板",
        },
        todo_identifier="template_task",
    )

    document = builder.build_document(todo)

    assert len(document.sections) == 2
    template_section = document.sections[0]
    assert template_section.title == "角色模板"
    assert isinstance(template_section.blocks[0], ParagraphBlock)
    assert template_section.blocks[0].style == ParagraphStyle.EMPHASIS
    assert template_section.blocks[0].text == "实体类型：角色"
    assert isinstance(template_section.blocks[1], ParagraphBlock)
    assert template_section.blocks[1].text == "带有基础属性的角色模板"
    summary_section = document.sections[1]
    assert summary_section.title == "配置清单"
    assert isinstance(summary_section.blocks[0], TableBlock)
    assert summary_section.blocks[0].headers == ["配置项", "数量"]
    assert summary_section.blocks[0].rows == [["基础属性", "2"], ["组件", "1"]]


def test_detail_builder_graph_bind_signal_blocks() -> None:
    builder = TodoDetailBuilder(
        collect_categories_info=lambda todo: {},
        collect_category_items=lambda todo: [],
        collect_template_summary=lambda todo: {},
        collect_instance_summary=lambda todo: {},
    )
    todo = create_todo_item(
        "graph_bind_signal",
        title="绑定信号",
        detail_extra={
            "node_title": "监听事件",
            "node_id": "node_1",
            "signal_name": "进入战斗",
            "signal_id": "signal_enter",
        },
        todo_identifier="bind_signal",
    )

    document = builder.build_document(todo)

    assert len(document.sections) == 1
    section = document.sections[0]
    assert section.title == "绑定信号"
    assert len(section.blocks) == 3
    target_block, signal_block, hint_block = section.blocks
    assert isinstance(target_block, ParagraphBlock)
    assert target_block.style == ParagraphStyle.EMPHASIS
    assert target_block.text == "目标节点：监听事件 (node_1)"
    assert isinstance(signal_block, ParagraphBlock)
    assert signal_block.style == ParagraphStyle.NORMAL
    assert signal_block.text == "当前绑定信号：进入战斗 (signal_enter)"
    assert isinstance(hint_block, ParagraphBlock)
    assert hint_block.style == ParagraphStyle.HINT


def test_build_rich_tokens_for_connect_uses_node_titles() -> None:
    graph_model = GraphModel(graph_id="graph_for_tokens")
    graph_model.nodes["src_node"] = NodeModel(
        id="src_node",
        title="开始",
        category="事件",
    )
    graph_model.nodes["dst_node"] = NodeModel(
        id="dst_node",
        title="结束",
        category="执行",
    )
    todo = create_todo_item(
        "graph_connect",
        title="连接节点",
        detail_extra={"src_node": "src_node", "dst_node": "dst_node"},
        todo_identifier="connect_step",
    )

    tokens = build_rich_tokens_for_todo(
        todo,
        graph_model=graph_model,
        get_task_icon=lambda task: "★",
    )

    assert tokens is not None
    token_texts = [token["text"] for token in tokens]
    assert token_texts == ["★ ", "连接", "：", "开始", " → ", "结束"]
    action_color = StepTypeColors.get_step_color("graph_connect")
    assert tokens[1]["color"] == action_color
    assert tokens[1]["bg"] == compute_tinted_color(action_color)
    assert tokens[3]["color"] == StepTypeColors.get_node_category_color("事件")
    assert tokens[5]["color"] == StepTypeColors.get_node_category_color("执行")


def test_build_rich_tokens_for_branch_outputs_adds_count_hint() -> None:
    todo = create_todo_item(
        "graph_config_branch_outputs",
        title="配置分支输出",
        detail_extra={
            "node_title": "条件节点",
            "node_id": "node_branch",
            "branches": [
                {"port_name": "是", "value": "1"},
                {"port_name": "否", "value": "0"},
            ],
        },
        todo_identifier="branch_config",
    )

    tokens = build_rich_tokens_for_todo(
        todo,
        graph_model=None,
        get_task_icon=lambda task: "☆",
    )

    assert tokens is not None
    token_texts = [token["text"] for token in tokens]
    assert token_texts == ["☆ ", "配置分支输出", "：", "条件节点", "（2项）"]
    action_color = StepTypeColors.get_step_color("graph_config_branch_outputs")
    assert tokens[1]["color"] == action_color
    assert tokens[1]["bg"] == compute_tinted_color(action_color)
    assert tokens[4]["color"] == ThemeColors.TEXT_PLACEHOLDER


def test_build_rich_tokens_returns_none_for_parent_items() -> None:
    todo = create_todo_item(
        "graph_connect",
        title="父级步骤",
        detail_extra={"src_node": "a", "dst_node": "b"},
        todo_identifier="parent_step",
    )
    todo.children = ["child-step"]

    tokens = build_rich_tokens_for_todo(
        todo,
        graph_model=None,
        get_task_icon=lambda task: "★",
    )

    assert tokens is None

