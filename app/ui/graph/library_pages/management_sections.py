"""管理配置库页面用的 Section 注册与查表入口。

原始的 `management_sections.py` 已拆分为多个子模块：
- 通用类型别名与基类：`management_sections_base.py`
- 各具体 Section 实现：`management_section_*.py`

本模块仅负责：
- 统一导出 `BaseManagementSection` / `ManagementRowData` 供其他模块复用；
- 集中实例化所有 Section，并构建 `MANAGEMENT_SECTION_MAP`；
- 提供按 `section_key` 查找 Section 的便捷函数。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from .management_sections_base import BaseManagementSection, ManagementRowData
from .management_section_signals import SignalSection
from .management_section_struct_definitions import (
    StructDefinitionSection,
    InGameSaveStructDefinitionSection,
)
from .management_section_level_settings import LevelSettingsSection
from .management_section_peripheral_systems import PeripheralSystemSection
from .management_section_currency_backpack import CurrencyBackpackSection
from .management_section_timer import TimerSection
from .management_section_variable import VariableSection
from .management_section_preset_point import PresetPointSection
from .management_section_skill_resource import SkillResourceSection
from .management_section_background_music import BackgroundMusicSection
from .management_section_equipment_data import (
    EquipmentEntrySection,
    EquipmentTagSection,
    EquipmentTypeSection,
)
from .management_section_main_camera import MainCameraSection
from .management_section_path import PathSection
from .management_section_multi_language import MultiLanguageSection
from .management_section_light_sources import LightSourcesSection
from .management_section_chat_channels import ChatChannelsSection
from .management_section_unit_tags import UnitTagSection
from .management_section_shields import ShieldSection
from .management_section_scan_tags import ScanTagSection
from .management_section_shop_templates import ShopTemplatesSection
from .management_section_save_points import SavePointsSection
from .management_section_entity_deployment_groups import EntityDeploymentGroupsSection


MANAGEMENT_LIBRARY_SECTIONS: Tuple[BaseManagementSection, ...] = (
    SignalSection(),
    StructDefinitionSection(),
    InGameSaveStructDefinitionSection(),
    LevelSettingsSection(),
    PeripheralSystemSection(),
    CurrencyBackpackSection(),
    TimerSection(),
    VariableSection(),
    PresetPointSection(),
    SkillResourceSection(),
    BackgroundMusicSection(),
    EquipmentEntrySection(),
    EquipmentTagSection(),
    EquipmentTypeSection(),
    MainCameraSection(),
    PathSection(),
    MultiLanguageSection(),
    LightSourcesSection(),
    ChatChannelsSection(),
    UnitTagSection(),
    ShieldSection(),
    ScanTagSection(),
    ShopTemplatesSection(),
    SavePointsSection(),
    EntityDeploymentGroupsSection(),
)


MANAGEMENT_SECTION_MAP: Dict[str, BaseManagementSection] = {
    section.section_key: section for section in MANAGEMENT_LIBRARY_SECTIONS
}


def get_management_section_by_key(section_key: str) -> Optional[BaseManagementSection]:
    """根据 section_key 返回对应的 Section 实例。"""
    return MANAGEMENT_SECTION_MAP.get(section_key)


__all__ = [
    "BaseManagementSection",
    "ManagementRowData",
    "MANAGEMENT_LIBRARY_SECTIONS",
    "MANAGEMENT_SECTION_MAP",
    "get_management_section_by_key",
    "EquipmentEntrySection",
    "EquipmentTagSection",
    "EquipmentTypeSection",
]



