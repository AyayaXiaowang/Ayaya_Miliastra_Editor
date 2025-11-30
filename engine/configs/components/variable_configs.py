"""
组件配置 - 自定义变量
基于知识库文档定义的自定义变量组件配置项
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any
from enum import Enum


class VariableDataType(Enum):
    """自定义变量数据类型（自定义变量.md 第7-21行）"""
    # 基础数据类型
    INTEGER = "整数"
    FLOAT = "浮点数"
    STRING = "字符串"
    BOOLEAN = "布尔值"
    VECTOR3 = "三维向量"
    ENTITY = "实体"
    GUID = "GUID"
    COMPONENT_ID = "元件ID"
    CONFIG_ID = "配置ID"
    CAMP = "阵营"
    STRUCT = "结构体"
    
    # 列表数据类型
    INTEGER_LIST = "整数列表"
    FLOAT_LIST = "浮点数列表"
    STRING_LIST = "字符串列表"
    BOOLEAN_LIST = "布尔值列表"
    VECTOR3_LIST = "三维向量列表"
    ENTITY_LIST = "实体列表"
    GUID_LIST = "GUID列表"
    COMPONENT_ID_LIST = "元件ID列表"
    CONFIG_ID_LIST = "配置ID列表"
    CAMP_LIST = "阵营列表"
    STRUCT_LIST = "结构体列表"
    
    # 字典数据类型（所有字典数据类型）
    DICT_ALL = "所有字典数据类型"


@dataclass
class CustomVariableConfig:
    """
    自定义变量配置
    """
    # 自定义变量名（唯一序号，不允许重名）
    variable_name: str
    # 自定义变量数据类型（强类型，必须明确）
    data_type: VariableDataType
    # 默认值（实体创建时的初始值）
    default_value: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "变量名": self.variable_name,
            "数据类型": self.data_type.value,
            "默认值": self.default_value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CustomVariableConfig':
        data_type_str = data.get("数据类型", VariableDataType.INTEGER.value)
        data_type = VariableDataType(data_type_str)
        return cls(
            variable_name=data.get("变量名", ""),
            data_type=data_type,
            default_value=data.get("默认值")
        )


@dataclass
class CustomVariableComponentConfig:
    """
    自定义变量组件配置
    """
    # 组件内定义的所有自定义变量
    variables: List[CustomVariableConfig] = field(default_factory=list)
    
    def add_variable(self, variable: CustomVariableConfig) -> bool:
        """添加自定义变量，检查重名"""
        # 检查是否重名（自定义变量.md 第6行）
        for existing_var in self.variables:
            if existing_var.variable_name == variable.variable_name:
                return False
        self.variables.append(variable)
        return True
    
    def remove_variable(self, variable_name: str) -> bool:
        """移除自定义变量"""
        for index, var in enumerate(self.variables):
            if var.variable_name == variable_name:
                self.variables.pop(index)
                return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "已定义自定义变量": [var.to_dict() for var in self.variables]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CustomVariableComponentConfig':
        variables_data = data.get("已定义自定义变量", [])
        variables = [CustomVariableConfig.from_dict(var_data) for var_data in variables_data]
        return cls(variables=variables)

