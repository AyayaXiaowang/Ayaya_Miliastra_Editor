from __future__ import annotations

"""
缓存管理脚本（运行期产物）

提供命令：
- 清空磁盘缓存：运行时缓存根目录（默认 app/runtime/cache）下的 graph_cache/resource_cache/node_cache
- 清空内存缓存（ResourceManager 内部）
- 重建资源索引缓存（扫描资源库并写入 resource_cache/resource_index.json）
- 预构建节点图持久化缓存（遍历全部节点图并加载，以生成 graph_cache/*.json）

使用示例（在项目根目录执行）：
  python -X utf8 -m tools.clear_caches --clear
  python -X utf8 -m tools.clear_caches --clear --rebuild-index
  python -X utf8 -m tools.clear_caches --clear --rebuild-index --rebuild-graph-caches
  python -X utf8 -m tools.clear_caches --clear-graph-cache
"""

import argparse
from pathlib import Path

import shutil

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path, get_workspace_root
else:
    from _bootstrap import ensure_workspace_root_on_sys_path, get_workspace_root

ensure_workspace_root_on_sys_path()


def compute_workspace_path() -> Path:
    return get_workspace_root()


def _remove_dir_contents(dir_path: Path) -> int:
    if not dir_path.exists():
        return 0
    removed = 0
    for p in dir_path.glob("*"):
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        removed += 1
    # 若目录已空则删除目录本身
    if dir_path.exists() and (not any(dir_path.iterdir())):
        dir_path.rmdir()
    return removed


def _remove_file_if_exists(file_path: Path) -> int:
    if not file_path.exists():
        return 0
    file_path.unlink()
    return 1


def run_clear_operations(
    workspace_path: Path,
    clear_all: bool,
    clear_graph_cache: bool,
    clear_resource_index_cache: bool,
    clear_node_cache: bool,
) -> None:
    from engine.utils.cache.cache_paths import (  # noqa: WPS433
        get_graph_cache_dir,
        get_node_cache_dir,
        get_resource_cache_dir,
        get_runtime_cache_root,
    )

    runtime_cache_root = get_runtime_cache_root(workspace_path)
    graph_cache = get_graph_cache_dir(workspace_path)
    resource_cache = get_resource_cache_dir(workspace_path)
    node_cache = get_node_cache_dir(workspace_path)

    ui_session_state_file = runtime_cache_root / "ui_last_session.json"
    ingame_save_selection_file = runtime_cache_root / "player_ingame_save_selection.json"
    todo_states_dir = workspace_path / "app" / "runtime" / "todo_states"

    if clear_all:
        removed = 0
        removed += _remove_dir_contents(graph_cache)
        removed += _remove_dir_contents(resource_cache)
        removed += _remove_dir_contents(node_cache)
        removed += _remove_file_if_exists(ui_session_state_file)
        removed += _remove_file_if_exists(ingame_save_selection_file)
        removed += _remove_dir_contents(todo_states_dir)
        print(f"[OK] 已清除所有缓存（磁盘）。删除的持久化文件/目录数: {removed}")
        return

    removed_total = 0
    if clear_graph_cache:
        removed = _remove_dir_contents(graph_cache)
        removed_total += removed
        print(f"[OK] 已清空图缓存 {graph_cache}，删除条目数: {removed}")
    if clear_resource_index_cache:
        removed = _remove_dir_contents(resource_cache)
        removed_total += removed
        print(f"[OK] 已清空资源索引缓存 {resource_cache}，删除条目数: {removed}")
    if clear_node_cache:
        removed = _remove_dir_contents(node_cache)
        removed_total += removed
        print(f"[OK] 已清空节点库缓存 {node_cache}，删除条目数: {removed}")
    if removed_total == 0 and not (clear_graph_cache or clear_resource_index_cache or clear_node_cache):
        print("[信息] 未指定任何清理目标；如需全量清理请添加 --clear")


def run_rebuild_operations(
    workspace_path: Path,
    rebuild_index: bool,
    rebuild_graph_caches: bool,
) -> None:
    # 兼容外壳：暂不执行重建，待引擎稳定导出后挂接
    if rebuild_index:
        print("[信息] 跳过索引重建（等待引擎稳定导出接口）")
    if rebuild_graph_caches:
        print("[信息] 跳过图缓存预构建（等待引擎稳定导出接口）")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行期缓存管理（清空/重建）")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="清空所有缓存（等价于依次清理 graph_cache/resource_cache/node_cache，并清空内存缓存）",
    )
    parser.add_argument(
        "--clear-graph-cache",
        action="store_true",
        help="仅清空 graph_cache（位于运行时缓存根目录下）",
    )
    parser.add_argument(
        "--clear-resource-index-cache",
        action="store_true",
        help="仅清空 resource_cache（资源索引缓存，位于运行时缓存根目录下）",
    )
    parser.add_argument(
        "--clear-node-cache",
        action="store_true",
        help="仅清空 node_cache（节点库持久化缓存）",
    )
    parser.add_argument(
        "--rebuild-index",
        action="store_true",
        help="清空后重建资源索引并写入持久化缓存（建议与 --clear 一起使用）",
    )
    parser.add_argument(
        "--rebuild-graph-caches",
        action="store_true",
        help="遍历全部节点图以生成持久化图缓存（建议与 --clear 一起使用）",
    )

    args = parser.parse_args()
    workspace_path = compute_workspace_path()

    run_clear_operations(
        workspace_path=workspace_path,
        clear_all=bool(args.clear),
        clear_graph_cache=bool(args.clear_graph_cache),
        clear_resource_index_cache=bool(args.clear_resource_index_cache),
        clear_node_cache=bool(args.clear_node_cache),
    )
    run_rebuild_operations(
        workspace_path=workspace_path,
        rebuild_index=bool(args.rebuild_index),
        rebuild_graph_caches=bool(args.rebuild_graph_caches),
    )


if __name__ == "__main__":
    main()


