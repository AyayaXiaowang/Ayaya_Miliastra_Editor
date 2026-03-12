"""实体摆放页面常量。"""

from __future__ import annotations

from PyQt6 import QtCore

# QListWidget item roles -------------------------------------------------------

INSTANCE_ID_ROLE = QtCore.Qt.ItemDataRole.UserRole
ENTITY_TYPE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
SEARCH_TEXT_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2
IS_SHARED_INSTANCE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 3

# Category keys ----------------------------------------------------------------

CATEGORY_ALL = "all"
CATEGORY_LEVEL_ENTITY = "level_entity"

# Level entity visual semantics -------------------------------------------------

LEVEL_ENTITY_ICON = "📍"
LEVEL_ENTITY_LABEL_TEXT = "关卡实体"

# Form dialog / editor ranges ---------------------------------------------------

NEW_INSTANCE_DIALOG_SIZE = (520, 640)
POSITION_EDITOR_MIN = -10000
POSITION_EDITOR_MAX = 10000
ROTATION_EDITOR_MIN = -360
ROTATION_EDITOR_MAX = 360

# Display formatting ------------------------------------------------------------

VECTOR_DISPLAY_DECIMALS = 1
DEFAULT_VECTOR3 = (0.0, 0.0, 0.0)

# Formatting helpers -----------------------------------------------------------


def format_vector3(vector: list[float] | tuple[float, ...], *, decimals: int = VECTOR_DISPLAY_DECIMALS) -> str:
    """将三维向量格式化为 (x, y, z) 文本。"""
    x, y, z = vector
    fmt = "{:." + str(int(decimals)) + "f}"
    return f"({fmt.format(float(x))}, {fmt.format(float(y))}, {fmt.format(float(z))})"

# Decorations merge -------------------------------------------------------------

MERGE_TARGET_NEW_INSTANCE_ID = "__new__"
MERGE_CARRIER_TEMPLATE_ID_PREFIX = "shape_editor_empty__"

