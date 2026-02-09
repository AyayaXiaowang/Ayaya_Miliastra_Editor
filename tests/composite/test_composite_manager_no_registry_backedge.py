from __future__ import annotations

from pathlib import Path

import pytest

import engine.nodes.composite_node_manager as composite_manager_module
import engine.nodes.node_registry as node_registry_module
from engine.nodes.composite_node_manager import (
    clear_global_composite_node_manager_for_tests,
    get_composite_node_manager,
)
from engine.nodes.composite_node_loader import CompositeNodeLoader


def test_get_composite_node_manager_does_not_call_node_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clear_global_composite_node_manager_for_tests()

    def forbidden_get_node_registry(*args: object, **kwargs: object) -> object:
        raise AssertionError("get_composite_node_manager 不应隐式调用 get_node_registry")

    monkeypatch.setattr(node_registry_module, "get_node_registry", forbidden_get_node_registry)
    monkeypatch.setattr(composite_manager_module, "load_all_nodes_from_impl", lambda *args, **kwargs: {})

    manager = get_composite_node_manager(workspace_path=tmp_path, verbose=False)
    assert manager.workspace_path == tmp_path.resolve()


def test_get_composite_node_manager_cached_by_workspace(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    clear_global_composite_node_manager_for_tests()
    monkeypatch.setattr(composite_manager_module, "load_all_nodes_from_impl", lambda *args, **kwargs: {})

    ws1 = tmp_path_factory.mktemp("ws1")
    ws2 = tmp_path_factory.mktemp("ws2")

    manager1a = get_composite_node_manager(workspace_path=ws1, verbose=False)
    manager1b = get_composite_node_manager(workspace_path=ws1, verbose=False)
    manager2 = get_composite_node_manager(workspace_path=ws2, verbose=False)

    assert manager1a is manager1b
    assert manager1a is not manager2


def test_composite_node_loader_requires_base_node_library_for_subgraph(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    composite_library_dir = tmp_path / "assets" / "资源库" / "复合节点库"
    composite_library_dir.mkdir(parents=True, exist_ok=True)
    composite_file = composite_library_dir / "composite_test.py"
    composite_file.write_text("# dummy", encoding="utf-8")

    loader = CompositeNodeLoader(
        workspace_path=tmp_path,
        composite_library_dir=composite_library_dir,
        verbose=False,
        base_node_library=None,
    )

    with pytest.raises(ValueError, match="需要注入 base_node_library"):
        loader.load_composite_from_file(composite_file, load_subgraph=True)


