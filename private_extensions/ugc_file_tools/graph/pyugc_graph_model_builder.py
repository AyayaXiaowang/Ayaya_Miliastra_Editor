from __future__ import annotations

"""
pyugc_graph_model_builder.py

将项目存档导出的 `pyugc_graphs/graph_*.json`（含 records base64）转换为 Graph_Generater 的 `engine.graph.models.GraphModel`。

定位：
- 本模块是 **pyugc → GraphModel** 的库层单一真源；
- GraphModel → Graph Code 的生成统一由 `app.codegen.ExecutableCodeGenerator` 负责（ugc_file_tools 仅做薄封装/调用）。
"""

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.repo_paths import resolve_graph_generater_root


def _infer_graph_scope_from_id_int(graph_id_int: int) -> str:
    masked_value = int(graph_id_int) & 0xFF800000
    if masked_value == 0x40000000:
        return "server"
    if masked_value == 0x40800000:
        return "client"
    return "unknown"


def infer_graph_scope_from_id_int(graph_id_int: int) -> str:
    """根据 graph_id_int 的高位前缀推断 scope：server/client/unknown。"""
    return _infer_graph_scope_from_id_int(int(graph_id_int))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _decode_base64_bytes(base64_text: str) -> bytes:
    cleaned = str(base64_text or "").strip()
    padding = "=" * ((4 - (len(cleaned) % 4)) % 4)
    return base64.b64decode(cleaned + padding)


def _get_nested_int(decoded: Dict[str, Any], path: Sequence[str]) -> Optional[int]:
    cursor: Any = decoded
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    if not isinstance(cursor, dict):
        return None
    value = cursor.get("int")
    return int(value) if isinstance(value, int) else None


def _load_node_type_semantic_map(mapping_path: Path) -> Dict[int, Dict[str, Any]]:
    mapping_object = _load_json(mapping_path)
    if not isinstance(mapping_object, dict):
        raise TypeError(f"node_type_semantic_map must be dict: {str(mapping_path)!r}")
    result: Dict[int, Dict[str, Any]] = {}
    for key, value in mapping_object.items():
        if isinstance(key, int):
            type_id_int = int(key)
        elif isinstance(key, str) and key.strip().isdigit():
            type_id_int = int(key.strip())
        else:
            continue
        if isinstance(value, dict):
            result[type_id_int] = dict(value)
    return result


def load_node_type_semantic_map(mapping_path: Path) -> Dict[int, Dict[str, Any]]:
    """加载 type_id_int → 节点语义映射（兼容 key 为 str/int）。"""
    return _load_node_type_semantic_map(Path(mapping_path))


def _find_pyugc_graph_json_for_graph_id(package_root: Path, graph_id_int: int) -> Path:
    index_path = package_root / "节点图" / "原始解析" / "pyugc_graphs_index.json"
    index_obj = _load_json(index_path)
    if not isinstance(index_obj, list):
        raise TypeError(f"pyugc_graphs_index.json format error: {str(index_path)!r}")
    for entry in index_obj:
        if not isinstance(entry, dict):
            continue
        if entry.get("graph_id_int") != int(graph_id_int):
            continue
        output_value = entry.get("output")
        if not isinstance(output_value, str) or output_value.strip() == "":
            raise ValueError(f"graph index missing output: graph_id_int={graph_id_int}")
        graph_path = (package_root / Path(output_value)).resolve()
        if not graph_path.is_file():
            raise FileNotFoundError(f"pyugc graph json not found: {str(graph_path)!r}")
        return graph_path
    raise FileNotFoundError(f"graph_id_int not found in pyugc_graphs_index.json: {graph_id_int}")


def find_pyugc_graph_json_for_graph_id(package_root: Path, graph_id_int: int) -> Path:
    """从 `pyugc_graphs_index.json` 定位 graph_*.json 的绝对路径。"""
    return _find_pyugc_graph_json_for_graph_id(Path(package_root), int(graph_id_int))


@dataclass(frozen=True, slots=True)
class _ResolvedNodeDef:
    node_key: str
    node_def: Any


def _resolve_node_def_by_name(
    node_name: str,
    *,
    node_library: Dict[str, Any],
    node_name_index: Dict[str, str],
) -> _ResolvedNodeDef:
    node_name_text = str(node_name or "").strip()
    if node_name_text == "":
        raise ValueError("node_name is empty")
    node_key = node_name_index.get(node_name_text)
    if not isinstance(node_key, str) or node_key.strip() == "":
        raise KeyError(f"node name not found in node_name_index: {node_name_text!r}")
    node_def = node_library.get(node_key)
    if node_def is None:
        raise KeyError(f"node key not found in node_library: {node_key!r}")
    return _ResolvedNodeDef(node_key=node_key, node_def=node_def)


def _is_flow_port_name(port_name: str) -> bool:
    from engine.utils.graph.graph_utils import is_flow_port_name as _is_flow

    return bool(_is_flow(str(port_name or "")))


def _iter_flow_input_ports(node_def: Any) -> List[str]:
    return [str(p) for p in list(getattr(node_def, "inputs", []) or []) if _is_flow_port_name(str(p))]


def _iter_flow_output_ports(node_def: Any) -> List[str]:
    return [str(p) for p in list(getattr(node_def, "outputs", []) or []) if _is_flow_port_name(str(p))]


def _iter_data_input_ports(node_def: Any) -> List[str]:
    return [str(p) for p in list(getattr(node_def, "inputs", []) or []) if not _is_flow_port_name(str(p))]


def _iter_data_output_ports(node_def: Any) -> List[str]:
    return [str(p) for p in list(getattr(node_def, "outputs", []) or []) if not _is_flow_port_name(str(p))]


def _has_range_input_ports(node_def: Any) -> bool:
    inputs = list(getattr(node_def, "inputs", []) or [])
    return any("~" in str(p) for p in inputs)


def _map_slot_to_input_port_name(
    *,
    node_title: str,
    node_def: Any,
    slot_index_int: int,
) -> str:
    """
    将 pyugc record 中的 slot_index 映射到 GraphModel 端口名。

    约定（由 test4 校准图观测总结）：
    - 普通固定端口：slot_index 为 0-based，按“数据输入端口序列（不含流程端口）”索引；
    - 变参端口（如 拼装列表/拼装字典）：slot_index 通常从 1 开始（0 可能用于内部计数/占位），
      需映射为实际端口实例名（如 '0','1' 或 '键0','值0'）。
    """
    title = str(node_title or "").strip()
    if title == "":
        raise ValueError("node_title is empty")
    if not isinstance(slot_index_int, int):
        raise TypeError("slot_index_int must be int")

    if title == "拼装列表":
        if slot_index_int <= 0:
            raise ValueError(f"拼装列表 slot_index must be >=1, got {slot_index_int}")
        return str(int(slot_index_int) - 1)

    if title == "拼装字典":
        if slot_index_int <= 0:
            raise ValueError(f"拼装字典 slot_index must be >=1, got {slot_index_int}")
        # 约定：键0/值0/键1/值1... 交错排列
        zero_based = int(slot_index_int) - 1
        pair_index = int(zero_based // 2)
        in_pair = int(zero_based % 2)
        return f"键{pair_index}" if in_pair == 0 else f"值{pair_index}"

    data_inputs = _iter_data_input_ports(node_def)
    if int(slot_index_int) < 0:
        raise IndexError(f"data input slot out of range: {title!r} slot={slot_index_int} inputs={data_inputs!r}")

    # 主路径：0-based（大量节点实测如此）
    if int(slot_index_int) < len(data_inputs):
        return str(data_inputs[int(slot_index_int)])

    # 兼容：少数节点（如多输出数据节点）在 record 中出现 1-based slot（slot=1 表示第 0 个输入）
    # 只在“越界但 -1 后可落入范围”时触发，避免误映射。
    if int(slot_index_int) - 1 >= 0 and int(slot_index_int) - 1 < len(data_inputs):
        return str(data_inputs[int(slot_index_int) - 1])

    raise IndexError(f"data input slot out of range: {title!r} slot={slot_index_int} inputs={data_inputs!r}")


def _map_slot_to_output_port_name(
    *,
    node_title: str,
    node_def: Any,
    slot_index_int: int,
) -> str:
    title = str(node_title or "").strip()
    if title == "":
        raise ValueError("node_title is empty")
    if not isinstance(slot_index_int, int):
        raise TypeError("slot_index_int must be int")

    data_outputs = _iter_data_output_ports(node_def)
    if int(slot_index_int) < 0 or int(slot_index_int) >= len(data_outputs):
        raise IndexError(f"data output slot out of range: {title!r} slot={slot_index_int} outputs={data_outputs!r}")
    return str(data_outputs[int(slot_index_int)])


def _extract_record_literal_value(decoded_record: Dict[str, Any]) -> Any:
    """
    从 record.decoded 中提取“常量值”。

    实测：常量值通常出现在 field_3.message 的以下字段之一（可能嵌套在 field_110.message 内）：
    - field_101.message.field_1.int
    - field_102.message.field_1.int
    - field_104.message.field_1.fixed32_float
    - field_105.message.field_1.utf8
    """
    field_3 = decoded_record.get("field_3")
    if not isinstance(field_3, dict):
        return None

    # 兼容：部分 string 常量 record 直接落在 field_3.utf8（无 message 包裹）
    if "utf8" in field_3 and isinstance(field_3.get("utf8"), str):
        raw_text = str(field_3.get("utf8") or "").strip()
        if raw_text != "":
            # 经验：某些 payload 前缀会被 decode_gil 误当成可打印字符（例如 \")\\n'），
            # 这里提取“最像业务字符串”的 token（中文/字母数字/下划线）。
            tokens = re.findall(r"[0-9A-Za-z_\u4e00-\u9fff]+", raw_text)
            if tokens:
                return max(tokens, key=len)
            return raw_text

    field_3_msg = field_3.get("message")
    if not isinstance(field_3_msg, dict):
        return None

    # 兼容：枚举/布尔值/阵营 等“变体编码”常量（仅在无法提取到其它常量字段时启用）：
    # - field_3.message.field_4.message.field_100.message.field_1.int 是类型码（例如：14=枚举, 4=布尔值, 17=阵营）
    # - field_3.message.field_4.message.field_1.int 是“值”（通常为小整数）
    variant_type_code = _get_nested_int(
        decoded_record,
        ["field_3", "message", "field_4", "message", "field_100", "message", "field_1"],
    )
    variant_value_int = _get_nested_int(
        decoded_record,
        ["field_3", "message", "field_4", "message", "field_1"],
    )

    candidates: List[Any] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, dict):
            # 直接命中“值字段”
            for key in ("field_101", "field_102", "field_104", "field_105"):
                payload = obj.get(key)
                if not isinstance(payload, dict):
                    continue
                msg = payload.get("message")
                if not isinstance(msg, dict):
                    continue
                leaf = msg.get("field_1")
                if not isinstance(leaf, dict):
                    continue
                if "utf8" in leaf and isinstance(leaf.get("utf8"), str):
                    candidates.append(leaf.get("utf8"))
                elif "fixed32_float" in leaf and isinstance(leaf.get("fixed32_float"), float):
                    candidates.append(float(leaf.get("fixed32_float")))
                elif "fixed64_double" in leaf and isinstance(leaf.get("fixed64_double"), float):
                    candidates.append(float(leaf.get("fixed64_double")))
                elif "int" in leaf and isinstance(leaf.get("int"), int):
                    candidates.append(int(leaf.get("int")))

            # 额外：若 decode_gil 将某些字符串错误解为 message，修复后可能出现通用 utf8 节点
            if "utf8" in obj and isinstance(obj.get("utf8"), str) and obj.get("utf8").strip() != "":
                candidates.append(str(obj.get("utf8")).strip())

            for v in obj.values():
                walk(v)
            return

        if isinstance(obj, list):
            for v in obj:
                walk(v)
            return

    walk(field_3_msg)

    # 去重但保序
    unique: List[Any] = []
    seen: set[str] = set()
    for v in candidates:
        key = repr(v)
        if key in seen:
            continue
        seen.add(key)
        unique.append(v)

    if not unique:
        # 只对已确认的“变体编码类型码”启用，避免覆盖 float/int 等正常字段（例如 type_code=5 常伴随 field_104）。
        if variant_type_code in {4, 14, 17} and isinstance(variant_value_int, int):
            return int(variant_value_int)
        return None
    if len(unique) == 1:
        return unique[0]

    # 多个候选：优先选择“更像业务常量”的那一个（字符串优先，其次较大的数字）
    str_candidates = [v for v in unique if isinstance(v, str) and v.strip() != ""]
    if str_candidates:
        return str_candidates[0]
    num_candidates = [v for v in unique if isinstance(v, (int, float))]
    if num_candidates:
        return sorted(num_candidates, key=lambda x: float(x), reverse=True)[0]
    return unique[0]


def build_graph_model_from_pyugc_graph(
    *,
    package_root: Path,
    graph_id_int: int,
    mapping_path: Path,
) -> Tuple[Any, Dict[str, Any]]:
    """
    将 pyugc_graphs/graph_*.json（含 records base64）转换为 Graph_Generater 的 GraphModel。
    """
    graph_scope = _infer_graph_scope_from_id_int(graph_id_int)
    if graph_scope not in {"server", "client"}:
        raise ValueError(f"unsupported graph_scope: {graph_scope!r}")

    graph_path = _find_pyugc_graph_json_for_graph_id(package_root, graph_id_int)
    graph_payload = _load_json(graph_path)
    if not isinstance(graph_payload, dict):
        raise TypeError(f"pyugc graph json must be dict: {str(graph_path)!r}")

    decoded_nodes = graph_payload.get("decoded_nodes")
    if not isinstance(decoded_nodes, list):
        raise TypeError(f"decoded_nodes missing or invalid: {str(graph_path)!r}")

    mapping = _load_node_type_semantic_map(mapping_path)

    graph_generater_root = resolve_graph_generater_root(package_root)

    import sys

    graph_root_text = str(graph_generater_root.resolve())
    if graph_root_text not in sys.path:
        sys.path.insert(0, graph_root_text)

    from engine.configs.settings import settings
    from engine.graph.common import node_name_index_from_library
    from engine.graph.models import GraphModel, NodeModel, PortModel
    from engine.nodes.node_registry import get_node_registry

    settings.set_config_path(graph_generater_root.resolve())

    registry = get_node_registry(graph_generater_root.resolve(), include_composite=True)
    node_library = registry.get_library()
    node_name_index = node_name_index_from_library(node_library, scope=graph_scope)

    # GraphModel
    graph_model = GraphModel()
    graph_model.graph_name = str(graph_payload.get("graph_name") or "").strip()
    graph_model.graph_id = f"{graph_scope}_graph_{int(graph_id_int)}__{package_root.name}"

    # 预创建节点（id 使用 node_id_int，便于对齐与调试）
    node_def_by_node_id: Dict[int, _ResolvedNodeDef] = {}
    node_model_by_node_id: Dict[int, Any] = {}

    missing_type_ids: Dict[int, List[int]] = {}

    for node_payload in decoded_nodes:
        if not isinstance(node_payload, dict):
            continue
        node_id_value = node_payload.get("node_id_int")
        if not isinstance(node_id_value, int):
            continue
        node_id_int = int(node_id_value)

        pos_object = node_payload.get("pos")
        pos_x = 0.0
        pos_y = 0.0
        if isinstance(pos_object, dict):
            pos_x = float(pos_object.get("x", 0.0) or 0.0)
            pos_y = float(pos_object.get("y", 0.0) or 0.0)

        type_id_int = None
        data_2 = node_payload.get("data_2")
        if isinstance(data_2, dict):
            decoded_2 = data_2.get("decoded")
            if isinstance(decoded_2, dict):
                field_5 = decoded_2.get("field_5")
                if isinstance(field_5, dict) and isinstance(field_5.get("int"), int):
                    type_id_int = int(field_5.get("int"))
        if not isinstance(type_id_int, int):
            raise ValueError(f"node missing type id: node_id_int={node_id_int}")

        mapped = mapping.get(int(type_id_int)) or {}
        node_name = str(mapped.get("graph_generater_node_name") or "").strip()
        if node_name == "":
            missing_type_ids.setdefault(int(type_id_int), []).append(int(node_id_int))
            node_name = f"未识别节点类型_{int(type_id_int)}"

        if node_name.startswith("未识别节点类型_"):
            # 先占位创建，等统一报错
            node_def_by_node_id[node_id_int] = _ResolvedNodeDef(node_key="", node_def=None)
            node_model_by_node_id[node_id_int] = NodeModel(
                id=f"node_{node_id_int}",
                title=node_name,
                category="",
                pos=(pos_x, pos_y),
            )
            graph_model.nodes[node_model_by_node_id[node_id_int].id] = node_model_by_node_id[node_id_int]
            continue

        # 伪节点：常量源（Graph Code 中不会以“节点函数调用”体现，而应被编译为目标端口的 input_constants）
        # 说明：这类节点在资源库节点定义中通常不存在（因此无法 resolve NodeDef）。
        if node_name.startswith("常量_"):
            node_def_by_node_id[node_id_int] = _ResolvedNodeDef(node_key="", node_def=None)
            node_model = NodeModel(
                id=f"node_{node_id_int}",
                title=str(node_name),
                category="常量",
                pos=(pos_x, pos_y),
            )
            node_model.inputs = []
            node_model.outputs = []
            node_model._rebuild_port_maps()
            node_model_by_node_id[node_id_int] = node_model
            # 仍加入 graph_model.nodes 便于调试；后续会把“从该常量节点发出的 data edge”折叠为 input_constants
            graph_model.nodes[node_model.id] = node_model
            continue

        resolved = _resolve_node_def_by_name(
            node_name,
            node_library=node_library,
            node_name_index=node_name_index,
        )
        node_def_by_node_id[node_id_int] = resolved

        node_model = NodeModel(
            id=f"node_{node_id_int}",
            title=str(node_name),
            category=str(getattr(resolved.node_def, "category", "") or ""),
            pos=(pos_x, pos_y),
        )

        # 端口：对于变参输入节点（拼装列表/拼装字典），先延迟到 record 解析阶段按需补齐输入口；
        # 其它节点直接从 NodeDef 同步全量端口（便于后续端口名索引）。
        if _has_range_input_ports(resolved.node_def) and node_model.title in {"拼装列表", "拼装字典"}:
            node_model.inputs = []
        else:
            node_model.inputs = [PortModel(name=str(p), is_input=True) for p in list(getattr(resolved.node_def, "inputs", []) or [])]
        node_model.outputs = [PortModel(name=str(p), is_input=False) for p in list(getattr(resolved.node_def, "outputs", []) or [])]
        node_model._rebuild_port_maps()

        node_model_by_node_id[node_id_int] = node_model
        graph_model.nodes[node_model.id] = node_model

    if missing_type_ids:
        missing_lines = []
        for tid, node_ids in sorted(missing_type_ids.items(), key=lambda kv: kv[0]):
            missing_lines.append(f"- type_id={tid}: nodes={sorted(node_ids)}")
        raise KeyError(
            "node_type_semantic_map 缺少节点类型映射（无法生成 GraphModel/Graph Code）：\n"
            + "\n".join(missing_lines)
            + f"\n(mapping_file={str(mapping_path)!r})"
        )

    # record base64 → decoded
    from ugc_file_tools.decode_gil import decode_bytes_to_python

    node_id_set = {int(nid) for nid in node_model_by_node_id.keys()}

    def ensure_input_port(node_model: Any, port_name: str) -> None:
        if node_model.get_input_port(port_name) is not None:
            return
        node_model.add_input_port(str(port_name))

    def normalize_input_constant_value(
        *,
        node_title: str,
        node_def: Any,
        port_name: str,
        value: Any,
    ) -> Any:
        expected_type = str(node_def.get_port_type(str(port_name), is_input=True) or "").strip()

        # 枚举：record 常以小整数编码（0-based 或 1-based），需要映射为枚举字面量字符串
        if expected_type == "枚举":
            enum_options = getattr(node_def, "input_enum_options", {}) or {}
            candidates = enum_options.get(str(port_name))
            if isinstance(value, int) and isinstance(candidates, list) and len(candidates) > 0:
                index0 = int(value)
                index1 = int(value) - 1
                if 0 <= index0 < len(candidates):
                    return str(candidates[index0])
                if 0 <= index1 < len(candidates):
                    return str(candidates[index1])
                raise IndexError(
                    f"enum value out of range: node={node_title!r} port={port_name!r} "
                    f"value={value} options={candidates!r}"
                )
            return value

        # 布尔值：record 常以 0/1 或 1/2 编码，这里优先按 0/1 解释
        if expected_type == "布尔值":
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                if value in (0, 1):
                    return bool(value)
                if value in (1, 2):
                    return bool(int(value) - 1)
                return bool(value)
            if isinstance(value, str):
                text = value.strip()
                if text in ("0", "1"):
                    return text == "1"
            return value

        return value

    # 常量节点：预先解析其 literal 值，供 data edge 折叠为 input_constants 使用
    const_value_by_node_id: Dict[int, Any] = {}
    for node_payload in decoded_nodes:
        if not isinstance(node_payload, dict):
            continue
        node_id_value = node_payload.get("node_id_int")
        if not isinstance(node_id_value, int):
            continue
        node_id_int = int(node_id_value)
        node_model = node_model_by_node_id.get(node_id_int)
        if node_model is None:
            continue
        if not str(getattr(node_model, "title", "") or "").startswith("常量_"):
            continue
        records = node_payload.get("records")
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            base64_text = record.get("base64")
            if not isinstance(base64_text, str) or base64_text.strip() == "":
                continue
            decoded = decode_bytes_to_python(_decode_base64_bytes(base64_text))
            if not isinstance(decoded, dict):
                continue
            literal = _extract_record_literal_value(decoded)
            if literal is None:
                continue
            const_value_by_node_id[node_id_int] = literal
            break

    # edges & constants
    for node_payload in decoded_nodes:
        if not isinstance(node_payload, dict):
            continue
        node_id_value = node_payload.get("node_id_int")
        if not isinstance(node_id_value, int):
            continue
        dst_node_id_int = int(node_id_value)
        dst_node_model = node_model_by_node_id.get(dst_node_id_int)
        dst_node_def = node_def_by_node_id.get(dst_node_id_int)
        if dst_node_model is None or dst_node_def is None or dst_node_def.node_def is None:
            continue

        records = node_payload.get("records")
        if not isinstance(records, list):
            continue

        for record in records:
            if not isinstance(record, dict):
                continue
            base64_text = record.get("base64")
            if not isinstance(base64_text, str) or base64_text.strip() == "":
                continue
            decoded = decode_bytes_to_python(_decode_base64_bytes(base64_text))
            if not isinstance(decoded, dict):
                continue

            other_node_id_int = _get_nested_int(decoded, ["field_5", "message", "field_1"])
            local_group_int = _get_nested_int(decoded, ["field_4"])
            is_flow_edge = isinstance(other_node_id_int, int) and not isinstance(local_group_int, int)
            is_data_edge = isinstance(other_node_id_int, int) and isinstance(local_group_int, int)

            # flow edge: record on src node
            if is_flow_edge:
                src_node_id_int = dst_node_id_int
                dst_flow_node_id_int = int(other_node_id_int)
                if dst_flow_node_id_int not in node_id_set:
                    continue

                src_node_model = node_model_by_node_id.get(src_node_id_int)
                src_node_def = node_def_by_node_id.get(src_node_id_int)
                if src_node_model is None or src_node_def is None or src_node_def.node_def is None:
                    continue

                dst_node_model_flow = node_model_by_node_id.get(dst_flow_node_id_int)
                dst_node_def_flow = node_def_by_node_id.get(dst_flow_node_id_int)
                if dst_node_model_flow is None or dst_node_def_flow is None or dst_node_def_flow.node_def is None:
                    continue

                src_branch = _get_nested_int(decoded, ["field_1", "message", "field_2"])
                src_branch_index = int(src_branch) if isinstance(src_branch, int) else 0

                src_flow_ports = _iter_flow_output_ports(src_node_def.node_def)
                if src_branch_index < 0 or src_branch_index >= len(src_flow_ports):
                    raise IndexError(f"flow output branch out of range: node={src_node_model.title!r} branch={src_branch_index} ports={src_flow_ports!r}")

                dst_branch = _get_nested_int(decoded, ["field_5", "message", "field_2", "message", "field_2"])
                dst_branch_index = int(dst_branch) if isinstance(dst_branch, int) else 0

                dst_flow_ports = _iter_flow_input_ports(dst_node_def_flow.node_def)
                if not dst_flow_ports:
                    raise ValueError(f"flow target node has no flow input ports: {dst_node_model_flow.title!r}")
                if dst_branch_index < 0 or dst_branch_index >= len(dst_flow_ports):
                    raise IndexError(f"flow input branch out of range: node={dst_node_model_flow.title!r} branch={dst_branch_index} ports={dst_flow_ports!r}")

                edge_id = graph_model.gen_id("edge")
                from engine.graph.models import EdgeModel
                graph_model.edges[edge_id] = EdgeModel(
                    id=edge_id,
                    src_node=src_node_model.id,
                    src_port=str(src_flow_ports[src_branch_index]),
                    dst_node=dst_node_model_flow.id,
                    dst_port=str(dst_flow_ports[dst_branch_index]),
                )
                continue

            # data edge: record on dst node
            if is_data_edge:
                src_node_id_int = int(other_node_id_int)
                if src_node_id_int not in node_id_set:
                    continue
                src_node_model = node_model_by_node_id.get(src_node_id_int)
                src_node_def = node_def_by_node_id.get(src_node_id_int)
                if src_node_model is None or src_node_def is None:
                    continue

                src_is_constant = (src_node_def.node_def is None) and str(src_node_model.title).startswith("常量_")
                if src_node_def.node_def is None and not src_is_constant:
                    continue

                dst_slot = _get_nested_int(decoded, ["field_1", "message", "field_2"])
                dst_slot_index = int(dst_slot) if isinstance(dst_slot, int) else 0

                src_slot = _get_nested_int(decoded, ["field_5", "message", "field_2", "message", "field_2"])
                if not isinstance(src_slot, int):
                    src_slot = _get_nested_int(decoded, ["field_5", "message", "field_3", "message", "field_2"])
                src_slot_index = int(src_slot) if isinstance(src_slot, int) else 0

                dst_port_name = _map_slot_to_input_port_name(
                    node_title=dst_node_model.title,
                    node_def=dst_node_def.node_def,
                    slot_index_int=dst_slot_index,
                )

                if dst_node_model.title in {"拼装列表", "拼装字典"}:
                    ensure_input_port(dst_node_model, dst_port_name)

                # 常量源节点：折叠为目标端口的 input_constants（不创建 data edge）
                if src_is_constant:
                    const_value = const_value_by_node_id.get(src_node_id_int)
                    if const_value is None:
                        raise ValueError(f"constant node has no literal value: node_id_int={src_node_id_int}")
                    normalized = normalize_input_constant_value(
                        node_title=dst_node_model.title,
                        node_def=dst_node_def.node_def,
                        port_name=str(dst_port_name),
                        value=const_value,
                    )
                    dst_node_model.input_constants[str(dst_port_name)] = normalized
                    continue

                if src_node_def.node_def is None:
                    continue

                src_port_name = _map_slot_to_output_port_name(
                    node_title=src_node_model.title,
                    node_def=src_node_def.node_def,
                    slot_index_int=src_slot_index,
                )

                edge_id = graph_model.gen_id("edge")
                from engine.graph.models import EdgeModel
                graph_model.edges[edge_id] = EdgeModel(
                    id=edge_id,
                    src_node=src_node_model.id,
                    src_port=str(src_port_name),
                    dst_node=dst_node_model.id,
                    dst_port=str(dst_port_name),
                )
                continue

            # constant record (no field_5): bind input_constants
            slot = _get_nested_int(decoded, ["field_1", "message", "field_2"])
            if not isinstance(slot, int):
                # 常见编码：第 0 个输入端口用“缺省 field_2”表示；仅对变参节点保守跳过（其 slot=None 常为计数/占位）。
                if dst_node_model.title in {"拼装列表", "拼装字典"}:
                    continue
                slot_index = 0
            else:
                slot_index = int(slot)
            port_name = _map_slot_to_input_port_name(
                node_title=dst_node_model.title,
                node_def=dst_node_def.node_def,
                slot_index_int=slot_index,
            )
            value = _extract_record_literal_value(decoded)
            if value is None:
                continue

            value = normalize_input_constant_value(
                node_title=dst_node_model.title,
                node_def=dst_node_def.node_def,
                port_name=str(port_name),
                value=value,
            )

            if dst_node_model.title in {"拼装列表", "拼装字典"}:
                ensure_input_port(dst_node_model, port_name)

            dst_node_model.input_constants[str(port_name)] = value

    # 端口缓存重建（变参节点在解析阶段可能动态增删输入口）
    for node in graph_model.nodes.values():
        if hasattr(node, "_rebuild_port_maps"):
            node._rebuild_port_maps()

    # 图变量推断：pyugc_graphs 原始结构中不直接携带 GRAPH_VARIABLES，因此这里从“获取/设置节点图变量”节点的使用中推断。
    # 目的：
    # - 生成代码级 GRAPH_VARIABLES，满足校验规则（CODE_GRAPH_VAR_DECLARATION）
    # - 为“获取节点图变量”的输出类型推断提供依据（避免泛型输出必须手写注解）
    graph_vars_by_name: Dict[str, Dict[str, Any]] = {}
    for node in graph_model.nodes.values():
        title = str(getattr(node, "title", "") or "").strip()
        if title not in {"设置节点图变量", "获取节点图变量"}:
            continue
        input_constants = getattr(node, "input_constants", {}) or {}
        var_name_value = input_constants.get("变量名")
        if not isinstance(var_name_value, str) or var_name_value.strip() == "":
            continue
        var_name = var_name_value.strip()

        entry = graph_vars_by_name.get(var_name)
        if entry is None:
            entry = {
                "name": var_name,
                "variable_type": "",
                "default_value": None,
                "description": "",
                "is_exposed": False,
            }
            graph_vars_by_name[var_name] = entry

        if title == "设置节点图变量":
            value_expr = input_constants.get("变量值")
            inferred_type = ""
            if isinstance(value_expr, bool):
                inferred_type = "布尔值"
            elif isinstance(value_expr, int):
                inferred_type = "整数"
            elif isinstance(value_expr, float):
                inferred_type = "浮点数"
            elif isinstance(value_expr, str):
                inferred_type = "字符串"

            if inferred_type and not str(entry.get("variable_type") or "").strip():
                entry["variable_type"] = inferred_type
                if entry.get("default_value") is None:
                    if inferred_type == "整数":
                        entry["default_value"] = 0
                    elif inferred_type == "浮点数":
                        entry["default_value"] = 0.0
                    elif inferred_type == "布尔值":
                        entry["default_value"] = False
                    elif inferred_type == "字符串":
                        entry["default_value"] = ""

    # 过滤并写回 GraphModel
    graph_variables: List[Dict[str, Any]] = []
    for name, entry in sorted(graph_vars_by_name.items(), key=lambda kv: kv[0]):
        var_type = str(entry.get("variable_type") or "").strip()
        if not var_type:
            # 未能推断类型时保守跳过；此时生成代码仍可能触发校验，需后续补齐推断逻辑
            continue
        if entry.get("default_value") is None:
            entry["default_value"] = 0
        graph_variables.append(entry)
    if graph_variables:
        setattr(graph_model, "graph_variables", graph_variables)

    metadata = {
        "graph_id": graph_model.graph_id,
        "graph_name": graph_model.graph_name,
        "graph_type": graph_scope,
        "description": f"自动生成（pyugc→GraphModel→Graph Code）：无参考生成；graph_id_int={int(graph_id_int)}。",
    }
    return graph_model, metadata


__all__ = [
    "infer_graph_scope_from_id_int",
    "load_node_type_semantic_map",
    "find_pyugc_graph_json_for_graph_id",
    "build_graph_model_from_pyugc_graph",
]




