from __future__ import annotations

import json
from pathlib import Path

from engine.configs.resource_types import ResourceType
from engine.resources.resource_file_ops import ResourceFileOps
from engine.resources.resource_index_builder import ResourceIndexBuilder
from engine.resources.resource_index_service import ResourceIndexService
from engine.resources.resource_state import ResourceIndexState


def _build_index_service(workspace_path: Path) -> ResourceIndexService:
    resource_library_dir = workspace_path / "assets" / "资源库"
    index_builder = ResourceIndexBuilder(workspace_path, resource_library_dir)
    file_ops = ResourceFileOps(resource_library_dir)
    index_state = ResourceIndexState()
    return ResourceIndexService(
        workspace_path=workspace_path,
        index_builder=index_builder,
        file_ops=file_ops,
        index_state=index_state,
    )


def _write_json_file(target_file: Path, payload: dict) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with open(target_file, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)


def _read_json_file(target_file: Path) -> dict:
    with open(target_file, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def test_scan_does_not_overwrite_name_for_decoupled_json_resource(tmp_path: Path) -> None:
    """
    回归：当保存策略允许 name 与文件名解耦（默认沿用 id_to_filename_cache）时，
    索引扫描不应把 JSON 的 name 强行写回为文件名，否则会造成 UI 改名回滚。
    """
    index_service = _build_index_service(tmp_path)

    resource_id = "item_001"
    file_path = tmp_path / "old_filename.json"
    original_payload = {
        "item_id": resource_id,
        "name": "新的道具显示名",
        "updated_at": "2025-01-01T00:00:00",
    }
    _write_json_file(file_path, original_payload)

    did_sync = index_service._check_and_sync_name(
        file_path=file_path,
        resource_type=ResourceType.ITEM,
        resource_id=resource_id,
        filename_without_ext="old_filename",
        preloaded_data=_read_json_file(file_path),
    )
    assert did_sync is False

    payload_after_scan = _read_json_file(file_path)
    assert payload_after_scan.get("name") == "新的道具显示名"


def test_scan_overwrites_name_for_name_driven_filename_resource(tmp_path: Path) -> None:
    """
    对于保存策略明确“以 name 驱动物理文件名”的 JSON 资源类型：
    若用户手动修改了文件名，索引扫描允许以文件名为准回写 name，保持库内一致性。
    """
    index_service = _build_index_service(tmp_path)

    resource_id = "timer_001"
    file_path = tmp_path / "old_timer_name.json"
    original_payload = {
        "timer_id": resource_id,
        "name": "新的计时器显示名",
        "updated_at": "2025-01-01T00:00:00",
    }
    _write_json_file(file_path, original_payload)

    did_sync = index_service._check_and_sync_name(
        file_path=file_path,
        resource_type=ResourceType.TIMER,
        resource_id=resource_id,
        filename_without_ext="old_timer_name",
        preloaded_data=_read_json_file(file_path),
    )
    assert did_sync is True

    payload_after_scan = _read_json_file(file_path)
    assert payload_after_scan.get("name") == "old_timer_name"


