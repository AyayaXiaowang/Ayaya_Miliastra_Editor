from __future__ import annotations

import json
from pathlib import Path

from engine.configs.resource_types import ResourceType
from engine.resources.index_disk_consistency import collect_package_index_disk_consistency
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager
from engine.utils.resource_library_layout import get_packages_root_dir


def _write_template_json(target_file: Path, *, template_id: str, name: str) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "template_id": template_id,
        "name": name,
        "entity_type": "造物",
        "description": "",
        "default_graphs": [],
        "default_components": [],
        "entity_config": {},
        "metadata": {},
        "graph_variable_overrides": {},
    }
    target_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_index_disk_consistency_reports_orphan_when_resource_manager_scope_excludes_package(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace_root"
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "assets").mkdir(parents=True, exist_ok=True)

    resource_manager = ResourceManager(workspace_root)
    resource_library_dir = resource_manager.resource_library_dir

    package_id = "pkg_alpha"
    package_root_dir = get_packages_root_dir(resource_library_dir) / package_id
    package_root_dir.mkdir(parents=True, exist_ok=True)

    # 写入一个“包内模板”文件，但保持 ResourceManager 为 shared-only 作用域
    template_id = "template_pkg_1"
    template_file = package_root_dir / ResourceType.TEMPLATE.value / "包内模板.json"
    _write_template_json(template_file, template_id=template_id, name="包内模板")
    resource_manager.rebuild_index(active_package_id=None)

    package_index_manager = PackageIndexManager(workspace_root, resource_manager)
    report = collect_package_index_disk_consistency(
        package_id=package_id,
        resource_manager=resource_manager,
        package_index_manager=package_index_manager,
    )

    assert report.total_orphan == 1
    template_category = next(
        item for item in report.category_reports if item.category_key == "templates"
    )
    assert template_id in template_category.orphan_ids


def test_index_disk_consistency_reports_missing_when_resource_file_deleted_without_rebuild(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace_root"
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "assets").mkdir(parents=True, exist_ok=True)

    resource_manager = ResourceManager(workspace_root)
    resource_library_dir = resource_manager.resource_library_dir

    package_id = "pkg_beta"
    package_root_dir = get_packages_root_dir(resource_library_dir) / package_id
    package_root_dir.mkdir(parents=True, exist_ok=True)

    template_id = "template_pkg_2"
    template_file = package_root_dir / ResourceType.TEMPLATE.value / "模板2.json"
    _write_template_json(template_file, template_id=template_id, name="模板2")

    # 切到该包作用域建索引：索引侧将包含 template_id
    resource_manager.rebuild_index(active_package_id=package_id)
    package_index_manager = PackageIndexManager(workspace_root, resource_manager)

    # 删除文件但不重建索引：制造 “索引有、磁盘无”
    template_file.unlink()

    report = collect_package_index_disk_consistency(
        package_id=package_id,
        resource_manager=resource_manager,
        package_index_manager=package_index_manager,
    )
    assert report.total_missing == 1
    template_category = next(
        item for item in report.category_reports if item.category_key == "templates"
    )
    assert template_id in template_category.missing_ids


def test_index_disk_consistency_reports_disk_duplicate_ids(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace_root"
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "assets").mkdir(parents=True, exist_ok=True)

    resource_manager = ResourceManager(workspace_root)
    resource_library_dir = resource_manager.resource_library_dir

    package_id = "pkg_gamma"
    package_root_dir = get_packages_root_dir(resource_library_dir) / package_id
    package_root_dir.mkdir(parents=True, exist_ok=True)

    # 磁盘上制造同 ID 的两个模板文件（不同文件名）
    template_id = "template_dup_1"
    _write_template_json(
        package_root_dir / ResourceType.TEMPLATE.value / "模板A.json",
        template_id=template_id,
        name="模板A",
    )
    _write_template_json(
        package_root_dir / ResourceType.TEMPLATE.value / "模板B.json",
        template_id=template_id,
        name="模板B",
    )

    # 不切换到该包作用域，避免 ResourceIndexBuilder 在 build_index 时直接抛错
    resource_manager.rebuild_index(active_package_id=None)
    package_index_manager = PackageIndexManager(workspace_root, resource_manager)

    report = collect_package_index_disk_consistency(
        package_id=package_id,
        resource_manager=resource_manager,
        package_index_manager=package_index_manager,
    )

    assert report.total_duplicate_disk == 1
    template_category = next(
        item for item in report.category_reports if item.category_key == "templates"
    )
    assert any(entry.resource_id == template_id for entry in template_category.duplicate_disk_entries)


