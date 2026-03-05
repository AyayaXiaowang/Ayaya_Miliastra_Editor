from __future__ import annotations

"""
GraphVariable 写回合约校验（库层实现）。

说明：
- 原本逻辑存在于 `ugc_file_tools.commands.check_graph_variable_writeback_contract`（入口层）；
- 写回链路（node_graph_writeback）需要复用该校验，因此必须下沉到库层，避免反向依赖 commands/。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

from ugc_file_tools.gil.graph_variable_scanner import iter_gil_files_from_paths, scan_gil_file_graph_variables
from ugc_file_tools.integrations.graph_generater.type_registry_bridge import (
    load_graph_generater_type_registry,
    map_graph_variable_cn_type_to_var_type_int,
)
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


def check_graph_variable_writeback_contract_or_raise(
    *,
    inputs: Sequence[Path],
    output_json_name: str = "graph_variable_writeback_contract.report.json",
    allow_extra_var_types: Sequence[int] | None = None,
    focus_graph_ids: Sequence[int] | None = None,
) -> Path:
    input_paths = [str(Path(p).resolve()) for p in (inputs or [])]
    if not input_paths:
        raise ValueError("inputs 不能为空")

    gil_files = iter_gil_files_from_paths(input_paths)

    tr = load_graph_generater_type_registry()
    allowed_var_types: Set[int] = {int(map_graph_variable_cn_type_to_var_type_int(t)) for t in tr.VARIABLE_TYPES}
    allowed_kv_types: Set[int] = set(allowed_var_types) - {27}

    extra_allowed: Set[int] = {int(v) for v in (allow_extra_var_types or [])}
    allowed_all: Set[int] = set(allowed_var_types) | set(extra_allowed)

    focus_ids_set: Optional[Set[int]] = None
    if focus_graph_ids is not None:
        focus_ids_set = {int(x) for x in list(focus_graph_ids) if isinstance(x, int)}
        if not focus_ids_set:
            focus_ids_set = None

    violations: List[Dict[str, Any]] = []
    checked_graphs = 0
    checked_vars = 0

    for f in gil_files:
        file_obs = scan_gil_file_graph_variables(f)
        for g in file_obs.graphs:
            if len(g.variables) == 0:
                continue
            if focus_ids_set is not None and int(g.graph_id_int) not in focus_ids_set:
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
                            "detail": f"VarType={vt} 不在 Graph_Generater.VARIABLE_TYPES（或 allow_extra_var_types）允许集合内。",
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
                    # 非字典变量 keyType/valueType 的真源口径存在两种常见形态：
                    # - legacy：显式写入 keyType=6/valueType=6（字符串占位）
                    # - after_game：省略 keyType/valueType 字段（scanner 中通常表现为 -1/-1）
                    #
                    # 写回侧允许两者并存：二者语义等价，且不同工具链/版本可能产生不同形态。
                    if (kt, vtt) not in {(6, 6), (-1, -1)}:
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
                                "detail": "非字典变量允许两种形态：显式 keyType=6/valueType=6（legacy）或省略 keyType/valueType（after_game；scanner 通常为 -1/-1）。",
                            }
                        )

    report_obj: Dict[str, Any] = {
        "inputs": {"paths": input_paths, "gil_files": [str(p) for p in gil_files]},
        "rules": {
            "allowed_var_types_from_graph_generater": sorted(list(allowed_var_types)),
            "allowed_kv_types_for_dict": sorted(list(allowed_kv_types)),
            "extra_allowed_var_types": sorted(list(extra_allowed)),
            "focus_graph_ids": sorted(list(focus_ids_set)) if focus_ids_set is not None else [],
        },
        "stats": {
            "total_files": len(gil_files),
            "checked_graphs_with_vars": checked_graphs,
            "checked_variables": checked_vars,
            "violations": len(violations),
        },
        "violations": violations,
    }

    out_path = resolve_output_file_path_in_out_dir(Path(str(output_json_name)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    if violations:
        raise ValueError(f"节点图变量写回合约校验失败：violations={len(violations)}，详见报告：{str(out_path)}")

    return out_path

