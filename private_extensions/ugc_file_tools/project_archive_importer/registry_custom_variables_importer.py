from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message
from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object, get_payload_root
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


@dataclass(frozen=True, slots=True)
class RegistryCustomVariablesImportOptions:
    # item schema（dict[str,str]）：
    # - owner_ref: str（"level"/"player" 或 instance_id/template_id）
    # - owner_kind: str（可选；"level"/"player"/"instance"/"template"/"ref"）
    # - owner_display: str（可选；用于 instance/template 的 name 匹配）
    # - variable_id: str
    selected_custom_variable_refs: list[dict[str, str]]
    overwrite_when_type_mismatched: bool = False


def _as_list_allow_scalar(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _normalize_owner_ref(owner_ref: str) -> str:
    return str(owner_ref or "").strip()


def _build_level_variable_payload_from_registry_decl(
    decl: Mapping[str, Any],
    *,
    owner_ref: str,
) -> dict[str, Any]:
    vid = str(decl.get("variable_id") or "").strip()
    vname = str(decl.get("variable_name") or "").strip()
    vtype = str(decl.get("variable_type") or "").strip()
    if vid == "" or vname == "" or vtype == "":
        raise ValueError("registry decl missing variable_id/variable_name/variable_type")

    owner0 = _normalize_owner_ref(owner_ref)
    owner_lower = owner0.lower()
    owner = owner_lower if owner_lower in {"player", "level"} else owner0

    return {
        "variable_id": vid,
        "variable_name": vname,
        "variable_type": vtype,
        "default_value": decl.get("default_value"),
        "description": str(decl.get("description") or ""),
        "owner": str(owner),
        "category": str(decl.get("category") or ""),
        "metadata": (dict(decl.get("metadata")) if isinstance(decl.get("metadata"), dict) else {}),
    }


def _try_extract_template_name(entry: Dict[str, Any]) -> str:
    meta_list = entry.get("6")
    if isinstance(meta_list, dict):
        meta_list = [meta_list]
    if meta_list is None:
        meta_list = []
    if not isinstance(meta_list, list):
        return ""
    for item in meta_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        v11 = item.get("11")
        if isinstance(v11, str):
            return str(v11).strip()
        if isinstance(v11, dict):
            name_val = v11.get("1")
            if isinstance(name_val, str):
                return str(name_val).strip()
    return ""


def _find_root4_4_1_template_entry_by_name(payload_root: dict[str, Any], name: str) -> dict[str, Any] | None:
    section4 = payload_root.get("4")
    if not isinstance(section4, dict):
        return None
    entry_list = section4.get("1")
    if isinstance(entry_list, dict):
        entry_list = [entry_list]
        section4["1"] = entry_list
    if not isinstance(entry_list, list):
        return None
    want = str(name or "").strip()
    if want == "":
        return None
    for e in list(entry_list):
        if not isinstance(e, dict):
            continue
        got = _try_extract_template_name(e)
        if got == want:
            return e
    return None


def import_selected_registry_custom_variables_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    options: RegistryCustomVariablesImportOptions,
) -> Dict[str, Any]:
    """
    将 selection-json 指定的“注册表自定义变量（owner_ref+variable_id）”补齐写入输出 `.gil`。

    写回目标：
    - owner_ref="level"：关卡实体（root4/5/1 name=关卡实体）override_variables(group1)（group_list_key="7"）
    - owner_ref="player"：玩家实体 / 玩家模板 / 默认模版(角色编辑)（同 `UI 占位符变量同步` 口径）
    - 第三方 owner（instance/template/ref）：优先按 owner_display 匹配实体/模板 name 写入；缺失则 fail-fast

    语义：
    - 仅补齐缺失变量；不修改已存在同名变量的当前值
    - 同名但类型不同：默认不覆盖，报告中列出（可通过 overwrite_when_type_mismatched 显式覆盖）
    """
    project_root = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    refs0 = [dict(x) for x in list(options.selected_custom_variable_refs or []) if isinstance(x, dict)]
    # normalize + dedupe
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for r in refs0:
        owner_ref = str(r.get("owner_ref") or "").strip()
        variable_id = str(r.get("variable_id") or "").strip()
        if owner_ref == "" or variable_id == "":
            continue
        key = (owner_ref.casefold(), variable_id.casefold())
        if key in seen:
            continue
        seen.add(key)
        refs.append(
            {
                "owner_ref": owner_ref,
                "owner_kind": str(r.get("owner_kind") or "").strip(),
                "owner_display": str(r.get("owner_display") or "").strip(),
                "variable_id": variable_id,
            }
        )

    if not refs:
        return {
            "project_archive": str(project_root),
            "input_gil": str(input_path),
            "output_gil": str(output_path),
            "selected_custom_variable_refs": [],
            "created": [],
            "skipped_existing": [],
            "type_mismatched": [],
        }

    # 1) load registry decls (AST, no exec)
    registry_path = (project_root / "管理配置" / "关卡变量" / "自定义变量注册表.py").resolve()
    if not registry_path.is_file():
        raise FileNotFoundError(str(registry_path))

    from engine.resources.auto_custom_variable_registry import load_auto_custom_variable_registry_from_code
    from engine.resources.auto_custom_variable_registry import normalize_owner_refs

    decls = load_auto_custom_variable_registry_from_code(registry_path)
    decl_by_id: dict[str, dict[str, Any]] = {}
    owners_by_id: dict[str, list[str]] = {}
    for d in decls:
        vid = str(d.variable_id or "").strip()
        if not vid:
            continue
        if vid in decl_by_id:
            raise ValueError(f"registry has duplicated variable_id: {vid!r}")
        decl_by_id[vid] = {
            "variable_id": str(d.variable_id or ""),
            "variable_name": str(d.variable_name or ""),
            "variable_type": str(d.variable_type or ""),
            "default_value": d.default_value,
            "description": str(d.description or ""),
            "owner": d.owner,
            "category": str(d.category or ""),
            "metadata": (dict(d.metadata) if isinstance(d.metadata, dict) else {}),
        }
        owners_by_id[vid] = [str(x) for x in normalize_owner_refs(d.owner)]

    payloads_by_owner_ref_and_name: dict[tuple[str, str], dict[str, Any]] = {}
    payloads_by_owner_ref_and_vid: dict[tuple[str, str], dict[str, Any]] = {}
    for r in refs:
        owner_ref = str(r.get("owner_ref") or "").strip()
        vid = str(r.get("variable_id") or "").strip()
        decl = decl_by_id.get(vid)
        if decl is None:
            raise ValueError(f"所选变量不存在（注册表 variable_id 未找到）：{vid!r}")
        owners = owners_by_id.get(vid, [])
        if owner_ref not in owners:
            raise ValueError(
                f"所选变量与 owner_ref 不匹配：owner_ref={owner_ref!r} variable_id={vid!r} registry_owners={owners}"
            )
        payload = _build_level_variable_payload_from_registry_decl(decl, owner_ref=owner_ref)
        key_vid = (owner_ref.casefold(), vid.casefold())
        payloads_by_owner_ref_and_vid[key_vid] = dict(payload)
        key_name = (owner_ref.casefold(), str(payload.get("variable_name") or "").casefold())
        payloads_by_owner_ref_and_name[key_name] = dict(payload)

    # 2) decode gil -> payload_root
    raw_dump_object = dump_gil_to_raw_json_object(input_path)
    payload_root = get_payload_root(raw_dump_object)

    # 3) locate root4/5/1 entries
    from ugc_file_tools.custom_variables.apply import (
        collect_player_template_custom_variable_targets_from_payload_root,
        ensure_override_variables_group1_container,
        extract_instance_entry_name_from_root4_5_1_entry,
        find_root4_5_1_entry_by_name,
    )
    from ugc_file_tools.custom_variables.coerce import normalize_custom_variable_name_field2
    from ugc_file_tools.project_archive_importer.custom_variable_writeback import (
        build_custom_variable_item_from_level_variable_payload,
        ensure_override_variables_group1_variable_items_container,
    )

    section5 = payload_root.get("5")
    if not isinstance(section5, dict):
        raise ValueError("payload_root 缺少字段 '5'（期望为 dict）。")
    entry_list_any = section5.get("1")
    if isinstance(entry_list_any, dict):
        entry_list_any = [entry_list_any]
        section5["1"] = entry_list_any
    if not isinstance(entry_list_any, list):
        raise ValueError("payload_root 缺少字段 '5/1'（期望为 list）。")
    entry_list = [x for x in _as_list_allow_scalar(entry_list_any) if isinstance(x, dict)]

    level_entry = find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        raise RuntimeError("未在 root4/5/1 中找到 name=关卡实体 的条目，无法写入关卡变量。")

    player_entity_entry = find_root4_5_1_entry_by_name(entry_list, "玩家实体")
    role_editor_entry = find_root4_5_1_entry_by_name(entry_list, "默认模版(角色编辑)")
    player_template_targets = collect_player_template_custom_variable_targets_from_payload_root(payload_root)

    def _iter_targets_for_owner_ref(owner_ref: str, *, owner_kind: str, owner_display: str) -> list[tuple[Dict[str, Any], str, str]]:
        lower = str(owner_ref or "").strip().lower()
        if lower == "level":
            return [(level_entry, "7", "关卡实体")]
        if lower == "player":
            out: list[tuple[Dict[str, Any], str, str]] = []
            if player_entity_entry is not None:
                out.append((player_entity_entry, "7", "玩家实体"))
            for t in list(player_template_targets or []):
                wrappers = t.get("root5_wrappers")
                if isinstance(wrappers, list):
                    for w in wrappers:
                        if isinstance(w, dict):
                            name = extract_instance_entry_name_from_root4_5_1_entry(w) or "<玩家模板>"
                            out.append((w, "7", f"玩家模板:{name}"))
                e4 = t.get("root4_entry")
                if isinstance(e4, dict):
                    names = t.get("template_names")
                    label_name = ""
                    if isinstance(names, list) and names:
                        label_name = str(names[0])
                    label = f"玩家模板(模板段):{label_name}" if label_name else "玩家模板(模板段)"
                    out.append((e4, "8", label))
            if out:
                return out
            if role_editor_entry is not None:
                return [(role_editor_entry, "7", "默认模版(角色编辑)")]
            raise RuntimeError(
                "所选变量归属为 player，但存档中未找到 玩家实体 / 玩家模板(wrapper) / 默认模版(角色编辑) 条目。"
            )

        kind = str(owner_kind or "").strip().lower()
        display = str(owner_display or "").strip()
        if kind == "instance" and display:
            target = find_root4_5_1_entry_by_name(entry_list, display)
            if target is None:
                raise RuntimeError(f"未在 root4/5/1 中找到 name={display!r} 的实体条目（owner_ref={owner_ref!r}）。")
            return [(target, "7", f"实体:{display}")]
        if kind == "template" and display:
            tmpl = _find_root4_4_1_template_entry_by_name(payload_root, display)
            if tmpl is None:
                raise RuntimeError(f"未在 root4/4/1 中找到 name={display!r} 的模板条目（owner_ref={owner_ref!r}）。")
            return [(tmpl, "8", f"模板:{display}")]
        raise RuntimeError(
            f"无法解析 owner_ref 的写回目标：owner_ref={owner_ref!r} owner_kind={owner_kind!r} owner_display={owner_display!r}"
        )

    created: list[dict[str, Any]] = []
    skipped_existing: list[dict[str, Any]] = []
    type_mismatched: list[dict[str, Any]] = []

    # 4) apply
    for r in refs:
        owner_ref = str(r.get("owner_ref") or "").strip()
        owner_kind = str(r.get("owner_kind") or "").strip()
        owner_display = str(r.get("owner_display") or "").strip()
        vid = str(r.get("variable_id") or "").strip()
        payload = payloads_by_owner_ref_and_vid.get((owner_ref.casefold(), vid.casefold()))
        if not isinstance(payload, dict):
            raise RuntimeError("internal error: payload missing for selected ref")

        new_item, report_item = build_custom_variable_item_from_level_variable_payload(payload)
        name = str(report_item.get("variable_name") or "").strip()
        want_type = int(report_item.get("var_type_int") or 0)
        if name == "":
            raise RuntimeError("internal error: report_item missing variable_name")

        targets = _iter_targets_for_owner_ref(owner_ref, owner_kind=owner_kind, owner_display=owner_display)
        for target_entry, group_list_key, target_label in targets:
            group_item, _view = ensure_override_variables_group1_variable_items_container(
                target_entry, group_list_key=str(group_list_key)
            )
            container = group_item.get("11")
            if not isinstance(container, dict):
                raise RuntimeError("internal error: group_item['11'] is not dict")
            items_any = container.get("1")
            if not isinstance(items_any, list):
                raise RuntimeError("internal error: group_item['11']['1'] is not list")

            existed_item: dict[str, Any] | None = None
            for it in items_any:
                if not isinstance(it, dict):
                    continue
                if normalize_custom_variable_name_field2(it.get("2")).casefold() == name.casefold():
                    existed_item = it
                    break
            if existed_item is None:
                items_any.append(dict(new_item))
                created.append(
                    {
                        "owner_ref": owner_ref,
                        "owner_kind": owner_kind,
                        "owner_display": owner_display,
                        "target": target_label,
                        "variable_id": str(payload.get("variable_id") or ""),
                        "variable_name": name,
                        "var_type_int": int(want_type),
                    }
                )
                continue

            existed_type = existed_item.get("3")
            if isinstance(existed_type, int) and int(existed_type) == int(want_type):
                skipped_existing.append(
                    {
                        "owner_ref": owner_ref,
                        "owner_kind": owner_kind,
                        "owner_display": owner_display,
                        "target": target_label,
                        "variable_id": str(payload.get("variable_id") or ""),
                        "variable_name": name,
                        "var_type_int": int(want_type),
                    }
                )
                continue

            # 类型不一致：默认不覆盖，输出报告供上层提示
            if bool(options.overwrite_when_type_mismatched):
                # 删除第一个同名项（保持其它变量顺序）
                removed = False
                for idx, it2 in enumerate(list(items_any)):
                    if not isinstance(it2, dict):
                        continue
                    if normalize_custom_variable_name_field2(it2.get("2")).casefold() != name.casefold():
                        continue
                    items_any.pop(idx)
                    removed = True
                    break
                if not removed:
                    raise RuntimeError("internal error: failed to remove existing mismatched variable item")
                items_any.append(dict(new_item))
                created.append(
                    {
                        "owner_ref": owner_ref,
                        "owner_kind": owner_kind,
                        "owner_display": owner_display,
                        "target": target_label,
                        "variable_id": str(payload.get("variable_id") or ""),
                        "variable_name": name,
                        "var_type_int": int(want_type),
                        "overwritten_type_mismatch": True,
                        "previous_type_code": existed_type,
                    }
                )
                continue

            type_mismatched.append(
                {
                    "owner_ref": owner_ref,
                    "owner_kind": owner_kind,
                    "owner_display": owner_display,
                    "target": target_label,
                    "variable_id": str(payload.get("variable_id") or ""),
                    "variable_name": name,
                    "var_type_int": int(want_type),
                    "existing_type_code": existed_type,
                }
            )

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "project_archive": str(project_root),
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "selected_custom_variable_refs": list(refs),
        "overwrite_when_type_mismatched": bool(options.overwrite_when_type_mismatched),
        "created": list(created),
        "skipped_existing": list(skipped_existing),
        "type_mismatched": list(type_mismatched),
    }


__all__ = [
    "RegistryCustomVariablesImportOptions",
    "import_selected_registry_custom_variables_from_project_archive_to_gil",
]

