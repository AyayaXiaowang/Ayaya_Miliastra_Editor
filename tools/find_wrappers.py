# -*- coding: utf-8 -*-
"""
薄包装函数扫描器（只读）

用途：扫描项目中的 Python 源码，定位下面几类“仅转发调用”的函数：
- 仅一条语句：return foo(...)
- 仅一条语句：foo(...)（无返回）
- 两条语句：tmp = foo(...); return tmp

判定标准（宽松）：函数体只包含一次调用，不做额外计算；
参数转发以“名称直接转发”为主（如 a->a, b->b），允许存在部分参数未转发。

注意：本脚本不改写源码，仅打印候选位置，便于人工确认与优化。
在模块级别满足 def foo(*args, **kwargs): return bar(*args, **kwargs) 的场景，
通常可以将 foo 直接替换为别名：foo = bar。
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


class WrapperCandidate(ast.AST):
    def __init__(
        self,
        file_path: Path,
        qualname: str,
        line_no: int,
        wrapper_kind: str,
        target_repr: str,
        can_alias: bool,
    ) -> None:
        self.file_path = file_path
        self.qualname = qualname
        self.line_no = line_no
        self.wrapper_kind = wrapper_kind
        self.target_repr = target_repr
        self.can_alias = can_alias

    def to_row(self) -> str:
        alias_flag = "yes" if self.can_alias else "no"
        return f"{self.file_path}:{self.line_no}\t{self.qualname}\t{self.wrapper_kind}\t{self.target_repr}\taliasable={alias_flag}"


def read_text_utf8(path: Path) -> str:
    # 兼容含 BOM 的 UTF-8 文件
    return path.read_text(encoding="utf-8-sig")


def is_name_forward(value: ast.AST, param_names: set[str]) -> bool:
    # 仅接受直接参数名或 *args/**kwargs 这种透明转发
    if isinstance(value, ast.Name):
        return value.id in param_names
    if isinstance(value, ast.Starred) and isinstance(value.value, ast.Name):
        return value.value.id in param_names
    # 关键字参数：接收在上层处理
    return False


def call_is_simple_forward(call: ast.Call, param_names: List[str]) -> Tuple[bool, str, bool]:
    """判断调用是否是“简单转发”。

    返回：(是否简单转发, 目标可读文本, 是否可做别名替换)
    可别名替换的额外条件：
    - 调用对象为 ast.Name（模块级别函数）
    - 仅使用 *args/**kwargs 或按名直接转发（不引入 self. / cls. / 属性调用）
    """
    target_repr = ast.unparse(call.func) if hasattr(ast, "unparse") else getattr(call.func, "id", str(call.func))
    param_set = set(param_names)

    # 位置参数与可变参数
    for arg in call.args:
        if not is_name_forward(arg, param_set):
            return False, target_repr, False

    # 关键字参数
    for kw in call.keywords or []:
        if kw.arg is None:
            # **kwargs 场景
            if not (isinstance(kw.value, ast.Name) and kw.value.id in param_set):
                return False, target_repr, False
            continue
        if not (isinstance(kw.value, ast.Name) and kw.value.id in param_set):
            return False, target_repr, False

    # 简单：未做任何计算、取属性/下标等
    can_alias = isinstance(call.func, ast.Name)
    return True, target_repr, can_alias


def function_params(fn: ast.FunctionDef) -> List[str]:
    names: List[str] = []
    for a in fn.args.args:
        names.append(a.arg)
    if fn.args.vararg is not None:
        names.append(fn.args.vararg.arg)
    for a in fn.args.kwonlyargs:
        names.append(a.arg)
    if fn.args.kwarg is not None:
        names.append(fn.args.kwarg.arg)
    return names


def scan_file(file_path: Path) -> List[WrapperCandidate]:
    text = read_text_utf8(file_path)
    tree = ast.parse(text, filename=str(file_path))

    candidates: List[WrapperCandidate] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.qual_stack: List[str] = []

        def _qualname(self) -> str:
            return ".".join(self.qual_stack)

        def visit_ClassDef(self, node: ast.ClassDef) -> Any:
            self.qual_stack.append(node.name)
            self.generic_visit(node)
            self.qual_stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
            self.qual_stack.append(node.name)
            params = function_params(node)
            body = [b for b in node.body if not isinstance(b, ast.Pass)]

            # 1) 单语句：return foo(...)
            if len(body) == 1 and isinstance(body[0], ast.Return) and isinstance(body[0].value, ast.Call):
                ok, target, can_alias = call_is_simple_forward(body[0].value, params)
                if ok:
                    candidates.append(
                        WrapperCandidate(
                            file_path=file_path,
                            qualname=self._qualname(),
                            line_no=node.lineno,
                            wrapper_kind="return-call",
                            target_repr=target,
                            can_alias=can_alias and len(self.qual_stack) == 1,  # 仅模块级可安全别名
                        )
                    )

            # 2) 单语句：foo(...)（无返回）
            elif len(body) == 1 and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Call):
                ok, target, can_alias = call_is_simple_forward(body[0].value, params)
                if ok:
                    candidates.append(
                        WrapperCandidate(
                            file_path=file_path,
                            qualname=self._qualname(),
                            line_no=node.lineno,
                            wrapper_kind="expr-call",
                            target_repr=target,
                            can_alias=False,  # 无返回的转发通常不做别名
                        )
                    )

            # 3) 两语句：tmp = foo(...); return tmp
            elif (
                len(body) == 2
                and isinstance(body[0], ast.Assign)
                and isinstance(body[0].value, ast.Call)
                and isinstance(body[1], ast.Return)
                and isinstance(body[1].value, ast.Name)
            ):
                temp_names: List[str] = []
                for t in body[0].targets:
                    if isinstance(t, ast.Name):
                        temp_names.append(t.id)
                if len(temp_names) == 1 and temp_names[0] == body[1].value.id:
                    ok, target, can_alias = call_is_simple_forward(body[0].value, params)
                    if ok:
                        candidates.append(
                            WrapperCandidate(
                                file_path=file_path,
                                qualname=self._qualname(),
                                line_no=node.lineno,
                                wrapper_kind="assign-then-return",
                                target_repr=target,
                                can_alias=False,
                            )
                        )
            self.qual_stack.pop()

    Visitor().visit(tree)
    return candidates


def iter_workspace_py_files(workspace_root: Path, include_snapshots: bool) -> Iterable[Path]:
    """
    统一的“工作树 vs 快照树”遍历约定：
    - 默认仅扫描 engine/, plugins/, app/, assets/, tools/, tests/ 这些工作目录。
    - docs/snapshots 及其他包含 "snapshots" 片段的路径视为快照树，默认跳过。
    """
    workspace_dirs = ["engine", "plugins", "app", "assets", "tools", "tests"]
    for relative_name in workspace_dirs:
        directory_path = workspace_root / relative_name
        if not directory_path.exists():
            continue
        for python_path in directory_path.rglob("*.py"):
            if "__pycache__" in python_path.parts:
                continue
            if not include_snapshots and "snapshots" in python_path.parts:
                continue
            yield python_path


def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description=(
            "扫描工作树中的薄包装函数（默认忽略 docs/snapshots 等快照目录）。"
        )
    )
    parser.add_argument(
        "--include-snapshots",
        action="store_true",
        help="同时扫描包含 'snapshots' 片段的快照目录（默认不扫描）。",
    )
    arguments = parser.parse_args()

    all_py_files: List[Path] = []
    for python_file in sorted(iter_workspace_py_files(workspace_root, arguments.include_snapshots)):
        posix_path = python_file.as_posix()
        # 跳过非 Python DSL 或语法不标准目录
        if "/core/configs/" in posix_path:
            continue
        if "/node_definitions/" in posix_path:
            continue
        if "assets/资源库/节点图/" in posix_path:
            continue
        all_py_files.append(python_file)

    all_candidates: List[WrapperCandidate] = []
    for py_file in all_py_files:
        # 忽略本工具自身
        if py_file.name == Path(__file__).name:
            continue
        cs = scan_file(py_file)
        all_candidates.extend(cs)

    # 汇总输出
    if not all_candidates:
        print("No thin wrapper candidates found.")
        return

    print("file:line\tqualname\tkind\ttarget\taliasable")
    for c in all_candidates:
        print(c.to_row())

    # 建议：可别名替换的模块级函数
    aliasables = [c for c in all_candidates if c.can_alias]
    if aliasables:
        print("\nAliasable (suggest replace `def f(...): return g(...)` with `f = g`):")
        for c in aliasables:
            print(f"- {c.file_path}:{c.line_no} -> {c.qualname} = {c.target_repr}")


if __name__ == "__main__":
    main()
