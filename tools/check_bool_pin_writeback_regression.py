from __future__ import annotations

"""
tools.check_bool_pin_writeback_regression

离线回归校验：对“布尔常量/端口映射回归图”执行：
- Graph Code -> GraphModel(JSON)
- GraphModel -> 写回到 .gil（pure-json）
- 从输出 .gil payload 解析 Graph IR
- 断言：所有 Bool InParam 常量均为显式 bool；并重点校验 Set_Custom_Variable(type_id=22) 的双 Bol 槽位不再错位

运行：
  python -X utf8 -m tools.check_bool_pin_writeback_regression
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------- 常量（避免魔法数字） ----------------------------
NODE_TYPE_ID_SET_CUSTOM_VARIABLE = 22
INPARAM_KIND_INT = 3
BOOL_TYPE_EXPR = "Bol"
SET_CUSTOM_VARIABLE_BOOL_PIN_A = 3
SET_CUSTOM_VARIABLE_BOOL_PIN_B = 4

GRAPH_ID_INT_FOR_REGRESSION = 1073741825

REGRESSION_GRAPH_CODE_REL = Path(
    "assets/资源库/项目存档/测试项目/节点图/server/实体节点图/回归/写回回归_bool_pins/TS_写回回归_布尔值端口映射.py"
)
BASE_GIL_REL = Path("private_extensions/ugc_file_tools/builtin_resources/empty_base_samples/empty_base_with_infra.gil")

OUT_BASENAME_GRAPH_MODEL_JSON = "bool_pin_writeback_regression.graph_model.json"
OUT_BASENAME_GIL = "bool_pin_writeback_regression.pure_json.gil"


@dataclass(frozen=True, slots=True)
class _PinKey:
    kind_int: int
    index_int: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_roots() -> None:
    repo_root = _repo_root()
    private_extensions_root = repo_root / "private_extensions"
    for p in (repo_root, private_extensions_root):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _iter_nodes(graph_ir: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    nodes = graph_ir.get("nodes")
    if not isinstance(nodes, list):
        raise TypeError("graph_ir.nodes must be list")
    for n in list(nodes):
        if isinstance(n, dict):
            yield n


def _pin_map_by_kind_index(node: Dict[str, Any]) -> Dict[_PinKey, Dict[str, Any]]:
    pins = node.get("pins")
    if not isinstance(pins, list):
        return {}
    out: Dict[_PinKey, Dict[str, Any]] = {}
    for p in list(pins):
        if not isinstance(p, dict):
            continue
        kind = p.get("kind_int")
        idx = p.get("index_int")
        if not isinstance(kind, int) or not isinstance(idx, int):
            continue
        out[_PinKey(kind_int=int(kind), index_int=int(idx))] = p
    return out


def _assert_all_bool_inparams_are_explicit_bool(graph_ir: Dict[str, Any]) -> None:
    for node in _iter_nodes(graph_ir):
        pins = node.get("pins")
        if not isinstance(pins, list):
            continue
        for pin in pins:
            if not isinstance(pin, dict):
                continue
            if int(pin.get("kind_int") or 0) != INPARAM_KIND_INT:
                continue
            if str(pin.get("type_expr") or "") != BOOL_TYPE_EXPR:
                continue
            if not isinstance(pin.get("value"), bool):
                raise AssertionError(
                    "Bool InParam 常量缺失/类型不对（期望为 bool）。"
                    f" node_type_id={node.get('node_type_id_int')!r}"
                    f" node_type_name={node.get('node_type_name')!r}"
                    f" pin_index={pin.get('index_int')!r}"
                    f" value={pin.get('value')!r}"
                )


def _assert_set_custom_variable_double_bool_slots(graph_ir: Dict[str, Any]) -> None:
    """
    Set_Custom_Variable(type_id=22) 真源有两个 Bol 入参槽位：
    - pin 3: 布尔
    - pin 4: 布尔
    回归目标：两者都必须存在，且值必须相等（避免“导出后界面显示为 否”的错位）。
    """
    hits: List[Tuple[int, bool, bool]] = []
    for node in _iter_nodes(graph_ir):
        if int(node.get("node_type_id_int") or 0) != NODE_TYPE_ID_SET_CUSTOM_VARIABLE:
            continue
        pin_map = _pin_map_by_kind_index(node)
        pa = pin_map.get(_PinKey(kind_int=INPARAM_KIND_INT, index_int=SET_CUSTOM_VARIABLE_BOOL_PIN_A))
        pb = pin_map.get(_PinKey(kind_int=INPARAM_KIND_INT, index_int=SET_CUSTOM_VARIABLE_BOOL_PIN_B))
        if not isinstance(pa, dict) or not isinstance(pb, dict):
            raise AssertionError(
                "Set_Custom_Variable 缺失双 Bool InParam pins（pin 3/4）。"
                f" node_index={node.get('node_index_int')!r}"
                f" pins_len={len(node.get('pins') or []) if isinstance(node.get('pins'), list) else None}"
            )
        va = pa.get("value")
        vb = pb.get("value")
        if not isinstance(va, bool) or not isinstance(vb, bool):
            raise AssertionError(
                "Set_Custom_Variable 的 pin 3/4 不是 bool 常量。"
                f" node_index={node.get('node_index_int')!r} v3={va!r} v4={vb!r}"
            )
        hits.append((int(node.get("node_index_int") or 0), bool(va), bool(vb)))
        if bool(va) != bool(vb):
            raise AssertionError(
                "Set_Custom_Variable 的双 Bool 槽位值不一致（错位/翻转）。"
                f" node_index={node.get('node_index_int')!r} v3={va!r} v4={vb!r}"
            )

    if not hits:
        raise AssertionError("回归图中未找到 Set_Custom_Variable(type_id=22) 节点，无法完成回归校验。")


def main(argv: Optional[List[str]] = None) -> int:
    _ensure_import_roots()

    # 延迟导入：确保 sys.path 已注入 private_extensions
    from ugc_file_tools.commands.export.export_graph_model_json_from_graph_code import (
        export_graph_model_json_from_graph_code,
    )
    from ugc_file_tools.node_graph_writeback.writer import run_write_and_postcheck_pure_json
    from ugc_file_tools.graph.node_graph.gil_payload_graph_ir import parse_gil_payload_node_graphs_to_graph_ir
    from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir

    repo_root = _repo_root()
    graph_code_path = (repo_root / REGRESSION_GRAPH_CODE_REL).resolve()
    base_gil_path = (repo_root / BASE_GIL_REL).resolve()

    if not graph_code_path.is_file():
        raise FileNotFoundError(str(graph_code_path))
    if not base_gil_path.is_file():
        raise FileNotFoundError(str(base_gil_path))

    out_graph_model_json = resolve_output_file_path_in_out_dir(Path(OUT_BASENAME_GRAPH_MODEL_JSON))
    out_gil = resolve_output_file_path_in_out_dir(Path(OUT_BASENAME_GIL))

    export_result = export_graph_model_json_from_graph_code(
        graph_code_file=graph_code_path,
        output_json_file=out_graph_model_json,
        graph_generater_root=repo_root,
        strict=True,
    )

    report, _postcheck_path = run_write_and_postcheck_pure_json(
        graph_model_json_path=Path(export_result["output_json"]),
        base_gil_path=base_gil_path,
        output_gil_path=out_gil,
        scope_graph_id_int=int(GRAPH_ID_INT_FOR_REGRESSION),
        new_graph_name="TS_BOOL_PIN_WRITEBACK_REGRESSION_OUT",
        new_graph_id_int=int(GRAPH_ID_INT_FOR_REGRESSION),
        mapping_path=repo_root / "private_extensions/ugc_file_tools/graph_ir/node_type_semantic_map.json",
        graph_generater_root=repo_root,
        skip_postcheck=False,
        prefer_signal_specific_type_id=False,
        auto_sync_ui_custom_variable_defaults=False,
    )

    if str(report.get("output_gil") or "") == "":
        raise RuntimeError(f"writeback report missing output_gil: keys={sorted(report.keys())}")

    parsed = parse_gil_payload_node_graphs_to_graph_ir(
        gil_file_path=Path(report["output_gil"]),
        node_data_index_path=repo_root / "private_extensions/ugc_file_tools/node_data/index.json",
        graph_ids=[int(GRAPH_ID_INT_FOR_REGRESSION)],
        max_depth=32,
    )
    if len(parsed) != 1:
        raise AssertionError(f"expected 1 graph ir, got {len(parsed)}")
    graph_ir = parsed[0].graph_ir
    if not isinstance(graph_ir, dict):
        raise TypeError("graph_ir must be dict")

    _assert_all_bool_inparams_are_explicit_bool(graph_ir)
    _assert_set_custom_variable_double_bool_slots(graph_ir)

    # 输出少量证据（便于人工复核，不做“伪造成功路径”）
    print("=" * 80)
    print("OK: bool pin writeback regression passed")
    print(f"- graph_code: {graph_code_path}")
    print(f"- graph_model_json: {out_graph_model_json}")
    print(f"- output_gil: {out_gil}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

