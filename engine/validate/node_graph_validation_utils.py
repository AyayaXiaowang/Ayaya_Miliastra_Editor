from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from engine.utils.source_text import read_text
from engine.utils.workspace import ensure_settings_workspace_root

from .issue import EngineIssue


@dataclass(frozen=True, slots=True)
class _ParsedLineSpan:
    start: int
    end: int


def _parse_line_span(text: str | None) -> _ParsedLineSpan | None:
    """解析 EngineIssue.line_span 的常见表示形式为行号区间。"""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None

    # 常见形态：
    # - "第12~14行"
    # - "12"
    # - "12-14"
    # - "12~14"
    normalized = stripped
    if normalized.startswith("第") and normalized.endswith("行"):
        normalized = normalized[1:-1]
    normalized = normalized.replace("～", "~")
    normalized = normalized.replace("—", "-")
    normalized = normalized.replace("－", "-")

    if "~" in normalized:
        left, right = normalized.split("~", 1)
    elif "-" in normalized:
        left, right = normalized.split("-", 1)
    else:
        left, right = normalized, normalized

    left = left.strip()
    right = right.strip()
    if not left.isdigit() or not right.isdigit():
        return None
    start = int(left)
    end = int(right)
    if start <= 0 or end <= 0:
        return None
    if end < start:
        start, end = end, start
    return _ParsedLineSpan(start=start, end=end)


def _extract_snippet(file_path: Path, *, span: _ParsedLineSpan, context_lines: int = 1) -> List[str]:
    """从源码中抽取行号片段（严格读取；失败直接抛异常）。"""
    source = read_text(file_path)
    lines = source.splitlines()
    if not lines:
        return []

    start = max(1, span.start - context_lines)
    end = min(len(lines), span.end + context_lines)

    # 避免过长输出：最多展示 5 行，优先围绕 start。
    max_lines = 5
    if (end - start + 1) > max_lines:
        end = min(len(lines), start + max_lines - 1)

    out: List[str] = []
    for lineno in range(start, end + 1):
        text = lines[lineno - 1]
        out.append(f"{lineno:>4} | {text}")
    return out


def _format_issue_for_text(issue: EngineIssue, *, file_path: Path) -> str:
    """把结构化 EngineIssue 转成更可定位的多行文本（用于 validate-file 的纯文本报告）。"""
    base = str(issue.message or "").rstrip()
    extra: List[str] = []

    if issue.code or issue.category:
        if issue.code and issue.category:
            extra.append(f"定位: 规则={issue.code}（{issue.category}）")
        elif issue.code:
            extra.append(f"定位: 规则={issue.code}")
        else:
            extra.append(f"定位: 类别={issue.category}")

    if issue.line_span:
        extra.append(f"位置: {issue.line_span}")

    if issue.location:
        extra.append(f"路径: {issue.location}")

    node_bits: List[str] = []
    if issue.node_id:
        node_bits.append(f"id={issue.node_id}")
    if issue.port:
        node_bits.append(f"port={issue.port}")
    if node_bits:
        extra.append("节点: " + ", ".join(node_bits))

    # 代码片段：仅在能解析出明确行号时展示
    parsed_span = _parse_line_span(issue.line_span)
    if parsed_span is not None and file_path.exists():
        snippet = _extract_snippet(file_path, span=parsed_span, context_lines=1)
        if snippet:
            extra.append("代码片段:")
            extra.extend(f"  {line}" for line in snippet)

    # 针对高频告警补一段“判断口径”，降低用户困惑
    if issue.code == "CODE_DICT_COMPUTE_MULTI_USE":
        extra.append(
            "判断: 若后续存在“原地修改 dict 并期望后续读取到修改后的结果”，则必须按建议改为【节点图变量】承载；"
            "若所有消费均为只读且不依赖写回语义，可忽略该提示。"
        )
        if isinstance(issue.detail, dict):
            src_id = issue.detail.get("dict_source_node_id")
            src_port = issue.detail.get("dict_source_port")
            consumer_ids = issue.detail.get("consumer_node_ids")
            if src_id or src_port:
                extra.append(f"线索: source_node_id={src_id}, source_port={src_port}")
            if isinstance(consumer_ids, list) and consumer_ids:
                preview = "、".join(str(x) for x in consumer_ids[:6])
                tail = "…" if len(consumer_ids) > 6 else ""
                extra.append(f"线索: consumer_node_ids={preview}{tail}")

    if issue.code == "CODE_UNUSED_QUERY_OUTPUT":
        extra.append(
            "判断: 这不是“变量从未读取”，而是“该查询输出没有进入流程消费点（执行节点入参/分支条件/循环迭代器等）”，"
            "因此常见含义是冗余节点或漏连流程条件。"
        )

    if not extra:
        return base
    if not base:
        return "\n".join(extra)
    return base + "\n" + "\n".join(extra)


def format_validate_file_report(
    *,
    file_path: str | Path,
    passed: bool,
    errors: List[str],
    warnings: List[str],
) -> str:
    """格式化 `validate_file` 的文本报告（CLI/runtime 共用）。"""
    resolved_path = Path(file_path).resolve()

    def _emit_indexed_multiline(block_lines: List[str], *, index_prefix: str) -> List[str]:
        if not block_lines:
            return []
        first = block_lines[0]
        rest = block_lines[1:]
        out = [f"{index_prefix}{first}"]
        cont_prefix = " " * len(index_prefix)
        out.extend(f"{cont_prefix}{line}" for line in rest)
        return out

    lines: List[str] = []
    lines.append("=" * 80)
    lines.append("节点图自检:")
    lines.append(f"文件: {resolved_path}")
    lines.append(f"结果: {'通过' if passed else '未通过'}")

    if errors:
        lines.append("")
        lines.append("错误明细:")
        for index, message in enumerate(errors, start=1):
            msg_lines = str(message).splitlines() or [""]
            lines.extend(_emit_indexed_multiline(msg_lines, index_prefix=f"  [{index}] "))

    if warnings:
        lines.append("")
        lines.append("警告明细:")
        for index, message in enumerate(warnings, start=1):
            msg_lines = str(message).splitlines() or [""]
            lines.extend(_emit_indexed_multiline(msg_lines, index_prefix=f"  [{index}] "))

    lines.append("=" * 80)
    return "\n".join(lines)


def strict_parse_file(file_path: Path) -> None:
    """以解析器 strict fail-closed 模式解析单个节点图文件。"""
    resolved_target = file_path.resolve()
    workspace_root = ensure_settings_workspace_root(
        start_paths=[resolved_target, Path(__file__).resolve()],
        load_user_settings=False,
    )

    # 推断 active_package_id 并刷新作用域（与 collect_issue_messages_for_files 对齐）
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
            raise GraphParseError("严格模式：复合节点引脚类型校验未通过，已拒绝解析：\n" + "\n".join(bad) + f"\n文件: {resolved_target}")
        return

    from engine.graph.graph_code_parser import GraphCodeParser

    GraphCodeParser(workspace_root, strict=True).parse_file(resolved_target)


def collect_issue_messages_for_files(target_files: List[Path]) -> Dict[str, Dict[str, List[str]]]:
    """运行底层验证并聚合成“文件 → (错误/警告消息列表)”的映射。

    说明：
    - 消息为“可定位文本”：包含错误码、行号片段、以及部分规则的判定口径补充。
    """
    resolved_target_files: List[Path] = [path.resolve() for path in target_files]
    absolute_targets = {str(path) for path in resolved_target_files}
    issues: Dict[str, Dict[str, List[str]]] = {target: {"errors": [], "warnings": []} for target in absolute_targets}
    if not absolute_targets:
        return issues

    workspace_root = ensure_settings_workspace_root(
        start_paths=[*resolved_target_files, Path(__file__).resolve()],
        load_user_settings=False,
    )

    from engine.validate.api import validate_files

    def _infer_active_package_id_for_file(file_path: Path) -> str | None:
        from engine.utils.resource_library_layout import (
            PROJECT_ARCHIVE_LIBRARY_DIRNAME,
            SHARED_LIBRARY_DIRNAME,
            find_containing_resource_root,
        )

        resource_library_root = (workspace_root / "assets" / "资源库").resolve()
        resolved_file = file_path.resolve()
        resource_root = find_containing_resource_root(resource_library_root, resolved_file)
        if resource_root is None:
            from engine.utils.runtime_scope import get_active_package_id

            return get_active_package_id()
        if resource_root.name == SHARED_LIBRARY_DIRNAME:
            return None
        if resource_root.parent.name == PROJECT_ARCHIVE_LIBRARY_DIRNAME:
            return resource_root.name
        return None

    def _apply_scope_and_refresh_node_library(active_package_id: str | None) -> None:
        from engine.utils.runtime_scope import set_active_package_id as set_runtime_active_package_id

        from engine.resources.definition_schema_view import set_default_definition_schema_view_active_package_id
        from engine.resources.level_variable_schema_view import set_default_level_variable_schema_view_active_package_id
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

        from engine.nodes.node_registry import get_node_registry

        registry = get_node_registry(workspace_root, include_composite=True)
        registry.refresh()

    grouped: Dict[str | None, List[Path]] = {}
    for file_path in resolved_target_files:
        group_key = _infer_active_package_id_for_file(file_path) if isinstance(file_path, Path) else None
        grouped.setdefault(group_key, []).append(file_path)

    ordered_groups: List[Tuple[str | None, List[Path]]] = []
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
            if issue_file not in issues:
                continue
            bucket = issues[issue_file]
            formatted = _format_issue_for_text(issue, file_path=Path(issue_file))
            if issue.level == "error":
                bucket["errors"].append(formatted)
            elif issue.level == "warning":
                bucket["warnings"].append(formatted)
    return issues

