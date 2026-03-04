from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.repo_paths import ugc_file_tools_root


def _infer_graph_scope_from_id_int(graph_id_int: int) -> str:
    """
    根据 graph_id 的高位前缀推断节点图类型：
    - 0x40000000: server
    - 0x40800000: client
    """
    masked_value = int(graph_id_int) & 0xFF800000
    if masked_value == 0x40000000:
        return "server"
    if masked_value == 0x40800000:
        return "client"
    return "unknown"


def _load_json(file_path: Path) -> Any:
    return json.loads(file_path.read_text(encoding="utf-8"))


def _write_json(file_path: Path, payload: Any) -> None:
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _extract_flow_calls_from_graph_code(
    graph_code_path: Path,
    *,
    graph_generater_root: Path,
) -> List[str]:
    """
    从参考 Graph Code 的 handler 中提取“流程节点调用名”序列，用于对齐 flow 链。

    约定：
    - 仅收集 *语句级* 调用（Expr(Call) / Assign(Call) / AnnAssign(Call)）；
    - 仅保留“流程节点”（NodeDef.inputs/outputs 中存在流程端口名）。
    """
    import sys

    graph_generater_root = Path(graph_generater_root).resolve()
    if not graph_generater_root.is_dir():
        raise FileNotFoundError(str(graph_generater_root))

    if str(graph_generater_root) not in sys.path:
        sys.path.insert(0, str(graph_generater_root))

    from engine.nodes.node_registry import get_node_registry
    from engine.utils.name_utils import make_valid_identifier
    from engine.utils.graph.graph_utils import is_flow_port_name

    registry = get_node_registry(graph_generater_root, include_composite=True)
    library = registry.get_library()

    source_text = graph_code_path.read_text(encoding="utf-8")
    module = ast.parse(source_text, filename=str(graph_code_path))

    def iter_call_expressions() -> Iterable[ast.Call]:
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef) and node.name == "on_实体创建时":
                for stmt in node.body:
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                        yield stmt.value
                    elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                        yield stmt.value
                    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.value, ast.Call):
                        if isinstance(stmt.value, ast.Call):
                            yield stmt.value

    def get_call_name(call_node: ast.Call) -> str:
        func = call_node.func
        if isinstance(func, ast.Name):
            return str(func.id)
        if isinstance(func, ast.Attribute):
            return str(func.attr)
        return ""

    def build_alias_index(scope: str) -> Dict[str, Any]:
        alias_to_def: Dict[str, Any] = {}
        ambiguous_aliases: set[str] = set()

        def add(alias: str, nd: Any) -> None:
            key = str(alias or "").strip()
            if key == "":
                return
            if key in ambiguous_aliases:
                return
            existing = alias_to_def.get(key)
            if existing is not None and existing is not nd:
                # 兼容节点库里“同一节点的多键别名”：若显示名一致，则视为同一节点，保持首个映射即可
                existing_name = str(getattr(existing, "name", "") or "").strip()
                new_name = str(getattr(nd, "name", "") or "").strip()
                if existing_name != "" and existing_name == new_name:
                    return

                # 同一可调用别名命中多个不同节点：标记为歧义并移除，避免误映射
                ambiguous_aliases.add(key)
                alias_to_def.pop(key, None)
                return
            alias_to_def[key] = nd

        for nd in library.values():
            if nd is None:
                continue
            if hasattr(nd, "is_available_in_scope") and not nd.is_available_in_scope(scope):
                continue
            name = str(getattr(nd, "name", "") or "").strip()
            # Graph Code 中的调用名必须是合法标识符，因此仅收录“可调用别名”（与运行时 loader 规则一致）
            add(make_valid_identifier(name), nd)
            slash_removed = name.replace("/", "").strip()
            if slash_removed:
                add(make_valid_identifier(slash_removed), nd)

        return alias_to_def

    alias_index = build_alias_index("server")

    flow_call_names: List[str] = []
    for call in iter_call_expressions():
        call_name = get_call_name(call)
        if call_name == "":
            continue
        nd = alias_index.get(call_name)
        if nd is None:
            continue
        inputs = list(getattr(nd, "inputs", []) or [])
        outputs = list(getattr(nd, "outputs", []) or [])
        has_flow = any(is_flow_port_name(str(p)) for p in (inputs + outputs))
        if not has_flow:
            continue
        flow_call_names.append(call_name)

    if not flow_call_names:
        raise ValueError(f"no flow calls extracted from graph code: {str(graph_code_path)!r}")

    return flow_call_names


def _extract_linear_flow_chain_from_pyugc_graph(graph_ir_path: Path) -> Tuple[int, List[int], Dict[int, int]]:
    """
    从 pyugc_graphs 导出的 JSON（decoded_nodes + records）中抽取线性 flow 链：
    - 返回 (graph_id_int, ordered_node_ids, node_id_to_type_id)

    说明：
    - 仅支持“每个节点最多 1 条 outgoing flow”的线性链；
    - 该函数依赖于我们在 test4 中验证过的 flow 边解析结构：
      - flow record: decoded.field_5.message.field_1.int 指向下一个 node_id
      - local flow: decoded.field_1.message.field_1/int + field_1.message.field_2/int
      - dst flow: decoded.field_5.message.field_2.message.field_1/int
    """
    from ugc_file_tools.decode_gil import decode_bytes_to_python  # noqa: F401  # 仅保证导入路径一致

    graph_payload = _load_json(graph_ir_path)
    if not isinstance(graph_payload, dict):
        raise TypeError(f"pyugc graph json must be dict: {str(graph_ir_path)!r}")

    graph_id_value = graph_payload.get("graph_id_int")
    decoded_nodes = graph_payload.get("decoded_nodes")
    if not isinstance(graph_id_value, int):
        raise TypeError(f"graph_id_int missing or invalid: {str(graph_ir_path)!r}")
    if not isinstance(decoded_nodes, list):
        raise TypeError(f"decoded_nodes missing or invalid: {str(graph_ir_path)!r}")

    graph_id_int = int(graph_id_value)

    node_id_set: set[int] = set()
    node_id_to_type_id: Dict[int, int] = {}
    nodes_by_id: Dict[int, Dict[str, Any]] = {}

    for node in decoded_nodes:
        if not isinstance(node, dict):
            continue
        node_id_value = node.get("node_id_int")
        if not isinstance(node_id_value, int):
            continue
        node_id_int = int(node_id_value)
        node_id_set.add(node_id_int)
        nodes_by_id[node_id_int] = node

        # data_2.decoded.field_5.int 是 type_id
        data_2 = node.get("data_2")
        decoded_2 = (data_2 or {}).get("decoded") if isinstance(data_2, dict) else None
        type_id = None
        if isinstance(decoded_2, dict):
            field_5 = decoded_2.get("field_5")
            if isinstance(field_5, dict) and isinstance(field_5.get("int"), int):
                type_id = int(field_5.get("int"))
        if isinstance(type_id, int):
            node_id_to_type_id[node_id_int] = int(type_id)

    def get_int(decoded_record: Dict[str, Any], path: Sequence[str]) -> Optional[int]:
        cursor: Any = decoded_record
        for key in path:
            if not isinstance(cursor, dict):
                return None
            cursor = cursor.get(key)
        if not isinstance(cursor, dict):
            return None
        number = cursor.get("int")
        if isinstance(number, int):
            return int(number)
        return None

    # src_node_id -> dst_node_id
    next_by_src: Dict[int, int] = {}
    dst_set: set[int] = set()

    for src_id, node in nodes_by_id.items():
        records = node.get("records")
        if not isinstance(records, list):
            continue
        for rec in records:
            if not isinstance(rec, dict):
                continue
            decoded_record = rec.get("decoded")
            if not isinstance(decoded_record, dict):
                continue
            # flow record 通常没有 field_4
            if isinstance(decoded_record.get("field_4"), dict) and isinstance(decoded_record.get("field_4", {}).get("int"), int):
                continue
            other_node_id_int = get_int(decoded_record, ["field_5", "message", "field_1"])
            if not isinstance(other_node_id_int, int):
                continue
            if other_node_id_int not in node_id_set:
                continue
            # 必须具备 flow group：field_1.message.field_1
            src_group = get_int(decoded_record, ["field_1", "message", "field_1"])
            dst_group = get_int(decoded_record, ["field_5", "message", "field_2", "message", "field_1"])
            if not isinstance(src_group, int) or not isinstance(dst_group, int):
                continue
            # 约定：flow group=2（src）-> group=1（dst）
            if int(src_group) != 2 or int(dst_group) != 1:
                continue

            if src_id in next_by_src and next_by_src[src_id] != int(other_node_id_int):
                raise ValueError(f"non-linear flow: src node {src_id} has multiple outgoing flow edges")
            next_by_src[src_id] = int(other_node_id_int)
            dst_set.add(int(other_node_id_int))

    if not next_by_src:
        raise ValueError(f"no flow edges found in graph: {graph_id_int}")

    start_candidates = sorted([src for src in next_by_src.keys() if src not in dst_set])
    if len(start_candidates) != 1:
        raise ValueError(f"cannot find unique flow start node: candidates={start_candidates}")
    start_node_id = int(start_candidates[0])

    ordered: List[int] = [start_node_id]
    seen: set[int] = {start_node_id}
    cursor = start_node_id
    while cursor in next_by_src:
        nxt = int(next_by_src[cursor])
        if nxt in seen:
            raise ValueError(f"cycle detected in flow chain: node_id={nxt}")
        ordered.append(nxt)
        seen.add(nxt)
        cursor = nxt

    return graph_id_int, ordered, node_id_to_type_id


def main(argv: Optional[Iterable[str]] = None) -> None:
    configure_console_encoding()

    argument_parser = argparse.ArgumentParser(
        description="使用“校准_全节点覆盖”参考 Graph Code 对齐 test4 的线性 flow 链，自动补全 typeId→节点名 映射表。",
    )
    argument_parser.add_argument(
        "--package-root",
        dest="package_root",
        required=True,
        help="项目存档目录（例如 Graph_Generater/assets/资源库/项目存档/test4）",
    )
    argument_parser.add_argument(
        "--graph-id",
        dest="graph_id_int",
        type=int,
        required=True,
        help="用于对齐的 graph_id_int（例如 1073741826）",
    )
    argument_parser.add_argument(
        "--reference-graph-code",
        dest="reference_graph_code",
        required=True,
        help="参考 Graph Code 文件路径（例如 Graph_Generater/assets/.../校准_全节点覆盖_v1_001.py）",
    )
    argument_parser.add_argument(
        "--mapping-file",
        dest="mapping_file",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="输出/更新的映射文件路径（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）",
    )

    args = argument_parser.parse_args(list(argv) if argv is not None else None)

    package_root = Path(args.package_root).resolve()
    graph_id_int = int(args.graph_id_int)
    reference_graph_code_path = Path(args.reference_graph_code).resolve()
    mapping_file_path = Path(args.mapping_file).resolve()

    if not package_root.is_dir():
        raise FileNotFoundError(f"package_root not found: {str(package_root)!r}")
    if not reference_graph_code_path.is_file():
        raise FileNotFoundError(f"reference graph code not found: {str(reference_graph_code_path)!r}")

    graph_scope = _infer_graph_scope_from_id_int(graph_id_int)
    if graph_scope != "server":
        raise ValueError(f"only server calibration supported for now, got graph_scope={graph_scope!r}")

    pyugc_graph_path = (
        package_root
        / "节点图"
        / "原始解析"
        / "pyugc_graphs"
        / f"graph_{graph_id_int}_*.json"
    )
    # 这里不做 glob：直接通过索引定位
    graphs_index_path = package_root / "节点图" / "原始解析" / "pyugc_graphs_index.json"
    graphs_index = _load_json(graphs_index_path)
    if not isinstance(graphs_index, list):
        raise TypeError(f"pyugc_graphs_index invalid: {str(graphs_index_path)!r}")

    resolved_graph_json_rel = ""
    for entry in graphs_index:
        if not isinstance(entry, dict):
            continue
        if entry.get("graph_id_int") == graph_id_int:
            resolved_graph_json_rel = str(entry.get("output") or "").strip()
            break
    if resolved_graph_json_rel == "":
        raise FileNotFoundError(f"graph_id_int not found in index: {graph_id_int}")

    resolved_graph_json_path = package_root / Path(resolved_graph_json_rel)
    if not resolved_graph_json_path.is_file():
        raise FileNotFoundError(f"pyugc graph json not found: {str(resolved_graph_json_path)!r}")

    from ugc_file_tools.repo_paths import resolve_graph_generater_root

    graph_generater_root = resolve_graph_generater_root(package_root)

    flow_call_names = _extract_flow_calls_from_graph_code(
        reference_graph_code_path,
        graph_generater_root=graph_generater_root,
    )
    graph_id_from_dump, flow_node_ids, node_id_to_type_id = _extract_linear_flow_chain_from_pyugc_graph(
        resolved_graph_json_path
    )
    if int(graph_id_from_dump) != int(graph_id_int):
        raise ValueError("graph_id mismatch between index and graph file")

    # flow_node_ids[0] 是事件入口，剩余为流程链节点
    flow_chain_type_ids: List[int] = []
    for node_id in flow_node_ids[1:]:
        type_id = node_id_to_type_id.get(int(node_id))
        if not isinstance(type_id, int):
            raise ValueError(f"missing type_id for node_id={node_id}")
        flow_chain_type_ids.append(int(type_id))

    if len(flow_chain_type_ids) != len(flow_call_names):
        raise ValueError(
            "flow chain length mismatch: "
            f"flow_nodes={len(flow_chain_type_ids)} vs flow_calls_in_code={len(flow_call_names)}"
        )

    import sys

    graph_generater_root = Path(graph_generater_root).resolve()
    if str(graph_generater_root) not in sys.path:
        sys.path.insert(0, str(graph_generater_root))

    from engine.nodes.node_registry import get_node_registry
    from engine.utils.name_utils import make_valid_identifier

    registry = get_node_registry(graph_generater_root, include_composite=True)
    library = registry.get_library()

    def build_alias_index(scope: str) -> Dict[str, Any]:
        alias_to_def: Dict[str, Any] = {}
        ambiguous_aliases: set[str] = set()

        def add(alias: str, nd: Any) -> None:
            key = str(alias or "").strip()
            if key == "":
                return
            if key in ambiguous_aliases:
                return
            existing = alias_to_def.get(key)
            if existing is not None and existing is not nd:
                # 兼容节点库里“同一节点的多键别名”：若显示名一致，则视为同一节点，保持首个映射即可
                existing_name = str(getattr(existing, "name", "") or "").strip()
                new_name = str(getattr(nd, "name", "") or "").strip()
                if existing_name != "" and existing_name == new_name:
                    return

                # 同一可调用别名命中多个不同节点：标记为歧义并移除，避免误映射
                ambiguous_aliases.add(key)
                alias_to_def.pop(key, None)
                return
            alias_to_def[key] = nd

        for nd in library.values():
            if nd is None:
                continue
            if hasattr(nd, "is_available_in_scope") and not nd.is_available_in_scope(scope):
                continue
            name = str(getattr(nd, "name", "") or "").strip()
            # Graph Code 中的调用名必须是合法标识符，因此仅收录“可调用别名”（与运行时 loader 规则一致）
            add(make_valid_identifier(name), nd)
            slash_removed = name.replace("/", "").strip()
            if slash_removed:
                add(make_valid_identifier(slash_removed), nd)

        return alias_to_def

    alias_index = build_alias_index("server")

    existing_mapping: Dict[str, Any] = {}
    if mapping_file_path.is_file():
        mapping_obj = _load_json(mapping_file_path)
        if not isinstance(mapping_obj, dict):
            raise TypeError(f"mapping file must be dict: {str(mapping_file_path)!r}")
        existing_mapping = dict(mapping_obj)

    updated = 0
    for type_id_int, node_name in zip(flow_chain_type_ids, flow_call_names):
        node_def = alias_index.get(str(node_name))
        if node_def is None:
            raise ValueError(f"cannot resolve node def from call name: {str(node_name)!r}")
        canonical_node_name = str(getattr(node_def, "name", "") or "").strip()
        if canonical_node_name == "":
            raise ValueError(f"resolved node def missing name for call: {str(node_name)!r}")
        semantic_id = str(getattr(node_def, "semantic_id", "") or "").strip()
        new_entry = {
            "scope": "server",
            "graph_generater_node_name": canonical_node_name,
            "semantic_id": semantic_id,
            "confidence": "high",
            "notes": (
                "由校准图 graph_id_int="
                f"{graph_id_int} 与参考 Graph Code 对齐自动生成（线性 flow 链）；用于后续 Graph Code 生成。"
            ),
        }

        key = str(int(type_id_int))
        old = existing_mapping.get(key)
        if old is None:
            existing_mapping[key] = new_entry
            updated += 1
            continue
        if not isinstance(old, dict):
            raise TypeError(f"existing mapping entry is not dict: type_id={key}")
        old_name = str(old.get("graph_generater_node_name") or "").strip()
        if old_name != "" and old_name != str(canonical_node_name):
            raise ValueError(f"mapping conflict for type_id={key}: {old_name!r} vs {canonical_node_name!r}")
        merged = dict(old)
        for k2, v2 in new_entry.items():
            if str(merged.get(k2) or "").strip() == "":
                merged[k2] = v2
        existing_mapping[key] = merged

    _write_json(mapping_file_path, existing_mapping)

    print("=" * 80)
    print("已完成 typeId→节点名 映射补全：")
    print(f"- package_root: {package_root}")
    print(f"- graph_id_int: {graph_id_int}")
    print(f"- reference_graph_code: {reference_graph_code_path}")
    print(f"- updated_new_entries: {updated}")
    print(f"- mapping_file: {mapping_file_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()



