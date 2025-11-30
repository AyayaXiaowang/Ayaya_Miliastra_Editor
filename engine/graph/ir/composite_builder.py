"""复合节点构建器

提供复合节点特有的解析逻辑：参数使用追踪、常量变量采集、return语句处理等。
"""
from __future__ import annotations

import ast
import uuid
from typing import Dict, List, Optional, Tuple, Set

from engine.graph.models import NodeModel, PortModel
from engine.graph.utils.ast_utils import extract_constant_value, NOT_EXTRACTABLE
from .arg_normalizer import normalize_call_arguments


class CompositeContext:
    """复合节点解析上下文
    
    记录复合节点特有的状态：
    - 输入参数使用情况
    - 常量变量声明
    - return语句中的变量
    """
    
    def __init__(self, param_names: List[str]):
        """初始化上下文
        
        Args:
            param_names: 输入参数名列表（跳过game）
        """
        self.param_names: Set[str] = set(param_names)
        # 参数使用记录：{参数名: [(node_id, port_name), ...]}
        self.param_usage: Dict[str, List[Tuple[str, str]]] = {}
        # 常量变量：{变量名: 常量文本值}
        self.const_var_values: Dict[str, str] = {}
        # return语句中的变量名列表
        self.return_vars: List[str] = []
    
    def record_param_usage(self, param_name: str, node_id: str, port_name: str) -> None:
        """记录参数使用
        
        Args:
            param_name: 参数名
            node_id: 使用该参数的节点ID
            port_name: 使用该参数的端口名
        """
        if param_name not in self.param_names:
            return
        
        if param_name not in self.param_usage:
            self.param_usage[param_name] = []
        self.param_usage[param_name].append((node_id, port_name))
    
    def add_const_var(self, var_name: str, value: str) -> None:
        """添加常量变量
        
        Args:
            var_name: 变量名
            value: 常量值（文本形式）
        """
        self.const_var_values[var_name] = value
    
    def set_return_vars(self, var_names: List[str]) -> None:
        """设置return语句中的变量
        
        Args:
            var_names: 变量名列表
        """
        self.return_vars = var_names


def extract_constant_declarations(func_body: List[ast.stmt], comp_ctx: CompositeContext) -> None:
    """从函数体中提取常量声明
    
    识别形如以下的赋值语句并记录为常量变量：
    - `排序方式_枚举: "枚举" = "降序"`
    - `X = 3.14`
    
    Args:
        func_body: 函数体语句列表
        comp_ctx: 复合节点上下文（会被修改）
    """
    for stmt in func_body:
        # 带类型标注的赋值（AnnAssign）
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name):
                var_name = stmt.target.id
                if stmt.value:
                    const_val = extract_constant_value(stmt.value)
                    if const_val is not NOT_EXTRACTABLE:
                        comp_ctx.add_const_var(var_name, str(const_val))
        
        # 普通赋值（Assign）
        elif isinstance(stmt, ast.Assign):
            if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                var_name = stmt.targets[0].id
                const_val = extract_constant_value(stmt.value)
                if const_val is not NOT_EXTRACTABLE:
                    comp_ctx.add_const_var(var_name, str(const_val))


def extract_return_variables(func_body: List[ast.stmt], comp_ctx: CompositeContext) -> None:
    """从函数体中提取return语句的变量
    
    支持：
    - `return var`（单个返回值）
    - `return var1, var2, var3`（多个返回值）
    - `return (var1, var2)`（元组返回值）
    
    Args:
        func_body: 函数体语句列表
        comp_ctx: 复合节点上下文（会被修改）
    """
    for stmt in ast.walk(ast.Module(body=func_body)):
        if isinstance(stmt, ast.Return) and stmt.value:
            var_names = _extract_var_names_from_return(stmt.value)
            if var_names:
                comp_ctx.set_return_vars(var_names)
                break  # 只处理第一个return


def _extract_var_names_from_return(value_node: ast.expr) -> List[str]:
    """从return表达式中提取变量名
    
    Args:
        value_node: return值的AST节点
        
    Returns:
        变量名列表
    """
    if isinstance(value_node, ast.Name):
        return [value_node.id]
    
    if isinstance(value_node, ast.Tuple):
        var_names = []
        for elt in value_node.elts:
            if isinstance(elt, ast.Name):
                var_names.append(elt.id)
        return var_names
    
    return []


def track_parameter_usage_in_call(
    call_node: ast.Call,
    node_id: str,
    comp_ctx: CompositeContext,
) -> None:
    """追踪调用表达式中的参数使用
    
    扫描函数调用的参数，如果发现使用了输入参数，则记录到上下文中。
    
    Args:
        call_node: 函数调用AST节点
        node_id: 当前节点ID
        comp_ctx: 复合节点上下文（会被修改）
    """
    # 扫描位置参数
    for i, arg in enumerate(call_node.args):
        _track_param_in_expr(arg, node_id, f"arg_{i}", comp_ctx)
    
    # 扫描关键字参数
    for keyword in call_node.keywords:
        if keyword.arg:
            _track_param_in_expr(keyword.value, node_id, keyword.arg, comp_ctx)


def _track_param_in_expr(expr: ast.expr, node_id: str, port_name: str, comp_ctx: CompositeContext) -> None:
    """递归追踪表达式中的参数使用
    
    Args:
        expr: 表达式AST节点
        node_id: 节点ID
        port_name: 端口名
        comp_ctx: 复合节点上下文（会被修改）
    """
    if isinstance(expr, ast.Name):
        if expr.id in comp_ctx.param_names:
            comp_ctx.record_param_usage(expr.id, node_id, port_name)
    
    # 递归处理嵌套表达式
    for child in ast.walk(expr):
        if isinstance(child, ast.Name) and child.id in comp_ctx.param_names:
            comp_ctx.record_param_usage(child.id, node_id, port_name)


def create_composite_node_from_instance_call(call_node: ast.Call, node_library: Dict, env) -> Optional[NodeModel]:
    """识别并创建复合节点实例方法调用的节点
    
    识别形式：self.xxx.yyy(...) 
    其中 xxx 是复合节点实例，yyy 是方法名
    
    Args:
        call_node: 调用节点
        node_library: 节点库（{节点名: NodeDef}）
        env: 变量环境（VarEnv）
        
    Returns:
        如果识别成功，返回创建的NodeModel；否则返回None
    """
    if not isinstance(call_node.func, ast.Attribute):
        return None
    
    # 检查是否是 self.属性.方法() 的形式
    method_name = call_node.func.attr
    obj = call_node.func.value
    
    # 暂时只处理简单的 self.xxx 形式
    if not isinstance(obj, ast.Attribute):
        return None
    if not isinstance(obj.value, ast.Name) or obj.value.id != 'self':
        return None
    
    instance_attr = obj.attr  # 实例属性名，如 "延迟执行器"
    
    # 从环境中查找实例属性对应的复合节点ID
    composite_id = env.get_composite_instance(instance_attr)
    
    # 在节点库中查找匹配的复合节点
    target_node_def = None
    for key, node_def in node_library.items():
        if not hasattr(node_def, 'is_composite') or not node_def.is_composite:
            continue
        
        # 如果有composite_id，精确匹配
        if composite_id and hasattr(node_def, 'composite_id'):
            if node_def.composite_id == composite_id:
                target_node_def = node_def
                break
        
        # 否则，通过名称模糊匹配（类格式复合节点）
        # 检查类名是否包含在实例属性名中，或者实例属性名包含在类名中
        node_name_lower = node_def.name.lower().replace('_', '').replace('-', '')
        attr_lower = instance_attr.lower().replace('_', '').replace('-', '')
        if node_name_lower in attr_lower or attr_lower in node_name_lower:
            target_node_def = node_def
            break
    
    if not target_node_def:
        return None
    
    # 创建节点
    node_id = f"composite_{target_node_def.name}_{uuid.uuid4().hex[:8]}"
    
    # 创建输入输出端口（包括流程端口）
    input_ports = []
    output_ports = []
    
    for inp in target_node_def.inputs:
        port_type = target_node_def.input_types.get(inp, "泛型")
        input_ports.append(PortModel(name=inp, is_input=True))
    
    for outp in target_node_def.outputs:
        port_type = target_node_def.output_types.get(outp, "泛型")
        output_ports.append(PortModel(name=outp, is_input=False))
    
    node = NodeModel(
        id=node_id,
        title=target_node_def.name,
        category=target_node_def.category,
        pos=(100.0, 100.0),
        inputs=input_ports,
        outputs=output_ports,
        composite_id=target_node_def.composite_id if hasattr(target_node_def, 'composite_id') else ""
    )
    
    # 重建端口映射
    node._rebuild_port_maps()
    
    # 源码行号：记录调用表达式位置，便于错误定位与稳定布局
    node.source_lineno = getattr(call_node, 'lineno', 0)
    node.source_end_lineno = getattr(call_node, 'end_lineno', getattr(call_node, 'lineno', 0))
    
    # 常量回填：与普通节点保持一致，将可静态提取的字面量写入 input_constants
    # 说明：数据连线在后续由 create_data_edges_for_node_enhanced 负责建立
    norm = normalize_call_arguments(call_node, target_node_def)  # 统一归一化（位置/关键字）
    # 位置参数（已映射到目标端口名）
    for dst_port, expr in norm.positional:
        val = extract_constant_value(expr)
        if val is not NOT_EXTRACTABLE:
            node.input_constants[dst_port] = str(val)
    # 关键字参数
    for pname, expr in norm.keywords.items():
        val = extract_constant_value(expr)
        if val is not NOT_EXTRACTABLE:
            node.input_constants[pname] = str(val)
    
    # 记录实例属性关联（用于后续匹配）
    if hasattr(target_node_def, 'composite_id'):
        env.set_composite_instance(instance_attr, target_node_def.composite_id)
    
    return node


