"""战斗预设面板的内部编辑结构（纯数据）。

把各面板里反复出现的“editor 分组 dict”抽到独立模块，减少巨型面板文件体积，
也避免在 UI 模块之间形成循环 import。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ClassEditorStruct:
    """职业编辑结构：metadata.class_editor.{battle,skills}。"""

    battle: Dict[str, Any]
    skills: Dict[str, Any]


@dataclass
class ItemEditorStruct:
    """道具编辑结构：metadata.item_editor.{basic,drop,interaction}。"""

    basic: Dict[str, Any]
    drop: Dict[str, Any]
    interaction: Dict[str, Any]


@dataclass
class SkillEditorStruct:
    """技能编辑结构：metadata.skill_editor.{basic,combo,numeric,lifecycle}。"""

    basic: Dict[str, Any]
    combo: Dict[str, Any]
    numeric: Dict[str, Any]
    lifecycle: Dict[str, Any]


__all__ = [
    "ClassEditorStruct",
    "ItemEditorStruct",
    "SkillEditorStruct",
]


