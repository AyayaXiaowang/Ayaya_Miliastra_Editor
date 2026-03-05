from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class _ExportGiaPlan:
    package_id: str
    project_root: Path
    graph_selection: object  # GraphSelection（避免顶层 import）
    template_json_files: list[Path]
    player_template_json_files: list[Path]
    selected_signal_ids: list[str]
    selected_basic_struct_ids: list[str]
    selected_ingame_struct_ids: list[str]
    output_dir_name_in_out: str
    output_user_dir: Path | None
    node_pos_scale: float
    allow_unresolved_ui_keys: bool
    ui_export_record_id: str | None
    id_ref_gil_file: Path | None
    bundle_enabled: bool
    bundle_include_signals: bool
    bundle_include_ui_guid_registry: bool
    pack_graphs_to_single_gia: bool
    pack_output_gia_file_name: str
    base_template_gia_file: Path | None
    base_player_template_gia_file: Path | None
    template_base_decode_max_depth: int
    player_template_base_decode_max_depth: int
    # 可选：手动覆盖 entity_key/component_key 的映射（占位符 name → ID）。
    # 说明：用于“识别时查不到 ID → 用户手动从地图/参考 GIL 选择一个”场景。
    id_ref_override_component_name_to_id: dict[str, int] = field(default_factory=dict)
    id_ref_override_entity_name_to_guid: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _ExportGilPlan:
    package_id: str
    project_root: Path
    input_gil_path: Path
    use_builtin_empty_base: bool
    output_user_path: Path
    struct_mode: str
    templates_mode: str
    instances_mode: str
    signals_param_build_mode: str
    prefer_signal_specific_type_id: bool
    ui_widget_templates_mode: str
    write_ui: bool
    ui_auto_sync_custom_variables: bool
    # 用户在导出中心左侧勾选的 UI源码（HTML）文件（仅 project scope；用于导出前 bundle 自动更新与冲突检查口径）。
    selected_ui_html_files: list[Path]
    # 导出前自动更新：需要从 UI源码 HTML 重新生成 Workbench bundle（写入 UI源码/__workbench_out__/）。
    # 为空表示不更新（或无需更新）。
    ui_workbench_bundle_update_html_files: list[Path]
    # UI Workbench bundle（UI源码/__workbench_out__/*.ui_bundle.json）写回时的“同名布局冲突策略”
    # item schema（dict）：
    # - layout_name: str
    # - action: "overwrite" | "add" | "skip"
    # - new_layout_name: str（仅 action="add" 时需要）
    ui_layout_conflict_resolutions: list[dict[str, str]]
    # 节点图写回时的“同名节点图冲突策略”（导出中心交互用；按 graph_code_file 精确匹配）。
    # item schema（dict）：
    # - graph_code_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_graph_name: str（仅 action="add" 时需要；写回输出将使用该新名字）
    node_graph_conflict_resolutions: list[dict[str, str]]
    # 元件库模板写回时的“同名模板冲突策略”（导出中心交互用；按 template_json_file 精确匹配）。
    # item schema（dict）：
    # - template_json_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_template_name: str（仅 action="add" 时需要；写回输出将使用该新名字）
    template_conflict_resolutions: list[dict[str, str]]
    # 实体摆放写回时的“同名实体冲突策略”（导出中心交互用；按 instance_json_file 精确匹配）。
    # item schema（dict）：
    # - instance_json_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_instance_name: str（仅 action="add" 时需要；写回输出将使用该新名字）
    instance_conflict_resolutions: list[dict[str, str]]
    # 自定义变量（注册表）：按 owner_ref+variable_id 精确选择（可跨：关卡实体/玩家/第三方 owner）。
    # - selection-json 仅携带该选择集合；写回阶段再按注册表查表并写入对应条目的 override_variables(group1)。
    selected_custom_variable_refs: list[dict[str, str]]
    # 关卡实体（root4/5/1 name=关卡实体）需要补齐写入的关卡变量（LevelVariableDefinition.variable_id）列表。
    selected_level_custom_variable_ids: list[str]
    selected_template_json_files: list[Path]
    selected_instance_json_files: list[Path]
    selected_graph_code_files: list[Path]
    selected_struct_ids: list[str]
    selected_ingame_struct_ids: list[str]
    selected_signal_ids: list[str]
    graph_source_roots: list[Path]
    ui_export_record_id: str | None
    id_ref_gil_file: Path | None
    # 可选：手动覆盖 entity_key/component_key 的映射（占位符 name → ID）。
    # 说明：用于“识别时查不到 ID → 用户手动从地图/参考 GIL 选择一个”场景。
    id_ref_override_component_name_to_id: dict[str, int] = field(default_factory=dict)
    id_ref_override_entity_name_to_guid: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _RepairSignalsPlan:
    package_id: str
    project_root: Path
    input_gil_path: Path
    output_gil_path: Path
    selected_graph_code_files: list[Path]
    graph_source_roots: list[Path]
    prune_placeholder_orphans: bool


@dataclass(frozen=True, slots=True)
class _MergeSignalEntriesPlan:
    package_id: str
    project_root: Path
    input_gil_path: Path
    output_gil_path: Path
    keep_signal_name: str
    remove_signal_name: str
    rename_keep_to: str
    patch_composite_pin_index: bool

