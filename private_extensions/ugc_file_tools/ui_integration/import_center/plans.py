from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


IMPORT_TASK_GIL_FULL = "gil_full"
IMPORT_TASK_GIL_SELECTED = "gil_selected"
IMPORT_TASK_GIA = "gia"

IMPORT_TASKS = (IMPORT_TASK_GIL_FULL, IMPORT_TASK_GIL_SELECTED, IMPORT_TASK_GIA)


@dataclass(frozen=True, slots=True)
class ImportGilPlan:
    """描述 `.gil` 导入为项目存档的执行参数。"""

    input_gil_path: Path
    package_id: str
    output_package_root: Path
    overwrite_existing: bool
    enable_dll_dump: bool
    generate_graph_code: bool
    validate_after_generate: bool


@dataclass(frozen=True, slots=True)
class ImportGilSelectedPlan:
    """描述“选择性 `.gil` 导入”的执行参数。"""

    input_gil_path: Path
    package_id: str
    output_package_root: Path
    overwrite_existing: bool

    export_raw_pyugc_dump: bool
    export_node_graphs: bool
    export_templates: bool
    export_instances: bool
    export_combat_presets: bool
    export_section15: bool
    export_struct_definitions: bool
    export_signals: bool
    export_data_blobs: bool
    export_decoded_dtype_type3: bool
    export_decoded_generic: bool

    selected_node_graph_id_ints: list[int]

    enable_dll_dump: bool
    generate_graph_code: bool
    validate_after_generate: bool


@dataclass(frozen=True, slots=True)
class ImportGiaPlan:
    """描述 `.gia` 导入到项目存档的执行参数。"""

    input_gia_path: Path
    import_kind: str
    package_id: str
    output_package_root: Path
    overwrite_existing: bool
    import_templates: bool
    import_instances: bool
    instances_mode: str
    decode_max_depth: int
    validate_after_import: bool

