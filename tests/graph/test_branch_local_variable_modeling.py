from __future__ import annotations

from engine.graph.graph_code_parser import GraphCodeParser
from tests._helpers.project_paths import get_repo_root


def _find_line_number_in_file(*, file_path, needle: str) -> int:
    needle_text = str(needle).strip()
    if needle_text == "":
        raise ValueError("needle must be non-empty")
    text = file_path.read_text(encoding="utf-8-sig")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.strip() == needle_text:
            return line_number
    raise ValueError(f"needle not found in {file_path}: {needle_text}")


def test_template_branch_assign_models_local_var_merge() -> None:
    """回归：if-else 分支合流变量赋值应正确建模为【获取/设置局部变量】。

    预期行为：
    - 分支前的初始化赋值应建模为【获取局部变量】（提供句柄）；
    - if 与 else 两条分支内的赋值应建模为【设置局部变量】（写回到同一句柄）。

    背景：
    - 分支体解析会对 VarEnv 做 snapshot/restore；
    - 若未在分支前建模句柄，容易出现“句柄在某个分支内首次创建、另一分支只能引用该句柄”的错误建模，
      进而让 UI 图结构与源码语义不一致。
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
        / "测试_局部变量_分支设置.py"
    )

    parser = GraphCodeParser(project_root)
    model, _meta = parser.parse_file(template_path)

    get_nodes = [
        node for node in model.nodes.values() if getattr(node, "title", "") == "获取局部变量"
    ]
    set_nodes = [
        node for node in model.nodes.values() if getattr(node, "title", "") == "设置局部变量"
    ]

    assert len(get_nodes) == 1
    assert len(set_nodes) == 2

    # 源码行号锚定：便于未来模板变更时快速定位到 IR 行为漂移点
    get_lines = sorted({int(n.source_lineno) for n in get_nodes if getattr(n, "source_lineno", 0)})
    set_lines = sorted({int(n.source_lineno) for n in set_nodes if getattr(n, "source_lineno", 0)})
    init_line = _find_line_number_in_file(file_path=template_path, needle='当前结果值: "整数" = 0')
    assign_a_line = _find_line_number_in_file(file_path=template_path, needle='当前结果值: "整数" = 10')
    assign_b_line = _find_line_number_in_file(file_path=template_path, needle='当前结果值: "整数" = 20')
    assert get_lines == [init_line]
    assert set_lines == sorted([assign_a_line, assign_b_line])


