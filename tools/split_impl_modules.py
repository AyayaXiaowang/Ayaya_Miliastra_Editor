from __future__ import annotations

import ast
import io
import os
import re
from pathlib import Path
from typing import List, Tuple, Dict


WORKSPACE = Path(__file__).resolve().parents[1]
ROOT_IMPL = WORKSPACE / "node_implementations"
from engine.utils.name_utils import sanitize_node_filename as _sanitize_node_filename


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _module_scope_and_basename(py_file: Path) -> Tuple[str, str]:
    name = py_file.stem  # e.g., server_执行节点_impl
    scope = "server" if name.startswith("server_") else ("client" if name.startswith("client_") else "server")
    return scope, name


def _collect_source_segments(source: str, node_list: List[ast.AST]) -> str:
    # 拼接指定节点在原文件的源代码片段（保持注释/空行顺序）
    lines = source.splitlines(keepends=True)
    spans: List[Tuple[int, int]] = []
    for n in node_list:
        if hasattr(n, "lineno") and hasattr(n, "end_lineno"):
            spans.append((n.lineno, n.end_lineno))
    spans.sort()
    buf = io.StringIO()
    for start, end in spans:
        # ast 行号从1开始
        for i in range(start - 1, end):
            if 0 <= i < len(lines):
                buf.write(lines[i])
    return buf.getvalue()


def _is_node_spec_decorator(dec: ast.expr) -> bool:
    # 形如 @node_spec(...)
    return isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "node_spec"


def _get_node_spec_arg_str(call: ast.Call, arg_name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == arg_name and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _extract_functions(source: str) -> Tuple[List[ast.FunctionDef], List[ast.AST]]:
    tree = ast.parse(source)
    node_funcs: List[ast.FunctionDef] = []
    helpers: List[ast.AST] = []

    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            if any(_is_node_spec_decorator(d) for d in n.decorator_list):
                node_funcs.append(n)
            else:
                helpers.append(n)
        elif isinstance(n, (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Assign, ast.AnnAssign)):
            helpers.append(n)
        else:
            # 其余语句（常量字符串/表达式）也作为 helpers 保留（如模块级文档字符串）
            helpers.append(n)
    return node_funcs, helpers


def _sanitize_print_to_logger(text: str) -> str:
    # 将实现中的 print(...) 统一替换为 log_info(...)
    return re.sub(r"\bprint\(", "log_info(", text)


def split_module(py_file: Path) -> None:
    scope, base = _module_scope_and_basename(py_file)
    source = _read_text(py_file)
    node_funcs, helpers_nodes = _extract_functions(source)
    if not node_funcs:
        return

    # 写 helpers 模块
    helper_code = _collect_source_segments(source, helpers_nodes)
    helper_module_name = f"{base}_helpers"
    helper_path = ROOT_IMPL / "shared" / f"{helper_module_name}.py"
    if helper_code.strip():
        header = (
            "from __future__ import annotations\n\n"
        )
        _write_text(helper_path, header + helper_code)

    # 逐个函数生成目标文件
    for f in node_funcs:
        node_name = f.name
        node_spec_call = next((d for d in f.decorator_list if isinstance(d, ast.Call) and _is_node_spec_decorator(d)), None)
        category = _get_node_spec_arg_str(node_spec_call, "category") if isinstance(node_spec_call, ast.Call) else None
        name_from_spec = _get_node_spec_arg_str(node_spec_call, "name") if isinstance(node_spec_call, ast.Call) else None
        target_name = name_from_spec or node_name
        # 统一：实现文件名按“显示名→安全文件名”规则生成（无视斜杠，避免形成子目录）
        target_name = _sanitize_node_filename(target_name)
        if not category:
            raise ValueError(f"函数 {node_name} 缺少 @node_spec(category=...) 标注")

        target_dir = ROOT_IMPL / scope / category / ""
        target_path = target_dir / f"{target_name}.py"

        # 还原装饰器源代码（仅保留 @node_spec(...)）
        decorator_src = ""
        for d in f.decorator_list:
            if _is_node_spec_decorator(d):
                seg = ast.get_source_segment(source, d)
                if seg:
                    decorator_src = "@" + seg + "\n"
                break

        func_code = _collect_source_segments(source, [f])
        func_code = _sanitize_print_to_logger(func_code)

        header_lines = [
            "from __future__ import annotations\n",
            "from engine.nodes.node_spec import node_spec\n",
        ]
        if helper_code.strip():
            header_lines.append(f"from node_implementations.shared.{helper_module_name} import *\n")
        header_lines.append("from engine.utils.logging.logger import log_info\n\n")

        _write_text(target_path, "".join(header_lines) + decorator_src + func_code)


def main() -> None:
    candidates = [
        ROOT_IMPL / "server_事件节点_impl.py",
        ROOT_IMPL / "server_执行节点_impl.py",
        ROOT_IMPL / "server_查询节点_impl.py",
        ROOT_IMPL / "server_流程控制节点_impl.py",
        ROOT_IMPL / "server_运算节点_impl.py",
        ROOT_IMPL / "client_其他节点_impl.py",
        ROOT_IMPL / "client_执行节点_impl.py",
        ROOT_IMPL / "client_查询节点_impl.py",
        ROOT_IMPL / "client_流程控制节点_impl.py",
        ROOT_IMPL / "client_运算节点_impl.py",
    ]

    for f in candidates:
        if f.exists():
            split_module(f)

    # 可选：不自动删除旧文件，交由后续步骤处理


if __name__ == "__main__":
    main()


