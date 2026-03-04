from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True, slots=True)
class _NepPinDef:
    direction: str  # "In" | "Out"
    shell_index: int
    kernel_index: int
    type_expr: str
    identifier: str
    label_zh: str


def _resolve_node_editor_pack_data_json_path() -> Path:
    private_extensions_dir = Path(__file__).resolve().parents[2]
    return (
        private_extensions_dir
        / "third_party"
        / "Genshin-Impact-Miliastra-Wonderland-Code-Node-Editor-Pack"
        / "utils"
        / "node_data"
        / "data.json"
    ).resolve()


@lru_cache(maxsize=1)
def _load_node_editor_pack_nodes_by_id() -> Dict[int, Dict[str, Any]]:
    data_json_path = _resolve_node_editor_pack_data_json_path()
    if not data_json_path.is_file():
        return {}
    obj = json.loads(data_json_path.read_text(encoding="utf-8"))
    nodes = obj.get("Nodes") if isinstance(obj, dict) else None
    if not isinstance(nodes, list):
        return {}

    out: Dict[int, Dict[str, Any]] = {}
    for item in nodes:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("ID")
        if not isinstance(raw_id, int):
            continue
        out[int(raw_id)] = item
    return out


def _iter_nep_pins(node_record: Mapping[str, Any], *, is_flow: bool) -> List[_NepPinDef]:
    key = "FlowPins" if bool(is_flow) else "DataPins"
    raw = node_record.get(key)
    if not isinstance(raw, list):
        return []

    out: List[_NepPinDef] = []
    for p in raw:
        if not isinstance(p, Mapping):
            continue
        direction = str(p.get("Direction") or "").strip()
        if direction not in {"In", "Out"}:
            continue
        type_expr = str(p.get("Type") or "").strip()
        label_zh = ""
        label_obj = p.get("Label")
        if isinstance(label_obj, Mapping):
            label_zh = str(label_obj.get("zh-Hans") or "").strip()
        identifier = str(p.get("Identifier") or "").strip()
        shell_index = int(p.get("ShellIndex") or 0)
        raw_kernel_index = p.get("KernelIndex")
        kernel_index = int(raw_kernel_index) if isinstance(raw_kernel_index, int) else int(shell_index)
        out.append(
            _NepPinDef(
                direction=str(direction),
                shell_index=int(shell_index),
                kernel_index=int(kernel_index),
                type_expr=str(type_expr),
                identifier=str(identifier),
                label_zh=str(label_zh),
            )
        )
    return out


def _find_nep_pin_def(
    node_record: Optional[Mapping[str, Any]],
    *,
    is_flow: bool,
    direction: str,
    port_name: str,
    ordinal: int,
) -> Optional[_NepPinDef]:
    if node_record is None:
        return None
    direction_norm = str(direction or "").strip()
    if direction_norm not in {"In", "Out"}:
        raise ValueError(f"invalid direction: {direction!r}")

    name = str(port_name or "").strip()
    pins = [p for p in _iter_nep_pins(node_record, is_flow=bool(is_flow)) if p.direction == direction_norm]

    if name != "":
        for p in pins:
            if p.label_zh != "" and p.label_zh == name:
                return p
        for p in pins:
            if p.identifier != "" and p.identifier == name:
                return p

    pins_sorted = sorted(pins, key=lambda x: int(x.shell_index))
    if 0 <= int(ordinal) < len(pins_sorted):
        return pins_sorted[int(ordinal)]
    return None


def resolve_node_editor_pack_pin_indices(
    *,
    node_type_id_int: Optional[int],
    is_flow: bool,
    direction: str,
    port_name: str,
    ordinal: int,
    fallback_index: int,
) -> Tuple[int, int]:
    if not isinstance(node_type_id_int, int) or int(node_type_id_int) <= 0:
        return int(fallback_index), int(fallback_index)

    node_record = _load_node_editor_pack_nodes_by_id().get(int(node_type_id_int))
    hit = _find_nep_pin_def(
        node_record,
        is_flow=bool(is_flow),
        direction=str(direction),
        port_name=str(port_name),
        ordinal=int(ordinal),
    )
    if hit is None:
        return int(fallback_index), int(fallback_index)
    return int(hit.shell_index), int(hit.kernel_index)

