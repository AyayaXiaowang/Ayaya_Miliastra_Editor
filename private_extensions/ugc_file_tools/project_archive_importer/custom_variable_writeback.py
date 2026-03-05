from __future__ import annotations

from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from engine.graph.models.package_model import LevelVariableDefinition
from ugc_file_tools.custom_variables.value_message import (
    build_custom_variable_type_descriptor,
    build_custom_variable_value_message,
    build_dict_custom_variable_item,
    infer_dict_value_type_int,
)
from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import binary_data_text_to_numeric_message
from ugc_file_tools.integrations.graph_generater.type_registry_bridge import parse_typed_dict_alias
from ugc_file_tools.repo_paths import repo_root
from ugc_file_tools.var_type_map import map_server_port_type_text_to_var_type_id_or_raise


def _coerce_section_message(value: Any, *, max_depth: int) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.startswith("<binary_data>"):
        msg = binary_data_text_to_numeric_message(value, max_depth=int(max_depth))
        if not isinstance(msg, dict):
            raise TypeError(f"binary_data_text_to_numeric_message returned {type(msg).__name__}")
        return dict(msg)
    if value is None:
        return None
    return None


def load_level_variable_payloads_by_file_id(*, project_root: Path) -> Dict[str, List[Dict[str, Any]]]:
    """
    扫描项目存档 + 共享根 的“关卡变量/自定义变量”变量文件（Python），构建：
      VARIABLE_FILE_ID -> [LevelVariableDefinition.serialize(), ...]

    说明：
    - 变量文件必须导出：VARIABLE_FILE_ID / LEVEL_VARIABLES（见 assets/资源库/项目存档/*/管理配置/关卡变量/claude.md）。
    - 仅加载“普通自定义变量”（自定义变量/）；不加载“局内存档变量”（自定义变量-局内存档变量/）。
    """
    project_root = Path(project_root).resolve()
    project_dir = (project_root / "管理配置" / "关卡变量" / "自定义变量").resolve()
    shared_dir = (repo_root() / "assets" / "资源库" / "共享" / "管理配置" / "关卡变量" / "自定义变量").resolve()

    out: Dict[str, List[Dict[str, Any]]] = {}

    def _scan_dir(d: Path) -> None:
        if not d.is_dir():
            return
        py_paths = sorted((p for p in d.rglob("*.py") if p.is_file()), key=lambda p: p.as_posix())
        for py_path in py_paths:
            if "校验" in py_path.stem:
                continue
            module_name = f"code_level_variable_file_{abs(hash(py_path.as_posix()))}"
            module = SourceFileLoader(module_name, str(py_path)).load_module()

            vars_list = getattr(module, "LEVEL_VARIABLES", None)
            if vars_list is None:
                continue
            if not isinstance(vars_list, list):
                raise ValueError(f"LEVEL_VARIABLES 未定义为列表（{py_path}）")

            file_id = getattr(module, "VARIABLE_FILE_ID", None)
            if not isinstance(file_id, str) or str(file_id).strip() == "":
                raise ValueError(f"变量文件缺少 VARIABLE_FILE_ID（{py_path}）")
            file_id_text = str(file_id).strip()
            if file_id_text in out:
                raise ValueError(f"重复的 VARIABLE_FILE_ID：{file_id_text!r}（file={str(py_path)}）")

            payloads: list[dict[str, Any]] = []
            for entry in vars_list:
                if isinstance(entry, LevelVariableDefinition):
                    payload = entry.serialize()
                elif isinstance(entry, dict):
                    payload = dict(entry)
                else:
                    raise ValueError(f"无效的关卡变量条目类型（{py_path}）：{type(entry)!r}")
                if not isinstance(payload, dict):
                    raise TypeError(f"LevelVariableDefinition.serialize() must return dict (file={str(py_path)})")
                payloads.append(payload)

            out[file_id_text] = payloads

    # shared + project（VARIABLE_FILE_ID 约定全局唯一；重复直接 fail-fast）
    _scan_dir(shared_dir)
    _scan_dir(project_dir)

    return dict(out)


def build_custom_variable_item_from_level_variable_payload(payload: Mapping[str, Any]) -> Tuple[dict[str, Any], dict[str, Any]]:
    """
    将 LevelVariableDefinition.serialize() 结果转为 `.gil` 元件/实体自定义变量 group1 的 variable_item。

    返回：(variable_item, report_item)
    """
    variable_id = str(payload.get("variable_id") or "").strip()
    if variable_id == "":
        raise ValueError("level variable missing variable_id")

    name = str(payload.get("variable_name") or "").strip()
    if name == "":
        raise ValueError(f"level variable missing variable_name: {variable_id}")

    type_text = str(payload.get("variable_type") or "").strip()
    if type_text == "":
        raise ValueError(f"level variable missing variable_type: {variable_id}")

    default_value = payload.get("default_value")

    vt = map_server_port_type_text_to_var_type_id_or_raise(type_text)
    if int(vt) == 27:
        is_typed_dict, key_type_text, value_type_text = parse_typed_dict_alias(type_text)
        if is_typed_dict:
            key_vt = map_server_port_type_text_to_var_type_id_or_raise(key_type_text)
            val_vt = map_server_port_type_text_to_var_type_id_or_raise(value_type_text)
        else:
            key_vt = 6
            if isinstance(default_value, dict):
                val_vt = int(infer_dict_value_type_int(default_value))
            else:
                val_vt = 6
        default_map = default_value if isinstance(default_value, dict) else {}
        item = build_dict_custom_variable_item(
            variable_name=name,
            dict_key_type_int=int(key_vt),
            dict_value_type_int=int(val_vt),
            default_value_by_key=default_map,
        )
        return (
            item,
            {
                "variable_id": variable_id,
                "variable_name": name,
                "var_type_int": 27,
                "dict_key_type_int": int(key_vt),
                "dict_value_type_int": int(val_vt),
            },
        )

    value_message = build_custom_variable_value_message(var_type_int=int(vt), default_value=default_value)
    item2: dict[str, Any] = {
        "2": name,
        "3": int(vt),
        "4": value_message,
        "5": 1,
        "6": build_custom_variable_type_descriptor(var_type_int=int(vt)),
    }
    return (item2, {"variable_id": variable_id, "variable_name": name, "var_type_int": int(vt)})


def _normalize_custom_variable_name_field2(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        v1 = raw.get("1")
        if isinstance(v1, str):
            return str(v1).strip()
        v2 = raw.get("2")
        if isinstance(v2, str):
            return str(v2).strip()
    return str(raw if raw is not None else "").strip()


def ensure_override_variables_group1_variable_items_container(
    asset_entry: Dict[str, Any],
    *,
    group_list_key: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    确保 asset_entry[group_list_key] 中存在 group_id=1 的 group_item，且其 group_item['11']['1'] 为 list[variable_item]。

    经验结构（对齐真源 dump-json）：
      - group_list = asset_entry[group_list_key]  (list)
      - group_item = {'1': 1, '2': 1, '11': <message>}
      - group_item['11']['1'] = repeated variable_item（只有 1 个元素时 dump-json 可能折叠为 dict）
    """
    group_list = asset_entry.get(group_list_key)
    if isinstance(group_list, dict):
        group_list = [group_list]
        asset_entry[group_list_key] = group_list
    if not isinstance(group_list, list):
        group_list = []
        asset_entry[group_list_key] = group_list

    target_group: Optional[Dict[str, Any]] = None
    for it in group_list:
        if not isinstance(it, dict):
            continue
        if it.get("1") != 1 or it.get("2") != 1:
            continue
        target_group = it
        break
    if target_group is None:
        target_group = {"1": 1, "2": 1, "11": {}}
        group_list.append(target_group)

    container0 = target_group.get("11")
    container = _coerce_section_message(container0, max_depth=32)
    if container is None:
        container = {}
    target_group["11"] = container

    items0 = container.get("1")
    if isinstance(items0, dict):
        container["1"] = [items0]
    elif items0 is None:
        container["1"] = []
    elif isinstance(items0, list):
        pass
    else:
        container["1"] = [items0]

    variable_items = container.get("1")
    if not isinstance(variable_items, list):
        raise RuntimeError("internal error: container['1'] is not list")
    variable_items2: List[Dict[str, Any]] = [x for x in variable_items if isinstance(x, dict)]
    # keep original list object; filter is for returning view
    return (target_group, variable_items2)


def upsert_custom_variables_from_level_variable_payloads(
    asset_entry: Dict[str, Any],
    *,
    group_list_key: str,
    variable_payloads: List[Dict[str, Any]],
    overwrite_when_type_mismatched: bool = True,
) -> Dict[str, Any]:
    """
    将变量 payloads 写入到 asset_entry 的 group1。
    - 去重键：variable_name（忽略大小写）
    - 同名 type 相同：跳过
    - 同名 type 不同：默认覆盖（删除旧条目再追加新条目）
    """
    payloads = [p for p in list(variable_payloads or []) if isinstance(p, dict)]
    if not payloads:
        return {"applied": False, "reason": "no_payloads", "created": 0, "skipped_existing": 0, "overwritten": 0}

    _group_item, existing_items_view = ensure_override_variables_group1_variable_items_container(
        asset_entry,
        group_list_key=str(group_list_key),
    )

    # 取“真实 list”（允许包含非 dict 的噪音项，但写回我们只处理 dict）
    container = _coerce_section_message(_group_item.get("11"), max_depth=32)
    if not isinstance(container, dict):
        raise RuntimeError("internal error: group_item['11'] is not dict after ensure")
    variable_items_any = container.get("1")
    if not isinstance(variable_items_any, list):
        raise RuntimeError("internal error: group_item['11']['1'] is not list after ensure")

    existing_by_name_cf: Dict[str, Dict[str, Any]] = {}
    for it in list(existing_items_view):
        name0 = _normalize_custom_variable_name_field2(it.get("2"))
        if name0 == "":
            continue
        if name0.casefold() in existing_by_name_cf:
            continue
        existing_by_name_cf[name0.casefold()] = it

    created = 0
    skipped_existing = 0
    overwritten = 0

    for payload in payloads:
        new_item, report_item = build_custom_variable_item_from_level_variable_payload(payload)
        name = str(report_item.get("variable_name") or "").strip()
        if name == "":
            raise RuntimeError("internal error: report_item missing variable_name")

        existed = existing_by_name_cf.get(name.casefold())
        if existed is None:
            variable_items_any.append(dict(new_item))
            existing_by_name_cf[name.casefold()] = dict(new_item)
            created += 1
            continue

        existed_type = existed.get("3")
        want_type = int(report_item.get("var_type_int") or 0)
        if isinstance(existed_type, int) and int(existed_type) == int(want_type):
            skipped_existing += 1
            continue

        if not bool(overwrite_when_type_mismatched):
            raise ValueError(
                "自定义变量同名但类型不一致（不允许静默跳过）："
                f"name={name!r} existing_type={existed_type!r} want_type={want_type!r}"
            )

        # 删除第一个同名项（保持其它变量顺序）
        removed = False
        for idx, it in enumerate(list(variable_items_any)):
            if not isinstance(it, dict):
                continue
            if _normalize_custom_variable_name_field2(it.get("2")).casefold() != name.casefold():
                continue
            variable_items_any.pop(idx)
            removed = True
            break
        if not removed:
            raise RuntimeError("internal error: failed to remove existing mismatched variable item")
        variable_items_any.append(dict(new_item))
        existing_by_name_cf[name.casefold()] = dict(new_item)
        overwritten += 1

    return {
        "applied": True,
        "group_list_key": str(group_list_key),
        "payloads_total": len(payloads),
        "created": int(created),
        "skipped_existing": int(skipped_existing),
        "overwritten": int(overwritten),
    }


__all__ = [
    "load_level_variable_payloads_by_file_id",
    "build_custom_variable_item_from_level_variable_payload",
    "ensure_override_variables_group1_variable_items_container",
    "upsert_custom_variables_from_level_variable_payloads",
]

