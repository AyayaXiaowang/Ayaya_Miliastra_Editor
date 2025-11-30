"""战斗预设页面的拆分模块导出。"""

from .sections import (
    BaseCombatPresetSection,
    TableRowData,
    SECTION_SEQUENCE,
    SECTION_MAP,
    SECTION_SELECTION_LABELS,
    get_section_by_key,
    get_section_by_selection_label,
)

__all__ = [
    "BaseCombatPresetSection",
    "TableRowData",
    "SECTION_SEQUENCE",
    "SECTION_MAP",
    "SECTION_SELECTION_LABELS",
    "get_section_by_key",
    "get_section_by_selection_label",
]


