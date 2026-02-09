from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

from engine.graph.common import STRUCT_NAME_PORT_NAME
from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.utils.resource_library_layout import find_containing_resource_root
from engine.validate.node_semantics import (
    SEMANTIC_STRUCT_BUILD,
    SEMANTIC_STRUCT_MODIFY,
    SEMANTIC_STRUCT_SPLIT,
    is_semantic_node_call,
)

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    infer_graph_scope,
    iter_class_methods,
    line_span_text,
)
from .resource_scope_utils import (
    relative_path_text,
    resource_root_id,
    try_build_graph_resource_scope,
)


def _collect_module_constant_strings(tree: ast.AST) -> Dict[str, str]:
    """收集模块顶层的字符串常量声明（支持普通与注解赋值）。"""
    constant_strings: Dict[str, str] = {}
    module_body = getattr(tree, "body", []) or []
    for node in module_body:
        target_names: List[str] = []
        value_node = None
        if isinstance(node, ast.Assign):
            value_node = getattr(node, "value", None)
            for target in getattr(node, "targets", []) or []:
                if isinstance(target, ast.Name):
                    target_names.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            value_node = getattr(node, "value", None)
            target = getattr(node, "target", None)
            if isinstance(target, ast.Name):
                target_names.append(target.id)
        if not target_names or not isinstance(value_node, ast.Constant):
            continue
        if not isinstance(getattr(value_node, "value", None), str):
            continue
        constant_text = value_node.value.strip()
        if not constant_text:
            continue
        for target_name in target_names:
            if target_name and target_name not in constant_strings:
                constant_strings[target_name] = constant_text
    return constant_strings


def _extract_struct_name_from_value(
    value_node: ast.AST | None, constant_strings: Dict[str, str]
) -> str:
    """解析“结构体名”参数的取值：直接字面量或顶层命名常量。"""
    if isinstance(value_node, ast.Constant) and isinstance(
        getattr(value_node, "value", None), str
    ):
        return value_node.value.strip()
    if isinstance(value_node, ast.Name):
        referenced_text = constant_strings.get(value_node.id, "")
        return referenced_text.strip()
    return ""


class StructNameRequiredRule(ValidationRule):
    """结构体相关节点：“结构体名”参数的值必须可静态解析且指向有效结构体定义。

    目标：
    - 对 `结构体名` 的内容做强校验（非空、可解析、存在于结构体定义中），避免拼写错误被静默忽略；
    - “缺少必填入参”的情况由通用规则 `RequiredInputsRule` 统一处理，此规则不再重复报错。
    """

    rule_id = "engine_code_struct_name_required"
    category = "结构体系统"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        module_constant_strings = _collect_module_constant_strings(tree)
        schema_view = get_default_definition_schema_view()
        struct_sources = schema_view.get_all_struct_definition_sources()
        struct_payloads = schema_view.get_all_struct_definitions()
        # 注意：DefinitionSchemaView 的聚合结果受运行期 active_package_id 影响（共享 / 共享+当前项目存档）。
        # validate-graphs 会按文件所属项目存档分组切换作用域；本规则必须**按当前作用域**判断结构体是否存在，
        # 禁止用进程级缓存“记住上一组”的结构体集合，否则会产生跨项目误报。
        # Graph Code 的结构体“结构体名”入参：只允许使用结构体定义中的 `STRUCT_PAYLOAD.struct_name`（唯一名称），
        # 不再兼容直接填写 STRUCT_ID，也不再使用 `name` 作为备用字段。
        struct_id_by_name: Dict[str, str] = {}
        if isinstance(struct_payloads, dict):
            for struct_id, payload in struct_payloads.items():
                if not isinstance(struct_id, str):
                    continue
                if not isinstance(payload, dict):
                    continue
                value = payload.get("struct_name")
                if not isinstance(value, str):
                    continue
                name_text = value.strip()
                if not name_text:
                    continue
                struct_id_by_name.setdefault(name_text, struct_id.strip())
        known_struct_names: Set[str] = set(struct_id_by_name.keys())
        graph_scope = try_build_graph_resource_scope(ctx.workspace_path, file_path)

        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                node_title = func.id
                is_struct_node = (
                    is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=node_title,
                        semantic_id=SEMANTIC_STRUCT_SPLIT,
                        include_composite=False,
                    )
                    or is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=node_title,
                        semantic_id=SEMANTIC_STRUCT_BUILD,
                        include_composite=False,
                    )
                    or is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=node_title,
                        semantic_id=SEMANTIC_STRUCT_MODIFY,
                        include_composite=False,
                    )
                )
                if not is_struct_node:
                    continue

                struct_kw_value_node = None
                for kw in getattr(node, "keywords", []) or []:
                    if kw.arg == STRUCT_NAME_PORT_NAME:
                        struct_kw_value_node = getattr(kw, "value", None)
                        break

                if struct_kw_value_node is None:
                    # 缺参由通用必填入参规则负责
                    continue

                struct_name = _extract_struct_name_from_value(
                    struct_kw_value_node, module_constant_strings
                )

                if not struct_name:
                    msg = (
                        f"{line_span_text(node)}: 【{node_title}】的“{STRUCT_NAME_PORT_NAME}”必须是非空字符串字面量，"
                        f"或引用模块顶层字符串常量；不允许使用运行期表达式。"
                    )
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_STRUCT_NAME_INVALID",
                            msg,
                        )
                    )
                    continue

                resolved_struct_id = str(struct_id_by_name.get(struct_name) or "").strip()
                if known_struct_names and not resolved_struct_id:
                    msg = (
                        f"{line_span_text(node)}: 【{node_title}】的“{STRUCT_NAME_PORT_NAME}”取值 '{struct_name}' "
                        f"在当前工程的结构体定义中不存在；请在“管理配置/结构体定义”中确认结构体定义的名字"
                        f"（STRUCT_PAYLOAD.struct_name），并修正为有效结构体名。"
                    )
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_STRUCT_NAME_UNKNOWN",
                            msg,
                        )
                    )
                    continue

                # 跨项目/共享边界：结构体定义必须来自“当前项目存档”或“共享”。
                if graph_scope is not None and resolved_struct_id:
                    payload = struct_payloads.get(str(resolved_struct_id)) or {}
                    struct_type_text = str(
                        payload.get("struct_type") or payload.get("struct_ype") or ""
                    ).strip()
                    kind_dirname = ""
                    if struct_type_text == "basic":
                        kind_dirname = "基础结构体"
                    elif struct_type_text:
                        kind_dirname = "局内存档结构体"

                    cross_issue = _maybe_collect_cross_project_struct_issue(
                        rule=self,
                        file_path=file_path,
                        at=node,
                        graph_scope=graph_scope,
                        struct_id=str(resolved_struct_id),
                        struct_sources=struct_sources,
                        kind_dirname=kind_dirname,
                    )
                    if cross_issue is not None:
                        issues.append(cross_issue)

        return issues


def _maybe_collect_cross_project_struct_issue(
    *,
    rule: ValidationRule,
    file_path: Path,
    at: ast.AST,
    graph_scope,
    struct_id: str,
    struct_sources: Dict[str, Path],
    kind_dirname: str,
) -> EngineIssue | None:
    source_path = struct_sources.get(str(struct_id))
    if source_path is None:
        return None
    definition_root = find_containing_resource_root(graph_scope.resource_library_root, source_path)
    if definition_root is None:
        return None
    if graph_scope.is_definition_root_allowed(definition_root):
        return None

    definition_owner_id = resource_root_id(
        shared_root_dir=graph_scope.shared_root_dir,
        packages_root_dir=graph_scope.packages_root_dir,
        resource_root_dir=definition_root,
    )
    current_owner_id = graph_scope.graph_owner_root_id
    source_rel = relative_path_text(graph_scope.workspace_path, source_path)
    suggest_dir = relative_path_text(
        graph_scope.workspace_path,
        graph_scope.suggest_current_project_struct_dir(kind_dirname),
    )
    kind_hint = f"{kind_dirname}/" if kind_dirname else ""
    message = (
        f"{line_span_text(at)}: 结构体『{struct_id}』的定义位于项目存档『{definition_owner_id}』，"
        f"但当前节点图属于项目存档『{current_owner_id}』；禁止跨项目引用结构体。"
        f"请在当前项目目录『{suggest_dir}』下新建/补齐该结构体定义（放入 {kind_hint}），并在节点上重新绑定后再使用。"
        f"（当前定义来源：{source_rel}）"
    )
    return create_rule_issue(
        rule,
        file_path,
        at,
        "CODE_STRUCT_OUT_OF_PROJECT_SCOPE",
        message,
    )


__all__ = ["StructNameRequiredRule"]


