from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .file_io import _ensure_directory, _write_json_file
from .generic_decode import _extract_field_501_named_message_records, _extract_utf8_texts_from_generic_decoded
from .models import DataBlobRecord


def _export_generic_decoded_indexes_from_data_blobs(
    *,
    output_package_root: Path,
    data_blob_index: List[DataBlobRecord],
    generic_scan_min_bytes: int,
    saved_full_min_bytes: int,
) -> None:
    """
    对 data blob 做“通用 protobuf”方式解码，生成：
    - decoded_generic/index.json：保存过完整解码 JSON 的记录索引
    - decoded_generic/keyword_hits_index.json：关键字命中汇总（便于定位）
    - decoded_generic/utf8_index.json：utf8 文本频次索引
    - 原始解析/关卡变量/解析_*：疑似变量名与 field_501 命名记录（避免污染 Graph_Generater 的资源目录）
    """
    decoded_generic_directory = output_package_root / "原始解析" / "数据块" / "decoded_generic"
    keyword_hits_directory = decoded_generic_directory / "keyword_hits"
    analysis_directory = output_package_root / "原始解析" / "关卡变量"
    _ensure_directory(decoded_generic_directory)
    _ensure_directory(keyword_hits_directory)
    _ensure_directory(analysis_directory)

    generic_decode_index: List[Dict[str, Any]] = []
    all_generic_utf8_records: List[Dict[str, Any]] = []
    all_field_501_named_records: List[Dict[str, Any]] = []
    keyword_hit_map: Dict[str, Dict[str, Any]] = {}
    keywords = [
        "节点图",
        "关卡实体",
        "实体",
        "自定义变量",
        "变量",
        "结构体",
        "技能",
        "职业",
        "道具",
        "元件",
    ]

    for record in data_blob_index:
        blob_path = output_package_root / "原始解析" / "数据块" / f"{record.file_stem}.bin"
        blob_bytes = blob_path.read_bytes()
        if len(blob_bytes) < generic_scan_min_bytes:
            continue

        decoded_generic = decode_bytes_to_python(blob_bytes)
        utf8_records_for_blob = _extract_utf8_texts_from_generic_decoded(decoded_generic)

        matched_keywords: List[str] = []
        matched_text_samples: List[str] = []
        for utf8_record in utf8_records_for_blob:
            text_value = utf8_record.get("text")
            if not isinstance(text_value, str):
                continue
            for keyword in keywords:
                if keyword in text_value:
                    if keyword not in matched_keywords:
                        matched_keywords.append(keyword)
                    if len(matched_text_samples) < 10 and text_value not in matched_text_samples:
                        matched_text_samples.append(text_value)

        # 仅对“足够大”的块落盘完整通用解码 JSON（避免生成成千上万文件）
        if len(blob_bytes) >= saved_full_min_bytes:
            output_path = decoded_generic_directory / f"{record.file_stem}.json"
            _write_json_file(output_path, decoded_generic)
            generic_decode_index.append(
                {
                    "file_stem": record.file_stem,
                    "byte_size": record.byte_size,
                    "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
                }
            )

        # 如果命中关键字，则额外落盘一份（便于快速定位）
        if matched_keywords:
            keyword_output_path = keyword_hits_directory / f"{record.file_stem}.json"
            _write_json_file(keyword_output_path, decoded_generic)
            existing_hit = keyword_hit_map.get(record.file_stem)
            if existing_hit is None:
                existing_hit = {
                    "file_stem": record.file_stem,
                    "byte_size": record.byte_size,
                    "matched_keywords": [],
                    "sample_texts": [],
                    "output": str(keyword_output_path.relative_to(output_package_root)).replace("\\", "/"),
                }
                keyword_hit_map[record.file_stem] = existing_hit
            for keyword in matched_keywords:
                if keyword not in existing_hit["matched_keywords"]:
                    existing_hit["matched_keywords"].append(keyword)
            for sample_text in matched_text_samples:
                if len(existing_hit["sample_texts"]) >= 10:
                    break
                if sample_text not in existing_hit["sample_texts"]:
                    existing_hit["sample_texts"].append(sample_text)

        for utf8_record in utf8_records_for_blob:
            all_generic_utf8_records.append(
                {
                    **utf8_record,
                    "source_blob": record.file_stem,
                }
            )

        for named_record in _extract_field_501_named_message_records(decoded_generic):
            all_field_501_named_records.append(
                {
                    **named_record,
                    "source_blob": record.file_stem,
                }
            )

    _write_json_file(decoded_generic_directory / "index.json", generic_decode_index)

    keyword_hits = sorted(keyword_hit_map.values(), key=lambda item: int(item.get("byte_size", 0)), reverse=True)
    _write_json_file(decoded_generic_directory / "keyword_hits_index.json", keyword_hits)

    # 通用解码的 utf8 文本索引（便于人工搜索“变量/实体/节点图”等关键字）
    utf8_count_map: Dict[str, Dict[str, Any]] = {}
    for record in all_generic_utf8_records:
        text = record.get("text")
        if not isinstance(text, str):
            continue
        existing = utf8_count_map.get(text)
        if existing is None:
            existing = {"count": 0, "samples": []}
            utf8_count_map[text] = existing
        existing["count"] += 1
        if len(existing["samples"]) < 20:
            existing["samples"].append(
                {
                    "source_blob": record.get("source_blob"),
                    "path": record.get("path"),
                }
            )
    sorted_utf8_index = sorted(utf8_count_map.items(), key=lambda item: int(item[1]["count"]), reverse=True)
    _write_json_file(
        decoded_generic_directory / "utf8_index.json",
        [{"text": text, **meta} for text, meta in sorted_utf8_index],
    )

    # field_501 命名记录（疑似“变量/命名条目”）：按前缀分组并输出到 关卡变量 目录，便于直接查阅
    variable_like_names: List[str] = []
    variable_group_map: Dict[str, List[str]] = {}
    for named_record in all_field_501_named_records:
        name_value = named_record.get("name")
        if not isinstance(name_value, str):
            continue
        if "_" not in name_value and "变量" not in name_value:
            continue
        variable_like_names.append(name_value)
        prefix = name_value.split("_", 1)[0] if "_" in name_value else "其他"
        group_list = variable_group_map.get(prefix)
        if group_list is None:
            group_list = []
            variable_group_map[prefix] = group_list
        if name_value not in group_list:
            group_list.append(name_value)

    variable_like_names = sorted(set(variable_like_names))
    for prefix, group_list in variable_group_map.items():
        variable_group_map[prefix] = sorted(set(group_list))

    _write_json_file(analysis_directory / "解析_疑似变量名.json", variable_like_names)
    _write_json_file(
        analysis_directory / "解析_疑似变量名_按前缀.json",
        dict(sorted(variable_group_map.items(), key=lambda item: item[0])),
    )
    _write_json_file(analysis_directory / "解析_field501_命名记录.json", all_field_501_named_records)


