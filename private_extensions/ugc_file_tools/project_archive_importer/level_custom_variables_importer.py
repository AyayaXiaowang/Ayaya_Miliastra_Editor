from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text
from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object, get_payload_root
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.var_type_map import map_server_port_type_text_to_var_type_id_or_raise
from ugc_file_tools.custom_variables.value_message import (
    build_custom_variable_type_descriptor as _cv_build_custom_variable_type_descriptor,
    build_custom_variable_value_message as _cv_build_custom_variable_value_message,
    build_dict_custom_variable_item as _cv_build_dict_custom_variable_item,
    infer_dict_value_type_int as _cv_infer_dict_value_type_int,
)


@dataclass(frozen=True, slots=True)
class LevelCustomVariablesImportOptions:
    selected_level_custom_variable_ids: list[str]
    overwrite_when_type_mismatched: bool = False


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


def _ensure_path_dict(root: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = root.get(key)
    if isinstance(value, dict):
        return value
    if value is None:
        new_value: Dict[str, Any] = {}
        root[key] = new_value
        return new_value
    raise ValueError(f"expected dict at key={key!r}, got {type(value).__name__}")


def _ensure_path_list_allow_scalar(root: Dict[str, Any], key: str) -> List[Any]:
    """
    dump-json 中 repeated 字段在“只有 1 个元素”时可能被输出为标量（int/dict/str）。
    这里将其统一为 list 视图，便于追加/遍历。
    """
    value = root.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        new_value: List[Any] = []
        root[key] = new_value
        return new_value
    new_value = [value]
    root[key] = new_value
    return new_value


def _normalize_custom_variable_name_field2(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        # prefer utf8
        v1 = raw.get("1")
        if isinstance(v1, str):
            return str(v1).strip()
        v2 = raw.get("2")
        if isinstance(v2, str):
            return str(v2).strip()
    return str(raw if raw is not None else "").strip()


def _extract_instance_entry_name_from_root4_5_1_entry(entry: Mapping[str, Any]) -> str:
    meta_list = entry.get("5")
    for item in _as_list(meta_list):
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        container = item.get("11")
        if isinstance(container, dict):
            name = container.get("1")
            if isinstance(name, str):
                return name.strip()
    return ""


def _extract_instance_id_int_from_root4_5_1_entry(entry: Mapping[str, Any]) -> int | None:
    raw = entry.get("1")
    if isinstance(raw, int):
        return int(raw)
    if isinstance(raw, list) and raw and isinstance(raw[0], int):
        return int(raw[0])
    return None


def _find_root4_5_1_entry_by_name(entry_list: list[Any], target_name: str) -> dict[str, Any] | None:
    target = str(target_name or "").strip()
    if target == "":
        return None
    for entry in list(entry_list or []):
        if not isinstance(entry, dict):
            continue
        if _extract_instance_entry_name_from_root4_5_1_entry(entry) == target:
            return entry
    return None


_SEED_LEVEL_ENTITY_ENTRY_CACHE: dict[str, Any] | None = None


def _load_seed_level_entity_entry() -> dict[str, Any]:
    """
    极空 base `.gil` 常见缺失 root4/5/1 的核心条目（关卡实体/默认模版等）。
    本工具在“写回关卡实体自定义变量”时需要定位 name=关卡实体 的 entry，
    若目标缺失则从 seed `.gil` 引入该条目作为最小基底（不覆盖目标已存在条目）。
    """
    global _SEED_LEVEL_ENTITY_ENTRY_CACHE
    if _SEED_LEVEL_ENTITY_ENTRY_CACHE is not None:
        return _SEED_LEVEL_ENTITY_ENTRY_CACHE

    from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root

    ugc_root = ugc_file_tools_builtin_resources_root()
    seed_gil_path = (ugc_root / "空的界面控件组" / "进度条样式.gil").resolve()
    if not seed_gil_path.is_file():
        raise FileNotFoundError(str(seed_gil_path))

    seed_dump = dump_gil_to_raw_json_object(seed_gil_path)
    seed_root = get_payload_root(seed_dump)
    seed_instance_section = seed_root.get("5")
    if not isinstance(seed_instance_section, dict):
        raise ValueError("seed gil 缺少实体摆放段 root4/5（期望为 dict）。")

    seed_entries = seed_instance_section.get("1")
    if isinstance(seed_entries, dict):
        seed_entries = [seed_entries]
    if seed_entries is None:
        seed_entries = []
    if not isinstance(seed_entries, list):
        raise ValueError("seed gil 字段 root4/5/1 结构异常（期望为 list/dict/None）。")

    for entry in seed_entries:
        if not isinstance(entry, dict):
            continue
        if _extract_instance_entry_name_from_root4_5_1_entry(entry) == "关卡实体":
            _SEED_LEVEL_ENTITY_ENTRY_CACHE = entry
            return entry

    raise RuntimeError("seed gil 的 root4/5/1 未找到 name=关卡实体 的条目（内部错误）。")


def _ensure_override_variables_group1_container(asset_entry: Dict[str, Any]) -> Dict[str, Any]:
    """
    确保 asset_entry['7'] 内存在 group_id=1 的变量容器，并返回该 group_item：
      group_item = {'1': 1, '2': 1, '11': {'1': [variable_item, ...]}}
    """
    group_list = asset_entry.get("7")
    if not isinstance(group_list, list):
        group_list = []
        asset_entry["7"] = group_list

    target_group: Optional[Dict[str, Any]] = None
    for item in group_list:
        if not isinstance(item, dict):
            continue
        if item.get("1") != 1:
            continue
        if item.get("2") != 1:
            continue
        if "11" in item and isinstance(item.get("11"), dict):
            target_group = item
            break

    if target_group is None:
        target_group = {"1": 1, "2": 1, "11": {}}
        group_list.append(target_group)

    container = target_group.get("11")
    if not isinstance(container, dict):
        container = {}
        target_group["11"] = container

    variable_items = container.get("1")
    # 兼容 DLL dump-json：repeated message 在“只有 1 个元素”时可能被折叠为 dict 而非 list。
    if isinstance(variable_items, dict):
        container["1"] = [variable_items]
    elif not isinstance(variable_items, list):
        container["1"] = []

    return target_group


def _pack_vector3_to_bytes(value: Any) -> bytes:
    if value is None:
        return b""
    if isinstance(value, dict):
        # 兼容：{x:...,y:...,z:...} 或 {1:x,2:y,3:z}
        x = value.get("x", value.get("1", 0.0))
        y = value.get("y", value.get("2", 0.0))
        z = value.get("z", value.get("3", 0.0))
        xf, yf, zf = float(x or 0.0), float(y or 0.0), float(z or 0.0)
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        xf, yf, zf = float(value[0]), float(value[1]), float(value[2])
    elif isinstance(value, str):
        # 兼容："(1,2,3)" / "1,2,3"
        text = value.strip().strip("()")
        parts = [p.strip() for p in text.split(",") if p.strip() != ""]
        if len(parts) != 3:
            raise ValueError(f"无法解析三维向量默认值：{value!r}")
        xf, yf, zf = float(parts[0]), float(parts[1]), float(parts[2])
    else:
        raise TypeError(f"无法将默认值转为三维向量：{value!r}")

    if xf == 0.0 and yf == 0.0 and zf == 0.0:
        # 与真源样本对齐：零向量常用 empty bytes 表达（减少写回差异）
        return b""
    # 经验：向量常以 3x float32 little-endian 表达
    return struct.pack("<fff", float(xf), float(yf), float(zf))


def _value_field_key_for_custom_variable(*, var_type_int: int) -> str:
    return str(int(var_type_int) + 10)


def _build_custom_variable_type_descriptor(
    *,
    var_type_int: int,
    dict_value_type_int: int | None = None,
    dict_key_type_int: int | None = None,
) -> dict[str, Any]:
    return _cv_build_custom_variable_type_descriptor(
        var_type_int=int(var_type_int),
        dict_value_type_int=(int(dict_value_type_int) if isinstance(dict_value_type_int, int) else None),
        dict_key_type_int=(int(dict_key_type_int) if isinstance(dict_key_type_int, int) else None),
    )


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"列表默认值必须为 list/tuple 或 None，实际：{value!r}")


def _coerce_int_list(value: Any) -> list[int]:
    raw_list = _coerce_list(value)
    out: list[int] = []
    for x in raw_list:
        if x is None:
            out.append(0)
            continue
        if isinstance(x, bool):
            out.append(int(1 if x else 0))
            continue
        if isinstance(x, int):
            out.append(int(x))
            continue
        if isinstance(x, float):
            if not (x == x):
                raise ValueError("整数列表默认值包含 NaN（不支持）")
            out.append(int(x))
            continue
        text = str(x).strip()
        out.append(int(float(text))) if text else out.append(0)
    return out


def _coerce_float_list(value: Any) -> list[float]:
    raw_list = _coerce_list(value)
    out: list[float] = []
    for x in raw_list:
        if x is None:
            out.append(0.0)
            continue
        if isinstance(x, bool):
            out.append(1.0 if x else 0.0)
            continue
        if isinstance(x, (int, float)):
            fv = float(x)
            if not (fv == fv):
                raise ValueError("浮点列表默认值包含 NaN（不支持）")
            out.append(float(fv))
            continue
        text = str(x).strip()
        fv2 = float(text) if text else 0.0
        if not (fv2 == fv2):
            raise ValueError("浮点列表默认值包含 NaN（不支持）")
        out.append(float(fv2))
    return out


def _coerce_bool_list_as_ints(value: Any) -> list[int]:
    raw_list = _coerce_list(value)
    out: list[int] = []
    for x in raw_list:
        if isinstance(x, bool):
            out.append(int(1 if x else 0))
            continue
        if isinstance(x, int):
            out.append(int(1 if int(x) != 0 else 0))
            continue
        if isinstance(x, str):
            s = x.strip().lower()
            if s in ("true", "1", "yes", "y", "是"):
                out.append(1)
                continue
            if s in ("false", "0", "no", "n", "否", ""):
                out.append(0)
                continue
        if x is None:
            out.append(0)
            continue
        raise TypeError(f"布尔值列表元素不支持：{x!r}")
    return out


def _coerce_string_list(value: Any) -> list[str]:
    raw_list = _coerce_list(value)
    return [str(x if x is not None else "") for x in raw_list]


def _infer_dict_value_type_int(default_value_by_key: Mapping[Any, Any]) -> int:
    return _cv_infer_dict_value_type_int(default_value_by_key)


def _build_custom_variable_value_message(*, var_type_int: int, default_value: Any) -> dict[str, Any]:
    return _cv_build_custom_variable_value_message(var_type_int=int(var_type_int), default_value=default_value)


def _build_dict_custom_variable_item(
    *,
    variable_name: str,
    dict_key_type_int: int,
    dict_value_type_int: int,
    default_value_by_key: Mapping[Any, Any],
) -> dict[str, Any]:
    return _cv_build_dict_custom_variable_item(
        variable_name=str(variable_name),
        default_value_by_key=default_value_by_key,
        dict_key_type_int=int(dict_key_type_int),
        dict_value_type_int=int(dict_value_type_int),
    )


def _build_custom_variable_item_from_level_variable_payload(payload: Mapping[str, Any]) -> Tuple[dict[str, Any], dict[str, Any]]:
    """
    将 LevelVariableDefinition.serialize() 结果转为 `.gil` 实体 override_variables(group1) 的 variable_item。

    返回：(variable_item, report_item)
    """
    from ugc_file_tools.integrations.graph_generater.type_registry_bridge import parse_typed_dict_alias

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
                val_vt = int(_infer_dict_value_type_int(default_value))
            else:
                val_vt = 6

        default_map = default_value if isinstance(default_value, dict) else {}
        item = _build_dict_custom_variable_item(
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

    value_message = _build_custom_variable_value_message(var_type_int=int(vt), default_value=default_value)
    item2: dict[str, Any] = {
        "2": name,
        "3": int(vt),
        "4": value_message,
        "5": 1,
        "6": _build_custom_variable_type_descriptor(var_type_int=int(vt)),
    }
    return (item2, {"variable_id": variable_id, "variable_name": name, "var_type_int": int(vt)})


def _load_level_variable_payloads_by_id_from_custom_variables_dir(custom_variables_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    加载 `管理配置/关卡变量/自定义变量/**/*.py`，返回 {variable_id: LevelVariableDefinition.serialize()}。
    """
    base_dir = Path(custom_variables_dir).resolve()
    if not base_dir.is_dir():
        return {}

    from engine.graph.models.package_model import LevelVariableDefinition
    from engine.resources.level_variable_owner_contract import validate_and_fill_level_variable_payload_owner

    out: Dict[str, Dict[str, Any]] = {}
    py_paths = sorted((p for p in base_dir.rglob("*.py") if p.is_file()), key=lambda p: p.as_posix())
    for py_path in py_paths:
        if "校验" in py_path.stem:
            continue
        module_name = f"code_level_variable_{abs(hash(py_path.as_posix()))}"
        module = SourceFileLoader(module_name, str(py_path)).load_module()
        vars_list = getattr(module, "LEVEL_VARIABLES", None)
        if not isinstance(vars_list, list):
            raise ValueError(f"LEVEL_VARIABLES 未定义为列表（{py_path}）")

        for entry in vars_list:
            if isinstance(entry, LevelVariableDefinition):
                payload = entry.serialize()
            elif isinstance(entry, dict):
                payload = dict(entry)
            else:
                raise ValueError(f"无效的关卡变量条目类型（{py_path}）：{type(entry)!r}")

            variable_id = str(payload.get("variable_id") or "").strip()
            if variable_id == "":
                raise ValueError(f"无效的 variable_id（{py_path}）")
            if variable_id in out:
                raise ValueError(f"重复的关卡变量 ID：{variable_id!r}（file={str(py_path)}）")

            validate_and_fill_level_variable_payload_owner(payload, py_path=py_path)
            out[variable_id] = payload
    return out


def import_selected_level_custom_variables_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    options: LevelCustomVariablesImportOptions,
) -> Dict[str, Any]:
    """
    将 selection-json 指定的关卡自定义变量（LevelVariableDefinition.variable_id）补齐到 `.gil` 的关卡实体 override_variables(group1)。
    """
    project_root = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    selected_ids = [str(x).strip() for x in list(options.selected_level_custom_variable_ids or []) if str(x).strip() != ""]
    # 去重（保持顺序）
    seen: set[str] = set()
    selected_ids_deduped: list[str] = []
    for vid in selected_ids:
        k = vid.casefold()
        if k in seen:
            continue
        seen.add(k)
        selected_ids_deduped.append(vid)

    if not selected_ids_deduped:
        return {
            "project_archive": str(project_root),
            "input_gil": str(input_path),
            "output_gil": str(output_path),
            "selected_variable_ids": [],
            "created": [],
            "skipped_existing": [],
            "type_mismatched": [],
        }

    # 1) 加载变量定义（project scope + shared scope）
    project_custom_dir = (project_root / "管理配置" / "关卡变量" / "自定义变量").resolve()
    project_vars = _load_level_variable_payloads_by_id_from_custom_variables_dir(project_custom_dir)

    # shared scope（可选）
    shared_vars: Dict[str, Dict[str, Any]] = {}
    try:
        from ugc_file_tools.repo_paths import repo_root

        shared_custom_dir = (repo_root() / "assets" / "资源库" / "共享" / "管理配置" / "关卡变量" / "自定义变量").resolve()
        shared_vars = _load_level_variable_payloads_by_id_from_custom_variables_dir(shared_custom_dir)
    except FileNotFoundError:
        shared_vars = {}

    # 合并（严格：重复 variable_id 直接抛错，避免“引用同名但内容不同”悄悄混用）
    variable_payloads_by_id: Dict[str, Dict[str, Any]] = {}
    for vid, payload in shared_vars.items():
        variable_payloads_by_id[str(vid)] = dict(payload)
    for vid, payload in project_vars.items():
        if str(vid) in variable_payloads_by_id:
            raise ValueError(f"关卡变量 ID 在 shared 与 project 中重复：{vid!r}")
        variable_payloads_by_id[str(vid)] = dict(payload)

    # 2) dump + 定位关卡实体 entry
    raw_dump_object = dump_gil_to_raw_json_object(input_path)
    payload_root = get_payload_root(raw_dump_object)
    instance_section = _ensure_path_dict(payload_root, "5")
    entry_list = _ensure_path_list_allow_scalar(instance_section, "1")
    level_entry = _find_root4_5_1_entry_by_name(entry_list, "关卡实体")
    if level_entry is None:
        # 极空 base：尝试从 seed `.gil` 引入关卡实体条目作为最小基底
        seed_level_entry = _load_seed_level_entity_entry()
        seed_instance_id = _extract_instance_id_int_from_root4_5_1_entry(seed_level_entry)
        if not isinstance(seed_instance_id, int):
            raise RuntimeError("seed 关卡实体条目缺少 instance_id(field_1)，无法 bootstrap（内部错误）。")

        # 若目标已存在同 instance_id 的条目，则优先复用（避免 duplicate instance_id）
        existing_by_id: dict[int, dict[str, Any]] = {}
        for e in list(entry_list or []):
            if not isinstance(e, dict):
                continue
            iid = _extract_instance_id_int_from_root4_5_1_entry(e)
            if isinstance(iid, int) and iid not in existing_by_id:
                existing_by_id[int(iid)] = e

        matched = existing_by_id.get(int(seed_instance_id))
        if matched is not None:
            level_entry = matched
        else:
            cloned = json.loads(json.dumps(seed_level_entry, ensure_ascii=False))
            entry_list.append(cloned)
            level_entry = cloned
        bootstrapped_level_entry_from_seed = True
    else:
        bootstrapped_level_entry_from_seed = False

    group_item = _ensure_override_variables_group1_container(level_entry)
    container = _require_dict(group_item.get("11"), path="level_entry['7'][group1]['11']")
    variable_items = container.get("1")
    if not isinstance(variable_items, list):
        raise RuntimeError("internal error: override_variables container['1'] is not list")

    existing_by_name: Dict[str, Dict[str, Any]] = {}
    for item in variable_items:
        if not isinstance(item, dict):
            continue
        name_norm = _normalize_custom_variable_name_field2(item.get("2"))
        if name_norm == "":
            continue
        if name_norm.casefold() in existing_by_name:
            continue
        existing_by_name[name_norm.casefold()] = item

    created: list[dict[str, Any]] = []
    skipped_existing: list[dict[str, Any]] = []
    type_mismatched: list[dict[str, Any]] = []

    for variable_id in selected_ids_deduped:
        payload = variable_payloads_by_id.get(str(variable_id))
        if not isinstance(payload, dict):
            raise ValueError(f"所选关卡变量不存在（variable_id 未找到）：{variable_id!r}")

        # 安全护栏：导出中心的“关卡实体自定义变量”只允许写入归属为 level 的变量。
        owner = str(payload.get("owner") or "").strip().lower()
        if owner != "level":
            vname = str(payload.get("variable_name") or "").strip()
            raise ValueError(
                "所选『关卡实体自定义变量』必须归属关卡实体（owner='level'）。"
                f"实际 variable_id={variable_id!r}, variable_name={vname!r}, owner={owner!r}"
            )

        new_item, report_item = _build_custom_variable_item_from_level_variable_payload(payload)
        name = str(report_item.get("variable_name") or "").strip()
        if name == "":
            raise RuntimeError("internal error: report_item missing variable_name")

        existed = existing_by_name.get(name.casefold())
        if existed is None:
            variable_items.append(dict(new_item))
            existing_by_name[name.casefold()] = dict(new_item)
            created.append(dict(report_item))
            continue

        # 已存在：检查 type_code 是否一致
        existed_type = existed.get("3")
        want_type = int(report_item.get("var_type_int") or 0)
        if isinstance(existed_type, int) and int(existed_type) == int(want_type):
            skipped_existing.append(dict(report_item))
            continue

        # 类型不一致：默认不覆盖，输出报告供上层提示
        if bool(options.overwrite_when_type_mismatched):
            # 删除第一个同名项（保持其它变量顺序）
            removed = False
            for idx, it in enumerate(list(variable_items)):
                if not isinstance(it, dict):
                    continue
                if _normalize_custom_variable_name_field2(it.get("2")).casefold() != name.casefold():
                    continue
                variable_items.pop(idx)
                removed = True
                break
            if not removed:
                raise RuntimeError("internal error: failed to remove existing mismatched variable item")
            variable_items.append(dict(new_item))
            existing_by_name[name.casefold()] = dict(new_item)
            created.append(dict(report_item) | {"overwritten_type_mismatch": True, "previous_type_code": existed_type})
            continue

        type_mismatched.append(dict(report_item) | {"existing_type_code": existed_type})

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "project_archive": str(project_root),
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "selected_variable_ids": list(selected_ids_deduped),
        "overwrite_when_type_mismatched": bool(options.overwrite_when_type_mismatched),
        "bootstrapped_level_entry_from_seed": bool(bootstrapped_level_entry_from_seed),
        "created": list(created),
        "skipped_existing": list(skipped_existing),
        "type_mismatched": list(type_mismatched),
    }


__all__ = [
    "LevelCustomVariablesImportOptions",
    "import_selected_level_custom_variables_from_project_archive_to_gil",
]



# -------------------- Public helpers (reusable) --------------------


def build_custom_variable_type_descriptor(
    *,
    var_type_int: int,
    dict_key_type_int: int | None = None,
    dict_value_type_int: int | None = None,
) -> dict[str, object]:
    return _build_custom_variable_type_descriptor(
        var_type_int=int(var_type_int),
        dict_key_type_int=(int(dict_key_type_int) if isinstance(dict_key_type_int, int) else None),
        dict_value_type_int=(int(dict_value_type_int) if isinstance(dict_value_type_int, int) else None),
    )


def infer_dict_value_type_int(default_value_by_key: Mapping[Any, Any]) -> int:
    return _infer_dict_value_type_int(default_value_by_key)


def build_custom_variable_value_message(*, var_type_int: int, default_value: Any) -> dict[str, Any]:
    return _build_custom_variable_value_message(var_type_int=int(var_type_int), default_value=default_value)


def build_dict_custom_variable_item(
    *,
    variable_name: str,
    default_value_by_key: Mapping[Any, Any],
    dict_key_type_int: int | None = None,
    dict_value_type_int: int | None = None,
) -> dict[str, Any]:
    key_vt = int(dict_key_type_int) if isinstance(dict_key_type_int, int) else 6
    val_vt = int(dict_value_type_int) if isinstance(dict_value_type_int, int) else _infer_dict_value_type_int(default_value_by_key)
    return _build_dict_custom_variable_item(
        variable_name=str(variable_name),
        default_value_by_key=default_value_by_key,
        dict_key_type_int=int(key_vt),
        dict_value_type_int=int(val_vt),
    )

