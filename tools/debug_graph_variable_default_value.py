from __future__ import annotations

import io
import json
import sys
from pathlib import Path

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path
else:
    from _bootstrap import ensure_workspace_root_on_sys_path

WORKSPACE_ROOT = ensure_workspace_root_on_sys_path()

# 修复 Windows 控制台编码问题（与本目录其它脚本保持一致）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from engine.configs.resource_types import ResourceType
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.resources.resource_manager import ResourceManager
from engine.utils.cache.cache_paths import get_graph_cache_dir


def _find_var_default(graph_variables: list[dict], variable_name: str):
    for item in graph_variables:
        if isinstance(item, dict) and item.get("name") == variable_name:
            return item.get("default_value")
    return None


def main() -> None:
    workspace_path = WORKSPACE_ROOT
    graph_id = "server_template_pedal_switch_signal_broadcast_01"
    graph_file = (
        workspace_path
        / "assets"
        / "资源库"
        / "节点图"
        / "server"
        / "模板示例"
        / "模板示例_踏板开关_信号广播.py"
    )
    variable_name = "相对位移方向"

    print("=== debug_graph_variable_default_value ===")
    print(f"python_executable: {sys.executable}")
    print(f"python_version: {sys.version.splitlines()[0]}")
    print(f"workspace_path: {workspace_path}")
    print(f"graph_file: {graph_file}")
    print(f"graph_id: {graph_id}")
    print(f"variable_name: {variable_name}")
    print("")

    # 1) 直接从源码提取元数据（GRAPH_VARIABLES AST）
    metadata = load_graph_metadata_from_file(graph_file)
    meta_default = _find_var_default(metadata.graph_variables, variable_name)
    print("[A] metadata_extractor.load_graph_metadata_from_file -> default_value:")
    print(meta_default)
    print("")

    # 2) 通过 ResourceManager 加载图（模拟 UI 的资源加载路径）
    resource_manager = ResourceManager(workspace_path)
    resource_manager.rebuild_index()
    graph_resource = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    rm_default = None
    if isinstance(graph_resource, dict):
        data = graph_resource.get("data", {})
        if isinstance(data, dict):
            rm_default = _find_var_default(data.get("graph_variables", []), variable_name)
    print("[B] ResourceManager.load_resource(ResourceType.GRAPH, graph_id) -> default_value:")
    print(rm_default)
    print("")

    # 3) 读取持久化缓存文件（若存在）
    cache_dir = get_graph_cache_dir(workspace_path)
    cache_file = cache_dir / f"{graph_id}.json"
    print("[C] graph_cache:")
    print(f"cache_dir: {cache_dir}")
    print(f"cache_file_exists: {cache_file.exists()}")
    if cache_file.exists():
        root = json.loads(cache_file.read_text(encoding="utf-8"))
        result_data = root.get("result_data", {})
        data = result_data.get("data", {})
        cached_default = None
        if isinstance(data, dict):
            cached_default = _find_var_default(data.get("graph_variables", []), variable_name)
        print("cached default_value:")
        print(cached_default)
    print("")

    print("=== done ===")


if __name__ == "__main__":
    main()


