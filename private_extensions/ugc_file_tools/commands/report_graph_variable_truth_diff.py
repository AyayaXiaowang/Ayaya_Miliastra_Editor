from __future__ import annotations

"""
report_graph_variable_truth_diff.py

目标：
- 以“真源 `.gil` 文件”为输入，不依赖 DLL，直接用自研 protobuf-like 解码器解析 payload；
- 扫描每个节点图 GraphEntry 的节点图变量定义表（GraphEntry['6']），提取：
  - VarType（变量类型）
  - keyType/valueType（字典键/值类型；非字典通常为字符串占位）
- 将“真源样本中观察到的类型集合”与 Graph_Generater 的 type_registry.VARIABLE_TYPES 做对比输出报告。

说明：
- 真源永远是唯一事实来源；Graph_Generater 作为高质量模拟器/规则实现，用于加速与约束生成形态。
- 不使用 try/except；失败直接抛错，便于定位样本差异或解码不兼容点。
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.integrations.graph_generater.type_registry_bridge import load_graph_generater_type_registry
from ugc_file_tools.gil.graph_variable_scanner import (
    FileObserved,
    iter_gil_files_from_paths,
    scan_gil_file_graph_variables,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def _build_var_type_int_to_cn_type_name_map() -> Dict[int, str]:
    """
    构造 var_type_int -> 中文类型名映射，用于报告可读性。

    约定：
    - 以 Graph_Generater.type_registry 的中文类型名作为主要来源（图变量允许集合）；
    - 对于真源样本中可能出现、但 Graph_Generater 不允许写回到“节点图变量表”的类型（例如 14/16），
      这里额外提供一个“可读名称”，但它们仍会被报告为 diff（不代表允许写回）。
    """
    tr = load_graph_generater_type_registry()
    mapping: Dict[int, str] = {}

    def put(cn_name: str, var_type_int: int) -> None:
        mapping.setdefault(int(var_type_int), str(cn_name))

    put(tr.TYPE_ENTITY, 1)
    put(tr.TYPE_GUID, 2)
    put(tr.TYPE_INTEGER, 3)
    put(tr.TYPE_BOOLEAN, 4)
    put(tr.TYPE_FLOAT, 5)
    put(tr.TYPE_STRING, 6)
    put(tr.TYPE_GUID_LIST, 7)
    put(tr.TYPE_INTEGER_LIST, 8)
    put(tr.TYPE_BOOLEAN_LIST, 9)
    put(tr.TYPE_FLOAT_LIST, 10)
    put(tr.TYPE_STRING_LIST, 11)
    put(tr.TYPE_VECTOR3, 12)
    put(tr.TYPE_ENTITY_LIST, 13)
    put(tr.TYPE_VECTOR3_LIST, 15)
    put(tr.TYPE_CAMP, 17)
    put(tr.TYPE_CONFIG_ID, 20)
    put(tr.TYPE_COMPONENT_ID, 21)
    put(tr.TYPE_CONFIG_ID_LIST, 22)
    put(tr.TYPE_COMPONENT_ID_LIST, 23)
    put(tr.TYPE_CAMP_LIST, 24)
    put(tr.TYPE_STRUCT, 25)
    put(tr.TYPE_STRUCT_LIST, 26)
    put(tr.TYPE_DICT, 27)

    # 已知但不允许作为“节点图变量类型”写回的 VarType（仅用于报告可读性）
    mapping.setdefault(14, "枚举")
    mapping.setdefault(16, "局部变量")
    return mapping


def _to_jsonable_file_observed(item: FileObserved, *, var_type_name_by_int: Dict[int, str]) -> Dict[str, Any]:
    return {
        "gil_path": item.gil_path,
        "graphs": [
            {
                "graph_id_int": g.graph_id_int,
                "graph_name": g.graph_name,
                "variables_count": len(g.variables),
                "var_types": sorted({int(v.var_type_int) for v in g.variables}),
                "var_type_names": sorted(
                    {var_type_name_by_int.get(int(v.var_type_int), f"<unknown:{v.var_type_int}>") for v in g.variables}
                ),
                "dict_kv_types": sorted(
                    {
                        (int(v.key_type_int), int(v.value_type_int))
                        for v in g.variables
                        if int(v.var_type_int) == 27 and int(v.key_type_int) >= 0 and int(v.value_type_int) >= 0
                    }
                ),
            }
            for g in item.graphs
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(description="扫描真源 .gil 中 GraphEntry['6'] 的节点图变量类型，并与 Graph_Generater VARIABLE_TYPES 做对比。")
    parser.add_argument(
        "inputs",
        nargs="+",
        help="输入 .gil 文件或目录（目录会递归扫描 *.gil）。建议传 ugc_file_tools/save/ 下的真源样本目录。",
    )
    parser.add_argument(
        "--output-json",
        default="graph_variable_truth_diff.report.json",
        help="输出报告文件名（强制写入 ugc_file_tools/out/）。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    input_paths = list(args.inputs)
    gil_files = iter_gil_files_from_paths(input_paths)

    tr = load_graph_generater_type_registry()
    expected_var_type_ints: Set[int] = set()
    for t in tr.VARIABLE_TYPES:
        # 仅收敛到 VarType 数字集合（字典仍为 27）
        # 这里不处理别名字典（因为 VARIABLE_TYPES 中包含 TYPE_DICT=字典；别名字典属于“表达方式”而非基础类型名）。
        if t == tr.TYPE_DICT:
            expected_var_type_ints.add(27)
            continue
        # 复用固定映射（与写回侧一致）
        expected_map = _build_var_type_int_to_cn_type_name_map()
        inv = {v: k for k, v in expected_map.items()}
        # 通过 cn_name 找 var_type_int：反查
        for vt_int, cn_name in expected_map.items():
            if cn_name == t:
                expected_var_type_ints.add(int(vt_int))
                break

    var_type_name_by_int = _build_var_type_int_to_cn_type_name_map()

    observed_files: List[FileObserved] = []
    observed_var_types: Set[int] = set()
    observed_dict_kv: Set[Tuple[int, int]] = set()
    diff_occurrences_by_var_type: Dict[int, List[Dict[str, Any]]] = {}

    for f in gil_files:
        file_obs = scan_gil_file_graph_variables(f)
        observed_files.append(file_obs)
        for g in file_obs.graphs:
            for v in g.variables:
                observed_var_types.add(int(v.var_type_int))
                if int(v.var_type_int) == 27 and int(v.key_type_int) >= 0 and int(v.value_type_int) >= 0:
                    observed_dict_kv.add((int(v.key_type_int), int(v.value_type_int)))
                if int(v.var_type_int) not in expected_var_type_ints:
                    diff_occurrences_by_var_type.setdefault(int(v.var_type_int), []).append(
                        {
                            "gil_path": file_obs.gil_path,
                            "graph_id_int": g.graph_id_int,
                            "graph_name": g.graph_name,
                            "var_name": v.name,
                            "var_type_int": int(v.var_type_int),
                            "key_type_int": int(v.key_type_int),
                            "value_type_int": int(v.value_type_int),
                        }
                    )

    observed_not_in_expected = sorted([t for t in observed_var_types if int(t) not in expected_var_type_ints])
    expected_not_observed = sorted([t for t in expected_var_type_ints if int(t) not in observed_var_types])

    diff_occurrences = [
        {
            "var_type_int": int(vt),
            "var_type_name": var_type_name_by_int.get(int(vt), f"<unknown:{vt}>"),
            "count": len(items),
            "occurrences": items,
        }
        for vt, items in sorted(diff_occurrences_by_var_type.items(), key=lambda kv: int(kv[0]))
    ]

    report_obj: Dict[str, Any] = {
        "inputs": {
            "paths": input_paths,
            "gil_files": [str(p) for p in gil_files],
        },
        "graph_generater": {
            "variable_types": list(tr.VARIABLE_TYPES),
            "expected_var_type_ints": sorted(list(expected_var_type_ints)),
        },
        "summary": {
            "total_files": len(observed_files),
            "files_with_graph_vars": sum(1 for f in observed_files if any(len(g.variables) > 0 for g in f.graphs)),
            "observed_var_type_ints": sorted(list(observed_var_types)),
            "observed_var_type_names": [
                var_type_name_by_int.get(int(x), f"<unknown:{x}>") for x in sorted(list(observed_var_types))
            ],
            "observed_dict_kv_types": sorted(list(observed_dict_kv)),
            "diff": {
                "observed_not_in_graph_generater": observed_not_in_expected,
                "graph_generater_not_observed": expected_not_observed,
                "occurrences": diff_occurrences,
            },
        },
        "files": [_to_jsonable_file_observed(f, var_type_name_by_int=var_type_name_by_int) for f in observed_files],
    }

    out_path = resolve_output_file_path_in_out_dir(Path(str(args.output_json)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print("================================================================================")
    print("真源节点图变量扫描报告已生成：")
    print(f"- inputs: {input_paths}")
    print(f"- gil_files: {len(gil_files)}")
    print(f"- output: {str(out_path)}")
    print("---- summary ----")
    print(f"observed_var_type_ints = {report_obj['summary']['observed_var_type_ints']}")
    print(f"observed_not_in_graph_generater = {observed_not_in_expected}")
    print(f"graph_generater_not_observed = {expected_not_observed}")
    print("================================================================================")


if __name__ == "__main__":
    main()




