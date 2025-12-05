"""
节点图高级特性
基于知识库：附录/节点图高级特性
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from enum import Enum

from engine.graph.models.package_model import SignalConfig

if TYPE_CHECKING:
    from engine.nodes.node_definition_loader import NodeDef
    from engine.resources.package_interfaces import PackageLike


# ============================================================================
# 复合节点 (复合节点.md)
# ============================================================================

@dataclass
class MappedPort:
    """映射的内部端口
    
    记录虚拟引脚对应的内部节点端口
    """
    node_id: str  # 内部节点ID
    port_name: str  # 端口名称
    is_input: bool  # 端口方向（True=输入，False=输出）
    is_flow: bool = False  # 是否为流程端口（True=流程口，False=数据口）
    
    def serialize(self) -> dict:
        return {
            "node_id": self.node_id,
            "port_name": self.port_name,
            "is_input": self.is_input,
            "is_flow": self.is_flow
        }
    
    @staticmethod
    def deserialize(data: dict) -> "MappedPort":
        return MappedPort(
            node_id=data["node_id"],
            port_name=data["port_name"],
            is_input=data["is_input"],
            is_flow=data.get("is_flow", False)
        )


@dataclass
class VirtualPinConfig:
    """虚拟引脚配置
    
    支持多端口映射：
    - 输入引脚：一个虚拟输入可以分发到多个内部输入（数据复制）
    - 输出引脚：多个内部输出可以收集到一个虚拟输出（数据合并）
    """
    pin_index: int  # 引脚序号（从1开始，流程口和数据口分别编号）
    pin_name: str  # 引脚名称
    pin_type: str  # 数据类型
    is_input: bool  # True为输入引脚，False为输出引脚
    is_flow: bool = False  # True为流程引脚，False为数据引脚
    description: str = ""  # 引脚描述
    
    # 映射的内部端口列表（支持多个端口）
    mapped_ports: List[MappedPort] = field(default_factory=list)
    
    # 合并策略（仅用于输出引脚的多对一场景）
    # "last": 取最后一个值（默认）
    # "first": 取第一个值
    # "array": 合并为数组
    merge_strategy: str = "last"

    # 是否允许在没有内部端口映射的情况下视为“已使用”
    # 用于支持某些仅在控制流条件中使用的数据输入引脚：
    # 这类引脚不会绑定到具体节点端口，但在复合节点代码层面已参与逻辑判断。
    allow_unmapped: bool = False
    
    def serialize(self) -> dict:
        return {
            "pin_index": self.pin_index,
            "pin_name": self.pin_name,
            "pin_type": self.pin_type,
            "is_input": self.is_input,
            "is_flow": self.is_flow,
            "description": self.description,
            "mapped_ports": [port.serialize() for port in self.mapped_ports],
            "merge_strategy": self.merge_strategy,
            "allow_unmapped": self.allow_unmapped,
        }
    
    @staticmethod
    def deserialize(data: dict) -> "VirtualPinConfig":
        return VirtualPinConfig(
            pin_index=data["pin_index"],
            pin_name=data["pin_name"],
            pin_type=data["pin_type"],
            is_input=data["is_input"],
            is_flow=data.get("is_flow", False),
            description=data.get("description", ""),
            mapped_ports=[MappedPort.deserialize(p) for p in data.get("mapped_ports", [])],
            merge_strategy=data.get("merge_strategy", "last"),
            allow_unmapped=data.get("allow_unmapped", False),
        )


@dataclass
class CompositeNodeConfig:
    """复合节点配置（基于虚拟引脚）"""
    composite_id: str  # 唯一标识符
    node_name: str  # 节点名称
    node_description: str  # 节点描述
    scope: str = "server"  # 作用域（固定为server）
    virtual_pins: List[VirtualPinConfig] = field(default_factory=list)  # 虚拟引脚列表
    sub_graph: Dict[str, Any] = field(default_factory=dict)  # 内部子图（标准节点图格式）
    folder_path: str = ""  # 文件夹路径（空字符串表示根目录）
    
    doc_reference: str = "复合节点.md"
    notes: str = "复合节点可以封装一组节点图逻辑，作为单个节点使用。仅支持服务器节点。"
    
    def serialize(self) -> dict:
        """序列化为JSON格式"""
        return {
            "composite_id": self.composite_id,
            "node_name": self.node_name,
            "node_description": self.node_description,
            "scope": self.scope,
            "virtual_pins": [pin.serialize() for pin in self.virtual_pins],
            "sub_graph": self.sub_graph,
            "folder_path": self.folder_path,
            "doc_reference": self.doc_reference,
            "notes": self.notes
        }
    
    @staticmethod
    def deserialize(data: dict) -> "CompositeNodeConfig":
        """从JSON格式反序列化"""
        return CompositeNodeConfig(
            composite_id=data["composite_id"],
            node_name=data["node_name"],
            node_description=data.get("node_description", ""),
            scope=data.get("scope", "server"),
            virtual_pins=[VirtualPinConfig.deserialize(pin) for pin in data.get("virtual_pins", [])],
            sub_graph=data.get("sub_graph", {}),
            folder_path=data.get("folder_path", ""),
            doc_reference=data.get("doc_reference", "复合节点.md"),
            notes=data.get("notes", "")
        )
    
    def get_input_pins(self) -> List[VirtualPinConfig]:
        """获取所有输入引脚"""
        return [pin for pin in self.virtual_pins if pin.is_input]
    
    def get_output_pins(self) -> List[VirtualPinConfig]:
        """获取所有输出引脚"""
        return [pin for pin in self.virtual_pins if not pin.is_input]


def convert_composite_to_node_def(composite: CompositeNodeConfig) -> "NodeDef":
    """将复合节点配置转换为 NodeDef 格式
    
    这是统一的转换函数，被以下模块调用：
    - CompositeNodeManager.composite_to_node_def
    - pipeline.composite_parse._to_node_def
    
    Args:
        composite: 复合节点配置
        
    Returns:
        NodeDef对象
        
    规则说明：
    - 输入/输出端口按虚拟引脚序号排序
    - 流程端口类型统一为"流程"，数据端口使用虚拟引脚声明的类型
    - 节点类别自动判断：
      * 有输入流程端口 → 执行节点
      * 仅有输出流程端口（无输入流程端口）→ 事件节点
      * 既无输入也无输出流程端口 → 查询节点
    - 标记 is_composite=True 且带 composite_id
    """
    from engine.nodes.node_definition_loader import NodeDef
    
    # 提取输入端口名称（按序号排序）
    input_pins = sorted(composite.get_input_pins(), key=lambda p: p.pin_index)
    input_names = [pin.pin_name for pin in input_pins]
    
    # 提取输出端口名称（按序号排序）
    output_pins = sorted(composite.get_output_pins(), key=lambda p: p.pin_index)
    output_names = [pin.pin_name for pin in output_pins]
    
    # 构建端口类型映射
    input_types = {}
    output_types = {}
    for pin in input_pins:
        input_types[pin.pin_name] = "流程" if pin.is_flow else pin.pin_type
    for pin in output_pins:
        output_types[pin.pin_name] = "流程" if pin.is_flow else pin.pin_type
    
    # 根据虚拟引脚的流程端口特征动态判断节点类型
    has_input_flow = any(pin.is_input and pin.is_flow for pin in composite.virtual_pins)
    has_output_flow = any(not pin.is_input and pin.is_flow for pin in composite.virtual_pins)
    
    if has_input_flow:
        category = "执行节点"
    elif has_output_flow:
        category = "事件节点"
    else:
        category = "查询节点"
    
    # 创建NodeDef
    node_def = NodeDef(
        name=composite.node_name,
        category=category,
        inputs=input_names,
        outputs=output_names,
        description=composite.node_description,
        scopes=["server"],  # 复合节点仅支持服务器
        mount_restrictions=[],
        doc_reference=composite.doc_reference,
        input_types=input_types,
        output_types=output_types
    )
    
    # 添加特殊标记以便后续识别
    node_def.is_composite = True
    node_def.composite_id = composite.composite_id
    
    return node_def


# ============================================================================
# 结构体 (结构体.md)
# ============================================================================

@dataclass
class StructFieldDefinition:
    """结构体字段定义"""
    field_name: str
    field_type: str
    default_value: Any = None


@dataclass
class StructDefinition:
    """结构体定义"""
    struct_name: str
    struct_id: int
    fields: List[StructFieldDefinition] = field(default_factory=list)
    
    doc_reference: str = "结构体.md"
    notes: str = "结构体用于组织复杂的数据结构"


@dataclass
class StructInstanceConfig:
    """结构体实例配置"""
    struct_id: int
    field_values: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# 信号系统 (信号.md)
# ============================================================================

class SignalScope(str, Enum):
    """信号作用域"""
    GLOBAL = "全局"  # 所有实体都能接收
    LOCAL = "局部"  # 仅特定实体能接收
    TEAM = "阵营"  # 同阵营实体能接收


@dataclass
class SignalParameter:
    """信号参数定义"""
    param_name: str
    param_type: str
    is_required: bool = True


@dataclass
class SignalDefinition:
    """信号定义"""
    signal_name: str
    signal_id: str
    scope: SignalScope = SignalScope.LOCAL
    parameters: List[SignalParameter] = field(default_factory=list)
    
    doc_reference: str = "信号.md"
    notes: str = "信号用于实体间通信，发送信号节点和接收信号事件配合使用"


@dataclass
class SendSignalConfig:
    """发送信号配置"""
    signal_id: str
    target_entities: List[int] = field(default_factory=list)  # 目标实体（局部信号）
    parameter_values: Dict[str, Any] = field(default_factory=dict)


def build_signal_definitions(
    signal_configs: Dict[str, SignalConfig],
    default_scope: SignalScope = SignalScope.LOCAL,
) -> Dict[str, SignalDefinition]:
    """从包级信号定义字典构建运行时信号定义映射。

    输入为 {signal_id: SignalConfig} 字典，输出为 {signal_id: SignalDefinition} 字典，
    参数列表会被转换为 `SignalParameter`，目前全部视为必需参数。
    """
    signal_definitions: Dict[str, SignalDefinition] = {}

    for signal_id, signal_config in signal_configs.items():
        parameter_definitions: List[SignalParameter] = []
        for parameter_config in signal_config.parameters:
            parameter_definition = SignalParameter(
                param_name=parameter_config.name,
                param_type=parameter_config.parameter_type,
                is_required=True,
            )
            parameter_definitions.append(parameter_definition)

        signal_definition = SignalDefinition(
            signal_name=signal_config.signal_name,
            signal_id=signal_id,
            scope=default_scope,
            parameters=parameter_definitions,
        )
        signal_definitions[signal_id] = signal_definition

    return signal_definitions


def build_signal_definitions_from_package(
    package_model: "PackageLike",
    default_scope: SignalScope = SignalScope.LOCAL,
) -> Dict[str, SignalDefinition]:
    """便捷入口：直接从包级视图对象构建运行时信号定义映射。

    约定：
    - `package_model.signals` 暴露 `{signal_id: SignalConfig}` 字典；
    - 调用方可以传入 `PackageView` / `GlobalResourceView` 等包级视图实现。
    """
    return build_signal_definitions(package_model.signals, default_scope=default_scope)


# ============================================================================
# 泛型引脚 (泛型引脚.md)
# ============================================================================

class GenericPinType(str, Enum):
    """泛型引脚类型"""
    ANY = "任意类型"
    NUMERIC = "数值类型"  # 整数/浮点数
    LIST = "列表类型"
    COMPARABLE = "可比较类型"  # 支持大小比较


@dataclass
class GenericPinConfig:
    """泛型引脚配置"""
    pin_name: str
    generic_type: GenericPinType
    
    doc_reference: str = "泛型引脚.md"
    notes: str = "泛型引脚可以接受多种数据类型，在连接时确定具体类型"


# ============================================================================
# 节点图日志系统 (节点图日志.md, 客户端节点图日志.md, 复合节点图日志.md)
# ============================================================================

class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "调试"
    INFO = "信息"
    WARNING = "警告"
    ERROR = "错误"


class LogTarget(str, Enum):
    """日志目标"""
    SERVER = "服务器"
    CLIENT = "客户端"
    COMPOSITE = "复合节点"


@dataclass
class NodeGraphLogConfig:
    """节点图日志配置"""
    log_level: LogLevel = LogLevel.INFO
    log_target: LogTarget = LogTarget.SERVER
    enabled: bool = True
    
    # 日志过滤
    filter_node_types: List[str] = field(default_factory=list)  # 过滤特定节点类型
    filter_keywords: List[str] = field(default_factory=list)  # 过滤关键词
    
    doc_reference: str = "节点图日志.md"


@dataclass
class PrintLogNodeConfig:
    """打印日志节点配置"""
    log_message: str
    log_level: LogLevel = LogLevel.INFO
    include_timestamp: bool = True
    include_entity_info: bool = True
    
    doc_reference: str = "节点图日志.md"


# ============================================================================
# 单位状态效果池 (单位状态效果池.md)
# ============================================================================

class UnitStateEffectType(str, Enum):
    """单位状态效果类型"""
    ATTRIBUTE_MODIFIER = "属性修改"
    BEHAVIOR_MODIFIER = "行为修改"
    DAMAGE_OVER_TIME = "持续伤害"
    HEAL_OVER_TIME = "持续治疗"
    CONTROL = "控制效果"


@dataclass
class UnitStateEffect:
    """单位状态效果定义"""
    effect_id: int
    effect_name: str
    effect_type: UnitStateEffectType
    effect_value: float
    duration: float = -1.0  # -1表示永久
    tick_interval: float = 1.0  # 生效间隔(s)
    
    doc_reference: str = "单位状态效果池.md"


@dataclass
class UnitStateEffectPoolConfig:
    """单位状态效果池配置"""
    pool_name: str
    pool_id: int
    effects: List[UnitStateEffect] = field(default_factory=list)
    
    doc_reference: str = "单位状态效果池.md"
    notes: str = "效果池定义了可重用的单位状态效果"


# ============================================================================
# 能力单元效果 (能力单元效果.md)
# ============================================================================

class AbilityEffectType(str, Enum):
    """能力单元效果类型"""
    DAMAGE = "伤害"
    HEAL = "治疗"
    APPLY_UNIT_STATE = "施加单位状态"
    CREATE_PROJECTILE = "创建投射物"
    PLAY_EFFECT = "播放特效"


@dataclass
class AbilityEffectConfig:
    """能力单元效果配置"""
    effect_type: AbilityEffectType
    effect_value: float = 0.0
    target_type: str = "敌方"  # 敌方/友方/自身
    
    # 伤害/治疗特定
    damage_type: Optional[str] = None  # 物理/魔法/真实
    
    # 单位状态特定
    unit_state_id: Optional[int] = None
    state_duration: float = 5.0
    
    # 投射物特定
    projectile_id: Optional[int] = None
    
    # 特效特定
    effect_asset_id: Optional[int] = None
    
    doc_reference: str = "能力单元效果.md"


# ============================================================================
# 造物技能系统 (造物技能说明.md)
# ============================================================================

class CreatureSkillCategory(str, Enum):
    """造物技能类别"""
    MELEE = "近战技能"
    RANGED = "远程技能"
    SPECIAL = "特殊技能"


@dataclass
class CreatureSkillDefinition:
    """造物技能定义"""
    skill_id: int
    skill_name: str
    skill_category: CreatureSkillCategory
    skill_description: str
    cooldown: float = 5.0
    range: float = 5.0
    
    doc_reference: str = "造物技能说明.md"


# ============================================================================
# 造物行为模式 (造物行为模式图鉴.md, 造物行为模式的未入战行为.md)
# ============================================================================

class CreatureBehaviorPattern(str, Enum):
    """造物行为模式"""
    AGGRESSIVE = "激进"
    DEFENSIVE = "防御"
    PATROL = "巡逻"
    STATIONARY = "静止"
    # 更多模式由行为模式图鉴定义


class OutOfCombatAction(str, Enum):
    """未入战行为动作"""
    IDLE = "待机"
    WANDER = "游荡"
    PATROL = "巡逻"
    RETURN_TO_SPAWN = "返回出生点"


@dataclass
class CreatureBehaviorConfig:
    """造物行为配置"""
    behavior_pattern: CreatureBehaviorPattern
    out_of_combat_action: OutOfCombatAction
    
    doc_reference: str = "造物行为模式图鉴.md"


# ============================================================================
# 验证函数
# ============================================================================

def validate_signal_parameters(
    signal_def: SignalDefinition, 
    provided_params: Dict[str, Any]
) -> List[str]:
    """验证信号参数"""
    errors = []
    
    # 检查必需参数
    for param in signal_def.parameters:
        if param.is_required and param.param_name not in provided_params:
            errors.append(
                f"[信号参数错误] 缺少必需参数'{param.param_name}'\n"
                f"信号：{signal_def.signal_name}\n"
                f"参数类型：{param.param_type}"
            )
    
    return errors


def validate_struct_instance(
    struct_def: StructDefinition, 
    instance: StructInstanceConfig
) -> List[str]:
    """验证结构体实例"""
    errors = []
    
    # 检查所有字段是否存在
    defined_fields = {field.field_name for field in struct_def.fields}
    provided_fields = set(instance.field_values.keys())
    
    missing_fields = defined_fields - provided_fields
    if missing_fields:
        errors.append(
            f"[结构体错误] 缺少字段：{', '.join(missing_fields)}\n"
            f"结构体：{struct_def.struct_name}"
        )
    
    extra_fields = provided_fields - defined_fields
    if extra_fields:
        errors.append(
            f"[结构体警告] 未定义的字段：{', '.join(extra_fields)}\n"
            f"结构体：{struct_def.struct_name}"
        )
    
    return errors
