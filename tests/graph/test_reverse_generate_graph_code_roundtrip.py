from __future__ import annotations

from pathlib import Path

from engine.graph import GraphCodeParser, build_semantic_signature, diff_semantic_signature, generate_graph_code_from_model
from engine.nodes.node_registry import get_node_registry
from engine.resources.definition_schema_view import set_default_definition_schema_view_active_package_id
from engine.signal import invalidate_default_signal_repository_cache
from engine.utils.runtime_scope import set_active_package_id
from tests._helpers.project_paths import get_repo_root


def test_reverse_generate_graph_code_roundtrip_linear_graph(tmp_path: Path) -> None:
    repo_root = get_repo_root()
    # 该用例依赖示例项目模板下的信号定义（assets/资源库/项目存档/示例项目模板/管理配置/信号）。
    # 若不切换 Schema 作用域，默认只扫描共享根，会导致【监听信号】事件节点缺少“信号名”常量并触发 strict fail-closed。
    set_active_package_id("示例项目模板")
    set_default_definition_schema_view_active_package_id("示例项目模板")
    invalidate_default_signal_repository_cache()
    registry = get_node_registry(repo_root, include_composite=True)
    node_library = registry.get_library()

    source_file = (
        repo_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "模板示例"
        / "模板示例_信号全类型_发送与监听.py"
    )
    assert source_file.is_file()

    parser = GraphCodeParser(repo_root, node_library=node_library, strict=True)
    try:
        model_a, _ = parser.parse_file(source_file)

        code = generate_graph_code_from_model(model_a, node_library=node_library)

        generated_file = tmp_path / "generated_reverse_graph_code.py"
        generated_file.write_text(code, encoding="utf-8")

        model_b, _ = parser.parse_file(generated_file)

        sig_a = build_semantic_signature(model_a)
        sig_b = build_semantic_signature(model_b)
        diffs = diff_semantic_signature(sig_a, sig_b)
        assert diffs == []
    finally:
        set_active_package_id(None)
        set_default_definition_schema_view_active_package_id(None)
        invalidate_default_signal_repository_cache()


