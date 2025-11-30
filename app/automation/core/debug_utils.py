"""核心调试工具集：供执行器与识别模块共享的日志逻辑。"""

from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from engine.graph.models.graph_model import GraphModel, NodeModel


def log_branch_ambiguity_report(
    logger: Callable[[str, object | None], None],
    graph_model: GraphModel,
    name_to_model_nodes: Dict[str, List[NodeModel]],
    name_to_detections: Dict[str, List[Tuple[int, int, int, int]]],
    scale: float,
    tx: float,
    ty: float,
    epsilon_px: float,
    log_callback=None,
    *,
    max_items: int = 8,
) -> None:
    """输出同名节点的残差/间隙报告，帮助诊断映射歧义。"""

    ambiguous_names: List[str] = []
    merged_names = set(name_to_model_nodes.keys()) | set(name_to_detections.keys())
    for name in sorted(merged_names):
        model_count = len(name_to_model_nodes.get(name, []))
        detect_count = len(name_to_detections.get(name, []))
        if model_count > 1 or detect_count > 1:
            ambiguous_names.append(name)

    if not ambiguous_names:
        logger("[调试] 无重名标题，歧义报告为空", log_callback)
        return

    logger(f"[调试] 重名标题数: {len(ambiguous_names)} — 逐项输出残差与间隙", log_callback)

    def expected_editor_xy(program_x: float, program_y: float) -> Tuple[float, float]:
        editor_x = float(scale) * float(program_x) + float(tx)
        editor_y = float(scale) * float(program_y) + float(ty)
        return editor_x, editor_y

    def fmt_points(points: List[Tuple[float, float]]) -> str:
        return ", ".join([f"({int(px)},{int(py)})" for px, py in points])

    for name in ambiguous_names[:max_items]:
        models = name_to_model_nodes.get(name, [])
        detections = name_to_detections.get(name, [])

        program_points: List[Tuple[float, float]] = []
        for model in models:
            ex, ey = expected_editor_xy(float(model.pos[0]), float(model.pos[1]))
            program_points.append((ex, ey))
        program_points_sorted = sorted(program_points, key=lambda pos: (pos[0], pos[1]))

        detection_points: List[Tuple[float, float]] = []
        for bbox in detections:
            detection_points.append((float(bbox[0]), float(bbox[1])))
        detection_points_sorted = sorted(detection_points, key=lambda pos: (pos[0], pos[1]))

        residuals: List[float] = []
        gaps: List[float] = []
        for ex, ey in program_points:
            distances = [((dx - ex) ** 2 + (dy - ey) ** 2) ** 0.5 for dx, dy in detection_points]
            if not distances:
                continue
            distances.sort()
            best = float(distances[0])
            second = float(distances[1]) if len(distances) > 1 else float("inf")
            residuals.append(best)
            gaps.append(second - best if second < float("inf") else float("inf"))

        residual_summary = ", ".join([str(int(value)) for value in residuals]) if residuals else "-"
        gap_summary = ", ".join(
            ["∞" if value == float("inf") else str(int(value)) for value in gaps]
        ) if gaps else "-"
        near_eps = sum(1 for value in residuals if value <= float(epsilon_px)) if residuals else 0

        logger(
            (
                f"[歧义] '{name}': 模型{len(models)} 检测{len(detections)} | "
                f"期望={fmt_points(program_points_sorted)} | 检测={fmt_points(detection_points_sorted)} | "
                f"残差px=[{residual_summary}] (≤ε:{near_eps}/{len(residuals) if residuals else 0}) | "
                f"间隙Δ=[{gap_summary}]"
            ),
            log_callback,
        )


