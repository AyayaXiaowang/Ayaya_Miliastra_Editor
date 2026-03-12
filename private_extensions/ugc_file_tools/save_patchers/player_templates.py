from __future__ import annotations

"""
玩家模板写回：兼容层（旧 import 路径不变），实现拆分在 `_player_templates/`。
"""

from ._player_templates.common import (
    PlayerTemplateRef,
    _choose_template_name_from_strings,
    _collect_player_templates,
    _collect_strings,
    _enforce_no_overlap_or_raise,
    _looks_like_player_template_msg,
    _normalize_player_index_list,
    _parse_human_players,
    _players_to_human,
    _try_extract_players_from_template_msg,
    _walk,
)
from ._player_templates.io_ops import (
    dump_player_templates_report,
    find_bytes_fields_containing_pattern,
    find_text_paths,
    load_payload_root,
    write_back_payload,
)
from ._player_templates.structured_entries import (
    PlayerTemplateEntry,
    _decode_players_bytes,
    _extract_name_from_entry_meta_list,
    _extract_players_bytes_from_entry_meta_list,
    _find_root4_entry_index_by_id,
    _find_root5_entry_index_by_name,
    _get_root4_entries,
    _get_root5_entries,
    _is_player_template_like_root5_entry,
    _iter_root5_indices_by_ref_id,
    list_player_templates,
    set_template_players_inplace,
)
from ._player_templates.structured_variables import (
    _build_player_template_custom_variable_def_item,
    _extract_group1_variable_def_items,
    _extract_group1_variable_names,
    _find_player_template_entry_by_name,
    _replace_group1_var_defs_in_group_list,
    add_custom_variable_to_template_inplace,
    copy_template_custom_variable_defs_inplace,
    set_template_custom_variable_defs_inplace,
)
from ._player_templates.wire_helpers import (
    _build_group1_container_item_bytes,
    _extract_root5_ref_root4_entry_id,
    _extract_template_name_from_root5_entry_bytes,
    _is_group1_container_item_bytes,
    _is_player_template_like_root5_entry_bytes,
    _patch_group_list_field_in_entry_bytes,
    _patch_section_entries_field1_by_predicate,
    _read_single_length_delimited_payload_from_message_bytes,
    _read_single_varint_field_from_message_bytes,
)
from ._player_templates.wire_patchers import (
    extract_player_template_group1_container_item_bytes_from_gil,
    patch_player_template_custom_variable_defs_in_gil,
    patch_player_template_custom_variable_group1_item_bytes_in_gil,
)

