# -*- coding: utf-8 -*-
"""
静态扫描工具：在 core/automation 下查找 capture_window/capture_region 的使用点，
检查其后 N 行内是否存在 _emit_visual(...) 或 visual_callback(...) 的调用；若无，则打印提醒。

用法：
    python tools/scan_capture_emit.py --window 30

说明：
    - 仅为开发提醒，不修改源码；
    - 路径基于项目根目录运行；
    - 规则简单：字符串级别查找，可能有少量误报/漏报。
"""

from __future__ import annotations

import argparse
import os
import sys


def iter_py_files(root_dir: str):
    for base, _dirs, files in os.walk(root_dir):
        for fn in files:
            if fn.endswith('.py'):
                yield os.path.join(base, fn)


def scan_file(filepath: str, window: int) -> list[tuple[int, str]]:
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    findings: list[tuple[int, str]] = []
    n = len(lines)
    for i, line in enumerate(lines):
        if 'capture_window(' in line or 'capture_region(' in line:
            end = min(n, i + 1 + int(window))
            region = ''.join(lines[i + 1:end])
            if ('_emit_visual(' not in region) and ('visual_callback(' not in region):
                snippet = line.strip()
                findings.append((i + 1, snippet))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', type=int, default=30, help='向后搜索的行数窗口，默认 30')
    args = parser.parse_args()
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_root = os.path.join(project_root, 'core', 'automation')
    if not os.path.isdir(target_root):
        print(f"✗ 目录不存在: {target_root}")
        return 1
    total = 0
    warned = 0
    for path in iter_py_files(target_root):
        findings = scan_file(path, int(args.window))
        if findings:
            print(f"[WARN] {os.path.relpath(path, project_root)} 存在可能缺少 _emit_visual 的捕获用例：")
            for lineno, snippet in findings:
                print(f"  - L{lineno}: {snippet}")
            warned += len(findings)
        total += 1
    print(f"扫描完成：文件 {total} 个，疑似缺失 {warned} 处。窗口={int(args.window)}行。")
    return 0


if __name__ == '__main__':
    sys.exit(main())


