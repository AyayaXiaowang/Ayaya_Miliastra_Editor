"""集中维护通用组件定义的注册表。

本模块提供“通用组件”的单一事实来源：
- 组件类型名称
- 显示名与说明文案
- 允许挂载的实体类型
- 与通用组件文档的引用信息

注意：这里仅维护元数据，不涉及运行时行为或具体配置字段。
配置字段 Schema 仍由同目录下的各 `*_configs.py` 模块负责定义。
"""

from __future__ import annotations

from typing import Dict, List


# 组件定义（基于通用组件文档和各实体文档）
# 说明：
# - key 为组件类型字符串（在模板/实例、节点图、文档中统一使用）
# - applicable_entities 使用实体规则中的用户可见实体类型名称
COMPONENT_DEFINITIONS: Dict[str, Dict[str, object]] = {
    "自定义变量": {
        "display_name": "自定义变量",
        "description": "可添加给实体的自定义变量组件",
        "applicable_entities": ["关卡", "角色", "玩家", "物件-动态", "造物"],
        "config_params": ["变量名", "变量类型", "默认值"],
        "lifecycle": "仅可在编辑时添加或删除，运行中无法动态添加或删除",
        "reference": "通用组件.md:1-12",
    },
    "全局计时器": {
        "display_name": "全局计时器",
        "description": "全局计时器组件",
        "applicable_entities": ["关卡", "角色", "玩家", "物件-动态", "造物"],
        "lifecycle": "组件所属实体在场景中时持续生效，直到实体销毁或移除",
        "reference": "通用组件.md:9-12",
    },
    "定时器": {
        "display_name": "定时器",
        "description": "定时器组件",
        "applicable_entities": ["物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "碰撞触发器": {
        "display_name": "碰撞触发器",
        "description": "碰撞触发器组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "can_enable_disable": True,  # 部分组件可以通过节点图开启或关闭
        "reference": "通用组件.md:10",
    },
    "碰撞触发源": {
        "display_name": "碰撞触发源",
        "description": "碰撞触发源组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "单位状态": {
        "display_name": "单位状态",
        "description": "单位状态组件",
        "applicable_entities": ["角色", "玩家", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "特效播放": {
        "display_name": "特效播放",
        "description": "特效播放组件",
        "applicable_entities": ["角色", "物件-动态", "造物", "本地投射物"],
        "reference": "通用组件.md",
    },
    "单位挂接点": {
        "display_name": "单位挂接点",
        "description": "自定义挂接点组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "背包": {
        "display_name": "背包",
        "description": "背包组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "战利品": {
        "display_name": "战利品",
        "description": "战利品组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "铭牌": {
        "display_name": "铭牌",
        "description": "铭牌组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "气泡": {
        "display_name": "文本气泡",
        "description": "文本气泡组件",
        "applicable_entities": ["角色"],
        "reference": "通用组件.md",
    },
    "文本气泡": {
        "display_name": "文本气泡",
        "description": "文本气泡组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "装备栏": {
        "display_name": "装备栏",
        "description": "装备栏组件，仅角色可添加",
        "applicable_entities": ["角色"],  # 角色.md:22-23 "仅角色可以添加的装备栏组件"
        "reference": "角色.md:22-23",
    },
    "选项卡": {
        "display_name": "选项卡",
        "description": "选项卡组件",
        "applicable_entities": ["造物"],
        "reference": "造物.md:62",
    },
    "商店": {
        "display_name": "商店",
        "description": "商店组件",
        "applicable_entities": ["造物"],
        "reference": "造物.md:75",
    },
    "投射运动器": {
        "display_name": "投射运动器",
        "description": "投射运动器组件，本地投射物专用",
        "applicable_entities": ["本地投射物"],
        "reference": "本地投射物.md:51-52",
    },
    "命中检测": {
        "display_name": "命中检测",
        "description": "命中检测组件，本地投射物专用",
        "applicable_entities": ["本地投射物"],
        "reference": "本地投射物.md:54-55",
    },
    "基础运动器": {
        "display_name": "基础运动器",
        "description": "基础运动器组件，用于实现各种运动效果",
        "applicable_entities": ["角色", "物件-动态", "造物", "本地投射物"],
        "reference": "通用组件.md",
    },
    "跟随运动器": {
        "display_name": "跟随运动器",
        "description": "跟随运动器组件，用于实现实体跟随效果",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "自定义挂接点": {
        "display_name": "自定义挂接点",
        "description": "自定义挂接点组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "额外碰撞": {
        "display_name": "额外碰撞",
        "description": "额外碰撞组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "扫描标签": {
        "display_name": "扫描标签",
        "description": "扫描标签组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "小地图标识": {
        "display_name": "小地图标识",
        "description": "小地图标识组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
    "角色扰动装置": {
        "display_name": "角色扰动装置",
        "description": "角色扰动装置组件",
        "applicable_entities": ["角色", "物件-动态", "造物"],
        "reference": "通用组件.md",
    },
}


def get_all_component_names() -> List[str]:
    """获取所有通用组件名称列表（注册表主入口）。"""
    return list(COMPONENT_DEFINITIONS.keys())


__all__ = ["COMPONENT_DEFINITIONS", "get_all_component_names"]


