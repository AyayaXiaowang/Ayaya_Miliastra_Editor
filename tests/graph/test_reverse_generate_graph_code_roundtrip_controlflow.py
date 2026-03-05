from __future__ import annotations

from pathlib import Path

from engine.graph import GraphCodeParser, build_semantic_signature, diff_semantic_signature, generate_graph_code_from_model
from engine.nodes.node_registry import get_node_registry
from tests._helpers.project_paths import get_repo_root


def _roundtrip_and_assert_equal(*, model_a, generated_path: Path, parser: GraphCodeParser) -> None:
    model_b, _ = parser.parse_file(generated_path)
    sig_a = build_semantic_signature(model_a)
    sig_b = build_semantic_signature(model_b)
    diffs = diff_semantic_signature(sig_a, sig_b)
    assert diffs == []


def test_reverse_roundtrip_template_branch_local_var(tmp_path: Path) -> None:
    repo_root = get_repo_root()
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
        / "模板示例_局部变量_分支设置.py"
    )
    assert source_file.is_file()

    parser = GraphCodeParser(repo_root, node_library=node_library, strict=True)
    model_a, _ = parser.parse_file(source_file)

    code = generate_graph_code_from_model(model_a, node_library=node_library)
    generated_file = tmp_path / "reverse_branch_local_var.py"
    generated_file.write_text(code, encoding="utf-8")

    _roundtrip_and_assert_equal(model_a=model_a, generated_path=generated_file, parser=parser)


def test_reverse_roundtrip_template_loop_local_var(tmp_path: Path) -> None:
    repo_root = get_repo_root()
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
        / "模板示例_局部变量计数.py"
    )
    assert source_file.is_file()

    parser = GraphCodeParser(repo_root, node_library=node_library, strict=True)
    model_a, _ = parser.parse_file(source_file)

    code = generate_graph_code_from_model(model_a, node_library=node_library)
    generated_file = tmp_path / "reverse_loop_local_var.py"
    generated_file.write_text(code, encoding="utf-8")

    _roundtrip_and_assert_equal(model_a=model_a, generated_path=generated_file, parser=parser)


def test_reverse_roundtrip_nested_match_break_in_loop(tmp_path: Path) -> None:
    repo_root = get_repo_root()
    registry = get_node_registry(repo_root, include_composite=True)
    node_library = registry.get_library()
    parser = GraphCodeParser(repo_root, node_library=node_library, strict=True)

    graph_code = '''
"""
graph_id: graph_nested_match_break_in_loop
graph_name: 嵌套解析_多分支_循环内break
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 嵌套解析_多分支_循环内break:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        计数: "整数" = 0
        for 轮次 in range(3):
            match 轮次:
                case 0:
                    break
                case _:
                    计数: "整数" = 计数 + 1
            设置节点图变量(self.game, 变量名="调试_计数", 变量值=计数, 是否触发事件=False)
'''
    source_file = tmp_path / "graph_nested_match_break_in_loop.py"
    source_file.write_text(graph_code, encoding="utf-8")

    model_a, _ = parser.parse_file(source_file)
    code = generate_graph_code_from_model(model_a, node_library=node_library)
    generated_file = tmp_path / "reverse_nested_match_break_in_loop.py"
    generated_file.write_text(code, encoding="utf-8")

    _roundtrip_and_assert_equal(model_a=model_a, generated_path=generated_file, parser=parser)


def test_reverse_roundtrip_template_composite_match_multiexit(tmp_path: Path) -> None:
    """复合节点多流程出口：要求生成 `match self.<实例>.<入口>(...)` 语法以保持端口级流程语义一致。"""
    repo_root = get_repo_root()

    # 复合节点 NodeDef 的发现范围受 active_package_id 影响：这里显式切换到“示例项目模板”作用域，
    # 确保节点库包含 `复合节点/多分支_示例_类格式`。
    from engine.utils.runtime_scope import set_active_package_id
    from engine.nodes.node_registry import clear_all_registries_for_tests

    set_active_package_id("示例项目模板")
    clear_all_registries_for_tests()
    try:
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
            / "模板示例_多分支_复合节点用法.py"
        )
        assert source_file.is_file()

        parser = GraphCodeParser(repo_root, node_library=node_library, strict=True)
        model_a, _ = parser.parse_file(source_file)

        code = generate_graph_code_from_model(model_a, node_library=node_library)
        generated_file = tmp_path / "reverse_composite_match_multiexit.py"
        generated_file.write_text(code, encoding="utf-8")

        _roundtrip_and_assert_equal(model_a=model_a, generated_path=generated_file, parser=parser)
    finally:
        # 还原默认作用域，避免影响同进程内后续测试
        set_active_package_id(None)
        clear_all_registries_for_tests()


def test_reverse_roundtrip_template_composite_default_exit_linear(tmp_path: Path) -> None:
    """复合节点存在多个流程出口，但仅通过“默认出口（首个流程输出）”接续：允许不生成 match。"""
    repo_root = get_repo_root()

    # 复合节点 NodeDef 的发现范围受 active_package_id 影响：这里显式切换到“示例项目模板”作用域，
    # 确保节点库包含 `复合节点/多分支_示例_类格式`。
    from engine.utils.runtime_scope import set_active_package_id
    from engine.nodes.node_registry import clear_all_registries_for_tests

    set_active_package_id("示例项目模板")
    clear_all_registries_for_tests()
    try:
        registry = get_node_registry(repo_root, include_composite=True)
        node_library = registry.get_library()
        parser = GraphCodeParser(repo_root, node_library=node_library, strict=True)

        graph_code = '''
"""
graph_id: graph_composite_default_exit_linear
graph_name: 反向生成_复合节点_默认出口线性接续
graph_type: server
"""

from __future__ import annotations

from _prelude import *  # noqa: F401,F403


class 反向生成_复合节点_默认出口线性接续:
    def __init__(self, game, owner_entity):
        self.game = game
        self.owner_entity = owner_entity

        self.多分支 = 多分支_示例_类格式(game, owner_entity)

    def on_实体创建时(self, 事件源实体, 事件源GUID):
        self.多分支.按整数多分支(分支值=0)
        设置节点图变量(self.game, 变量名="调试_标记", 变量值=0, 是否触发事件=False)
'''
        source_file = tmp_path / "graph_composite_default_exit_linear.py"
        source_file.write_text(graph_code, encoding="utf-8")

        model_a, _ = parser.parse_file(source_file)
        code = generate_graph_code_from_model(model_a, node_library=node_library)
        generated_file = tmp_path / "reverse_composite_default_exit_linear.py"
        generated_file.write_text(code, encoding="utf-8")

        _roundtrip_and_assert_equal(model_a=model_a, generated_path=generated_file, parser=parser)
    finally:
        # 还原默认作用域，避免影响同进程内后续测试
        set_active_package_id(None)
        clear_all_registries_for_tests()


