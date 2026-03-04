from __future__ import annotations

from .helpers import *  # noqa: F401,F403
from .helpers import __all__ as _HELPERS_ALL

from .preset_all_types_test import add_all_types_test_struct_definition
from .preset_clone_all_supported import clone_struct_all_supported_definition
from .preset_misc import add_empty_struct_definition, add_one_string_struct_definition, rename_struct_definition
from .gia_export import BasicStructPyRecord, ExportBasicStructsGiaPlan, collect_basic_struct_py_records, export_basic_structs_to_gia

__all__ = [
    "_dump_gil_to_raw_json_object",
    "_ensure_path_dict",
    "_ensure_path_list",
    "_ensure_path_list_allow_scalar",
    "_decode_struct_id_from_blob_bytes",
    "_try_decode_struct_id_from_blob_bytes",
    "_choose_next_struct_id",
    "_collect_reserved_struct_ids_from_payload_root",
    "_set_text_node_utf8",
    "_set_int_node",
    "_set_default_string_node",
    "_encode_varint",
    "_encode_packed_varints",
    "_encode_float32_list",
    "_get_utf8_from_text_node",
    "_get_struct_message_from_decoded_blob",
    "_iter_field_entries",
    "_decode_field_entry",
    "_commit_field_entry",
    "_find_field_message",
    "_get_type_value_container",
    "_set_default_bool_node",
    "_set_default_int_in_message_container",
    "_set_default_float_in_message_container",
    "_set_default_vector3_in_message_container",
    "_set_default_packed_varint_list",
    "_set_default_float_list",
    "_set_default_string_list_raw",
    "_set_default_dict_string_bool",
    "_collect_all_binary_data_texts",
    "_replace_binary_data_bytes_in_object",
    "_replace_int_values_in_object",
    "_sanitize_decoded_invalid_field0_message_nodes",
    "_ensure_struct_visible_in_tabs",
    "_find_template_struct_node_defs",
    "_extract_node_type_id_from_node_def",
    "_collect_existing_node_type_ids",
    "_collect_existing_struct_ref_ids",
    "_collect_existing_struct_internal_ids",
    "add_all_types_test_struct_definition",
    "clone_struct_all_supported_definition",
    "add_empty_struct_definition",
    "rename_struct_definition",
    "add_one_string_struct_definition",
    "ExportBasicStructsGiaPlan",
    "BasicStructPyRecord",
    "collect_basic_struct_py_records",
    "export_basic_structs_to_gia",
]
