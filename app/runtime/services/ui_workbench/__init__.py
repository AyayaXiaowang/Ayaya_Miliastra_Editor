from __future__ import annotations

from .base_gil_cache import (
    get_ui_workbench_cache_dir,
    load_base_gil_cache,
    save_base_gil_cache,
)
from .naming import collect_existing_names, ensure_unique_name, generate_unique_id
from .types import ImportBundleResult, ImportResult
from .ui_catalog_api import build_ui_catalog_payload, get_ui_layout_payload, get_ui_template_payload
from .ui_import_api import (
    UniqueIdGenerator,
    UniqueNameEnsurer,
    ensure_builtin_widget_templates,
    ensure_management_ui_dicts,
    import_layout_from_bundle_payload,
    import_layout_from_template_payload,
)
from .ui_source_api import (
    build_ui_source_catalog_payload,
    get_project_ui_source_dir,
    get_shared_ui_source_dir,
    read_ui_source_payload,
    resolve_ui_source_path,
)
from .utils import (
    crc32_hex,
    decode_utf8_b64,
    encode_utf8_b64,
    list_html_files,
    read_json,
    write_json,
)
from .variable_defaults import (
    ImportedVariable,
    discover_player_templates,
    extract_import_items,
    get_player_custom_variable_file_ids_from_template,
    infer_variable_type_and_default,
    set_player_custom_variable_file_ids,
    try_attach_ps_variable_file_to_player_templates,
    variable_id_for,
    write_level_variable_file,
)

__all__ = [
    "UniqueIdGenerator",
    "UniqueNameEnsurer",
    "ImportBundleResult",
    "ImportResult",
    "ImportedVariable",
    "build_ui_catalog_payload",
    "build_ui_source_catalog_payload",
    "collect_existing_names",
    "crc32_hex",
    "decode_utf8_b64",
    "discover_player_templates",
    "encode_utf8_b64",
    "ensure_builtin_widget_templates",
    "ensure_management_ui_dicts",
    "ensure_unique_name",
    "extract_import_items",
    "generate_unique_id",
    "get_player_custom_variable_file_ids_from_template",
    "get_project_ui_source_dir",
    "get_shared_ui_source_dir",
    "get_ui_layout_payload",
    "get_ui_template_payload",
    "get_ui_workbench_cache_dir",
    "import_layout_from_bundle_payload",
    "import_layout_from_template_payload",
    "list_html_files",
    "load_base_gil_cache",
    "infer_variable_type_and_default",
    "read_json",
    "read_ui_source_payload",
    "resolve_ui_source_path",
    "set_player_custom_variable_file_ids",
    "save_base_gil_cache",
    "try_attach_ps_variable_file_to_player_templates",
    "variable_id_for",
    "write_json",
    "write_level_variable_file",
]

