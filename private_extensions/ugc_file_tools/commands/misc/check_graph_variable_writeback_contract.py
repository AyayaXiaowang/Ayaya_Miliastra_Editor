from __future__ import annotations

"""
check_graph_variable_writeback_contract.py

用途：
- 对“写回生成/改写后的 .gil”做合约校验（Contract Test），重点关注节点图变量定义表（GraphEntry['6']）：
  - VarType 必须属于 Graph_Generater.type_registry.VARIABLE_TYPES（允许用 --allow-extra-var-types 额外放行）
  - 非字典变量：keyType/valueType 必须为 6/6（字符串占位，按当前 schema/样本口径）
  - 字典变量：keyType/valueType 必须是受支持的非字典类型（禁止 dict 递归）

说明：
- 本工具不依赖 DLL，直接解码 `.gil` payload（protobuf-like）。
- 不使用 try/except；错误直接抛出（或汇总后抛出），便于定位不符合合约的写回产物。
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.gil.graph_variable_scanner import iter_gil_files_from_paths, scan_gil_file_graph_variables
from ugc_file_tools.integrations.graph_generater.type_registry_bridge import (
    load_graph_generater_type_registry,
    map_graph_variable_cn_type_to_var_type_int,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _parse_int_list(values: Sequence[str]) -> List[int]:
    out: List[int] = []
    for v in values:
        t = str(v).strip()
        if t == "":
            continue
        if not t.isdigit():
            raise ValueError(f"期望整数列表，但收到：{v!r}")
        out.append(int(t))
    return out


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="合约校验：检查写回 .gil 的 GraphEntry['6'] 节点图变量表是否满足类型/字段不变量。")
    parser.add_argument("inputs", nargs="+", help="输入 .gil 文件或目录（目录会递归扫描 *.gil）。")
    parser.add_argument(
        "--allow-extra-var-types",
        nargs="*",
        default=[],
        help="额外允许出现的 VarType 整数（例如真源样本可能包含 14/16）。默认不允许。",
    )
    parser.add_argument(
        "--output-json",
        default="graph_variable_writeback_contract.report.json",
        help="输出报告文件名（强制写入 ugc_file_tools/out/）。",
    )
    parser.add_argument(
        "--graph-id",
        action="append",
        default=None,
        type=int,
        help="仅校验指定 graph_id_int（可重复传入多次）。不传则校验所有包含节点图变量的图。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    input_paths = list(args.inputs)
    gil_files = iter_gil_files_from_paths(input_paths)

    tr = load_graph_generater_type_registry()
    allowed_var_types: Set[int] = {int(map_graph_variable_cn_type_to_var_type_int(t)) for t in tr.VARIABLE_TYPES}
    allowed_kv_types: Set[int] = set(allowed_var_types) - {27}

    extra_allowed: Set[int] = set(_parse_int_list(list(args.allow_extra_var_types)))
    allowed_all: Set[int] = set(allowed_var_types) | set(extra_allowed)

    focus_graph_ids: Optional[Set[int]] = None
    if args.graph_id is not None:
        focus_graph_ids = {int(x) for x in list(args.graph_id) if isinstance(x, int)}
        if not focus_graph_ids:
            focus_graph_ids = None

    violations: List[Dict[str, Any]] = []
    checked_graphs = 0
    checked_vars = 0

    for f in gil_files:
        file_obs = scan_gil_file_graph_variables(f)
        for g in file_obs.graphs:
            if len(g.variables) == 0:
                continue
            if focus_graph_ids is not None and int(g.graph_id_int) not in focus_graph_ids:
                continue
            checked_graphs += 1
            for v in g.variables:
                checked_vars += 1

                vt = int(v.var_type_int)
                kt = int(v.key_type_int)
                vtt = int(v.value_type_int)

                if vt not in allowed_all:
                    violations.append(
                        {
                            "gil_path": file_obs.gil_path,
                            "graph_id_int": g.graph_id_int,
                            "graph_name": g.graph_name,
                            "var_name": v.name,
                            "var_type_int": vt,
                            "issue": "VAR_TYPE_NOT_ALLOWED",
                            "detail": f"VarType={vt} 不在 Graph_Generater.VARIABLE_TYPES（或 --allow-extra-var-types）允许集合内。",
                        }
                    )
                    continue

                if vt == 27:
                    if kt not in allowed_kv_types:
                        violations.append(
                            {
                                "gil_path": file_obs.gil_path,
                                "graph_id_int": g.graph_id_int,
                                "graph_name": g.graph_name,
                                "var_name": v.name,
                                "var_type_int": vt,
                                "key_type_int": kt,
                                "value_type_int": vtt,
                                "issue": "DICT_KEY_TYPE_INVALID",
                                "detail": f"字典变量 keyType={kt} 非法（必须为受支持的非字典类型）。",
                            }
                        )
                    if vtt not in allowed_kv_types:
                        violations.append(
                            {
                                "gil_path": file_obs.gil_path,
                                "graph_id_int": g.graph_id_int,
                                "graph_name": g.graph_name,
                                "var_name": v.name,
                                "var_type_int": vt,
                                "key_type_int": kt,
                                "value_type_int": vtt,
                                "issue": "DICT_VALUE_TYPE_INVALID",
                                "detail": f"字典变量 valueType={vtt} 非法（必须为受支持的非字典类型）。",
                            }
                        )
                else:
                    if kt != 6 or vtt != 6:
                        violations.append(
                            {
                                "gil_path": file_obs.gil_path,
                                "graph_id_int": g.graph_id_int,
                                "graph_name": g.graph_name,
                                "var_name": v.name,
                                "var_type_int": vt,
                                "key_type_int": kt,
                                "value_type_int": vtt,
                                "issue": "NON_DICT_KEY_VALUE_TYPE_NOT_6_6",
                                "detail": "非字典变量应写入 keyType=6/valueType=6（字符串占位）。",
                            }
                        )

    report_obj: Dict[str, Any] = {
        "inputs": {"paths": input_paths, "gil_files": [str(p) for p in gil_files]},
        "rules": {
            "allowed_var_types_from_graph_generater": sorted(list(allowed_var_types)),
            "allowed_kv_types_for_dict": sorted(list(allowed_kv_types)),
            "extra_allowed_var_types": sorted(list(extra_allowed)),
            "focus_graph_ids": sorted(list(focus_graph_ids)) if focus_graph_ids is not None else [],
        },
        "stats": {
            "total_files": len(gil_files),
            "checked_graphs_with_vars": checked_graphs,
            "checked_variables": checked_vars,
            "violations": len(violations),
        },
        "violations": violations,
    }

    out_path = resolve_output_file_path_in_out_dir(Path(str(args.output_json)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("================================================================================")
    print("节点图变量写回合约校验报告已生成：")
    print(f"- inputs: {input_paths}")
    print(f"- gil_files: {len(gil_files)}")
    print(f"- output: {str(out_path)}")
    print("---- stats ----")
    print(f"checked_graphs_with_vars = {checked_graphs}")
    print(f"checked_variables = {checked_vars}")
    print(f"violations = {len(violations)}")
    print("================================================================================")

    if violations:
        raise ValueError(f"节点图变量写回合约校验失败：violations={len(violations)}，详见报告：{str(out_path)}")


if __name__ == "__main__":
    main()



