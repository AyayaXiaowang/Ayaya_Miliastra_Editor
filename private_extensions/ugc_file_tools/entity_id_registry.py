from __future__ import annotations

"""
entity_id_registry.py

目标：
- 提供 `entity_key:` / `entity:` 占位符的解析辅助（扫描占位符、抽取 key）。

设计约束：
- 该模块只负责“占位符文本”的解析与 where-used 扫描；
- 不负责从 `.gil` 读取/抽取映射（见 `id_ref_from_gil.py`）。
"""

from typing import Dict


def extract_entity_key_from_placeholder_text(text: str) -> str | None:
    raw = str(text or "").strip()
    lowered = raw.lower()
    if lowered.startswith("entity_key:"):
        key = raw[len("entity_key:") :].strip()
    elif lowered.startswith("entity:"):
        key = raw[len("entity:") :].strip()
    else:
        return None
    return key if key != "" else None


def collect_entity_key_placeholders_from_value(value: object) -> set[str]:
    out: set[str] = set()
    if isinstance(value, str):
        k = extract_entity_key_from_placeholder_text(value)
        if k is not None:
            out.add(str(k))
        return out
    if isinstance(value, list):
        for item in value:
            out |= collect_entity_key_placeholders_from_value(item)
        return out
    if isinstance(value, dict):
        for k, v in value.items():
            out |= collect_entity_key_placeholders_from_value(k)
            out |= collect_entity_key_placeholders_from_value(v)
        return out
    return out


def collect_entity_key_placeholders_from_graph_json_object(*, graph_json_object: Dict[str, object]) -> set[str]:
    from ugc_file_tools.graph.model_ir import iter_node_payload_dicts, normalize_graph_model_payload

    graph_model = normalize_graph_model_payload(graph_json_object)
    if not isinstance(graph_model, dict):
        return set()

    keys: set[str] = set()
    for payload in iter_node_payload_dicts(graph_model):
        input_constants = payload.get("input_constants")
        if isinstance(input_constants, dict):
            keys |= collect_entity_key_placeholders_from_value(input_constants)

    graph_variables = graph_model.get("graph_variables")
    if isinstance(graph_variables, list):
        for v in graph_variables:
            if not isinstance(v, dict):
                continue
            default_value = v.get("default_value")
            keys |= collect_entity_key_placeholders_from_value(default_value)

    return keys


__all__ = [
    "extract_entity_key_from_placeholder_text",
    "collect_entity_key_placeholders_from_value",
    "collect_entity_key_placeholders_from_graph_json_object",
]

