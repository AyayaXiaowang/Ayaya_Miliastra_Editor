from __future__ import annotations

import ast
import keyword
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    infer_graph_scope,
    iter_class_methods,
    parse_module,
    line_span_text,
)
from ..node_index import node_function_names
from engine.nodes.pipeline.runner import run_pipeline


def _is_game_expr(expr: ast.AST) -> bool:
    if isinstance(expr, ast.Name) and expr.id == "game":
        return True
    if isinstance(expr, ast.Attribute):
        if isinstance(getattr(expr, "value", None), ast.Name) and expr.value.id == "self":
            return expr.attr == "game"
    return False


def _has_game_arg(call_node: ast.Call) -> bool:
    for arg in list(getattr(call_node, "args", []) or []):
        if _is_game_expr(arg):
            return True

    for kw in getattr(call_node, "keywords", []) or []:
        if getattr(kw, "arg", None) != "game":
            continue
        if _is_game_expr(getattr(kw, "value", ast.Constant(value=None))):
            return True
    return False


def _split_name_scope(name_part: str) -> Tuple[str, Optional[str]]:
    text = str(name_part or "")
    if "#" not in text:
        return text, None
    base, suffix = text.split("#", 1)
    return base, (suffix or None)


def _is_safe_call_name(name: str) -> bool:
    text = str(name or "").strip()
    return bool(text) and text.isidentifier() and (not keyword.iskeyword(text))


def _node_requires_game_from_impl(file_path: Path, func_name: str) -> bool:
    """通过解析实现文件 AST 判断节点函数是否包含 `game` 参数。"""
    module = parse_module(file_path)
    for node in getattr(module, "body", []) or []:
        if not isinstance(node, ast.FunctionDef):
            continue
        if getattr(node, "name", "") != func_name:
            continue
        args = getattr(node, "args", None)
        if args is None:
            return False
        positional = list(getattr(args, "posonlyargs", []) or []) + list(getattr(args, "args", []) or [])
        kwonly = list(getattr(args, "kwonlyargs", []) or [])
        all_args = positional + kwonly
        return any(getattr(a, "arg", None) == "game" for a in all_args)
    return False


def _build_nodes_requiring_game(workspace: Path, scope_text: str) -> Set[str]:
    """返回在指定 scope 下“必须传 game”的节点名集合。

    规则：
    - 仅对当前 scope 可调用的节点生效（含 `名称#scope` 变体的可调用名规约）；
    - 仅当实现函数签名包含 `game` 参数时才视为必须传 game；
      例如客户端 `获取当前角色()` 这类无 `game` 的节点不应被强制传 game。
    """
    index = run_pipeline(workspace)
    by_key: Dict[str, Dict[str, object]] = index.get("by_key", {}) if isinstance(index, dict) else {}

    chosen: Dict[str, Tuple[int, Path]] = {}
    for full_key, item in (by_key.items() if isinstance(by_key, dict) else []):
        if not isinstance(full_key, str) or "/" not in full_key:
            continue
        if not isinstance(item, dict):
            continue
        name_text = str(item.get("name", "") or "").strip()
        if not _is_safe_call_name(name_text):
            continue

        file_path_text = str(item.get("file_path", "") or "").strip()
        if not file_path_text:
            continue
        impl_path = Path(file_path_text)

        _, name_part = full_key.split("/", 1)
        base_name, scope_suffix = _split_name_scope(name_part)
        if base_name != name_text:
            # 容错：以 name_text 为准，避免 key/name 漂移导致误判
            base_name = name_text

        if scope_suffix is None:
            priority = 1
        elif scope_suffix == scope_text:
            priority = 2
        else:
            continue

        prev = chosen.get(base_name)
        if prev is None or priority > prev[0]:
            chosen[base_name] = (priority, impl_path)

    requires: Set[str] = set()
    for call_name, (_, impl_path) in chosen.items():
        if _node_requires_game_from_impl(impl_path, call_name):
            requires.add(call_name)
    return requires


class NodeCallGameRequiredRule(ValidationRule):
    """通用节点调用规范：已知节点函数必须显式传入 `self.game/game`。

    背景：
    - 多数代码规则仅对“看起来像节点调用”的形态进行分析（例如 `节点名(self.game, ...)`）以避免误伤普通 Python 调用；
    - 若漏传 `self.game/game`，该调用会绕过部分规则，导致问题潜伏到运行期才爆炸。
    """

    rule_id = "engine_code_node_call_game_required"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        scope_text = str(scope or "").strip().lower() or "server"
        known_node_names = node_function_names(ctx.workspace_path, scope_text)
        if not known_node_names:
            return []
        nodes_requiring_game = _build_nodes_requiring_game(ctx.workspace_path, scope_text)
        if not nodes_requiring_game:
            return []

        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                call_name = func.id
                if call_name not in known_node_names:
                    continue
                if call_name not in nodes_requiring_game:
                    continue

                if _has_game_arg(node):
                    continue

                message = (
                    f"{line_span_text(node)}: 发现已知节点『{call_name}』的调用，但未显式传入 `self.game/game`。"
                    "节点调用必须包含 game 参数，否则会绕过部分静态规则并在运行期报错。"
                    f"推荐写法：`{call_name}(self.game, ...)` 或 `{call_name}(game=self.game, ...)`。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        node,
                        "CODE_NODE_CALL_GAME_REQUIRED",
                        message,
                    )
                )

        return issues


__all__ = ["NodeCallGameRequiredRule"]


