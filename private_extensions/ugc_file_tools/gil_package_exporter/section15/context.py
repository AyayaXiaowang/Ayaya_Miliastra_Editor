from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Section15ExportContext:
    output_package_root: Path
    package_namespace: str

    skill_directory: Path
    item_directory: Path
    unit_status_directory: Path
    currency_backpack_directory: Path
    level_settings_directory: Path
    preset_point_directory: Path
    shield_directory: Path
    unit_tag_directory: Path
    equipment_data_directory: Path
    growth_curve_directory: Path
    equipment_slot_template_directory: Path
    unclassified_directory: Path

    skill_raw_directory: Path
    item_raw_directory: Path
    unit_status_raw_directory: Path
    currency_backpack_raw_directory: Path
    level_settings_raw_directory: Path
    shield_raw_directory: Path
    unit_tag_raw_directory: Path
    equipment_data_raw_directory: Path
    growth_curve_raw_directory: Path
    equipment_slot_template_raw_directory: Path

    referenced_graph_sources: Dict[int, List[Dict[str, Any]]]

    currency_entries: List[Dict[str, Any]]
    backpack_entry: Optional[Tuple[int, Dict[str, Any]]]


