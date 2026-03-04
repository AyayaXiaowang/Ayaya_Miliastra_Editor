from __future__ import annotations

"""
writeback_defaults.py

收口“写回/导出 .gil”相关的默认路径，避免在 UI/CLI 中重复硬编码。

约定：
- 这些默认路径只作为“可用的默认候选”，并不保证一定存在；
- 调用方若需要强制存在，应自行做 is_file/is_dir 校验并抛错。
"""

from pathlib import Path

from ugc_file_tools.repo_paths import ugc_file_tools_builtin_resources_root, ugc_file_tools_root


def default_signal_template_gil_path() -> Path:
    """信号写回的默认模板 .gil（用于克隆 node_defs 样本）。"""
    return ugc_file_tools_builtin_resources_root() / "seeds" / "signal_node_def_templates.gil"


def default_struct_template_gil_hint_path() -> Path:
    """结构体写回的默认 base/提示 .gil（通常包含结构体系统模板样本）。"""
    return ugc_file_tools_builtin_resources_root() / "seeds" / "struct_def_exemplars.gil"


def default_ingame_save_structs_bootstrap_gil_path() -> Path:
    """局内存档结构体导入的自举模板 .gil（用于空壳存档补齐结构体系统基底）。"""
    return ugc_file_tools_builtin_resources_root() / "seeds" / "ingame_save_structs_bootstrap.gil"


def default_node_graph_server_template_gil_path() -> Path:
    return (
        ugc_file_tools_builtin_resources_root()
        / "template_library"
        / "test2_server_writeback_samples"
        / "autowire_templates_test2_server_direct_export_v2.gil"
    )


def default_node_graph_client_template_gil_path() -> Path:
    return (
        ugc_file_tools_builtin_resources_root()
        / "template_library"
        / "test2_client_writeback_samples"
        / "missing_nodes_wall_test2_client_autowired.gil"
    )


def default_node_graph_server_template_library_dir() -> Path:
    return ugc_file_tools_builtin_resources_root() / "template_library" / "test2_server_writeback_samples"


def default_node_graph_client_template_library_dir() -> Path:
    return ugc_file_tools_builtin_resources_root() / "template_library" / "test2_client_writeback_samples"


def default_node_graph_mapping_json_path() -> Path:
    return ugc_file_tools_root() / "graph_ir" / "node_type_semantic_map.json"


def default_gil_infrastructure_bootstrap_gil_path() -> Path:
    """
    `.gil` 写回时用于“补齐空壳 base 缺失基础设施段”的 bootstrap 模板。

    背景（样本差异已观测）：
    - 部分“空存档 base”会缺失 `root4/11` 的初始阵营互斥表（entries 缺 key=13），以及 `root4/35` 的默认分组列表；
    - 这些段缺失时，节点图/信号写回本身虽然能完成，但官方侧更严格校验可能失败。

    该模板用于在不覆盖 base 其它业务段（节点图/信号/模板/实体等）的前提下，按需从模板中复制缺失字段。
    """
    return ugc_file_tools_builtin_resources_root() / "seeds" / "infrastructure_bootstrap.gil"

