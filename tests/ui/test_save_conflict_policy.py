from __future__ import annotations

import json
from pathlib import Path

from engine.configs.resource_types import ResourceType
from engine.graph.models.package_model import TemplateConfig
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager
from engine.utils.resource_library_layout import get_packages_root_dir
from app.ui.controllers.package_save.resource_container_save_service import ResourceContainerSaveService


def _read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise AssertionError("json root must be dict")
    return data


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, ensure_ascii=False, indent=2)


def _find_single_json_file(directory: Path) -> Path:
    json_files = list(directory.glob("*.json"))
    if len(json_files) != 1:
        raise AssertionError(f"expected exactly 1 json file in {directory}, got: {json_files}")
    return json_files[0]


def test_resource_save_aborts_when_disk_changed_and_expected_mtime_provided(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    (workspace_path / "assets").mkdir(parents=True, exist_ok=True)
    resource_manager = ResourceManager(workspace_path)

    template_config = TemplateConfig(
        template_id="template_save_conflict_01",
        name="初始模板",
        entity_type="测试类型",
    )
    save_ok = resource_manager.save_resource(
        ResourceType.TEMPLATE,
        template_config.template_id,
        template_config.serialize(),
    )
    assert save_ok is True

    template_file = resource_manager.list_resource_file_paths(ResourceType.TEMPLATE).get(
        template_config.template_id
    )
    assert template_file is not None and template_file.exists()
    baseline_mtime = float(template_file.stat().st_mtime)

    # 模拟外部工具修改磁盘内容（并确保 mtime 变化）
    external_payload = _read_json(template_file)
    external_payload["name"] = "外部已更新"
    _write_json(template_file, external_payload)
    assert float(template_file.stat().st_mtime) != baseline_mtime

    # 本地尝试保存旧内容：期望被拒绝（不允许静默覆盖）
    local_payload = template_config.serialize()
    local_payload["description"] = "本地修改"
    save_ok_after_external_change = resource_manager.save_resource(
        ResourceType.TEMPLATE,
        template_config.template_id,
        local_payload,
        expected_mtime=baseline_mtime,
        allow_overwrite_external=False,
    )
    assert save_ok_after_external_change is False

    # 文件内容应保持外部版本
    assert _read_json(template_file)["name"] == "外部已更新"


def test_resource_save_can_overwrite_when_policy_allows(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    (workspace_path / "assets").mkdir(parents=True, exist_ok=True)
    resource_manager = ResourceManager(workspace_path)

    template_config = TemplateConfig(
        template_id="template_save_conflict_02",
        name="初始模板",
        entity_type="测试类型",
    )
    assert (
        resource_manager.save_resource(
            ResourceType.TEMPLATE,
            template_config.template_id,
            template_config.serialize(),
        )
        is True
    )

    template_file = resource_manager.list_resource_file_paths(ResourceType.TEMPLATE).get(
        template_config.template_id
    )
    assert template_file is not None and template_file.exists()
    baseline_mtime = float(template_file.stat().st_mtime)

    external_payload = _read_json(template_file)
    external_payload["name"] = "外部已更新"
    _write_json(template_file, external_payload)
    assert float(template_file.stat().st_mtime) != baseline_mtime

    local_payload = template_config.serialize()
    local_payload["name"] = "本地覆盖"
    save_ok_after_external_change = resource_manager.save_resource(
        ResourceType.TEMPLATE,
        template_config.template_id,
        local_payload,
        expected_mtime=baseline_mtime,
        allow_overwrite_external=True,
    )
    assert save_ok_after_external_change is True
    assert _read_json(template_file)["name"] == "本地覆盖"


def test_package_index_save_does_not_write_pkg_json_in_directory_mode(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    (workspace_path / "assets").mkdir(parents=True, exist_ok=True)
    resource_manager = ResourceManager(workspace_path)
    package_index_manager = PackageIndexManager(workspace_path, resource_manager)

    # 目录模式下的 create_package 依赖“示例项目模板”目录；本测试只关注 save_package_index 的 no-op 语义，
    # 因此直接构造一个最小包目录并用 load_package_index 派生出 PackageIndex 视图。
    packages_root_dir = get_packages_root_dir(workspace_path / "assets" / "资源库")
    package_root_dir = packages_root_dir / "pkg_save_conflict_01"
    package_root_dir.mkdir(parents=True, exist_ok=True)

    package_index = package_index_manager.load_package_index(package_root_dir.name)
    assert package_index is not None
    legacy_root = workspace_path / "assets" / "资源库"
    legacy_pkg_files = list(legacy_root.glob("pkg_*.json")) + list(legacy_root.glob("packages.json"))
    assert not legacy_pkg_files

    package_index.description = "本地修改（目录模式下不会写 pkg_*.json）"
    save_ok = package_index_manager.save_package_index(
        package_index,
        expected_mtime=123.0,
        allow_overwrite_external=False,
    )
    assert save_ok is True
    legacy_pkg_files = list(legacy_root.glob("pkg_*.json")) + list(legacy_root.glob("packages.json"))
    assert not legacy_pkg_files


def test_package_index_save_overwrite_flag_is_noop_in_directory_mode(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    (workspace_path / "assets").mkdir(parents=True, exist_ok=True)
    resource_manager = ResourceManager(workspace_path)
    package_index_manager = PackageIndexManager(workspace_path, resource_manager)

    packages_root_dir = get_packages_root_dir(workspace_path / "assets" / "资源库")
    package_root_dir = packages_root_dir / "pkg_save_conflict_02"
    package_root_dir.mkdir(parents=True, exist_ok=True)

    package_index = package_index_manager.load_package_index(package_root_dir.name)
    assert package_index is not None
    legacy_root = workspace_path / "assets" / "资源库"
    legacy_pkg_files = list(legacy_root.glob("pkg_*.json")) + list(legacy_root.glob("packages.json"))
    assert not legacy_pkg_files

    package_index.description = "本地覆盖"
    save_ok = package_index_manager.save_package_index(
        package_index,
        expected_mtime=123.0,
        allow_overwrite_external=True,
    )
    assert save_ok is True
    legacy_pkg_files = list(legacy_root.glob("pkg_*.json")) + list(legacy_root.glob("packages.json"))
    assert not legacy_pkg_files


def test_resource_container_save_service_blocks_overwrite_when_container_has_source_mtime(tmp_path: Path) -> None:
    workspace_path = tmp_path / "workspace"
    (workspace_path / "assets").mkdir(parents=True, exist_ok=True)
    resource_manager = ResourceManager(workspace_path)

    template_config = TemplateConfig(
        template_id="template_save_conflict_03",
        name="初始模板",
        entity_type="测试类型",
    )
    assert (
        resource_manager.save_resource(
            ResourceType.TEMPLATE,
            template_config.template_id,
            template_config.serialize(),
        )
        is True
    )

    template_file = resource_manager.list_resource_file_paths(ResourceType.TEMPLATE).get(
        template_config.template_id
    )
    assert template_file is not None and template_file.exists()
    baseline_mtime = float(template_file.stat().st_mtime)

    # 模拟“对象来自加载”的基线：保存服务应使用该 mtime 做冲突检测
    setattr(template_config, "_source_mtime", baseline_mtime)

    external_payload = _read_json(template_file)
    external_payload["name"] = "外部已更新"
    _write_json(template_file, external_payload)
    assert float(template_file.stat().st_mtime) != baseline_mtime

    template_config.description = "本地修改"
    saver = ResourceContainerSaveService(resource_manager)
    save_ok = saver.save_container(template_config, "template", verbose=False)
    assert save_ok is False
    assert _read_json(template_file)["name"] == "外部已更新"


