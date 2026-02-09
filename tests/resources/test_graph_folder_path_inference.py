from __future__ import annotations

import json
from pathlib import Path

from tests._helpers.project_paths import get_repo_root

from engine.configs.resource_types import ResourceType
from engine.resources.resource_manager import ResourceManager
from engine.utils.cache.cache_paths import get_graph_cache_dir
from engine.utils.resource_library_layout import get_packages_root_dir


def _prepare_resource_manager_scope_for_sample_graph(resource_manager: ResourceManager, repo_root: Path) -> None:
    """将 ResourceManager 的索引作用域切换到包含示例节点图的项目存档根目录。

    背景：
    - 资源索引在默认情况下仅扫描共享根目录；
    - 本用例节点图（server_signal_all_types_example_01）位于示例项目存档目录内，因此需要显式切换作用域。
    """
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


def test_load_resource_infers_folder_path_when_docstring_missing_folder_path() -> None:
    """回归：节点图 docstring 未写 folder_path 时，load_resource 应从文件路径推断。

    该行为直接影响 UI「节点图属性/基本信息/文件夹」字段的展示。
    """
    repo_root = get_repo_root()
    resource_manager = ResourceManager(repo_root)
    _prepare_resource_manager_scope_for_sample_graph(resource_manager, repo_root)

    graph_id = "server_signal_all_types_example_01"
    resource_manager.invalidate_graph_for_reparse(graph_id)

    payload = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    assert isinstance(payload, dict)
    assert payload.get("folder_path") == "实体节点图/模板示例"


def test_load_resource_infers_folder_path_on_persistent_cache_hit_when_cached_folder_path_is_empty() -> None:
    """回归：即使持久化 graph_cache 中的 result_data.folder_path 为空，也必须能自愈。

    典型场景：旧版本缓存写入不包含 folder_path，但用户升级后不应需要手动清缓存。
    """
    repo_root = get_repo_root()
    resource_manager = ResourceManager(repo_root)
    _prepare_resource_manager_scope_for_sample_graph(resource_manager, repo_root)

    graph_id = "server_signal_all_types_example_01"
    resource_manager.invalidate_graph_for_reparse(graph_id)

    first_payload = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    assert isinstance(first_payload, dict)
    assert first_payload.get("folder_path") == "实体节点图/模板示例"

    cache_file = get_graph_cache_dir(repo_root) / f"{graph_id}.json"
    assert cache_file.is_file()

    cache_payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert isinstance(cache_payload, dict)

    result_data = cache_payload.get("result_data")
    assert isinstance(result_data, dict)
    result_data["folder_path"] = ""
    cache_payload["result_data"] = result_data

    cache_file.write_text(
        json.dumps(cache_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 清理内存缓存，确保下一次 load_resource 命中“持久化缓存”路径
    resource_manager.clear_cache(ResourceType.GRAPH, graph_id)

    second_payload = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    assert isinstance(second_payload, dict)
    assert second_payload.get("folder_path") == "实体节点图/模板示例"


def test_load_graph_metadata_repairs_cached_folder_path_when_empty() -> None:
    """回归：轻量元数据缓存命中时若 folder_path 为空，应补齐并回写缓存。"""
    repo_root = get_repo_root()
    resource_manager = ResourceManager(repo_root)
    _prepare_resource_manager_scope_for_sample_graph(resource_manager, repo_root)

    graph_id = "server_signal_all_types_example_01"

    metadata = resource_manager.load_graph_metadata(graph_id)
    assert isinstance(metadata, dict)
    assert metadata.get("folder_path") == "实体节点图/模板示例"

    cache_service = getattr(resource_manager, "_cache_service")
    cache_key = (ResourceType.GRAPH, f"{graph_id}_metadata")
    cached_entry = getattr(cache_service, "_resource_cache").get(cache_key)
    assert cached_entry is not None

    cached_data, cached_mtime = cached_entry
    assert isinstance(cached_data, dict)
    assert isinstance(cached_mtime, float)

    cached_data["folder_path"] = ""
    getattr(cache_service, "_resource_cache")[cache_key] = (cached_data, cached_mtime)

    repaired = resource_manager.load_graph_metadata(graph_id)
    assert isinstance(repaired, dict)
    assert repaired.get("folder_path") == "实体节点图/模板示例"


