"""存档索引模型 - 轻量级存档定义"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class PackageResources:
    """存档资源引用"""
    # 基础资源
    templates: List[str] = field(default_factory=list)
    instances: List[str] = field(default_factory=list)
    graphs: List[str] = field(default_factory=list)
    # 复合节点资源（composite_id 列表）
    composites: List[str] = field(default_factory=list)
    
    # 战斗预设资源
    combat_presets: Dict[str, List[str]] = field(
        default_factory=lambda: {
            "player_templates": [],
            "player_classes": [],
            "unit_statuses": [],
            "skills": [],
            "projectiles": [],
            "items": [],
        }
    )
    
    # 管理配置资源
    management: Dict[str, List[str]] = field(default_factory=lambda: {
        "timers": [],
        "level_variables": [],
        "preset_points": [],
        "skill_resources": [],
        "currency_backpack": [],
        "equipment_data": [],
        "shop_templates": [],
        "ui_layouts": [],
        "ui_widget_templates": [],
        "multi_language": [],
        "main_cameras": [],
        "light_sources": [],
        "background_music": [],
        "paths": [],
        "entity_deployment_groups": [],
        "unit_tags": [],
        "scan_tags": [],
        "shields": [],
        "peripheral_systems": [],
        "save_points": [],
        "chat_channels": [],
        "level_settings": [],
        "signals": [],
        "struct_definitions": [],
    })
    
    def serialize(self) -> dict:
        """序列化为字典"""
        return {
            "templates": self.templates,
            "instances": self.instances,
            "graphs": self.graphs,
            "composites": self.composites,
            "combat_presets": self.combat_presets,
            "management": self.management
        }
    
    @staticmethod
    def deserialize(data: dict) -> PackageResources:
        """从字典反序列化"""
        resources = PackageResources()
        
        resources.templates = data.get("templates", [])
        resources.instances = data.get("instances", [])
        resources.graphs = data.get("graphs", [])
        resources.composites = data.get("composites", [])
        
        # 战斗预设：结构标准化（缺失字段使用默认空列表）
        combat_data = data.get("combat_presets", {})
        resources.combat_presets = {
            "player_templates": combat_data.get("player_templates", []),
            "player_classes": combat_data.get("player_classes", []),
            "unit_statuses": combat_data.get("unit_statuses", []),
            "skills": combat_data.get("skills", []),
            "projectiles": combat_data.get("projectiles", []),
            "items": combat_data.get("items", []),
        }
        
        # 管理配置：结构标准化（缺失字段使用默认空列表）
        management_data = data.get("management", {})
        resources.management = {
            "timers": management_data.get("timers", []),
            "level_variables": management_data.get("level_variables", []),
            "preset_points": management_data.get("preset_points", []),
            "skill_resources": management_data.get("skill_resources", []),
            "currency_backpack": management_data.get("currency_backpack", []),
            "equipment_data": management_data.get("equipment_data", []),
            "shop_templates": management_data.get("shop_templates", []),
            "ui_layouts": management_data.get("ui_layouts", []),
            "ui_widget_templates": management_data.get("ui_widget_templates", []),
            "multi_language": management_data.get("multi_language", []),
            "main_cameras": management_data.get("main_cameras", []),
            "light_sources": management_data.get("light_sources", []),
            "background_music": management_data.get("background_music", []),
            "paths": management_data.get("paths", []),
            "entity_deployment_groups": management_data.get("entity_deployment_groups", []),
            "unit_tags": management_data.get("unit_tags", []),
            "scan_tags": management_data.get("scan_tags", []),
            "shields": management_data.get("shields", []),
            "peripheral_systems": management_data.get("peripheral_systems", []),
            "save_points": management_data.get("save_points", []),
            "chat_channels": management_data.get("chat_channels", []),
            "level_settings": management_data.get("level_settings", []),
            "signals": management_data.get("signals", []),
            "struct_definitions": management_data.get("struct_definitions", []),
        }
        
        return resources
    
    def get_all_resource_ids(self) -> List[str]:
        """获取所有资源ID的列表"""
        all_ids = []
        
        # 基础资源
        all_ids.extend(self.templates)
        all_ids.extend(self.instances)
        all_ids.extend(self.graphs)
        all_ids.extend(self.composites)
        
        # 战斗预设
        for resource_list in self.combat_presets.values():
            all_ids.extend(resource_list)
        
        # 管理配置
        for resource_list in self.management.values():
            all_ids.extend(resource_list)
        
        return all_ids


@dataclass
class PackageIndex:
    """轻量级存档索引
    
    存档索引只存储资源ID引用，不存储资源的实际数据。
    所有资源（模板、实例、节点图、战斗预设、管理配置）都存储在资源库中。
    
    关卡实体作为特殊的实例存储在资源库中，通过 level_entity_id 引用。
    """
    package_id: str
    name: str
    description: str = ""
    resources: PackageResources = field(default_factory=PackageResources)
    resource_names: Dict[str, dict] = field(default_factory=dict)
    level_entity_id: Optional[str] = None  # 关卡实体实例ID（存储在资源库/实例/中）
    signals: Dict[str, dict] = field(default_factory=dict)  # 信号配置（存档级别）
    created_at: str = ""
    updated_at: str = ""
    todo_states: Dict[str, bool] = field(default_factory=dict)
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
    
    def add_template(self, template_id: str) -> None:
        """添加模板引用"""
        if template_id not in self.resources.templates:
            self.resources.templates.append(template_id)
            self.updated_at = datetime.now().isoformat()
    
    def remove_template(self, template_id: str) -> None:
        """移除模板引用"""
        if template_id in self.resources.templates:
            self.resources.templates.remove(template_id)
            self.updated_at = datetime.now().isoformat()
    
    def add_instance(self, instance_id: str) -> None:
        """添加实例引用"""
        if instance_id not in self.resources.instances:
            self.resources.instances.append(instance_id)
            self.updated_at = datetime.now().isoformat()
    
    def remove_instance(self, instance_id: str) -> None:
        """移除实例引用"""
        if instance_id in self.resources.instances:
            self.resources.instances.remove(instance_id)
            self.updated_at = datetime.now().isoformat()
    
    def add_graph(self, graph_id: str) -> None:
        """添加节点图引用"""
        if graph_id not in self.resources.graphs:
            self.resources.graphs.append(graph_id)
            self.updated_at = datetime.now().isoformat()
    
    def add_composite(self, composite_id: str) -> None:
        """添加复合节点引用"""
        if composite_id not in self.resources.composites:
            self.resources.composites.append(composite_id)
            self.updated_at = datetime.now().isoformat()
    
    def remove_graph(self, graph_id: str) -> None:
        """移除节点图引用"""
        if graph_id in self.resources.graphs:
            self.resources.graphs.remove(graph_id)
            self.updated_at = datetime.now().isoformat()
    
    def remove_composite(self, composite_id: str) -> None:
        """移除复合节点引用"""
        if composite_id in self.resources.composites:
            self.resources.composites.remove(composite_id)
            self.updated_at = datetime.now().isoformat()
    
    def add_combat_preset(self, preset_type: str, preset_id: str) -> None:
        """添加战斗预设引用
        
        Args:
            preset_type: 预设类型（player_classes, unit_statuses, skills, projectiles, items）
            preset_id: 预设ID
        """
        if preset_type in self.resources.combat_presets:
            if preset_id not in self.resources.combat_presets[preset_type]:
                self.resources.combat_presets[preset_type].append(preset_id)
                self.updated_at = datetime.now().isoformat()
    
    def remove_combat_preset(self, preset_type: str, preset_id: str) -> None:
        """移除战斗预设引用"""
        if preset_type in self.resources.combat_presets:
            if preset_id in self.resources.combat_presets[preset_type]:
                self.resources.combat_presets[preset_type].remove(preset_id)
                self.updated_at = datetime.now().isoformat()
    
    def add_management_resource(self, resource_type: str, resource_id: str) -> None:
        """添加管理资源引用
        
        Args:
            resource_type: 资源类型（timers, level_variables等）
            resource_id: 资源ID
        """
        if resource_type in self.resources.management:
            if resource_id not in self.resources.management[resource_type]:
                self.resources.management[resource_type].append(resource_id)
                self.updated_at = datetime.now().isoformat()
    
    def remove_management_resource(self, resource_type: str, resource_id: str) -> None:
        """移除管理资源引用"""
        if resource_type in self.resources.management:
            if resource_id in self.resources.management[resource_type]:
                self.resources.management[resource_type].remove(resource_id)
                self.updated_at = datetime.now().isoformat()
    
    def serialize(self) -> dict:
        """序列化为字典。

        设计约定：
        - PackageIndex 负责“索引”，只在磁盘上保存资源 ID 与基础元数据；
          存档级信号的完整定义存储在 `资源库/管理配置/信号/<package_id>_signals.json` 中；
        - Todo 勾选状态属于编辑器运行期状态，不写回功能包索引 JSON，而是由运行时状态文件单独持久化。
        - 内存中的 `signals` 字段可暂存完整定义，
          但序列化到存档索引 JSON 时只输出一个轻量摘要（信号 ID 列表），
          真实数据由管理配置资源承载。
        """
        # 仅保留信号 ID 的占位结构，避免在索引中重复保存完整配置
        signals_summary: Dict[str, dict] = {}
        if isinstance(self.signals, dict):
            for signal_id in self.signals.keys():
                if isinstance(signal_id, str) and signal_id:
                    signals_summary[signal_id] = {}

        return {
            "package_id": self.package_id,
            "name": self.name,
            "description": self.description,
            "resources": self.resources.serialize(),
            "resource_names": self.resource_names,
            "level_entity_id": self.level_entity_id,
            "signals": signals_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
    
    @staticmethod
    def deserialize(data: dict) -> PackageIndex:
        """从字典反序列化"""
        return PackageIndex(
            package_id=data["package_id"],
            name=data["name"],
            description=data.get("description", ""),
            resources=PackageResources.deserialize(data.get("resources", {})),
            resource_names=data.get("resource_names", {}),
            level_entity_id=data.get("level_entity_id"),
            signals=data.get("signals", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            todo_states=data.get("todo_states", {})
        )

