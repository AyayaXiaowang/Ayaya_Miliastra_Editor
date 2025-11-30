# -*- coding: utf-8 -*-
"""
扫描仓库内超过阈值行数的 Python 模块，并输出可读的拆分建议。

使用方式：
    python -X utf8 tools/find_large_modules.py --threshold 800
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


@dataclass
class ModuleStatistic:
    file_path: Path
    line_count: int
    function_count: int
    class_count: int
    average_function_length: float
    suggestion: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "列出超过给定行数阈值的 Python 文件，"
            "并为后续的拆分与优化提供参考指标。"
        )
    )
    parser.add_argument(
        "--root",
        default=".",
        help="扫描起点目录，默认是当前仓库根目录。",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=800,
        help="输出文件的最小行数阈值。",
    )
    parser.add_argument(
        "--extensions",
        default=".py,.pyw",
        help="逗号分隔的扩展名列表，仅匹配这些文件。",
    )
    parser.add_argument(
        "--ignore",
        default=".git,.cursor,.pytest_cache,__pycache__,build,dist",
        help="逗号分隔的目录名称，匹配到将被整体忽略。",
    )
    return parser.parse_args()


def should_ignore(directory_name: str, ignored_names: Sequence[str]) -> bool:
    return any(directory_name == ignored_name for ignored_name in ignored_names)


def iter_python_files(
    root_path: Path,
    extensions: Sequence[str],
    ignored_names: Sequence[str],
) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [
            directory_name
            for directory_name in dirnames
            if not should_ignore(directory_name, ignored_names)
        ]
        current_dir = Path(dirpath)
        for filename in filenames:
            file_path = current_dir / filename
            if file_path.suffix not in extensions:
                continue
            if any(ignored_name in file_path.parts for ignored_name in ignored_names):
                continue
            yield file_path


def count_lines(file_path: Path) -> int:
    with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for _ in handle)


def calculate_average_length(lengths: Sequence[int]) -> float:
    if not lengths:
        return 0.0
    return sum(lengths) / len(lengths)


def analyze_module(file_path: Path) -> ModuleStatistic:
    source_lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    line_count = len(source_lines)

    function_start_indices = [
        index for index, line in enumerate(source_lines)
        if line.lstrip().startswith("def ")
    ]
    class_start_indices = [
        index for index, line in enumerate(source_lines)
        if line.lstrip().startswith("class ")
    ]

    function_lengths: List[int] = []
    for position, start_index in enumerate(function_start_indices):
        if position + 1 < len(function_start_indices):
            end_index = function_start_indices[position + 1]
        else:
            end_index = line_count
        function_lengths.append(max(end_index - start_index, 1))

    average_length = calculate_average_length(function_lengths)

    return ModuleStatistic(
        file_path=file_path,
        line_count=line_count,
        function_count=len(function_start_indices),
        class_count=len(class_start_indices),
        average_function_length=average_length,
        suggestion=build_suggestion(
            file_path=file_path,
            function_count=len(function_start_indices),
            class_count=len(class_start_indices),
            average_function_length=average_length,
        ),
    )


def build_suggestion(
    file_path: Path,
    function_count: int,
    class_count: int,
    average_function_length: float,
) -> str:
    normalized_path = str(file_path).replace("\\", "/")
    suggestion_parts: List[str] = []

    if "app/ui" in normalized_path:
        suggestion_parts.append("按界面组件/交互职责拆分子模块")
    if "app/models" in normalized_path:
        suggestion_parts.append("拆分为独立的数据模型与生成策略文件")
    if "engine/layout" in normalized_path:
        suggestion_parts.append("将布局算法步骤拆成独立的求解器与工具模块")
    if "plugins/nodes" in normalized_path:
        suggestion_parts.append("按照节点类别拆分注册表，减少单文件常量")
    if "tools/" in normalized_path:
        suggestion_parts.append("提取通用扫描逻辑为库模块，脚本仅保留 CLI 入口")

    if class_count > 8:
        suggestion_parts.append("依据类角色拆成多个模块，便于按领域维护")
    if function_count > 25:
        suggestion_parts.append("将重复的业务流程抽取到共享工具模块")
    if average_function_length > 80:
        suggestion_parts.append("拆分超长函数为更细粒度的管线步骤")
    if not suggestion_parts:
        suggestion_parts.append("按功能边界拆分，保持每个文件只承担单一职责")

    return "；".join(suggestion_parts)


def format_report(statistics: Sequence[ModuleStatistic]) -> str:
    if not statistics:
        return "未找到超过阈值的文件。"

    report_lines: List[str] = []
    header = (
        f"{'Lines':>8}  {'Functions':>9}  {'Classes':>8}  "
        f"{'AvgFunc':>7}  File"
    )
    report_lines.append(header)
    report_lines.append("-" * len(header))

    for statistic in statistics:
        line = (
            f"{statistic.line_count:8d}  "
            f"{statistic.function_count:9d}  "
            f"{statistic.class_count:8d}  "
            f"{statistic.average_function_length:7.1f}  "
            f"{statistic.file_path.as_posix()}"
        )
        report_lines.append(line)
        report_lines.append(f"    建议：{statistic.suggestion}")

    return "\n".join(report_lines)


def main() -> None:
    arguments = parse_arguments()
    root_path = Path(arguments.root).resolve()
    extensions = tuple(ext if ext.startswith(".") else f".{ext}" for ext in arguments.extensions.split(","))
    ignored_names = tuple(name.strip() for name in arguments.ignore.split(",") if name.strip())

    candidate_files = (
        file_path
        for file_path in iter_python_files(root_path, extensions, ignored_names)
        if file_path.is_file()
    )

    statistics: List[ModuleStatistic] = []
    for file_path in candidate_files:
        if count_lines(file_path) <= arguments.threshold:
            continue
        statistics.append(analyze_module(file_path))

    statistics.sort(key=lambda item: item.line_count, reverse=True)
    print(format_report(statistics))


if __name__ == "__main__":
    main()

