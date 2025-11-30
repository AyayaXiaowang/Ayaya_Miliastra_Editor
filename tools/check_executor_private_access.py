# -*- coding: utf-8 -*-
"""
静态检查：禁止跨模块直接访问执行器的私有方法（executor._ensure_* / *_executor._xxx 等）。

规则摘要：
- 仅允许在类内部通过 self / cls 访问私有成员（例如 self._ensure_program_point_visible）；
- 当变量名为 executor / *_executor 或属性链以 *.executor 结尾时，
  禁止继续访问以下划线开头的属性（例如 executor._ensure_xxx、shared_executor._reset_view_state）；
- 允许任意模块通过 ViewportController / EditorExecutorProtocol / EditorExecutorWithViewport
  等协议或公开方法访问执行与视口能力。

用法：
    python tools/check_executor_private_access.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


# 将工程根目录加入 sys.path，便于直接导入 engine/* 工具。
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from engine.utils.logging.console_sanitizer import ascii_safe_print


safe_print = ascii_safe_print


class ExecutorPrivateAccessVisitor(ast.NodeVisitor):
    """扫描单个模块中对执行器私有方法的访问。"""

    def __init__(self, filename: Path) -> None:
        self.filename = filename
        self.violations: list[tuple[int, str, str]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        attr_name = node.attr
        if not isinstance(attr_name, str):
            self.generic_visit(node)
            return
        if not attr_name.startswith("_"):
            self.generic_visit(node)
            return

        offender: str | None = None

        # 形如 executor._ensure_xxx / shared_executor._reset_view_state
        if isinstance(node.value, ast.Name):
            base_name = node.value.id
            if base_name not in ("self", "cls") and (
                base_name == "executor" or base_name.endswith("executor")
            ):
                offender = base_name

        # 形如 self.executor._ensure_xxx / ctx.shared_executor._reset_xxx
        elif isinstance(node.value, ast.Attribute):
            inner_attr = node.value.attr
            if isinstance(inner_attr, str) and (
                inner_attr == "executor" or inner_attr.endswith("executor")
            ):
                offender = inner_attr

        if offender is not None:
            self.violations.append((node.lineno, offender, attr_name))

        self.generic_visit(node)


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    visitor = ExecutorPrivateAccessVisitor(path)
    visitor.visit(tree)
    return visitor.violations


def iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if path.is_file():
            files.append(path)
    return files


def main() -> None:
    workspace_root = Path(__file__).resolve().parents[1]
    all_files = iter_python_files(workspace_root)

    has_violation = False

    safe_print("=" * 80)
    safe_print("Static Check: executor private access")
    safe_print("=" * 80)
    safe_print("")

    for path in all_files:
        relative = path.relative_to(workspace_root)
        violations = scan_file(path)
        if not violations:
            continue
        has_violation = True
        safe_print(f"[X] {relative}")
        for lineno, owner, attr in violations:
            safe_print(
                f"    line {lineno}: {owner}.{attr}  # 禁止跨模块访问执行器私有成员"
            )

    safe_print("")
    if has_violation:
        safe_print("[X] 检测到以上对执行器私有成员的跨模块访问，请改为通过协议或公开方法调用。")
        sys.exit(1)

    safe_print("[OK] 未发现对执行器私有成员的跨模块访问。")
    sys.exit(0)


if __name__ == "__main__":
    main()


