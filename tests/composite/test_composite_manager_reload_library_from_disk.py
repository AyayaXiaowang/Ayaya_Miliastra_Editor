from __future__ import annotations

import json
from pathlib import Path

from engine.nodes.composite_node_manager import CompositeNodeManager


def _write_payload_composite_file(file_path: Path, *, composite_id: str, node_name: str) -> None:
    payload = {
        "composite_id": composite_id,
        "node_name": node_name,
        "node_description": "",
        "scope": "server",
        "virtual_pins": [
            {
                "pin_index": 1,
                "pin_name": "流程入",
                "pin_type": "流程",
                "is_input": True,
                "is_flow": True,
                "description": "",
                "mapped_ports": [],
            }
        ],
        "sub_graph": {"nodes": [], "edges": [], "graph_variables": []},
        "folder_path": "",
        "doc_reference": "复合节点.md",
        "notes": "",
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    file_path.write_text(f"COMPOSITE_PAYLOAD_JSON = {payload_json!r}\n", encoding="utf-8")


def test_composite_node_manager_reload_library_from_disk(tmp_path: Path) -> None:
    composite_library_dir = tmp_path / "assets" / "资源库" / "共享" / "复合节点库"
    composite_library_dir.mkdir(parents=True, exist_ok=True)

    composite_id = "composite_test_reload"
    composite_file_path = composite_library_dir / f"{composite_id}.py"

    _write_payload_composite_file(
        composite_file_path,
        composite_id=composite_id,
        node_name="旧名称",
    )

    manager = CompositeNodeManager(
        tmp_path,
        verbose=False,
        base_node_library={},
    )
    loaded = manager.get_composite_node(composite_id)
    assert loaded is not None
    assert loaded.node_name == "旧名称"

    _write_payload_composite_file(
        composite_file_path,
        composite_id=composite_id,
        node_name="新名称",
    )

    manager.reload_library_from_disk()
    reloaded = manager.get_composite_node(composite_id)
    assert reloaded is not None
    assert reloaded.node_name == "新名称"


