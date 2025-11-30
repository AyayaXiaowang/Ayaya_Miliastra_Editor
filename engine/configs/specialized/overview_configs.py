"""
总览文档配置模块

本模块实现各类总览性配置，包括：
- 高级概念总览
- 通用组件总览
- 其他总览性文档
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


# ==================== 高级概念总览 ====================

@dataclass
class AdvancedConceptOverview:
    """高级概念总览配置
    
    高级概念定义：
    当一份数据需要预先定义在关卡全局层面，才能被多个单位和模块进行调用，则称为"高级概念"。
    
    包含的高级概念类型：
    - 技能系统
    - 职业系统
    - 护盾系统
    - 单位状态系统
    - 关卡结算系统
    - 局内存档系统
    - 技能资源系统
    - 文字聊天系统
    - 成就系统
    - 排行榜系统
    - 竞技段位系统
    - 多语言文本系统
    - 资源系统（商店、背包、装备、货币、道具）
    - 界面控件组系统
    - 主镜头系统
    - 全局路径系统
    - 预设点系统
    - 复苏系统
    """
    
    concept_name: str = "高级概念"
    description: str = '当一份数据需要预先定义在关卡全局层面，才能被多个单位和模块进行调用，则称为"高级概念"'
    
    # 高级概念分类
    combat_concepts: List[str] = field(default_factory=lambda: [
        "技能系统", "职业系统", "护盾系统", "单位状态系统"
    ])
    
    game_flow_concepts: List[str] = field(default_factory=lambda: [
        "关卡结算系统", "局内存档系统", "复苏系统"
    ])
    
    resource_concepts: List[str] = field(default_factory=lambda: [
        "技能资源系统", "资源系统", "商店", "背包", "装备", "货币", "道具"
    ])
    
    ui_concepts: List[str] = field(default_factory=lambda: [
        "界面控件组系统", "文字聊天系统"
    ])
    
    external_concepts: List[str] = field(default_factory=lambda: [
        "成就系统", "排行榜系统", "竞技段位系统"
    ])
    
    global_concepts: List[str] = field(default_factory=lambda: [
        "主镜头系统", "全局路径系统", "预设点系统", "多语言文本系统"
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "概念名称": self.concept_name,
            "描述": self.description,
            "战斗相关概念": self.combat_concepts.copy(),
            "游戏流程概念": self.game_flow_concepts.copy(),
            "资源相关概念": self.resource_concepts.copy(),
            "界面相关概念": self.ui_concepts.copy(),
            "外围系统概念": self.external_concepts.copy(),
            "全局系统概念": self.global_concepts.copy()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AdvancedConceptOverview':
        return cls(
            concept_name=data.get("概念名称", "高级概念"),
            description=data.get("描述", ""),
            combat_concepts=data.get("战斗相关概念", []).copy(),
            game_flow_concepts=data.get("游戏流程概念", []).copy(),
            resource_concepts=data.get("资源相关概念", []).copy(),
            ui_concepts=data.get("界面相关概念", []).copy(),
            external_concepts=data.get("外围系统概念", []).copy(),
            global_concepts=data.get("全局系统概念", []).copy()
        )
    
    def get_all_concepts(self) -> List[str]:
        """获取所有高级概念列表"""
        return (
            self.combat_concepts + 
            self.game_flow_concepts + 
            self.resource_concepts + 
            self.ui_concepts + 
            self.external_concepts + 
            self.global_concepts
        )


# ==================== 通用组件总览 ====================

class ComponentLifecycle(Enum):
    """组件生命周期状态"""
    INACTIVE = "未激活"
    ACTIVE = "激活中"
    DISABLED = "已禁用"
    DESTROYED = "已销毁"


@dataclass
class ComponentOverview:
    """通用组件总览配置
    
    组件定义：
    组件是可以添加给实体的一项功能。
    当为实体添加组件后，实体就可以使用对应的功能，同时也可以通过节点图修改组件的数据和逻辑。
    
    组件特性：
    - 通用组件可以自由的在元件或实体上添加和删除
    - 部分单位会默认携带一些自身常用的组件
    - 组件仅可在编辑时被添加到元件和实体上或从元件和实体上删除
    - 在游戏运行中无法动态添加或删除组件，部分组件可以通过节点图来进行开启或关闭
    - 当组件所属的实体在场景中时，组件功能会持续生效，直到实体销毁或移除
    """
    
    component_name: str = "通用组件"
    description: str = "组件是可以添加给实体的一项功能"
    
    # 编辑规则
    can_add_at_runtime: bool = False  # 运行时不能添加
    can_remove_at_runtime: bool = False  # 运行时不能删除
    can_toggle_at_runtime: bool = True  # 部分组件可在运行时开启/关闭
    
    # 组件分类
    movement_components: List[str] = field(default_factory=lambda: [
        "基础运动器", "投射运动器", "跟随运动器"
    ])
    
    combat_components: List[str] = field(default_factory=lambda: [
        "命中检测", "碰撞触发器", "碰撞触发源", "额外碰撞"
    ])
    
    visual_components: List[str] = field(default_factory=lambda: [
        "特效播放", "文本气泡", "铭牌", "小地图标识"
    ])
    
    logic_components: List[str] = field(default_factory=lambda: [
        "自定义变量", "定时器", "全局计时器", "选项卡"
    ])
    
    resource_components: List[str] = field(default_factory=lambda: [
        "背包", "商店", "战利品"
    ])
    
    utility_components: List[str] = field(default_factory=lambda: [
        "自定义挂接点", "角色扰动装置", "扫描标签", "单位状态"
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "组件名称": self.component_name,
            "描述": self.description,
            "运行时可添加": self.can_add_at_runtime,
            "运行时可删除": self.can_remove_at_runtime,
            "运行时可切换": self.can_toggle_at_runtime,
            "移动组件": self.movement_components.copy(),
            "战斗组件": self.combat_components.copy(),
            "视觉组件": self.visual_components.copy(),
            "逻辑组件": self.logic_components.copy(),
            "资源组件": self.resource_components.copy(),
            "工具组件": self.utility_components.copy()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ComponentOverview':
        return cls(
            component_name=data.get("组件名称", "通用组件"),
            description=data.get("描述", ""),
            can_add_at_runtime=data.get("运行时可添加", False),
            can_remove_at_runtime=data.get("运行时可删除", False),
            can_toggle_at_runtime=data.get("运行时可切换", True),
            movement_components=data.get("移动组件", []).copy(),
            combat_components=data.get("战斗组件", []).copy(),
            visual_components=data.get("视觉组件", []).copy(),
            logic_components=data.get("逻辑组件", []).copy(),
            resource_components=data.get("资源组件", []).copy(),
            utility_components=data.get("工具组件", []).copy()
        )
    
    def get_all_components(self) -> List[str]:
        """获取所有组件列表"""
        return (
            self.movement_components + 
            self.combat_components + 
            self.visual_components + 
            self.logic_components + 
            self.resource_components + 
            self.utility_components
        )
    
    def get_component_count(self) -> int:
        """获取组件总数"""
        return len(self.get_all_components())


# ==================== 组件编辑规则 ====================

@dataclass
class ComponentEditRule:
    """组件编辑规则
    
    定义了组件在编辑器中的行为规则
    """
    
    # 编辑入口
    edit_location: str = "右侧通用组件页签"
    
    # 编辑时机
    can_edit_in_editor: bool = True  # 编辑器中可编辑
    can_edit_in_runtime: bool = False  # 运行时不可编辑
    
    # 组件操作
    operations: List[str] = field(default_factory=lambda: [
        "添加组件", "删除组件", "配置组件参数", "开启/关闭组件（部分）"
    ])
    
    # 默认组件
    default_components_by_entity: Dict[str, List[str]] = field(default_factory=lambda: {
        "角色": ["基础运动器"],
        "造物": ["基础运动器"],
        "物件": [],
        "玩家": [],
        "关卡": [],
        "本地投射物": ["投射运动器"]
    })
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "编辑位置": self.edit_location,
            "编辑器中可编辑": self.can_edit_in_editor,
            "运行时可编辑": self.can_edit_in_runtime,
            "支持操作": self.operations.copy(),
            "单位默认组件": self.default_components_by_entity.copy()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ComponentEditRule':
        return cls(
            edit_location=data.get("编辑位置", "右侧通用组件页签"),
            can_edit_in_editor=data.get("编辑器中可编辑", True),
            can_edit_in_runtime=data.get("运行时可编辑", False),
            operations=data.get("支持操作", []).copy(),
            default_components_by_entity=data.get("单位默认组件", {}).copy()
        )


# ==================== 知识库结构总览 ====================

@dataclass
class KnowledgeBaseStructure:
    """知识库结构总览
    
    记录整个知识库的组织结构
    """
    
    main_categories: List[str] = field(default_factory=lambda: [
        "概念介绍",
        "界面介绍",
        "节点大全",
        "辅助功能",
        "附录"
    ])
    
    concept_subcategories: List[str] = field(default_factory=lambda: [
        "单位",
        "功能",
        "资产",
        "高级概念"
    ])
    
    function_subcategories: List[str] = field(default_factory=lambda: [
        "基础信息",
        "特化配置",
        "节点图",
        "通用组件"
    ])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "主要分类": self.main_categories.copy(),
            "概念介绍子分类": self.concept_subcategories.copy(),
            "功能子分类": self.function_subcategories.copy()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeBaseStructure':
        return cls(
            main_categories=data.get("主要分类", []).copy(),
            concept_subcategories=data.get("概念介绍子分类", []).copy(),
            function_subcategories=data.get("功能子分类", []).copy()
        )


# ==================== 导出配置实例 ====================

# 创建默认配置实例
DEFAULT_ADVANCED_CONCEPT_OVERVIEW = AdvancedConceptOverview()
DEFAULT_COMPONENT_OVERVIEW = ComponentOverview()
DEFAULT_COMPONENT_EDIT_RULE = ComponentEditRule()
DEFAULT_KNOWLEDGE_BASE_STRUCTURE = KnowledgeBaseStructure()

