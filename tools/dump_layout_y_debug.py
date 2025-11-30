"""
布局Y调试信息巡检脚本。

给定 graph_cache 中的目标图，运行 LayoutService 并统计
哪些节点缺少 `_layout_y_debug_info`，辅助定位“右上角感叹号缺失”问题。

用法（项目根目录）：
    python -X utf8 tools/dump_layout_y_debug.py server_scoreboard_controller_01
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

WORKSPACE = Path(__file__).resolve().parents[1]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from engine.graph.models import GraphModel  # noqa: E402
from engine.layout import LayoutService  # noqa: E402
from engine.configs.settings import settings  # noqa: E402


def _load_graph_from_cache(target_name: str) -> Tuple[GraphModel, Path]:
    cache_dir = WORKSPACE / "app" / "runtime" / "cache" / "graph_cache"
    if not cache_dir.exists():
        print("[ERROR] 未找到缓存目录 app/runtime/cache/graph_cache")
        sys.exit(2)
    normalized_target = target_name.strip().lower()
    for entry in sorted(cache_dir.glob("*.json")):
        data = json.loads(entry.read_text(encoding="utf-8"))
        payload = data.get("result_data", {}) or {}
        graph_data = payload.get("data", {}) or {}
        graph_id = str(graph_data.get("graph_id") or "").lower()
        cache_key = entry.stem.lower()
        if normalized_target in (graph_id, cache_key):
            model = GraphModel.deserialize(graph_data)
            return model, entry
    print(f"[ERROR] 未在 graph_cache 中找到图：{target_name}")
    sys.exit(2)


def _summarize_missing_nodes(model: GraphModel, debug_info: Dict[str, dict]) -> List[Tuple[str, str, str]]:
    missing: List[Tuple[str, str, str]] = []
    for node_id, node in model.nodes.items():
        if node_id not in debug_info:
            missing.append((node_id, node.title, node.category))
    return missing


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python -X utf8 tools/dump_layout_y_debug.py <graph_id_or_cache_name>")
        return 1

    target = sys.argv[1]
    settings.SHOW_LAYOUT_Y_DEBUG = True

    model, source_path = _load_graph_from_cache(target)
    print(f"[INFO] 载入图：{model.graph_name} ({model.graph_id})")
    print(f"[INFO] 来源缓存：{source_path}")

    layout_result = LayoutService.compute_layout(model, include_augmented_model=False)
    debug_info = layout_result.y_debug_info or {}
    total_nodes = len(model.nodes)
    covered = len(debug_info)
    missing = _summarize_missing_nodes(model, debug_info)
    print(f"[INFO] 节点总数：{total_nodes}，含调试信息：{covered}，缺失：{len(missing)}")

    if not missing:
        print("[OK] 所有节点均具备布局Y调试明细。")
        return 0

    print("[WARN] 以下节点缺少布局Y调试信息（最多显示前40个）：")
    for node_id, title, category in missing[:40]:
        print(f"  - {node_id:<14} | {title:<24} | {category}")
    if len(missing) > 40:
        print(f"  ... 其余 {len(missing) - 40} 项省略")
    return 0


if __name__ == "__main__":
    sys.exit(main())

