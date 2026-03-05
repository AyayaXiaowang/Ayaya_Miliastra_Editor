"""
节点图代码严格验证器（引擎侧统一入口）

目标：
- 为“类结构节点图(.py)”提供按文件粒度的静态规则校验入口；
- 供 runtime/UI/CLI 等上层复用，避免上层各自实现校验分发与聚合。

说明：
- 校验规则与管线由 `engine.validate.api.validate_files` 提供；
- 本模块仅负责：运行期开关、按文件缓存、错误/警告聚合与便捷 API；
  收集/格式化等复杂逻辑拆分至 `engine.validate.node_graph_validation_utils`。
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import List, Set, Tuple

from .node_graph_validation_utils import (
    collect_issue_messages_for_files as _collect_issues_for_files,
    format_validate_file_report,
    strict_parse_file,
)


class NodeGraphValidationError(Exception):
    """节点图代码规范错误"""


class NodeGraphValidator:
    """节点图验证器：基于文件粒度委托引擎进行校验。"""

    def __init__(self, strict: bool = True):
        self.strict = strict
        self.errors: List[str] = []
        self.warnings: List[str] = []
        # 已完成校验的文件绝对路径集合：同一节点图文件只在当前进程中校验一次
        self.validated_files: Set[str] = set()

    def validate_class(self, node_graph_class) -> None:
        """基于所属文件调用引擎校验并在严格模式下抛错。"""
        source_file = inspect.getsourcefile(node_graph_class)
        if not isinstance(source_file, str) or len(source_file) == 0:
            return

        absolute_target = str(Path(source_file).resolve())
        # 同一文件在当前进程中仅校验一次，避免重复解析与规则执行
        if absolute_target in self.validated_files:
            return

        # 每次针对单个文件校验前清空累计问题列表
        self.errors = []
        self.warnings = []

        issues = _collect_issues_for_files([Path(source_file)])
        file_issues = issues.get(absolute_target, {"errors": [], "warnings": []})
        self.errors = file_issues["errors"]
        self.warnings = file_issues["warnings"]
        self.validated_files.add(absolute_target)

        if self.errors and self.strict:
            raise NodeGraphValidationError("\n".join(f"[X] {message}" for message in self.errors))


_global_validator = NodeGraphValidator(strict=True)


def validate_node_graph(node_graph_class):
    """验证节点图类（装饰器或直接调用）

    用法1（装饰器）：
    ```python
    @validate_node_graph
    class 我的节点图:
        ...
    ```

    用法2（直接调用）：
    ```python
    class 我的节点图:
        ...

    validate_node_graph(我的节点图)
    ```

    Args:
        node_graph_class: 节点图类

    Returns:
        原始类（用于装饰器）

    Raises:
        NodeGraphValidationError: 如果发现规范错误
    """
    _global_validator.validate_class(node_graph_class)
    return node_graph_class


def validate_file(file_path: Path) -> Tuple[bool, List[str], List[str]]:
    """验证单个节点图文件。

    Args:
        file_path: 节点图文件路径

    Returns:
        (是否通过, 错误列表, 警告列表)
    """
    absolute_target = str(file_path.resolve())
    issues = _collect_issues_for_files([file_path])
    file_issues = issues.get(absolute_target, {"errors": [], "warnings": []})
    errors = file_issues["errors"]
    warnings = file_issues["warnings"]
    return (len(errors) == 0), errors, warnings


