"""复合节点装饰器系统 - 类格式复合节点定义

提供装饰器来定义复合节点的类格式：
- @composite_class: 标记类为复合节点
- @flow_entry: 定义流程入口方法（有流程入/出引脚）
- @event_handler: 定义事件处理器方法（事件触发，有流程出引脚）
- @data_method: 定义纯数据计算方法（只有数据引脚）
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Callable, Optional, Any


@dataclass
class PinDefinition:
    """引脚定义"""
    name: str  # 引脚名称
    pin_type: str  # 引脚类型（"流程"、"实体"、"浮点数"等）
    description: str = ""  # 引脚描述
    
    def __repr__(self):
        return f"PinDefinition(name='{self.name}', type='{self.pin_type}')"


@dataclass
class FlowEntrySpec:
    """流程入口方法规范
    
    流程入口方法：
    - 有流程入引脚（触发点）
    - 可以有数据入引脚（参数）
    - 可以有流程出引脚（执行完成后的出口）
    - 可以有数据出引脚（返回值）
    """
    method_name: str  # 方法名称
    inputs: List[Tuple[str, str]]  # [(引脚名, 类型)]
    outputs: List[Tuple[str, str]] = field(default_factory=list)  # [(引脚名, 类型)]
    description: str = ""  # 方法描述
    auto_inputs: bool = False
    auto_outputs: bool = False
    internal: bool = False
    
    def __post_init__(self):
        # 验证至少有一个流程入引脚（自动推断模式除外）
        if not self.auto_inputs:
            has_flow_in = any(pin_type == "流程" for _, pin_type in self.inputs)
            if not has_flow_in:
                raise ValueError(f"流程入口方法 '{self.method_name}' 必须至少有一个流程入引脚")
    
    def get_flow_inputs(self) -> List[PinDefinition]:
        """获取流程入引脚"""
        return [PinDefinition(name, pin_type) for name, pin_type in self.inputs if pin_type == "流程"]
    
    def get_data_inputs(self) -> List[PinDefinition]:
        """获取数据入引脚"""
        return [PinDefinition(name, pin_type) for name, pin_type in self.inputs if pin_type != "流程"]
    
    def get_flow_outputs(self) -> List[PinDefinition]:
        """获取流程出引脚"""
        return [PinDefinition(name, pin_type) for name, pin_type in self.outputs if pin_type == "流程"]
    
    def get_data_outputs(self) -> List[PinDefinition]:
        """获取数据出引脚"""
        return [PinDefinition(name, pin_type) for name, pin_type in self.outputs if pin_type != "流程"]


@dataclass
class EventHandlerSpec:
    """事件处理器方法规范
    
    事件处理器方法：
    - 无流程入引脚（由事件触发）
    - 事件参数自动暴露为数据出引脚
    - 可以有流程出引脚（事件处理完成后的出口）
    - 可以有数据出引脚（额外的返回值）
    """
    method_name: str  # 方法名称
    event_name: str  # 事件名称（如"定时器触发时"）
    outputs: List[Tuple[str, str]] = field(default_factory=list)  # [(引脚名, 类型)]
    description: str = ""  # 方法描述
    expose_event_params: bool = True  # 是否将事件参数暴露为数据出引脚
    auto_outputs: bool = False
    internal: bool = False
    
    def get_flow_outputs(self) -> List[PinDefinition]:
        """获取流程出引脚"""
        return [PinDefinition(name, pin_type) for name, pin_type in self.outputs if pin_type == "流程"]
    
    def get_data_outputs(self) -> List[PinDefinition]:
        """获取数据出引脚（不包括事件参数）"""
        return [PinDefinition(name, pin_type) for name, pin_type in self.outputs if pin_type != "流程"]


@dataclass
class DataMethodSpec:
    """纯数据计算方法规范
    
    纯数据计算方法：
    - 无流程引脚
    - 只有数据入引脚（参数）
    - 只有数据出引脚（返回值）
    """
    method_name: str  # 方法名称
    inputs: List[Tuple[str, str]]  # [(引脚名, 类型)]
    outputs: List[Tuple[str, str]]  # [(引脚名, 类型)]
    description: str = ""  # 方法描述
    auto_inputs: bool = False
    auto_outputs: bool = False
    internal: bool = False
    
    def __post_init__(self):
        # 验证没有流程引脚（对应段未启用自动推断时）
        if not self.auto_inputs:
            for name, pin_type in self.inputs:
                if pin_type == "流程":
                    raise ValueError(f"纯数据方法 '{self.method_name}' 的数据入不能是流程引脚")
        if not self.auto_outputs:
            for name, pin_type in self.outputs:
                if pin_type == "流程":
                    raise ValueError(f"纯数据方法 '{self.method_name}' 的数据出不能是流程引脚")
    
    def get_data_inputs(self) -> List[PinDefinition]:
        """获取数据入引脚"""
        return [PinDefinition(name, pin_type) for name, pin_type in self.inputs]
    
    def get_data_outputs(self) -> List[PinDefinition]:
        """获取数据出引脚"""
        return [PinDefinition(name, pin_type) for name, pin_type in self.outputs]


@dataclass
class CompositeClassSpec:
    """复合节点类规范
    
    存储复合节点类的元数据，包括：
    - 类名和描述
    - 所有方法的规范（流程入口、事件处理器、数据方法）
    """
    class_name: str  # 类名
    description: str = ""  # 类描述
    flow_entries: List[FlowEntrySpec] = field(default_factory=list)  # 流程入口方法列表
    event_handlers: List[EventHandlerSpec] = field(default_factory=list)  # 事件处理器方法列表
    data_methods: List[DataMethodSpec] = field(default_factory=list)  # 数据方法列表
    
    def get_all_methods(self) -> List[Any]:
        """获取所有方法规范"""
        return list(self.flow_entries) + list(self.event_handlers) + list(self.data_methods)
    
    def find_method_spec(self, method_name: str) -> Optional[Any]:
        """根据方法名查找方法规范"""
        for method_spec in self.get_all_methods():
            if method_spec.method_name == method_name:
                return method_spec
        return None


# ============================================================================
# 装饰器实现
# ============================================================================

def composite_class(cls):
    """标记类为复合节点类
    
    用法:
        @composite_class
        class 我的复合节点:
            ...
    """
    # 创建类规范对象
    spec = CompositeClassSpec(
        class_name=cls.__name__,
        description=cls.__doc__ or ""
    )
    
    # 收集所有方法的规范
    for attr_name in dir(cls):
        attr = getattr(cls, attr_name)
        if callable(attr):
            # 检查方法是否有装饰器规范
            if hasattr(attr, "__flow_entry_spec__"):
                spec.flow_entries.append(getattr(attr, "__flow_entry_spec__"))
            elif hasattr(attr, "__event_handler_spec__"):
                spec.event_handlers.append(getattr(attr, "__event_handler_spec__"))
            elif hasattr(attr, "__data_method_spec__"):
                spec.data_methods.append(getattr(attr, "__data_method_spec__"))
    
    # 将规范对象附加到类上
    setattr(cls, "__composite_class_spec__", spec)
    
    return cls


def flow_entry(
    *,
    inputs: Optional[List[Tuple[str, str]]] = None,
    outputs: Optional[List[Tuple[str, str]]] = None,
    description: str = "",
    internal: bool = False,
):
    """定义流程入口方法
    
    用法:
        @flow_entry(
            inputs=[("流程入", "流程"), ("目标实体", "实体")],
            outputs=[("流程出", "流程")]
        )
        def 启动定时器(self, 目标实体):
            ...
    
    参数:
        inputs: 输入引脚列表 [(引脚名, 类型)]
        outputs: 输出引脚列表 [(引脚名, 类型)]，默认为空列表
        description: 方法描述
    """
    resolved_inputs = inputs or []
    resolved_outputs = outputs or []
    auto_inputs = inputs is None
    auto_outputs = outputs is None
    
    def decorator(func):
        # 创建方法规范
        spec = FlowEntrySpec(
            method_name=func.__name__,
            inputs=resolved_inputs,
            outputs=resolved_outputs,
            description=description or func.__doc__ or "",
            auto_inputs=auto_inputs,
            auto_outputs=auto_outputs,
            internal=internal,
        )
        
        # 将规范附加到方法上
        setattr(func, "__flow_entry_spec__", spec)
        
        return func
    
    return decorator


def event_handler(
    *,
    event: str,
    outputs: Optional[List[Tuple[str, str]]] = None,
    description: str = "",
    expose_event_params: bool = True,
    internal: bool = False,
):
    """定义事件处理器方法
    
    用法:
        @event_handler(
            event="定时器触发时",
            outputs=[("触发完成", "流程"), ("事件源实体", "实体")]
        )
        def on_定时器触发时(self, 事件源实体, 事件源GUID, ...):
            ...
    
    参数:
        event: 事件名称
        outputs: 输出引脚列表 [(引脚名, 类型)]
        description: 方法描述
        expose_event_params: 是否将事件参数暴露为数据出引脚（默认True）
    """
    resolved_outputs = outputs or []
    auto_outputs = outputs is None
    
    def decorator(func):
        # 创建方法规范
        spec = EventHandlerSpec(
            method_name=func.__name__,
            event_name=event,
            outputs=resolved_outputs,
            description=description or func.__doc__ or "",
            expose_event_params=expose_event_params,
            auto_outputs=auto_outputs,
            internal=internal,
        )
        
        # 将规范附加到方法上
        setattr(func, "__event_handler_spec__", spec)
        
        return func
    
    return decorator


def data_method(
    *,
    inputs: Optional[List[Tuple[str, str]]] = None,
    outputs: Optional[List[Tuple[str, str]]] = None,
    description: str = "",
    internal: bool = False,
):
    """定义纯数据计算方法
    
    用法:
        @data_method(
            inputs=[("X", "浮点数"), ("Y", "浮点数")],
            outputs=[("长度", "浮点数")]
        )
        def calculate(self, X, Y):
            ...
    
    参数:
        inputs: 输入引脚列表 [(引脚名, 类型)]
        outputs: 输出引脚列表 [(引脚名, 类型)]
        description: 方法描述
    """
    resolved_inputs = inputs or []
    resolved_outputs = outputs or []
    auto_inputs = inputs is None
    auto_outputs = outputs is None
    
    def decorator(func):
        # 创建方法规范
        spec = DataMethodSpec(
            method_name=func.__name__,
            inputs=resolved_inputs,
            outputs=resolved_outputs,
            description=description or func.__doc__ or "",
            auto_inputs=auto_inputs,
            auto_outputs=auto_outputs,
            internal=internal,
        )
        
        # 将规范附加到方法上
        setattr(func, "__data_method_spec__", spec)
        
        return func
    
    return decorator


# ============================================================================
# 辅助函数
# ============================================================================

def is_composite_class(cls) -> bool:
    """检查类是否是复合节点类"""
    return hasattr(cls, "__composite_class_spec__")


def get_composite_class_spec(cls) -> Optional[CompositeClassSpec]:
    """获取类的复合节点规范"""
    return getattr(cls, "__composite_class_spec__", None)


def get_method_spec(method: Callable) -> Optional[Any]:
    """获取方法的规范（FlowEntrySpec/EventHandlerSpec/DataMethodSpec）"""
    if hasattr(method, "__flow_entry_spec__"):
        return getattr(method, "__flow_entry_spec__")
    elif hasattr(method, "__event_handler_spec__"):
        return getattr(method, "__event_handler_spec__")
    elif hasattr(method, "__data_method_spec__"):
        return getattr(method, "__data_method_spec__")
    return None


