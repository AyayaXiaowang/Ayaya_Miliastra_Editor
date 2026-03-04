from __future__ import annotations

from typing import Any, Dict, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text
from ugc_file_tools.node_graph_semantics.type_binding_plan import (
    build_variant_concrete_plan as _build_variant_concrete_plan,
)

from ..node_property import _build_server_node_property_binary_text
from ..record_codec import _extract_nested_int
from .types import _ConstantsWritebackContext, _ConstantsWritebackNodeState


def _try_extract_existing_node_runtime_id(*, node_obj: Dict[str, Any]) -> Optional[int]:
    node_property_text = node_obj.get("3")
    if not isinstance(node_property_text, str) or not node_property_text.startswith("<binary_data>"):
        return None
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(node_property_text))
    if not isinstance(decoded, dict):
        return None
    runtime_id = _extract_nested_int(decoded, ["field_5"])
    if isinstance(runtime_id, int) and int(runtime_id) > 0:
        return int(runtime_id)
    return None


def patch_node_runtime_id_inplace(*, ctx: _ConstantsWritebackContext, state: _ConstantsWritebackNodeState) -> None:
    # 对齐真源：监听信号“事件节点”（GraphModel: node_def_ref.kind=event 且 outputs 含“信号来源实体”）
    # - 若节点 runtime 仍为通用（300001=监听信号），则不写 concrete_id（避免端口解释漂移）
    # - 若节点 runtime 已切换为 signal-specific（0x4000xxxx/0x6000xxxx...），则允许写入 concrete_id（与 genericId 对齐）
    node_def_ref = state.node_payload.get("node_def_ref")
    if isinstance(node_def_ref, dict) and str(node_def_ref.get("kind") or "").strip().lower() == "event":
        outputs0 = state.node_payload.get("outputs")
        if isinstance(outputs0, list) and any(str(x) == "信号来源实体" for x in outputs0):
            if int(state.node_type_id_int_for_node) < 0x40000000:
                state.node_obj.pop("3", None)
                return

    # 与 gia 导出同口径：当能唯一确定 Variant/Generic 的具体类型时，同步更新节点 concrete_id。
    plan = _build_variant_concrete_plan(
        node_entry_by_id=dict(ctx.node_entry_by_id),
        node_type_id_int=int(state.node_type_id_int_for_node),
        forced_concrete_runtime_id=(int(state.forced_concrete_runtime_id) if isinstance(state.forced_concrete_runtime_id, int) else None),
        variant_primary_vt_candidates=set(int(x) for x in set(state.variant_primary_vt_candidates or set()) if isinstance(x, int)),
    )
    concrete_runtime_id = (
        int(plan.resolved_concrete_runtime_id)
        if isinstance(plan.resolved_concrete_runtime_id, int) and int(plan.resolved_concrete_runtime_id) > 0
        else int(state.node_type_id_int_for_node)
    )

    if (not isinstance(plan.resolved_concrete_runtime_id, int) or int(plan.resolved_concrete_runtime_id) <= 0) and str(
        state.title
    ) == "拼装字典":
        # 兜底：若本轮未能解析出 concrete（例如缺失 key0/value0 类型信息），保留模板已有 concrete，
        # 避免把已实例化的拼装字典回退成 generic(1788) 导致编辑器端口行为漂移。
        existing_runtime_id = _try_extract_existing_node_runtime_id(node_obj=state.node_obj)
        if isinstance(existing_runtime_id, int) and int(existing_runtime_id) > 0:
            concrete_runtime_id = int(existing_runtime_id)

    state.node_obj["3"] = _build_server_node_property_binary_text(node_id_int=int(concrete_runtime_id))

