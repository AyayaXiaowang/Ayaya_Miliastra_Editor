"""
跨块复制 / 布局调试小工具

用途：
- 直接从节点图 Python 源文件解析 GraphModel；
- 通过 LayoutService 执行一次完整布局（含跨块复制与副本处理）；
- 按节点标题子串筛选目标节点，输出其所在基本块、位置信息与入/出边摘要。

用法（在项目根目录执行）：
  python -X utf8 -m tools.debug_cross_block_copy assets/资源库/节点图/server/锻刀/打造/锻刀英雄_武器展示与选择_界面事件.py 是否相等
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path
else:
    from _bootstrap import ensure_workspace_root_on_sys_path

WORKSPACE = ensure_workspace_root_on_sys_path()


from engine.nodes.node_registry import get_node_registry  # noqa: E402
from engine.graph.graph_code_parser import GraphCodeParser  # noqa: E402
from engine.layout import LayoutService  # noqa: E402
from engine.configs.settings import settings  # noqa: E402


def _resolve_code_path(arg: str) -> Path:
    candidate = Path(arg)
    if not candidate.is_absolute():
        candidate = WORKSPACE / candidate
    return candidate


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "用法: python -X utf8 tools/debug_cross_block_copy.py "
            "<graph_py_path> [title_substring]"
        )
        sys.exit(1)

    code_path = _resolve_code_path(sys.argv[1])
    if not code_path.exists():
        print(f"文件不存在: {code_path}")
        sys.exit(1)

    title_substring = sys.argv[2] if len(sys.argv) >= 3 else ""

    # GraphCodeParser 解析阶段会触发一次 quiet layout，需要 settings 中可推导 workspace_path
    settings.set_config_path(WORKSPACE)

    registry = get_node_registry(WORKSPACE, include_composite=True)
    node_library = registry.get_library()

    parser = GraphCodeParser(WORKSPACE, node_library=node_library, verbose=False)
    model, metadata = parser.parse_file(code_path)

    layout_result = LayoutService.compute_layout(
        model,
        node_library=node_library,
        include_augmented_model=True,
        clone_model=True,
        write_back_to_input_model=False,
        workspace_path=WORKSPACE,
    )
    augmented = layout_result.augmented_model

    if augmented is None:
        print("布局服务未返回增强模型（augmented_model is None）")
        sys.exit(1)

    debug_map = getattr(augmented, "_layout_y_debug_info", {}) or {}

    # 按标题子串筛选目标节点（若未提供子串，则列出所有数据副本节点）
    targets: List[Dict[str, Any]] = []
    for node_id, node_obj in augmented.nodes.items():
        title_value = getattr(node_obj, "title", "")
        is_copy = bool(getattr(node_obj, "is_data_node_copy", False))

        if title_substring:
            if not isinstance(title_value, str):
                continue
            if title_substring not in title_value:
                continue
        else:
            if not is_copy:
                continue

        pos_value = getattr(node_obj, "pos", (0.0, 0.0)) or (0.0, 0.0)
        pos_x = float(pos_value[0]) if len(pos_value) > 0 else 0.0
        pos_y = float(pos_value[1]) if len(pos_value) > 1 else 0.0

        debug_info_raw = debug_map.get(node_id, {})
        debug_chains = []
        if isinstance(debug_info_raw, dict):
            chains_value = debug_info_raw.get("chains")
            if isinstance(chains_value, list):
                debug_chains = list(chains_value)

        targets.append(
            {
                "id": str(node_id),
                "title": str(title_value),
                "is_data_node_copy": is_copy,
                "original_node_id": getattr(node_obj, "original_node_id", ""),
                "copy_block_id": getattr(node_obj, "copy_block_id", ""),
                "pos": [pos_x, pos_y],
                "debug_chain_count": len(debug_chains),
                "debug_chains": debug_chains,
            }
        )

    if not targets:
        print("未找到匹配节点。")
        print(f"图文件: {code_path}")
        print(f"节点总数: {len(augmented.nodes)}")
        sys.exit(0)

    # 统计每个目标节点所在的基本块索引（可能属于多个块时会全部列出）
    block_membership: Dict[str, List[int]] = {}
    basic_blocks = list(getattr(augmented, "basic_blocks", None) or [])
    for index, block in enumerate(basic_blocks, start=1):
        node_ids_in_block = list(getattr(block, "nodes", []) or [])
        for info in targets:
            node_id = info["id"]
            if node_id in node_ids_in_block:
                bucket = block_membership.setdefault(node_id, [])
                if index not in bucket:
                    bucket.append(index)

    # 统计每个目标节点在 LayoutBlock 缓存中的归属（flow_nodes + data_nodes）
    layout_block_membership: Dict[str, List[int]] = {}
    layout_blocks_cache = getattr(augmented, "_layout_blocks_cache", None)
    if isinstance(layout_blocks_cache, list):
        for index, layout_block in enumerate(layout_blocks_cache, start=1):
            flow_ids = list(getattr(layout_block, "flow_nodes", []) or [])
            data_ids = list(getattr(layout_block, "data_nodes", []) or [])
            all_ids = flow_ids + data_ids
            if not all_ids:
                continue
            for info in targets:
                node_id = info["id"]
                if node_id in all_ids:
                    bucket = layout_block_membership.setdefault(node_id, [])
                    if index not in bucket:
                        bucket.append(index)

    # 统计每个目标节点的入/出数据边
    edge_summary: Dict[str, Dict[str, Any]] = {}
    for info in targets:
        node_id = info["id"]
        outgoing: List[Dict[str, Any]] = []
        incoming: List[Dict[str, Any]] = []
        for edge_id, edge_obj in augmented.edges.items():
            if edge_obj.src_node == node_id:
                outgoing.append(
                    {
                        "id": edge_id,
                        "dst_node": edge_obj.dst_node,
                        "dst_port": edge_obj.dst_port,
                    }
                )
            if edge_obj.dst_node == node_id:
                incoming.append(
                    {
                        "id": edge_id,
                        "src_node": edge_obj.src_node,
                        "src_port": edge_obj.src_port,
                    }
                )
        edge_summary[node_id] = {
            "outgoing": outgoing,
            "incoming": incoming,
        }

    payload = {
        "graph_file": str(code_path),
        "graph_id": getattr(augmented, "graph_id", metadata.get("graph_id", "")),
        "targets": targets,
        "block_membership": block_membership,
        "layout_blocks": layout_block_membership,
        "edges": edge_summary,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


