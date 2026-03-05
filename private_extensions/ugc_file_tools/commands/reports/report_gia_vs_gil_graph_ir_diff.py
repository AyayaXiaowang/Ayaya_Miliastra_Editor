from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.graph.model_ir import pick_graph_model_payload_and_metadata
from ugc_file_tools.graph.node_graph.gia_graph_ir import read_graph_irs_from_gia_file
from ugc_file_tools.graph.node_graph.gil_payload_graph_ir import parse_gil_payload_node_graphs_to_graph_ir
from ugc_file_tools.gia_export.node_graph.asset_bundle_builder import GiaAssetBundleGraphExportHints, create_gia_file_from_graph_model_json
from ugc_file_tools.node_graph_semantics.type_id_map import build_node_def_key_to_type_id
from ugc_file_tools.node_graph_writeback.pipeline import write_graph_model_to_gil
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir, resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import repo_root, ugc_file_tools_root


def _read_json(path: Path) -> Dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError(f"GraphModel JSON 顶层必须为 dict：path={str(path)!r}")
    return obj


def _infer_scope(metadata: Mapping[str, Any], graph_model: Mapping[str, Any]) -> str:
    for key in ("graph_scope", "graph_type"):
        v = metadata.get(key)
        if isinstance(v, str) and v.strip():
            text = v.strip().lower()
            if text in {"server", "client"}:
                return text
    meta2 = graph_model.get("metadata")
    if isinstance(meta2, Mapping):
        v2 = meta2.get("graph_type")
        if isinstance(v2, str) and v2.strip():
            text2 = v2.strip().lower()
            if text2 in {"server", "client"}:
                return text2
    return "server"


def _infer_graph_name(metadata: Mapping[str, Any], graph_model: Mapping[str, Any], fallback: str) -> str:
    v = metadata.get("graph_name")
    if isinstance(v, str) and v.strip():
        return v.strip()
    v2 = graph_model.get("graph_name")
    if isinstance(v2, str) and v2.strip():
        return v2.strip()
    return str(fallback or "untitled")


def _pick_graph_id_int_for_export(*, scope: str) -> int:
    # 仅用于本报告工具的“临时导出/对照”，不要求与真实项目分配一致。
    return 0x40000001 if str(scope) == "server" else 0x40800001


def _default_mapping_path() -> Path:
    return (ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json").resolve()


def _iter_node_dicts(graph_ir: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    nodes = graph_ir.get("nodes")
    if isinstance(nodes, list):
        for n in list(nodes):
            if isinstance(n, dict):
                yield n


def _iter_pin_dicts(node: Mapping[str, Any]) -> Iterable[Dict[str, Any]]:
    pins = node.get("pins")
    if isinstance(pins, list):
        for p in list(pins):
            if isinstance(p, dict):
                yield p


def _pin_key(pin: Mapping[str, Any]) -> Tuple[int, int]:
    kind = pin.get("kind_int")
    idx = pin.get("index_int")
    return (int(kind) if isinstance(kind, int) else 0, int(idx) if isinstance(idx, int) else 0)


def _node_index(node: Mapping[str, Any]) -> int:
    v = node.get("node_index_int")
    if isinstance(v, int):
        return int(v)
    return 0


def _node_type_id(node: Mapping[str, Any]) -> int:
    v = node.get("node_type_id_int")
    if isinstance(v, int):
        return int(v)
    return 0


def _compare_pin_fields(*, gia_pin: Mapping[str, Any], gil_pin: Mapping[str, Any]) -> List[Dict[str, Any]]:
    diffs: List[Dict[str, Any]] = []

    def _cmp_int(key: str) -> None:
        gv = gia_pin.get(key)
        lv = gil_pin.get(key)
        if gv is None and lv is None:
            return
        if isinstance(gv, int) and isinstance(lv, int) and int(gv) == int(lv):
            return
        diffs.append({"field": key, "gia": gv, "gil": lv})

    # VarType / type_id
    _cmp_int("type_id_int")

    # ConcreteBase.indexOfConcrete
    _cmp_int("concrete_index_of_concrete_int")

    # 字典 KV（MapBase K/V）
    _cmp_int("dict_key_type_int")
    _cmp_int("dict_value_type_int")

    return diffs


def diff_gia_vs_gil_graph_ir(
    *,
    gia_graph_ir: Mapping[str, Any],
    gil_graph_ir: Mapping[str, Any],
    allow_mismatched_node_type_ids: bool = False,
) -> Dict[str, Any]:
    gia_nodes_by_index: Dict[int, Dict[str, Any]] = {int(_node_index(n)): dict(n) for n in _iter_node_dicts(gia_graph_ir)}
    gil_nodes_by_index: Dict[int, Dict[str, Any]] = {int(_node_index(n)): dict(n) for n in _iter_node_dicts(gil_graph_ir)}

    issues: List[Dict[str, Any]] = []

    for node_index_int, gia_node in sorted(gia_nodes_by_index.items(), key=lambda kv: int(kv[0])):
        if int(node_index_int) <= 0:
            continue
        gil_node = gil_nodes_by_index.get(int(node_index_int))
        if gil_node is None:
            issues.append(
                {
                    "kind": "missing_node_in_gil",
                    "node_index_int": int(node_index_int),
                    "node_type_id_int": int(_node_type_id(gia_node)),
                }
            )
            continue

        gia_type = int(_node_type_id(gia_node))
        gil_type = int(_node_type_id(gil_node))
        if int(gia_type) != int(gil_type) and not bool(allow_mismatched_node_type_ids):
            issues.append(
                {
                    "kind": "node_type_id_mismatch",
                    "node_index_int": int(node_index_int),
                    "gia_node_type_id_int": int(gia_type),
                    "gil_node_type_id_int": int(gil_type),
                }
            )

        gia_pins = { _pin_key(p): dict(p) for p in _iter_pin_dicts(gia_node) }
        gil_pins = { _pin_key(p): dict(p) for p in _iter_pin_dicts(gil_node) }

        for pk, gia_pin in sorted(gia_pins.items(), key=lambda kv: (int(kv[0][0]), int(kv[0][1]))):
            gil_pin = gil_pins.get(pk)
            if gil_pin is None:
                issues.append(
                    {
                        "kind": "missing_pin_in_gil",
                        "node_index_int": int(node_index_int),
                        "node_type_id_int": int(gia_type),
                        "pin_kind_int": int(pk[0]),
                        "pin_index_int": int(pk[1]),
                        "gia_pin": {
                            "type_id_int": gia_pin.get("type_id_int"),
                            "type_expr": gia_pin.get("type_expr"),
                            "concrete_index_of_concrete_int": gia_pin.get("concrete_index_of_concrete_int"),
                            "dict_key_type_int": gia_pin.get("dict_key_type_int"),
                            "dict_value_type_int": gia_pin.get("dict_value_type_int"),
                        },
                    }
                )
                continue

            pin_diffs = _compare_pin_fields(gia_pin=gia_pin, gil_pin=gil_pin)
            if pin_diffs:
                issues.append(
                    {
                        "kind": "pin_field_mismatch",
                        "node_index_int": int(node_index_int),
                        "node_type_id_int": int(gia_type),
                        "pin_kind_int": int(pk[0]),
                        "pin_index_int": int(pk[1]),
                        "diffs": list(pin_diffs),
                    }
                )

    return {
        "gia_node_count": int(len(gia_nodes_by_index)),
        "gil_node_count": int(len(gil_nodes_by_index)),
        "issues_count": int(len(issues)),
        "issues": issues,
    }


def run_report_for_graph_model(
    *,
    graph_json_path: Path,
    template_gil_path: Path,
    base_gil_path: Optional[Path],
    template_library_dir: Optional[Path],
    template_graph_id_int: int,
    output_dir: Path,
    mapping_path: Path,
    graph_generater_root: Path,
    report_graph_id_int: int,
    allow_mismatched_node_type_ids: bool,
) -> Dict[str, Any]:
    graph_json_object = _read_json(Path(graph_json_path))
    metadata, graph_model = pick_graph_model_payload_and_metadata(dict(graph_json_object))

    scope = _infer_scope(metadata, graph_model)
    graph_name = _infer_graph_name(metadata, graph_model, fallback=Path(graph_json_path).stem)

    node_type_id_by_node_def_key = build_node_def_key_to_type_id(
        mapping_path=Path(mapping_path),
        scope=str(scope),
        graph_generater_root=Path(graph_generater_root),
    )

    output_dir = resolve_output_dir_path_in_out_dir(Path(output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    gia_out = resolve_output_file_path_in_out_dir(Path(output_dir) / f"{Path(graph_json_path).stem}.gia")
    hints = GiaAssetBundleGraphExportHints(
        graph_id_int=int(_pick_graph_id_int_for_export(scope=str(scope))),
        graph_name=str(graph_name),
        graph_scope=str(scope),
        resource_class=("ENTITY_NODE_GRAPH" if str(scope) == "server" else "BOOLEAN_FILTER_GRAPH"),
        graph_generater_root=Path(graph_generater_root).resolve(),
        node_type_id_by_node_def_key=dict(node_type_id_by_node_def_key),
        export_uid=0,
    )
    gia_report = create_gia_file_from_graph_model_json(
        graph_json_object=dict(graph_json_object),
        hints=hints,
        output_gia_path=Path(gia_out),
    )

    # 写回 gil：产出一份包含该图的 .gil，用于从 payload 抽取 Graph IR 对照
    gil_out = resolve_output_file_path_in_out_dir(Path(output_dir) / f"{Path(graph_json_path).stem}.gil")
    gil_report = write_graph_model_to_gil(
        graph_model_json_path=Path(graph_json_path),
        template_gil_path=Path(template_gil_path),
        base_gil_path=(Path(base_gil_path) if base_gil_path is not None else None),
        template_library_dir=(Path(template_library_dir) if template_library_dir is not None else None),
        output_gil_path=Path(gil_out),
        template_graph_id_int=int(template_graph_id_int),
        new_graph_name=f"_tmp_gia_vs_gil_diff__{graph_name}",
        new_graph_id_int=int(report_graph_id_int),
        mapping_path=Path(mapping_path),
        graph_generater_root=Path(graph_generater_root),
        auto_sync_ui_custom_variable_defaults=False,
        auto_fill_graph_variable_defaults_from_ui_registry=False,
        prefer_signal_specific_type_id=False,
    )

    gia_graph_irs = read_graph_irs_from_gia_file(Path(gia_out), check_header=False)
    if not gia_graph_irs:
        raise ValueError(f"未从 .gia 中解析到 NodeGraph GraphUnit：{str(gia_out)!r}")
    if len(gia_graph_irs) != 1:
        raise ValueError(f"报告工具期望 .gia 仅包含 1 张图，但得到 {len(gia_graph_irs)}：{str(gia_out)!r}")
    gia_graph_ir = dict(gia_graph_irs[0])

    gil_graph_irs = parse_gil_payload_node_graphs_to_graph_ir(
        gil_file_path=Path(gil_out),
        graph_ids=[int(report_graph_id_int)],
        max_depth=24,
    )
    if not gil_graph_irs:
        raise ValueError(
            "未从 .gil payload 中解析到目标 graph_id 的 NodeGraph blob："
            f"graph_id_int={int(report_graph_id_int)} path={str(gil_out)!r}"
        )
    if len(gil_graph_irs) != 1:
        raise ValueError(f"报告工具期望 .gil 仅命中 1 张图，但得到 {len(gil_graph_irs)}：graph_id_int={int(report_graph_id_int)}")
    gil_graph_ir = dict(gil_graph_irs[0].graph_ir)

    diff = diff_gia_vs_gil_graph_ir(
        gia_graph_ir=gia_graph_ir,
        gil_graph_ir=gil_graph_ir,
        allow_mismatched_node_type_ids=bool(allow_mismatched_node_type_ids),
    )

    report: Dict[str, Any] = {
        "graph_json": str(Path(graph_json_path).resolve()),
        "graph_name": str(graph_name),
        "graph_scope": str(scope),
        "gia": {"output_gia": str(gia_out), "create_report": dict(gia_report)},
        "gil": {"output_gil": str(gil_out), "writeback_report": dict(gil_report), "graph_id_int": int(report_graph_id_int)},
        "diff": dict(diff),
    }

    report_path = (Path(output_dir) / "report.gia_vs_gil_graph_ir_diff.json").resolve()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "output_dir": str(output_dir),
        "report": str(report_path),
        "issues_count": int(diff.get("issues_count") or 0),
        "output_gia": str(gia_out),
        "output_gil": str(gil_out),
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="对同一份 GraphModel 同时跑 GIA 导出与 GIL 写回，解析两边 Graph IR 并输出差异报告（用于定位“GIA 有但 GIL 没有/不一致”的口径问题）。"
    )
    parser.add_argument("--graph-json", required=True, help="输入 GraphModel JSON 文件路径（export_graph_model_json_from_graph_code 的输出）")
    parser.add_argument("--template-gil", required=True, help="GIL 写回使用的模板 .gil（提供节点图段结构与样本入口）")
    parser.add_argument("--template-graph-id", required=True, type=int, help="template .gil 中用于取样的 graph_id_int（server/client 视 scope 而定）")
    parser.add_argument("--base-gil", default="", help="可选：作为输出容器的 base .gil；为空则等同 template-gil")
    parser.add_argument("--template-library-dir", default="", help="可选：额外的样本库目录（递归扫描 *.gil）")
    parser.add_argument("--output-dir", default="_tmp_gia_vs_gil_graph_ir_diff", help="输出目录名（实际会被收口到 ugc_file_tools/out/ 下）")
    parser.add_argument("--mapping-path", default=str(_default_mapping_path()), help="node_type_semantic_map.json 路径")
    parser.add_argument("--graph-generater-root", default=str(repo_root()), help="Graph_Generater 根目录（包含 engine/assets）")
    parser.add_argument("--report-graph-id", type=int, default=0x40010001, help="写回到 .gil 的临时 graph_id_int（用于从 payload 定位目标图）")
    parser.add_argument("--allow-mismatched-node-type-ids", action="store_true", help="允许 node_type_id 不一致时仍继续比较 pins（仅用于诊断）")
    args = parser.parse_args(list(argv) if argv is not None else None)

    graph_json_path = Path(str(args.graph_json)).resolve()
    template_gil_path = Path(str(args.template_gil)).resolve()
    base_gil_path = Path(str(args.base_gil)).resolve() if str(args.base_gil).strip() else None
    template_library_dir = Path(str(args.template_library_dir)).resolve() if str(args.template_library_dir).strip() else None
    output_dir = Path(str(args.output_dir)).resolve()

    result = run_report_for_graph_model(
        graph_json_path=graph_json_path,
        template_gil_path=template_gil_path,
        base_gil_path=base_gil_path,
        template_library_dir=template_library_dir,
        template_graph_id_int=int(args.template_graph_id),
        output_dir=output_dir,
        mapping_path=Path(str(args.mapping_path)).resolve(),
        graph_generater_root=Path(str(args.graph_generater_root)).resolve(),
        report_graph_id_int=int(args.report_graph_id),
        allow_mismatched_node_type_ids=bool(args.allow_mismatched_node_type_ids),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


__all__ = ["main", "run_report_for_graph_model", "diff_gia_vs_gil_graph_ir"]

