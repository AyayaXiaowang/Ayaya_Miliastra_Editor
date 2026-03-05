from __future__ import annotations

from pathlib import Path
import threading

import pytest

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import NodeRegistry, NodeRegistryRecursiveLoadError
import engine.nodes.node_registry as node_registry_module


def test_node_registry_recursive_load_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry = NodeRegistry(workspace_path=tmp_path, include_composite=False)

    monkeypatch.setattr(registry, "_load_persistent_node_library", lambda: None)
    monkeypatch.setattr(registry, "_save_persistent_node_library", lambda library: None)

    def fake_load_all_nodes(*args: object, **kwargs: object) -> dict[str, NodeDef]:
        registry.get_library()
        return {}

    monkeypatch.setattr(node_registry_module, "load_all_nodes", fake_load_all_nodes)

    with pytest.raises(NodeRegistryRecursiveLoadError):
        registry.get_library()

    # 失败后必须复位加载状态，否则会把后续调用永久卡死在“加载中”
    assert registry._is_loading is False


def test_node_registry_concurrent_get_library_waits_for_loading(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry = NodeRegistry(workspace_path=tmp_path, include_composite=False)

    monkeypatch.setattr(registry, "_load_persistent_node_library", lambda: None)
    monkeypatch.setattr(registry, "_save_persistent_node_library", lambda library: None)

    entered_loader_event = threading.Event()
    allow_loader_finish_event = threading.Event()

    expected_key = "测试类别/测试节点"
    expected_node = NodeDef(name="测试节点", category="测试类别")
    expected_library = {expected_key: expected_node}

    def fake_load_all_nodes(*args: object, **kwargs: object) -> dict[str, NodeDef]:
        entered_loader_event.set()
        allow_loader_finish_event.wait(timeout=5.0)
        return dict(expected_library)

    monkeypatch.setattr(node_registry_module, "load_all_nodes", fake_load_all_nodes)

    loader_thread_exception: list[BaseException] = []
    loader_thread_result: dict[str, dict[str, NodeDef]] = {}

    def loader_thread_target() -> None:
        try:
            loader_thread_result["library"] = registry.get_library()
        except BaseException as exc:
            loader_thread_exception.append(exc)

    loader_thread = threading.Thread(target=loader_thread_target, name="test_node_registry_loader")
    loader_thread.start()

    assert entered_loader_event.wait(timeout=5.0)

    waiter_thread_exception: list[BaseException] = []
    waiter_thread_result: dict[str, dict[str, NodeDef]] = {}

    def waiter_thread_target() -> None:
        try:
            waiter_thread_result["library"] = registry.get_library()
        except BaseException as exc:
            waiter_thread_exception.append(exc)

    waiter_thread = threading.Thread(target=waiter_thread_target, name="test_node_registry_waiter")
    waiter_thread.start()

    # 在 loader 还未放行前，waiter 必须卡在等待中（不能返回空库）
    waiter_thread.join(timeout=0.2)
    assert waiter_thread.is_alive() is True

    allow_loader_finish_event.set()
    loader_thread.join(timeout=5.0)
    waiter_thread.join(timeout=5.0)

    assert loader_thread_exception == []
    assert waiter_thread_exception == []
    assert loader_thread_result["library"][expected_key].name == expected_node.name
    assert waiter_thread_result["library"][expected_key].name == expected_node.name


