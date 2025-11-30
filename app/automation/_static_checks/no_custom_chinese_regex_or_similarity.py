#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性静态扫描（自动化目录）：
- 禁止在运行路径手写正则匹配中文（应统一走 executor._extract_chinese → node_detection.extract_chinese → ocr_utils.extract_chinese）
- 禁止在运行路径自实现相似度（应统一走 core.utilities.text_similarity.chinese_similar）
发现违规时退出码为 1。
"""

from __future__ import annotations

import os
import re
import sys
from typing import Tuple

from .utils import iter_python_files


_REGEX_CHINESE_PATTERNS = [
    r"\\u4e00-\\u9fff",  # Unicode 范围
    r"[一-龥]",          # 常见区间
]

_SIMILARITY_HINTS = [
    r"\bdifflib\.SequenceMatcher\b",
    r"\brapidfuzz\b",
    r"\bfuzzywuzzy\b",
    r"\bLevenshtein\b",
    r"\bsimilarit(y|ies)\b",
]


def scan_file(filepath: str) -> list[Tuple[int, str]]:
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    findings: list[Tuple[int, str]] = []
    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        # 跳过注释行
        if line.startswith("#"):
            continue
        # 中文正则嫌疑
        if "re." in line:
            for pat in _REGEX_CHINESE_PATTERNS:
                if re.search(pat, line):
                    findings.append((idx, "疑似自写中文正则匹配，请改用统一中文提取入口"))
                    break
        # 相似度嫌疑
        for hint in _SIMILARITY_HINTS:
            if re.search(hint, line, flags=re.IGNORECASE):
                findings.append((idx, "疑似自实现相似度，请改用 core.utilities.text_similarity.chinese_similar"))
                break
    return findings


def main() -> int:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    violations = 0
    for file_path in iter_py_files(root_dir):
        rel = os.path.relpath(file_path, root_dir)
        results = scan_file(file_path)
        if results:
            for ln, msg in results:
                print(f"[中文规则统一] {rel}:{int(ln)} {msg}", file=sys.stderr)
            violations += len(results)
    if violations > 0:
        print(f"共发现 {violations} 处可能违反“中文提取/相似度统一路径”的代码。", file=sys.stderr)
        return 1
    print("扫描通过：未发现自写中文正则或相似度实现。")
    return 0


if __name__ == "__main__":
    sys.exit(main())


