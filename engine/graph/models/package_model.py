"""存档相关配置模型 - 变量、模板、实例、战斗预设、管理配置与信号定义"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional


@dataclass
class VariableConfig:
    """自定义变量配置（实体级别的全局变量）"""
    name: str
    variable_type: str
    default_value: Any = None
    description: str = ""
    
    def serialize(self) -> dict:
        return {
            "name": self.name,
            "variable_type": self.variable_type,
            "default_value": self.default_value,
            "description": self.description
        }
    
    @staticmethod
    def deserialize(data: dict) -> VariableConfig:
        return VariableConfig(
            name=data["name"],
            variable_type=data["variable_type"],
            default_value=data.get("default_value"),
            description=data.get("description", "")
        )


@dataclass
class GraphVariableConfig:
    """节点图变量配置（节点图级别的局部变量）"""
    name: str
    variable_type: str
    default_value: Any = None
    description: str = ""
    is_exposed: bool = False  # 是否对外暴露到关卡层
    # 字典类型专用字段：仅当 variable_type 为 "字典" 或对应别名时有意义
    dict_key_type: str = ""   # 字典键的数据类型（使用中文类型名，如 "字符串"、"整数" 等）
    dict_value_type: str = "" # 字典值的数据类型
    
    def serialize(self) -> dict:
        return {
            "name": self.name,
            "variable_type": self.variable_type,
            "default_value": self.default_value,
            "description": self.description,
            "is_exposed": self.is_exposed,
            "dict_key_type": self.dict_key_type,
            "dict_value_type": self.dict_value_type,
        }
    
    @staticmethod
    def deserialize(data: dict) -> GraphVariableConfig:
        return GraphVariableConfig(
            name=data["name"],
            variable_type=data["variable_type"],
            default_value=data.get("default_value"),
            description=data.get("description", ""),
            is_exposed=data.get("is_exposed", False),
            dict_key_type=data.get("dict_key_type", ""),
            dict_value_type=data.get("dict_value_type", ""),
        )


@dataclass
class SignalParameterConfig:
    """信号参数配置"""
    name: str
    parameter_type: str  # 参数数据类型
    description: str = ""
    
    def serialize(self) -> dict:
        return {
            "name": self.name,
            "parameter_type": self.parameter_type,
            "description": self.description
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'SignalParameterConfig':
        return SignalParameterConfig(
            name=data["name"],
            parameter_type=data["parameter_type"],
            description=data.get("description", "")
        )


@dataclass
class SignalConfig:
    """信号配置（全局信号定义）"""
    signal_id: str
    signal_name: str  # 信号名（唯一标识）
    parameters: List['SignalParameterConfig'] = field(default_factory=list)
    description: str = ""
    
    def serialize(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "signal_name": self.signal_name,
            "parameters": [p.serialize() for p in self.parameters],
            "description": self.description
        }
    
    @staticmethod
    def deserialize(data: dict) -> 'SignalConfig':
        return SignalConfig(
            signal_id=data["signal_id"],
            signal_name=data["signal_name"],
            parameters=[SignalParameterConfig.deserialize(p) for p in data.get("parameters", [])],
            description=data.get("description", "")
        )


@dataclass
class ComponentConfig:
    """组件配置"""
    component_type: str
    settings: dict = field(default_factory=dict)
    description: str = ""
    
    def serialize(self) -> dict:
        return {
            "component_type": self.component_type,
            "settings": self.settings,
            "description": self.description
        }
    
    @staticmethod
    def deserialize(data: dict) -> ComponentConfig:
        return ComponentConfig(
            component_type=data["component_type"],
            settings=data.get("settings", {}),
            description=data.get("description", "")
        )


@dataclass
class TemplateConfig:
    """模板配置（元件库中的模板）"""
    template_id: str
    name: str
    entity_type: str
    description: str = ""
    default_graphs: List[str] = field(default_factory=list)  # 新格式：存储graph_id列表
    default_variables: List[VariableConfig] = field(default_factory=list)
    default_components: List[ComponentConfig] = field(default_factory=list)
    # 实体特定配置（根据entity_type存储不同的配置对象）
    entity_config: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    # 节点图变量覆盖：{graph_id: {var_name: value}}
    graph_variable_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "entity_type": self.entity_type,
            "description": self.description,
            "default_graphs": self.default_graphs,
            "default_variables": [v.serialize() for v in self.default_variables],
            "default_components": [c.serialize() for c in self.default_components],
            "entity_config": self.entity_config,
            "metadata": self.metadata,
            "graph_variable_overrides": self.graph_variable_overrides
        }
    
    @staticmethod
    def deserialize(data: dict) -> TemplateConfig:
        return TemplateConfig(
            template_id=data["template_id"],
            name=data["name"],
            entity_type=data["entity_type"],
            description=data.get("description", ""),
            default_graphs=data.get("default_graphs", []),
            default_variables=[VariableConfig.deserialize(v) for v in data.get("default_variables", [])],
            default_components=[ComponentConfig.deserialize(c) for c in data.get("default_components", [])],
            entity_config=data.get("entity_config", {}),
            metadata=data.get("metadata", {}),
            graph_variable_overrides=data.get("graph_variable_overrides", {})
        )


@dataclass
class InstanceConfig:
    """实例配置（实体摆放中的实例）"""
    instance_id: str
    name: str
    template_id: str
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    override_variables: List[VariableConfig] = field(default_factory=list)
    additional_graphs: List[str] = field(default_factory=list)  # 新格式：存储graph_id列表
    additional_components: List[ComponentConfig] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # 节点图变量覆盖：{graph_id: {var_name: value}}
    graph_variable_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    def serialize(self) -> dict:
        return {
            "instance_id": self.instance_id,
            "name": self.name,
            "template_id": self.template_id,
            "position": self.position,
            "rotation": self.rotation,
            "override_variables": [v.serialize() for v in self.override_variables],
            "additional_graphs": self.additional_graphs,
            "additional_components": [c.serialize() for c in self.additional_components],
            "metadata": self.metadata,
            "graph_variable_overrides": self.graph_variable_overrides
        }
    
    @staticmethod
    def deserialize(data: dict) -> InstanceConfig:
        return InstanceConfig(
            instance_id=data["instance_id"],
            name=data["name"],
            template_id=data["template_id"],
            position=data.get("position", [0.0, 0.0, 0.0]),
            rotation=data.get("rotation", [0.0, 0.0, 0.0]),
            override_variables=[VariableConfig.deserialize(v) for v in data.get("override_variables", [])],
            additional_graphs=data.get("additional_graphs", []),
            additional_components=[ComponentConfig.deserialize(c) for c in data.get("additional_components", [])],
            metadata=data.get("metadata", {}),
            graph_variable_overrides=data.get("graph_variable_overrides", {})
        )


@dataclass
class CombatPresets:
    """战斗预设"""
    player_templates: Dict[str, dict] = field(default_factory=dict)  # 玩家模板
    player_classes: Dict[str, dict] = field(default_factory=dict)  # 职业（原玩家职业）
    unit_statuses: Dict[str, dict] = field(default_factory=dict)  # 单位状态
    skills: Dict[str, dict] = field(default_factory=dict)  # 技能
    projectiles: Dict[str, dict] = field(default_factory=dict)  # 本地投射物
    items: Dict[str, dict] = field(default_factory=dict)  # 道具
    
    def serialize(self) -> dict:
        return {
            "player_templates": self.player_templates,
            "player_classes": self.player_classes,
            "unit_statuses": self.unit_statuses,
            "skills": self.skills,
            "projectiles": self.projectiles,
            "items": self.items
        }
    
    @staticmethod
    def deserialize(data: dict) -> CombatPresets:
        # 处理旧格式（列表）转换为新格式（字典）
        def convert_to_dict(value, default={}):
            if isinstance(value, dict):
                return value
            elif isinstance(value, list):
                # 如果是列表，转换为字典（使用索引作为key）
                return {f"item_{i}": item for i, item in enumerate(value)}
            else:
                return default
        
        return CombatPresets(
            player_templates=convert_to_dict(data.get("player_templates", {})),
            player_classes=convert_to_dict(data.get("player_classes", {})),
            unit_statuses=convert_to_dict(data.get("unit_statuses", {})),
            skills=convert_to_dict(data.get("skills", {})),
            projectiles=convert_to_dict(data.get("projectiles", {})),
            items=convert_to_dict(data.get("items", {}))
        )


@dataclass
class ManagementData:
    """管理数据"""
    # 基础管理
    timers: Dict[str, dict] = field(default_factory=dict)  # 计时器管理
    level_variables: Dict[str, dict] = field(default_factory=dict)  # 关卡变量管理
    preset_points: Dict[str, dict] = field(default_factory=dict)  # 预设点管理
    skill_resources: Dict[str, dict] = field(default_factory=dict)  # 技能资源管理
    
    # 资源与经济
    currency_backpack: dict = field(default_factory=dict)  # 货币与背包
    equipment_data: Dict[str, dict] = field(default_factory=dict)  # 装备数据管理
    shop_templates: Dict[str, dict] = field(default_factory=dict)  # 商店模板管理
    
    # 界面与显示
    ui_layouts: Dict[str, dict] = field(default_factory=dict)  # 界面布局
    ui_widget_templates: Dict[str, dict] = field(default_factory=dict)  # 界面控件组模板库
    multi_language: Dict[str, dict] = field(default_factory=dict)  # 多语言文本管理
    
    # 场景与环境
    main_cameras: Dict[str, dict] = field(default_factory=dict)  # 主镜头管理
    light_sources: Dict[str, dict] = field(default_factory=dict)  # 光源管理
    background_music: Dict[str, dict] = field(default_factory=dict)  # 背景音乐管理
    paths: Dict[str, dict] = field(default_factory=dict)  # 路径管理
    
    # 实体与对象
    entity_deployment_groups: Dict[str, dict] = field(default_factory=dict)  # 实体布设组管理
    unit_tags: Dict[str, dict] = field(default_factory=dict)  # 单位标签管理
    scan_tags: Dict[str, dict] = field(default_factory=dict)  # 扫描标签管理
    shields: Dict[str, dict] = field(default_factory=dict)  # 护盾管理
    
    # 系统与功能
    peripheral_systems: Dict[str, dict] = field(default_factory=dict)  # 外围系统管理
    save_points: Dict[str, dict] = field(default_factory=dict)  # 局内存档管理
    chat_channels: Dict[str, dict] = field(default_factory=dict)  # 文字聊天管理
    
    # 关卡配置
    level_settings: dict = field(default_factory=dict)  # 关卡设置
    
    def serialize(self) -> dict:
        return {
            # 基础管理
            "timers": self.timers,
            "level_variables": self.level_variables,
            "preset_points": self.preset_points,
            "skill_resources": self.skill_resources,
            # 资源与经济
            "currency_backpack": self.currency_backpack,
            "equipment_data": self.equipment_data,
            "shop_templates": self.shop_templates,
            # 界面与显示
            "ui_layouts": self.ui_layouts,
            "ui_widget_templates": self.ui_widget_templates,
            "multi_language": self.multi_language,
            # 场景与环境
            "main_cameras": self.main_cameras,
            "light_sources": self.light_sources,
            "background_music": self.background_music,
            "paths": self.paths,
            # 实体与对象
            "entity_deployment_groups": self.entity_deployment_groups,
            "unit_tags": self.unit_tags,
            "scan_tags": self.scan_tags,
            "shields": self.shields,
            # 系统与功能
            "peripheral_systems": self.peripheral_systems,
            "save_points": self.save_points,
            "chat_channels": self.chat_channels,
            # 关卡配置
            "level_settings": self.level_settings
        }
    
    @staticmethod
    def deserialize(data: dict) -> ManagementData:
        # 处理旧格式（列表）转换为新格式（字典）
        def convert_to_dict(value, default={}):
            if isinstance(value, dict):
                return value
            elif isinstance(value, list):
                return {f"item_{i}": item for i, item in enumerate(value)}
            else:
                return default
        
        return ManagementData(
            # 基础管理
            timers=convert_to_dict(data.get("timers", {})),
            level_variables=convert_to_dict(data.get("level_variables", {})),
            preset_points=convert_to_dict(data.get("preset_points", {})),
            skill_resources=convert_to_dict(data.get("skill_resources", {})),
            # 资源与经济
            currency_backpack=convert_to_dict(data.get("currency_backpack", {})),
            equipment_data=convert_to_dict(data.get("equipment_data", {})),
            shop_templates=convert_to_dict(data.get("shop_templates", {})),
            # 界面与显示
            ui_layouts=convert_to_dict(data.get("ui_layouts", {})),
            ui_widget_templates=convert_to_dict(data.get("ui_widget_templates", {})),
            multi_language=convert_to_dict(data.get("multi_language", {})),
            # 场景与环境
            main_cameras=convert_to_dict(data.get("main_cameras", {})),
            light_sources=convert_to_dict(data.get("light_sources", {})),
            background_music=convert_to_dict(data.get("background_music", {})),
            paths=convert_to_dict(data.get("paths", {})),
            # 实体与对象
            entity_deployment_groups=convert_to_dict(data.get("entity_deployment_groups", {})),
            unit_tags=convert_to_dict(data.get("unit_tags", {})),
            scan_tags=convert_to_dict(data.get("scan_tags", {})),
            shields=convert_to_dict(data.get("shields", {})),
            # 系统与功能
            peripheral_systems=convert_to_dict(data.get("peripheral_systems", {})),
            save_points=convert_to_dict(data.get("save_points", {})),
            chat_channels=convert_to_dict(data.get("chat_channels", {})),
            # 关卡配置
            level_settings=convert_to_dict(data.get("level_settings", {}))
        )


