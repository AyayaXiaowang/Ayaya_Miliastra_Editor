from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

ProgressCallback = Callable[[int, int, str], None]


def _emit_progress(cb: ProgressCallback | None, current: int, total: int, label: str) -> None:
    if cb is None:
        return
    cb(int(current), int(total), str(label or ""))


@dataclass(frozen=True, slots=True)
class ProjectExportGiaPlan:
    """
    项目存档 → 导出 `.gia`（当前阶段：节点图 .gia）。

    说明：
    - `.gia` 导出是“只导出资产”的链路，不会修改 `.gil`；
    - 输出文件会强制落盘到 `ugc_file_tools/out/` 下（允许子目录），
      若用户提供了 out 外的绝对目录，则会额外复制一份过去。
    """

    project_archive_path: Path
    graphs_scope: str = "all"  # "all" | "server" | "client"
    graph_scan_all: bool = True
    # 可选：仅导出指定 graph_key（Graph_Generater 的 graph_id 字符串）
    graph_keys: list[str] | None = None
    # 可选：显式指定要导出的节点图源码文件（支持 project/shared 混选）。若提供则忽略 scan_all/overview。
    graph_code_files: list[Path] | None = None
    # 可选：用于“分配 graph_id_int 的全量扫描根”（默认仅 project_archive_path）。
    # 设计目的：当显式导出子集时，仍按“全量图集合”稳定分配 graph_id_int，避免子集导出时 id 漂移。
    graph_source_roots: list[Path] | None = None

    node_type_semantic_map_json: Path | None = None
    output_dir_name_in_out: str = ""  # 默认 <package_id>_gia_export
    output_user_dir: Path | None = None  # 绝对目录：额外复制一份过去
    node_pos_scale: float = 2.0  # 导出节点图 `.gia` 时对 x/y 同步乘法缩放（展示用，不影响逻辑）
    allow_unresolved_ui_keys: bool = False  # 允许 ui_key: 占位符缺映射时回填为 0 并继续导出
    # 可选：选择一条“UI 导出记录”（用于 ui_key: 占位符回填）。
    # 默认空：优先自动选择最新记录；若不存在记录则无法回填（除非 allow_unresolved_ui_keys=True）。
    ui_export_record_id: str | None = None
    # 可选：基底存档（.gil），用于在导出 .gia 时解析“信号定义表”，避免信号节点导入后串号
    base_gil_for_signal_defs: Path | None = None
    # 可选：参考 `.gil` 文件，用于回填节点图中的占位符 ID：
    # - entity_key:<实体名> / entity:<实体名>
    # - component_key:<元件名> / component:<元件名>
    id_ref_gil_file: Path | None = None
    # 可选：手动覆盖 entity_key/component_key 的映射（JSON 文件；占位符 name → ID）。
    id_ref_overrides_json_file: Path | None = None

    # bundle 导出：将图与必要配置打到同一目录，便于分发/导入
    bundle_enabled: bool = False
    bundle_include_signals: bool = True  # 拷贝 <项目存档>/管理配置/信号
    bundle_include_ui_guid_registry: bool = True  # 拷贝 UIKey→GUID 映射（优先运行时缓存 ui_guid_registry.json）

    # pack 导出：将多张节点图合并到同一个 `.gia`（Root.field_1 为 GraphUnit 列表）。
    # 说明：
    # - 该模式用于解决“多张图分别导出后一起导入会出现 信号_1/信号_2 等串号/占位名”的问题；
    # - 由于信号 node_def 的 signal_index/node_def_id/port_index 需要跨图一致，pack 模式会先收集全量用到的信号，
    #   构建一次“共享自包含信号 bundle”，再用于所有图的导出。
    pack_graphs_to_single_gia: bool = False
    pack_output_gia_file_name: str = ""  # 仅文件名（例如 打包一起.gia），实际输出到 out/<dir>/graphs/ 下

    # 可选：导出后直接注入到某个 .gil（文件级 patch；用于“导出后立即在真源地图里生效”）
    inject_target_gil_file: Path | None = None
    inject_check_gia_header: bool = False
    inject_skip_non_empty_check: bool = False
    inject_create_backup: bool = True

