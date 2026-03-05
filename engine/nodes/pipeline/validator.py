from __future__ import annotations

import re
from typing import Any, Dict, List, Union

from .types import NormalizedSpec
from engine.nodes.constants import NODE_CATEGORY_VALUES, ALLOWED_SCOPES


def validate_specs(normalized_items: List[Union[NormalizedSpec, Dict[str, Any]]]) -> List[NormalizedSpec]:
    """
    对标准化后的项进行阻断式校验。

    校验项（发现问题直接抛出异常，不做包装）:
    - 类别合法性（内部统一为“...节点”）
    - 名称/标准键完整性
    - 作用域声明合法性（仅允许 server/client）
    - 端口类型完整性（端口名与类型为非空字符串；动态端口放行）
    - 别名冲突（同类别下别名映射到多个不同标准键）
    """
    if not isinstance(normalized_items, list):
        raise TypeError("normalized_items 必须是列表")

    allowed_categories = set(NODE_CATEGORY_VALUES)
    allowed_scopes = set(ALLOWED_SCOPES)

    # 别名冲突检测：category/name_or_alias -> standard_key
    alias_to_owner: Dict[str, str] = {}

    # semantic_id 冲突检测：semantic_id -> standard_key（允许同一 key 的 server/client 多实现重用同一 semantic_id）
    semantic_id_to_key: Dict[str, str] = {}

    semantic_id_pattern = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")

    # 在输出中统一返回 NormalizedSpec（若输入为 dict 则跳过，因为当前管线期望已是 NormalizedSpec）
    result: List[NormalizedSpec] = []

    for item in normalized_items:
        if isinstance(item, NormalizedSpec):
            category_standard = str(item.category_standard or "").strip()
            name_text = str(item.name or "").strip()
            standard_key = str(item.standard_key or "").strip()
            file_path_text = str(item.file_path or "")
            scopes_list = list(item.scopes or [])
            input_types = dict(item.input_types or {})
            output_types = dict(item.output_types or {})
            aliases_field = list(item.aliases or [])
            dynamic_port_type_text = str(getattr(item, "dynamic_port_type", "") or "")
            input_port_aliases = dict(getattr(item, "input_port_aliases", {}) or {})
            output_port_aliases = dict(getattr(item, "output_port_aliases", {}) or {})
            input_generic_constraints = dict(getattr(item, "input_generic_constraints", {}) or {})
            output_generic_constraints = dict(getattr(item, "output_generic_constraints", {}) or {})
            input_enum_options = dict(getattr(item, "input_enum_options", {}) or {})
            output_enum_options = dict(getattr(item, "output_enum_options", {}) or {})
            input_defaults = dict(getattr(item, "input_defaults", {}) or {})
            semantic_id_text = str(getattr(item, "semantic_id", "") or "").strip()
        elif isinstance(item, dict):
            category_standard = str(item.get("category_standard", "") or "").strip()
            name_text = str(item.get("name", "") or "").strip()
            standard_key = str(item.get("standard_key", "") or "").strip()
            file_path_text = str(item.get("file_path", "") or "")
            scopes_list = list(item.get("scopes") or [])
            input_types = item.get("input_types") or {}
            output_types = item.get("output_types") or {}
            aliases_field = list(item.get("aliases") or [])
            dynamic_port_type_text = str(item.get("dynamic_port_type", "") or "")
            input_port_aliases = dict(item.get("input_port_aliases") or {})
            output_port_aliases = dict(item.get("output_port_aliases") or {})
            input_generic_constraints = dict(item.get("input_generic_constraints") or {})
            output_generic_constraints = dict(item.get("output_generic_constraints") or {})
            input_enum_options = dict(item.get("input_enum_options") or {})
            output_enum_options = dict(item.get("output_enum_options") or {})
            input_defaults = dict(item.get("input_defaults") or {})
            semantic_id_text = str(item.get("semantic_id") or "").strip()
        else:
            raise ValueError("[VALIDATOR] 项目类型非法: 期望 NormalizedSpec 或 dict")

        # 1) 类别合法性
        if category_standard == "":
            raise ValueError(f"[VALIDATOR] 类别缺失: key={standard_key or '<empty>'}, file={file_path_text}")
        if category_standard not in allowed_categories:
            raise ValueError(f"[VALIDATOR] 类别非法: key={standard_key or '<unknown>'}, category={category_standard}, file={file_path_text}")

        # 2) 名称/标准键完整性
        if name_text == "":
            raise ValueError(f"[VALIDATOR] 名称缺失: category={category_standard}, file={file_path_text}")
        expected_key = f"{category_standard}/{name_text}"
        if standard_key != expected_key:
            raise ValueError(f"[VALIDATOR] 标准键不匹配: got={standard_key}, expected={expected_key}, file={file_path_text}")

        # 2.1) semantic_id 合法性与冲突检查
        if semantic_id_text:
            if not semantic_id_pattern.match(semantic_id_text):
                raise ValueError(
                    f"[VALIDATOR] semantic_id 非法: key={standard_key}, semantic_id={semantic_id_text!r}, "
                    f"expected_pattern={semantic_id_pattern.pattern}, file={file_path_text}"
                )
            prev_key = semantic_id_to_key.get(semantic_id_text)
            if prev_key is None:
                semantic_id_to_key[semantic_id_text] = standard_key
            elif prev_key != standard_key:
                raise ValueError(
                    f"[VALIDATOR] semantic_id 冲突: semantic_id={semantic_id_text!r}, ownerA={prev_key}, ownerB={standard_key}"
                )

        # 3) 作用域声明合法性
        for scope in scopes_list:
            scope_text = str(scope or "").strip()
            if scope_text and scope_text not in allowed_scopes:
                raise ValueError(f"[VALIDATOR] 作用域非法: key={standard_key}, scope={scope_text}")

        # 4) 端口类型完整性（非空字符串）
        if not isinstance(input_types, dict) or not isinstance(output_types, dict):
            raise ValueError(f"[VALIDATOR] 端口类型结构非法: key={standard_key}")

        # 4.1) 禁止使用旧称/不允许的泛型同义词（从源头掐灭）
        def _assert_no_banned_type(where: str, type_name_text: str) -> None:
            tn = str(type_name_text or "").strip()
            if tn in {"通用", "Any", "any", "ANY"}:
                raise ValueError(f"[VALIDATOR] 禁止使用旧称类型: {where} type='{tn}' → 请改为 '泛型' (key={standard_key}, file={file_path_text})")

        if dynamic_port_type_text:
            _assert_no_banned_type("dynamic_port_type", dynamic_port_type_text)

        for port_name, type_name in input_types.items():
            pn = str(port_name or "").strip()
            tn = str(type_name or "").strip()
            if pn == "" or tn == "":
                raise ValueError(f"[VALIDATOR] 输入端口类型缺失: key={standard_key}, port={port_name!r}, type={type_name!r}")
            _assert_no_banned_type("input", tn)

        for port_name, type_name in output_types.items():
            pn = str(port_name or "").strip()
            tn = str(type_name or "").strip()
            if pn == "" or tn == "":
                raise ValueError(f"[VALIDATOR] 输出端口类型缺失: key={standard_key}, port={port_name!r}, type={type_name!r}")
            _assert_no_banned_type("output", tn)

        def _validate_port_aliases(aliases_map: Dict[str, Any], type_dict: Dict[str, str], direction: str) -> Dict[str, List[str]]:
            if not aliases_map:
                return {}
            if not isinstance(aliases_map, dict):
                raise ValueError(f"[VALIDATOR] {direction}端口别名结构非法: key={standard_key}, expected=dict")

            normalized_map: Dict[str, List[str]] = {}
            alias_to_owner: Dict[str, str] = {}
            current_ports = set([str(k) for k in type_dict.keys() if str(k)])

            for canonical_port, alias_values in aliases_map.items():
                canonical_text = str(canonical_port or "").strip()
                if canonical_text == "":
                    raise ValueError(f"[VALIDATOR] {direction}端口别名存在空端口名: key={standard_key}")
                if canonical_text not in current_ports:
                    raise ValueError(f"[VALIDATOR] {direction}端口别名引用未知端口 '{canonical_text}': key={standard_key}")

                if not isinstance(alias_values, (list, tuple)) or len(alias_values) == 0:
                    raise ValueError(f"[VALIDATOR] {direction}端口 '{canonical_text}' 的别名必须为非空列表: key={standard_key}")

                normalized_aliases: List[str] = []
                for alias_value in list(alias_values or []):
                    alias_text = str(alias_value or "").strip()
                    if alias_text == "":
                        raise ValueError(f"[VALIDATOR] {direction}端口 '{canonical_text}' 的别名包含空字符串: key={standard_key}")
                    if alias_text == canonical_text:
                        raise ValueError(f"[VALIDATOR] {direction}端口 '{canonical_text}' 的别名不能与自身同名: key={standard_key}")
                    if alias_text in current_ports:
                        raise ValueError(
                            f"[VALIDATOR] {direction}端口 '{canonical_text}' 的别名与当前端口名冲突: alias={alias_text!r}, key={standard_key}"
                        )
                    prev_owner = alias_to_owner.get(alias_text)
                    if prev_owner is not None and prev_owner != canonical_text:
                        raise ValueError(
                            f"[VALIDATOR] {direction}端口别名冲突: alias={alias_text!r}, ownerA={prev_owner!r}, ownerB={canonical_text!r}, key={standard_key}"
                        )
                    alias_to_owner[alias_text] = canonical_text
                    if alias_text not in normalized_aliases:
                        normalized_aliases.append(alias_text)

                normalized_map[canonical_text] = normalized_aliases

            return normalized_map

        def _validate_generic_constraints(constraints: Dict[str, Any], type_dict: Dict[str, str], direction: str) -> None:
            for port_name, allowed_types in (constraints or {}).items():
                port_text = str(port_name or "").strip()
                if port_text == "":
                    raise ValueError(f"[VALIDATOR] {direction}泛型约束存在空端口名: key={standard_key}")
                if port_text not in type_dict:
                    raise ValueError(f"[VALIDATOR] {direction}泛型约束引用未知端口 '{port_text}': key={standard_key}")
                declared_type = str(type_dict.get(port_text, "") or "").strip()
                if "泛型" not in declared_type:
                    raise ValueError(
                        f"[VALIDATOR] {direction}端口 '{port_text}' 非泛型类型 '{declared_type}'，无法声明泛型约束: key={standard_key}"
                    )
                if not isinstance(allowed_types, (list, tuple)) or len(allowed_types) == 0:
                    raise ValueError(
                        f"[VALIDATOR] {direction}端口 '{port_text}' 泛型约束必须为非空列表: key={standard_key}"
                    )
                normalized_allowed: List[str] = []
                for candidate in allowed_types:
                    candidate_text = str(candidate or "").strip()
                    if candidate_text == "":
                        raise ValueError(
                            f"[VALIDATOR] {direction}端口 '{port_text}' 泛型约束包含空类型: key={standard_key}"
                        )
                    normalized_allowed.append(candidate_text)
                constraints[port_text] = normalized_allowed

        _validate_generic_constraints(input_generic_constraints, input_types, "输入")
        _validate_generic_constraints(output_generic_constraints, output_types, "输出")

        normalized_input_port_aliases = _validate_port_aliases(input_port_aliases, input_types, "输入")
        normalized_output_port_aliases = _validate_port_aliases(output_port_aliases, output_types, "输出")
        if isinstance(item, NormalizedSpec):
            item.input_port_aliases = normalized_input_port_aliases
            item.output_port_aliases = normalized_output_port_aliases
        else:
            item["input_port_aliases"] = normalized_input_port_aliases
            item["output_port_aliases"] = normalized_output_port_aliases

        def _validate_input_defaults(defaults: Dict[str, Any], type_dict: Dict[str, str]) -> Dict[str, Any]:
            """校验并规范化 input_defaults。

            约定：
            - key 必须是已声明的输入端口名（来自 inputs/type_dict），不允许引用流程端口或变参占位端口；
            - value 必须为“可静态序列化”的字面量（此处不做深度类型推断，仅保留原值）。
            """
            if not defaults:
                return {}
            if not isinstance(defaults, dict):
                raise ValueError(f"[VALIDATOR] input_defaults 结构非法: key={standard_key}, expected=dict")
            normalized: Dict[str, Any] = {}
            for port_name, default_value in defaults.items():
                port_text = str(port_name or "").strip()
                if port_text == "":
                    raise ValueError(f"[VALIDATOR] input_defaults 存在空端口名: key={standard_key}")
                if port_text in {"流程入", "流程出"}:
                    raise ValueError(f"[VALIDATOR] input_defaults 禁止声明流程端口默认值: port={port_text!r}, key={standard_key}")
                if "~" in port_text:
                    raise ValueError(f"[VALIDATOR] input_defaults 禁止声明变参占位端口默认值: port={port_text!r}, key={standard_key}")
                if port_text not in type_dict:
                    raise ValueError(f"[VALIDATOR] input_defaults 引用未知输入端口 '{port_text}': key={standard_key}")
                normalized[port_text] = default_value
            return normalized

        normalized_input_defaults = _validate_input_defaults(input_defaults, input_types)
        if isinstance(item, NormalizedSpec):
            item.input_defaults = normalized_input_defaults
        else:
            item["input_defaults"] = normalized_input_defaults

        # 5) 别名冲突（同类别内）
        # 自身名称也注册为“别名键”，便于统一入口
        alias_keys: List[str] = [f"{category_standard}/{name_text}"]
        for alias in list(aliases_field or []):
            alias_text = str(alias or "").strip()
            if alias_text:
                alias_keys.append(f"{category_standard}/{alias_text}")

        for akey in alias_keys:
            prev = alias_to_owner.get(akey)
            if prev is None:
                alias_to_owner[akey] = standard_key
            elif prev != standard_key:
                raise ValueError(f"[VALIDATOR] 别名冲突: alias_key={akey}, ownerA={prev}, ownerB={standard_key}")

        if isinstance(item, NormalizedSpec):
            result.append(item)
        else:
            # 回退：将 dict 透传为 NormalizedSpec 以统一类型
            result.append(NormalizedSpec.from_dict(item))  # type: ignore[arg-type]

    return result


