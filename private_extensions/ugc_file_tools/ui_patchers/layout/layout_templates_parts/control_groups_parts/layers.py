from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ugc_file_tools.output_paths import resolve_output_file_path_in_out_dir
from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ..shared import (
    _dump_gil_to_raw_json_object,
    _find_record_by_guid,
    _set_rect_transform_layer,
    _try_extract_rect_transform_layer,
    _write_back_modified_gil_by_reencoding_payload,
)


def set_control_rect_transform_layers(
    *,
    input_gil_file_path: Path,
    output_gil_file_path: Path,
    layers_by_guid: Dict[int, int],
    verify_with_dll_dump: bool = True,
) -> Dict[str, Any]:
    """
    设置 UI 控件的“层级”字段（样本：`505[2]/503/13/12/503`）。

    备注：该字段在样本中缺失表示默认；写入后会在 dump-json 中出现。
    """
    input_path = Path(input_gil_file_path).resolve()
    output_path = resolve_output_file_path_in_out_dir(Path(output_gil_file_path))
    if not input_path.is_file():
        raise FileNotFoundError(str(input_path))

    if not isinstance(layers_by_guid, dict) or not layers_by_guid:
        raise ValueError("layers_by_guid 不能为空")

    normalized: Dict[int, int] = {}
    for guid, layer in layers_by_guid.items():
        g = int(guid)
        l = int(layer)
        normalized[g] = l

    raw_dump_object = _dump_gil_to_raw_json_object(input_path)
    ui_record_list = _extract_ui_record_list(raw_dump_object)

    for guid, layer in normalized.items():
        record = _find_record_by_guid(ui_record_list, int(guid))
        if record is None:
            raise RuntimeError(f"未找到 guid={int(guid)} 对应的 UI record。")
        _set_rect_transform_layer(record, int(layer))

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_path,
        output_gil_path=output_path,
    )

    report: Dict[str, Any] = {
        "input_gil": str(input_path),
        "output_gil": str(output_path),
        "updated_total": len(normalized),
        "updated": [{"guid": int(g), "layer": int(l)} for g, l in sorted(normalized.items())],
    }

    if verify_with_dll_dump:
        verify_dump = _dump_gil_to_raw_json_object(output_path)
        verify_ui_records = _extract_ui_record_list(verify_dump)
        ok = True
        for guid, layer in normalized.items():
            record = _find_record_by_guid(verify_ui_records, int(guid))
            if record is None:
                ok = False
                continue
            extracted = _try_extract_rect_transform_layer(record)
            if extracted is None or int(extracted) != int(layer):
                ok = False
        report["verify"] = {"ok": ok}

    return report


__all__ = ["set_control_rect_transform_layers"]

