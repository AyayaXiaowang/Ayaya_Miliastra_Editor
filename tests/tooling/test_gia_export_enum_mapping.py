from __future__ import annotations

import sys
from pathlib import Path


def _ensure_private_extensions_importable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    private_extensions_root = (repo_root / "private_extensions").resolve()
    if str(private_extensions_root) not in sys.path:
        sys.path.insert(0, str(private_extensions_root))


def test_gia_export_enum_item_id_mapping_smoke() -> None:
    """
    回归：`.gia` 导出时，枚举输入常量（中文选项）必须能稳定映射到 enum item id。

    这里选用 enum_codec 内置的“样本直写兜底”路径，避免依赖真实 NodeDef/节点库加载：
    - 节点：设置扫描标签的规则
    - 端口：规则类型
    - 选项：视野优先 -> 5100
    """
    _ensure_private_extensions_importable()

    from ugc_file_tools.node_graph_semantics.enum_codec import (
        build_entry_by_id_map,
        load_node_data_index_doc,
        resolve_enum_item_id_for_input_constant,
    )

    class _DummyNodeDef:
        name = "设置扫描标签的规则"
        input_enum_options = {"规则类型": ["视野优先", "距离优先"]}

    node_data_doc = load_node_data_index_doc()
    node_entry_by_id = build_entry_by_id_map(node_data_doc.get("NodesList"))
    enum_entry_by_id = build_entry_by_id_map(node_data_doc.get("EnumList"))

    item_id = resolve_enum_item_id_for_input_constant(
        node_type_id_int=123456,
        slot_index=0,
        port_name="规则类型",
        raw_value="视野优先",
        node_def=_DummyNodeDef(),
        node_entry_by_id=node_entry_by_id,
        enum_entry_by_id=enum_entry_by_id,
    )
    assert item_id == 5100


def test_gia_asset_bundle_builder_importable() -> None:
    """回归：`.gia` 导出模块可被导入（避免 NameError / 循环依赖）。"""
    _ensure_private_extensions_importable()

    from ugc_file_tools.gia_export.node_graph import asset_bundle_builder as _unused  # noqa: F401

