from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil.signal_scanner import (
    build_signal_name_role_to_id_map,
    build_signal_node_type_map,
    extract_signal_nodes_from_graph_ir,
    summarize_signal_entries,
)
from ugc_file_tools.gil_dump_codec.dump_json_tree import load_gil_payload_as_numeric_message
from ugc_file_tools.graph.node_graph.gil_payload_graph_ir import (
    parse_gil_payload_node_graphs_to_graph_ir,
)
from ugc_file_tools.node_data_index import resolve_default_node_data_index_path
from ugc_file_tools.output_paths import resolve_output_dir_path_in_out_dir


def _ensure_directory(target_dir: Path) -> None:
    Path(target_dir).mkdir(parents=True, exist_ok=True)


def _write_json_file(target_path: Path, payload: Any) -> None:
    Path(target_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text_file(target_path: Path, text: str) -> None:
    Path(target_path).write_text(str(text or ""), encoding="utf-8")


def _build_issues(
    *,
    signal_summaries: List[Mapping[str, Any]],
    graphs: List[Mapping[str, Any]],
    reference_signal_name_role_to_id: Optional[Mapping[str, Mapping[str, int]]] = None,
    reference_signal_name_to_signal_index: Optional[Mapping[str, int]] = None,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []

    # 运行时卡死类硬约束（无需 reference）：
    # - 在部分真源/编辑器口径中，0x6000xxxx/0x6080xxxx 的信号表会保留 (prefix+4,+5,+6) 给“占位无参信号”，
    #   后续真实信号从 (prefix+7) 起分配。若把带参数的真实信号误占用到 (prefix+4) 且未先写入占位项，
    #   编辑器可能仍能渲染，但运行时解析/分发可能失败，表现为“进不了游戏/无法开始游戏”。
    #
    # 兼容旧口径：若同一文件中出现了 (prefix+1)，则视为“从 0x..01 起递增三连号”的另一套口径，
    # 此时 (prefix+4) 可能是第 2 个信号的合法 id，不做占位约束。
    send_id_set = {int(s.get("send_id_int")) for s in signal_summaries if isinstance(s.get("send_id_int"), int)}
    for prefix in (0x60000000, 0x60800000):
        reserved_send_id = int(prefix + 4)
        reserved_listen_id = int(prefix + 5)
        reserved_server_id = int(prefix + 6)
        start_send_id = int(prefix + 1)

        if reserved_send_id not in send_id_set:
            continue
        if start_send_id in send_id_set:
            continue

        reserved_entries = [
            dict(s)
            for s in signal_summaries
            if isinstance(s.get("send_id_int"), int) and int(s.get("send_id_int")) == reserved_send_id
        ]
        ok_placeholder = False
        for s in reserved_entries:
            param_count = s.get("param_count")
            signal_index_int = s.get("signal_index_int")
            listen_id = s.get("listen_id_int")
            server_id = s.get("server_id_int")
            if (
                isinstance(param_count, int)
                and int(param_count) == 0
                and isinstance(signal_index_int, int)
                and int(signal_index_int) == 2
                and isinstance(listen_id, int)
                and int(listen_id) == reserved_listen_id
                and isinstance(server_id, int)
                and int(server_id) == reserved_server_id
            ):
                ok_placeholder = True
                break
        if not ok_placeholder:
            issues.append(
                {
                    "kind": "signal_entry_reserved_placeholder_mismatch",
                    "message": "检测到 0x6000/0x6080 信号号段的保留位被非占位无参信号占用（缺失/错写 bootstrap 占位项或其 signal_index 口径错误）。该口径下运行时可能无法开始游戏。",
                    "scope_prefix_int": int(prefix),
                    "scope_prefix_hex": f"0x{int(prefix):08X}",
                    "reserved_send_id_int": reserved_send_id,
                    "reserved_send_id_hex": f"0x{reserved_send_id:08X}",
                    "reserved_listen_id_int": reserved_listen_id,
                    "reserved_listen_id_hex": f"0x{reserved_listen_id:08X}",
                    "reserved_server_id_int": reserved_server_id,
                    "reserved_server_id_hex": f"0x{reserved_server_id:08X}",
                    "expected_placeholder": {
                        "param_count": 0,
                        "signal_index_int": 2,
                        "send_id_int": reserved_send_id,
                        "listen_id_int": reserved_listen_id,
                        "server_id_int": reserved_server_id,
                    },
                    "reserved_entries": reserved_entries,
                }
            )

    if reference_signal_name_role_to_id:
        for s in signal_summaries:
            name = str(s.get("signal_name") or "").strip()
            if name == "":
                continue
            ref = reference_signal_name_role_to_id.get(name)
            if not isinstance(ref, Mapping):
                continue

            for role in ("send", "listen", "server"):
                expected = ref.get(role)
                actual = s.get(f"{role}_id_int")
                if not isinstance(expected, int) or not isinstance(actual, int):
                    continue
                if int(expected) != int(actual):
                    issues.append(
                        {
                            "kind": "signal_entry_id_mismatch_against_reference",
                            "message": "同名信号的 entry id 与 reference .gil 不一致（可能导致运行时按另一套主键查表/分发失败）。",
                            "signal_name": name,
                            "role": role,
                            "expected_id_int": int(expected),
                            "actual_id_int": int(actual),
                            "expected_id_hex": f"0x{int(expected):08X}",
                            "actual_id_hex": f"0x{int(actual):08X}",
                            "signal_summary": dict(s),
                        }
                    )

    if reference_signal_name_to_signal_index:
        for s in signal_summaries:
            name = str(s.get("signal_name") or "").strip()
            if name == "":
                continue
            expected = reference_signal_name_to_signal_index.get(name)
            actual = s.get("signal_index_int")
            if not isinstance(expected, int) or not isinstance(actual, int):
                continue
            if int(expected) != int(actual):
                issues.append(
                    {
                        "kind": "signal_entry_signal_index_mismatch_against_reference",
                        "message": "同名信号的 signal_index 与 reference .gil 不一致（signal_entry.field_6 / node_def.meta.field_5 口径漂移可能触发更严格校验失败）。",
                        "signal_name": name,
                        "expected_signal_index_int": int(expected),
                        "actual_signal_index_int": int(actual),
                        "signal_summary": dict(s),
                    }
                )

    for s in signal_summaries:
        name = str(s.get("signal_name") or "").strip()
        if name == "":
            issues.append(
                {
                    "kind": "signal_entry_missing_name",
                    "message": "signal entry 缺少 signal_name（entry['3'] 为空）。",
                    "signal_summary": dict(s),
                }
            )

        for role in ("send", "listen", "server"):
            tid = s.get(f"{role}_id_int")
            if tid is None:
                issues.append(
                    {
                        "kind": "signal_entry_missing_node_def_id",
                        "message": f"signal entry 缺少 {role}_id_int（meta.field_5 未解析到）。",
                        "role": role,
                        "signal_name": name,
                        "signal_summary": dict(s),
                    }
                )
                continue
            if not isinstance(tid, int):
                issues.append(
                    {
                        "kind": "signal_entry_node_def_id_not_int",
                        "message": f"signal entry 的 {role}_id_int 不是 int。",
                        "role": role,
                        "signal_name": name,
                        "value_type": type(tid).__name__,
                        "signal_summary": dict(s),
                    }
                )

    for g in graphs:
        graph_id_int = g.get("graph_id_int")
        nodes = g.get("signal_nodes")
        if not isinstance(nodes, list):
            continue

        for n in nodes:
            if not isinstance(n, Mapping):
                continue

            node_index_int = n.get("node_index_int")
            role = str(n.get("role") or "")
            signal_name = str(n.get("signal_name") or "")
            node_type_id_int = n.get("node_type_id_int")

            pins_order_is_sorted = n.get("pins_order_is_sorted_by_kind_index")
            if pins_order_is_sorted is False:
                issues.append(
                    {
                        "kind": "signal_node_pin_records_not_sorted_by_kind_index",
                        "message": "信号节点的 pins(records) 顺序未按 (kind,index) 稳定排序（真源常见为 flow(2)→inparam(3)→outparam(4)→meta(5)）。已观测该差异可能导致“编辑器可渲染但运行时无法开始游戏”的现象。",
                        "graph_id_int": graph_id_int,
                        "node_index_int": node_index_int,
                        "role": role,
                        "signal_name": signal_name,
                        "pins_order": n.get("pins_order"),
                    }
                )

            if reference_signal_name_role_to_id and signal_name:
                ref = reference_signal_name_role_to_id.get(signal_name)
                expected = ref.get(role) if isinstance(ref, Mapping) else None
                if isinstance(expected, int) and isinstance(node_type_id_int, int) and int(expected) != int(node_type_id_int):
                    issues.append(
                        {
                            "kind": "signal_node_type_id_mismatch_against_reference",
                            "message": "信号节点实例 node_type_id_int 与 reference .gil 的同名信号/同 role id 不一致。",
                            "graph_id_int": graph_id_int,
                            "node_index_int": node_index_int,
                            "role": role,
                            "signal_name": signal_name,
                            "expected_id_int": int(expected),
                            "actual_id_int": int(node_type_id_int),
                            "expected_id_hex": f"0x{int(expected):08X}",
                            "actual_id_hex": f"0x{int(node_type_id_int):08X}",
                        }
                    )

            meta_pin = n.get("meta_pin")
            if meta_pin is None:
                issues.append(
                    {
                        "kind": "signal_node_missing_meta_pin",
                        "message": "信号节点缺少 META pin(kind=5,index=0)。",
                        "graph_id_int": graph_id_int,
                        "node_index_int": node_index_int,
                        "role": role,
                        "signal_name": signal_name,
                    }
                )
            elif isinstance(meta_pin, Mapping):
                meta_value = meta_pin.get("value")
                if meta_value != signal_name:
                    issues.append(
                        {
                            "kind": "signal_node_meta_mismatch",
                            "message": "信号节点 META pin 的 value 与 signal_name 不一致。",
                            "graph_id_int": graph_id_int,
                            "node_index_int": node_index_int,
                            "role": role,
                            "signal_name": signal_name,
                            "meta_value": meta_value,
                        }
                    )

            if role == "send":
                expected_param_count = int(n.get("signal_param_count") or 0)
                param_pins = n.get("param_pins")
                actual_param_count = len(param_pins) if isinstance(param_pins, list) else 0
                if actual_param_count != expected_param_count:
                    issues.append(
                        {
                            "kind": "signal_node_param_pin_count_mismatch",
                            "message": "发送信号节点的参数 pin 数量与 signal entry 的 param_count 不一致。",
                            "graph_id_int": graph_id_int,
                            "node_index_int": node_index_int,
                            "signal_name": signal_name,
                            "expected_param_count": expected_param_count,
                            "actual_param_pins": actual_param_count,
                        }
                    )

                if isinstance(param_pins, list):
                    indices = [
                        int(p.get("index_int") or 0)
                        for p in param_pins
                        if isinstance(p, Mapping) and p.get("index_int") is not None
                    ]
                    if indices and indices != list(range(min(indices), min(indices) + len(indices))):
                        issues.append(
                            {
                                "kind": "signal_node_param_pin_indices_not_contiguous",
                                "message": "发送信号节点的参数 pin index 不连续（可能导致端口绑定漂移）。",
                                "graph_id_int": graph_id_int,
                                "node_index_int": node_index_int,
                                "signal_name": signal_name,
                                "param_pin_indices": indices,
                            }
                        )

    return issues


def main(argv: Optional[Sequence[str]] = None) -> None:
    """
    提取 `.gil` 中“信号定义段 + NodeGraph 内信号节点使用情况”的只读摘要。

    推荐运行（仓库根目录）：
    - python -X utf8 private_extensions/run_ugc_file_tools.py tool inspect_gil_signals --help
    """
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="只读分析：从 .gil 提取 signal entries(root4/10/5/3) + NodeGraph 内信号节点实例摘要。",
    )
    parser.add_argument("--input-gil", dest="input_gil_file", required=True, help="输入 .gil 文件路径")
    parser.add_argument(
        "--reference-gil",
        dest="reference_gil_file",
        default="",
        help="可选：reference .gil（用于对照同名信号的 send/listen/server id 是否一致）。",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default="inspect_gil_signals",
        help="输出目录名（默认 inspect_gil_signals；实际会被收口到 ugc_file_tools/out/ 下）。",
    )
    parser.add_argument(
        "--node-data-index",
        dest="node_data_index",
        default=str(resolve_default_node_data_index_path()),
        help="节点数据索引 index.json 路径（默认：ugc_file_tools/node_data/index.json）",
    )
    parser.add_argument(
        "--graph-id",
        dest="graph_ids",
        action="append",
        type=int,
        default=[],
        help="仅分析指定 graph_id_int（可重复传多次）。不传则分析全部。",
    )
    parser.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=16,
        help="NodeGraph blob 深度解码上限（默认 16）。",
    )

    arguments = parser.parse_args(list(argv) if argv is not None else None)

    gil_path = Path(arguments.input_gil_file).resolve()
    if not gil_path.is_file():
        raise FileNotFoundError(str(gil_path))

    output_dir = resolve_output_dir_path_in_out_dir(Path(arguments.output_dir), default_dir_name="inspect_gil_signals")
    _ensure_directory(output_dir)

    payload_root = load_gil_payload_as_numeric_message(gil_path)
    signal_summaries = summarize_signal_entries(payload_root)
    signal_type_map = build_signal_node_type_map(signal_summaries)

    reference_signal_name_role_to_id: Optional[Mapping[str, Mapping[str, int]]] = None
    reference_signal_name_to_signal_index: Optional[Mapping[str, int]] = None
    reference_gil_file = str(arguments.reference_gil_file or "").strip()
    if reference_gil_file:
        ref_path = Path(reference_gil_file).resolve()
        if not ref_path.is_file():
            raise FileNotFoundError(str(ref_path))
        ref_payload_root = load_gil_payload_as_numeric_message(ref_path)
        ref_signal_summaries = summarize_signal_entries(ref_payload_root)
        reference_signal_name_role_to_id = build_signal_name_role_to_id_map(ref_signal_summaries)
        reference_signal_name_to_signal_index = {
            str(s.get("signal_name") or "").strip(): int(s.get("signal_index_int"))
            for s in ref_signal_summaries
            if str(s.get("signal_name") or "").strip() != "" and isinstance(s.get("signal_index_int"), int)
        }

    selected_graph_id_set: Optional[set[int]] = None
    if arguments.graph_ids:
        selected_graph_id_set = {int(x) for x in list(arguments.graph_ids or []) if isinstance(x, int)}

    parsed_graphs = parse_gil_payload_node_graphs_to_graph_ir(
        gil_file_path=gil_path,
        node_data_index_path=Path(arguments.node_data_index),
        graph_ids=(list(selected_graph_id_set) if selected_graph_id_set is not None else None),
        max_depth=int(arguments.max_depth),
    )

    graphs_out: List[Dict[str, Any]] = []
    for item in parsed_graphs:
        graph_ir = dict(item.graph_ir)
        signal_nodes = extract_signal_nodes_from_graph_ir(graph_ir, signal_type_map=signal_type_map)
        if not signal_nodes:
            continue
        graphs_out.append(
            {
                "graph_id_int": int(item.graph_id_int),
                "graph_name": str(item.graph_name or ""),
                "node_count": int(graph_ir.get("node_count") or 0),
                "signal_nodes_count": len(signal_nodes),
                "signal_nodes": signal_nodes,
            }
        )

    issues = _build_issues(
        signal_summaries=signal_summaries,
        graphs=graphs_out,
        reference_signal_name_role_to_id=reference_signal_name_role_to_id,
        reference_signal_name_to_signal_index=reference_signal_name_to_signal_index,
    )

    index = {
        "source_gil_file": str(gil_path),
        "output_dir": str(output_dir),
        "signals_count": len(signal_summaries),
        "graphs_count": len(parsed_graphs),
        "graphs_with_signal_nodes_count": len(graphs_out),
        "issues_count": len(issues),
        "files": {
            "signals": "signals.json",
            "graphs": "graphs.json",
            "issues": "issues.json",
        },
    }

    _write_json_file(output_dir / "index.json", index)
    _write_json_file(output_dir / "signals.json", signal_summaries)
    _write_json_file(output_dir / "graphs.json", graphs_out)
    _write_json_file(output_dir / "issues.json", issues)

    _write_text_file(
        output_dir / "claude.md",
        "\n".join(
            [
                "## 目录用途",
                "- `inspect_gil_signals` 的输出目录：汇总 `.gil` 的 signal entries 与 NodeGraph 内信号节点使用情况（用于对照/排查/反推格式）。",
                "",
                "## 当前状态",
                f"- 当前来源：`{gil_path}`",
                f"- signals_count: {len(signal_summaries)}",
                f"- graphs_count: {len(parsed_graphs)}（其中 graphs_with_signal_nodes_count={len(graphs_out)}）",
                f"- issues_count: {len(issues)}",
                "",
                "## 注意事项",
                "- 本目录为分析产物，可随时删除重建。",
                "- 本文件不记录修改历史，仅保持用途/状态/注意事项的实时描述。",
                "",
                "---",
                "注意：本文件不记录任何修改历史。请始终保持对“目录用途、当前状态、注意事项”的实时描述。",
                "",
            ]
        ),
    )

    print("=" * 80)
    print("inspect_gil_signals 完成：")
    print(f"- source_gil_file: {gil_path}")
    print(f"- output_dir: {output_dir}")
    print(f"- signals_count: {len(signal_summaries)}")
    print(f"- graphs_with_signal_nodes_count: {len(graphs_out)}")
    print(f"- issues_count: {len(issues)}")
    print("=" * 80)


__all__ = ["main"]

