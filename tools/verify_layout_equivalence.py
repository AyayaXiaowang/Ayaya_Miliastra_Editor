"""
验证布局等价性：对比运行时 graph_cache（默认 app/runtime/cache/graph_cache）中的已缓存坐标与当前 LayoutService 计算结果。

用法：
  python -X utf8 -m tools.verify_layout_equivalence

判定：
  - 同一图内，节点集合必须一致；
  - 所有节点的 |dx|、|dy| <= 1.0 视为等价；
  - 统计总文件数、通过数、失败数，失败详细打印差异摘要。
"""
from __future__ import annotations

import sys
import io
import json
from pathlib import Path
from typing import Dict, Tuple

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")  # type: ignore[attr-defined]

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path
else:
    from _bootstrap import ensure_workspace_root_on_sys_path

WORKSPACE = ensure_workspace_root_on_sys_path()

from engine.graph.models import GraphModel  # noqa: E402
from engine.layout import LayoutService  # noqa: E402
from engine.utils.cache.cache_paths import get_graph_cache_dir  # noqa: E402


def _load_cached_graphs(cache_dir: Path) -> list[tuple[str, GraphModel, Dict[str, Tuple[float, float]]]]:
    items = []
    for fp in sorted(cache_dir.glob("*.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        payload = data.get("result_data", {}) or {}
        graph_data = payload.get("data", {}) or {}
        model = GraphModel.deserialize(graph_data)
        baseline_positions: Dict[str, Tuple[float, float]] = {}
        for nid, node in model.nodes.items():
            x, y = tuple(node.pos)
            baseline_positions[nid] = (float(x), float(y))
        graph_name = graph_data.get("graph_name", fp.stem)
        items.append((graph_name, model, baseline_positions))
    return items


def verify_equivalence(tol: float = 1.0) -> int:
    cache_dir = get_graph_cache_dir(WORKSPACE)
    if not cache_dir.exists():
        print(f"[ERROR] 未找到 graph_cache 目录：{cache_dir}")
        return 2

    entries = _load_cached_graphs(cache_dir)
    if not entries:
        print("[ERROR] 未找到任何缓存的图数据。请先运行一次主程序或相关工具以生成缓存。")
        return 2

    total = len(entries)
    failures = 0

    for graph_name, model, baseline in entries:
        # 纯计算布局，不修改原模型
        result = LayoutService.compute_layout(model, workspace_path=WORKSPACE)
        # 先比节点集合
        if set(result.positions.keys()) != set(baseline.keys()):
            print(f"[DIFF] 节点集合不一致：{graph_name}")
            print(f"  期望节点数={len(baseline)}, 实际节点数={len(result.positions)}")
            failures += 1
            continue
        # 比坐标差
        bad = []
        for nid in sorted(baseline.keys()):
            bx, by = baseline[nid]
            rx, ry = result.positions.get(nid, (None, None))  # type: ignore[assignment]
            if rx is None or ry is None:
                bad.append((nid, "missing", (bx, by), (rx, ry)))
                continue
            dx = abs(float(rx) - float(bx))
            dy = abs(float(ry) - float(by))
            if dx > tol or dy > tol:
                bad.append((nid, f"dx={dx:.2f}, dy={dy:.2f}", (bx, by), (rx, ry)))
        if bad:
            failures += 1
            print(f"[DIFF] {graph_name} 存在位置差异（容差={tol}）：{len(bad)} 个节点")
            for nid, reason, (bx, by), (rx, ry) in bad[:10]:
                print(f"  - {nid}: {reason} baseline=({bx:.1f},{by:.1f}) now=({rx:.1f},{ry:.1f})")
            if len(bad) > 10:
                print(f"  ... 其余 {len(bad) - 10} 项省略")
        else:
            print(f"[OK] 等价：{graph_name}")

    print("=" * 72)
    print(f"总图数: {total}  失败: {failures}  通过: {total - failures}")
    return 0 if failures == 0 else 1


def main() -> int:
    return verify_equivalence(tol=1.0)


if __name__ == "__main__":
    sys.exit(main())



