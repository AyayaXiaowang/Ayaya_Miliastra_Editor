from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.type_registry import TYPE_DICT

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, iter_class_methods, line_span_text


class DictAnnotationRequiresKeyValueRule(ValidationRule):
    """禁止在变量中文类型注解中使用裸 `字典`。

    背景：
    - `字典` 是一种容器类型，若不显式声明键/值类型，会导致端口类型推断与可读性变差；
    - 项目已支持“别名字典类型”语法：`键类型-值类型字典` / `键类型_值类型字典`；
    - 因此在 Graph Code / 复合节点代码中，局部变量的中文类型注解必须使用别名字典。
    """

    rule_id = "engine_code_dict_annotation_requires_key_value"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)

        issues: List[EngineIssue] = []
        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.AnnAssign):
                    continue

                annotation = getattr(node, "annotation", None)
                if not (
                    isinstance(annotation, ast.Constant)
                    and isinstance(getattr(annotation, "value", None), str)
                ):
                    continue

                type_name = str(annotation.value).strip()
                if type_name != TYPE_DICT:
                    continue

                target = getattr(node, "target", None)
                var_name = getattr(target, "id", "") if isinstance(target, ast.Name) else ""
                var_label = f"变量『{var_name}』" if var_name else "该变量"

                message = (
                    f"{line_span_text(node)}: {var_label}使用了裸类型注解『{TYPE_DICT}』；"
                    "字典类型必须显式声明键和值的数据类型，请改为形如『键类型-值类型字典』或『键类型_值类型字典』的别名字典类型。"
                    "例如：映射: \"字符串-整数字典\" = {\"a\": 1, \"b\": 2}"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        node,
                        "CODE_DICT_ANNOTATION_REQUIRES_KEY_VALUE",
                        message,
                    )
                )

        return issues


__all__ = ["DictAnnotationRequiresKeyValueRule"]


