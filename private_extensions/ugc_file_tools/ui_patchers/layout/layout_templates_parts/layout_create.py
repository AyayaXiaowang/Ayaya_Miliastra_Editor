from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from .shared import (
    _append_layout_root_guid_to_layout_registry,
    _allocate_next_guid,
    _collect_all_widget_guids,
    _dump_gil_to_raw_json_object,
    _find_record_by_guid,
    _get_children_guids_from_parent_record,
    _infer_base_layout_guid,
    _set_children_guids_to_parent_record,
    _set_widget_guid,
    _set_widget_name,
    _set_widget_parent_guid_field504,
    _write_back_modified_gil_by_reencoding_payload,
)


def create_layout_in_gil(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    new_layout_name: str,
    base_layout_guid: Optional[int] = None,
    empty_layout: bool = False,
    clone_children: bool = True,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    在 `.gil` 内新增一个“界面布局（layout root）”记录。

    实现：复制一个现有布局 root record，分配新 GUID，改名；默认克隆 base_layout 的 children（生成“带固有内容”的新布局）。
    若需要创建纯空布局（危险），需显式传入 empty_layout=True 且 clone_children=False。

    备注：
    - 当前样本中布局 root 的特征：record 没有 field 504（parent），且 field 503[0] 为 children guid 的 varint stream。
    - 本函数不尝试改“默认布局选择/激活布局”；只是把新布局写入文件，供编辑器/后续流程使用。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))
    new_layout_name = str(new_layout_name or "").strip()
    if new_layout_name == "":
        raise ValueError("new_layout_name 不能为空")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    if base_layout_guid is None:
        base_layout_guid = _infer_base_layout_guid(ui_record_list)
    base_layout_guid = int(base_layout_guid)
    base_record = _find_record_by_guid(ui_record_list, base_layout_guid)
    if base_record is None:
        raise RuntimeError(f"未找到 base_layout_guid={base_layout_guid} 对应的 UI record。")

    max_guid = max(existing_guids)
    new_layout_guid = _allocate_next_guid(existing_guids, start=max_guid + 1)
    existing_guids.add(int(new_layout_guid))

    cloned = copy.deepcopy(base_record)
    _set_widget_guid(cloned, int(new_layout_guid))
    _set_widget_name(cloned, new_layout_name)
    if "504" in cloned:
        del cloned["504"]

    if bool(clone_children) and bool(empty_layout):
        raise ValueError("clone_children=True 时 empty_layout 必须为 False（否则语义冲突）。")

    new_child_records: List[Dict[str, Any]] = []
    if bool(clone_children):
        base_child_guids = _get_children_guids_from_parent_record(base_record)
        if not base_child_guids:
            raise RuntimeError(
                f"base_layout_guid={int(base_layout_guid)} 的 children 为空，无法克隆固有内容；"
                "请显式指定一个有 children 的 base_layout_guid，或使用 empty_layout=True 创建空布局。"
            )
        base_child_records: List[Dict[str, Any]] = []
        for child_guid in base_child_guids:
            child_record = _find_record_by_guid(ui_record_list, int(child_guid))
            if child_record is None:
                raise RuntimeError(f"base_layout 的 children guid={int(child_guid)} 未找到对应 record。")
            base_child_records.append(child_record)

        next_start = int(new_layout_guid) + 1
        new_child_guids: List[int] = []
        for child_record in base_child_records:
            new_child_guid = _allocate_next_guid(existing_guids, start=next_start)
            existing_guids.add(int(new_child_guid))
            next_start = int(new_child_guid) + 1

            cloned_child = copy.deepcopy(child_record)
            _set_widget_guid(cloned_child, int(new_child_guid))
            _set_widget_parent_guid_field504(cloned_child, int(new_layout_guid))
            new_child_records.append(cloned_child)
            new_child_guids.append(int(new_child_guid))

        _set_children_guids_to_parent_record(cloned, new_child_guids)
    else:
        if bool(empty_layout):
            _set_children_guids_to_parent_record(cloned, [])
        else:
            raise ValueError("empty_layout=False 但未启用 clone_children，会导致 child 归属不一致。")

    ui_record_list.append(cloned)
    ui_record_list.extend(new_child_records)
    _append_layout_root_guid_to_layout_registry(raw_dump_object, int(new_layout_guid))

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "created_layout": {
            "guid": int(new_layout_guid),
            "name": new_layout_name,
            "base_layout_guid": int(base_layout_guid),
            "empty_layout": bool(empty_layout),
        },
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        report["verify"] = {
            "ui_record_total": len(verify_ui_records),
            "layout_exists": _find_record_by_guid(verify_ui_records, int(new_layout_guid)) is not None,
        }

    return report



