from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def get_by_key(index: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    """按标准键 `类别/名称` 获取节点定义。"""
    if not isinstance(index, dict):
        raise TypeError("index 必须是字典")
    return index.get("by_key", {}).get(key) if "by_key" in index else None


def list_by_category(index: Dict[str, Any], category: str) -> List[Tuple[str, Dict[str, Any]]]:
    """列举某类别下的所有节点。"""
    if not isinstance(index, dict):
        raise TypeError("index 必须是字典")
    by_key = index.get("by_key", {})
    result: List[Tuple[str, Dict[str, Any]]] = []
    for node_key, node_item in by_key.items():
        if node_key.startswith(f"{category}/"):
            result.append((node_key, node_item))
    return result


def get_by_alias(index: Dict[str, Any], category: str, name_or_alias: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """按别名或名称获取节点。
    
    优先使用别名映射表命中，未命中则回退为标准键直查。
    """
    if not isinstance(index, dict):
        raise TypeError("index 必须是字典")

    candidate_key = f"{category}/{name_or_alias}"
    alias_to_key = index.get("alias_to_key", {})

    # 先查别名映射
    mapped_key = alias_to_key.get(candidate_key)
    if mapped_key:
        item = get_by_key(index, mapped_key)
        if item is not None:
            return (mapped_key, item)

    # 回退为标准键直查
    item = get_by_key(index, candidate_key)
    if item is not None:
        return (candidate_key, item)

    return None


def find_variants(index: Dict[str, Any], base_key: str) -> List[Tuple[str, Dict[str, Any]]]:
    """查找同一基键下的作用域变体。"""
    if not isinstance(index, dict):
        raise TypeError("index 必须是字典")
    by_key = index.get("by_key", {})
    result: List[Tuple[str, Dict[str, Any]]] = []
    for node_key, node_item in by_key.items():
        if node_key == base_key:
            continue
        if node_key.startswith(f"{base_key}#"):
            result.append((node_key, node_item))
    return result


