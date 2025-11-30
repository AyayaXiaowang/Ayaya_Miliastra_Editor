#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性静态扫描：禁止在自动化目录内直接导入 `tools.vision_bridge`。

说明：
- 视觉识别能力应统一通过 `app.automation.vision` 访问；
- `tools.vision_bridge` 模块已移除，本检查仅用于防止后续重新引入并被自动化层直接依赖；
- 发现违规时退出码为 1。
"""

from __future__ import annotations

import ast
import os
import sys
from typing import Tuple

from .utils import iter_python_files


def find_violations(file_path: str) -> list[Tuple[int, str]]:
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source, filename=file_path)

    lines: list[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if isinstance(node.module, str) and node.module.startswith("tools.vision_bridge"):
                lines.append((node.lineno or 0, f"from {node.module} import ..."))
        if isinstance(node, ast.Import):
            for alias in node.names:
                if isinstance(alias.name, str) and alias.name.startswith("tools.vision_bridge"):
                    lines.append((node.lineno or 0, f"import {alias.name}"))
    return lines


def main() -> int:
    # 自动化根目录
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    allow_path = os.path.normpath(os.path.join(root_dir, "vision.py"))

    violations_total = 0
    for file_path in iter_python_files(root_dir):
        # 仅自动化目录内扫描；允许门面 vision.py
        if os.path.normpath(file_path) == allow_path:
            continue
        findings = find_violations(file_path)
        if findings:
            rel = os.path.relpath(file_path, root_dir)
            for line_no, stmt in findings:
                print(f"[违反识别门面唯一入口] {rel}:{int(line_no)} 发现直依：{stmt}", file=sys.stderr)
            violations_total += len(findings)

    if violations_total > 0:
        print(f"共发现 {violations_total} 处违反 '禁止直接导入 tools.vision_bridge' 的代码。", file=sys.stderr)
        return 1
    print("扫描通过：未发现对 tools.vision_bridge 的直接导入。")
    return 0


if __name__ == "__main__":
    sys.exit(main())


