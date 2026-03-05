from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.repo_paths import ugc_file_tools_root
from ugc_file_tools.ui_parsers.progress_bars import find_progressbar_binding_blob as _find_progressbar_binding_blob
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    DEFAULT_CANVAS_SIZE_BY_STATE_INDEX,
    append_children_guids_to_parent_record as _append_children_guids_to_parent_record,
    append_layout_root_guid_to_layout_registry as _append_layout_root_guid_to_layout_registry,
    allocate_next_guid as _allocate_next_guid,
    collect_all_widget_guids as _collect_all_widget_guids,
    collect_existing_meta_blob13_field501_values as _collect_existing_meta_blob13_field501_values,
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    find_record_by_guid as _find_record_by_guid,
    prepend_layout_root_guid_to_layout_registry as _prepend_layout_root_guid_to_layout_registry,
    has_meta_blob13 as _has_meta_blob13,
    set_rect_state_canvas_position_and_size as _set_rect_state_canvas_position_and_size,
    set_rect_transform_layer as _set_rect_transform_layer,
    set_meta_blob13_field501_value as _set_meta_blob13_field501_value,
    try_extract_meta_blob13_field501_value as _try_extract_meta_blob13_field501_value,
    set_widget_guid as _set_widget_guid,
    set_widget_name as _set_widget_name,
    set_widget_parent_guid_field504 as _set_widget_parent_guid_field504,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)


def _sanitize_schema_id(schema_id: str) -> str:
    text = str(schema_id or "").strip().lower()
    if text == "":
        raise ValueError("schema_id 不能为空")
    if re.fullmatch(r"[0-9a-f]{40}", text) is None:
        raise ValueError("schema_id 必须是 40 位 hex（sha1）字符串")
    return text


def _load_schema_record(schema_id: str) -> Dict[str, Any]:
    sid = _sanitize_schema_id(schema_id)
    record_path = (
        ugc_file_tools_root()
        / "ui_schema_library"
        / "data"
        / "records"
        / f"{sid}.record.json"
    )
    if not record_path.is_file():
        raise FileNotFoundError(str(record_path))
    obj = json.loads(record_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("schema record file 顶层不是 dict")
    record = obj.get("record")
    if not isinstance(record, dict):
        raise ValueError("schema record file 缺少 record(dict)")
    return record


def clone_ui_record_from_schema_library(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    schema_id: str,
    parent_guid: int,
    new_name: Optional[str] = None,
    new_guid: Optional[int] = None,
    # 可选：写回位置/大小（固定锚点语义；state0=电脑, state1=手机）
    pc_canvas_position: Optional[Tuple[float, float]] = None,
    pc_size: Optional[Tuple[float, float]] = None,
    mobile_canvas_position: Optional[Tuple[float, float]] = None,
    mobile_size: Optional[Tuple[float, float]] = None,
    # 可选：写回层级字段（RectTransform layer）
    layer: Optional[int] = None,
    # 可选：把该 GUID 注册到 4/9/501[0]（用于布局 root / 模板 root）
    register_layout_root_mode: str = "none",  # "none" | "append" | "prepend"
    # 可选：对 record 中的 template_id blob（502/*/13，field_501(varint)）做重分配
    template_id_mode: str = "keep",  # "keep" | "auto" | "set"
    template_id: Optional[int] = None,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    从 `ui_schema_library` 中读取一个“模板 record”（按 schema_id），克隆并插入到目标 `.gil`：
    - 分配/写入新 GUID
    - 设置 parent_guid（写入 record['504']）
    - 追加到 parent_record.children（record['503'][0] varint stream）
    - 可选写回 name / RectTransform 坐标尺寸 / layer
    - 可选将新 GUID 注册到 layout registry（4/9/501[0]）
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    parent_guid_int = int(parent_guid)
    template_record = _load_schema_record(schema_id)

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    parent_record = _find_record_by_guid(ui_record_list, parent_guid_int)
    if parent_record is None:
        raise RuntimeError(f"未找到 parent_guid={parent_guid_int} 对应的 UI record。")

    reserved = set(existing_guids)
    if new_guid is None:
        max_guid = max(reserved)
        allocated_guid = _allocate_next_guid(reserved, start=int(max_guid) + 1)
    else:
        allocated_guid = int(new_guid)
        if allocated_guid in reserved:
            raise ValueError(f"new_guid 已存在于目标存档：{allocated_guid}")
    reserved.add(int(allocated_guid))

    cloned_record = copy.deepcopy(template_record)
    _set_widget_guid(cloned_record, int(allocated_guid))
    _set_widget_parent_guid_field504(cloned_record, parent_guid_int)

    if new_name is not None:
        name_text = str(new_name or "").strip()
        if name_text == "":
            raise ValueError("new_name 不能为空字符串")
        _set_widget_name(cloned_record, name_text)

    if layer is not None:
        _set_rect_transform_layer(cloned_record, int(layer))

    mode_tid = str(template_id_mode or "").strip().lower()
    if mode_tid not in {"keep", "auto", "set"}:
        raise ValueError(f"template_id_mode 不支持：{mode_tid!r}")

    blob13_field501_before: Optional[int] = None
    blob13_field501_after: Optional[int] = None
    if _has_meta_blob13(cloned_record):
        blob13_field501_before = _try_extract_meta_blob13_field501_value(cloned_record)
        blob13_field501_after = blob13_field501_before

        if mode_tid == "auto":
            existing_values = _collect_existing_meta_blob13_field501_values(ui_record_list)
            reserved_values = set(existing_guids) | set(existing_values) | {int(allocated_guid)}
            # 若 record 本身已有 field501 值，则也视为“占用”（避免不必要的 self-collision）
            if blob13_field501_before is not None:
                reserved_values.add(int(blob13_field501_before))
            new_value = _allocate_next_guid(reserved_values, start=max(reserved_values) + 1)
            _set_meta_blob13_field501_value(cloned_record, int(new_value))
            blob13_field501_after = int(new_value)

        elif mode_tid == "set":
            if template_id is None:
                raise ValueError("template_id_mode=set 时必须提供 template_id")
            existing_values = _collect_existing_meta_blob13_field501_values(ui_record_list)
            reserved_values = set(existing_guids) | set(existing_values) | {int(allocated_guid)}
            if int(template_id) in reserved_values:
                raise ValueError(f"field_501 值已存在于目标存档（或与 GUID 冲突）：{int(template_id)}")
            _set_meta_blob13_field501_value(cloned_record, int(template_id))
            blob13_field501_after = int(template_id)

    if pc_canvas_position is not None and pc_size is not None:
        _set_rect_state_canvas_position_and_size(
            record=cloned_record,
            state_index=0,
            canvas_position=(float(pc_canvas_position[0]), float(pc_canvas_position[1])),
            size=(float(pc_size[0]), float(pc_size[1])),
            canvas_size_by_state_index=dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX),
        )

    if mobile_canvas_position is not None and mobile_size is not None:
        _set_rect_state_canvas_position_and_size(
            record=cloned_record,
            state_index=1,
            canvas_position=(float(mobile_canvas_position[0]), float(mobile_canvas_position[1])),
            size=(float(mobile_size[0]), float(mobile_size[1])),
            canvas_size_by_state_index=dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX),
        )

    ui_record_list.append(cloned_record)
    _append_children_guids_to_parent_record(parent_record, [int(allocated_guid)])

    mode = str(register_layout_root_mode or "").strip().lower()
    if mode not in {"none", "append", "prepend"}:
        raise ValueError(f"register_layout_root_mode 不支持：{mode!r}")
    if mode == "append":
        _append_layout_root_guid_to_layout_registry(raw_dump_object, int(allocated_guid))
    elif mode == "prepend":
        _prepend_layout_root_guid_to_layout_registry(raw_dump_object, int(allocated_guid))

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "schema_id": _sanitize_schema_id(schema_id),
        "parent_guid": int(parent_guid_int),
        "new_guid": int(allocated_guid),
        "new_name": (str(new_name) if new_name is not None else None),
        "register_layout_root_mode": mode,
        "rect": {
            "pc": {
                "canvas_position": (
                    {"x": float(pc_canvas_position[0]), "y": float(pc_canvas_position[1])}
                    if pc_canvas_position is not None
                    else None
                ),
                "size": (
                    {"x": float(pc_size[0]), "y": float(pc_size[1])}
                    if pc_size is not None
                    else None
                ),
            },
            "mobile": {
                "canvas_position": (
                    {"x": float(mobile_canvas_position[0]), "y": float(mobile_canvas_position[1])}
                    if mobile_canvas_position is not None
                    else None
                ),
                "size": (
                    {"x": float(mobile_size[0]), "y": float(mobile_size[1])}
                    if mobile_size is not None
                    else None
                ),
            },
            "layer": (int(layer) if layer is not None else None),
        },
        "meta_blob13_field501": {
            "mode": mode_tid,
            "before": (int(blob13_field501_before) if blob13_field501_before is not None else None),
            "after": (int(blob13_field501_after) if blob13_field501_after is not None else None),
        },
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_records = _extract_ui_record_list(verify_dump)
        verify_hit = _find_record_by_guid(verify_records, int(allocated_guid))
        report["verify"] = {"ok": bool(verify_hit is not None)}

    return report


def place_ui_control_from_schema_library(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_entry_schema_id: str,
    instance_schema_id: str,
    # parent：模板条目落到哪个节点下（通常是控件组库根，或某个组容器）
    template_parent_guid: int,
    # parent：实例落到哪个布局 root 下
    layout_guid: int,
    template_name: Optional[str] = None,
    instance_name: Optional[str] = None,
    # 可选：写回位置/大小（固定锚点语义；state0=电脑, state1=手机）
    pc_canvas_position: Optional[Tuple[float, float]] = None,
    pc_size: Optional[Tuple[float, float]] = None,
    mobile_canvas_position: Optional[Tuple[float, float]] = None,
    mobile_size: Optional[Tuple[float, float]] = None,
    # template_id：默认 auto 分配，确保与目标存档不冲突
    template_id_mode: str = "auto",  # "auto" | "set"
    template_id: Optional[int] = None,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    一键“放置一个控件”（B）：
    - 克隆一个“模板库条目 record”（template_entry_schema_id）并插入到 template_parent_guid 下
    - 克隆一个“布局实例 record”（instance_schema_id）并插入到 layout_guid 下
    - 自动分配一个新的 template_id，并把两条 record 的 502/*/13 blob 写成同一个值
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    if (pc_canvas_position is None) != (pc_size is None):
        raise ValueError("pc_canvas_position 与 pc_size 必须同时提供或同时省略")
    if (mobile_canvas_position is None) != (mobile_size is None):
        raise ValueError("mobile_canvas_position 与 mobile_size 必须同时提供或同时省略")

    mode_tid = str(template_id_mode or "").strip().lower()
    if mode_tid not in {"auto", "set"}:
        raise ValueError(f"template_id_mode 不支持：{mode_tid!r}")
    if mode_tid == "set" and template_id is None:
        raise ValueError("template_id_mode=set 时必须提供 template_id")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")
    existing_blob13_values = _collect_existing_meta_blob13_field501_values(ui_record_list)

    reserved = set(existing_guids) | set(existing_blob13_values)

    if mode_tid == "auto":
        chosen_blob13_field501 = _allocate_next_guid(reserved, start=max(reserved) + 1)
    else:
        chosen_blob13_field501 = int(template_id)
        if chosen_blob13_field501 in reserved:
            raise ValueError(f"field_501 值已存在于目标存档（或与 GUID 冲突）：{int(chosen_blob13_field501)}")
    reserved.add(int(chosen_blob13_field501))

    template_parent_guid_int = int(template_parent_guid)
    layout_guid_int = int(layout_guid)

    template_parent_record = _find_record_by_guid(ui_record_list, template_parent_guid_int)
    if template_parent_record is None:
        raise RuntimeError(f"未找到 template_parent_guid={template_parent_guid_int} 对应的 UI record。")
    layout_record = _find_record_by_guid(ui_record_list, layout_guid_int)
    if layout_record is None:
        raise RuntimeError(f"未找到 layout_guid={layout_guid_int} 对应的 UI record。")

    template_record = _load_schema_record(template_entry_schema_id)
    instance_record = _load_schema_record(instance_schema_id)

    if _find_progressbar_binding_blob(template_record) is not None or _find_progressbar_binding_blob(instance_record) is not None:
        raise ValueError(
            "place-control-from-schemas 暂不支持进度条：进度条模板/实例的依赖关系并非简单的 `502/*/13(field_501)` 对齐。"
            "请改用 `ui create-progressbar-template-and-place(-many)`（创建自定义模板+放置无模板实例），"
            "或使用 `ui add-progressbars-corners` / `ui clone-record-from-schema` 放置无模板进度条。"
        )

    # 1) 克隆模板库条目
    new_template_entry_guid = _allocate_next_guid(reserved, start=max(reserved) + 1)
    reserved.add(int(new_template_entry_guid))

    cloned_template_entry = copy.deepcopy(template_record)
    _set_widget_guid(cloned_template_entry, int(new_template_entry_guid))
    _set_widget_parent_guid_field504(cloned_template_entry, int(template_parent_guid_int))
    if template_name is not None:
        tn = str(template_name or "").strip()
        if tn == "":
            raise ValueError("template_name 不能为空字符串")
        _set_widget_name(cloned_template_entry, tn)
    if not _has_meta_blob13(cloned_template_entry):
        raise ValueError("template_entry record 缺少 meta blob（502/*/13），无法写回 field_501")
    _set_meta_blob13_field501_value(cloned_template_entry, int(chosen_blob13_field501))

    ui_record_list.append(cloned_template_entry)
    _append_children_guids_to_parent_record(template_parent_record, [int(new_template_entry_guid)])

    # 2) 克隆布局实例
    new_instance_guid = _allocate_next_guid(reserved, start=max(reserved) + 1)
    reserved.add(int(new_instance_guid))

    cloned_instance = copy.deepcopy(instance_record)
    _set_widget_guid(cloned_instance, int(new_instance_guid))
    _set_widget_parent_guid_field504(cloned_instance, int(layout_guid_int))
    if instance_name is not None:
        ins = str(instance_name or "").strip()
        if ins == "":
            raise ValueError("instance_name 不能为空字符串")
        _set_widget_name(cloned_instance, ins)
    if not _has_meta_blob13(cloned_instance):
        raise ValueError("instance record 缺少 meta blob（502/*/13），无法写回 field_501")
    _set_meta_blob13_field501_value(cloned_instance, int(chosen_blob13_field501))

    if pc_canvas_position is not None and pc_size is not None:
        _set_rect_state_canvas_position_and_size(
            record=cloned_instance,
            state_index=0,
            canvas_position=(float(pc_canvas_position[0]), float(pc_canvas_position[1])),
            size=(float(pc_size[0]), float(pc_size[1])),
            canvas_size_by_state_index=dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX),
        )
    if mobile_canvas_position is not None and mobile_size is not None:
        _set_rect_state_canvas_position_and_size(
            record=cloned_instance,
            state_index=1,
            canvas_position=(float(mobile_canvas_position[0]), float(mobile_canvas_position[1])),
            size=(float(mobile_size[0]), float(mobile_size[1])),
            canvas_size_by_state_index=dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX),
        )

    ui_record_list.append(cloned_instance)
    _append_children_guids_to_parent_record(layout_record, [int(new_instance_guid)])

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "template_entry_schema_id": _sanitize_schema_id(template_entry_schema_id),
        "instance_schema_id": _sanitize_schema_id(instance_schema_id),
        "template_parent_guid": int(template_parent_guid_int),
        "layout_guid": int(layout_guid_int),
        "meta_blob13_field501": {"mode": mode_tid, "value": int(chosen_blob13_field501)},
        "created": {
            "template_entry_guid": int(new_template_entry_guid),
            "instance_guid": int(new_instance_guid),
        },
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_records = _extract_ui_record_list(verify_dump)
        verify_template = _find_record_by_guid(verify_records, int(new_template_entry_guid))
        verify_instance = _find_record_by_guid(verify_records, int(new_instance_guid))
        report["verify"] = {
            "ok": bool((verify_template is not None) and (verify_instance is not None)),
            "template_entry_ok": bool(verify_template is not None),
            "instance_ok": bool(verify_instance is not None),
        }

    return report


__all__ = [
    "clone_ui_record_from_schema_library",
    "place_ui_control_from_schema_library",
]


