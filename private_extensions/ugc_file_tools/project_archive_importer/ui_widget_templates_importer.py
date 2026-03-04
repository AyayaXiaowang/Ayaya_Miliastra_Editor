from __future__ import annotations

import copy
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from ugc_file_tools.gil_dump_codec.gil_container import build_gil_file_bytes_from_payload, read_gil_container_spec
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.node_graph_writeback.gil_dump import dump_gil_to_raw_json_object, get_payload_root
from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir


@dataclass(frozen=True, slots=True)
class UIWidgetTemplatesImportOptions:
    mode: str = "merge"  # "merge" | "overwrite"


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


def _extract_primary_guid(record: Dict[str, Any]) -> Optional[int]:
    """
    UI record 的 guid（field 501）。

    注意：
    - DLL dump-json 口径通常为 list（即使只有 1 个元素）
    - 纯 Python protobuf-like dump（`node_graph_writeback.gil_dump`）对“只出现一次的字段”可能输出为 scalar

    为避免 overwrite/merge 判定漂移，这里同时兼容 list 与 scalar 两种表示。
    """
    guid_value = record.get("501")
    if isinstance(guid_value, int) and not isinstance(guid_value, bool):
        return int(guid_value)
    if not isinstance(guid_value, list) or not guid_value:
        return None
    first = guid_value[0]
    if isinstance(first, int) and not isinstance(first, bool):
        return int(first)
    return None


def _set_primary_guid(record: Dict[str, Any], new_guid: int) -> None:
    guid_value = record.get("501")
    if isinstance(guid_value, int) and not isinstance(guid_value, bool):
        old_guid = int(guid_value)
        record["501"] = int(new_guid)
    elif isinstance(guid_value, list) and guid_value:
        old_guid_value = guid_value[0]
        if not isinstance(old_guid_value, int) or isinstance(old_guid_value, bool):
            raise ValueError("record field 501[0] must be int")
        old_guid = int(old_guid_value)
        guid_value[0] = int(new_guid)
    else:
        raise ValueError("record missing guid at field 501")

    meta_list = record.get("502")
    if not isinstance(meta_list, list):
        return
    for meta in meta_list:
        if not isinstance(meta, dict):
            continue
        node11 = meta.get("11")
        if not isinstance(node11, dict):
            continue
        current = node11.get("501")
        if isinstance(current, int) and int(current) == old_guid:
            node11["501"] = int(new_guid)


def _ensure_layout_registry_blob(node9: Dict[str, Any]) -> tuple[List[int], List[Any]]:
    """
    返回：
    - decoded_registry_guids：layout registry varint stream 解码后的 guid 列表
    - list501：node9["501"] 的 list 视图（用于写回 list501[0]）
    """
    list501 = _ensure_path_list_allow_scalar(node9, "501")
    if not list501:
        list501.append(format_binary_data_hex_text(b""))
        return [], list501

    first = list501[0]
    if first == "":
        return [], list501
    if not isinstance(first, str) or not first.startswith("<binary_data>"):
        raise ValueError("字段 '4/9/501[0]' 期望为 '<binary_data>' 字符串或空字符串。")
    data = parse_binary_data_hex_text(first)
    if not data:
        return [], list501
    return _decode_varint_stream(data), list501


def _extract_children_guids_from_record(record: Dict[str, Any]) -> List[int]:
    field503 = record.get("503")
    if not isinstance(field503, list) or not field503:
        return []
    first = field503[0]
    if isinstance(first, str) and first == "":
        return []
    if not isinstance(first, str) or not first.startswith("<binary_data>"):
        return []
    data = parse_binary_data_hex_text(first)
    if not data:
        return []
    return _decode_varint_stream(data)


def _set_children_guids_to_parent_record(record: Dict[str, Any], child_guids: List[int]) -> None:
    field503 = record.get("503")
    if isinstance(field503, list):
        list503 = field503
    elif field503 is None:
        list503 = []
        record["503"] = list503
    else:
        list503 = [field503]
        record["503"] = list503
    if not list503:
        list503.append(format_binary_data_hex_text(b""))
    list503[0] = format_binary_data_hex_text(_encode_varint_stream([int(v) for v in child_guids]))


def _decode_varint(data: bytes, offset: int) -> tuple[int, int, bool]:
    value = 0
    shift_bits = 0
    current_offset = offset
    while True:
        if current_offset >= len(data):
            return 0, current_offset, False
        current_byte = data[current_offset]
        current_offset += 1
        value |= (current_byte & 0x7F) << shift_bits
        if (current_byte & 0x80) == 0:
            return value, current_offset, True
        shift_bits += 7
        if shift_bits >= 64:
            return 0, current_offset, False


def _decode_varint_stream(data: bytes) -> List[int]:
    values: List[int] = []
    offset = 0
    end_offset = len(data)
    while offset < end_offset:
        value, offset, ok = _decode_varint(data, offset)
        if not ok:
            raise ValueError("invalid varint stream")
        values.append(int(value))
    return values


def _encode_varint(value: int) -> bytes:
    out = bytearray()
    v = int(value)
    while True:
        to_write = v & 0x7F
        v >>= 7
        if v:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            break
    return bytes(out)


def _encode_varint_stream(values: List[int]) -> bytes:
    out = bytearray()
    for v in values:
        out.extend(_encode_varint(int(v)))
    return bytes(out)


def _iter_ui_widget_template_files(project_root: Path) -> List[Path]:
    directory = (Path(project_root) / "管理配置" / "UI控件模板").resolve()
    if not directory.is_dir():
        return []
    files: List[Path] = []
    for p in sorted(directory.glob("*.json"), key=lambda x: x.as_posix()):
        if p.name == "ui_widget_templates_index.json":
            continue
        files.append(p.resolve())
    return files


def _load_ui_widget_template_json(path: Path) -> Optional[Dict[str, Any]]:
    p = Path(path).resolve()
    if not p.is_file():
        return None
    obj = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return None
    template_id = obj.get("template_id")
    if not isinstance(template_id, str) or template_id.strip() == "":
        return None
    return obj


def _load_raw_template_bundle(project_root: Path, template_obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metadata = template_obj.get("metadata")
    if not isinstance(metadata, dict):
        return None
    ugc = metadata.get("ugc")
    if not isinstance(ugc, dict):
        return None
    ui_meta = ugc.get("ui_widget_template")
    if not isinstance(ui_meta, dict):
        return None
    raw_path_text = ui_meta.get("raw_template")
    if not isinstance(raw_path_text, str) or raw_path_text.strip() == "":
        return None

    raw_path = (Path(project_root) / Path(raw_path_text)).resolve()
    if not raw_path.is_file():
        return None
    obj = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        return None
    return obj


def import_ui_widget_templates_from_project_archive_to_gil(
    *,
    project_archive_path: Path,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    options: UIWidgetTemplatesImportOptions,
) -> Dict[str, Any]:
    project_path = Path(project_archive_path).resolve()
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not project_path.is_dir():
        raise FileNotFoundError(str(project_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    mode = str(options.mode or "").strip().lower()
    if mode not in {"merge", "overwrite"}:
        raise ValueError(f"unsupported mode: {mode!r}")

    template_files = _iter_ui_widget_template_files(project_path)
    templates_skipped_invalid_files: List[str] = []
    templates_skipped_missing_raw: List[str] = []
    raw_templates: List[tuple[str, Dict[str, Any], Dict[str, Any]]] = []

    for template_file in template_files:
        template_obj = _load_ui_widget_template_json(template_file)
        if template_obj is None:
            templates_skipped_invalid_files.append(str(template_file))
            continue

        template_id_text = str(template_obj.get("template_id") or "").strip()
        if template_id_text == "":
            templates_skipped_invalid_files.append(str(template_file))
            continue

        raw_bundle = _load_raw_template_bundle(project_path, template_obj)
        if raw_bundle is None:
            templates_skipped_missing_raw.append(template_id_text)
            continue
        root_record = raw_bundle.get("template_root_record")
        child_records_obj = raw_bundle.get("child_records")
        if not isinstance(root_record, dict) or not isinstance(child_records_obj, list):
            templates_skipped_missing_raw.append(template_id_text)
            continue

        raw_templates.append((template_id_text, template_obj, raw_bundle))

    # 当前 UI控件模板写回依赖 raw_template（record 级 bundle）。当项目存档仅存在“高层模板 JSON”
    #（例如 HTML 导入/手工创建）而缺少 raw_bundle 时，不应对 base .gil 做 payload 重编码：
    # - 重编码会导致与真源 bytes 不一致，且在部分样本上会导入失败
    # - 本段语义应为“无变化”：保持 base .gil 不变
    if not raw_templates:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, output_path)
        return {
            "project_archive": str(project_path),
            "input_gil": str(input_path),
            "output_gil": str(output_path),
            "mode": mode,
            "templates_total": int(len(template_files)),
            "templates_added": [],
            "templates_overwritten": [],
            "templates_skipped_existing": [],
            "templates_skipped_invalid_files": templates_skipped_invalid_files,
            "templates_skipped_missing_raw": templates_skipped_missing_raw,
            "child_guid_remaps": {},
            "no_changes": True,
        }

    raw_dump_object = dump_gil_to_raw_json_object(input_path)
    payload_root = get_payload_root(raw_dump_object)

    node9 = _ensure_path_dict(payload_root, "9")
    ui_record_list = _ensure_path_list_allow_scalar(node9, "502")

    existing_index_by_guid: Dict[int, int] = {}
    existing_guids: set[int] = set()
    for index, record in enumerate(ui_record_list):
        if not isinstance(record, dict):
            continue
        guid = _extract_primary_guid(record)
        if guid is None:
            continue
        existing_index_by_guid[int(guid)] = int(index)
        existing_guids.add(int(guid))

    layout_registry_guids, list501 = _ensure_layout_registry_blob(node9)

    templates_added: List[str] = []
    templates_overwritten: List[str] = []
    templates_skipped_existing: List[str] = []
    child_guid_remaps: Dict[str, Dict[str, int]] = {}

    reserved_guids: set[int] = set(existing_guids)
    next_guid_candidate = (max(reserved_guids) + 1) if reserved_guids else 1

    def _allocate_new_guid() -> int:
        nonlocal next_guid_candidate
        candidate = int(next_guid_candidate)
        while candidate in reserved_guids:
            candidate += 1
        reserved_guids.add(int(candidate))
        next_guid_candidate = int(candidate) + 1
        return int(candidate)

    for template_id_text, template_obj, raw_bundle in raw_templates:
        root_record_obj = raw_bundle.get("template_root_record")
        child_records_obj = raw_bundle.get("child_records")
        if not isinstance(root_record_obj, dict) or not isinstance(child_records_obj, list):
            templates_skipped_missing_raw.append(template_id_text)
            continue

        root_record = copy.deepcopy(root_record_obj)
        child_records: List[Dict[str, Any]] = [copy.deepcopy(r) for r in child_records_obj if isinstance(r, dict)]

        # 可选：按 template JSON 的 widgets/settings 对 raw_template 进行增量写回（当前覆盖：道具展示）。
        widgets_obj = template_obj.get("widgets")
        if isinstance(widgets_obj, list) and widgets_obj:
            from ugc_file_tools.ui_patchers.web_ui.web_ui_import import (
                find_item_display_blob,
                patch_item_display_blob_bytes,
                write_item_display_blob_back_to_record,
            )

            guid_to_record_local: Dict[int, Dict[str, Any]] = {}
            for r in [root_record, *child_records]:
                if not isinstance(r, dict):
                    continue
                g = _extract_primary_guid(r)
                if isinstance(g, int):
                    guid_to_record_local[int(g)] = r

            for widget in widgets_obj:
                if not isinstance(widget, dict):
                    continue
                widget_type = str(widget.get("widget_type") or "").strip()
                if widget_type != "道具展示":
                    continue

                guid_hint = widget.get("__ugc_guid_int")
                if not isinstance(guid_hint, int):
                    # 仅对“来自 DLL dump 导出的模板（带 guid 回溯字段）”做增量写回；
                    # HTML 导入/手工创建的模板通常没有 guid，可由其它链路（web import）生成。
                    continue

                target_record = guid_to_record_local.get(int(guid_hint))
                if target_record is None:
                    raise RuntimeError(f"UI控件模板 {template_id_text} 的 widgets 引用 guid={int(guid_hint)}，但 raw_template 中未找到对应 record")

                settings = widget.get("settings")
                if not isinstance(settings, dict):
                    settings = {}
                display_type = str(settings.get("display_type") or "").strip() or "玩家当前装备"

                hit = find_item_display_blob(target_record)
                if hit is None:
                    raise RuntimeError(
                        f"UI控件模板 {template_id_text} 的 record guid={int(guid_hint)} 未找到可识别的 道具展示 blob"
                    )
                binding_path, blob_bytes = hit
                patched_blob = patch_item_display_blob_bytes(
                    blob_bytes=blob_bytes,
                    display_type=display_type,
                    settings=settings,
                )
                write_item_display_blob_back_to_record(
                    target_record,
                    binding_path=binding_path,
                    new_blob_bytes=patched_blob,
                )

        root_guid = _extract_primary_guid(root_record)
        if root_guid is None:
            templates_skipped_missing_raw.append(template_id_text)
            continue
        root_guid = int(root_guid)

        root_exists = root_guid in existing_index_by_guid
        if mode == "merge" and root_exists:
            templates_skipped_existing.append(template_id_text)
            continue

        # === children guid 冲突处理（当 root 不存在时尽量避免覆盖无关 record） ===
        child_guid_map: Dict[int, int] = {}
        root_children = _extract_children_guids_from_record(root_record)
        if not root_children:
            # 兜底：使用 raw_bundle 提供的 children_guids
            bundle_children = raw_bundle.get("children_guids")
            if isinstance(bundle_children, list):
                root_children = [int(v) for v in bundle_children if isinstance(v, int)]

        if not root_exists:
            # 先将“将要保留/写入的 guid”加入 reserved，避免 allocate 时撞到同 bundle 内的其他 child guid。
            incoming_child_guids: set[int] = set(int(v) for v in root_children)
            for child_record in child_records:
                child_guid = _extract_primary_guid(child_record)
                if child_guid is None:
                    continue
                incoming_child_guids.add(int(child_guid))
            reserved_guids.add(int(root_guid))
            reserved_guids.update(incoming_child_guids)

            # merge/overwrite 的“新增模板”场景：如 children guid 发生冲突，则为冲突项分配新 guid
            for child_record in child_records:
                child_guid = _extract_primary_guid(child_record)
                if child_guid is None:
                    continue
                child_guid = int(child_guid)
                if child_guid in existing_guids or child_guid in child_guid_map:
                    new_guid = _allocate_new_guid()
                    child_guid_map[int(child_guid)] = int(new_guid)
                    _set_primary_guid(child_record, int(new_guid))
                # 统一 parent 指向 root（即使 child guid 被重映射）
                child_record["504"] = int(root_guid)

            if child_guid_map:
                mapped_children = [int(child_guid_map.get(int(g), int(g))) for g in root_children]
                _set_children_guids_to_parent_record(root_record, mapped_children)
                child_guid_remaps[template_id_text] = {str(k): int(v) for k, v in sorted(child_guid_map.items())}
        else:
            # overwrite root 时：按 guid 直接覆盖 children（不做重映射），并强制 parent 指向 root
            for child_record in child_records:
                child_record["504"] = int(root_guid)

        # === layout registry：注册模板 root（插到开头；若已存在则不重复） ===
        if root_guid not in layout_registry_guids:
            layout_registry_guids.insert(0, int(root_guid))

        # === 写回 record_list ===
        if root_exists:
            # overwrite：替换 root record
            ui_record_list[int(existing_index_by_guid[int(root_guid)])] = root_record
            templates_overwritten.append(template_id_text)
        else:
            # 新增：追加到 record_list 末尾（避免打乱既有索引；写回语义以 guid 引用为准）
            insert_index = len(ui_record_list)
            ui_record_list.extend([root_record, *child_records])
            templates_added.append(template_id_text)
            existing_index_by_guid[int(root_guid)] = int(insert_index)
            existing_guids.add(int(root_guid))
            reserved_guids.add(int(root_guid))
            for offset, child_record in enumerate(child_records, start=1):
                child_guid = _extract_primary_guid(child_record)
                if child_guid is None:
                    continue
                child_guid = int(child_guid)
                existing_index_by_guid[int(child_guid)] = int(insert_index + offset)
                existing_guids.add(int(child_guid))
                reserved_guids.add(int(child_guid))

        # children：overwrite 模式下若 root 已存在，则按 guid 覆盖；否则已插入
        if root_exists:
            for child_record in child_records:
                child_guid = _extract_primary_guid(child_record)
                if child_guid is None:
                    continue
                child_guid = int(child_guid)
                existing_index = existing_index_by_guid.get(int(child_guid))
                if existing_index is None:
                    ui_record_list.append(child_record)
                    existing_index_by_guid[int(child_guid)] = len(ui_record_list) - 1
                    existing_guids.add(int(child_guid))
                    reserved_guids.add(int(child_guid))
                    continue
                ui_record_list[int(existing_index)] = child_record

    changed = bool(templates_added or templates_overwritten or child_guid_remaps)
    if not changed:
        # 无实质变化：保持 base .gil 不变（避免 payload 重编码导致导入失败）
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, output_path)
        return {
            "project_archive": str(project_path),
            "input_gil": str(input_path),
            "output_gil": str(output_path),
            "mode": mode,
            "templates_total": int(len(template_files)),
            "templates_added": templates_added,
            "templates_overwritten": templates_overwritten,
            "templates_skipped_existing": templates_skipped_existing,
            "templates_skipped_invalid_files": templates_skipped_invalid_files,
            "templates_skipped_missing_raw": templates_skipped_missing_raw,
            "child_guid_remaps": child_guid_remaps,
            "no_changes": True,
        }

    # 写回 layout registry blob
    if not list501:
        list501.append(format_binary_data_hex_text(b""))
    list501[0] = format_binary_data_hex_text(_encode_varint_stream([int(v) for v in layout_registry_guids]))

    payload_bytes = encode_message(payload_root)
    container_spec = read_gil_container_spec(input_path)
    output_bytes = build_gil_file_bytes_from_payload(payload_bytes=payload_bytes, container_spec=container_spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_bytes)

    return {
        "project_archive": str(project_path),
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "mode": mode,
        "templates_total": len(template_files),
        "templates_added": templates_added,
        "templates_overwritten": templates_overwritten,
        "templates_skipped_existing": templates_skipped_existing,
        "templates_skipped_invalid_files": templates_skipped_invalid_files,
        "templates_skipped_missing_raw": templates_skipped_missing_raw,
        "child_guid_remaps": child_guid_remaps,
    }


__all__ = ["UIWidgetTemplatesImportOptions", "import_ui_widget_templates_from_project_archive_to_gil"]


