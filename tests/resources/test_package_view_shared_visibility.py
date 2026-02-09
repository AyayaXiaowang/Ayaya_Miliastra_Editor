from __future__ import annotations

from pathlib import Path

from engine.configs.resource_types import ResourceType
from engine.resources.package_index import PackageIndex
from engine.resources.package_view import PackageView
from engine.resources.resource_manager import ResourceManager
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir


def test_package_view_templates_include_shared_templates(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace_root"
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "assets").mkdir(parents=True, exist_ok=True)

    resource_manager = ResourceManager(workspace_root)
    resource_library_dir = resource_manager.resource_library_dir

    shared_root_dir = get_shared_root_dir(resource_library_dir)
    package_id = "pkg_alpha"
    package_root_dir = get_packages_root_dir(resource_library_dir) / package_id
    package_root_dir.mkdir(parents=True, exist_ok=True)

    shared_template_id = "template_shared_1"
    package_template_id = "template_pkg_1"

    shared_payload = {
        "template_id": shared_template_id,
        "name": "共享模板",
        "entity_type": "造物",
        "description": "",
        "default_graphs": [],
        "default_components": [],
        "entity_config": {},
        "metadata": {},
        "graph_variable_overrides": {},
    }
    package_payload = {
        "template_id": package_template_id,
        "name": "包内模板",
        "entity_type": "造物",
        "description": "",
        "default_graphs": [],
        "default_components": [],
        "entity_config": {},
        "metadata": {},
        "graph_variable_overrides": {},
    }

    assert resource_manager.save_resource(
        ResourceType.TEMPLATE,
        shared_template_id,
        dict(shared_payload),
        resource_root_dir=shared_root_dir,
    )
    assert resource_manager.save_resource(
        ResourceType.TEMPLATE,
        package_template_id,
        dict(package_payload),
        resource_root_dir=package_root_dir,
    )

    # 具体存档视图：索引作用域应切换为“共享 + 当前项目存档”
    resource_manager.rebuild_index(active_package_id=package_id)

    package_index = PackageIndex(package_id=package_id, name="Pkg Alpha")
    package_index.resources.templates = [package_template_id]

    view = PackageView(package_index, resource_manager)
    templates = view.templates

    assert package_template_id in templates
    assert shared_template_id in templates
    assert templates[package_template_id].name == "包内模板"
    assert templates[shared_template_id].name == "共享模板"

    assert view.get_template(shared_template_id) is not None
    assert view.get_template("template_missing") is None


