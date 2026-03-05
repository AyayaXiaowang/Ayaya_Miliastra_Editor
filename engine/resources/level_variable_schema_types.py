from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal

# 变量文件分类常量
CATEGORY_CUSTOM = "自定义变量"
CATEGORY_INGAME_SAVE = "自定义变量-局内存档变量"

# 关卡变量 payload.owner（强语义一等字段）
LEVEL_VARIABLE_OWNER_LEVEL = "level"
LEVEL_VARIABLE_OWNER_PLAYER = "player"
LEVEL_VARIABLE_OWNER_DATA = "data"
LEVEL_VARIABLE_OWNER_VALUES = {
    LEVEL_VARIABLE_OWNER_LEVEL,
    LEVEL_VARIABLE_OWNER_PLAYER,
    LEVEL_VARIABLE_OWNER_DATA,
}
LevelVariableOwner = Literal["level", "player", "data"]


@dataclass
class VariableFileInfo:
    """变量文件元信息"""

    file_id: str
    file_name: str
    category: str  # CATEGORY_CUSTOM 或 CATEGORY_INGAME_SAVE
    source_path: str  # 相对于关卡变量目录的路径
    absolute_path: Path  # 物理文件绝对路径（用于按项目存档目录过滤/归属判断）
    variables: List[Dict] = field(default_factory=list)


__all__ = [
    "CATEGORY_CUSTOM",
    "CATEGORY_INGAME_SAVE",
    "LEVEL_VARIABLE_OWNER_DATA",
    "LEVEL_VARIABLE_OWNER_LEVEL",
    "LEVEL_VARIABLE_OWNER_PLAYER",
    "LEVEL_VARIABLE_OWNER_VALUES",
    "LevelVariableOwner",
    "VariableFileInfo",
]

