"""
局内存档系统配置
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class SaveDataType(str, Enum):
    """存档数据类型"""
    INTEGER = "整数"
    FLOAT = "浮点数"
    STRING = "字符串"
    BOOLEAN = "布尔值"
    LIST = "列表"
    DICT = "字典"


class SaveScope(str, Enum):
    """存档作用域"""
    PLAYER = "玩家"  # 玩家级别存档
    LEVEL = "关卡"   # 关卡级别存档
    GLOBAL = "全局"  # 全局存档


@dataclass
class SaveVariableConfig:
    """存档变量配置"""
    variable_name: str
    data_type: SaveDataType
    default_value: Any
    description: str = ""
    is_persistent: bool = True  # 是否持久化
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "变量名": self.variable_name,
            "数据类型": self.data_type.value,
            "默认值": self.default_value,
            "描述": self.description,
            "是否持久化": self.is_persistent
        }


@dataclass
class InGameSaveConfig:
    """
    局内存档配置 (局内存档.md)
    
    局内存档系统允许在游戏过程中保存和加载玩家数据
    """
    save_config_id: str
    save_config_name: str
    description: str = ""
    
    # 作用域
    save_scope: SaveScope = SaveScope.PLAYER
    
    # 存档变量列表
    save_variables: List[SaveVariableConfig] = field(default_factory=list)
    
    # 自动保存设置
    auto_save_enabled: bool = False
    auto_save_interval: float = 60.0  # 自动保存间隔（秒）
    
    # 保存时机配置
    save_on_level_complete: bool = True  # 关卡完成时保存
    save_on_checkpoint: bool = True      # 检查点保存
    save_on_player_death: bool = False   # 玩家死亡时保存
    
    # 最大存档数量
    max_save_slots: int = 10
    
    # 文档引用
    doc_reference: str = "局内存档.md"
    
    def add_variable(self, name: str, data_type: SaveDataType, default_value: Any, description: str = ""):
        """添加存档变量"""
        variable = SaveVariableConfig(
            variable_name=name,
            data_type=data_type,
            default_value=default_value,
            description=description
        )
        self.save_variables.append(variable)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "存档配置ID": self.save_config_id,
            "存档配置名称": self.save_config_name,
            "描述": self.description,
            "作用域": self.save_scope.value,
            "存档变量": [v.to_dict() for v in self.save_variables],
            "自动保存启用": self.auto_save_enabled,
            "自动保存间隔": self.auto_save_interval,
            "关卡完成时保存": self.save_on_level_complete,
            "检查点保存": self.save_on_checkpoint,
            "玩家死亡时保存": self.save_on_player_death,
            "最大存档数量": self.max_save_slots
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'InGameSaveConfig':
        config = InGameSaveConfig(
            save_config_id=data.get("存档配置ID", ""),
            save_config_name=data.get("存档配置名称", ""),
            description=data.get("描述", ""),
            save_scope=SaveScope(data.get("作用域", "玩家")),
            auto_save_enabled=data.get("自动保存启用", False),
            auto_save_interval=data.get("自动保存间隔", 60.0),
            save_on_level_complete=data.get("关卡完成时保存", True),
            save_on_checkpoint=data.get("检查点保存", True),
            save_on_player_death=data.get("玩家死亡时保存", False),
            max_save_slots=data.get("最大存档数量", 10)
        )
        
        # 加载存档变量
        for var_data in data.get("存档变量", []):
            var = SaveVariableConfig(
                variable_name=var_data.get("变量名", ""),
                data_type=SaveDataType(var_data.get("数据类型", "整数")),
                default_value=var_data.get("默认值", 0),
                description=var_data.get("描述", ""),
                is_persistent=var_data.get("是否持久化", True)
            )
            config.save_variables.append(var)
        
        return config


if __name__ == "__main__":
    print("=== 局内存档配置测试 ===")
    
    # 创建存档配置
    save_config = InGameSaveConfig(
        save_config_id="save_001",
        save_config_name="玩家进度存档",
        description="保存玩家游戏进度",
        save_scope=SaveScope.PLAYER,
        auto_save_enabled=True,
        auto_save_interval=120.0
    )
    
    # 添加存档变量
    save_config.add_variable("玩家等级", SaveDataType.INTEGER, 1, "玩家当前等级")
    save_config.add_variable("当前金币", SaveDataType.INTEGER, 0, "玩家拥有的金币")
    save_config.add_variable("完成关卡", SaveDataType.LIST, [], "已完成的关卡列表")
    save_config.add_variable("装备列表", SaveDataType.DICT, {}, "玩家装备信息")
    
    print(f"存档配置: {save_config.save_config_name}")
    print(f"作用域: {save_config.save_scope.value}")
    print(f"存档变量数量: {len(save_config.save_variables)}")
    print("\n存档变量列表:")
    for var in save_config.save_variables:
        print(f"  - {var.variable_name} ({var.data_type.value}): {var.description}")

