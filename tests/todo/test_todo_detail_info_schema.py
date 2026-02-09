from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.models.resource_task_configs import COMBAT_RESOURCE_CONFIGS, MANAGEMENT_RESOURCE_CONFIGS
from app.models.todo_detail_info_schema import get_detail_info_schema, validate_detail_info
from tests._helpers.project_paths import get_repo_root


def _workspace_root() -> Path:
    return get_repo_root()


def _collect_literal_detail_types_from_models() -> set[str]:
    """静态提取 app/models 中“直接写死的 detail_info['type'] 字面量集合”。

    目的：
    - 避免实例化 package/resource_manager 等重量对象；
    - 确保新增 detail_type 时必须同步补齐 schema（否则测试失败）。
    """

    root = _workspace_root()
    model_files = [
        root / "app" / "models" / "todo_generator.py",
        root / "app" / "models" / "todo_graph_task_generator.py",
        root / "app" / "models" / "todo_builder_helpers.py",
        root / "app" / "models" / "todo_graph_tasks" / "event_flow_emitters.py",
        root / "app" / "models" / "todo_graph_tasks" / "composite.py",
    ]

    collected: set[str] = set()

    for path in model_files:
        source = path.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(path))
        for node in ast.walk(module):
            if not isinstance(node, ast.Dict):
                continue

            type_key_index = -1
            for index, key in enumerate(node.keys):
                if isinstance(key, ast.Constant) and key.value == "type":
                    type_key_index = index
                    break
            if type_key_index == -1:
                continue

            value_node = node.values[type_key_index]
            if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                collected.add(value_node.value)

    return collected


def _collect_resource_detail_types() -> set[str]:
    return {cfg.detail_type for cfg in list(COMBAT_RESOURCE_CONFIGS) + list(MANAGEMENT_RESOURCE_CONFIGS)}


def test_detail_info_schema_covers_all_emitted_detail_types() -> None:
    emitted = _collect_literal_detail_types_from_models() | _collect_resource_detail_types()
    missing = sorted([t for t in emitted if get_detail_info_schema(t) is None])
    assert not missing, "发现未注册 schema 的 detail_type：\n" + "\n".join(missing)


def test_validate_detail_info_rejects_missing_required_fields() -> None:
    bad = {"type": "graph_create_node", "graph_id": "g1", "node_title": "n", "no_auto_jump": False}
    with pytest.raises(RuntimeError):
        validate_detail_info(bad, strict=True)


def test_validate_detail_info_allows_optional_none_fields() -> None:
    ok = {
        "type": "graph_bind_signal",
        "graph_id": "g1",
        "node_id": "n1",
        "node_title": "节点",
        "signal_id": None,
        "signal_name": "",
    }
    validate_detail_info(ok, strict=True)


@pytest.mark.parametrize(
    "detail_type",
    [
        "graph_add_variadic_inputs",
        "graph_add_dict_pairs",
        "graph_add_branch_outputs",
    ],
)
def test_detail_info_schema_covers_dynamic_port_step_types(detail_type: str) -> None:
    assert get_detail_info_schema(detail_type) is not None
    validate_detail_info(
        {
            "type": detail_type,
            "graph_id": "g1",
            "node_id": "n1",
            "node_title": "节点",
            "add_count": 1,
            "port_tokens": ["0"],
            "no_auto_jump": False,
        },
        strict=True,
    )


