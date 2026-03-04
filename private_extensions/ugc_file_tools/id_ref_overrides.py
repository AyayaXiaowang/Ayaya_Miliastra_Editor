from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple


@dataclass(frozen=True, slots=True)
class IdRefOverrides:
    """
    entity_key/component_key 占位符的手动覆盖映射（占位符 name → ID）。

    说明：
    - 该覆盖表的 key 是“占位符中的 name”，并不要求与参考 `.gil` 中的实体/元件 name 一致；
      覆盖的语义是“把这个占位符 name 当作另一个真实对象的 ID 来使用”。
    - 主要用于导出中心 UI：当按名称在参考 `.gil` 中找不到 ID 时，允许用户从地图/参考 `.gil`
      的候选全集中手动选择一个 ID，并继续导出/写回。
    """

    component_name_to_id: Dict[str, int]
    entity_name_to_guid: Dict[str, int]


_INT_RE = re.compile(r"^[+-]?\d+$")


def _coerce_positive_int_or_raise(value: object, *, label: str) -> int:
    if isinstance(value, int):
        if int(value) <= 0:
            raise ValueError(f"{label} 必须为正整数（got: {value!r}）")
        return int(value)
    if isinstance(value, str):
        text = str(value).strip()
        if not _INT_RE.fullmatch(text):
            raise ValueError(f"{label} 必须为整数文本（got: {value!r}）")
        iv = int(text)
        if int(iv) <= 0:
            raise ValueError(f"{label} 必须为正整数（got: {value!r}）")
        return int(iv)
    raise TypeError(f"{label} 必须为 int 或数字字符串（got: {type(value).__name__}）")


def _load_mapping_or_empty(obj: Any, *, field_name: str) -> Dict[str, int]:
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise TypeError(f"{field_name} must be dict[str,int] (got: {type(obj).__name__})")

    out: Dict[str, int] = {}
    for k, v in obj.items():
        key = str(k or "").strip()
        if key == "":
            raise ValueError(f"{field_name} 包含空 key")
        out[key] = _coerce_positive_int_or_raise(v, label=f"{field_name}[{key!r}]")
    return out


def load_id_ref_overrides_json_file(path: Path) -> IdRefOverrides:
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError("id_ref_overrides_json root must be dict")

    version = obj.get("version", 1)
    version_int = _coerce_positive_int_or_raise(version, label="version")
    if int(version_int) != 1:
        raise ValueError(f"unsupported id_ref_overrides_json version: {version_int!r}")

    comp = _load_mapping_or_empty(obj.get("component_name_to_id"), field_name="component_name_to_id")
    ent = _load_mapping_or_empty(obj.get("entity_name_to_guid"), field_name="entity_name_to_guid")
    return IdRefOverrides(component_name_to_id=dict(comp), entity_name_to_guid=dict(ent))


def apply_id_ref_overrides(
    *,
    component_name_to_id: Dict[str, int] | None,
    entity_name_to_guid: Dict[str, int] | None,
    overrides: IdRefOverrides | None,
) -> Tuple[Dict[str, int] | None, Dict[str, int] | None]:
    if overrides is None:
        return (
            (dict(component_name_to_id) if component_name_to_id is not None else None),
            (dict(entity_name_to_guid) if entity_name_to_guid is not None else None),
        )

    comp_base = dict(component_name_to_id or {})
    for k, v in dict(overrides.component_name_to_id or {}).items():
        key = str(k or "").strip()
        if key == "":
            continue
        if not isinstance(v, int) or int(v) <= 0:
            continue
        comp_base[key] = int(v)

    ent_base = dict(entity_name_to_guid or {})
    for k, v in dict(overrides.entity_name_to_guid or {}).items():
        key = str(k or "").strip()
        if key == "":
            continue
        if not isinstance(v, int) or int(v) <= 0:
            continue
        ent_base[key] = int(v)

    return (
        (dict(comp_base) if comp_base else (dict(component_name_to_id) if component_name_to_id else None)),
        (dict(ent_base) if ent_base else (dict(entity_name_to_guid) if entity_name_to_guid else None)),
    )


__all__ = [
    "IdRefOverrides",
    "apply_id_ref_overrides",
    "load_id_ref_overrides_json_file",
]

