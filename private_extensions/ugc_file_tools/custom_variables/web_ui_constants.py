from __future__ import annotations

from typing import Dict

from .constants import DEFAULT_VARIABLE_GROUP_NAME

__all__ = [
    "DEFAULT_ITEM_DISPLAY_BUTTON_CONFIG_ID_VARIABLE_FULL_NAME",
    "DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_VARIABLE_FULL_NAME",
    "DEFAULT_ITEM_DISPLAY_BUTTON_COOLDOWN_SECONDS_VARIABLE_FULL_NAME",
    "DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_DEFAULT",
    "DEFAULT_SHARED_PROGRESSBAR_VARIABLE_NAMES",
    "DEFAULT_PROGRESSBAR_INT_DEFAULTS",
]


# Web 导入：可交互道具展示按钮（按钮锚点）默认绑定的变量（写入关卡实体自定义变量）。
# 说明：
# - 这些变量仅作为占位/可写载体，不要求对应的配置ID真实存在；
# - 默认值策略：
#   - 配置ID/冷却等：默认 0（或 0.0）
#   - 道具数量：默认 100（更符合“可交互按钮展示数量”的常见预期）
# - 写回阶段会确保变量存在（若缺失则自动创建到目标实体）。
DEFAULT_ITEM_DISPLAY_BUTTON_CONFIG_ID_VARIABLE_FULL_NAME = f"{DEFAULT_VARIABLE_GROUP_NAME}.UI_交互按钮_道具配置ID"
DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_VARIABLE_FULL_NAME = f"{DEFAULT_VARIABLE_GROUP_NAME}.UI_交互按钮_道具数量"
DEFAULT_ITEM_DISPLAY_BUTTON_COOLDOWN_SECONDS_VARIABLE_FULL_NAME = f"{DEFAULT_VARIABLE_GROUP_NAME}.UI_交互按钮_栏位冷却时间"

# 可交互道具展示按钮：默认数量
DEFAULT_ITEM_DISPLAY_BUTTON_QUANTITY_DEFAULT = 100

# Web 导入：若进度条未显式绑定变量，则默认绑定到一套“共享装饰进度条变量”（避免用户手动补齐变量、也避免每个装饰条生成一堆变量）。
# 约定：默认写入到“关卡”变量组（对应关卡实体）。
DEFAULT_SHARED_PROGRESSBAR_VARIABLE_NAMES: Dict[str, str] = {
    "current": "UI_装饰进度条_当前值",
    "min": "UI_装饰进度条_最小值",
    "max": "UI_装饰进度条_最大值",
}

# 默认值：让装饰进度条“满条”显示（current=max，min=0）。
DEFAULT_PROGRESSBAR_INT_DEFAULTS: Dict[str, int] = {
    "current": 100,
    "min": 0,
    "max": 100,
}

