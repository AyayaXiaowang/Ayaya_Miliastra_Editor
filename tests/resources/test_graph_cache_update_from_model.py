from __future__ import annotations

from pathlib import Path

from tests._helpers.project_paths import get_repo_root

from engine.configs.resource_types import ResourceType
from engine.graph.models.graph_model import GraphModel
from engine.resources.resource_manager import ResourceManager
from engine.utils.resource_library_layout import get_packages_root_dir


def _prepare_resource_manager_scope_for_sample_graph(resource_manager: ResourceManager, repo_root: Path) -> None:
    """将 ResourceManager 的索引作用域切换到包含示例节点图的项目存档根目录。"""
    resource_library_root = repo_root / "assets" / "资源库"
    packages_root_dir = get_packages_root_dir(resource_library_root)
    expected_graph_file = Path("节点图/server/实体节点图/模板示例/模板示例_信号全类型_发送与监听.py")

    candidate_package_ids: list[str] = []
    if packages_root_dir.exists() and packages_root_dir.is_dir():
        for package_dir in packages_root_dir.iterdir():
            if not package_dir.is_dir():
                continue
            if (package_dir / expected_graph_file).is_file():
                candidate_package_ids.append(package_dir.name)

    if not candidate_package_ids:
        raise AssertionError(f"未找到包含示例节点图文件的项目存档目录：{expected_graph_file}")

    preferred = "示例项目模板"
    selected_package_id = preferred if preferred in candidate_package_ids else sorted(candidate_package_ids, key=lambda text: text.casefold())[0]
    resource_manager.rebuild_index(active_package_id=selected_package_id)


def test_update_persistent_graph_cache_from_model_populates_node_defs_fp_and_hits_memory_cache() -> None:
    """回归：UI 自动排版后用 GraphModel 刷新缓存时，result_data.metadata 必须完整（node_defs_fp）。"""
    repo_root = get_repo_root()
    resource_manager = ResourceManager(repo_root)
    _prepare_resource_manager_scope_for_sample_graph(resource_manager, repo_root)

    graph_id = "server_signal_all_types_example_01"
    resource_manager.invalidate_graph_for_reparse(graph_id)

    payload = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    assert isinstance(payload, dict)

    graph_data = payload.get("data")
    assert isinstance(graph_data, dict)
    model = GraphModel.deserialize(graph_data)

    # 模拟自动排版：仅调整位置（不改动 .py 源文件）
    if model.nodes:
        first_node = next(iter(model.nodes.values()))
        x_pos, y_pos = first_node.pos
        first_node.pos = (float(x_pos) + 10.0, float(y_pos) + 10.0)

    final_result = resource_manager.update_persistent_graph_cache_from_model(
        graph_id,
        model,
        layout_changed=True,
    )
    assert isinstance(final_result, dict)

    result_metadata = final_result.get("metadata")
    assert isinstance(result_metadata, dict)
    node_defs_fp = result_metadata.get("node_defs_fp")
    assert isinstance(node_defs_fp, str)
    assert node_defs_fp.strip() != ""

    # folder_path 应从文件路径推断并稳定输出（避免 UI 基本信息展示为空）
    assert final_result.get("folder_path") == "实体节点图/模板示例"

    file_path = resource_manager.get_graph_file_path(graph_id)
    assert file_path is not None
    assert file_path.is_file()
    current_mtime = float(file_path.stat().st_mtime)

    graph_service = getattr(resource_manager, "_graph_service")
    cache_facade = getattr(graph_service, "_cache_facade")
    cached = cache_facade.get_graph_from_memory_cache(graph_id, current_mtime)
    assert isinstance(cached, dict)
    cached_metadata = cached.get("metadata")
    assert isinstance(cached_metadata, dict)
    assert cached_metadata.get("node_defs_fp") == node_defs_fp


