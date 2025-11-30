from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Set


def find_node_functions_in_file(py_path: Path) -> List[str]:
    source = py_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_path))
    function_names: List[str] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        has_node_spec = False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "node_spec":
                has_node_spec = True
                break
        if has_node_spec:
            function_names.append(node.name)
    return function_names


def collect_all_server_node_functions(workspace_root: Path) -> List[str]:
    server_root = workspace_root / "node_implementations" / "server"
    if not server_root.exists():
        raise FileNotFoundError(f"server impl dir not found: {server_root}")

    function_name_set: Set[str] = set()
    for py_file in server_root.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        # 跳过 shared 辅助模块
        if (server_root / "shared") in py_file.parents:
            continue
        names = find_node_functions_in_file(py_file)
        for name in names:
            function_name_set.add(name)

    # 稳定排序（按 Unicode 码点排序），便于审阅
    return sorted(function_name_set)


def generate_pyi_content(function_names: List[str]) -> str:
    header_lines = [
        "from __future__ import annotations",
        "from typing import Any",
        "",
        "# 本文件为类型桩（stub），仅用于静态类型检查器（如 Pyright）解析",
        "# 运行时不生效，不参与实际导入逻辑",
        "",
    ]
    body_lines: List[str] = []
    for fn in function_names:
        body_lines.append(f"def {fn}(*args: Any, **kwargs: Any) -> Any: ...")
    body_lines.append("")
    # 显式导出列表，确保 from node_implementations.server import * 可被类型检查器识别
    all_items = ", ".join([f'\"{fn}\"' for fn in function_names])
    body_lines.append(f"__all__ = [{all_items}]")
    body_lines.append("")
    return "\n".join(header_lines + body_lines)


def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    function_names = collect_all_server_node_functions(workspace_root)
    target_path = workspace_root / "node_implementations" / "server" / "__init__.pyi"
    content = generate_pyi_content(function_names)
    target_path.write_text(content, encoding="utf-8")
    print(f"生成完成: {target_path}（函数数量: {len(function_names)}）")


if __name__ == "__main__":
    main()


