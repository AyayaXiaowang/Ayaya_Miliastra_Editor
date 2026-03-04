from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ..shared import (
    DEFAULT_LIBRARY_ROOT_GUID,
    CreatedControlGroup,
    _allocate_next_guid,
    _append_children_guids_to_parent_record,
    _collect_all_widget_guids,
    _dump_gil_to_raw_json_object,
    _find_record_by_guid,
    _force_record_to_group_container_shape,
    _get_children_guids_from_parent_record,
    _replace_children_guids_in_parent_record,
    _set_children_guids_to_parent_record,
    _set_widget_guid,
    _set_widget_name,
    _set_widget_parent_guid_field504,
    _write_back_modified_gil_by_reencoding_payload,
)
from .helpers import _assert_children_are_custom_placeable_controls, _extract_name_for_debug


def create_control_group_in_library_from_component_groups(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    component_group_guids: List[int],
    group_name: str,
    library_root_guid: int = DEFAULT_LIBRARY_ROOT_GUID,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    将“布局内的组件组（group container）”克隆一份到控件组库，并把其 children 打成一个库内控件组。

    典型场景（Web UI 导入）：
    - 每个按钮会在布局下生成一个组件组容器（纯组容器，无 RectTransform）
    - 组容器的 children 为多个可放置控件（道具展示/文本框/进度条/边框/阴影等，均含 RectTransform）
    - 希望把某些按钮（如左上角导航）写进“界面控件组库”以便复用/保存模板

    行为：
    - 从每个 component_group_guid 读取 children guids
    - 将这些 children records 逐条 clone 到 library_root 下（分配新 guid）
    - 再在 library_root 下把克隆后的 children 打组为一个父节点（组容器）
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    group_name = str(group_name or "").strip()
    if group_name == "":
        raise ValueError("group_name 不能为空")

    if not isinstance(component_group_guids, list) or not component_group_guids:
        raise ValueError("component_group_guids 不能为空")
    component_group_guids = [int(g) for g in component_group_guids]
    if len(set(component_group_guids)) != len(component_group_guids):
        raise ValueError("component_group_guids 存在重复值")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)
    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    library_root_guid = int(library_root_guid)
    library_root_record = _find_record_by_guid(ui_record_list, library_root_guid)
    if library_root_record is None:
        raise RuntimeError(f"未找到 library_root_guid={int(library_root_guid)} 对应的 UI record。")

    # 1) 收集“组件组 children”（必须是可放置控件）
    source_child_records: List[Dict[str, Any]] = []
    source_child_guids: List[int] = []
    for cg_guid in component_group_guids:
        group_record = _find_record_by_guid(ui_record_list, int(cg_guid))
        if group_record is None:
            raise RuntimeError(f"未找到 component_group_guid={int(cg_guid)} 对应的 UI record。")
        child_guids = _get_children_guids_from_parent_record(group_record)
        if not child_guids:
            raise ValueError(f"component_group_guid={int(cg_guid)} 的 children 为空，无法写入控件组库。")
        for child_guid in child_guids:
            rec = _find_record_by_guid(ui_record_list, int(child_guid))
            if rec is None:
                raise RuntimeError(f"component_group child guid={int(child_guid)} 未找到对应 record。")
            source_child_records.append(rec)
            source_child_guids.append(int(child_guid))

    _assert_children_are_custom_placeable_controls(
        child_records=source_child_records,
        context="create_control_group_in_library_from_component_groups",
    )

    # 2) clone children 到 library_root 下（分配新 guid；要求 child 本身无 children，避免克隆半棵树导致引用断裂）
    reserved = set(existing_guids)
    next_start = int(max(reserved)) + 1
    cloned_child_guids: List[int] = []
    cloned_child_records: List[Dict[str, Any]] = []

    for src in source_child_records:
        if _get_children_guids_from_parent_record(src):
            raise ValueError(
                "当前不支持克隆“带 children 的控件 record”（需要克隆整棵子树并重写引用）；"
                f"请先确保组件组 children 均为叶子控件。record_name={_extract_name_for_debug(src)!r}"
            )
        new_guid = _allocate_next_guid(reserved, start=next_start)
        reserved.add(int(new_guid))
        next_start = int(new_guid) + 1

        cloned = copy.deepcopy(src)
        _set_widget_guid(cloned, int(new_guid))
        _set_widget_parent_guid_field504(cloned, int(library_root_guid))
        cloned_child_guids.append(int(new_guid))
        cloned_child_records.append(cloned)

    # append cloned children and register to library_root children list
    ui_record_list.extend(cloned_child_records)
    _append_children_guids_to_parent_record(library_root_record, [int(g) for g in cloned_child_guids])

    # 3) 在 library_root 下把 clones 打组（复用 create_control_group_in_library 的写回口径）
    group_guid = _allocate_next_guid(reserved, start=next_start)
    reserved.add(int(group_guid))

    cloned_group = copy.deepcopy(library_root_record)
    _set_widget_guid(cloned_group, int(group_guid))
    # 兼容：部分存档中“库根/根容器”的 name component 形态为 505[0]/12 = "<binary_data> "（而不是 dict）。
    # 但库内“组容器”在样本中使用 dict 形态；这里强制写为 dict，确保组名可读且后续 dump 可解析。
    component_list = cloned_group.get("505")
    if not isinstance(component_list, list) or not component_list:
        raise ValueError("record missing component list at field 505")
    name_component = component_list[0]
    if not isinstance(name_component, dict):
        raise ValueError("record field 505[0] must be dict")
    name_component["12"] = {"501": str(group_name)}
    _set_widget_parent_guid_field504(cloned_group, int(library_root_guid))
    _set_children_guids_to_parent_record(cloned_group, [int(g) for g in cloned_child_guids])
    _force_record_to_group_container_shape(cloned_group)

    # 用 group_guid 替换刚插入的 cloned children（插入位置：第一个 cloned child 的位置）
    _replace_children_guids_in_parent_record(
        library_root_record,
        remove_child_guids=[int(g) for g in cloned_child_guids],
        insert_child_guids=[int(group_guid)],
    )

    # 将 cloned children 的 parent 指向 group
    for child_record in cloned_child_records:
        _set_widget_parent_guid_field504(child_record, int(group_guid))

    ui_record_list.append(cloned_group)

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    created_group = CreatedControlGroup(
        guid=int(group_guid),
        name=group_name,
        library_root_guid=int(library_root_guid),
        child_guids=tuple(int(g) for g in cloned_child_guids),
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "source_component_group_guids": [int(g) for g in component_group_guids],
        "source_child_guids_total": int(len(source_child_guids)),
        "created_group": {
            "guid": created_group.guid,
            "name": created_group.name,
            "library_root_guid": created_group.library_root_guid,
            "child_guids": list(created_group.child_guids),
        },
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        verify_group = _find_record_by_guid(verify_ui_records, int(group_guid))
        verify_library = _find_record_by_guid(verify_ui_records, int(library_root_guid))
        report["verify"] = {
            "ui_record_total": len(verify_ui_records),
            "group_exists": verify_group is not None,
            "library_root_exists": verify_library is not None,
            "library_children_contains_group": (
                (int(group_guid) in set(_get_children_guids_from_parent_record(verify_library)))
                if verify_library is not None
                else None
            ),
            "group_children_total": (
                len(_get_children_guids_from_parent_record(verify_group)) if verify_group is not None else None
            ),
            "child_parent_ok": all(
                (_find_record_by_guid(verify_ui_records, int(g)) or {}).get("504") == int(group_guid)
                for g in cloned_child_guids
            ),
        }

    return report


def create_control_group_in_library(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    library_root_guid: int = DEFAULT_LIBRARY_ROOT_GUID,
    group_name: str,
    child_guids: List[int],
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    在控件组库根（library_root_guid）下把若干控件“打组”为一个父节点（组容器）。

    样本结论（来自 `ugc_file_tools/save/界面控件组/*.gil`）：
    - parent 指针：record['504'] = parent_guid
    - children 列表：record['503'][0] 为 varint stream（<binary_data>）
    - 组容器的组件形态：record['505'][1] 固定为 14/...（见 `_GROUP_CONTAINER_COMPONENT1`）
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    group_name = str(group_name or "").strip()
    if group_name == "":
        raise ValueError("group_name 不能为空")

    if not isinstance(child_guids, list) or not child_guids:
        raise ValueError("child_guids 不能为空")
    normalized_child_guids: List[int] = [int(g) for g in child_guids]
    if len(set(normalized_child_guids)) != len(normalized_child_guids):
        raise ValueError("child_guids 存在重复值")

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    library_root_guid = int(library_root_guid)
    library_root_record = _find_record_by_guid(ui_record_list, library_root_guid)
    if library_root_record is None:
        raise RuntimeError(f"未找到 library_root_guid={library_root_guid} 对应的 UI record。")

    library_children = _get_children_guids_from_parent_record(library_root_record)
    for guid in normalized_child_guids:
        if int(guid) not in set(library_children):
            raise ValueError(f"child_guid={int(guid)} 不在 library_root(children) 中，无法打组。")

    child_records: List[Dict[str, Any]] = []
    for guid in normalized_child_guids:
        rec = _find_record_by_guid(ui_record_list, int(guid))
        if rec is None:
            raise RuntimeError(f"未找到 child_guid={int(guid)} 对应的 UI record。")
        child_records.append(rec)

    _assert_children_are_custom_placeable_controls(
        child_records=child_records,
        context="create_control_group_in_library",
    )

    group_guid = _allocate_next_guid(existing_guids, start=max(existing_guids) + 1)
    existing_guids.add(int(group_guid))

    # 组容器 record：使用 library_root_record 作为基底，强制套用“组容器”meta 与组件形态
    cloned_group = copy.deepcopy(library_root_record)
    _set_widget_guid(cloned_group, int(group_guid))
    _set_widget_name(cloned_group, group_name)
    _set_widget_parent_guid_field504(cloned_group, int(library_root_guid))
    _set_children_guids_to_parent_record(cloned_group, [int(g) for g in normalized_child_guids])
    _force_record_to_group_container_shape(cloned_group)

    # 更新 library_root 的 children：用 group_guid 替换原 child_guids（保持顺序稳定：插入在第一个 child 位置）
    _replace_children_guids_in_parent_record(
        library_root_record,
        remove_child_guids=normalized_child_guids,
        insert_child_guids=[int(group_guid)],
    )

    # 将 children 的 parent 指向 group
    for child_record in child_records:
        _set_widget_parent_guid_field504(child_record, int(group_guid))

    ui_record_list.append(cloned_group)

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    created_group = CreatedControlGroup(
        guid=int(group_guid),
        name=group_name,
        library_root_guid=int(library_root_guid),
        child_guids=tuple(int(g) for g in normalized_child_guids),
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "created_group": {
            "guid": created_group.guid,
            "name": created_group.name,
            "library_root_guid": created_group.library_root_guid,
            "child_guids": list(created_group.child_guids),
        },
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        verify_group = _find_record_by_guid(verify_ui_records, int(group_guid))
        verify_library = _find_record_by_guid(verify_ui_records, int(library_root_guid))

        report["verify"] = {
            "ui_record_total": len(verify_ui_records),
            "group_exists": verify_group is not None,
            "library_root_exists": verify_library is not None,
            "library_children": (
                _get_children_guids_from_parent_record(verify_library) if verify_library is not None else None
            ),
            "group_children": (
                _get_children_guids_from_parent_record(verify_group) if verify_group is not None else None
            ),
            "child_parent_ok": all(
                (_find_record_by_guid(verify_ui_records, int(g)) or {}).get("504") == int(group_guid)
                for g in normalized_child_guids
            ),
        }

    return report


__all__ = [
    "create_control_group_in_library_from_component_groups",
    "create_control_group_in_library",
]

