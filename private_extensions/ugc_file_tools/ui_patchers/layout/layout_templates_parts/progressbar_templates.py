from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui_parsers.progress_bars import find_progressbar_binding_blob as _find_progressbar_binding_blob
from ugc_file_tools.ui.readable_dump import (
    extract_primary_guid as _extract_primary_guid,
    extract_ui_record_list as _extract_ui_record_list,
)

from .shared import (
    DEFAULT_CANVAS_SIZE_BY_STATE_INDEX,
    DEFAULT_LIBRARY_ROOT_GUID,
    CreatedLayout,
    CreatedProgressbarTemplate,
    PlacedProgressbarInstance,
    _append_children_guids_to_parent_record,
    _append_layout_root_guid_to_layout_registry,
    _allocate_next_guid,
    _collect_all_widget_guids,
    _dump_gil_to_raw_json_object,
    _find_record_by_guid,
    _infer_base_layout_guid,
    _parse_protobuf_like_fields,
    _prepend_layout_root_guid_to_layout_registry,
    _set_children_guids_to_parent_record,
    _set_rect_state_canvas_position_and_size,
    _set_widget_guid,
    _set_widget_name,
    _set_widget_parent_guid_field504,
    _write_back_modified_gil_by_reencoding_payload,
)


def _is_progressbar_record(record: Dict[str, Any]) -> bool:
    return _find_progressbar_binding_blob(record) is not None


def _try_extract_field501_from_meta_blob13(record: Dict[str, Any]) -> Optional[int]:
    """
    从 record['502'] 的某个 element['13'](<binary_data>) 中解析 field_501(varint)。

    注意：该值不是统一意义上的 template_id，其语义依赖 record 形态：
    - 进度条“模板库条目”里，该值指向 template_root_guid
    - 控件组子控件里，该值更像是“next 指针”（用于保持 children 顺序）
    - 普通布局实例（无模板）通常没有该 blob
    """
    meta_list = record.get("502")
    if not isinstance(meta_list, list):
        return None
    for element in meta_list:
        if not isinstance(element, dict):
            continue
        blob = element.get("13")
        if not isinstance(blob, str) or not blob.startswith("<binary_data>"):
            continue
        data = parse_binary_data_hex_text(blob)
        fields, ok = _parse_protobuf_like_fields(data)
        if not ok:
            continue
        for field_number, wire_type, value in fields:
            if field_number == 501 and wire_type == 0 and isinstance(value, int):
                return int(value)
    return None


def _set_field501_to_meta_blob13(record: Dict[str, Any], value: int) -> None:
    meta_list = record.get("502")
    if not isinstance(meta_list, list):
        raise ValueError("record missing meta list at field 502")
    for element in meta_list:
        if not isinstance(element, dict):
            continue
        blob = element.get("13")
        if not isinstance(blob, str) or not blob.startswith("<binary_data>"):
            continue
        element["13"] = format_binary_data_hex_text(encode_message({"501": int(value)}))
        return
    raise ValueError("record missing <binary_data> blob at field 502/*/13")


def _find_any_progressbar_template_entry_and_root(
    ui_record_list: List[Any],
    *,
    library_root_guid: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    在目标存档中寻找一对“进度条模板样本”：
    - 模板库条目（parent == library_root_guid）
    - template_root（无 parent，且能被条目的 502/*/13 指到）
    """
    library_root_guid = int(library_root_guid)
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        if record.get("504") != library_root_guid:
            continue
        if not _is_progressbar_record(record):
            continue
        template_root_guid = _try_extract_field501_from_meta_blob13(record)
        if template_root_guid is None:
            continue
        root_record = _find_record_by_guid(ui_record_list, int(template_root_guid))
        if root_record is None:
            continue
        if "504" in root_record:
            continue
        if not _is_progressbar_record(root_record):
            continue
        return record, root_record
    raise RuntimeError(
        "未找到可复制的进度条模板样本：需要存在“库根下的进度条模板条目（parent==library_root_guid）”，"
        "且其 502/*/13(blob) 能指向一个无 parent 的 template_root record。"
        "建议使用 ugc_file_tools/save/test5更多界面控件.gil 作为基底，或先用官方编辑器保存一个进度条为自定义模板。"
    )


def _find_any_progressbar_no_template_instance(ui_record_list: List[Any]) -> Dict[str, Any]:
    """
    找一个“无模板”的进度条实例样本（通常是布局内直接放置的进度条）：
    - 有 parent（field 504）
    - meta(502) 形态为 list 且长度为 1（样本中无 502/*/13 blob）
    """
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        if not _is_progressbar_record(record):
            continue
        parent_value = record.get("504")
        if not isinstance(parent_value, int):
            continue
        meta_list = record.get("502")
        if not isinstance(meta_list, list) or len(meta_list) != 1:
            continue
        return record
    raise RuntimeError("未找到可复制的“无模板进度条实例”样本（需要存在布局内的进度条，且 meta_len==1）。")


def create_progressbar_template_and_place_in_layout(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_name: str,
    # 控件组库（模板库）根节点：test5/test6 均为 1073741838，可按需覆盖
    library_root_guid: int = DEFAULT_LIBRARY_ROOT_GUID,
    # 放置到哪个布局：二选一
    target_layout_guid: Optional[int] = None,
    create_layout_name: Optional[str] = None,
    base_layout_guid_for_create: Optional[int] = None,
    # 实例名（不填则复用 template_name）
    instance_name: Optional[str] = None,
    # 设备端坐标/大小（按 canvas_position 语义：左下角为 (0,0)）
    pc_canvas_position: Tuple[float, float] = (1.0, 1.0),
    pc_size: Tuple[float, float] = (200.0, 200.0),
    mobile_canvas_position: Tuple[float, float] = (5.0, 5.0),
    mobile_size: Tuple[float, float] = (10.0, 10.0),
    # 画布尺寸映射（如不传则使用校准默认）
    canvas_size_by_state_index: Optional[Dict[int, Tuple[float, float]]] = None,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    创建一个新的“进度条自定义模板”（模板库条目 + template_root）并在某个布局里放置一个“无模板实例”。

    写入内容：
    - 模板 root：新增一个 progressbar template_root record（无 parent），并注册到 `4/9/501[0]`（插到开头）。
    - 模板库条目：新增一个 progressbar record（parent=library_root_guid），并将其 `502/*/13` blob 写成 `template_root_guid`。
    - 布局实例：新增一个“无模板实例” progressbar record（parent=layout_guid，meta_len==1），按设备模板(state_index)设置位置/大小。

    目前仅支持“固定锚点”（anchor_min == anchor_max）。stretch 布局语义未完全补齐，遇到会直接抛错。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    template_name = str(template_name or "").strip()
    if template_name == "":
        raise ValueError("template_name 不能为空")

    if target_layout_guid is not None and create_layout_name is not None:
        raise ValueError("target_layout_guid 与 create_layout_name 只能二选一")

    if canvas_size_by_state_index is None:
        canvas_size_by_state_index = dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX)

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    library_root_guid = int(library_root_guid)
    library_root_record = _find_record_by_guid(ui_record_list, library_root_guid)
    if library_root_record is None:
        raise RuntimeError(f"未找到 library_root_guid={library_root_guid} 对应的 UI record。")

    template_entry_source, template_root_source = _find_any_progressbar_template_entry_and_root(
        ui_record_list,
        library_root_guid=int(library_root_guid),
    )
    # 用“无模板实例”作为布局放置复制源，避免把“模板库条目/模板root”错误放进布局导致编辑器显示为“模板控件”
    layout_instance_source = _find_any_progressbar_no_template_instance(ui_record_list)

    # 选择/创建布局
    created_layout: Optional[CreatedLayout] = None
    if create_layout_name is not None:
        create_layout_name = str(create_layout_name or "").strip()
        if create_layout_name == "":
            raise ValueError("create_layout_name 不能为空")
        if base_layout_guid_for_create is None:
            base_layout_guid_for_create = _infer_base_layout_guid(ui_record_list)
        base_layout_guid_for_create = int(base_layout_guid_for_create)

        max_guid = max(existing_guids)
        new_layout_guid = _allocate_next_guid(existing_guids, start=max_guid + 1)
        existing_guids.add(int(new_layout_guid))

        base_layout_record = _find_record_by_guid(ui_record_list, base_layout_guid_for_create)
        if base_layout_record is None:
            raise RuntimeError(f"未找到 base_layout_guid_for_create={base_layout_guid_for_create} 对应的 UI record。")

        cloned_layout = copy.deepcopy(base_layout_record)
        _set_widget_guid(cloned_layout, int(new_layout_guid))
        _set_widget_name(cloned_layout, create_layout_name)
        if "504" in cloned_layout:
            del cloned_layout["504"]
        _set_children_guids_to_parent_record(cloned_layout, [])

        ui_record_list.append(cloned_layout)
        _append_layout_root_guid_to_layout_registry(raw_dump_object, int(new_layout_guid))
        target_layout_guid = int(new_layout_guid)
        created_layout = CreatedLayout(
            guid=int(new_layout_guid),
            name=create_layout_name,
            base_layout_guid=base_layout_guid_for_create,
        )

    if target_layout_guid is None:
        raise ValueError("必须提供 target_layout_guid，或通过 create_layout_name 创建新布局。")

    target_layout_guid = int(target_layout_guid)
    layout_record = _find_record_by_guid(ui_record_list, target_layout_guid)
    if layout_record is None:
        raise RuntimeError(f"未找到 target_layout_guid={target_layout_guid} 对应的 UI record。")

    reserved = set(existing_guids)

    # 1) 新增 template_root（无 parent，注册到 4/9/501[0] 开头）
    max_guid = max(reserved)
    template_root_guid = _allocate_next_guid(reserved, start=int(max_guid) + 1)
    reserved.add(int(template_root_guid))

    cloned_template_root = copy.deepcopy(template_root_source)
    _set_widget_guid(cloned_template_root, int(template_root_guid))
    _set_widget_name(cloned_template_root, template_name)
    if "504" in cloned_template_root:
        del cloned_template_root["504"]
    ui_record_list.append(cloned_template_root)
    _prepend_layout_root_guid_to_layout_registry(raw_dump_object, int(template_root_guid))

    # 2) 新增模板库条目（parent=library_root_guid），并把 502/*/13 写成 template_root_guid
    template_entry_guid = _allocate_next_guid(reserved, start=int(template_root_guid) + 1)
    reserved.add(int(template_entry_guid))

    cloned_template_entry = copy.deepcopy(template_entry_source)
    _set_widget_guid(cloned_template_entry, int(template_entry_guid))
    _set_widget_name(cloned_template_entry, template_name)
    _set_widget_parent_guid_field504(cloned_template_entry, library_root_guid)
    _set_field501_to_meta_blob13(cloned_template_entry, int(template_root_guid))

    _append_children_guids_to_parent_record(library_root_record, [int(template_entry_guid)])
    ui_record_list.append(cloned_template_entry)

    created_template = CreatedProgressbarTemplate(
        entry_guid=int(template_entry_guid),
        template_root_guid=int(template_root_guid),
        name=template_name,
        library_root_guid=int(library_root_guid),
        entry_cloned_from_guid=int(_extract_primary_guid(template_entry_source) or 0),
        root_cloned_from_guid=int(_extract_primary_guid(template_root_source) or 0),
    )

    # 3) 在布局中新增一个“无模板实例”
    instance_name_value = str(instance_name or "").strip()
    if instance_name_value == "":
        instance_name_value = template_name

    instance_guid = _allocate_next_guid(reserved, start=int(template_entry_guid) + 1)
    reserved.add(int(instance_guid))

    cloned_instance = copy.deepcopy(layout_instance_source)
    _set_widget_guid(cloned_instance, int(instance_guid))
    _set_widget_name(cloned_instance, instance_name_value)
    _set_widget_parent_guid_field504(cloned_instance, int(target_layout_guid))

    # 写入设备端位置/大小：state0=电脑, state1=手机
    _set_rect_state_canvas_position_and_size(
        record=cloned_instance,
        state_index=0,
        canvas_position=(float(pc_canvas_position[0]), float(pc_canvas_position[1])),
        size=(float(pc_size[0]), float(pc_size[1])),
        canvas_size_by_state_index=canvas_size_by_state_index,
    )
    _set_rect_state_canvas_position_and_size(
        record=cloned_instance,
        state_index=1,
        canvas_position=(float(mobile_canvas_position[0]), float(mobile_canvas_position[1])),
        size=(float(mobile_size[0]), float(mobile_size[1])),
        canvas_size_by_state_index=canvas_size_by_state_index,
    )

    _append_children_guids_to_parent_record(layout_record, [int(instance_guid)])
    ui_record_list.append(cloned_instance)

    placed_instance = PlacedProgressbarInstance(
        guid=int(instance_guid),
        name=instance_name_value,
        layout_guid=int(target_layout_guid),
        cloned_from_guid=int(_extract_primary_guid(layout_instance_source) or 0),
    )

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "created_layout": (
            {
                "guid": created_layout.guid,
                "name": created_layout.name,
                "base_layout_guid": created_layout.base_layout_guid,
            }
            if created_layout is not None
            else None
        ),
        "created_template": {
            "entry_guid": created_template.entry_guid,
            "template_root_guid": created_template.template_root_guid,
            "name": created_template.name,
            "library_root_guid": created_template.library_root_guid,
            "entry_cloned_from_guid": created_template.entry_cloned_from_guid,
            "root_cloned_from_guid": created_template.root_cloned_from_guid,
        },
        "placed_instance": {
            "guid": placed_instance.guid,
            "name": placed_instance.name,
            "layout_guid": placed_instance.layout_guid,
            "cloned_from_guid": placed_instance.cloned_from_guid,
            "pc": {
                "canvas_position": {"x": float(pc_canvas_position[0]), "y": float(pc_canvas_position[1])},
                "size": {"x": float(pc_size[0]), "y": float(pc_size[1])},
            },
            "mobile": {
                "canvas_position": {"x": float(mobile_canvas_position[0]), "y": float(mobile_canvas_position[1])},
                "size": {"x": float(mobile_size[0]), "y": float(mobile_size[1])},
            },
        },
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        report["verify"] = {
            "ui_record_total": len(verify_ui_records),
            "layout_exists": _find_record_by_guid(verify_ui_records, int(target_layout_guid)) is not None,
            "template_entry_exists": _find_record_by_guid(verify_ui_records, int(template_entry_guid)) is not None,
            "template_root_exists": _find_record_by_guid(verify_ui_records, int(template_root_guid)) is not None,
            "instance_exists": _find_record_by_guid(verify_ui_records, int(instance_guid)) is not None,
        }

    return report


def create_progressbar_template_and_place_many_in_layout(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    template_name: str,
    # 控件组库（模板库）根节点：test5/test6 均为 1073741838，可按需覆盖
    library_root_guid: int = DEFAULT_LIBRARY_ROOT_GUID,
    # 放置到哪个布局：二选一
    target_layout_guid: Optional[int] = None,
    create_layout_name: Optional[str] = None,
    base_layout_guid_for_create: Optional[int] = None,
    # 实例名：默认使用 f"{instance_name_prefix}{i}"（i 从 1 开始）
    instance_name_prefix: Optional[str] = None,
    instance_total: int = 3,
    # 设备端坐标/大小（按 canvas_position 语义：左下角为 (0,0)）
    pc_canvas_position: Tuple[float, float] = (100.0, 100.0),
    pc_step: Tuple[float, float] = (0.0, 120.0),
    pc_size: Tuple[float, float] = (200.0, 50.0),
    mobile_canvas_position: Tuple[float, float] = (100.0, 100.0),
    mobile_step: Tuple[float, float] = (0.0, 100.0),
    mobile_size: Tuple[float, float] = (200.0, 50.0),
    # 画布尺寸映射（如不传则使用校准默认）
    canvas_size_by_state_index: Optional[Dict[int, Tuple[float, float]]] = None,
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    创建一个新的“进度条自定义模板”（模板库条目 + template_root），并在某个布局里放置多个“无模板实例”。

    与 `create_progressbar_template_and_place_in_layout` 的区别：
    - 会在同一布局内放置多个实例（instances），用于快速堆叠样本（坐标按 step 递增）
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    template_name = str(template_name or "").strip()
    if template_name == "":
        raise ValueError("template_name 不能为空")

    if target_layout_guid is not None and create_layout_name is not None:
        raise ValueError("target_layout_guid 与 create_layout_name 只能二选一")

    instance_total = int(instance_total)
    if instance_total <= 0:
        raise ValueError("instance_total 必须为正整数")

    if canvas_size_by_state_index is None:
        canvas_size_by_state_index = dict(DEFAULT_CANVAS_SIZE_BY_STATE_INDEX)

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    existing_guids = _collect_all_widget_guids(ui_record_list)
    if not existing_guids:
        raise RuntimeError("无法收集现有 GUID（疑似 dump 结构异常）。")

    library_root_guid = int(library_root_guid)
    library_root_record = _find_record_by_guid(ui_record_list, library_root_guid)
    if library_root_record is None:
        raise RuntimeError(f"未找到 library_root_guid={library_root_guid} 对应的 UI record。")

    template_entry_source, template_root_source = _find_any_progressbar_template_entry_and_root(
        ui_record_list,
        library_root_guid=int(library_root_guid),
    )
    layout_instance_source = _find_any_progressbar_no_template_instance(ui_record_list)

    # 选择/创建布局
    created_layout: Optional[CreatedLayout] = None
    if create_layout_name is not None:
        create_layout_name = str(create_layout_name or "").strip()
        if create_layout_name == "":
            raise ValueError("create_layout_name 不能为空")
        if base_layout_guid_for_create is None:
            base_layout_guid_for_create = _infer_base_layout_guid(ui_record_list)
        base_layout_guid_for_create = int(base_layout_guid_for_create)

        max_guid = max(existing_guids)
        new_layout_guid = _allocate_next_guid(existing_guids, start=max_guid + 1)
        existing_guids.add(int(new_layout_guid))

        base_layout_record = _find_record_by_guid(ui_record_list, base_layout_guid_for_create)
        if base_layout_record is None:
            raise RuntimeError(f"未找到 base_layout_guid_for_create={base_layout_guid_for_create} 对应的 UI record。")

        cloned_layout = copy.deepcopy(base_layout_record)
        _set_widget_guid(cloned_layout, int(new_layout_guid))
        _set_widget_name(cloned_layout, create_layout_name)
        if "504" in cloned_layout:
            del cloned_layout["504"]
        _set_children_guids_to_parent_record(cloned_layout, [])

        ui_record_list.append(cloned_layout)
        _append_layout_root_guid_to_layout_registry(raw_dump_object, int(new_layout_guid))
        target_layout_guid = int(new_layout_guid)
        created_layout = CreatedLayout(
            guid=int(new_layout_guid),
            name=create_layout_name,
            base_layout_guid=base_layout_guid_for_create,
        )

    if target_layout_guid is None:
        raise ValueError("必须提供 target_layout_guid，或通过 create_layout_name 创建新布局。")

    target_layout_guid = int(target_layout_guid)
    layout_record = _find_record_by_guid(ui_record_list, target_layout_guid)
    if layout_record is None:
        raise RuntimeError(f"未找到 target_layout_guid={target_layout_guid} 对应的 UI record。")

    reserved = set(existing_guids)

    # 1) 新增 template_root（无 parent，注册到 4/9/501[0] 开头）
    max_guid = max(reserved)
    template_root_guid = _allocate_next_guid(reserved, start=int(max_guid) + 1)
    reserved.add(int(template_root_guid))

    cloned_template_root = copy.deepcopy(template_root_source)
    _set_widget_guid(cloned_template_root, int(template_root_guid))
    _set_widget_name(cloned_template_root, template_name)
    if "504" in cloned_template_root:
        del cloned_template_root["504"]
    ui_record_list.append(cloned_template_root)
    _prepend_layout_root_guid_to_layout_registry(raw_dump_object, int(template_root_guid))

    # 2) 新增模板库条目（parent=library_root_guid），并把 502/*/13 写成 template_root_guid
    template_entry_guid = _allocate_next_guid(reserved, start=int(template_root_guid) + 1)
    reserved.add(int(template_entry_guid))

    cloned_template_entry = copy.deepcopy(template_entry_source)
    _set_widget_guid(cloned_template_entry, int(template_entry_guid))
    _set_widget_name(cloned_template_entry, template_name)
    _set_widget_parent_guid_field504(cloned_template_entry, library_root_guid)
    _set_field501_to_meta_blob13(cloned_template_entry, int(template_root_guid))

    _append_children_guids_to_parent_record(library_root_record, [int(template_entry_guid)])
    ui_record_list.append(cloned_template_entry)

    created_template = CreatedProgressbarTemplate(
        entry_guid=int(template_entry_guid),
        template_root_guid=int(template_root_guid),
        name=template_name,
        library_root_guid=int(library_root_guid),
        entry_cloned_from_guid=int(_extract_primary_guid(template_entry_source) or 0),
        root_cloned_from_guid=int(_extract_primary_guid(template_root_source) or 0),
    )

    # 3) 在布局中新增多个“无模板实例”（位置按 step 递增）
    instance_name_prefix_value = str(instance_name_prefix or "").strip()
    if instance_name_prefix_value == "":
        instance_name_prefix_value = template_name

    placed_instance_reports: List[Dict[str, Any]] = []
    instance_guids: List[int] = []

    next_start = int(template_entry_guid) + 1
    for i in range(instance_total):
        instance_guid = _allocate_next_guid(reserved, start=next_start)
        reserved.add(int(instance_guid))
        next_start = int(instance_guid) + 1

        instance_name_value = f"{instance_name_prefix_value}{i + 1}"

        cloned_instance = copy.deepcopy(layout_instance_source)
        _set_widget_guid(cloned_instance, int(instance_guid))
        _set_widget_name(cloned_instance, instance_name_value)
        _set_widget_parent_guid_field504(cloned_instance, int(target_layout_guid))

        pc_pos_i = (
            float(pc_canvas_position[0]) + float(pc_step[0]) * float(i),
            float(pc_canvas_position[1]) + float(pc_step[1]) * float(i),
        )
        mobile_pos_i = (
            float(mobile_canvas_position[0]) + float(mobile_step[0]) * float(i),
            float(mobile_canvas_position[1]) + float(mobile_step[1]) * float(i),
        )

        # 写入设备端位置/大小：state0=电脑, state1=手机
        _set_rect_state_canvas_position_and_size(
            record=cloned_instance,
            state_index=0,
            canvas_position=pc_pos_i,
            size=(float(pc_size[0]), float(pc_size[1])),
            canvas_size_by_state_index=canvas_size_by_state_index,
        )
        _set_rect_state_canvas_position_and_size(
            record=cloned_instance,
            state_index=1,
            canvas_position=mobile_pos_i,
            size=(float(mobile_size[0]), float(mobile_size[1])),
            canvas_size_by_state_index=canvas_size_by_state_index,
        )

        ui_record_list.append(cloned_instance)
        instance_guids.append(int(instance_guid))
        placed_instance_reports.append(
            {
                "guid": int(instance_guid),
                "name": instance_name_value,
                "layout_guid": int(target_layout_guid),
                "cloned_from_guid": int(_extract_primary_guid(layout_instance_source) or 0),
                "pc": {
                    "canvas_position": {"x": float(pc_pos_i[0]), "y": float(pc_pos_i[1])},
                    "size": {"x": float(pc_size[0]), "y": float(pc_size[1])},
                },
                "mobile": {
                    "canvas_position": {"x": float(mobile_pos_i[0]), "y": float(mobile_pos_i[1])},
                    "size": {"x": float(mobile_size[0]), "y": float(mobile_size[1])},
                },
            }
        )

    _append_children_guids_to_parent_record(layout_record, instance_guids)

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "created_layout": (
            {
                "guid": created_layout.guid,
                "name": created_layout.name,
                "base_layout_guid": created_layout.base_layout_guid,
            }
            if created_layout is not None
            else None
        ),
        "created_template": {
            "entry_guid": created_template.entry_guid,
            "template_root_guid": created_template.template_root_guid,
            "name": created_template.name,
            "library_root_guid": created_template.library_root_guid,
            "entry_cloned_from_guid": created_template.entry_cloned_from_guid,
            "root_cloned_from_guid": created_template.root_cloned_from_guid,
        },
        "placed_instances": placed_instance_reports,
        "placed_instance_total": len(placed_instance_reports),
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        report["verify"] = {
            "ui_record_total": len(verify_ui_records),
            "layout_exists": _find_record_by_guid(verify_ui_records, int(target_layout_guid)) is not None,
            "template_entry_exists": _find_record_by_guid(verify_ui_records, int(template_entry_guid)) is not None,
            "template_root_exists": _find_record_by_guid(verify_ui_records, int(template_root_guid)) is not None,
            "instances_exist": all(_find_record_by_guid(verify_ui_records, int(g)) is not None for g in instance_guids),
        }

    return report



