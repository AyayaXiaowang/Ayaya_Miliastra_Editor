from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .file_io import _sanitize_filename, _write_json_file
from .pyugc_extractors import _extract_section15_entry_id_int, _extract_section15_entry_name
from .section15_decoders import _try_decode_section15_meta_data


def _export_currency_backpacks_from_section15_scan(
    *,
    currency_entries: List[Dict[str, Any]],
    backpack_entry: Optional[Tuple[int, Dict[str, Any]]],
    output_package_root: Path,
    package_namespace: str,
    currency_backpack_directory: Path,
    currency_backpack_raw_directory: Path,
) -> List[Dict[str, Any]]:
    """
    将 section15 中的货币(type_code=11)与背包(type_code=12)组合导出为 Graph_Generater 的“货币背包”配置。

    说明：
    - `currency_entries` 来自第一轮扫描的缓存（保留原始 entry 结构）。
    - `backpack_entry` 为 (entry_index, entry_object)。
    """
    exported_currency_backpacks: List[Dict[str, Any]] = []

    if backpack_entry is None:
        return exported_currency_backpacks

    backpack_entry_index, backpack_entry_object = backpack_entry
    backpack_id_int = _extract_section15_entry_id_int(backpack_entry_object)
    backpack_name = _extract_section15_entry_name(backpack_entry_object) or "默认背包"
    if backpack_id_int is None:
        return exported_currency_backpacks

    decoded_backpack = _try_decode_section15_meta_data(backpack_entry_object, 42, "55@data")
    raw_file_name = f"ugc_currency_backpack_{backpack_id_int}.pyugc.json"
    raw_file_path = currency_backpack_raw_directory / raw_file_name
    _write_json_file(raw_file_path, backpack_entry_object)

    decoded_file_path = currency_backpack_raw_directory / f"ugc_currency_backpack_{backpack_id_int}.decoded.json"
    _write_json_file(decoded_file_path, decoded_backpack)

    backpack_capacity_value = 0
    if isinstance(decoded_backpack, dict):
        field_1 = decoded_backpack.get("decoded", {}).get("field_1", {})
        if isinstance(field_1, dict):
            field_1_message = field_1.get("message")
            if isinstance(field_1_message, dict):
                possible_capacity = field_1_message.get("field_1", {}).get("int")
                if isinstance(possible_capacity, int):
                    backpack_capacity_value = int(possible_capacity)

    currencies_list: List[Dict[str, Any]] = []
    for currency_record in currency_entries:
        currency_name = str(currency_record.get("entry_name", "") or "")
        currency_entry_id_int = int(currency_record.get("entry_id_int"))
        currency_entry_object = currency_record.get("entry")
        if not isinstance(currency_entry_object, dict):
            continue

        currency_decoded = _try_decode_section15_meta_data(currency_entry_object, 41, "54@data")
        initial_amount_value = 0
        max_amount_value = 9999999
        if isinstance(currency_decoded, dict):
            decoded_root = currency_decoded.get("decoded")
            if isinstance(decoded_root, dict):
                field_1 = decoded_root.get("field_1")
                if isinstance(field_1, dict):
                    field_1_message = field_1.get("message")
                    if isinstance(field_1_message, dict):
                        possible_initial_amount = field_1_message.get("field_2", {}).get("int")
                        if isinstance(possible_initial_amount, int):
                            initial_amount_value = int(possible_initial_amount)

        currency_id_text = f"currency_{currency_entry_id_int}__{package_namespace}"
        if "金币" in currency_name:
            currency_id_text = f"gold__{package_namespace}"
        if "钻石" in currency_name:
            currency_id_text = f"diamond__{package_namespace}"
        currencies_list.append(
            {
                "currency_id": currency_id_text,
                "currency_name": currency_name,
                "icon": "",
                "initial_amount": int(initial_amount_value),
                "max_amount": int(max_amount_value),
                "description": "",
                "metadata": {
                    "ugc_source_entry_id_int": currency_entry_id_int,
                    "ugc_decoded": currency_decoded,
                },
            }
        )

        currency_raw_file_name = f"ugc_currency_{currency_entry_id_int}.pyugc.json"
        _write_json_file(currency_backpack_raw_directory / currency_raw_file_name, currency_entry_object)

    backpack_config_id = f"currency_backpack_{backpack_id_int}__{package_namespace}"
    backpack_object: Dict[str, Any] = {
        "config_id": backpack_config_id,
        "currencies": currencies_list,
        "backpack_capacity": backpack_capacity_value,
        "max_stack_size": 99,
        "initial_items": [],
        "description": "",
        "metadata": {
            "ugc": {
                "source_entry_id_int": backpack_id_int,
                "source_type_code": 12,
                "source_pyugc_path": f"4/15/1/[{backpack_entry_index}]",
                "raw_pyugc_entry": str(raw_file_path.relative_to(output_package_root)).replace("\\", "/"),
                "decoded": str(decoded_file_path.relative_to(output_package_root)).replace("\\", "/"),
            }
        },
        "updated_at": "",
        "name": backpack_name,
    }
    output_file_name = _sanitize_filename(f"{backpack_name}_{backpack_id_int}") + ".json"
    output_path = currency_backpack_directory / output_file_name
    _write_json_file(output_path, backpack_object)
    exported_currency_backpacks.append(
        {
            "config_id": backpack_config_id,
            "name": backpack_name,
            "output": str(output_path.relative_to(output_package_root)).replace("\\", "/"),
        }
    )

    return exported_currency_backpacks


