from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True, slots=True)
class ImportedWebProgressbar:
    ui_key: str
    widget_id: str
    widget_name: str
    guid: int
    layer: int
    pc_canvas_position: Tuple[float, float]
    pc_size: Tuple[float, float]
    mobile_canvas_position: Optional[Tuple[float, float]]
    mobile_size: Optional[Tuple[float, float]]
    console_canvas_position: Optional[Tuple[float, float]]
    console_size: Optional[Tuple[float, float]]
    gamepad_canvas_position: Optional[Tuple[float, float]]
    gamepad_size: Optional[Tuple[float, float]]
    initial_visible: bool
    raw_codes: Dict[str, int]


@dataclass(frozen=True, slots=True)
class ImportedWebTextbox:
    ui_key: str
    widget_id: str
    widget_name: str
    guid: int
    layer: int
    pc_canvas_position: Tuple[float, float]
    pc_size: Tuple[float, float]
    mobile_canvas_position: Optional[Tuple[float, float]]
    mobile_size: Optional[Tuple[float, float]]
    console_canvas_position: Optional[Tuple[float, float]]
    console_size: Optional[Tuple[float, float]]
    gamepad_canvas_position: Optional[Tuple[float, float]]
    gamepad_size: Optional[Tuple[float, float]]
    initial_visible: bool
    text_content: str
    font_size: int
    raw_codes: Dict[str, Optional[int]]


@dataclass(frozen=True, slots=True)
class ImportedWebItemDisplay:
    ui_key: str
    widget_id: str
    widget_name: str
    guid: int
    layer: int
    pc_canvas_position: Tuple[float, float]
    pc_size: Tuple[float, float]
    mobile_canvas_position: Optional[Tuple[float, float]]
    mobile_size: Optional[Tuple[float, float]]
    console_canvas_position: Optional[Tuple[float, float]]
    console_size: Optional[Tuple[float, float]]
    gamepad_canvas_position: Optional[Tuple[float, float]]
    gamepad_size: Optional[Tuple[float, float]]
    initial_visible: bool
    display_type: str
    raw_codes: Dict[str, Optional[int]]

