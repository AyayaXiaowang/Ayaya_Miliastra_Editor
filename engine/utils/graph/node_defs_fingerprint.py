from __future__ import annotations

from pathlib import Path


def compute_node_defs_fingerprint(workspace_path: Path) -> str:
    """
    计算节点定义库的轻量指纹，用于节点库与图缓存的失效判定。

    统一规则（与 NodeRegistry/GraphCacheManager 共用）：
    - 实现库：`plugins/nodes/`
    - 节点定义/加载核心：`engine/nodes/`
    - 图解析/生成核心：`engine/graph/`
    - 复合节点库：`assets/资源库/复合节点库/`

    指纹由各目录的「*.py 文件数量 + 最新修改时间」拼接而成，
    任一目录发生变动都会导致指纹变化，从而触发相关缓存失效。
    """
    # 1) 实现库：plugins/nodes
    plugins_dir = workspace_path / "plugins" / "nodes"
    plugins_count = 0
    plugins_latest = 0.0
    if plugins_dir.exists():
        for path in plugins_dir.rglob("*.py"):
            # 生成产物（如 registry.py）同样纳入指纹，确保重新生成后能及时失效缓存
            stat = path.stat()
            plugins_count += 1
            if stat.st_mtime > plugins_latest:
                plugins_latest = stat.st_mtime

    # 2) 节点定义/加载核心
    nodes_core_dir = workspace_path / "engine" / "nodes"
    nodes_count = 0
    nodes_latest = 0.0
    if nodes_core_dir.exists():
        for path in nodes_core_dir.rglob("*.py"):
            stat = path.stat()
            nodes_count += 1
            if stat.st_mtime > nodes_latest:
                nodes_latest = stat.st_mtime

    # 3) 图解析/生成核心
    graph_code_dir = workspace_path / "engine" / "graph"
    graph_code_count = 0
    graph_code_latest = 0.0
    if graph_code_dir.exists():
        for path in graph_code_dir.rglob("*.py"):
            stat = path.stat()
            graph_code_count += 1
            if stat.st_mtime > graph_code_latest:
                graph_code_latest = stat.st_mtime

    # 4) 复合节点库
    composites_dir = workspace_path / "assets" / "资源库" / "复合节点库"
    composites_count = 0
    composites_latest = 0.0
    if composites_dir.exists():
        for path in composites_dir.rglob("*.py"):
            stat = path.stat()
            composites_count += 1
            if stat.st_mtime > composites_latest:
                composites_latest = stat.st_mtime

    return (
        f"plugins:{plugins_count}:{round(plugins_latest, 3)}"
        f"|nodes:{nodes_count}:{round(nodes_latest, 3)}"
        f"|gc:{graph_code_count}:{round(graph_code_latest, 3)}"
        f"|composites:{composites_count}:{round(composites_latest, 3)}"
    )



