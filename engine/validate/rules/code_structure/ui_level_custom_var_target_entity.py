from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.graph.common import TARGET_ENTITY_PORT_NAME, VARIABLE_NAME_PORT_NAME
from engine.graph.utils.ast_utils import collect_module_constants
from engine.validate.node_semantics import (
    SEMANTIC_CUSTOM_VAR_GET,
    SEMANTIC_CUSTOM_VAR_SET,
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
from ..ui_placeholder_vars_utils import try_load_ui_html_placeholder_var_contract_for_ctx


def _resolve_string_constant(expr: ast.AST | None, module_constants: dict) -> str | None:
    if isinstance(expr, ast.Constant) and isinstance(getattr(expr, "value", None), str):
        return str(expr.value).strip()
    if isinstance(expr, ast.Name):
        constant_value = module_constants.get(expr.id)
        if isinstance(constant_value, str):
            return constant_value.strip()
    return None


def _is_self_owner_entity_expr(expr: ast.AST | None) -> bool:
    return bool(
        isinstance(expr, ast.Attribute)
        and isinstance(expr.value, ast.Name)
        and str(expr.value.id or "") == "self"
        and str(expr.attr or "") == "owner_entity"
    )


def _looks_like_self_game_expr(expr: ast.AST | None) -> bool:
    if not isinstance(expr, ast.Attribute):
        return False
    value = getattr(expr, "value", None)
    return isinstance(value, ast.Name) and str(value.id or "") == "self" and str(expr.attr or "") == "game"


def _extract_target_and_var_expr(call_node: ast.Call) -> tuple[ast.AST | None, ast.AST | None]:
    """兼容关键字参数与语法糖改写后的“位置参数”形式。"""
    target_expr: ast.AST | None = None
    var_expr: ast.AST | None = None

    for kw in getattr(call_node, "keywords", []) or []:
        if kw.arg == TARGET_ENTITY_PORT_NAME:
            target_expr = getattr(kw, "value", None)
        elif kw.arg == VARIABLE_NAME_PORT_NAME:
            var_expr = getattr(kw, "value", None)

    # 位置参数兜底：自定义变量节点签名为 (game, 目标实体, 变量名, ...)
    args = list(getattr(call_node, "args", []) or [])
    if len(args) >= 3 and (_looks_like_self_game_expr(args[0]) or (isinstance(args[0], ast.Name) and str(args[0].id or "") == "game")):
        if target_expr is None:
            target_expr = args[1]
        if var_expr is None:
            var_expr = args[2]

    return target_expr, var_expr


def _infer_declared_owner_entity_kind(tree: ast.AST) -> str | None:
    """从文件头 docstring 推断 self.owner_entity 的“实体归属”。

    约定：
    - mount_entity_type / owner_entity_type / mount_entity 允许取值：关卡/关卡实体/玩家/玩家实体
    - 返回：
      - "level"：self.owner_entity 表示关卡实体
      - "player"：self.owner_entity 表示玩家实体
      - None：未声明（self.owner_entity 归属未知，校验将要求显式声明或显式取实体）
    """
    docstring = ast.get_docstring(tree) or ""
    for raw_line in str(docstring).splitlines():
        line = str(raw_line).strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        normalized_key = key.strip().lower()
        if normalized_key not in {"mount_entity_type", "owner_entity_type", "mount_entity"}:
            continue
        v = value.strip()
        if v in {"关卡", "关卡实体"}:
            return "level"
        if v in {"玩家", "玩家实体"}:
            return "player"
    return None


class UiLevelCustomVarTargetEntityRule(ValidationRule):
    """工程化：UI 源码占位符引用到的 ui_* 自定义变量必须写入正确的“目标实体”。

    规则逻辑：
    - 扫描当前作用域 UI源码(HTML) 中的占位符：
      - `{1:lv.xxx}` → 关卡作用域变量（归属：关卡实体）
      - `{{ps.xxx}}` / `{{p1.xxx}}..{{p8.xxx}}` → 玩家作用域变量（归属：玩家实体）
    - 对 Graph Code 中【获取/设置自定义变量】节点调用：
      - 若变量名为常量，且命中“关卡/玩家作用域变量集合”，且变量名以 `ui_` 开头；
      - 若目标实体写成 `self.owner_entity`：
        - 要求文件头 docstring 显式声明 `mount_entity_type/owner_entity_type: 关卡/玩家`，使 self.owner_entity 的归属明确；
        - 若声明与变量归属不一致，则报错提示作者“该变量归属哪个实体”，并要求改为：
          - 修正文档声明（若节点图确实挂载在该实体上），或
          - 显式取对应实体再读写（例如关卡实体用 GUID 查询；玩家实体通常使用事件源实体）。
    """

    rule_id = "engine_code_ui_level_custom_var_target_entity"
    category = "UI/自定义变量"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        declared_owner_kind = _infer_declared_owner_entity_kind(tree)

        view = try_load_ui_html_placeholder_var_contract_for_ctx(ctx)
        if view is None or (not view.level_scoped_var_names and not view.player_scoped_var_names):
            return []

        level_var_names: set[str] = set(view.level_scoped_var_names)
        player_var_names: set[str] = set(view.player_scoped_var_names)
        scope = infer_graph_scope(ctx)
        module_constants = collect_module_constants(tree)

        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                call_name = str(func.id or "").strip()
                if not call_name:
                    continue

                is_custom_var_node = (
                    is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=call_name,
                        semantic_id=SEMANTIC_CUSTOM_VAR_GET,
                    )
                    or is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=call_name,
                        semantic_id=SEMANTIC_CUSTOM_VAR_SET,
                    )
                )
                if not is_custom_var_node:
                    continue

                target_expr, var_expr = _extract_target_and_var_expr(node)
                var_name = _resolve_string_constant(var_expr, module_constants) if var_expr is not None else None
                if not var_name:
                    continue
                if not str(var_name).lower().startswith("ui_"):
                    continue
                is_level_scoped = var_name in level_var_names
                is_player_scoped = var_name in player_var_names
                if not is_level_scoped and not is_player_scoped:
                    continue
                # 极少数情况下同名变量同时出现在 lv/ps 作用域，静态上无法判定归属；跳过避免误报。
                if is_level_scoped and is_player_scoped:
                    continue
                if target_expr is None:
                    continue

                if _is_self_owner_entity_expr(target_expr):
                    expected_kind = "level" if is_level_scoped else "player"
                    expected_entity_name = "关卡实体" if expected_kind == "level" else "玩家实体"
                    expected_scope_hint = "lv" if expected_kind == "level" else "ps/p1..p8"
                    if declared_owner_kind == expected_kind:
                        continue
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            target_expr or node,
                            "CODE_UI_LEVEL_CUSTOM_VAR_TARGET_ENTITY_REQUIRED",
                            (
                                f"{line_span_text(node)}: UI源码占位符使用了 {expected_scope_hint} 作用域变量 {var_name!r}，"
                                f"该变量归属【{expected_entity_name}】；但此处目标实体为 self.owner_entity，且文件头未显式声明其归属。\n"
                                "修复建议（二选一）：\n"
                                f"- 若该节点图确实挂载在【{expected_entity_name}】上：请在文件头 docstring 显式声明 "
                                f"`mount_entity_type: {'关卡' if expected_kind == 'level' else '玩家'}`（或 `owner_entity_type: ...`），使 self.owner_entity 归属明确。\n"
                                f"- 若该节点图不挂载在【{expected_entity_name}】上：请显式获取正确实体后再读写该变量（关卡实体通常用 GUID 查询；玩家实体通常使用事件源实体）。"
                            ),
                        )
                    )

        return issues


__all__ = ["UiLevelCustomVarTargetEntityRule"]

