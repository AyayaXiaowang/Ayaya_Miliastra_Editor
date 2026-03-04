from __future__ import annotations

"""
check_get_custom_variable_dict_outparam.py

端到端诊断：定位“导出/写回 .gil 时，获取自定义变量（Get_Custom_Variable）字典输出退化为整数”等问题。

做什么：
- 输入 Graph Code（或已导出的 GraphModel JSON）
- 导出/读取 GraphModel(JSON, typed)
- 写回生成一份临时 `.gil`（节点图段 10.1.1）
- 直接解析 `.gil` payload 为 Graph IR
- 对齐校验：GraphModel 推断为“别名字典”的 Get_Custom_Variable 输出，写回产物必须：
  - OUT_PARAM var_type == 27（字典）
  - 且携带 MapBase(K,V) 的 key/value VarType，并与 GraphModel 的端口类型推断一致
  - 若命中 node_data TypeMappings `S<T:D<K,V>>`（单泛型 T=字典），还必须写入：
    - 节点 concrete runtime_id（NodeProperty.runtime_id / concrete_id）切换为命中的 ConcreteId
    - OUT_PARAM.ConcreteBase.indexOfConcrete（常见为 20）

说明：
- 默认使用“模板克隆模式”写回（能覆盖“模板里默认 OUT_PARAM 错类型/重复 record 未覆盖”这类真实问题）。
- 所有产物统一写入 `ugc_file_tools/out/`；不修改输入 `.gil`。
- 不使用 try/except；失败直接抛错（fail-fast）。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.contracts.node_graph_type_mappings import try_resolve_t_dict_concrete_mapping
from ugc_file_tools.graph.model_ir import iter_node_payload_dicts, pick_graph_model_payload_and_metadata
from ugc_file_tools.node_data_index import load_node_entry_by_id_map, resolve_default_node_data_index_path
from ugc_file_tools.node_graph_semantics.dict_kv_types import try_resolve_dict_kv_var_types_from_type_text
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root
from ugc_file_tools.var_type_map import (
    map_server_port_type_text_to_var_type_id_or_raise,
    try_map_server_port_type_text_to_var_type_id,
    try_map_var_type_id_to_server_port_type_text,
)

from ugc_file_tools.commands.export.export_graph_model_json_from_graph_code import (
    export_graph_model_json_from_graph_code,
)
from ugc_file_tools.graph.node_graph.gil_payload_graph_ir import (
    extract_node_graph_blobs_from_gil_payload,
    parse_gil_payload_node_graphs_to_graph_ir,
)
from ugc_file_tools.node_graph_writeback.writer import (
    run_precheck_and_write_and_postcheck,
    run_write_and_postcheck_pure_json,
)


@dataclass(frozen=True, slots=True)
class _ExpectedDictOutParam:
    graph_node_id: str
    var_name: str
    output_type_text: str
    dict_key_vt_int: int
    dict_value_vt_int: int
    expected_concrete_runtime_id_int: Optional[int]
    expected_out_index_of_concrete_int: Optional[int]


@dataclass(frozen=True, slots=True)
class _ActualDictOutParam:
    node_index_int: int
    var_name: str
    outparam_var_type_int: int
    dict_key_vt_int: Optional[int]
    dict_value_vt_int: Optional[int]
    outparam_type_expr: str
    concrete_runtime_id_int: int
    outparam_index_of_concrete_int: Optional[int]


def _is_get_custom_variable_node(node_payload: Dict[str, Any]) -> bool:
    title = str(node_payload.get("title") or "").strip()
    if title in {"获取自定义变量", "Get_Custom_Variable"}:
        return True
    ref = node_payload.get("node_def_ref")
    if isinstance(ref, dict):
        key = str(ref.get("key") or "").strip()
        if key.endswith("获取自定义变量") or key.endswith("Get_Custom_Variable"):
            return True
        if key in {"查询节点/获取自定义变量", "查询节点/Get_Custom_Variable"}:
            return True
    return False


def _extract_custom_var_name_from_graph_model(node_payload: Dict[str, Any]) -> str:
    ic = node_payload.get("input_constants")
    if not isinstance(ic, dict):
        return ""
    return str(ic.get("变量名") or "").strip()


def _extract_output_type_text_from_graph_model(node_payload: Dict[str, Any]) -> str:
    out_types = node_payload.get("output_port_types")
    if not isinstance(out_types, dict):
        return ""
    text = str(out_types.get("变量值") or "").strip()
    if text != "":
        return text
    if len(out_types) == 1:
        return str(next(iter(out_types.values())) or "").strip()
    return ""


def _collect_expected_dict_outparams(
    *,
    graph_model_payload: Dict[str, Any],
    only_var_names: Optional[set[str]],
    node_entry_by_id: Optional[Dict[int, Dict[str, Any]]],
) -> list[_ExpectedDictOutParam]:
    expected: list[_ExpectedDictOutParam] = []

    for node_payload in iter_node_payload_dicts(graph_model_payload):
        if not _is_get_custom_variable_node(node_payload):
            continue

        var_name = _extract_custom_var_name_from_graph_model(node_payload)
        if only_var_names is not None:
            if var_name == "" or var_name not in only_var_names:
                continue

        out_type_text = _extract_output_type_text_from_graph_model(node_payload)
        if out_type_text == "":
            continue

        vt = try_map_server_port_type_text_to_var_type_id(out_type_text)
        if int(vt or 0) != 27:
            continue

        kv = try_resolve_dict_kv_var_types_from_type_text(
            out_type_text,
            map_port_type_text_to_var_type_id=map_server_port_type_text_to_var_type_id_or_raise,
            reject_generic=True,
        )
        if kv is None:
            raise ValueError(
                "GraphModel 推断为“字典”但缺少可解析的 K/V 类型（无法校验写回是否正确）："
                f"node_id={node_payload.get('id')!r} var_name={var_name!r} output_type_text={out_type_text!r}"
            )
        dict_key_vt_int, dict_value_vt_int = kv

        expected_concrete_runtime_id_int: Optional[int] = None
        expected_out_index_of_concrete_int: Optional[int] = None
        if isinstance(node_entry_by_id, dict) and node_entry_by_id:
            resolved_t_dict = try_resolve_t_dict_concrete_mapping(
                node_entry_by_id=dict(node_entry_by_id),
                node_type_id_int=50,  # Get_Custom_Variable（server）
                dict_key_vt=int(dict_key_vt_int),
                dict_value_vt=int(dict_value_vt_int),
            )
            if resolved_t_dict is not None:
                concrete_id_int, _in_idx, out_idx = resolved_t_dict
                if isinstance(concrete_id_int, int) and int(concrete_id_int) > 0:
                    expected_concrete_runtime_id_int = int(concrete_id_int)
                if isinstance(out_idx, int) and int(out_idx) > 0:
                    expected_out_index_of_concrete_int = int(out_idx)

        expected.append(
            _ExpectedDictOutParam(
                graph_node_id=str(node_payload.get("id") or "").strip(),
                var_name=str(var_name),
                output_type_text=str(out_type_text),
                dict_key_vt_int=int(dict_key_vt_int),
                dict_value_vt_int=int(dict_value_vt_int),
                expected_concrete_runtime_id_int=expected_concrete_runtime_id_int,
                expected_out_index_of_concrete_int=expected_out_index_of_concrete_int,
            )
        )

    return expected


def _extract_get_custom_variable_actuals_from_graph_ir(graph_ir: Dict[str, Any]) -> list[_ActualDictOutParam]:
    actuals: list[_ActualDictOutParam] = []
    for node in graph_ir.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if str(node.get("node_type_name") or "") != "Get_Custom_Variable":
            continue

        node_index_int = int(node.get("node_index_int") or 0)
        concrete_runtime_id_int = 0
        concrete_id_obj = node.get("concrete_id")
        if isinstance(concrete_id_obj, dict):
            raw_node_id_int = concrete_id_obj.get("node_id_int")
            if isinstance(raw_node_id_int, int):
                concrete_runtime_id_int = int(raw_node_id_int)
        var_name = ""
        outparam_var_type_int = 0
        outparam_type_expr = ""
        dict_key_vt_int: Optional[int] = None
        dict_value_vt_int: Optional[int] = None
        outparam_index_of_concrete_int: Optional[int] = None

        for pin in node.get("pins") or []:
            if not isinstance(pin, dict):
                continue

            kind_int = int(pin.get("kind_int") or 0)
            index_int = int(pin.get("index_int") or 0)

            # InParam: 变量名（字符串）通常为 kind=3 index=1
            if kind_int == 3 and index_int == 1 and str(pin.get("type_expr") or "") == "Str":
                var_name = str(pin.get("value") or "").strip()

            # OutParam: 输出（变量值）通常为 kind=4 index=0
            if kind_int == 4 and index_int == 0:
                outparam_var_type_int = int(pin.get("type_id_int") or 0)
                outparam_type_expr = str(pin.get("type_expr") or "").strip()
                raw_k = pin.get("dict_key_type_int")
                raw_v = pin.get("dict_value_type_int")
                dict_key_vt_int = int(raw_k) if isinstance(raw_k, int) else None
                dict_value_vt_int = int(raw_v) if isinstance(raw_v, int) else None
                raw_idx = pin.get("concrete_index_of_concrete_int")
                outparam_index_of_concrete_int = int(raw_idx) if isinstance(raw_idx, int) else None

        actuals.append(
            _ActualDictOutParam(
                node_index_int=int(node_index_int),
                var_name=str(var_name),
                outparam_var_type_int=int(outparam_var_type_int),
                dict_key_vt_int=dict_key_vt_int,
                dict_value_vt_int=dict_value_vt_int,
                outparam_type_expr=str(outparam_type_expr),
                concrete_runtime_id_int=int(concrete_runtime_id_int),
                outparam_index_of_concrete_int=outparam_index_of_concrete_int,
            )
        )
    return actuals


def _format_vt(vt: Optional[int]) -> str:
    if vt is None:
        return "None"
    text = try_map_var_type_id_to_server_port_type_text(int(vt))
    if isinstance(text, str) and text.strip():
        return f"{int(vt)}({text})"
    return str(int(vt))


_SCOPE_MASK = 0xFF800000
_SERVER_SCOPE_MASK = 0x40000000
_CLIENT_SCOPE_MASK = 0x40800000


def _infer_graph_scope_from_metadata(metadata: Dict[str, Any]) -> str:
    for key in ("graph_scope", "graph_type", "scope"):
        v = metadata.get(key)
        if not isinstance(v, str):
            continue
        scope = v.strip().lower()
        if scope in {"server", "client"}:
            return scope
    return ""


def _resolve_inspect_graph_id_ints(
    *,
    inspect_gil_path: Path,
    explicit_graph_ids: Sequence[int],
    explicit_graph_name: str,
    metadata: Dict[str, Any],
) -> list[int]:
    if explicit_graph_ids:
        deduped: list[int] = []
        seen: set[int] = set()
        for gid in list(explicit_graph_ids):
            if not isinstance(gid, int) or int(gid) <= 0:
                continue
            if int(gid) in seen:
                continue
            seen.add(int(gid))
            deduped.append(int(gid))
        if deduped:
            return deduped
        raise ValueError("inspect_graph_ids 全部无效（必须为正整数）")

    graph_name = str(explicit_graph_name or "").strip()
    if graph_name == "":
        graph_name = str(metadata.get("graph_name") or metadata.get("name") or "").strip()
    if graph_name == "":
        raise ValueError("inspect 模式下无法推断 graph_name（GraphModel metadata 缺失）。请改用 --inspect-graph-id-int 指定。")

    expected_scope = _infer_graph_scope_from_metadata(dict(metadata))

    blobs = extract_node_graph_blobs_from_gil_payload(gil_file_path=Path(inspect_gil_path))
    matched = [b for b in blobs if str(b.graph_name) == graph_name]
    if expected_scope in {"server", "client"} and matched:
        expected_mask = _SERVER_SCOPE_MASK if expected_scope == "server" else _CLIENT_SCOPE_MASK
        scoped = [b for b in matched if (int(b.graph_id_int) & int(_SCOPE_MASK)) == int(expected_mask)]
        if scoped:
            matched = scoped

    if not matched:
        available = sorted({str(b.graph_name) for b in blobs if str(b.graph_name).strip() != ""})
        preview = ", ".join(repr(x) for x in available[:20])
        raise ValueError(
            "inspect 模式：在目标 .gil 中未找到同名节点图。\n"
            f"- inspect_gil: {str(Path(inspect_gil_path).resolve())}\n"
            f"- expected_graph_name: {graph_name!r}\n"
            f"- inferred_scope: {expected_scope!r}\n"
            f"- available_graph_names(sample<=20): {preview}"
        )

    if len(matched) > 1:
        candidates = ", ".join(f"{int(b.graph_id_int)}" for b in matched[:20])
        raise ValueError(
            "inspect 模式：目标 .gil 中存在多个同名节点图，无法自动消歧。\n"
            f"- inspect_gil: {str(Path(inspect_gil_path).resolve())}\n"
            f"- graph_name: {graph_name!r}\n"
            f"- candidates_graph_id_int(sample<=20): {candidates}\n"
            "解决方案：显式传入 --inspect-graph-id-int <id>（可重复）。"
        )

    return [int(matched[0].graph_id_int)]


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    default_template_library_dir = (
        ugc_file_tools_root() / "builtin_resources" / "template_library" / "test2_server_writeback_samples"
    )
    default_template_gil = default_template_library_dir / "01_ng_minimal_wiring_graph_var_set_entity.gil"
    default_empty_base_gil = default_template_library_dir / "03_node_graph_new_empty.gil"
    default_template_graph_id_int = 1073741825

    parser = argparse.ArgumentParser(
        description=(
            "端到端诊断：导出 GraphModel→写回临时 GIL→解析 Graph IR，校验 Get_Custom_Variable 的 dict OUT_PARAM(K/V) 与 GraphModel 推断一致。"
        )
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--graph-code", dest="graph_code_file", help="输入 Graph Code 文件（Graph_Generater 资源库内 .py）")
    input_group.add_argument(
        "--graph-json",
        dest="graph_json_file",
        help="输入 GraphModel JSON（export_graph_model_json_from_graph_code 的输出）",
    )
    parser.add_argument(
        "--var-name",
        dest="var_names",
        action="append",
        default=[],
        help="仅校验指定的自定义变量名（可重复传多次）。不传则校验 GraphModel 中所有“别名字典”输出的 Get_Custom_Variable。",
    )
    parser.add_argument(
        "--pure-json",
        dest="pure_json",
        action="store_true",
        help="使用纯 JSON 写回（不克隆模板节点/record）。默认关闭：使用模板克隆模式以覆盖“模板默认 OUT_PARAM 错类型/重复 record”场景。",
    )
    parser.add_argument("--template-gil", default=str(default_template_gil), help="模板 .gil（模板克隆模式使用）")
    parser.add_argument(
        "--base-gil",
        default=None,
        help="可选：base .gil（输出容器）。纯 JSON 模式若不传，会默认使用内置“新建空图”样本。",
    )
    parser.add_argument(
        "--template-library-dir",
        default=str(default_template_library_dir),
        help="可选：额外样本库目录（递归扫描 *.gil 以补齐节点/record 样本）。",
    )
    parser.add_argument(
        "--template-graph-id",
        dest="template_graph_id_int",
        type=int,
        default=int(default_template_graph_id_int),
        help="模板 .gil 中用于取样/推断 scope 的 graph_id_int（默认 1073741825）。",
    )
    parser.add_argument(
        "--output-gil",
        dest="output_gil",
        default="",
        help="输出 .gil 文件名/路径（最终会写入 ugc_file_tools/out/；不要覆盖重要样本）。",
    )
    parser.add_argument(
        "--inspect-gil",
        dest="inspect_gil",
        default="",
        help="可选：不写回临时 .gil，直接解析并校验指定 .gil（用于验证“导出中心/CLI 导出产物”是否仍会把字典退化为整数）。",
    )
    parser.add_argument(
        "--inspect-graph-id-int",
        dest="inspect_graph_ids",
        type=int,
        action="append",
        default=[],
        help="可选：inspect 模式下显式指定要校验的 graph_id_int（可重复）。不传则按 graph_name 自动匹配。",
    )
    parser.add_argument(
        "--inspect-graph-name",
        dest="inspect_graph_name",
        default="",
        help="可选：inspect 模式下用于匹配的 graph_name（默认取 GraphModel metadata.graph_name）。",
    )
    parser.add_argument(
        "--graph-generater-root",
        dest="graph_generater_root",
        default=str(repo_root()),
        help="Graph_Generater 工程根目录（默认 workspace/Graph_Generater）。",
    )
    parser.add_argument(
        "--node-type-map",
        dest="mapping_path",
        default=str(ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"),
        help="typeId→节点名 映射文件（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）。",
    )
    parser.add_argument(
        "--node-data-index",
        dest="node_data_index_path",
        default=str(resolve_default_node_data_index_path()),
        help="node_data/index.json 路径（默认 ugc_file_tools/node_data/index.json）。",
    )
    parser.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=16,
        help="payload NodeGraph blob 深度解码上限（默认 16）。",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    # ===== 1) 准备 GraphModel JSON =====
    graph_json_path: Path
    graph_code_path: Optional[Path] = None
    if args.graph_json_file:
        graph_json_path = Path(args.graph_json_file).resolve()
        if not graph_json_path.is_file():
            raise FileNotFoundError(str(graph_json_path))
    else:
        graph_code_path = Path(args.graph_code_file).resolve()
        if not graph_code_path.is_file():
            raise FileNotFoundError(str(graph_code_path))
        default_graph_json_name = f"_tmp_check_get_custom_var_dict_outparam.{graph_code_path.stem}.graph_model.json"
        export_report = export_graph_model_json_from_graph_code(
            graph_code_file=graph_code_path,
            output_json_file=Path(default_graph_json_name),
            graph_generater_root=Path(args.graph_generater_root),
        )
        graph_json_path = Path(str(export_report.get("output_json") or "")).resolve()
        if str(graph_json_path) == "" or not graph_json_path.is_file():
            raise FileNotFoundError(f"GraphModel JSON 导出失败或未落盘：{export_report!r}")

    graph_json_object = json.loads(graph_json_path.read_text(encoding="utf-8"))
    metadata, graph_model_payload = pick_graph_model_payload_and_metadata(dict(graph_json_object))

    # ===== 2) 收集期望：GraphModel 中推断为“别名字典”的 Get_Custom_Variable =====
    raw_var_names = [str(x or "").strip() for x in (args.var_names or [])]
    var_name_filters = {x for x in raw_var_names if x != ""}
    expected = _collect_expected_dict_outparams(
        graph_model_payload=dict(graph_model_payload),
        only_var_names=(var_name_filters if var_name_filters else None),
        node_entry_by_id=(
            dict(load_node_entry_by_id_map(Path(str(args.node_data_index_path))) or {})
        ),
    )
    if not expected:
        graph_name = str(metadata.get("graph_name") or metadata.get("name") or "").strip()
        raise ValueError(
            "未在 GraphModel 中找到“输出端口类型为别名字典”的 Get_Custom_Variable 节点。\n"
            f"- graph_json: {str(graph_json_path)}\n"
            f"- graph_name: {graph_name!r}\n"
            f"- var_name_filters: {sorted(var_name_filters)}"
        )

    # ===== 3) inspect 模式：直接解析现成导出产物 .gil 并对齐校验 =====
    inspect_gil_text = str(args.inspect_gil or "").strip()
    if inspect_gil_text != "":
        inspect_gil_path = Path(inspect_gil_text).resolve()
        if not inspect_gil_path.is_file():
            raise FileNotFoundError(str(inspect_gil_path))

        graph_id_ints = _resolve_inspect_graph_id_ints(
            inspect_gil_path=Path(inspect_gil_path),
            explicit_graph_ids=list(args.inspect_graph_ids or []),
            explicit_graph_name=str(args.inspect_graph_name or ""),
            metadata=dict(metadata),
        )

        parsed = parse_gil_payload_node_graphs_to_graph_ir(
            gil_file_path=Path(inspect_gil_path),
            node_data_index_path=Path(str(args.node_data_index_path)),
            graph_ids=[int(x) for x in list(graph_id_ints)],
            max_depth=int(args.max_depth),
        )
        if not parsed:
            raise RuntimeError(
                f"inspect 模式：未解析到目标 graph_id 的 NodeGraph：graph_id_ints={graph_id_ints} gil={str(inspect_gil_path)!r}"
            )

        mismatch_lines: list[str] = []
        for item in parsed:
            graph_ir = dict(item.graph_ir)
            actuals = _extract_get_custom_variable_actuals_from_graph_ir(graph_ir)
            actual_by_var_name: Dict[str, list[_ActualDictOutParam]] = {}
            for a in actuals:
                actual_by_var_name.setdefault(str(a.var_name), []).append(a)

            for exp in expected:
                matched = actual_by_var_name.get(exp.var_name) or []
                if not matched:
                    mismatch_lines.append(
                        "未在目标 .gil 中找到对应的 Get_Custom_Variable（按变量名匹配失败）："
                        f"graph_id_int={int(item.graph_id_int)} var_name={exp.var_name!r} "
                        f"expected={_format_vt(exp.dict_key_vt_int)}->{_format_vt(exp.dict_value_vt_int)}"
                    )
                    continue

                for act in matched:
                    if int(act.outparam_var_type_int) != 27:
                        mismatch_lines.append(
                            "OUT_PARAM 类型错误（期望字典 VarType=27）："
                            f"graph_id_int={int(item.graph_id_int)} var_name={exp.var_name!r} node_index={act.node_index_int} "
                            f"got={_format_vt(act.outparam_var_type_int)} type_expr={act.outparam_type_expr!r} "
                            f"expected=dict({exp.output_type_text!r})"
                        )
                        continue

                    if act.dict_key_vt_int is None or act.dict_value_vt_int is None:
                        mismatch_lines.append(
                            "OUT_PARAM 缺少 MapBase(K,V)（常见会导致编辑器回退为整数）："
                            f"graph_id_int={int(item.graph_id_int)} var_name={exp.var_name!r} node_index={act.node_index_int} "
                            f"got_kv={_format_vt(act.dict_key_vt_int)}->{_format_vt(act.dict_value_vt_int)} "
                            f"expected_kv={_format_vt(exp.dict_key_vt_int)}->{_format_vt(exp.dict_value_vt_int)}"
                        )
                        continue

                    if int(act.dict_key_vt_int) != int(exp.dict_key_vt_int) or int(act.dict_value_vt_int) != int(exp.dict_value_vt_int):
                        mismatch_lines.append(
                            "OUT_PARAM 字典 K/V 类型不一致："
                            f"graph_id_int={int(item.graph_id_int)} var_name={exp.var_name!r} node_index={act.node_index_int} "
                            f"got_kv={_format_vt(act.dict_key_vt_int)}->{_format_vt(act.dict_value_vt_int)} "
                            f"expected_kv={_format_vt(exp.dict_key_vt_int)}->{_format_vt(exp.dict_value_vt_int)} "
                            f"(from GraphModel output_port_types={exp.output_type_text!r})"
                        )

                    if isinstance(exp.expected_concrete_runtime_id_int, int) and int(exp.expected_concrete_runtime_id_int) > 0:
                        if int(act.concrete_runtime_id_int) != int(exp.expected_concrete_runtime_id_int):
                            mismatch_lines.append(
                                "节点 concrete runtime_id 未按 TypeMappings(S<T:D<K,V>>) 切换（编辑器可能回退为整数）："
                                f"graph_id_int={int(item.graph_id_int)} var_name={exp.var_name!r} node_index={act.node_index_int} "
                                f"got={int(act.concrete_runtime_id_int)} expected={int(exp.expected_concrete_runtime_id_int)}"
                            )

                    if isinstance(exp.expected_out_index_of_concrete_int, int) and int(exp.expected_out_index_of_concrete_int) > 0:
                        if int(act.outparam_index_of_concrete_int or 0) != int(exp.expected_out_index_of_concrete_int):
                            mismatch_lines.append(
                                "OUT_PARAM 缺少/写错 indexOfConcrete（编辑器可能回退为默认 concrete）："
                                f"graph_id_int={int(item.graph_id_int)} var_name={exp.var_name!r} node_index={act.node_index_int} "
                                f"got={act.outparam_index_of_concrete_int!r} expected={int(exp.expected_out_index_of_concrete_int)}"
                            )

        if mismatch_lines:
            raise ValueError(
                "inspect 模式：Get_Custom_Variable 字典 OUT_PARAM 校验失败：\n"
                f"- inspect_gil: {str(inspect_gil_path)}\n"
                f"- graph_id_ints: {graph_id_ints}\n"
                + "\n".join(f"- {line}" for line in mismatch_lines)
            )

        print("=" * 80)
        print("inspect 模式：校验通过")
        print(f"- inspect_gil: {str(inspect_gil_path)}")
        print(f"- graph_id_ints: {graph_id_ints}")
        print(f"- expected_dict_nodes: {len(expected)}")
        for exp in expected:
            print(
                f"- {exp.var_name}: kv={_format_vt(exp.dict_key_vt_int)}->{_format_vt(exp.dict_value_vt_int)} "
                f"(type={exp.output_type_text!r})"
            )
        print("=" * 80)
        return

    # ===== 4) 写回生成临时 GIL（默认模板克隆，覆盖真实“模板带错 record”场景）=====
    new_graph_name = f"diag_check_get_custom_var_dict_outparam_{Path(graph_json_path).stem}"
    output_gil_name = str(args.output_gil or "").strip()
    if output_gil_name == "":
        suffix = (graph_code_path.stem if graph_code_path is not None else Path(graph_json_path).stem).strip()
        output_gil_name = f"_tmp_check_get_custom_var_dict_outparam.{suffix}.gil"

    if bool(args.pure_json):
        base_gil_path = Path(str(args.base_gil or "")).resolve() if args.base_gil else default_empty_base_gil
        report, _ = run_write_and_postcheck_pure_json(
            graph_model_json_path=graph_json_path,
            base_gil_path=Path(base_gil_path),
            output_gil_path=Path(output_gil_name),
            scope_graph_id_int=int(args.template_graph_id_int),
            new_graph_name=str(new_graph_name),
            new_graph_id_int=None,
            mapping_path=Path(args.mapping_path),
            graph_generater_root=Path(args.graph_generater_root),
            skip_postcheck=True,
            prefer_signal_specific_type_id=False,
            auto_sync_ui_custom_variable_defaults=False,
        )
    else:
        report, _, _ = run_precheck_and_write_and_postcheck(
            graph_model_json_path=graph_json_path,
            template_gil_path=Path(str(args.template_gil)),
            base_gil_path=(Path(str(args.base_gil)) if args.base_gil else None),
            template_library_dir=(Path(str(args.template_library_dir)) if args.template_library_dir else None),
            output_gil_path=Path(output_gil_name),
            template_graph_id_int=int(args.template_graph_id_int),
            new_graph_name=str(new_graph_name),
            new_graph_id_int=None,
            mapping_path=Path(args.mapping_path),
            graph_generater_root=Path(args.graph_generater_root),
            skip_precheck=True,
            prefer_signal_specific_type_id=False,
            auto_sync_ui_custom_variable_defaults=False,
            auto_fill_graph_variable_defaults_from_ui_registry=False,
        )

    output_gil_written = Path(str(report.get("output_gil") or "")).resolve()
    if str(output_gil_written) == "" or not output_gil_written.is_file():
        raise FileNotFoundError(f"写回产物不存在：{str(output_gil_written)!r} report={report!r}")
    raw_new_graph_id_int = report.get("new_graph_id_int")
    if not isinstance(raw_new_graph_id_int, int):
        raise ValueError(f"写回报告缺少 new_graph_id_int：{raw_new_graph_id_int!r}")
    new_graph_id_int = int(raw_new_graph_id_int)

    print("=" * 80)
    print("写回产物：")
    print(f"- graph_json: {str(graph_json_path)}")
    print(f"- output_gil: {str(output_gil_written)}")
    print(f"- new_graph_id_int: {new_graph_id_int}")
    print(f"- expected_dict_nodes: {len(expected)}")
    print("=" * 80)

    # ===== 5) 解析 output_gil 的 payload NodeGraph → Graph IR =====
    parsed = parse_gil_payload_node_graphs_to_graph_ir(
        gil_file_path=output_gil_written,
        node_data_index_path=Path(str(args.node_data_index_path)),
        graph_ids=[int(new_graph_id_int)],
        max_depth=int(args.max_depth),
    )
    if not parsed:
        raise RuntimeError(f"未解析到目标 graph_id 的 NodeGraph：graph_id_int={new_graph_id_int} gil={str(output_gil_written)!r}")
    item0 = parsed[0]
    graph_ir = dict(item0.graph_ir)

    actuals = _extract_get_custom_variable_actuals_from_graph_ir(graph_ir)
    actual_by_var_name: Dict[str, list[_ActualDictOutParam]] = {}
    for a in actuals:
        actual_by_var_name.setdefault(str(a.var_name), []).append(a)

    # ===== 6) 对齐校验 =====
    mismatch_lines: list[str] = []
    for exp in expected:
        matched = actual_by_var_name.get(exp.var_name) or []
        if not matched:
            mismatch_lines.append(
                "未在写回产物中找到对应的 Get_Custom_Variable（按变量名匹配失败）："
                f"var_name={exp.var_name!r} expected={_format_vt(exp.dict_key_vt_int)}->{_format_vt(exp.dict_value_vt_int)}"
            )
            continue

        for act in matched:
            if int(act.outparam_var_type_int) != 27:
                mismatch_lines.append(
                    "OUT_PARAM 类型错误（期望字典 VarType=27）："
                    f"var_name={exp.var_name!r} node_index={act.node_index_int} "
                    f"got={_format_vt(act.outparam_var_type_int)} type_expr={act.outparam_type_expr!r} "
                    f"expected=dict({exp.output_type_text!r})"
                )
                continue

            if act.dict_key_vt_int is None or act.dict_value_vt_int is None:
                mismatch_lines.append(
                    "OUT_PARAM 缺少 MapBase(K,V)（常见会导致编辑器回退为整数）："
                    f"var_name={exp.var_name!r} node_index={act.node_index_int} "
                    f"got_kv={_format_vt(act.dict_key_vt_int)}->{_format_vt(act.dict_value_vt_int)} "
                    f"expected_kv={_format_vt(exp.dict_key_vt_int)}->{_format_vt(exp.dict_value_vt_int)}"
                )
                continue

            if int(act.dict_key_vt_int) != int(exp.dict_key_vt_int) or int(act.dict_value_vt_int) != int(exp.dict_value_vt_int):
                mismatch_lines.append(
                    "OUT_PARAM 字典 K/V 类型不一致："
                    f"var_name={exp.var_name!r} node_index={act.node_index_int} "
                    f"got_kv={_format_vt(act.dict_key_vt_int)}->{_format_vt(act.dict_value_vt_int)} "
                    f"expected_kv={_format_vt(exp.dict_key_vt_int)}->{_format_vt(exp.dict_value_vt_int)} "
                    f"(from GraphModel output_port_types={exp.output_type_text!r})"
                )

            if isinstance(exp.expected_concrete_runtime_id_int, int) and int(exp.expected_concrete_runtime_id_int) > 0:
                if int(act.concrete_runtime_id_int) != int(exp.expected_concrete_runtime_id_int):
                    mismatch_lines.append(
                        "节点 concrete runtime_id 未按 TypeMappings(S<T:D<K,V>>) 切换（编辑器可能回退为整数）："
                        f"var_name={exp.var_name!r} node_index={act.node_index_int} "
                        f"got={int(act.concrete_runtime_id_int)} expected={int(exp.expected_concrete_runtime_id_int)}"
                    )

            if isinstance(exp.expected_out_index_of_concrete_int, int) and int(exp.expected_out_index_of_concrete_int) > 0:
                if int(act.outparam_index_of_concrete_int or 0) != int(exp.expected_out_index_of_concrete_int):
                    mismatch_lines.append(
                        "OUT_PARAM 缺少/写错 indexOfConcrete（编辑器可能回退为默认 concrete）："
                        f"var_name={exp.var_name!r} node_index={act.node_index_int} "
                        f"got={act.outparam_index_of_concrete_int!r} expected={int(exp.expected_out_index_of_concrete_int)}"
                    )

    if mismatch_lines:
        raise ValueError(
            "Get_Custom_Variable 字典 OUT_PARAM 校验失败：\n"
            f"- output_gil: {str(output_gil_written)}\n"
            f"- graph_id_int: {new_graph_id_int}\n"
            + "\n".join(f"- {line}" for line in mismatch_lines)
        )

    print("OK：Get_Custom_Variable 的字典 OUT_PARAM(K,V) 与 GraphModel 推断一致。")
    for exp in expected:
        print(
            f"- {exp.var_name}: kv={_format_vt(exp.dict_key_vt_int)}->{_format_vt(exp.dict_value_vt_int)} "
            f"(type={exp.output_type_text!r})"
        )
    print("=" * 80)

