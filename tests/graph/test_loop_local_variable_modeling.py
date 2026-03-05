from __future__ import annotations

from pathlib import Path

from engine.graph.graph_code_parser import GraphCodeParser
from tests._helpers.project_paths import get_repo_root


def _find_line_number_in_file(*, file_path: Path, needle: str) -> int:
    needle_text = str(needle).strip()
    if needle_text == "":
        raise ValueError("needle must be non-empty")
    text = file_path.read_text(encoding="utf-8-sig")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.strip() == needle_text:
            return line_number
    raise ValueError(f"needle not found in {file_path}: {needle_text}")


def test_template_loop_counter_models_local_var_updates() -> None:
    """回归：循环体内对变量的重复赋值应触发【获取/设置局部变量】建模。

    背景：
    - IR 在解析 for 循环体时会对 VarEnv 做 snapshot/restore；
    - 若循环体内更新的变量不走【设置局部变量】持久写回，循环后的使用会退回到旧映射，
      导致“累计/计数”类逻辑在节点图语义下失效。
    """
    project_root = get_repo_root()
    template_path = (
        project_root
        / "assets"
        / "资源库"
        / "项目存档"
        / "示例项目模板"
        / "节点图"
        / "server"
        / "实体节点图"
        / "测试"
        / "测试_局部变量计数.py"
    )

    parser = GraphCodeParser(project_root)
    model, _meta = parser.parse_file(template_path)

    get_nodes = [
        node for node in model.nodes.values() if getattr(node, "title", "") == "获取局部变量"
    ]
    set_nodes = [
        node for node in model.nodes.values() if getattr(node, "title", "") == "设置局部变量"
    ]

    # 该模板中有 2 个变量需要跨迭代更新：当前命中次数、最近一次摇值
    assert len(get_nodes) == 2
    assert len(set_nodes) == 2

    # 源码行号锚定：便于未来模板变更时快速定位到 IR 行为漂移点
    get_lines = sorted({int(n.source_lineno) for n in get_nodes if getattr(n, "source_lineno", 0)})
    set_lines = sorted({int(n.source_lineno) for n in set_nodes if getattr(n, "source_lineno", 0)})
    init_a_line = _find_line_number_in_file(file_path=template_path, needle='当前命中次数: "整数" = 0')
    init_b_line = _find_line_number_in_file(file_path=template_path, needle='最近一次摇值: "整数" = 0')
    set_a_line = _find_line_number_in_file(file_path=template_path, needle='最近一次摇值: "整数" = random.randint(0, 2)')
    set_b_line = _find_line_number_in_file(file_path=template_path, needle='当前命中次数 += 1')
    assert get_lines == sorted([init_a_line, init_b_line])
    assert set_lines == sorted([set_a_line, set_b_line])


