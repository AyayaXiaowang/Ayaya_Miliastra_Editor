"""造物模型枚举与查询工具。

本模块集中维护“造物”实体可用的模型列表，用于：
- 元件库新建造物模板时提供模型下拉选项
- 校验与运行时按名称/分类进行逻辑分组

约定：
- 不做任何外部 I/O，仅提供纯数据与查询函数
- 模型名称与分类名称与设计文档保持一致（中文名）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass(frozen=True)
class CreatureModelSpec:
    """单个造物模型的定义。

    Attributes:
        category: 上级分类名称，例如“元素生命”“丘丘部族”。
        name: 模型显示名称，例如“火史莱姆”“遗迹守卫”。
    """

    category: str
    name: str


# 顶层分类 -> 模型名称列表
_CREATURE_MODEL_TREE: Dict[str, List[str]] = {
    "元素生命": [
        "火史莱姆",
        "大型火史莱姆",
        "水史莱姆",
        "大型水史莱姆",
        "风史莱姆",
        "大型风史莱姆",
        "雷史莱姆",
        "大型雷史莱姆",
        "草史莱姆",
        "大型草史莱姆",
        "冰史莱姆",
        "大型冰史莱姆",
        "岩史莱姆",
        "大型岩史莱姆",
    ],
    "丘丘部族": [
        "丘丘人",
        "打手丘丘人",
        "火箭丘丘人",
        "木盾丘丘暴徒",
        "火斧丘丘暴徒",
        "丘丘雷兜王",
        "丘丘霜铠王",
        "丘丘岩盔王",
        "水丘丘萨满",
    ],
    "深渊": [
        "火深渊法师",
        "水深渊法师",
        "雷深渊法师",
        "冰深渊法师",
    ],
    "愚人众": [
        # 按设计稿保留两个不同的名称变体
        "愚入众先遣队",
        "愚人众先遣队",
    ],
    "自律机关": [
        "遗迹守卫",
        "遗迹重机",
        "遗迹龙兽·空",
        "魔偶剑鬼",
    ],
    "人类势力": [
        "盗宝团·斥候",
        "盗宝团·海上",
    ],
    "异种魔兽": [
        "冰霜骗骗花",
        "炽热骗骗花",
        "电气骗骗花",
        "浮游水蕈兽",
        "有翼冰本真蕈",
        "金焰绒翼龙暴",
    ],
    "野生生物": [
        "野林猪",
        "浮流鸟",
    ],
}


def get_creature_model_tree() -> Dict[str, List[str]]:
    """返回造物模型的完整分类树（顶层分类 -> 模型名称列表）。"""
    return _CREATURE_MODEL_TREE


def get_creature_model_categories() -> List[str]:
    """返回所有造物模型顶层分类名称。"""
    return list(_CREATURE_MODEL_TREE.keys())


def get_creature_models_by_category(category: str) -> List[str]:
    """按分类名称返回该分类下的全部模型名称。"""
    return list(_CREATURE_MODEL_TREE.get(category, []))


def get_all_creature_models() -> List[CreatureModelSpec]:
    """返回扁平化后的造物模型列表（含分类信息）。"""
    result: List[CreatureModelSpec] = []
    for category_name, model_names in _CREATURE_MODEL_TREE.items():
        for model_name in model_names:
            result.append(CreatureModelSpec(category=category_name, name=model_name))
    return result


def get_creature_model_category_for_name(model_name: str) -> Optional[str]:
    """根据模型名称反查所属分类。

    Args:
        model_name: 模型显示名称。

    Returns:
        分类名称，如果未找到则为 None。
    """
    for category_name, model_names in _CREATURE_MODEL_TREE.items():
        if model_name in model_names:
            return category_name
    return None


def get_creature_model_display_pairs() -> List[Tuple[str, str]]:
    """返回 (显示名, 模型名) 列表，供 UI 直接使用。

    显示名格式："{分类} / {模型名}"
    """
    display_pairs: List[Tuple[str, str]] = []
    for spec in get_all_creature_models():
        display_text = f"{spec.category} / {spec.name}"
        display_pairs.append((display_text, spec.name))
    return display_pairs


