from __future__ import annotations

from engine.nodes.pipeline.merger import merge_specs
from engine.nodes.pipeline.indexer import build_index
from engine.nodes.pipeline.lookup import get_by_alias


def test_unscoped_alias_must_not_point_to_scoped_variant() -> None:
    """
    回归：当同一 `类别/名称` 在不同作用域下端口不兼容时，merger 会生成 `#scope` 变体。
    indexer 构建 alias_to_key 时必须保证：
    - `类别/名称`（不带 #）永远指向基键 `类别/名称`
    - `类别/名称#scope` 才指向 scoped 变体键
    """
    category_standard = "执行节点"
    name_text = "同名节点"
    standard_key = f"{category_standard}/{name_text}"

    client_item = {
        "standard_key": standard_key,
        "category_standard": category_standard,
        "name": name_text,
        "aliases": ["别名A"],
        "scopes": ["client"],
        "inputs": [["流程入", "流程"]],
        "outputs": [["流程出", "流程"]],
        "input_types": {"流程入": "流程", "参数": "整数"},
        "output_types": {"流程出": "流程"},
        "dynamic_port_type": "",
        "input_generic_constraints": {},
        "output_generic_constraints": {},
    }

    server_item = {
        "standard_key": standard_key,
        "category_standard": category_standard,
        "name": name_text,
        "aliases": ["别名A"],
        "scopes": ["server"],
        "inputs": [["流程入", "流程"]],
        "outputs": [["流程出", "流程"]],
        # 关键：端口不兼容（client=整数，server=浮点数）
        "input_types": {"流程入": "流程", "参数": "浮点数"},
        "output_types": {"流程出": "流程"},
        "dynamic_port_type": "",
        "input_generic_constraints": {},
        "output_generic_constraints": {},
    }

    library_by_key = merge_specs([client_item, server_item])
    index = build_index(library_by_key)

    # 不带 scope 的 alias 必须指向基键（server 优先）
    resolved = get_by_alias(index, category_standard, name_text)
    assert resolved is not None
    resolved_key, _ = resolved
    assert resolved_key == standard_key

    # 显式带 scope 时，应该能命中对应变体（别名 + #scope 也应可解析）
    resolved_client = get_by_alias(index, category_standard, f"{name_text}#client")
    assert resolved_client is not None
    resolved_client_key, _ = resolved_client
    assert resolved_client_key == f"{standard_key}#client"

    resolved_client_by_alias = get_by_alias(index, category_standard, "别名A#client")
    assert resolved_client_by_alias is not None
    resolved_client_by_alias_key, _ = resolved_client_by_alias
    assert resolved_client_by_alias_key == f"{standard_key}#client"


