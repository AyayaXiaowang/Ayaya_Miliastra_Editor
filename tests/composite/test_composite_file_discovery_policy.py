from __future__ import annotations

from pathlib import Path

from tests._helpers.project_paths import get_repo_root

from engine.nodes.composite_file_policy import (
    discover_composite_definition_files,
    discover_composite_library_dirs,
    is_composite_definition_file,
)
from engine.nodes.composite_node_manager import CompositeNodeManager
from engine.nodes.pipeline.composite_discovery import discover_composite_files


def _is_under_dir(path: Path, root: Path) -> bool:
    path_text = path.resolve().as_posix().rstrip("/")
    root_text = root.resolve().as_posix().rstrip("/")
    return path_text.startswith(root_text + "/")


def test_composite_definition_file_policy_single_source_of_truth() -> None:
    workspace = get_repo_root()
    composite_library_dirs = discover_composite_library_dirs(workspace)
    assert composite_library_dirs

    policy_files = discover_composite_definition_files(workspace)
    pipeline_files = discover_composite_files(workspace)

    assert policy_files == pipeline_files
    assert all(is_composite_definition_file(path) for path in policy_files)
    assert all(any(_is_under_dir(path, root) for root in composite_library_dirs) for path in policy_files)


def test_composite_node_manager_loads_same_files_as_policy() -> None:
    workspace = get_repo_root()

    policy_files = discover_composite_definition_files(workspace)
    manager = CompositeNodeManager(workspace_path=workspace, verbose=False, base_node_library=None)

    loaded_files = sorted(manager.composite_index.values(), key=lambda p: str(p.as_posix()).lower())

    assert loaded_files == policy_files


