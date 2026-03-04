from __future__ import annotations

import re
from typing import Dict, List

from engine.type_registry import (
    TYPE_GENERIC,
    TYPE_GENERIC_DICT,
    TYPE_GENERIC_LIST,
    TYPE_LIST_PLACEHOLDER,
    parse_typed_dict_alias,
)


def _find_forbidden_placeholder_type_impl(type_name: str) -> str:
    """复用校验规则口径：显式注解中禁止出现“泛型家族”占位类型。"""
    text = str(type_name or "").strip()
    if not text:
        return ""
    if text in {TYPE_GENERIC, TYPE_LIST_PLACEHOLDER, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT}:
        return text
    is_typed_dict, key_type_name, value_type_name = parse_typed_dict_alias(text)
    if is_typed_dict:
        forbidden_key = _find_forbidden_placeholder_type_impl(key_type_name)
        if forbidden_key:
            return forbidden_key
        forbidden_value = _find_forbidden_placeholder_type_impl(value_type_name)
        if forbidden_value:
            return forbidden_value
    return ""


class _ExecutableCodegenTypeInferenceMixin:
    @staticmethod
    def _find_forbidden_placeholder_type(type_name: str) -> str:
        return _find_forbidden_placeholder_type_impl(type_name)

    @staticmethod
    def _should_emit_type_annotation(type_name: str) -> bool:
        """决定是否输出 `x: \"类型\" = ...` 的显式注解行。"""
        return _find_forbidden_placeholder_type_impl(type_name) == ""

    @staticmethod
    def _strip_string_literal(expr: str) -> str:
        text = str(expr or "").strip()
        if (len(text) >= 2) and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
            return text[1:-1]
        return text

    @staticmethod
    def _infer_expr_type(expr: str, *, var_types: Dict[str, str]) -> str:
        text = str(expr or "").strip()
        if not text:
            return ""
        if (len(text) >= 2) and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
            return "字符串"
        if text in ("True", "False"):
            return "布尔值"
        # 数字：仅识别常见的十进制字面量
        if re.fullmatch(r"-?\d+\.\d+", text):
            return "浮点数"
        if re.fullmatch(r"-?\d+", text):
            return "整数"
        # 变量
        if text.isidentifier():
            return var_types.get(text, "")
        return ""

    def _infer_output_type(
        self,
        *,
        node_title: str,
        declared_type: str,
        input_params: Dict[str, str],
        var_types: Dict[str, str],
        graph_variable_types: Dict[str, str],
    ) -> str:
        declared = str(declared_type or "").strip()

        # 1) 获取节点图变量：用 GRAPH_VARIABLES 声明推断类型
        if node_title == "获取节点图变量":
            var_name_expr = input_params.get("变量名", "")
            var_name = self._strip_string_literal(var_name_expr)
            inferred = graph_variable_types.get(var_name, "")
            return inferred or declared

        # 2) 获取自定义变量：节点本身输出为『泛型』，若无法推断则回退到“字符串”作为最常见默认
        if node_title == "获取自定义变量":
            var_name_expr = input_params.get("变量名", "")
            var_name = self._strip_string_literal(var_name_expr)
            inferred = graph_variable_types.get(var_name, "")
            if inferred:
                return inferred
            if declared in {TYPE_GENERIC, TYPE_LIST_PLACEHOLDER, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT, ""}:
                return "字符串"
            return declared

        # 3) 拼装列表：根据元素类型推断列表具体类型（字符串列表/整数列表/浮点数列表/布尔值列表）
        if node_title == "拼装列表":
            element_types: List[str] = []
            for key, value in input_params.items():
                if key.isdigit():
                    element_types.append(self._infer_expr_type(value, var_types=var_types))
            normalized = [t for t in element_types if t]
            if not normalized:
                return declared
            unique = set(normalized)
            # int + float -> float
            if unique.issubset({"整数", "浮点数"}):
                return "浮点数列表" if "浮点数" in unique else "整数列表"
            if len(unique) == 1:
                only = next(iter(unique))
                if only == "字符串":
                    return "字符串列表"
                if only == "整数":
                    return "整数列表"
                if only == "浮点数":
                    return "浮点数列表"
                if only == "布尔值":
                    return "布尔值列表"
                # 通用：实体/配置ID/GUID/三维向量/... 等具体类型
                return f"{only}列表"
            return declared

        # 3.1) 拼装字典：根据键/值类型推断字典具体类型（如：配置ID-整数字典）
        if node_title == "拼装字典":
            key_types: List[str] = []
            value_types: List[str] = []

            for port_name, expr in input_params.items():
                name = str(port_name or "").strip()
                inferred = self._infer_expr_type(str(expr or ""), var_types=var_types)
                if not inferred:
                    continue

                # 兼容：按位置参数归一化（0/1/2/3... 偶数为键，奇数为值）
                if name.isdigit():
                    index = int(name)
                    if index % 2 == 0:
                        key_types.append(inferred)
                    else:
                        value_types.append(inferred)
                    continue

                # 常见：键0/值0/键1/值1...
                if name.startswith("键") and name[1:].isdigit():
                    key_types.append(inferred)
                    continue
                if name.startswith("值") and name[1:].isdigit():
                    value_types.append(inferred)
                    continue

            if not key_types or not value_types:
                return declared

            key_set = set(key_types)
            value_set = set(value_types)

            # 小幅容错：{整数, 配置ID/元件ID/GUID} 视为 ID 类型（常见于 0/默认值混入）
            if key_set.issubset({"整数", "配置ID"}) and "配置ID" in key_set:
                key_set = {"配置ID"}
            if key_set.issubset({"整数", "元件ID"}) and "元件ID" in key_set:
                key_set = {"元件ID"}
            if key_set.issubset({"字符串", "GUID"}) and "GUID" in key_set:
                key_set = {"GUID"}

            if len(key_set) == 1 and len(value_set) == 1:
                key_only = next(iter(key_set))
                value_only = next(iter(value_set))
                return f"{key_only}-{value_only}字典"
            return declared

        # 4) 加法/减法/乘法/除法：根据左右输入推断数值类型
        if node_title in {"加法运算", "减法运算", "乘法运算", "除法运算"}:
            left_expr = input_params.get("左值", "")
            right_expr = input_params.get("右值", "")
            left_type = self._infer_expr_type(left_expr, var_types=var_types)
            right_type = self._infer_expr_type(right_expr, var_types=var_types)
            if left_type or right_type:
                if "浮点数" in (left_type, right_type):
                    return "浮点数"
                if (left_type == "整数") and (right_type == "整数"):
                    return "整数"
            return declared

        return declared


__all__ = ["_ExecutableCodegenTypeInferenceMixin"]

