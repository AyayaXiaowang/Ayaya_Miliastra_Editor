from __future__ import annotations

import hashlib
from pathlib import Path


def compute_node_defs_fingerprint(workspace_path: Path) -> str:
    """
    计算节点定义库的轻量指纹，用于节点库与图缓存的失效判定。

    统一规则（与 NodeRegistry/PersistentGraphCacheManager 共用）：
    - 实现库：`plugins/nodes/`
    - 节点定义/加载核心：`engine/nodes/`
    - 图解析/生成核心：`engine/graph/`
    - 复合节点库：`assets/资源库/复合节点库/`

    指纹由各目录的以下信息拼接而成：
    - *.py 文件数量
    - 最新修改时间（max mtime）
    - 文件清单签名（基于相对路径 + mtime(ms) + size 的哈希）

    说明：
    - 仅依赖文件元信息，不读取文件内容，保持轻量；
    - 相比“仅看最新修改时间”，加入清单签名可避免“修改了非最新文件但 max mtime 未变”
      导致缓存未失效的问题。
    """

    def _dir_signature(root_dir: Path) -> tuple[int, float, str]:
        """返回 (count, latest_mtime, signature_hex8)。"""
        if not root_dir.exists():
            return 0, 0.0, "0" * 8

        paths = sorted(root_dir.rglob("*.py"))
        hasher = hashlib.md5()
        latest_mtime = 0.0
        count = 0
        for path in paths:
            stat = path.stat()
            count += 1
            if stat.st_mtime > latest_mtime:
                latest_mtime = stat.st_mtime
            rel = path.relative_to(workspace_path).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(str(int(stat.st_mtime * 1000)).encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(str(int(stat.st_size)).encode("utf-8"))
            hasher.update(b"\0")
        return count, latest_mtime, hasher.hexdigest()[:8]

    # 1) 实现库：plugins/nodes
    plugins_dir = workspace_path / "plugins" / "nodes"
    plugins_count, plugins_latest, plugins_sig = _dir_signature(plugins_dir)

    # 2) 节点定义/加载核心
    nodes_core_dir = workspace_path / "engine" / "nodes"
    nodes_count, nodes_latest, nodes_sig = _dir_signature(nodes_core_dir)

    # 3) 图解析/生成核心
    graph_code_dir = workspace_path / "engine" / "graph"
    graph_code_count, graph_code_latest, graph_sig = _dir_signature(graph_code_dir)

    # 4) 复合节点库
    composites_dir = workspace_path / "assets" / "资源库" / "复合节点库"
    composites_count, composites_latest, composites_sig = _dir_signature(composites_dir)

    return (
        f"plugins:{plugins_count}:{round(plugins_latest, 3)}:{plugins_sig}"
        f"|nodes:{nodes_count}:{round(nodes_latest, 3)}:{nodes_sig}"
        f"|gc:{graph_code_count}:{round(graph_code_latest, 3)}:{graph_sig}"
        f"|composites:{composites_count}:{round(composites_latest, 3)}:{composites_sig}"
    )



