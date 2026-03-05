from __future__ import annotations

import json
from pathlib import Path

from engine.configs.resource_types import ResourceType
from engine.resources.resource_index_builder import ResourceIndexBuilder


def _build_index_without_name_sync(workspace_path: Path) -> ResourceIndexBuilder:
    resource_library_dir = workspace_path / "assets" / "资源库"
    builder = ResourceIndexBuilder(workspace_path, resource_library_dir)
    # 直接触发一次全量扫描，避免依赖磁盘上的持久化索引缓存。
    builder.build_index(lambda *args, **kwargs: False)
    return builder


def _write_item_json(target_file: Path, *, item_id: str, item_name: str) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"item_id": item_id, "item_name": item_name}
    with open(target_file, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)


def test_all_item_json_files_are_indexed(tmp_path: Path) -> None:
    """
    展示型仓库不依赖真实资源库：在临时工作区构造最小资源目录，
    确保 `战斗预设/道具` 目录下的所有 JSON 文件都能被资源索引扫描并出现在
    ResourceType.ITEM 的索引映射中。
    """
    workspace_path = tmp_path
    resource_library_dir = workspace_path / "assets" / "资源库"
    items_dir = resource_library_dir / "共享" / ResourceType.ITEM.value

    _write_item_json(items_dir / "item_a.json", item_id="item_a", item_name="示例道具A")
    _write_item_json(items_dir / "item_b.json", item_id="item_b", item_name="示例道具B")

    builder = _build_index_without_name_sync(workspace_path)
    # 触发完 build_index 后，直接从新构建的索引缓存中读取 ITEM bucket。
    index_data = builder.try_load_from_cache()
    assert index_data is not None, "索引缓存应在刚刚构建后立即可用"

    item_bucket = index_data.resource_index.get(ResourceType.ITEM, {})
    assert item_bucket, "ResourceType.ITEM 索引结果不应为空"

    indexed_paths = {path.resolve() for path in item_bucket.values()}
    json_files = [path for path in items_dir.glob("*.json")]

    # 目录下的每一个 JSON 文件都应该出现在 ITEM 类型的索引映射中。
    missing_files = [path for path in json_files if path.resolve() not in indexed_paths]
    assert not missing_files, f"以下道具 JSON 未出现在 ResourceType.ITEM 索引中: {[p.name for p in missing_files]}"


def test_stale_item_bucket_cache_is_invalidated(tmp_path: Path) -> None:
    """
    构造一个“磁盘上 JSON 文件已增加，但缓存中的 ITEM bucket 仍只包含部分条目”的场景，
    验证 ResourceIndexBuilder.try_load_from_cache 会将该缓存判定为失效并返回 None。
    """
    workspace_path = tmp_path
    resource_library_dir = workspace_path / "assets" / "资源库"
    items_dir = resource_library_dir / "共享" / ResourceType.ITEM.value
    _write_item_json(items_dir / "item_a.json", item_id="item_a", item_name="示例道具A")
    _write_item_json(items_dir / "item_b.json", item_id="item_b", item_name="示例道具B")

    # 第一次构建：生成一个完整且自洽的索引，并写入持久化缓存。
    builder = ResourceIndexBuilder(workspace_path, resource_library_dir)
    full_index_data = builder.build_index(lambda *args, **kwargs: False)

    full_item_bucket = full_index_data.resource_index.get(ResourceType.ITEM, {})
    # 需要至少存在一条 ITEM 资源，才能构造“只保留部分条目”的场景。
    assert full_item_bucket, "测试依赖于至少一条战斗预设-道具资源"

    # 人为构造一个“过期”的 ITEM bucket：仅保留其中一条记录。
    # 其他资源类型保持不变，模拟现实中“外部脚本直接写入 JSON，但未刷新索引”的情况。
    stale_resource_index = dict(full_index_data.resource_index)
    first_item_id, first_item_path = next(iter(full_item_bucket.items()))
    stale_resource_index[ResourceType.ITEM] = {first_item_id: first_item_path}

    builder._save_persistent_resource_index(  # type: ignore[attr-defined]
        resource_index=stale_resource_index,
        name_to_id_index=full_index_data.name_to_id_index,
        id_to_filename_cache=full_index_data.id_to_filename_cache,
    )

    # 在新的防御逻辑下，try_load_from_cache 应检测到“磁盘 JSON 数量 > 索引条目数”，
    # 从而返回 None，强制后续走全量扫描路径。
    cached_after_stale = builder.try_load_from_cache()
    assert cached_after_stale is None, "对于 ITEM bucket 少于磁盘 JSON 数量的缓存，应视为无效"

    # 为避免影响后续手动运行工具或 UI，再次构建一次完整索引写回磁盘。
    builder.build_index(lambda *args, **kwargs: False)


