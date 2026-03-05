from __future__ import annotations

"""Todo detail_info schema：按 detail_type 显式声明并可运行时校验。

目标：
- 将“每种 detail_type 需要哪些字段”变为可查询/可校验的单一真源；
- 在任务生成阶段尽早暴露破坏性变更（缺字段/错类型/空字符串）；
- 测试期可用 strict 模式强制“所有已产生的 detail_type 都必须有 schema”。
"""

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Sequence

from app.models.resource_task_configs import COMBAT_RESOURCE_CONFIGS, MANAGEMENT_RESOURCE_CONFIGS


@dataclass(frozen=True, slots=True)
class FieldSpec:
    name: str
    expected_types: tuple[type, ...] = ()
    required: bool = True
    allow_none: bool = False
    allow_empty_string: bool = False


@dataclass(frozen=True, slots=True)
class DetailInfoSchema:
    detail_type: str
    fields: tuple[FieldSpec, ...]


def _normalize_detail_type(detail_type: object) -> str:
    if isinstance(detail_type, str):
        return detail_type
    if detail_type is None:
        return ""
    return str(detail_type)


def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted({str(v or "") for v in values if str(v or "")})


def _validate_field(detail_type: str, detail_info: dict, spec: FieldSpec) -> None:
    name = spec.name
    if spec.required and name not in detail_info:
        raise RuntimeError(f"detail_info[{detail_type}] 缺少必填字段: {name}")

    if name not in detail_info:
        return

    value = detail_info.get(name)
    if value is None:
        if spec.allow_none:
            return
        raise RuntimeError(f"detail_info[{detail_type}] 字段为 None: {name}")

    if isinstance(value, str) and value == "" and not spec.allow_empty_string:
        raise RuntimeError(f"detail_info[{detail_type}] 字符串字段为空: {name}")

    if spec.expected_types:
        if not isinstance(value, spec.expected_types):
            expected = ", ".join(t.__name__ for t in spec.expected_types)
            raise RuntimeError(
                f"detail_info[{detail_type}] 字段类型错误: {name} 期望({expected}) 实际({type(value).__name__})"
            )


def _req(name: str, *types: type, allow_empty_string: bool = False) -> FieldSpec:
    return FieldSpec(
        name=str(name or ""),
        expected_types=tuple(types),
        required=True,
        allow_none=False,
        allow_empty_string=bool(allow_empty_string),
    )


def _opt(
    name: str,
    *types: type,
    allow_none: bool = True,
    allow_empty_string: bool = False,
) -> FieldSpec:
    return FieldSpec(
        name=str(name or ""),
        expected_types=tuple(types),
        required=False,
        allow_none=bool(allow_none),
        allow_empty_string=bool(allow_empty_string),
    )


def _req_str(name: str, *, allow_empty_string: bool = False) -> FieldSpec:
    return _req(name, str, allow_empty_string=allow_empty_string)


def _opt_str(
    name: str,
    *,
    allow_none: bool = True,
    allow_empty_string: bool = False,
) -> FieldSpec:
    return _opt(
        name,
        str,
        allow_none=allow_none,
        allow_empty_string=allow_empty_string,
    )


def _req_int(name: str) -> FieldSpec:
    return _req(name, int)


def _req_bool(name: str) -> FieldSpec:
    return _req(name, bool)


def _opt_bool(name: str) -> FieldSpec:
    return _opt(name, bool, allow_none=False)


def _req_list(name: str) -> FieldSpec:
    return _req(name, list)


def _opt_list(name: str) -> FieldSpec:
    return _opt(name, list, allow_none=False)


def _req_dict(name: str) -> FieldSpec:
    return _req(name, dict)


def _req_any(name: str) -> FieldSpec:
    return FieldSpec(name=str(name or ""), expected_types=(), required=True)


def _build_schemas() -> Dict[str, DetailInfoSchema]:
    schemas: Dict[str, DetailInfoSchema] = {}

    def register(detail_type: str, *fields: FieldSpec) -> None:
        normalized = str(detail_type or "")
        if not normalized:
            raise RuntimeError("DetailInfoSchema.detail_type 不能为空")
        if normalized in schemas:
            raise RuntimeError(f"重复注册 DetailInfoSchema: {normalized}")
        schemas[normalized] = DetailInfoSchema(detail_type=normalized, fields=tuple(fields))

    # ------------------------------------------------------------------ shared groups
    _CTX_TEMPLATE_INSTANCE = (
        _opt_str("template_id"),
        _opt_str("instance_id"),
    )
    _NO_AUTO_JUMP_REQUIRED = (_req_bool("no_auto_jump"),)
    _NO_AUTO_JUMP_OPTIONAL = (_opt_bool("no_auto_jump"),)

    # ------------------------------------------------------------------ root/category/template/instance
    register("root", _req_str("package_name"), _req_str("package_id"))
    register("category", _req_str("category"), _req_int("count"))
    register(
        "template",
        _req_str("template_id"),
        _req_str("name"),
        _req_str("entity_type"),
        _opt_str("description", allow_empty_string=True),
    )
    register("template_basic", _req_str("template_id"), _req_dict("config"))
    register("template_variables_table", _req_str("template_id"), _req_list("variables"))
    register("template_components_table", _req_str("template_id"), _req_list("components"))
    register(
        "instance",
        _req_str("instance_id"),
        _req_str("name"),
        _req_str("template_id"),
        _req_str("template_name"),
    )
    register(
        "instance_properties_table",
        _req_str("instance_id"),
        _req_any("position"),
        _req_any("rotation"),
        _req_list("override_variables"),
    )

    # ------------------------------------------------------------------ graph roots / flow roots / steps
    register(
        "template_graph_root",
        _req_str("graph_id"),
        _req_str("graph_name"),
        _req_str("task_type"),
        *_CTX_TEMPLATE_INSTANCE,
        _opt_str("graph_data_key"),
        _opt_bool("no_auto_jump"),
    )
    register("graph_variables_table", _req_list("variables"))
    register(
        "graph_signals_overview",
        _req_str("graph_id"),
        _req_str("graph_name"),
        _req_list("signals"),
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "event_flow_root",
        _req_str("graph_id"),
        _req_str("event_node_id"),
        _req_str("event_node_title"),
        _req_str("graph_root_todo_id"),
        _req_str("task_type"),
        *_CTX_TEMPLATE_INSTANCE,
        *_NO_AUTO_JUMP_OPTIONAL,
    )

    # create / connect / config
    register(
        "graph_create_node",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_create_and_connect",
        _req_str("graph_id"),
        _req_str("prev_node_id"),
        _req_str("prev_node_title"),
        _req_str("node_id"),
        _req_str("node_title"),
        _req_str("edge_id"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_create_and_connect_data",
        _req_str("graph_id"),
        _req_str("target_node_id"),
        _req_str("target_node_title"),
        _req_str("data_node_id"),
        _req_str("data_node_title"),
        _req_str("edge_id"),
        _req_bool("is_copy"),
        _opt_str("original_node_id", allow_empty_string=True),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_config_node_merged",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        _req_list("params"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_set_port_types_merged",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        _req_list("params"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_connect",
        _req_str("graph_id"),
        _req_str("src_node"),
        _req_str("dst_node"),
        _req_str("edge_id"),
        _req_str("src_port"),
        _req_str("dst_port"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_connect_merged",
        _req_str("graph_id"),
        _req_str("node1_id"),
        _req_str("node2_id"),
        _req_str("node1_title"),
        _req_str("node2_title"),
        _req_list("edges"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_config_branch_outputs",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        _req_list("branches"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_add_variadic_inputs",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        _req_int("add_count"),
        _req_list("port_tokens"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_add_dict_pairs",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        _req_int("add_count"),
        _req_list("port_tokens"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_add_branch_outputs",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        _req_int("add_count"),
        _req_list("port_tokens"),
        *_NO_AUTO_JUMP_REQUIRED,
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "graph_bind_signal",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        _opt_str("signal_id", allow_empty_string=True),
        _req_str("signal_name", allow_empty_string=True),
        _opt_list("signal_param_names"),
        *_CTX_TEMPLATE_INSTANCE,
        *_NO_AUTO_JUMP_OPTIONAL,
    )
    register(
        "graph_bind_struct",
        _req_str("graph_id"),
        _req_str("node_id"),
        _req_str("node_title"),
        _opt_str("struct_id", allow_empty_string=True),
        _req_str("struct_name", allow_empty_string=True),
        _req_list("field_names"),
        *_CTX_TEMPLATE_INSTANCE,
        *_NO_AUTO_JUMP_OPTIONAL,
    )

    # ------------------------------------------------------------------ composite
    register(
        "composite_root",
        _req_str("composite_id"),
        _req_str("composite_name"),
        _req_str("graph_id"),
        _req_str("graph_name"),
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "composite_create_new",
        _req_str("composite_id"),
        _req_str("composite_name"),
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "composite_set_meta",
        _req_str("name"),
        _req_str("description", allow_empty_string=True),
        _req_str("folder_path", allow_empty_string=True),
        _req_str("composite_id"),
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "composite_set_pins",
        _req_str("composite_id"),
        _req_list("inputs"),
        _req_list("outputs"),
        _req_int("input_count"),
        _req_int("output_count"),
        *_CTX_TEMPLATE_INSTANCE,
    )
    register(
        "composite_save",
        _req_str("composite_id"),
        *_CTX_TEMPLATE_INSTANCE,
    )

    # ------------------------------------------------------------------ resource tasks (combat/management)
    resource_configs = list(COMBAT_RESOURCE_CONFIGS) + list(MANAGEMENT_RESOURCE_CONFIGS)
    for config in resource_configs:
        detail_type = str(getattr(config, "detail_type", "") or "")
        id_field = str(getattr(config, "id_field", "") or "")
        if not detail_type or not id_field:
            continue
        register(
            detail_type,
            _req_str(id_field),
            _req_any("data"),
            _opt_str("guide", allow_none=False, allow_empty_string=True),
        )

    return schemas


_SCHEMAS_BY_TYPE: Dict[str, DetailInfoSchema] = _build_schemas()


def get_detail_info_schema(detail_type: object) -> Optional[DetailInfoSchema]:
    normalized = _normalize_detail_type(detail_type)
    if not normalized:
        return None
    return _SCHEMAS_BY_TYPE.get(normalized)


def list_registered_detail_info_schema_types() -> list[str]:
    return _sorted_unique(_SCHEMAS_BY_TYPE.keys())


def validate_detail_info(detail_info: object, *, strict: bool = True) -> None:
    if not isinstance(detail_info, dict):
        raise RuntimeError("detail_info 必须为 dict")

    raw_type = detail_info.get("type")
    if not isinstance(raw_type, str) or not raw_type:
        raise RuntimeError("detail_info 字段 type 必须为非空字符串")
    detail_type = raw_type

    schema = _SCHEMAS_BY_TYPE.get(detail_type)
    if schema is None:
        if strict:
            raise RuntimeError(f"detail_info 未注册 schema: {detail_type}")
        return

    for field in schema.fields:
        _validate_field(detail_type, detail_info, field)


