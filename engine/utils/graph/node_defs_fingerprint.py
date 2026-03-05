from __future__ import annotations

import hashlib
import sys
import threading
from pathlib import Path

from engine.utils.resource_library_layout import discover_scoped_resource_root_directories
from engine.utils.runtime_scope import get_active_package_id

_TOOLCHAIN_SEGMENT_CACHE_LOCK = threading.Lock()
_TOOLCHAIN_SEGMENT_CACHE: dict[tuple[str, str, str, str, str, str], str] = {}

_COMPOSITES_SEGMENT_CACHE_LOCK = threading.Lock()
_COMPOSITES_SEGMENT_CACHE: dict[tuple[str, str], str] = {}


def invalidate_toolchain_node_defs_fingerprint_cache() -> None:
    """清空“工具链（plugins/engine 核心）”段的指纹缓存。

    说明：
    - 该段默认认为在运行期稳定（便携版/发行版），因此允许长期缓存；
    - 源码开发期若修改了 `plugins/nodes` 或 `engine/nodes|graph`，可通过调用该函数强制下次重算。
    """
    with _TOOLCHAIN_SEGMENT_CACHE_LOCK:
        _TOOLCHAIN_SEGMENT_CACHE.clear()


def invalidate_composite_node_defs_fingerprint_cache() -> None:
    """清空“复合节点库（资源库）”段的指纹缓存。"""
    with _COMPOSITES_SEGMENT_CACHE_LOCK:
        _COMPOSITES_SEGMENT_CACHE.clear()


def invalidate_node_defs_fingerprint_cache() -> None:
    """清空节点定义指纹的全部进程内缓存。"""
    invalidate_toolchain_node_defs_fingerprint_cache()
    invalidate_composite_node_defs_fingerprint_cache()


def _infer_toolchain_root() -> Path:
    """推断“工具链根目录”。

    用途：当工作区是“外置资源库目录”（仅包含 assets/）时，
    节点实现库与引擎源码仍位于工具链目录（源码仓库根目录或 PyInstaller 便携版 exe 目录）。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    start = Path(__file__).resolve()
    for candidate in (start.parent, *start.parents):
        if (candidate / "engine").is_dir() and (candidate / "plugins").is_dir():
            return candidate
    # 兜底：engine/utils/graph/node_defs_fingerprint.py -> repo_root 为 parents[3]
    return start.parents[3]


def compute_node_defs_fingerprint(workspace_path: Path) -> str:
    """
    计算节点定义库的轻量指纹，用于节点库与图缓存的失效判定。

    统一规则（与 NodeRegistry/PersistentGraphCacheManager 共用）：
    - 实现库：`plugins/nodes/`
    - 节点定义/加载核心：`engine/nodes/`
    - 图解析/生成核心：`engine/graph/`
    - 复合节点库：按运行期作用域（active_package_id）收敛到：
      - `assets/资源库/共享/复合节点库/`
      - （可选）`assets/资源库/项目存档/<active_package_id>/复合节点库/`

    指纹由各目录的以下信息拼接而成：
    - *.py 文件数量
    - 最新修改时间（max mtime）
    - 文件清单签名（基于相对路径 + mtime(ms) + size 的哈希）

    说明：
    - 仅依赖文件元信息，不读取文件内容，保持轻量；
    - 相比“仅看最新修改时间”，加入清单签名可避免“修改了非最新文件但 max mtime 未变”
      导致缓存未失效的问题。
    """

    def _dir_signature(root_dir: Path, *, base_dir: Path) -> tuple[int, float, str]:
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
            rel = path.relative_to(base_dir).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(str(int(stat.st_mtime * 1000)).encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(str(int(stat.st_size)).encode("utf-8"))
            hasher.update(b"\0")
        return count, latest_mtime, hasher.hexdigest()[:8]

    resolved_workspace = workspace_path.resolve()
    toolchain_root = _infer_toolchain_root()

    # ===== 目录定位（兼容“外置工作区”） =====
    # 1) 实现库：plugins/nodes
    plugins_dir = resolved_workspace / "plugins" / "nodes"
    plugins_base = resolved_workspace
    if not plugins_dir.exists():
        fallback_plugins_dir = toolchain_root / "plugins" / "nodes"
        if fallback_plugins_dir.exists():
            plugins_dir = fallback_plugins_dir
            plugins_base = toolchain_root

    # 2) 节点定义/加载核心
    nodes_core_dir = resolved_workspace / "engine" / "nodes"
    nodes_base = resolved_workspace
    if not nodes_core_dir.exists():
        fallback_nodes_core_dir = toolchain_root / "engine" / "nodes"
        if fallback_nodes_core_dir.exists():
            nodes_core_dir = fallback_nodes_core_dir
            nodes_base = toolchain_root

    # 3) 图解析/生成核心
    graph_code_dir = resolved_workspace / "engine" / "graph"
    graph_base = resolved_workspace
    if not graph_code_dir.exists():
        fallback_graph_code_dir = toolchain_root / "engine" / "graph"
        if fallback_graph_code_dir.exists():
            graph_code_dir = fallback_graph_code_dir
            graph_base = toolchain_root

    # ===== 工具链段缓存（plugins/nodes/engine core）=====
    toolchain_key = (
        str(plugins_dir.resolve()),
        str(plugins_base.resolve()),
        str(nodes_core_dir.resolve()),
        str(nodes_base.resolve()),
        str(graph_code_dir.resolve()),
        str(graph_base.resolve()),
    )
    with _TOOLCHAIN_SEGMENT_CACHE_LOCK:
        toolchain_segment = _TOOLCHAIN_SEGMENT_CACHE.get(toolchain_key)
        if toolchain_segment is None:
            plugins_count, plugins_latest, plugins_sig = _dir_signature(plugins_dir, base_dir=plugins_base)
            nodes_count, nodes_latest, nodes_sig = _dir_signature(nodes_core_dir, base_dir=nodes_base)
            graph_code_count, graph_code_latest, graph_sig = _dir_signature(graph_code_dir, base_dir=graph_base)
            toolchain_segment = (
                f"plugins:{plugins_count}:{round(plugins_latest, 3)}:{plugins_sig}"
                f"|nodes:{nodes_count}:{round(nodes_latest, 3)}:{nodes_sig}"
                f"|gc:{graph_code_count}:{round(graph_code_latest, 3)}:{graph_sig}"
            )
            _TOOLCHAIN_SEGMENT_CACHE[toolchain_key] = toolchain_segment

    # ===== 复合节点库段缓存（资源库作用域相关）=====
    active_package_id = get_active_package_id()
    composites_key = (str(resolved_workspace), str(active_package_id or ""))
    with _COMPOSITES_SEGMENT_CACHE_LOCK:
        composites_segment = _COMPOSITES_SEGMENT_CACHE.get(composites_key)
        if composites_segment is None:
            resource_library_root = resolved_workspace / "assets" / "资源库"
            composite_root_dirs = [
                root / "复合节点库"
                for root in discover_scoped_resource_root_directories(
                    resource_library_root,
                    active_package_id=active_package_id,
                )
            ]

            composite_paths: list[Path] = []
            for composite_root in composite_root_dirs:
                if not composite_root.exists():
                    continue
                composite_paths.extend(composite_root.rglob("*.py"))

            composite_paths = sorted(set(composite_paths))
            composites_hasher = hashlib.md5()
            composites_latest = 0.0
            composites_count = 0
            for path in composite_paths:
                stat = path.stat()
                composites_count += 1
                if stat.st_mtime > composites_latest:
                    composites_latest = stat.st_mtime
                rel = path.relative_to(resolved_workspace).as_posix()
                composites_hasher.update(rel.encode("utf-8"))
                composites_hasher.update(b"\0")
                composites_hasher.update(str(int(stat.st_mtime * 1000)).encode("utf-8"))
                composites_hasher.update(b"\0")
                composites_hasher.update(str(int(stat.st_size)).encode("utf-8"))
                composites_hasher.update(b"\0")
            composites_sig = composites_hasher.hexdigest()[:8] if composites_count > 0 else "0" * 8

            composites_segment = (
                f"|composites:{composites_count}:{round(composites_latest, 3)}:{composites_sig}"
            )
            _COMPOSITES_SEGMENT_CACHE[composites_key] = composites_segment

    exe_marker = ""
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        exe_stat = exe_path.stat()
        exe_marker = f"|exe:{int(exe_stat.st_mtime)}:{int(exe_stat.st_size)}"

    return f"{toolchain_segment}{composites_segment}{exe_marker}"



