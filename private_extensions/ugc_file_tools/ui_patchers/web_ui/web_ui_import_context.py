from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass(slots=True)
class WebUiImportContext:
    input_path: Path
    output_path: Path
    template_path: Path

    template_obj: Dict[str, Any]
    ui_record_list: List[Any]
    existing_guids: Set[int]

    layout_guid: int
    layout_record: Dict[str, Any]
    created_layout: Optional[Dict[str, Any]]

    pc_canvas_size: Tuple[float, float]
    # Web 导出坐标系（position/size）所使用的“参考 PC 画布尺寸”。
    #
    # 说明：
    # - Web Workbench 在不同画布尺寸（1600×900 / 1920×1080 / ...）下提取的 rect 是不同的；
    # - 写回 `.gil` 时需要以“导出时的参考尺寸”为基准，再缩放到各端 state 的 canvas_size。
    # - 若参考尺寸与目标 pc_canvas_size 不一致（例如导出时仍按 1920 提取，但写回目标为 1600），
    #   不做缩放会导致控件整体飞出屏幕/重叠（表现为 1600×900 “全乱”）。
    reference_pc_canvas_size: Tuple[float, float]
    mobile_canvas_size: Tuple[float, float]
    canvas_size_by_state_index: Dict[int, Tuple[float, float]]

    registry_path: Optional[Path]
    ui_key_to_guid: Dict[str, int]
    registry_loaded: bool
    registry_guid_dedup_report: Optional[Dict[str, Any]]
    registry_saved: bool

    guid_collision_avoided: List[Dict[str, Any]]
    reserved_guid_to_ui_key: Dict[int, str]

    # 基底兼容：不同 `.gil` 的“组容器 record”meta/component 形态可能不同。
    # 写回端优先从当前基底中挑选一个“组容器样本 record”作为原型来 clone，
    # 避免用固定样本形态写回导致编辑器无法打开/解析异常。
    group_container_prototype_record: Optional[Dict[str, Any]]

