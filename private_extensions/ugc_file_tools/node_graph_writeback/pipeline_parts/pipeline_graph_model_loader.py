from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.node_graph_semantics.graph_model import normalize_graph_model_payload as _normalize_graph_model_payload

from ..graph_variables import _normalize_graph_variables_from_graph_json
from .pipeline_graph_variables_autofill import _build_graph_variable_type_text_by_name
from .pipeline_placeholders import (
    _WritebackRequiredPlaceholders,
    _collect_required_placeholders_from_graph_json_object,
    _load_graph_model_json_object,
)
from .pipeline_scope import _infer_scope_from_graph_id_int, _infer_scope_from_graph_json_object


@dataclass(frozen=True, slots=True)
class _GraphModelWritebackInputs:
    graph_json_object: Dict[str, Any]
    graph_model: Dict[str, Any]
    graph_variables: List[Dict[str, Any]]
    graph_variable_type_text_by_name: Dict[str, str]
    placeholders: _WritebackRequiredPlaceholders
    required_ui_keys: set[str]
    layout_name_hint: Optional[str]
    scope: str
    inferred_scope_hint: Optional[str]


def _load_graph_model_writeback_inputs(
    *,
    graph_model_json_path: Path,
    scope_graph_id_int: int,
    scope_graph_id_label: str,
    scope_hint_label: str,
    forbid_id_ref_placeholders: bool,
) -> _GraphModelWritebackInputs:
    graph_json_object = _load_graph_model_json_object(graph_model_json_path=Path(graph_model_json_path))
    placeholders = _collect_required_placeholders_from_graph_json_object(graph_json_object=dict(graph_json_object))
    required_ui_keys = set(placeholders.required_ui_keys)
    layout_name_hint = placeholders.layout_name_hint

    if bool(forbid_id_ref_placeholders) and (placeholders.required_component_names or placeholders.required_entity_names):
        raise ValueError(
            "纯 JSON 写回模式不支持 component_key:/entity_key: 占位符回填。\n"
            f"- graph_model: {str(Path(graph_model_json_path).resolve())}\n"
            "- 解决方案：改用“模板克隆模式”并提供占位符参考 GIL（或在调用 write_graph_model_to_gil 时传入 preloaded_* 映射）。"
        )

    graph_model = _normalize_graph_model_payload(graph_json_object)
    if not isinstance(graph_model, dict):
        raise TypeError("graph_model payload must be dict")

    graph_variables = _normalize_graph_variables_from_graph_json(graph_json_object)
    graph_variable_type_text_by_name = _build_graph_variable_type_text_by_name(list(graph_variables))

    inferred_scope_hint = _infer_scope_from_graph_id_int(int(scope_graph_id_int))
    scope = _infer_scope_from_graph_json_object(
        graph_json_object=graph_json_object,
        default_scope=(inferred_scope_hint or "server"),
    )
    if inferred_scope_hint is not None and str(scope) != str(inferred_scope_hint):
        raise ValueError(
            f"GraphModel.scope 与 {scope_graph_id_label} 的 scope 不一致：graph_scope={scope!r} {scope_hint_label}={inferred_scope_hint!r} {scope_graph_id_label}={int(scope_graph_id_int)}"
        )

    return _GraphModelWritebackInputs(
        graph_json_object=dict(graph_json_object),
        graph_model=dict(graph_model),
        graph_variables=list(graph_variables),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        placeholders=placeholders,
        required_ui_keys=set(required_ui_keys),
        layout_name_hint=(str(layout_name_hint).strip() if layout_name_hint else None),
        scope=str(scope),
        inferred_scope_hint=(str(inferred_scope_hint) if inferred_scope_hint is not None else None),
    )

