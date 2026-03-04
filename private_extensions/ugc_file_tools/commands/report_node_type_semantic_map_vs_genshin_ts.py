from __future__ import annotations

"""
report_node_type_semantic_map_vs_genshin_ts.py

目标：
- 将 `graph_ir/node_type_semantic_map.json`（type_id → 中文节点名/置信度）与
  genshin-ts/NodeEditorPack 导出的 `genshin_ts__node_schema.report.json`（node_pin_records + concrete_map）
  做交叉对照，输出一份“可读诊断报告”，帮助快速定位：
  - type_id 映射缺失/错映射
  - 同名节点映射到多个 type_id（歧义）
  - 哪些节点存在 concrete_map（意味着写回阶段需要正确的 indexOfConcrete 才稳定）
  - 说明：genshin-ts 报告默认读取 `ugc_file_tools/refs/genshin_ts/genshin_ts__node_schema.report.json`

约束：
- 不使用 try/except；失败直接抛错（fail-fast）。
- 报告输出强制落盘到 `ugc_file_tools/out/`。
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.console_encoding import configure_console_encoding
from ugc_file_tools.node_graph_semantics.genshin_ts_node_schema import load_genshin_ts_node_schema_index
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import ugc_file_tools_root


def _default_mapping_json_path() -> Path:
    return (ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json").resolve()


def _read_json(path: Path) -> Any:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return json.loads(p.read_text(encoding="utf-8"))


def _try_parse_int(text: str) -> Optional[int]:
    t = str(text or "").strip()
    if t == "":
        return None
    if t.lstrip("-").isdigit():
        return int(t)
    return None


def _truncate_list(values: List[str], *, max_items: int) -> Tuple[List[str], bool]:
    if len(values) <= int(max_items):
        return list(values), False
    return list(values[: int(max_items)]), True


@dataclass(frozen=True, slots=True)
class _ConcretePinStat:
    total: int
    inparam: int
    outparam: int


def _build_concrete_pin_stats(concrete_pins: Dict[str, int]) -> Dict[int, _ConcretePinStat]:
    """
    将 ConcreteMap.pins（key: "generic_id:pin_type:pin_index"）汇总为：
    - generic_id -> count(inparam/outparam/total)
    """
    by_generic: Dict[int, Dict[str, int]] = {}
    for raw_key in concrete_pins.keys():
        key = str(raw_key or "").strip()
        parts = key.split(":")
        if len(parts) != 3:
            continue
        gid = _try_parse_int(parts[0])
        ptype = _try_parse_int(parts[1])
        if not isinstance(gid, int) or not isinstance(ptype, int):
            continue
        row = by_generic.setdefault(int(gid), {"total": 0, "inparam": 0, "outparam": 0})
        row["total"] += 1
        if int(ptype) == 3:
            row["inparam"] += 1
        elif int(ptype) == 4:
            row["outparam"] += 1

    out: Dict[int, _ConcretePinStat] = {}
    for gid, row in by_generic.items():
        out[int(gid)] = _ConcretePinStat(
            total=int(row.get("total") or 0),
            inparam=int(row.get("inparam") or 0),
            outparam=int(row.get("outparam") or 0),
        )
    return out


def build_report(
    *,
    mapping_json_path: Path,
    genshin_ts_report_path: Optional[Path],
    inputs_preview_max: int,
    outputs_preview_max: int,
) -> Dict[str, Any]:
    mapping_obj = _read_json(Path(mapping_json_path))
    if not isinstance(mapping_obj, dict):
        raise TypeError("node_type_semantic_map.json must be dict")

    schema_index = load_genshin_ts_node_schema_index(report_path=genshin_ts_report_path)
    if schema_index is None:
        raise FileNotFoundError(
            "genshin-ts node schema report 不存在："
            f"{str(genshin_ts_report_path) if genshin_ts_report_path is not None else '<default>'}"
        )

    concrete_stats_by_generic_id = _build_concrete_pin_stats(schema_index.concrete_pins)

    rows: List[Dict[str, Any]] = []
    missing_server_in_genshin_ts: List[int] = []
    missing_client_in_genshin_ts: List[int] = []

    cn_name_to_type_ids: Dict[Tuple[str, str], List[int]] = {}
    scope_counter: Dict[str, int] = {"server": 0, "client": 0, "unknown": 0}

    mapped_total = 0
    mapped_with_cn_name = 0
    matched_in_schema = 0

    for type_id_text, entry in mapping_obj.items():
        tid = _try_parse_int(type_id_text)
        if not isinstance(tid, int):
            continue
        if not isinstance(entry, dict):
            continue

        mapped_total += 1
        scope = str(entry.get("scope") or "").strip().lower() or "server"
        if scope not in {"server", "client"}:
            scope = "unknown"
        scope_counter[scope] = int(scope_counter.get(scope, 0)) + 1

        cn_name = str(entry.get("graph_generater_node_name") or "").strip()
        if cn_name:
            mapped_with_cn_name += 1
            cn_name_to_type_ids.setdefault((scope, cn_name), []).append(int(tid))

        rec = schema_index.record_by_node_id_int.get(int(tid))
        genshin_obj: Dict[str, Any] = {"exists": False}
        concrete_obj: Dict[str, Any] = {"has_any": False}
        if rec is None:
            if scope == "client":
                missing_client_in_genshin_ts.append(int(tid))
            else:
                missing_server_in_genshin_ts.append(int(tid))
        else:
            matched_in_schema += 1
            inputs_preview, inputs_truncated = _truncate_list(rec.inputs, max_items=int(inputs_preview_max))
            outputs_preview, outputs_truncated = _truncate_list(rec.outputs, max_items=int(outputs_preview_max))
            genshin_obj = {
                "exists": True,
                "name_en": str(rec.name),
                "generic_id": int(rec.id),
                "inputs_count": len(rec.inputs),
                "outputs_count": len(rec.outputs),
                "inputs_preview": inputs_preview,
                "outputs_preview": outputs_preview,
                "inputs_truncated": bool(inputs_truncated),
                "outputs_truncated": bool(outputs_truncated),
            }
            stat = concrete_stats_by_generic_id.get(int(rec.id))
            if stat is not None and int(stat.total) > 0:
                concrete_obj = {
                    "has_any": True,
                    "pin_key_total": int(stat.total),
                    "pin_key_inparam": int(stat.inparam),
                    "pin_key_outparam": int(stat.outparam),
                }
            else:
                concrete_obj = {"has_any": False, "pin_key_total": 0, "pin_key_inparam": 0, "pin_key_outparam": 0}

        rows.append(
            {
                "type_id_int": int(tid),
                "scope": str(scope),
                "graph_generater_node_name": str(cn_name),
                "confidence": str(entry.get("confidence") or ""),
                "semantic_id": str(entry.get("semantic_id") or ""),
                "notes": str(entry.get("notes") or ""),
                "genshin_ts": genshin_obj,
                "concrete_map": concrete_obj,
            }
        )

    def _sort_key(r: Dict[str, Any]) -> tuple:
        return (str(r.get("scope") or ""), int(r.get("type_id_int") or 0))

    rows.sort(key=_sort_key)
    missing_server_in_genshin_ts = sorted(set(int(x) for x in missing_server_in_genshin_ts))
    missing_client_in_genshin_ts = sorted(set(int(x) for x in missing_client_in_genshin_ts))

    duplicate_cn_name_mappings: List[Dict[str, Any]] = []
    for (scope, cn_name), ids in sorted(cn_name_to_type_ids.items(), key=lambda x: (x[0][0], x[0][1])):
        uniq = sorted(set(int(i) for i in ids))
        if len(uniq) <= 1:
            continue
        duplicate_cn_name_mappings.append({"scope": str(scope), "cn_name": str(cn_name), "type_ids": uniq})

    report: Dict[str, Any] = {
        "sources": {
            "node_type_semantic_map_json": str(Path(mapping_json_path).resolve()),
            "genshin_ts_node_schema_report_json": str(schema_index.report_path),
        },
        "summary": {
            "mapped_type_id_count": int(mapped_total),
            "mapped_with_cn_name_count": int(mapped_with_cn_name),
            "scope_counts": dict(scope_counter),
            "matched_in_genshin_ts_schema_count": int(matched_in_schema),
            "missing_server_in_genshin_ts_schema_count": int(len(missing_server_in_genshin_ts)),
            "missing_client_in_genshin_ts_schema_count": int(len(missing_client_in_genshin_ts)),
            "genshin_ts_schema_record_count": int(len(schema_index.record_by_node_id_int)),
            "genshin_ts_concrete_pins_count": int(len(schema_index.concrete_pins)),
            "duplicates_by_cn_name_count": int(len(duplicate_cn_name_mappings)),
        },
        "duplicates_by_cn_name": duplicate_cn_name_mappings,
        "missing_server_in_genshin_ts_schema_type_ids": missing_server_in_genshin_ts[:200],
        "missing_client_in_genshin_ts_schema_type_ids": missing_client_in_genshin_ts[:200],
        "rows": rows,
    }
    return report


def main(argv: Optional[Sequence[str]] = None) -> None:
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="对齐诊断：node_type_semantic_map.json ↔ genshin-ts node schema/concrete_map。",
    )
    parser.add_argument(
        "--mapping-json",
        default=str(_default_mapping_json_path()),
        help="node_type_semantic_map.json 路径（默认 ugc_file_tools/graph_ir/node_type_semantic_map.json）。",
    )
    parser.add_argument(
        "--genshin-ts-report-json",
        default="",
        help="可选：指定 genshin_ts__node_schema.report.json 路径（为空则使用默认 refs/genshin_ts 路径）。",
    )
    parser.add_argument(
        "--output-json",
        default="node_type_semantic_map_vs_genshin_ts.report.json",
        help="输出报告文件名（强制写入 ugc_file_tools/out/）。",
    )
    parser.add_argument(
        "--inputs-preview-max",
        type=int,
        default=8,
        help="每个节点在报告中最多预览多少个 inputs token（避免大节点爆炸）。",
    )
    parser.add_argument(
        "--outputs-preview-max",
        type=int,
        default=8,
        help="每个节点在报告中最多预览多少个 outputs token（避免大节点爆炸）。",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    mapping_json_path = Path(str(args.mapping_json)).resolve()
    genshin_report_text = str(getattr(args, "genshin_ts_report_json", "") or "").strip()
    genshin_report_path = Path(genshin_report_text).resolve() if genshin_report_text else None

    report = build_report(
        mapping_json_path=mapping_json_path,
        genshin_ts_report_path=genshin_report_path,
        inputs_preview_max=int(args.inputs_preview_max),
        outputs_preview_max=int(args.outputs_preview_max),
    )

    out_path = resolve_output_file_path_in_out_dir(Path(str(args.output_json)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))



