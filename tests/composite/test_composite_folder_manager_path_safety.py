from __future__ import annotations

from pathlib import Path

from engine.nodes.composite_folder_manager import CompositeFolderManager


def _write_marker_file(directory_path: Path, file_name: str = "marker.txt") -> Path:
    directory_path.mkdir(parents=True, exist_ok=True)
    marker_file = directory_path / file_name
    marker_file.write_text("keep", encoding="utf-8")
    return marker_file


def test_create_folder_rejects_path_traversal_in_folder_name(tmp_path: Path) -> None:
    composite_library_dir = tmp_path / "composites"
    composite_library_dir.mkdir(parents=True, exist_ok=True)
    manager = CompositeFolderManager(composite_library_dir)
    manager.scan_folders()

    outside_dir = tmp_path / "outside_should_not_be_touched"
    marker_file = _write_marker_file(outside_dir)

    assert manager.create_folder("合法目录", "") is True

    assert manager.create_folder("..", "") is False
    assert manager.create_folder("../escape", "") is False
    assert manager.create_folder(r"..\..\escape", "") is False

    assert outside_dir.exists() is True
    assert marker_file.exists() is True


def test_create_folder_rejects_path_traversal_in_parent_folder(tmp_path: Path) -> None:
    composite_library_dir = tmp_path / "composites"
    composite_library_dir.mkdir(parents=True, exist_ok=True)
    manager = CompositeFolderManager(composite_library_dir)
    manager.scan_folders()

    outside_dir = tmp_path / "outside_should_not_be_touched"
    marker_file = _write_marker_file(outside_dir)

    assert manager.create_folder("parent", "") is True
    assert manager.create_folder("child", "parent") is True

    assert manager.create_folder("escape", "..") is False
    assert manager.create_folder("escape", "../") is False
    assert manager.create_folder("escape", r"..\..") is False
    assert manager.create_folder("escape", "parent/../..") is False

    assert outside_dir.exists() is True
    assert marker_file.exists() is True


def test_create_folder_rejects_absolute_paths(tmp_path: Path) -> None:
    composite_library_dir = tmp_path / "composites"
    composite_library_dir.mkdir(parents=True, exist_ok=True)
    manager = CompositeFolderManager(composite_library_dir)
    manager.scan_folders()

    assert manager.create_folder("/abs", "") is False
    assert manager.create_folder(r"\\server\share", "") is False
    assert manager.create_folder(r"C:\Windows\Temp", "") is False
    assert manager.create_folder("safe", r"C:\Windows\Temp") is False


def test_delete_folder_rejects_traversal_and_does_not_delete_outside(tmp_path: Path) -> None:
    composite_library_dir = tmp_path / "composites"
    composite_library_dir.mkdir(parents=True, exist_ok=True)
    manager = CompositeFolderManager(composite_library_dir)
    manager.scan_folders()

    outside_dir = tmp_path / "outside_should_not_be_touched"
    marker_file = _write_marker_file(outside_dir)

    assert manager.create_folder("safe", "") is True

    assert manager.delete_folder("..", [], force=True) is False
    assert manager.delete_folder("../outside_should_not_be_touched", [], force=True) is False
    assert manager.delete_folder(r"..\outside_should_not_be_touched", [], force=True) is False
    assert manager.delete_folder(r"C:\Windows\Temp", [], force=True) is False
    assert manager.delete_folder(r"\\server\share", [], force=True) is False

    assert outside_dir.exists() is True
    assert marker_file.exists() is True

    assert (composite_library_dir / "safe").exists() is True
    assert manager.delete_folder("safe", [], force=True) is True
    assert (composite_library_dir / "safe").exists() is False


