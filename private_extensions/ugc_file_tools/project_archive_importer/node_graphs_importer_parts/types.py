from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NodeGraphsImportOptions:
    scope: str = "all"  # "all" | "server" | "client"
    scan_all: bool = True
    strict_graph_code_files: bool = False
    output_model_dir_name: str = ""  # 默认 <package_id>_graph_models
    # 可选：显式指定要写回的节点图源码文件（允许 project/shared 混选）。若提供则忽略 scan_all/overview。
    graph_code_files: list[Path] | None = None
    # 可选：用于“分配 graph_id_int 的全量扫描根”（默认仅 project_archive_path）。
    graph_source_roots: list[Path] | None = None
    # 可选：同名节点图冲突策略（导出中心交互用；按 graph_code_file 精确匹配）。
    # item schema（dict）：
    # - graph_code_file: str（绝对路径）
    # - action: "overwrite" | "add" | "skip"
    # - new_graph_name: str（仅 action="add" 时需要；写回输出将使用该新名字）
    node_graph_conflict_resolutions: list[dict[str, str]] | None = None
    # 可选：节点图写回时使用指定 UI 导出记录的 registry 快照（record_id 或 latest）。
    ui_export_record_id: str | None = None
    # 可选：同次“UI+节点图写回”时由 UI 写回阶段提供的映射表（不落盘 registry）。
    ui_key_to_guid_for_writeback: dict[str, int] | None = None
    # 可选：参考 `.gil` 文件，用于回填节点图中的 entity_key/component_key 占位符（按名称匹配，取第一个）。
    # 若不提供，则默认使用 input_gil_file_path 作为参考。
    id_ref_gil_file: Path | None = None
    # 可选：entity_key/component_key 占位符手动覆盖映射 JSON（占位符 name → ID）。
    id_ref_overrides_json_file: Path | None = None
    # 可选策略（默认 False）：在满足“静态信号绑定 + base `.gil` 映射可用”时，
    # 将信号节点 type_id 从 generic runtime（300000/300001/300002）提升为 signal-specific runtime_id（常见 0x6000xxxx/0x6080xxxx；由 base `.gil` 的 node_def_id 0x4000xxxx/0x4080xxxx 推导）。
    prefer_signal_specific_type_id: bool = False

