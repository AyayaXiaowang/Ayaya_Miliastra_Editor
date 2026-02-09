"""
节点图代码严格验证器（引擎侧统一入口）

目标：
- 为“类结构节点图(.py)”提供按文件粒度的静态规则校验入口；
- 供 runtime/UI/CLI 等上层复用，避免上层各自实现校验分发与聚合。

说明：
- 校验规则与管线由 `engine.validate.api.validate_files` 提供；
- 本模块仅负责：运行期开关、按文件缓存、错误/警告聚合与便捷 API。
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Dict, List, Set, Tuple

from engine.utils.workspace import ensure_settings_workspace_root


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


def strict_parse_file(file_path: Path) -> None:
    """以解析器 strict fail-closed 模式解析单个节点图文件。

    用途：
    - 对齐资源加载/批量导出链路：GraphLoader/导出器通常使用 GraphCodeParser(strict=True)；
    - 在“工具校验/脚本自检”阶段提前发现 strict 下会拒绝解析的问题，避免批量导出中途失败。

    重要：
    - 本函数不捕获异常；strict 失败会抛出 GraphParseError（或更底层异常），由调用方决定如何展示。
    """
    resolved_target = file_path.resolve()
    workspace_root = ensure_settings_workspace_root(
        start_paths=[resolved_target, Path(__file__).resolve()],
        load_user_settings=False,
    )

    # 推断 active_package_id 并刷新作用域（与 validate_file/_collect_issues_for_files 对齐）
    from engine.utils.resource_library_layout import (
        PROJECT_ARCHIVE_LIBRARY_DIRNAME,
        SHARED_LIBRARY_DIRNAME,
        find_containing_resource_root,
    )
    from engine.utils.runtime_scope import get_active_package_id, set_active_package_id as set_runtime_active_package_id
    from engine.resources.definition_schema_view import set_default_definition_schema_view_active_package_id
    from engine.resources.level_variable_schema_view import set_default_level_variable_schema_view_active_package_id
    from engine.resources.ingame_save_template_schema_view import set_default_ingame_save_template_schema_view_active_package_id
    from engine.signal import invalidate_default_signal_repository_cache
    from engine.struct import invalidate_default_struct_repository_cache
    from engine.nodes.node_registry import get_node_registry

    resource_library_root = (workspace_root / "assets" / "资源库").resolve()
    resource_root = find_containing_resource_root(resource_library_root, resolved_target)
    if resource_root is None:
        active_package_id = get_active_package_id()
    elif resource_root.name == SHARED_LIBRARY_DIRNAME:
        active_package_id = None
    elif resource_root.parent.name == PROJECT_ARCHIVE_LIBRARY_DIRNAME:
        active_package_id = resource_root.name
    else:
        active_package_id = None

    set_runtime_active_package_id(active_package_id)
    set_default_definition_schema_view_active_package_id(active_package_id)
    set_default_level_variable_schema_view_active_package_id(active_package_id)
    set_default_ingame_save_template_schema_view_active_package_id(active_package_id)
    invalidate_default_signal_repository_cache()
    invalidate_default_struct_repository_cache()

    registry = get_node_registry(workspace_root, include_composite=True)
    registry.refresh()

    # 复合节点定义文件：严格模式应对齐“节点库构建/复合节点解析”链路，而不是 GraphCodeParser（其只支持节点图类结构）。
    from engine.nodes.composite_file_policy import is_composite_definition_file
    if is_composite_definition_file(resolved_target):
        from engine.graph.composite_code_parser import CompositeCodeParser
        from engine.nodes.advanced_node_features import convert_composite_to_node_def
        from engine.graph.graph_code_parser import GraphParseError
        from engine.type_registry import TYPE_GENERIC, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT

        # 复合节点解析需要基础节点库（以及可能的复合节点引用）；此处复用刷新后的注册表产物。
        node_library = registry.get_library()
        composite = CompositeCodeParser(
            node_library=node_library,
            verbose=False,
            workspace_path=workspace_root,
        ).parse_file(resolved_target)
        node_def = convert_composite_to_node_def(composite)

        generic_family = {TYPE_GENERIC, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT}
        bad: List[str] = []
        for port_name, type_text in (node_def.input_types or {}).items():
            if str(type_text) in generic_family:
                bad.append(f"- 复合节点输入端口类型未实例化（仍为泛型）：{node_def.name}.{port_name}({type_text})")
        for port_name, type_text in (node_def.output_types or {}).items():
            if str(type_text) in generic_family:
                bad.append(f"- 复合节点输出端口类型未实例化（仍为泛型）：{node_def.name}.{port_name}({type_text})")
        if bad:
            raise GraphParseError(
                "严格模式：复合节点引脚类型校验未通过，已拒绝解析：\n" + "\n".join(bad)
                + f"\n文件: {resolved_target}"
            )
        return

    from engine.graph.graph_code_parser import GraphCodeParser
    GraphCodeParser(workspace_root, strict=True).parse_file(resolved_target)


def format_validate_file_report(
    *,
    file_path: str | Path,
    passed: bool,
    errors: List[str],
    warnings: List[str],
) -> str:
    """格式化 `validate_file` 的文本报告（CLI/runtime 共用）。"""
    resolved_path = Path(file_path).resolve()

    lines: List[str] = []
    lines.append("=" * 80)
    lines.append("节点图自检:")
    lines.append(f"文件: {resolved_path}")
    lines.append(f"结果: {'通过' if passed else '未通过'}")

    if errors:
        lines.append("")
        lines.append("错误明细:")
        for index, message in enumerate(errors, start=1):
            lines.append(f"  [{index}] {message}")

    if warnings:
        lines.append("")
        lines.append("警告明细:")
        for index, message in enumerate(warnings, start=1):
            lines.append(f"  [{index}] {message}")

    lines.append("=" * 80)
    return "\n".join(lines)


def _collect_issues_for_files(target_files: List[Path]) -> Dict[str, Dict[str, List[str]]]:
    """运行底层验证并聚合成“文件 → (错误/警告列表)”的映射。"""
    resolved_target_files: List[Path] = [path.resolve() for path in target_files]
    absolute_targets = {str(path) for path in resolved_target_files}
    issues: Dict[str, Dict[str, List[str]]] = {
        target: {"errors": [], "warnings": []} for target in absolute_targets
    }
    if not absolute_targets:
        return issues

    # 兼容“直接运行节点图文件”的自检场景：
    # 节点图校验会触发布局计算，而布局层需要从 settings 读取 workspace_root。
    # CLI/GUI 启动入口会提前调用 settings.set_config_path(workspace_root)，但直接 python xxx.py 时不会。
    # 这里会尽量从被校验文件向上推断 workspace_root，并在必要时注入到 settings。
    workspace_root = ensure_settings_workspace_root(
        start_paths=[*resolved_target_files, Path(__file__).resolve()],
        load_user_settings=False,
    )

    from engine.validate.api import validate_files

    def _infer_active_package_id_for_file(file_path: Path) -> str | None:
        """根据文件路径推断其所属项目存档作用域（None=共享根）。

        说明：
        - 单文件/少量文件校验也必须切换作用域，否则复合节点、结构体/信号/关卡变量等代码级定义会串包，
          导致“未知信号/未知结构体/复合节点缺失”等误报。
        """
        from engine.utils.resource_library_layout import (
            PROJECT_ARCHIVE_LIBRARY_DIRNAME,
            SHARED_LIBRARY_DIRNAME,
            find_containing_resource_root,
        )

        resource_library_root = (workspace_root / "assets" / "资源库").resolve()
        resolved_file = file_path.resolve()
        resource_root = find_containing_resource_root(resource_library_root, resolved_file)
        if resource_root is None:
            # 文件不在资源库目录结构下：保持调用方当前作用域，避免把临时文件/生成文件强行降级为“共享根”。
            # 典型场景：测试在 tmp_path 下写入最小 Graph Code 并通过 set_active_package_id(...) 选择复合节点作用域。
            from engine.utils.runtime_scope import get_active_package_id

            return get_active_package_id()
        if resource_root.name == SHARED_LIBRARY_DIRNAME:
            return None
        if resource_root.parent.name == PROJECT_ARCHIVE_LIBRARY_DIRNAME:
            return resource_root.name
        return None

    def _apply_scope_and_refresh_node_library(active_package_id: str | None) -> None:
        """应用当前作用域（共享 / 共享+存档）并刷新节点库/Schema 缓存。"""
        from engine.utils.runtime_scope import set_active_package_id as set_runtime_active_package_id

        from engine.resources.definition_schema_view import (
            set_default_definition_schema_view_active_package_id,
        )
        from engine.resources.level_variable_schema_view import (
            set_default_level_variable_schema_view_active_package_id,
        )
        from engine.resources.ingame_save_template_schema_view import (
            set_default_ingame_save_template_schema_view_active_package_id,
        )
        from engine.signal import invalidate_default_signal_repository_cache
        from engine.struct import invalidate_default_struct_repository_cache

        set_runtime_active_package_id(active_package_id)
        set_default_definition_schema_view_active_package_id(active_package_id)
        set_default_level_variable_schema_view_active_package_id(active_package_id)
        set_default_ingame_save_template_schema_view_active_package_id(active_package_id)
        invalidate_default_signal_repository_cache()
        invalidate_default_struct_repository_cache()

        # NodeRegistry 需要显式 refresh 才会按新作用域重建复合节点集合。
        from engine.nodes.node_registry import get_node_registry

        registry = get_node_registry(workspace_root, include_composite=True)
        registry.refresh()

    # 分组：按文件所属项目存档作用域分别执行 validate_files，避免跨存档串包
    grouped: Dict[str | None, List[Path]] = {}
    for file_path in resolved_target_files:
        group_key = _infer_active_package_id_for_file(file_path) if isinstance(file_path, Path) else None
        grouped.setdefault(group_key, []).append(file_path)

    # 稳定顺序：共享根在前，其余存档按名称排序
    ordered_groups: List[tuple[str | None, List[Path]]] = []
    if None in grouped:
        ordered_groups.append((None, grouped.pop(None)))
    for pkg_id in sorted(grouped.keys(), key=lambda x: str(x or "").casefold()):
        ordered_groups.append((pkg_id, grouped[pkg_id]))

    for active_package_id, group_targets in ordered_groups:
        _apply_scope_and_refresh_node_library(active_package_id)
        report = validate_files(
            list(group_targets or []),
            workspace_root,
            strict_entity_wire_only=False,
            use_cache=True,
        )
        for issue in report.issues:
            issue_file = issue.file or ""
            if issue_file in issues:
                bucket = issues[issue_file]
                if issue.level == "error":
                    bucket["errors"].append(issue.message)
                elif issue.level == "warning":
                    bucket["warnings"].append(issue.message)
    return issues


