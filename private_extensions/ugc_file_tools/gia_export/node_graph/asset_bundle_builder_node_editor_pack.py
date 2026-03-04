from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple


@dataclass(frozen=True, slots=True)
class _NepPinDef:
    is_flow: bool
    direction: str  # "In" | "Out"
    shell_index: int
    kernel_index: int
    type_expr: str
    identifier: str
    label_zh: str


def _resolve_node_editor_pack_data_json_path() -> Path:
    """
    NodeEditorPack 节点画像真源（包含 ShellIndex/KernelIndex）。

    约定路径：
      private_extensions/third_party/Genshin-Impact-Miliastra-Wonderland-Code-Node-Editor-Pack/utils/node_data/data.json
    """
    private_extensions_dir = Path(__file__).resolve().parents[3]
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
        # NodeEditorPack 可能未随仓库分发/未初始化子模块；此时保持可导出，
        # 端口索引将回退到 GraphModel 顺序（shell=kernel=fallback_index）。
        return {}
    obj = json.loads(data_json_path.read_text(encoding="utf-8"))
    nodes = obj.get("Nodes") if isinstance(obj, dict) else None
    if not isinstance(nodes, list):
        # 不阻断导出：回退到 GraphModel 顺序（shell=kernel=fallback_index）。
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
                is_flow=bool(is_flow),
                direction=str(direction),
                shell_index=int(shell_index),
                kernel_index=int(kernel_index),
                type_expr=str(type_expr),
                identifier=str(identifier),
                label_zh=str(label_zh),
            )
        )
    return out


def _map_nep_type_expr_to_server_var_type_int(type_expr: str) -> int:
    """
    NodeEditorPack pin Type → server VarType（用于“补齐缺失 pins”的占位类型）。

    说明：
    - 这里只覆盖常见基础类型/列表/枚举；未知类型返回 0（仍会写入空 VarBase，避免阻断导出）。
    - 该映射只用于 **未在 GraphModel 中出现** 的占位 pins，不参与连线与常量写回。
    """
    t = str(type_expr or "").strip()
    if t == "":
        return 0
    # enum item：E<?>（注意：E<1016> 等并非枚举，而是特殊句柄/实体类型）
    if t == "E<?>":
        return 14
    # local variable handle：E<1016>（node_data TypeId=16）
    if t == "E<1016>":
        return 16
    # list：L<T>
    if t.startswith("L<") and t.endswith(">"):
        inner = t[len("L<") : -1].strip()
        inner_map: Dict[str, int] = {
            "GUID": 7,
            "Gid": 7,
            "Int": 8,
            "Bol": 9,
            "Flt": 10,
            "Str": 11,
            "Ety": 13,
            "Vec": 15,
        }
        hit = inner_map.get(inner)
        return int(hit or 0)
    mapping: Dict[str, int] = {
        "Ety": 1,  # Entity
        "GUID": 2,
        "Gid": 2,
        "Int": 3,
        "Bol": 4,
        "Flt": 5,
        "Str": 6,
        "Loc": 16,  # LocalVariable（node_data: E<1016>）
        "GUIDArr": 7,
        "IntArr": 8,
        "BolArr": 9,
        "FltArr": 10,
        "StrArr": 11,
        "Vec": 12,
        "EtyArr": 13,
        "VecArr": 15,
        "Faction": 17,
        "Config": 20,
        "Prefab": 21,
        "ConfigArr": 22,
        "PrefabArr": 23,
    }
    return int(mapping.get(t, 0))


def _find_nep_pin_def(
    node_record: Mapping[str, Any] | None,
    *,
    is_flow: bool,
    direction: str,
    port_name: str,
    ordinal: int,
) -> _NepPinDef | None:
    if node_record is None:
        return None
    direction_norm = str(direction or "").strip()
    if direction_norm not in {"In", "Out"}:
        raise ValueError(f"invalid direction: {direction!r}")

    name = str(port_name or "").strip()
    pins = [p for p in _iter_nep_pins(node_record, is_flow=bool(is_flow)) if p.direction == direction_norm]

    # 1) 优先按中文标签命中（GraphModel 端口名通常为 zh-Hans）
    if name != "":
        for p in pins:
            if p.label_zh != "" and p.label_zh == name:
                return p
        for p in pins:
            if p.identifier != "" and p.identifier == name:
                return p

    # 2) 兜底按顺序（按 ShellIndex 升序）
    pins_sorted = sorted(pins, key=lambda x: int(x.shell_index))
    if 0 <= int(ordinal) < len(pins_sorted):
        return pins_sorted[int(ordinal)]
    return None


def _resolve_pin_indices(
    node_record: Mapping[str, Any] | None,
    *,
    is_flow: bool,
    direction: str,
    port_name: str,
    ordinal: int,
    fallback_index: int,
) -> Tuple[int, int]:
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

