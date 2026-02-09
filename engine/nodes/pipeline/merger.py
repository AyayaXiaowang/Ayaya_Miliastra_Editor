from __future__ import annotations

from typing import Any, Dict, List, Union

from .types import NormalizedSpec


def _are_ports_compatible(item_a: Dict[str, Any], item_b: Dict[str, Any]) -> bool:
    """
    判断两个节点项的端口定义是否完全一致（用于决定是否可以直接合并）。
    """
    a_inputs = list(item_a.get("inputs") or [])
    b_inputs = list(item_b.get("inputs") or [])
    a_outputs = list(item_a.get("outputs") or [])
    b_outputs = list(item_b.get("outputs") or [])
    a_input_types = dict(item_a.get("input_types") or {})
    b_input_types = dict(item_b.get("input_types") or {})
    a_output_types = dict(item_a.get("output_types") or {})
    b_output_types = dict(item_b.get("output_types") or {})
    a_dynamic = str(item_a.get("dynamic_port_type") or "")
    b_dynamic = str(item_b.get("dynamic_port_type") or "")

    return (
        a_inputs == b_inputs and
        a_outputs == b_outputs and
        a_input_types == b_input_types and
        a_output_types == b_output_types and
        a_dynamic == b_dynamic and
        dict(item_a.get("input_defaults") or {}) == dict(item_b.get("input_defaults") or {}) and
        dict(item_a.get("input_generic_constraints") or {}) == dict(item_b.get("input_generic_constraints") or {}) and
        dict(item_a.get("output_generic_constraints") or {}) == dict(item_b.get("output_generic_constraints") or {}) and
        dict(item_a.get("input_enum_options") or {}) == dict(item_b.get("input_enum_options") or {}) and
        dict(item_a.get("output_enum_options") or {}) == dict(item_b.get("output_enum_options") or {})
    )


def _pick_precedence(item_x: Dict[str, Any], item_y: Dict[str, Any]) -> (Dict[str, Any], Dict[str, Any]):
    """
    选择优先项（server 优先），并返回 (preferred, secondary)。
    """
    x_scopes = set(list(item_x.get("scopes") or []))
    y_scopes = set(list(item_y.get("scopes") or []))
    x_is_server = "server" in x_scopes
    y_is_server = "server" in y_scopes

    if x_is_server and not y_is_server:
        return item_x, item_y
    if y_is_server and not x_is_server:
        return item_y, item_x
    # 平局时保持先到先得（由调用方控制遍历顺序）
    return item_x, item_y


def _merge_same_ports(preferred: Dict[str, Any], secondary: Dict[str, Any]) -> Dict[str, Any]:
    """
    端口完全一致时，合并元数据（别名/作用域等），返回合并后的项。
    """
    merged: Dict[str, Any] = dict(preferred)

    # 合并 semantic_id：优先保留非空值；若两边都非空且不一致则视为错误
    preferred_semantic_id = str(preferred.get("semantic_id") or "").strip()
    secondary_semantic_id = str(secondary.get("semantic_id") or "").strip()
    if preferred_semantic_id and secondary_semantic_id and preferred_semantic_id != secondary_semantic_id:
        raise ValueError(
            f"[MERGER] semantic_id 冲突（端口一致但语义不一致）: key={preferred.get('standard_key')}, "
            f"preferred={preferred_semantic_id!r}, secondary={secondary_semantic_id!r}"
        )
    merged["semantic_id"] = preferred_semantic_id or secondary_semantic_id

    # 合并 input_defaults：端口完全一致时，默认值也必须一致（或其中一侧为空）
    preferred_defaults = dict(preferred.get("input_defaults") or {})
    secondary_defaults = dict(secondary.get("input_defaults") or {})
    if preferred_defaults and secondary_defaults and preferred_defaults != secondary_defaults:
        raise ValueError(
            f"[MERGER] input_defaults 冲突（端口一致但默认值不一致）: key={preferred.get('standard_key')}, "
            f"preferred={preferred_defaults}, secondary={secondary_defaults}"
        )
    merged["input_defaults"] = preferred_defaults or secondary_defaults

    # 合并别名（去重）
    aliases = list(merged.get("aliases") or [])
    for alias in list(secondary.get("aliases") or []):
        alias_text = str(alias or "")
        if alias_text and alias_text not in aliases:
            aliases.append(alias_text)
    merged["aliases"] = aliases

    # 合并作用域（去重）
    scopes = list(merged.get("scopes") or [])
    for scope in list(secondary.get("scopes") or []):
        scope_text = str(scope or "")
        if scope_text and scope_text not in scopes:
            scopes.append(scope_text)
    merged["scopes"] = scopes

    def _merge_port_aliases(preferred_map: Dict[str, Any], secondary_map: Dict[str, Any], direction: str) -> Dict[str, List[str]]:
        merged_map: Dict[str, List[str]] = {}
        alias_to_owner: Dict[str, str] = {}

        for source in [dict(preferred_map or {}), dict(secondary_map or {})]:
            for canonical_port, aliases in source.items():
                canonical_text = str(canonical_port or "").strip()
                if canonical_text == "":
                    continue
                bucket = merged_map.setdefault(canonical_text, [])
                for alias_value in list(aliases or []):
                    alias_text = str(alias_value or "").strip()
                    if alias_text == "":
                        continue
                    prev_owner = alias_to_owner.get(alias_text)
                    if prev_owner is not None and prev_owner != canonical_text:
                        raise ValueError(
                            f"[MERGER] {direction}端口别名冲突: key={preferred.get('standard_key')}, "
                            f"alias={alias_text!r}, ownerA={prev_owner!r}, ownerB={canonical_text!r}"
                        )
                    alias_to_owner[alias_text] = canonical_text
                    if alias_text not in bucket:
                        bucket.append(alias_text)

        stable: Dict[str, List[str]] = {}
        for canonical_text in sorted(merged_map.keys()):
            stable[canonical_text] = sorted(set([v for v in merged_map[canonical_text] if v]))
        return stable

    merged["input_port_aliases"] = _merge_port_aliases(
        dict(merged.get("input_port_aliases") or {}),
        dict(secondary.get("input_port_aliases") or {}),
        "输入",
    )
    merged["output_port_aliases"] = _merge_port_aliases(
        dict(merged.get("output_port_aliases") or {}),
        dict(secondary.get("output_port_aliases") or {}),
        "输出",
    )
    return merged


def merge_specs(valid_items: List[Union[NormalizedSpec, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """
    将通过校验的节点项合并为以标准键 `类别/名称` 为 key 的字典。
    
    约定：
    - server 优先：当同一标准键出现多项时，优先保留 server 版本
    - 端口完全一致：合并别名与作用域
    - 端口不兼容：保留主项为基键；次要项按作用域挂接为 `#{scope}` 变体键
    """
    if not isinstance(valid_items, list):
        raise TypeError("valid_items 必须是列表")

    library_by_key: Dict[str, Dict[str, Any]] = {}
    for item in valid_items:
        # 统一为 dict 视图，便于后续处理
        if isinstance(item, NormalizedSpec):
            item_dict: Dict[str, Any] = item.to_dict()
        elif isinstance(item, dict):
            item_dict = item
        else:
            continue
        key_text = str(item_dict.get("standard_key", "") or "")
        if key_text == "":
            continue
        if key_text not in library_by_key:
            library_by_key[key_text] = item_dict
            continue

        # 已存在：根据优先级与端口兼容性进行处理
        existing = library_by_key[key_text]
        preferred, secondary = _pick_precedence(existing, item_dict)

        # semantic_id 兼容性检查：同一基键的不同作用域实现必须保持相同语义（或其中一侧为空）
        preferred_semantic_id = str(preferred.get("semantic_id") or "").strip()
        secondary_semantic_id = str(secondary.get("semantic_id") or "").strip()
        if preferred_semantic_id and secondary_semantic_id and preferred_semantic_id != secondary_semantic_id:
            raise ValueError(
                f"[MERGER] semantic_id 冲突（同 key 不同实现）: key={key_text}, "
                f"preferred={preferred_semantic_id!r}, secondary={secondary_semantic_id!r}"
            )
        merged_semantic_id = preferred_semantic_id or secondary_semantic_id
        if merged_semantic_id:
            preferred["semantic_id"] = merged_semantic_id
            secondary["semantic_id"] = merged_semantic_id

        if _are_ports_compatible(preferred, secondary):
            library_by_key[key_text] = _merge_same_ports(preferred, secondary)
        else:
            # 端口不兼容：基键保留主项，次要项拆为变体键
            library_by_key[key_text] = preferred
            sec_scopes = list(secondary.get("scopes") or [])
            for scope in sec_scopes:
                scope_text = str(scope or "")
                if scope_text:
                    scoped_key = f"{key_text}#{scope_text}"
                    if scoped_key not in library_by_key:
                        library_by_key[scoped_key] = secondary

    return library_by_key


