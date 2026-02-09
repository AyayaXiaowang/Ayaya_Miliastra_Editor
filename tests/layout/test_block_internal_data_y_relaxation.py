from __future__ import annotations

from pathlib import Path

import pytest

from tests._helpers.project_paths import get_repo_root

from engine.graph import GraphCodeParser
from engine.graph.models import GraphModel
from engine.layout import LayoutService
from engine.layout.internal.layout_context import LayoutContext
from engine.layout.internal.layout_registry_context import ensure_layout_registry_context_for_model
from engine.layout.blocks.block_layout_context import BlockLayoutContext
from engine.layout.utils.data_y_relaxation import DataYRelaxationEngine


PROJECT_ROOT = get_repo_root()


def _asset_graph_file() -> Path:
    # 展示型仓库不依赖私有资源图；统一使用公开模板图作为回归输入。
    return (
        PROJECT_ROOT
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_踏板开关_信号广播.py"
    )


def test_effect_aim_last_attacker_graph_file_passes_node_graph_validator() -> None:
    # 使用运行时验证器适配层（唯一依赖 engine.validate 的入口）进行文件粒度校验
    from app.runtime.engine.node_graph_validator import validate_file

    ok, errors, warnings = validate_file(_asset_graph_file())
    assert ok, f"节点图校验失败：errors={errors}, warnings={warnings}"


def test_layout_is_deterministic_for_effect_aim_last_attacker_graph() -> None:
    parser = GraphCodeParser(PROJECT_ROOT)
    model, _ = parser.parse_file(_asset_graph_file())

    # 两次布局应完全可复现（相同输入输出相同坐标）
    first = LayoutService.compute_layout(model, clone_model=True, workspace_path=PROJECT_ROOT)
    second = LayoutService.compute_layout(model, clone_model=True, workspace_path=PROJECT_ROOT)

    assert set(first.positions.keys()) == set(second.positions.keys())
    for node_id, pos1 in first.positions.items():
        pos2 = second.positions[node_id]
        assert pos1 == pytest.approx(pos2, abs=1e-6), f"节点 {node_id} 坐标不稳定：{pos1} vs {pos2}"


def test_template_graph_self_entity_to_custom_var_keeps_small_vertical_offset() -> None:
    """回归：同一条数据链路上，相邻数据节点的垂直偏移不应过大。

    展示型仓库不依赖私有图：选择公开模板 `模板示例_多踏板联动` 中稳定存在的
    “获取自身实体 -> 获取自定义变量”连线对作为输入。

    断言目标：
    - 该结构确实存在（避免测试失效为“空跑”）。
    - 相邻数据节点的垂直偏移保持在合理范围内，避免因放置策略退化导致长折线与交叉显著增加。
    """
    parser = GraphCodeParser(PROJECT_ROOT)
    # 展示型仓库不依赖私有图：该结构在公开模板 `模板示例_多踏板联动` 中稳定存在。
    graph_file = (
        PROJECT_ROOT
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_多踏板联动.py"
    )
    model, _ = parser.parse_file(graph_file)
    result = LayoutService.compute_layout(model, clone_model=True, workspace_path=PROJECT_ROOT, include_augmented_model=True)
    augmented = result.augmented_model
    assert augmented is not None

    def has_kw(node_title: str, kw: str) -> bool:
        return kw in (node_title or "")

    # 构建边索引
    out_edges_by_src: dict[str, list] = {}
    for edge in augmented.edges.values():
        out_edges_by_src.setdefault(edge.src_node, []).append(edge)

    self_entity_ids = [node_id for node_id, node in augmented.nodes.items() if has_kw(node.title, "获取自身实体")]
    custom_var_ids = {node_id for node_id, node in augmented.nodes.items() if has_kw(node.title, "获取自定义变量")}

    matched_pairs: list[tuple[str, str]] = []
    for self_id in self_entity_ids:
        for edge in out_edges_by_src.get(self_id, []):
            if edge.dst_node in custom_var_ids:
                matched_pairs.append((self_id, edge.dst_node))

    assert matched_pairs, "未能在该模板图中找到“获取自身实体 -> 获取自定义变量”的连线对"

    for self_id, custom_id in matched_pairs:
        self_node = augmented.nodes[self_id]
        custom_node = augmented.nodes[custom_id]
        self_x = float(self_node.pos[0])
        self_y = float(self_node.pos[1])
        custom_x = float(custom_node.pos[0])
        custom_y = float(custom_node.pos[1])

        assert custom_x > self_x, (
            f"期望数据链路沿 X 轴从左到右："
            f"self={self_id}@({self_x},{self_y}), custom={custom_id}@({custom_x},{custom_y})"
        )

        # 允许少量偏移（不同块/策略可能导致同列微调），但不应出现明显的“上下拉开很远”。
        max_reasonable_offset = 400.0
        assert abs(custom_y - self_y) <= max_reasonable_offset, (
            f"相邻数据节点垂直偏移过大（可能导致折线/交叉显著增加）："
            f"self={self_id}@({self_x},{self_y}), custom={custom_id}@({custom_x},{custom_y}), "
            f"dy={custom_y - self_y}"
        )


def test_data_y_relaxation_centers_multi_parent_node() -> None:
    """
    回归核心诉求：多父合流时，目标节点应在父节点中心附近。

    该场景对“从右到左一次性放置”的策略并不友好（目标节点会先于父节点确定 Y），
    松弛收敛应能在父节点坐标出现后把目标节点拉回中心位置。
    """
    model = GraphModel(graph_id="test_data_y_relax_multi_parent", graph_name="test")

    # 纯数据节点：P1、P2 -> X
    parent1 = model.add_node(title="P1", category="数据", input_names=["in"], output_names=["out"])
    parent2 = model.add_node(title="P2", category="数据", input_names=["in"], output_names=["out"])
    merged = model.add_node(title="X", category="数据", input_names=["in1", "in2"], output_names=["out"])

    # 两条数据边：P1.out -> X.in1, P2.out -> X.in2
    model.add_edge(parent1.id, "out", merged.id, "in1")
    model.add_edge(parent2.id, "out", merged.id, "in2")

    registry_context = ensure_layout_registry_context_for_model(model, workspace_path=PROJECT_ROOT, include_composite=True)
    global_layout_context = LayoutContext(model, registry_context=registry_context)

    context = BlockLayoutContext(
        model=model,
        flow_node_ids=[],
        node_width=300.0,
        node_height=90.0,
        data_base_y=0.0,
        flow_to_data_gap=40.0,
        data_stack_gap=20.0,
        ui_node_header_height=20.0,
        ui_row_height=20.0,
        input_port_to_data_gap=20.0,
        global_layout_context=global_layout_context,
        block_order_index=1,
        shared_edge_indices=None,
    )

    # 该块内已放置的数据节点（按任意稳定顺序）
    context.data_nodes_in_order = [merged.id, parent1.id, parent2.id]
    context.placed_data_nodes = {merged.id, parent1.id, parent2.id}

    # 手动设置 X 列：merged 在右侧列，parents 在左侧列
    node_x_position = {parent1.id: 1.0, parent2.id: 1.0, merged.id: 2.0}
    slot_width = 220.0

    # 人为构造一个“未居中”的初值：parents 拉开，merged 偏离中心
    context.node_local_pos[parent1.id] = (node_x_position[parent1.id] * slot_width, 0.0)
    context.node_local_pos[parent2.id] = (node_x_position[parent2.id] * slot_width, 400.0)
    context.node_local_pos[merged.id] = (node_x_position[merged.id] * slot_width, 0.0)

    relaxer = DataYRelaxationEngine(context, node_x_position, slot_width)
    changed = relaxer.relax_in_place()
    assert changed is True

    parent_center = (context.node_local_pos[parent1.id][1] + context.node_local_pos[parent2.id][1]) / 2.0
    merged_y = context.node_local_pos[merged.id][1]
    assert merged_y == pytest.approx(parent_center, abs=10.0)


def test_pedal_switch_vector_scale_is_between_vector_add_and_graph_var() -> None:
    """
    回归用户反馈（模板示例_踏板开关_信号广播）：
    在同一块内，当一个纯数据节点同时由“向量加法”和“获取节点图变量”两条数据边输入时，
    期望该被连节点的 Y 落在两父节点 Y 的区间内（减少连线交叉与回折观感）。

    该测试不依赖固定 node_id：通过“节点标题 + 真实连线关系 + 所属块/事件流调试信息”定位目标实例。
    """
    parser = GraphCodeParser(PROJECT_ROOT)
    graph_file = (
        PROJECT_ROOT
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_踏板开关_信号广播.py"
    )

    # 强制开启块内数据Y松弛与调试信息，保证可定位 block/event 信息
    from engine.configs.settings import settings

    settings.SHOW_LAYOUT_Y_DEBUG = True
    settings.LAYOUT_RELAX_DATA_Y_IN_BLOCK = True

    model, _ = parser.parse_file(graph_file)
    result = LayoutService.compute_layout(model, clone_model=True, workspace_path=PROJECT_ROOT, include_augmented_model=True)
    augmented = result.augmented_model
    assert augmented is not None

    yinfo = result.y_debug_info or {}

    # 反向索引：dst -> in_edges
    in_edges_by_dst: dict[str, list] = {}
    for edge in augmented.edges.values():
        in_edges_by_dst.setdefault(edge.dst_node, []).append(edge)

    def node_title(node_id: str) -> str:
        node = augmented.nodes.get(node_id)
        return (node.title or "") if node is not None else ""

    def node_y(node_id: str) -> float:
        node = augmented.nodes.get(node_id)
        assert node is not None
        return float(node.pos[1])

    target_id: str | None = None
    parent_ids: list[str] = []

    for node_id, node in augmented.nodes.items():
        if (node.title or "") != "三维向量缩放":
            continue

        incoming = in_edges_by_dst.get(node_id, [])
        incoming_src_ids = [edge.src_node for edge in incoming]
        src_titles = [node_title(src_id) for src_id in incoming_src_ids]

        if not (any("三维向量加法" in title for title in src_titles) and any("获取节点图变量" in title for title in src_titles)):
            continue

        dbg = yinfo.get(node_id, {}) if isinstance(yinfo, dict) else {}
        if dbg.get("block_id") != "block_1":
            continue
        if dbg.get("event_flow_title") != "实体创建时":
            continue

        target_id = node_id
        parent_ids = incoming_src_ids
        break

    assert target_id is not None, "未能在该模板中定位到（加法 + 获取节点图变量）-> 三维向量缩放 的目标实例"
    assert len(parent_ids) >= 2

    parent_y_values = [node_y(pid) for pid in parent_ids if pid in augmented.nodes]
    assert len(parent_y_values) >= 2

    def node_height(node_id: str) -> float:
        info = yinfo.get(node_id, {}) if isinstance(yinfo, dict) else {}
        value = info.get("node_height", 0.0)
        return float(value) if isinstance(value, (int, float)) else 0.0

    def node_center_y(node_id: str) -> float:
        return node_y(node_id) + node_height(node_id) * 0.5

    target_center_y = node_center_y(target_id)
    parent_center_values = [node_center_y(pid) for pid in parent_ids if pid in augmented.nodes]
    assert len(parent_center_values) >= 2
    min_parent_center_y = min(parent_center_values)
    max_parent_center_y = max(parent_center_values)

    assert min_parent_center_y <= target_center_y <= max_parent_center_y, (
        f"期望三维向量缩放的中心Y位于父节点中心Y区间内："
        f"target={target_id}@{target_center_y}, parents_center_range=({min_parent_center_y}, {max_parent_center_y}), "
        f"parents={[(pid, node_title(pid), node_center_y(pid)) for pid in parent_ids if pid in augmented.nodes]}"
    )


