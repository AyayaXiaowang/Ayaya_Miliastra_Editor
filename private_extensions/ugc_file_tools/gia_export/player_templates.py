from __future__ import annotations

import copy
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from ugc_file_tools.fs_naming import sanitize_file_stem
from ugc_file_tools.gia.container import wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message

from .templates import (
    CustomVariableDef,
    load_component_base_bundle_from_gia,
    patch_bundle_with_custom_variables,
)


@dataclass(frozen=True, slots=True)
class PlayerTemplateConfig:
    template_id: str
    template_name: str
    custom_variable_file_refs: list[str]


def build_player_template_low16(*, template_key: str) -> int:
    """
    生成玩家模板相关资源的 low16（强制 0x8000~0xFFFF），用于构造稳定 root_id_int：
    - player_template_root_id_int: 0x40C0xxxx
    - role_editor_root_id_int:     0x4100xxxx
    """
    key_text = str(template_key or "").strip()
    if key_text == "":
        raise ValueError("template_key 不能为空")
    h = int(zlib.crc32(key_text.encode("utf-8")) & 0xFFFFFFFF)
    return int(0x8000 | (h & 0x7FFF))


def bump_player_template_low16(value: int) -> int:
    """
    当稳定 low16 冲突时，按 low16 顺序 bump（保持 0x8000~0xFFFF）。
    """
    low = int(value) & 0xFFFF
    low2 = int(low) + 1
    if low2 > 0xFFFF:
        low2 = 0x8000
    if low2 < 0x8000:
        low2 = 0x8000
    return int(low2)


def build_player_template_root_id_int(*, low16: int) -> int:
    low = int(low16) & 0xFFFF
    if low < 0x8000:
        low = 0x8000
    return int(0x40C00000 | low)


def build_player_template_role_editor_root_id_int(*, low16: int) -> int:
    low = int(low16) & 0xFFFF
    if low < 0x8000:
        low = 0x8000
    return int(0x41000000 | low)


def load_player_template_base_bundle_from_gia(
    base_gia_file: Path,
    *,
    max_depth: int = 16,
    prefer_raw_hex_for_utf8: bool = True,
) -> dict[str, Any]:
    """
    读取一个“玩家模板 base .gia”，并解码为可写回的 numeric_message（数值键 dict）。

    说明：实现复用 `load_component_base_bundle_from_gia`（它本身对任意 .gia bundle 都适用）。
    """
    return load_component_base_bundle_from_gia(
        base_gia_file,
        max_depth=int(max_depth),
        prefer_raw_hex_for_utf8=bool(prefer_raw_hex_for_utf8),
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _require_dict(value: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError(f"{path} must be dict, got {type(value).__name__}")
    return value


def _extract_resource_name_text(resource_entry: Mapping[str, Any]) -> str:
    raw = resource_entry.get("3")
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _extract_resource_root_id_int(resource_entry: Mapping[str, Any], *, path: str) -> int:
    id_message = _require_dict(resource_entry.get("1"), path=f"{path}['1']")
    rid = id_message.get("4")
    if not isinstance(rid, int):
        raise TypeError(f"{path}['1']['4'] must be int, got {type(rid).__name__}")
    return int(rid)


def _deep_replace_ints_in_place(value: Any, *, mapping: Mapping[int, int]) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        replaced = mapping.get(int(value))
        return int(replaced) if isinstance(replaced, int) else value
    if isinstance(value, list):
        for i, item in enumerate(list(value)):
            value[i] = _deep_replace_ints_in_place(item, mapping=mapping)
        return value
    if isinstance(value, dict):
        for k in list(value.keys()):
            value[k] = _deep_replace_ints_in_place(value.get(k), mapping=mapping)
        return value
    return value


def _patch_resource_entry_name_record_if_possible(resource_entry: dict[str, Any], *, new_name_text: str) -> None:
    payload11 = resource_entry.get("11")
    if not isinstance(payload11, dict):
        return
    payload = payload11.get("1")
    if not isinstance(payload, dict):
        return
    records = payload.get("6")
    if not isinstance(records, list):
        return
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("1") != 1:
            continue
        if "11" not in record:
            continue
        record["11"] = {"1": str(new_name_text)}
        return


def _patch_related_resource_names_by_prefix(
    bundle: dict[str, Any],
    *,
    base_template_name: str,
    new_template_name: str,
) -> None:
    base = str(base_template_name or "").strip()
    if base == "":
        return
    new_name = str(new_template_name or "").strip()
    if new_name == "":
        return

    extras_raw = bundle.get("2")
    extras_list = [x for x in _as_list(extras_raw) if isinstance(x, dict)]
    if not extras_list:
        return

    for entry in extras_list:
        name_text = _extract_resource_name_text(entry)
        if name_text == "" or not name_text.startswith(base):
            continue
        suffix = name_text[len(base) :]
        patched_name = new_name + suffix
        entry["3"] = str(patched_name)
        _patch_resource_entry_name_record_if_possible(entry, new_name_text=str(patched_name))


def _find_role_editor_resource_id_int(
    bundle: Mapping[str, Any],
    *,
    base_template_name: str,
) -> int | None:
    base = str(base_template_name or "").strip()
    if base == "":
        return None
    target_name = f"{base}(角色编辑)"
    extras_raw = bundle.get("2")
    for entry in _as_list(extras_raw):
        if not isinstance(entry, dict):
            continue
        name_text = _extract_resource_name_text(entry)
        if name_text != target_name:
            continue
        return _extract_resource_root_id_int(entry, path="bundle['2'][role_editor]")
    return None


def build_player_template_gia_bytes_from_base_bundle(
    base_bundle: Mapping[str, Any],
    *,
    template_name: str,
    custom_variables: Sequence[CustomVariableDef],
    template_root_id_int: int,
    role_editor_root_id_int: int | None = None,
    output_file_stem: str | None = None,
) -> bytes:
    """
    基于 base 玩家模板 bundle（numeric_message）生成新的玩家模板 `.gia`：
    - 写入主资源名称 + name record
    - 写入 override variables group1（自定义变量列表）
    - 替换主资源 root_id_int（并同步替换 role editor 的 root_id_int/引用，若存在）
    - 重建 Root.filePath（继承 base 的 uid/id，更新 timestamp 与 file 名）
    - 同步替换“相关资源条目”的名称前缀（例如 "<base>(角色编辑)" -> "<new>(角色编辑)"）

    注意：
    - 该实现仍是 template-driven：不重编码完整 schema，仅对可控字段做补丁；
    - `role_editor_root_id_int` 为空时，仅更新主资源 id，role editor 仍保持 base id（不推荐用于多模板导入场景）。
    """
    base_bundle_dict = dict(base_bundle)
    base_resource = _require_dict(base_bundle_dict.get("1"), path="bundle['1']")
    base_template_name = _extract_resource_name_text(base_resource)

    old_main_id_int = _extract_resource_root_id_int(base_resource, path="bundle['1']")
    old_role_id_int = _find_role_editor_resource_id_int(base_bundle_dict, base_template_name=base_template_name)

    # 1) patch 主资源：名称 + 自定义变量 + id + filePath
    bundle = patch_bundle_with_custom_variables(
        base_bundle_dict,
        template_name=str(template_name),
        custom_variables=custom_variables,
        template_root_id_int=int(template_root_id_int),
        output_file_stem=str(output_file_stem or "").strip() or sanitize_file_stem(str(template_name)) or None,
    )

    # 2) 替换 id 引用（主资源 + role editor）
    id_map: dict[int, int] = {int(old_main_id_int): int(template_root_id_int)}
    if isinstance(old_role_id_int, int) and isinstance(role_editor_root_id_int, int):
        id_map[int(old_role_id_int)] = int(role_editor_root_id_int)
    _deep_replace_ints_in_place(bundle, mapping=id_map)

    # 3) 同步 patch 相关资源名称（仅按 base_name 前缀替换）
    _patch_related_resource_names_by_prefix(
        bundle,
        base_template_name=str(base_template_name),
        new_template_name=str(template_name),
    )

    proto_bytes = encode_message(dict(bundle))
    return wrap_gia_container(proto_bytes)


__all__ = [
    "PlayerTemplateConfig",
    "build_player_template_low16",
    "bump_player_template_low16",
    "build_player_template_root_id_int",
    "build_player_template_role_editor_root_id_int",
    "load_player_template_base_bundle_from_gia",
    "build_player_template_gia_bytes_from_base_bundle",
]

