from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Set

from engine.nodes.port_type_system import BOOLEAN_TYPE_KEYWORDS

from .lookup import (
    get_by_key as lookup_get_by_key,
    get_by_alias as lookup_get_by_alias,
    list_by_category as lookup_list_by_category,
    find_variants as lookup_find_variants,
)


class NodeLibrary:
    """
    对基于管线构建的索引进行封装的查询类。
    
    约定：
    - index 结构由 run_pipeline(workspace_path) 返回
      {
        "by_key": { standard_key: item_dict, ... },
        "alias_to_key": { f"{category}/{alias}": standard_key, ... }
      }
    - 本类不做异常包装，遵循阻断式错误策略
    """

    def __init__(self, index: Dict[str, Any]) -> None:
        if not isinstance(index, dict):
            raise TypeError("index 必须是字典")
        self._index: Dict[str, Any] = index
        self._derived_flow_names: Optional[Set[str]] = None
        self._derived_boolean_names: Optional[Set[str]] = None
        self._derived_variadic_min_args: Optional[Dict[str, int]] = None

    def get_by_key(self, key: str) -> Optional[Dict[str, Any]]:
        """按标准键 `类别/名称` 获取节点定义。"""
        return lookup_get_by_key(self._index, str(key))

    def get_by_alias(self, category: str, name_or_alias: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """按别名或名称获取节点（优先使用别名映射，回退为标准键直查）。"""
        return lookup_get_by_alias(self._index, str(category), str(name_or_alias))

    def list_by_category(self, category: str) -> List[Tuple[str, Dict[str, Any]]]:
        """列举某类别下的所有节点。"""
        return lookup_list_by_category(self._index, str(category))

    def find_variants(self, base_key: str) -> List[Tuple[str, Dict[str, Any]]]:
        """查找同一基键下的作用域变体。"""
        return lookup_find_variants(self._index, str(base_key))

    # ------------------------ 派生集合（仅基础库） ------------------------
    def get_flow_node_names(self) -> Set[str]:
        """
        返回含流程端口的节点名称集合（基于索引 by_key，复合节点不含在内）。
        判定规则与 NodeRegistry 保持一致：
        - input_types/output_types 含“流程”
        - inputs/outputs 名称中包含“流程入/流程出”
        """
        if self._derived_flow_names is not None:
            return self._derived_flow_names
        by_key: Dict[str, Dict[str, Any]] = dict(self._index.get("by_key", {}))
        names: Set[str] = set()
        for _, item in by_key.items():
            if not isinstance(item, dict):
                continue
            name_text = str(item.get("name", "") or "")
            if name_text == "":
                continue
            input_types = dict(item.get("input_types") or {})
            output_types = dict(item.get("output_types") or {})
            inputs = list(item.get("inputs") or [])
            outputs = list(item.get("outputs") or [])
            has_flow = (
                any((isinstance(t, str) and ("流程" in t)) for t in input_types.values()) or
                any((isinstance(t, str) and ("流程" in t)) for t in output_types.values()) or
                ("流程入" in inputs) or
                ("流程出" in outputs)
            )
            if has_flow:
                names.add(name_text)
        self._derived_flow_names = names
        return names

    def get_boolean_node_names(self) -> Set[str]:
        """返回输出端包含布尔类型的节点名称集合（基于索引 by_key，复合节点不含在内）。"""
        if self._derived_boolean_names is not None:
            return self._derived_boolean_names
        by_key: Dict[str, Dict[str, Any]] = dict(self._index.get("by_key", {}))
        names: Set[str] = set()
        for _, item in by_key.items():
            if not isinstance(item, dict):
                continue
            name_text = str(item.get("name", "") or "")
            if name_text == "":
                continue
            output_types = dict(item.get("output_types") or {})
            for _, port_type in output_types.items():
                if isinstance(port_type, str) and any(k in port_type for k in BOOLEAN_TYPE_KEYWORDS):
                    names.add(name_text)
                    break
        self._derived_boolean_names = names
        return names

    def get_variadic_min_args(self) -> Dict[str, int]:
        """
        返回节点名到“最少实参数”的映射（基于 inputs 中是否存在多个范围占位）。
        - 若存在 1 个范围占位（如“0~99”）→ 1
        - 若存在 >=2 个范围占位 → 2
        """
        if self._derived_variadic_min_args is not None:
            return self._derived_variadic_min_args
        by_key: Dict[str, Dict[str, Any]] = dict(self._index.get("by_key", {}))
        rules: Dict[str, int] = {}
        for _, item in by_key.items():
            if not isinstance(item, dict):
                continue
            name_text = str(item.get("name", "") or "")
            if name_text == "":
                continue
            inputs = list(item.get("inputs") or [])
            if not inputs:
                continue
            variadic_inputs: List[str] = [str(inp) for inp in inputs if "~" in str(inp)]
            if not variadic_inputs:
                continue
            if len(variadic_inputs) == 1:
                rules[name_text] = 1
            else:
                rules[name_text] = 2
        self._derived_variadic_min_args = rules
        return rules


