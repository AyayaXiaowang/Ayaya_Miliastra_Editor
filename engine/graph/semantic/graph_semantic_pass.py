from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from engine.graph.common import (
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_NAME_PORT_NAME,
    SIGNAL_SEND_NODE_TITLE,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_BUILD_STATIC_INPUTS,
    STRUCT_MODIFY_NODE_TITLE,
    STRUCT_MODIFY_STATIC_INPUTS,
    STRUCT_NAME_PORT_NAME,
    STRUCT_NODE_TITLES,
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_SPLIT_STATIC_OUTPUTS,
)
from engine.graph.models.graph_model import GraphModel, NodeModel
from engine.struct.binding_schema import normalize_struct_binding_payload

from .constants import (
    SEMANTIC_SIGNAL_ID_CONSTANT_KEY,
    SEMANTIC_STRUCT_ID_CONSTANT_KEY,
    SIGNAL_BINDINGS_METADATA_KEY,
    STRUCT_BINDINGS_METADATA_KEY,
)


def _safe_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _dedupe_preserve_order(values: Sequence[str]) -> List[str]:
    result: List[str] = []
    for raw in values:
        text = _safe_text(raw)
        if not text:
            continue
        if text not in result:
            result.append(text)
    return result


def _ensure_input_constants_dict(node: NodeModel) -> Dict[str, Any]:
    constants = getattr(node, "input_constants", None)
    if not isinstance(constants, dict):
        node.input_constants = {}
        constants = node.input_constants
    return constants


def _extract_struct_dynamic_field_names(node: NodeModel) -> List[str]:
    """基于端口列表推导结构体节点当前“字段集合”（保持出现顺序）。"""
    node_title = _safe_text(getattr(node, "title", ""))
    if node_title == STRUCT_SPLIT_NODE_TITLE:
        static_outputs = set(STRUCT_SPLIT_STATIC_OUTPUTS)
        names = [
            _safe_text(getattr(port, "name", ""))
            for port in (getattr(node, "outputs", None) or [])
            if _safe_text(getattr(port, "name", "")) and _safe_text(getattr(port, "name", "")) not in static_outputs
        ]
        return _dedupe_preserve_order(names)

    if node_title == STRUCT_BUILD_NODE_TITLE:
        static_inputs = set(STRUCT_BUILD_STATIC_INPUTS)
        names = [
            _safe_text(getattr(port, "name", ""))
            for port in (getattr(node, "inputs", None) or [])
            if _safe_text(getattr(port, "name", "")) and _safe_text(getattr(port, "name", "")) not in static_inputs
        ]
        return _dedupe_preserve_order(names)

    if node_title == STRUCT_MODIFY_NODE_TITLE:
        static_inputs = set(STRUCT_MODIFY_STATIC_INPUTS)
        names = [
            _safe_text(getattr(port, "name", ""))
            for port in (getattr(node, "inputs", None) or [])
            if _safe_text(getattr(port, "name", "")) and _safe_text(getattr(port, "name", "")) not in static_inputs
        ]
        return _dedupe_preserve_order(names)

    return []


class GraphSemanticPass:
    """GraphSemanticPass：语义元数据的单一写入阶段。

    责任边界（单点写入）：
    - `GraphModel.metadata["signal_bindings"]`
    - `GraphModel.metadata["struct_bindings"]`

    输入事实来源（Pass 读取）：
    - 节点标题（是否为信号/结构体节点）
    - 节点端口列表（用于推导字段集合）
    - 节点 `input_constants`：
      - 可见选择端口：`信号名` / `结构体名`
      - 隐藏稳定 ID：`__signal_id` / `__struct_id`

    输出策略：
    - **覆盖式重建**：每次运行都会重建整张图的 bindings 映射，并覆盖写回 metadata。
    - **幂等**：在输入不变的前提下重复运行不会产生额外变化。
    """

    @staticmethod
    def apply(model: GraphModel) -> None:
        if not isinstance(getattr(model, "metadata", None), dict):
            model.metadata = {}

        GraphSemanticPass._apply_signal_bindings(model)
        GraphSemanticPass._apply_struct_bindings(model)

    # ---------------------------------------------------------------------
    # signal_bindings
    # ---------------------------------------------------------------------

    @staticmethod
    def _load_signal_payloads() -> Dict[str, Dict[str, Any]]:
        signal_module = import_module("engine.signal")
        get_repo = getattr(signal_module, "get_default_signal_repository")
        repo = get_repo()
        payloads = repo.get_all_payloads()
        return payloads if isinstance(payloads, dict) else {}

    @staticmethod
    def _build_signal_id_by_name(signal_payloads: Mapping[str, Mapping[str, Any]]) -> Dict[str, str]:
        id_by_name: Dict[str, str] = {}
        for signal_id, payload in signal_payloads.items():
            if not isinstance(payload, Mapping):
                continue
            name_text = _safe_text(payload.get("signal_name"))
            if not name_text:
                continue
            # 仅记录首次出现，避免重名信号引入不确定性
            id_by_name.setdefault(name_text, str(signal_id))
        return id_by_name

    @staticmethod
    def _apply_signal_bindings(model: GraphModel) -> None:
        signal_payloads = GraphSemanticPass._load_signal_payloads()
        signal_id_by_name = GraphSemanticPass._build_signal_id_by_name(signal_payloads)

        new_bindings: Dict[str, Dict[str, str]] = {}

        for node_id, node in (getattr(model, "nodes", None) or {}).items():
            node_title = _safe_text(getattr(node, "title", ""))
            if node_title not in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
                continue

            constants = _ensure_input_constants_dict(node)

            # 1) 优先使用“隐藏稳定 ID”
            signal_id = _safe_text(constants.get(SEMANTIC_SIGNAL_ID_CONSTANT_KEY))

            # 2) 最后使用“信号名”常量推导
            if not signal_id:
                literal = _safe_text(constants.get(SIGNAL_NAME_PORT_NAME))
                if literal:
                    if literal in signal_payloads:
                        signal_id = literal
                    else:
                        signal_id = _safe_text(signal_id_by_name.get(literal))

            if not signal_id:
                continue

            new_bindings[str(node_id)] = {"signal_id": str(signal_id)}

            # 回填稳定 ID（隐藏键）
            if _safe_text(constants.get(SEMANTIC_SIGNAL_ID_CONSTANT_KEY)) != str(signal_id):
                constants[SEMANTIC_SIGNAL_ID_CONSTANT_KEY] = str(signal_id)

            # 若“信号名”为空或仍为 ID，则回填显示名（不强行覆盖用户手动填的显示名）
            payload = signal_payloads.get(str(signal_id)) or {}
            display_name = _safe_text(payload.get("signal_name")) if isinstance(payload, dict) else ""
            if display_name:
                current_name = _safe_text(constants.get(SIGNAL_NAME_PORT_NAME))
                if (not current_name) or (current_name == str(signal_id)):
                    constants[SIGNAL_NAME_PORT_NAME] = display_name

        model.metadata[SIGNAL_BINDINGS_METADATA_KEY] = new_bindings

    # ---------------------------------------------------------------------
    # struct_bindings
    # ---------------------------------------------------------------------

    @staticmethod
    def _load_basic_struct_definitions() -> Dict[str, Dict[str, Any]]:
        module = import_module("engine.resources.definition_schema_view")
        get_schema_view = getattr(module, "get_default_definition_schema_view")
        schema_view = get_schema_view()
        all_structs = schema_view.get_all_struct_definitions() or {}

        result: Dict[str, Dict[str, Any]] = {}
        for struct_id, payload in all_structs.items():
            if not isinstance(payload, dict):
                continue
            # 仅保留结构体定义（type=Struct 或未显式标注）
            type_value = payload.get("type")
            if isinstance(type_value, str) and type_value.strip() and type_value.strip() != "Struct":
                continue
            # 仅保留基础结构体（与 UI/校验规则一致）
            struct_type_value = payload.get("struct_ype")
            struct_type = _safe_text(struct_type_value)
            if struct_type and struct_type != "basic":
                continue
            result[str(struct_id)] = dict(payload)
        return result

    @staticmethod
    def _build_struct_id_by_name(structs_by_id: Mapping[str, Mapping[str, Any]]) -> Dict[str, str]:
        id_by_name: Dict[str, str] = {}
        for struct_id, payload in structs_by_id.items():
            if not isinstance(payload, Mapping):
                continue
            # “结构体名”入参只接受结构体定义中的 `struct_name`（唯一名称），不再兼容传 STRUCT_ID 或 name。
            name_text = _safe_text(payload.get("struct_name"))
            if name_text:
                id_by_name.setdefault(name_text, str(struct_id))
        return id_by_name

    @staticmethod
    def _extract_struct_defined_fields(struct_payload: Mapping[str, Any]) -> Set[str]:
        fields: Set[str] = set()

        fields_entries = struct_payload.get("fields")
        if isinstance(fields_entries, Sequence) and not isinstance(fields_entries, (str, bytes)):
            for entry in fields_entries:
                if not isinstance(entry, Mapping):
                    continue
                name_text = _safe_text(entry.get("field_name"))
                if name_text:
                    fields.add(name_text)

        return fields

    @staticmethod
    def _infer_struct_id_by_fields(
        *,
        used_fields: List[str],
        defined_fields_by_id: Mapping[str, Set[str]],
    ) -> str:
        if not used_fields:
            return ""
        candidate_ids: List[str] = []
        for struct_id, defined in defined_fields_by_id.items():
            if not defined:
                continue
            if all(field in defined for field in used_fields):
                candidate_ids.append(str(struct_id))
        if len(candidate_ids) != 1:
            return ""
        return candidate_ids[0]

    @staticmethod
    def _apply_struct_bindings(model: GraphModel) -> None:
        structs_by_id = GraphSemanticPass._load_basic_struct_definitions()
        struct_id_by_name = GraphSemanticPass._build_struct_id_by_name(structs_by_id)

        defined_fields_by_id: Dict[str, Set[str]] = {}
        for struct_id, payload in structs_by_id.items():
            if isinstance(payload, Mapping):
                defined_fields_by_id[str(struct_id)] = GraphSemanticPass._extract_struct_defined_fields(payload)

        new_bindings: Dict[str, Dict[str, Any]] = {}

        for node_id, node in (getattr(model, "nodes", None) or {}).items():
            node_title = _safe_text(getattr(node, "title", ""))
            if node_title not in STRUCT_NODE_TITLES:
                continue

            constants = _ensure_input_constants_dict(node)

            # 端口推导字段集合（用于“反推结构体”与字段列表回写）
            used_fields = _extract_struct_dynamic_field_names(node)

            # 1) 优先使用隐藏稳定 ID
            struct_id = _safe_text(constants.get(SEMANTIC_STRUCT_ID_CONSTANT_KEY))

            # 2) 其次使用结构体名常量推导（只支持 struct_name；不再兼容 struct_id / name）
            if not struct_id:
                struct_name_constant = _safe_text(constants.get(STRUCT_NAME_PORT_NAME))
                if struct_name_constant:
                    struct_id = _safe_text(struct_id_by_name.get(struct_name_constant))

            # 3) 最后尝试“按字段集合反推唯一结构体”（仅在未填写结构体名时启用）
            if not struct_id:
                struct_name_constant = _safe_text(constants.get(STRUCT_NAME_PORT_NAME))
                if not struct_name_constant:
                    inferred_id = GraphSemanticPass._infer_struct_id_by_fields(
                        used_fields=used_fields,
                        defined_fields_by_id=defined_fields_by_id,
                    )
                    if inferred_id:
                        struct_id = inferred_id

            if not struct_id:
                continue

            struct_payload = structs_by_id.get(str(struct_id))
            if isinstance(struct_payload, dict):
                struct_name = (
                    _safe_text(struct_payload.get("struct_name"))
                    or str(struct_id)
                )
                defined_fields = defined_fields_by_id.get(str(struct_id)) or set()
            else:
                struct_name = _safe_text(constants.get(STRUCT_NAME_PORT_NAME)) or str(struct_id)
                defined_fields = set()

            field_names = used_fields
            if defined_fields:
                field_names = [name for name in used_fields if name in defined_fields]

            binding_payload = normalize_struct_binding_payload(
                {
                    "struct_id": str(struct_id),
                    "struct_name": str(struct_name),
                    "field_names": list(field_names),
                }
            )
            new_bindings[str(node_id)] = binding_payload

            # 回填隐藏 ID（稳定锚点）
            if _safe_text(constants.get(SEMANTIC_STRUCT_ID_CONSTANT_KEY)) != str(struct_id):
                constants[SEMANTIC_STRUCT_ID_CONSTANT_KEY] = str(struct_id)

            # 回填结构体名显示常量（仅在为空时补齐）
            current_name = _safe_text(constants.get(STRUCT_NAME_PORT_NAME))
            if not current_name:
                constants[STRUCT_NAME_PORT_NAME] = str(struct_name)

        model.metadata[STRUCT_BINDINGS_METADATA_KEY] = new_bindings


__all__ = ["GraphSemanticPass"]


