from __future__ import annotations

from pathlib import Path

from engine.nodes.stubgen import generate_nodes_pyi_stub

from tests._helpers.project_paths import get_repo_root


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_server_node_stub_pyi_is_up_to_date() -> None:
    repo_root = get_repo_root()
    expected = generate_nodes_pyi_stub(repo_root, scope="server")
    actual = _read_text(repo_root / "plugins" / "nodes" / "server" / "__init__.pyi")
    assert actual == expected


def test_client_node_stub_pyi_is_up_to_date() -> None:
    repo_root = get_repo_root()
    expected = generate_nodes_pyi_stub(repo_root, scope="client")
    actual = _read_text(repo_root / "plugins" / "nodes" / "client" / "__init__.pyi")
    assert actual == expected


