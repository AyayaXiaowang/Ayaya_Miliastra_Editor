from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.custom_variables.apply import ensure_override_variables_group1_container, find_root4_5_1_entry_by_name
from ugc_file_tools.custom_variables.coerce import normalize_custom_variable_name_field2
from ugc_file_tools.custom_variables.defaults import normalize_variable_defaults_map
from ugc_file_tools.custom_variables.specs import (
    CustomVariableSpec,
    build_custom_variable_item_from_spec,
    infer_custom_variable_spec_from_default,
)

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)
from .web_ui_import_bundle import _extract_variable_defaults_from_html_text

def _iter_specs_from_html_defaults(html_files: Iterable[Path]) -> List[CustomVariableSpec]:
    merged_raw: Dict[str, Any] = {}
    for p in list(html_files):
        text = Path(p).read_text(encoding="utf-8")
        extracted = _extract_variable_defaults_from_html_text(text)
        # 后者覆盖前者
        merged_raw.update(dict(extracted or {}))

    normalized = normalize_variable_defaults_map(merged_raw)
    specs: List[CustomVariableSpec] = []
    for full_name, value in normalized.items():
        full = str(full_name or "").strip()
        if full == "":
            continue
        group_name, sep, var_name = full.partition(".")
        if sep != "." or not group_name or not var_name:
            raise ValueError(f"variable_defaults key 非法（必须为 组.变量名）：{full!r}")
        specs.append(infer_custom_variable_spec_from_default(group_name=group_name, variable_name=var_name, default_value=value))
    return specs


def _patch_one_entry(
    asset_entry: Dict[str, Any],
    *,
    spec: CustomVariableSpec,
    overwrite_dict_when_exists: bool,
) -> Dict[str, Any]:
    group_item = ensure_override_variables_group1_container(asset_entry)
    container = group_item.get("11")
    if not isinstance(container, dict):
        raise RuntimeError("internal error: group_item['11'] is not dict")
    variable_items = container.get("1")
    if not isinstance(variable_items, list):
        raise RuntimeError("internal error: group_item['11']['1'] is not list")

    name = str(spec.variable_name or "").strip()
    if name == "":
        raise ValueError("variable_name 不能为空")

    indices: List[int] = []
    for i, item in enumerate(list(variable_items)):
        if not isinstance(item, dict):
            continue
        if normalize_custom_variable_name_field2(item.get("2")) == name:
            indices.append(int(i))

    desired_item = build_custom_variable_item_from_spec(spec)
    desired_vt = int(desired_item.get("3") or 0)

    if not indices:
        variable_items.append(desired_item)
        return {"action": "created", "name": name, "var_type_int": desired_vt}

    idx0 = indices[0]
    existing = variable_items[idx0]
    if not isinstance(existing, dict):
        # 结构异常：直接覆盖
        variable_items[idx0] = desired_item
        return {"action": "replaced", "name": name, "var_type_int": desired_vt, "reason": "existing_item_not_dict"}

    existing_vt = int(existing.get("3") or 0)
    if desired_vt == 27 and existing_vt == 27 and (not bool(overwrite_dict_when_exists)):
        # 安全策略：默认不覆盖已有 dict 的具体键值（避免破坏真源/历史 meta 结构）。
        return {"action": "kept", "name": name, "var_type_int": existing_vt, "reason": "dict_keep_existing"}

    # 覆盖：类型不对 / 或者值不对（我们按 spec 作为权威）
    variable_items[idx0] = desired_item
    if len(indices) > 1:
        # 去重：保留第一个，删除其余同名项（避免编辑器列表同名膨胀）
        for j in reversed(indices[1:]):
            del variable_items[int(j)]
        return {
            "action": "replaced_dedup",
            "name": name,
            "old_var_type_int": existing_vt,
            "var_type_int": desired_vt,
            "removed_duplicates": int(len(indices) - 1),
        }
    return {"action": "replaced", "name": name, "old_var_type_int": existing_vt, "var_type_int": desired_vt}


def fix_custom_variables_in_gil_from_html_defaults(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    html_file_paths: List[Path],
    overwrite_dict_when_exists: bool = False,
    verify: bool = True,
) -> Dict[str, Any]:
    input_path = Path(input_gil_file_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    specs = _iter_specs_from_html_defaults([Path(p) for p in list(html_file_paths or [])])
    if not specs:
        raise ValueError("未从 HTML 提取到任何 data-ui-variable-defaults，无法修复。")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)

    root4 = raw_dump_object.get("4")
    if not isinstance(root4, dict):
        raise ValueError("dump-json 缺少根字段 '4'（期望为 dict）。")
    section5 = root4.get("5")
    if not isinstance(section5, dict):
        raise ValueError("dump-json 缺少字段 '4/5'（期望为 dict）。")
    entry_list = section5.get("1")
    if not isinstance(entry_list, list):
        raise ValueError("dump-json 缺少字段 '4/5/1'（期望为 list）。")

    level_entry = find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        raise RuntimeError("未在 root4/5/1 中找到 name=关卡实体 的条目，无法写入关卡变量。")

    player_entry = find_root4_5_1_entry_by_name(entry_list, "玩家实体")
    player_entry_name = "玩家实体"
    if player_entry is None:
        player_entry = find_root4_5_1_entry_by_name(entry_list, "默认模版(角色编辑)")
        player_entry_name = "默认模版(角色编辑)"

    def _pick_entry(group_name: str) -> Tuple[Dict[str, Any], str]:
        g = str(group_name or "").strip()
        if g == "关卡":
            return level_entry, "关卡实体"
        if g == "玩家自身":
            if player_entry is None:
                raise RuntimeError("HTML defaults 引用了 玩家自身.<变量>，但存档中未找到 玩家实体 或 默认模版(角色编辑) 条目。")
            return player_entry, str(player_entry_name)
        raise ValueError(f"未知变量组名：{g!r}（仅支持：关卡 / 玩家自身）")

    changed: Dict[str, Any] = {"关卡实体": [], str(player_entry_name): []}

    for spec in specs:
        target_entry, target_name = _pick_entry(spec.group_name)
        action = _patch_one_entry(
            target_entry,
            spec=spec,
            overwrite_dict_when_exists=bool(overwrite_dict_when_exists),
        )
        if action.get("action") != "kept":
            changed.setdefault(target_name, []).append(action)

    output_path = Path(output_gil_file_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "html_files": [str(Path(p).resolve()) for p in list(html_file_paths or [])],
        "specs_total": int(len(specs)),
        "overwrite_dict_when_exists": bool(overwrite_dict_when_exists),
        "changed": changed,
    }

    if verify:
        _verify_custom_variables_in_output_gil(output_path, specs, overwrite_dict_when_exists=bool(overwrite_dict_when_exists))
        report["verified"] = True
    else:
        report["verified"] = False
    return report


def _verify_custom_variables_in_output_gil(
    output_gil_path: Path,
    specs: List[CustomVariableSpec],
    *,
    overwrite_dict_when_exists: bool,
) -> None:
    raw = _dump_gil_to_raw_json_object(Path(output_gil_path).resolve())
    root4 = raw.get("4")
    if not isinstance(root4, dict):
        raise ValueError("dump-json 缺少根字段 '4'（期望为 dict）。")
    section5 = root4.get("5")
    if not isinstance(section5, dict):
        raise ValueError("dump-json 缺少字段 '4/5'（期望为 dict）。")
    entry_list = section5.get("1")
    if not isinstance(entry_list, list):
        raise ValueError("dump-json 缺少字段 '4/5/1'（期望为 list）。")

    level_entry = find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        raise RuntimeError("verify: 未找到 关卡实体")

    player_entry = find_root4_5_1_entry_by_name(entry_list, "玩家实体")
    if player_entry is None:
        player_entry = find_root4_5_1_entry_by_name(entry_list, "默认模版(角色编辑)")

    def _pick_entry(group_name: str) -> Dict[str, Any]:
        g = str(group_name or "").strip()
        if g == "关卡":
            return level_entry
        if g == "玩家自身":
            if player_entry is None:
                raise RuntimeError("verify: 需要玩家实体，但未找到 玩家实体/默认模版(角色编辑)")
            return player_entry
        raise ValueError(f"verify: unknown group_name: {g!r}")

    errors: List[str] = []
    for spec in specs:
        entry = _pick_entry(spec.group_name)
        group_item = ensure_override_variables_group1_container(entry)
        container = group_item.get("11")
        if not isinstance(container, dict):
            raise RuntimeError("verify: group_item['11'] is not dict")
        variable_items = container.get("1")
        if not isinstance(variable_items, list):
            raise RuntimeError("verify: group_item['11']['1'] is not list")

        name = str(spec.variable_name or "").strip()
        found: Dict[str, Any] | None = None
        for item in variable_items:
            if not isinstance(item, dict):
                continue
            if normalize_custom_variable_name_field2(item.get("2")) == name:
                found = item
                break
        if found is None:
            errors.append(f"缺失变量：{spec.group_name}.{name}")
            continue

        desired_item = build_custom_variable_item_from_spec(spec)
        desired_vt = int(desired_item.get("3") or 0)
        actual_vt = int(found.get("3") or 0)
        if actual_vt != desired_vt:
            errors.append(f"类型不一致：{spec.group_name}.{name} actual={actual_vt} expected={desired_vt}")
            continue

        if desired_vt == 27 and (not bool(overwrite_dict_when_exists)):
            # 默认策略：不覆盖已有 dict 的 value；仅验证“存在且类型正确”
            continue

        actual_value = found.get("4")
        desired_value = desired_item.get("4")
        if not isinstance(actual_value, dict) or not isinstance(desired_value, dict):
            errors.append(f"value 节点结构异常：{spec.group_name}.{name}")
            continue

        # 用“编码后 bytes”做对照，避免 dump-json 的空 message 展示差异（{} vs "<binary_data> "）
        actual_bytes = encode_message(dict(actual_value))
        desired_bytes = encode_message(dict(desired_value))
        if actual_bytes != desired_bytes:
            errors.append(f"默认值不一致：{spec.group_name}.{name}")

    if errors:
        raise ValueError("自定义变量修复后校验失败：\n- " + "\n- ".join(errors))

