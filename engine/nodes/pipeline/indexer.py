from __future__ import annotations

from typing import Dict, Any, Tuple


def build_index(library_by_key: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    基于合并后的字典构建查找索引。
    
    约定：
    - 提供按 key 的直查
    - 提供别名到标准键的映射（同一类别内）
    - 后续可扩展类别清单、作用域变体等
    """
    if not isinstance(library_by_key, dict):
        raise TypeError("library_by_key 必须是字典")

    # 构建别名 -> 标准键 映射（限定在相同类别）
    alias_to_key: Dict[str, str] = {}
    for node_key, node_item in library_by_key.items():
        if not isinstance(node_item, dict):
            continue
        category_standard = str(node_item.get("category_standard", "") or "")
        name_text = str(node_item.get("name", "") or "")
        # 主键自身也记一份映射，便于统一入口
        if category_standard and name_text:
            alias_to_key[f"{category_standard}/{name_text}"] = node_key
        for alias_text in list(node_item.get("aliases") or []):
            alias_str = str(alias_text or "")
            if alias_str:
                alias_to_key[f"{category_standard}/{alias_str}"] = node_key

    return {
        "by_key": library_by_key,
        "alias_to_key": alias_to_key,
    }


