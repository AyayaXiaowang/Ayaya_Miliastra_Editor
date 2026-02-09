from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


def _ensure_shape_editor_backend_importable() -> None:
    # `private_extensions/shape-editor` uses a hyphen in directory name, so it isn't a normal Python package.
    # The runtime plugin injects these paths into sys.path; tests should do the same.
    workspace_root = Path(__file__).resolve().parents[2]
    plugin_dir = (workspace_root / "private_extensions" / "shape-editor").resolve()
    private_ext_root = plugin_dir.parent.resolve()
    plugin_dir_text = str(plugin_dir)
    if plugin_dir_text not in sys.path:
        sys.path.insert(0, plugin_dir_text)
    private_ext_root_text = str(private_ext_root)
    if private_ext_root_text not in sys.path:
        sys.path.insert(0, private_ext_root_text)


_ensure_shape_editor_backend_importable()

from shape_editor_backend.project_persistence import (  # noqa: E402
    create_blank_entity_in_project,
    ensure_canvas_persisted_in_project,
    list_project_entity_placements,
    read_project_entity_placement,
)
from shape_editor_backend.settings import load_shape_editor_settings  # noqa: E402


def _make_resource_library_dir(tmp_path: Path, *, package_id: str) -> Path:
    # project_persistence.resolve_project_root() uses engine.get_packages_root_dir(resource_library_dir)
    # In this repo, resource_library_dir corresponds to “assets/资源库/”.
    resource_library_dir = (tmp_path / "资源库").resolve()
    packages_root = (resource_library_dir / "项目存档").resolve()
    packages_root.mkdir(parents=True, exist_ok=True)
    # project_persistence expects the project root dir to already exist.
    (packages_root / str(package_id)).mkdir(parents=True, exist_ok=True)
    return resource_library_dir


def _count_payload_objects(*, placement_file: Path) -> int:
    obj = json.loads(placement_file.read_text(encoding="utf-8-sig"))
    se = (((obj.get("metadata") or {}).get("shape_editor") or {}) if isinstance(obj.get("metadata"), dict) else {})
    payload = se.get("canvas_payload") if isinstance(se, dict) else None
    if not isinstance(payload, dict):
        return -1
    objects = payload.get("objects")
    if not isinstance(objects, list):
        return -1
    return len(objects)


def _payload_with_n_objects(*, n: int, target_rel_path: str) -> dict:
    # Minimal canvas payload shape used by frontend buildGiaExportPayload()
    objs = []
    for i in range(int(n)):
        objs.append(
            {
                "type": "rect" if i % 2 == 0 else "circle",
                "label": f"obj_{i}",
                "color": "#FBAF5C" if i % 2 == 0 else "#F3D199",
                "left": 100 + i * 10,
                "top": 200 + i * 10,
                "width": 100,
                "height": 80,
                "angle": 0,
                "opacity": 1.0,
                "isReference": False,
                "isLocked": False,
            }
        )
    return {
        "meta": {
            "tool": "pytest",
            "mode": "gia_decorations_group",
            "target_rel_path": str(target_rel_path or "").strip(),
        },
        "canvas": {"width": 1600, "height": 900},
        "objects": objs,
    }


def test_create_blank_entity_and_save_overwrites_same_file(tmp_path: Path) -> None:
    package_id = "测试项目"
    resource_library_dir = _make_resource_library_dir(tmp_path, package_id=package_id)
    settings_obj = load_shape_editor_settings()

    created = create_blank_entity_in_project(
        workspace_root=tmp_path,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        settings_obj=settings_obj,
        instance_name="拼贴画画布",
    )
    assert created["ok"] is True
    rel_path = str(created["rel_path"])
    assert rel_path.startswith("实体摆放/")
    assert rel_path.endswith(".json")

    project_root = resource_library_dir / "项目存档" / package_id
    placement_file = (project_root / rel_path).resolve()
    assert placement_file.is_file()
    assert _count_payload_objects(placement_file=placement_file) == 0

    # First save: write 4 objects into that exact entity file.
    payload = _payload_with_n_objects(n=4, target_rel_path=rel_path)
    saved = ensure_canvas_persisted_in_project(
        workspace_root=tmp_path,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        canvas_payload=payload,
        settings_obj=settings_obj,
        target_rel_path=rel_path,
        bump_export_seq=False,
    )
    assert saved["ok"] is True
    assert str(saved["rel_path"]) == rel_path
    assert _count_payload_objects(placement_file=placement_file) == 4

    # Second save: overwrite with 2 objects, still same file (no new entity created).
    payload2 = _payload_with_n_objects(n=2, target_rel_path=rel_path)
    saved2 = ensure_canvas_persisted_in_project(
        workspace_root=tmp_path,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        canvas_payload=payload2,
        settings_obj=settings_obj,
        target_rel_path=rel_path,
        bump_export_seq=False,
    )
    assert saved2["ok"] is True
    assert str(saved2["rel_path"]) == rel_path
    assert _count_payload_objects(placement_file=placement_file) == 2


def test_save_with_empty_target_rel_path_writes_canvas_instance(tmp_path: Path) -> None:
    package_id = "测试项目"
    resource_library_dir = _make_resource_library_dir(tmp_path, package_id=package_id)
    settings_obj = load_shape_editor_settings()

    payload = _payload_with_n_objects(n=3, target_rel_path="")
    saved = ensure_canvas_persisted_in_project(
        workspace_root=tmp_path,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        canvas_payload=payload,
        settings_obj=settings_obj,
        target_rel_path="",
        bump_export_seq=False,
    )
    assert saved["ok"] is True
    assert str(saved["rel_path"]) == "实体摆放/shape_editor_canvas_instance.json"

    project_root = resource_library_dir / "项目存档" / package_id
    placement_file = (project_root / "实体摆放" / "shape_editor_canvas_instance.json").resolve()
    assert placement_file.is_file()
    assert _count_payload_objects(placement_file=placement_file) == 3


def test_list_and_read_entity_placements_roundtrip(tmp_path: Path) -> None:
    package_id = "测试项目"
    resource_library_dir = _make_resource_library_dir(tmp_path, package_id=package_id)
    settings_obj = load_shape_editor_settings()

    # Create two entities with different contents.
    e1 = create_blank_entity_in_project(
        workspace_root=tmp_path,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        settings_obj=settings_obj,
        instance_name="拼贴画画布",
    )
    e2 = create_blank_entity_in_project(
        workspace_root=tmp_path,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        settings_obj=settings_obj,
        instance_name="拼贴画画布",
    )
    rel1 = str(e1["rel_path"])
    rel2 = str(e2["rel_path"])

    ensure_canvas_persisted_in_project(
        workspace_root=tmp_path,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        canvas_payload=_payload_with_n_objects(n=1, target_rel_path=rel1),
        settings_obj=settings_obj,
        target_rel_path=rel1,
        bump_export_seq=False,
    )
    ensure_canvas_persisted_in_project(
        workspace_root=tmp_path,
        resource_library_dir=resource_library_dir,
        package_id=package_id,
        canvas_payload=_payload_with_n_objects(n=5, target_rel_path=rel2),
        settings_obj=settings_obj,
        target_rel_path=rel2,
        bump_export_seq=False,
    )

    cat = list_project_entity_placements(resource_library_dir=resource_library_dir, package_id=package_id, settings_obj=settings_obj)
    assert cat["ok"] is True
    rels = {str(it["rel_path"]) for it in (cat.get("placements") or [])}
    assert rel1 in rels
    assert rel2 in rels

    r1 = read_project_entity_placement(resource_library_dir=resource_library_dir, package_id=package_id, rel_path=rel1, settings_obj=settings_obj)
    assert r1["ok"] is True
    assert str(r1["rel_path"]) == rel1
    assert isinstance(r1.get("canvas_payload"), dict)
    assert len(r1["canvas_payload"]["objects"]) == 1

    r2 = read_project_entity_placement(resource_library_dir=resource_library_dir, package_id=package_id, rel_path=rel2, settings_obj=settings_obj)
    assert r2["ok"] is True
    assert str(r2["rel_path"]) == rel2
    assert isinstance(r2.get("canvas_payload"), dict)
    assert len(r2["canvas_payload"]["objects"]) == 5

