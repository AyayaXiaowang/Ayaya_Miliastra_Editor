from __future__ import annotations

from pathlib import Path

from tests._helpers.project_paths import get_repo_root

from engine.graph.composite_code_parser import CompositeCodeParser
from engine.graph.models.graph_model import GraphModel
from engine.nodes.node_definition_loader import load_all_nodes
from engine.validate.api import validate_files


def _parse_composite_template():
    workspace_root = get_repo_root()
    composite_path = (
        workspace_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "演示项目"
        / "复合节点库"
        / "composite_多引脚模板_示例.py"
    )
    assert composite_path.is_file()

    node_library = load_all_nodes(workspace_root, include_composite=False, verbose=False)
    parser = CompositeCodeParser(node_library=node_library, verbose=False)
    return parser.parse_file(composite_path)


def _deserialize_graph(cfg) -> GraphModel:
    return GraphModel.deserialize(cfg.sub_graph)


def test_template_file_passes_engine_validate_files() -> None:
    """模板示例应能通过引擎校验（禁止因规则/缓存漂移导致“示例无法自检通过”）。"""
    workspace_root = get_repo_root()
    composite_path = (
        workspace_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "演示项目"
        / "复合节点库"
        / "composite_多引脚模板_示例.py"
    )
    assert composite_path.is_file()

    report = validate_files([composite_path], workspace_root, strict_entity_wire_only=False, use_cache=False)
    errors = [issue for issue in report.issues if issue.level == "error"]
    assert not errors, f"模板示例不应触发 error：{[e.code for e in errors]}"


def test_virtual_pins_shape_for_main_and_aux_entries():
    cfg = _parse_composite_template()
    pins = {p.pin_name: p for p in cfg.virtual_pins}

    expected_names = {
        "主流程入口",
        "输入数值A",
        "输入数值B",
        "说明文本",
        "正向分支",
        "非正向分支",
        "求和结果",
        "描述回声",
        "辅助流程入口",
        "输入列表",
        "默认整数",
        "列表非空",
        "列表为空",
        "列表首元素",
        "列表长度",
    }
    assert expected_names.issubset(pins.keys())

    assert pins["主流程入口"].is_flow and pins["主流程入口"].is_input
    assert pins["正向分支"].is_flow and (not pins["正向分支"].is_input)
    assert pins["非正向分支"].is_flow and (not pins["非正向分支"].is_input)
    assert pins["辅助流程入口"].is_flow and pins["辅助流程入口"].is_input
    assert pins["列表非空"].is_flow and (not pins["列表非空"].is_input)
    assert pins["列表为空"].is_flow and (not pins["列表为空"].is_input)

    assert pins["输入数值A"].pin_type == "浮点数"
    assert pins["输入数值B"].pin_type == "浮点数"
    assert pins["说明文本"].pin_type == "字符串"
    assert pins["输入列表"].pin_type == "整数列表"
    assert pins["默认整数"].pin_type == "整数"
    assert pins["列表首元素"].pin_type == "整数"
    assert pins["列表长度"].pin_type == "整数"


def test_flow_outputs_mapped_to_branch_nodes():
    cfg = _parse_composite_template()
    graph = _deserialize_graph(cfg)
    title_by_id = {node_id: node.title for node_id, node in graph.nodes.items()}

    flow_expect = {
        "正向分支": "双分支",
        "非正向分支": "双分支",
        "列表非空": "双分支",
        "列表为空": "双分支",
    }

    for pin_name, expected_title in flow_expect.items():
        vpin = next((p for p in cfg.virtual_pins if p.pin_name == pin_name), None)
        assert vpin is not None and vpin.is_flow
        assert vpin.mapped_ports, f"流程引脚 {pin_name} 应映射到分支节点"
        mapped_titles = {title_by_id.get(port.node_id) for port in vpin.mapped_ports if port.node_id in title_by_id}
        assert expected_title in mapped_titles


def test_data_outputs_bound_to_calculation_nodes():
    cfg = _parse_composite_template()
    graph = _deserialize_graph(cfg)
    title_by_id = {node_id: node.title for node_id, node in graph.nodes.items()}

    def _assert_data_pin(pin_name: str, expected_title: str):
        vpin = next((p for p in cfg.virtual_pins if p.pin_name == pin_name), None)
        assert vpin is not None and (not vpin.is_flow)
        assert vpin.mapped_ports, f"数据引脚 {pin_name} 应有映射"
        mapped_titles = {title_by_id.get(port.node_id) for port in vpin.mapped_ports if port.node_id in title_by_id}
        assert expected_title in mapped_titles

    _assert_data_pin("求和结果", "加法运算")
    _assert_data_pin("列表首元素", "获取局部变量")
    _assert_data_pin("列表长度", "获取列表长度")


def test_graph_contains_expected_nodes():
    cfg = _parse_composite_template()
    graph = _deserialize_graph(cfg)
    titles = {node.title for node in graph.nodes.values()}

    expected_nodes = {"加法运算", "数值大于", "获取列表长度", "获取局部变量", "双分支"}
    assert expected_nodes.issubset(titles)

