from __future__ import annotations

from engine.nodes.node_definition_loader import NodeDef
from engine.validate.node_def_resolver import normalize_category_to_standard, resolve_node_def_from_library


def test_normalize_category_to_standard_appends_suffix() -> None:
    assert normalize_category_to_standard("执行") == "执行节点"
    assert normalize_category_to_standard("执行节点") == "执行节点"


def test_resolve_node_def_prefers_scope_variant_when_scope_given() -> None:
    node_base = NodeDef(name="测试", category="执行节点")
    node_scoped = NodeDef(name="测试", category="执行节点")
    node_library = {
        "执行节点/测试": node_base,
        "执行节点/测试#server": node_scoped,
    }
    resolved = resolve_node_def_from_library(
        node_library,
        node_category="执行节点",
        node_title="测试",
        scope_text="server",
    )
    assert resolved is not None
    assert resolved.key == "执行节点/测试#server"


def test_resolve_node_def_prefers_explicit_scope_suffix_in_title() -> None:
    node_client = NodeDef(name="测试", category="执行节点")
    node_server = NodeDef(name="测试", category="执行节点")
    node_library = {
        "执行节点/测试#client": node_client,
        "执行节点/测试#server": node_server,
    }
    resolved = resolve_node_def_from_library(
        node_library,
        node_category="执行节点",
        node_title="测试#client",
        scope_text="server",
    )
    assert resolved is not None
    assert resolved.key == "执行节点/测试#client"


def test_resolve_node_def_falls_back_to_other_scope_when_base_key_missing() -> None:
    node_client = NodeDef(name="测试", category="执行节点")
    node_library = {
        "执行节点/测试#client": node_client,
    }
    resolved = resolve_node_def_from_library(
        node_library,
        node_category="执行",
        node_title="测试",
        scope_text=None,
    )
    assert resolved is not None
    assert resolved.key == "执行节点/测试#client"


