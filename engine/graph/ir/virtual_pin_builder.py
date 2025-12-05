"""虚拟引脚构建器

提供复合节点虚拟引脚的解析和映射构建功能。
"""
from __future__ import annotations

import ast
from typing import Dict, List, Optional, Tuple

from engine.nodes.advanced_node_features import VirtualPinConfig, MappedPort
from engine.graph.common import validate_pin_type_annotation
from engine.graph.composite.pin_marker_collector import (
    PinMarker,
    PinMarkerSummary,
    collect_pin_markers,
    infer_data_inputs_from_signature,
)


def build_virtual_pins_from_class(class_def: ast.ClassDef) -> List[VirtualPinConfig]:
    """从类格式的复合节点提取虚拟引脚
    
    解析类中使用 @flow_entry、@event_handler、@data_method 装饰的方法，
    提取所有虚拟引脚定义。
    
    Args:
        class_def: 类定义AST节点
        
    Returns:
        虚拟引脚配置列表
    """
    virtual_pins: List[VirtualPinConfig] = []
    pin_index = 1
    
    # 遍历类的所有方法
    for item in class_def.body:
        if not isinstance(item, ast.FunctionDef):
            continue
        
        # 跳过 __init__ 等特殊方法
        if item.name.startswith('__'):
            continue
        
        # 检查方法的装饰器
        method_spec = extract_method_spec_from_decorators(item)
        if not method_spec:
            continue
        
        method_spec = _apply_auto_pin_configuration(item, method_spec)
        
        # 跳过内部方法（不对外暴露）
        if method_spec.get('internal', False):
            continue
        
        # 根据装饰器类型提取引脚
        if method_spec['type'] == 'flow_entry':
            # 流程入口：inputs 和 outputs
            for pin_name, pin_type in method_spec['inputs']:
                is_flow = (pin_type == "流程")
                virtual_pins.append(VirtualPinConfig(
                    pin_index=pin_index,
                    pin_name=pin_name,
                    pin_type=pin_type,
                    is_input=True,
                    is_flow=is_flow,
                    description="",
                    mapped_ports=[]
                ))
                pin_index += 1
            
            for pin_name, pin_type in method_spec['outputs']:
                is_flow = (pin_type == "流程")
                virtual_pins.append(VirtualPinConfig(
                    pin_index=pin_index,
                    pin_name=pin_name,
                    pin_type=pin_type,
                    is_input=False,
                    is_flow=is_flow,
                    description="",
                    mapped_ports=[]
                ))
                pin_index += 1
        
        elif method_spec['type'] == 'event_handler':
            # 事件处理器：只有 outputs（无流程入）
            # 事件参数需要从方法签名提取
            if method_spec.get('expose_event_params', True):
                # 提取事件参数作为数据出引脚
                for arg in item.args.args[1:]:  # 跳过self
                    param_name = arg.arg
                    # 尝试从类型标注推断类型
                    pin_type = _get_type_annotation(arg.annotation) if arg.annotation else "泛型"
                    virtual_pins.append(VirtualPinConfig(
                        pin_index=pin_index,
                        pin_name=param_name,
                        pin_type=pin_type,
                        is_input=False,
                        is_flow=False,
                        description="",
                        mapped_ports=[]
                    ))
                    pin_index += 1
            
            # 添加装饰器定义的输出引脚
            for pin_name, pin_type in method_spec['outputs']:
                is_flow = (pin_type == "流程")
                virtual_pins.append(VirtualPinConfig(
                    pin_index=pin_index,
                    pin_name=pin_name,
                    pin_type=pin_type,
                    is_input=False,
                    is_flow=is_flow,
                    description="",
                    mapped_ports=[]
                ))
                pin_index += 1
        
        elif method_spec['type'] == 'data_method':
            # 纯数据方法：inputs 和 outputs（无流程引脚）
            for pin_name, pin_type in method_spec['inputs']:
                virtual_pins.append(VirtualPinConfig(
                    pin_index=pin_index,
                    pin_name=pin_name,
                    pin_type=pin_type,
                    is_input=True,
                    is_flow=False,
                    description="",
                    mapped_ports=[]
                ))
                pin_index += 1
            
            for pin_name, pin_type in method_spec['outputs']:
                virtual_pins.append(VirtualPinConfig(
                    pin_index=pin_index,
                    pin_name=pin_name,
                    pin_type=pin_type,
                    is_input=False,
                    is_flow=False,
                    description="",
                    mapped_ports=[]
                ))
                pin_index += 1

    # 复合节点允许根据需要暴露多个流程出口（例如条件分支、多分支等），
    # 具体分支结构由后续 IR 构建与布局逻辑处理。
    return virtual_pins


def _apply_auto_pin_configuration(func_def: ast.FunctionDef, method_spec: Dict) -> Dict:
    method_spec.setdefault('data_output_var_map', {})
    auto_inputs = method_spec.get('auto_inputs', False)
    auto_outputs = method_spec.get('auto_outputs', False)
    
    if not (auto_inputs or auto_outputs):
        return method_spec
    
    markers = collect_pin_markers(func_def)
    method_type = method_spec.get('type')
    
    if method_type == 'flow_entry':
        if auto_inputs:
            method_spec['inputs'] = _build_flow_entry_inputs(func_def, markers)
        if auto_outputs:
            outputs, var_map = _build_outputs_from_markers(
                markers,
                include_default_flow=False,
            )
            method_spec['outputs'] = outputs
            method_spec['data_output_var_map'] = var_map
    
    elif method_type == 'event_handler':
        if auto_outputs:
            outputs, var_map = _build_outputs_from_markers(markers, include_default_flow=True)
            method_spec['outputs'] = outputs
            method_spec['data_output_var_map'] = var_map
    
    elif method_type == 'data_method':
        if auto_inputs:
            method_spec['inputs'] = _build_data_inputs(func_def, markers)
        if auto_outputs:
            outputs, var_map = _build_outputs_from_markers(markers, include_default_flow=False)
            method_spec['outputs'] = outputs
            method_spec['data_output_var_map'] = var_map
    
    return method_spec


def _build_flow_entry_inputs(func_def: ast.FunctionDef, markers: PinMarkerSummary) -> List[Tuple[str, str]]:
    inputs: List[Tuple[str, str]] = []
    flow_markers = markers.flow_inputs or [PinMarker("流程入", "流程")]
    for marker in flow_markers:
        inputs.append((marker.name, marker.pin_type))
    inputs.extend(_merge_data_inputs(func_def, markers))
    return inputs


def _build_data_inputs(func_def: ast.FunctionDef, markers: PinMarkerSummary) -> List[Tuple[str, str]]:
    return _merge_data_inputs(func_def, markers)


def _merge_data_inputs(func_def: ast.FunctionDef, markers: PinMarkerSummary) -> List[Tuple[str, str]]:
    signature_inputs = infer_data_inputs_from_signature(func_def)
    overrides: Dict[str, str] = {m.name: m.pin_type for m in markers.data_inputs}
    handled: set[str] = set()
    inputs: List[Tuple[str, str]] = []
    
    for sig in signature_inputs:
        pin_type = overrides.get(sig.name, sig.pin_type)
        inputs.append((sig.name, pin_type))
        handled.add(sig.name)
    
    for marker in markers.data_inputs:
        if marker.name not in handled:
            inputs.append((marker.name, marker.pin_type))
    
    return inputs


def _build_outputs_from_markers(markers: PinMarkerSummary, *, include_default_flow: bool) -> Tuple[List[Tuple[str, str]], Dict[str, str]]:
    outputs: List[Tuple[str, str]] = []
    var_map: Dict[str, str] = {}
    
    flow_markers = markers.flow_outputs or []
    if include_default_flow and not flow_markers:
        flow_markers = [PinMarker("流程出", "流程")]
    
    for marker in flow_markers:
        outputs.append((marker.name, marker.pin_type))
    
    for marker in markers.data_outputs:
        outputs.append((marker.name, marker.pin_type))
        var_map[marker.name] = marker.variable
    
    return outputs, var_map


def extract_method_spec_from_decorators(func_def: ast.FunctionDef) -> Optional[Dict]:
    """从方法的装饰器提取规范信息（公共API）
    
    Args:
        func_def: 函数定义AST节点
        
    Returns:
        方法规范字典，包含 type、inputs、outputs 等字段
        如果没有相关装饰器，返回 None
    """
    for decorator in func_def.decorator_list:
        if isinstance(decorator, ast.Call):
            # 装饰器是函数调用，如 @flow_entry(...)
            if isinstance(decorator.func, ast.Name):
                decorator_name = decorator.func.id
                
                if decorator_name == 'flow_entry':
                    # 提取 inputs 和 outputs
                    has_inputs_kw = _has_keyword(decorator, 'inputs')
                    has_outputs_kw = _has_keyword(decorator, 'outputs')
                    inputs = _extract_pin_list_from_decorator(decorator, 'inputs') if has_inputs_kw else []
                    outputs = _extract_pin_list_from_decorator(decorator, 'outputs') if has_outputs_kw else []
                    internal = _extract_bool_from_decorator(decorator, 'internal', False)
                    return {
                        'type': 'flow_entry',
                        'inputs': inputs,
                        'outputs': outputs,
                        'internal': internal,
                        'auto_inputs': not has_inputs_kw,
                        'auto_outputs': not has_outputs_kw,
                        'data_output_var_map': {},
                    }
                
                elif decorator_name == 'event_handler':
                    # 提取 event 和 outputs
                    event_name = _extract_string_from_decorator(decorator, 'event')
                    has_outputs_kw = _has_keyword(decorator, 'outputs')
                    outputs = _extract_pin_list_from_decorator(decorator, 'outputs') if has_outputs_kw else []
                    # 默认不暴露事件参数，用户需要明确指定 expose_event_params=True
                    expose_params = _extract_bool_from_decorator(decorator, 'expose_event_params', False)
                    internal = _extract_bool_from_decorator(decorator, 'internal', False)
                    return {
                        'type': 'event_handler',
                        'event_name': event_name,
                        'outputs': outputs,
                        'expose_event_params': expose_params,
                        'internal': internal,
                        'auto_outputs': not has_outputs_kw,
                        'data_output_var_map': {},
                    }
                
                elif decorator_name == 'data_method':
                    # 提取 inputs 和 outputs
                    has_inputs_kw = _has_keyword(decorator, 'inputs')
                    has_outputs_kw = _has_keyword(decorator, 'outputs')
                    inputs = _extract_pin_list_from_decorator(decorator, 'inputs') if has_inputs_kw else []
                    outputs = _extract_pin_list_from_decorator(decorator, 'outputs') if has_outputs_kw else []
                    internal = _extract_bool_from_decorator(decorator, 'internal', False)
                    return {
                        'type': 'data_method',
                        'inputs': inputs,
                        'outputs': outputs,
                        'internal': internal,
                        'auto_inputs': not has_inputs_kw,
                        'auto_outputs': not has_outputs_kw,
                        'data_output_var_map': {},
                    }
    
    return None


def _extract_pin_list_from_decorator(decorator: ast.Call, param_name: str) -> List[Tuple[str, str]]:
    """从装饰器调用中提取引脚列表
    
    例如: inputs=[("流程入", "流程"), ("目标实体", "实体")]
    
    Args:
        decorator: 装饰器调用AST节点
        param_name: 参数名（inputs 或 outputs）
        
    Returns:
        引脚列表 [(引脚名, 类型), ...]
    """
    pins = []
    
    for keyword in decorator.keywords:
        if keyword.arg == param_name:
            # 期望是一个列表
            if isinstance(keyword.value, ast.List):
                for elt in keyword.value.elts:
                    # 期望是元组 (name, type)
                    if isinstance(elt, ast.Tuple) and len(elt.elts) >= 2:
                        name_node = elt.elts[0]
                        type_node = elt.elts[1]
                        
                        # 提取名称和类型（都应该是字符串常量）
                        if isinstance(name_node, ast.Constant):
                            pin_name = name_node.value
                        else:
                            continue
                        
                        if isinstance(type_node, ast.Constant):
                            pin_type = type_node.value
                        else:
                            continue
                        
                        pins.append((pin_name, pin_type))
            break
    
    return pins


def _has_keyword(decorator: ast.Call, param_name: str) -> bool:
    return any(keyword.arg == param_name for keyword in decorator.keywords)


def _extract_string_from_decorator(decorator: ast.Call, param_name: str) -> str:
    """从装饰器调用中提取字符串参数
    
    Args:
        decorator: 装饰器调用AST节点
        param_name: 参数名
        
    Returns:
        字符串值，如果未找到返回空字符串
    """
    for keyword in decorator.keywords:
        if keyword.arg == param_name:
            if isinstance(keyword.value, ast.Constant):
                return keyword.value.value
            break
    return ""


def _extract_bool_from_decorator(decorator: ast.Call, param_name: str, default: bool) -> bool:
    """从装饰器调用中提取布尔参数
    
    Args:
        decorator: 装饰器调用AST节点
        param_name: 参数名
        default: 默认值
        
    Returns:
        布尔值
    """
    for keyword in decorator.keywords:
        if keyword.arg == param_name:
            if isinstance(keyword.value, ast.Constant):
                return bool(keyword.value.value)
            break
    return default


def build_virtual_pins_from_signature(func_def: ast.FunctionDef) -> List[VirtualPinConfig]:
    """从函数签名构建虚拟引脚列表
    
    解析复合节点函数的输入参数和返回值，生成虚拟引脚配置。
    
    Args:
        func_def: 函数定义AST节点
        
    Returns:
        虚拟引脚配置列表（输入+输出）
    """
    virtual_pins: List[VirtualPinConfig] = []
    pin_index = 1
    
    # 解析输入参数（跳过第一个game参数）
    for arg in func_def.args.args[1:]:
        pin_name = arg.arg
        pin_type = _get_type_annotation(arg.annotation)
        # 流程输入识别：名称含"流程"或为"流程入"
        is_flow = (pin_name == '流程入' or ('流程' in pin_name))
        virtual_pins.append(VirtualPinConfig(
            pin_index=pin_index,
            pin_name=pin_name,
            pin_type=pin_type,
            is_input=True,
            is_flow=is_flow,
            description="",
            mapped_ports=[]  # 稍后在映射阶段填充
        ))
        pin_index += 1
    
    # 解析返回值
    if func_def.returns:
        return_pins = _parse_return_annotation(func_def.returns)
        for return_pin in return_pins:
            return_pin.pin_index = pin_index
            virtual_pins.append(return_pin)
            pin_index += 1

    # 函数格式复合节点也支持多个流程出口（通过返回值类型声明多个“流程”端口），
    # 具体分支结构同样由 IR 构建层处理。
    return virtual_pins


def _get_type_annotation(annotation: Optional[ast.expr]) -> str:
    """获取类型标注对应的引脚类型（仅接受中文端口类型标记）
    
    支持：
    - 中文基础类型：来自 BASE_TYPES.keys()
    - 中文列表类型：来自 LIST_TYPES.keys()
    - 常用扩展：'通用'、'泛型'、'字典'、'列表'、'泛型列表'、'流程'
    
    Args:
        annotation: 类型标注AST节点
        
    Returns:
        端口类型字符串
    """
    if annotation is None:
        return "泛型"

    # 兼容：字符串字面量形式的中文类型标注（推荐写法：例如 "浮点数"、"实体"、"流程"）
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        type_name = annotation.value.strip()
        # 使用common.py的验证函数
        return validate_pin_type_annotation(type_name, allow_python_builtin=False)

    if isinstance(annotation, ast.Name):
        type_name = annotation.id
        # 使用common.py的验证函数
        return validate_pin_type_annotation(type_name, allow_python_builtin=False)

    # 其他复杂标注目前不参与类型推断，回退为泛型
    return "泛型"


def _parse_return_annotation(returns: ast.expr) -> List[VirtualPinConfig]:
    """解析返回类型标注
    
    Args:
        returns: 返回类型标注AST节点
        
    Returns:
        返回值虚拟引脚列表
    """
    pins = []
    
    if isinstance(returns, ast.Constant) and isinstance(returns.value, str):
        # 单个返回值（字符串字面量形式，例如 -> "流程"）
        type_str = returns.value.strip()
        if type_str == 'None':
            return []
        
        pin_type = _get_type_annotation(returns)
        pins.append(VirtualPinConfig(
            pin_index=0,  # 稍后设置
            pin_name="返回值",
            pin_type=pin_type,
            is_input=False,
            is_flow=(pin_type == "流程"),
            description="",
            mapped_ports=[]
        ))
    
    elif isinstance(returns, ast.Name):
        # 单个返回值（名称形式，例如 -> 流程）
        if returns.id == 'None':
            return []

        # 复用输入类型解析逻辑（同样拒绝内置Python类型）
        pin_type = _get_type_annotation(returns)
        pins.append(VirtualPinConfig(
            pin_index=0,  # 稍后设置
            pin_name="返回值",
            pin_type=pin_type,
            is_input=False,
            is_flow=(pin_type == "流程"),
            description="",
            mapped_ports=[]
        ))
    
    elif isinstance(returns, ast.Subscript):
        # Tuple[type1, type2, ...]
        if isinstance(returns.value, ast.Name) and returns.value.id == 'Tuple':
            if isinstance(returns.slice, ast.Tuple):
                # 多个返回值
                for i, elt in enumerate(returns.slice.elts):
                    if isinstance(elt, ast.Name):
                        # 支持中文类型名（拒绝内置Python类型名）
                        pin_type = _get_type_annotation(elt)
                    elif isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        # 支持字符串字面量形式的类型标注
                        pin_type = _get_type_annotation(elt)
                    else:
                        pin_type = "泛型"
                    
                    pins.append(VirtualPinConfig(
                        pin_index=0,  # 稍后设置
                        pin_name=f"返回值{i+1}",
                        pin_type=pin_type,
                        is_input=False,
                        is_flow=(pin_type == "流程"),
                        description="",
                        mapped_ports=[]
                    ))
    
    return pins


def map_input_parameters_to_nodes(
    virtual_pins: List[VirtualPinConfig],
    param_usage: Dict[str, List[Tuple[str, str]]],
) -> None:
    """将输入参数映射到节点端口
    
    根据参数使用记录，填充输入虚拟引脚的mapped_ports字段。
    
    Args:
        virtual_pins: 虚拟引脚列表（会被直接修改）
        param_usage: 参数使用记录 {参数名: [(node_id, port_name), ...]}
    """
    for vpin in virtual_pins:
        if not vpin.is_input:
            continue
        
        param_name = vpin.pin_name
        if param_name in param_usage:
            for node_id, port_name in param_usage[param_name]:
                vpin.mapped_ports.append(MappedPort(
                    node_id=node_id,
                    port_name=port_name,
                    is_input=True,
                    is_flow=vpin.is_flow,
                ))


def map_return_values_to_nodes(
    virtual_pins: List[VirtualPinConfig],
    return_vars: List[str],
    var_map: Dict[str, Tuple[str, str]],
) -> None:
    """将返回值映射到节点输出端口
    
    根据return语句中的变量，查找变量来源并填充输出虚拟引脚的mapped_ports字段。
    
    Args:
        virtual_pins: 虚拟引脚列表（会被直接修改）
        return_vars: return语句中的变量名列表
        var_map: 变量映射 {变量名: (node_id, port_name)}
    """
    output_pins = [vpin for vpin in virtual_pins if not vpin.is_input]
    
    for i, var_name in enumerate(return_vars):
        if i >= len(output_pins):
            break
        
        if var_name in var_map:
            node_id, port_name = var_map[var_name]
            output_pins[i].mapped_ports.append(MappedPort(
                node_id=node_id,
                port_name=port_name,
                is_input=False,
                is_flow=False,
            ))


