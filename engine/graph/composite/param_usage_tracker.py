"""参数使用追踪器

提供复合节点内部的形参使用采集、别名传播和常量采集能力。
"""

from __future__ import annotations
import ast
from typing import Dict, List, Tuple, Optional

from engine.graph.models import NodeModel


class ParamUsageTracker:
    """参数使用追踪器
    
    功能：
    1. 追踪函数形参在方法体内的使用位置（节点ID + 端口名）
    2. 支持 Name←Name 的别名传播（当别名来源为形参时）
    3. 采集常量变量定义（AnnAssign 和 Assign）
    4. 将常量值回填到节点的 input_constants
    5. 可选：追踪简单的实例字段别名 `self.xxx` ← 入口形参，用于类格式复合节点的跨方法虚拟引脚映射
    """
    
    def __init__(
        self,
        param_names: List[str],
        node_name_index: Dict[str, str],
        node_library: Dict,
        verbose: bool = False,
        state_attr_to_param: Optional[Dict[str, str]] = None,
    ):
        """初始化追踪器
        
        Args:
            param_names: 形参名称列表
            node_name_index: 节点名索引（含同义键）
            node_library: 节点库
            verbose: 是否输出详细日志
            state_attr_to_param: 可选的实例字段别名映射，如 {"_定时器标识": "定时器标识"}
        """
        self.param_names = set(param_names)
        self.node_name_index = node_name_index
        self.node_library = node_library
        self.verbose = verbose
        
        # 参数使用记录：参数名 -> [(节点ID, 端口名), ...]
        self.input_param_usage: Dict[str, List[Tuple[str, str]]] = {p: [] for p in param_names}
        
        # 类级状态别名：实例字段名（不含 self. 前缀） -> 入口形参名
        self.state_attr_to_param: Dict[str, str] = dict(state_attr_to_param or {})
        # 状态别名对应的“虚拟引脚使用”：入口形参名 -> [(节点ID, 端口名), ...]
        self.state_pin_usage: Dict[str, List[Tuple[str, str]]] = {
            pin_name: [] for pin_name in self.state_attr_to_param.values()
        }

        # 形参是否在控制流条件中被使用（例如 if 条件: / while 条件:）
        # 键为入口形参名，值为布尔标记；用于支持“仅通过控制流使用”的虚拟引脚判定。
        self.control_flow_usage: Dict[str, bool] = {param_name: False for param_name in param_names}
        
        # 别名映射：别名 -> 原始形参名
        self.alias_of_param: Dict[str, str] = {}
        
        # 常量变量映射：变量名 -> 原始文本值
        self.const_var_values: Dict[str, str] = {}
    
    def collect_aliases(self, stmts: List[ast.stmt]) -> None:
        """采集别名传播关系（Name <- Name）
        
        Args:
            stmts: 语句列表
        """
        self._collect_param_aliases_recursive(stmts)
    
    def collect_constants(self, stmts: List[ast.stmt]) -> None:
        """采集常量变量定义
        
        Args:
            stmts: 语句列表
        """
        self._collect_constant_vars_recursive(stmts)
    
    def collect_usage_from_calls(self, stmts: List[ast.stmt], title_to_queue: Dict[str, List[NodeModel]]) -> None:
        """从调用语句中采集参数使用
        
        Args:
            stmts: 语句列表
            title_to_queue: 节点标题到节点队列的映射（按创建顺序）
        """
        self._traverse_and_record_usage(stmts, title_to_queue)

    def collect_control_flow_usage(self, stmts: List[ast.stmt]) -> None:
        """采集形参在控制流条件中的使用情况。

        目前关注典型结构：
        - if 条件:
        - while 条件:
        其中 条件 可以是：
        - 直接引用入口形参；
        - 入口形参的简单别名；
        - self.xxx 形式且 xxx 与入口形参存在别名关系。
        """
        self._collect_control_flow_usage_recursive(stmts)
    
    def backfill_constants_to_nodes(self, stmts: List[ast.stmt], nodes: List[NodeModel]) -> None:
        """将常量值回填到节点的 input_constants
        
        Args:
            stmts: 语句列表
            nodes: 节点列表
        """
        # 构建调用列表
        call_list: List[Tuple[str, Dict[str, str]]] = []  # [(func_name, {param_name: const_var_name})]
        self._collect_const_var_refs(stmts, call_list)
        
        # 建立节点标题索引队列
        backfill_title_to_queue: Dict[str, List[NodeModel]] = {}
        for node in nodes:
            self._enqueue_aliases(node.title, node, backfill_title_to_queue)
        
        # 按顺序回填常量
        for func_name, const_params in call_list:
            target_queue = self._find_node_queue(func_name, backfill_title_to_queue)
            if target_queue and len(target_queue) > 0:
                target_node = target_queue.pop(0)
                for param_name, var_name in const_params.items():
                    target_node.input_constants[param_name] = self.const_var_values[var_name]
    
    # ========== 内部方法 ==========
    
    def _collect_param_aliases_recursive(self, stmts: List[ast.stmt]) -> None:
        """递归采集别名关系"""
        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                val = stmt.value
                if isinstance(val, ast.Name):
                    src = val.id
                    targets: List[ast.expr] = list(stmt.targets or [])
                    for target in targets:
                        if isinstance(target, ast.Name):
                            dst_name = target.id
                            if src in self.input_param_usage:
                                self.alias_of_param[dst_name] = src
                            elif src in self.alias_of_param:
                                self.alias_of_param[dst_name] = self.alias_of_param[src]
                        elif isinstance(target, ast.Tuple):
                            for elt in target.elts:
                                if isinstance(elt, ast.Name):
                                    dst = elt.id
                                    if src in self.input_param_usage:
                                        self.alias_of_param[dst] = src
                                    elif src in self.alias_of_param:
                                        self.alias_of_param[dst] = self.alias_of_param[src]
            
            elif isinstance(stmt, ast.AnnAssign):
                val2 = getattr(stmt, "value", None)
                target2 = getattr(stmt, "target", None)
                if isinstance(val2, ast.Name) and isinstance(target2, ast.Name):
                    src2 = val2.id
                    dst2 = target2.id
                    if src2 in self.input_param_usage:
                        self.alias_of_param[dst2] = src2
                    elif src2 in self.alias_of_param:
                        self.alias_of_param[dst2] = self.alias_of_param[src2]
            
            # 递归处理控制流
            elif isinstance(stmt, ast.If):
                self._collect_param_aliases_recursive(stmt.body or [])
                self._collect_param_aliases_recursive(stmt.orelse or [])
            elif hasattr(ast, "Match") and isinstance(stmt, getattr(ast, "Match")):
                for case in getattr(stmt, "cases", []):
                    self._collect_param_aliases_recursive(getattr(case, "body", []) or [])
            elif isinstance(stmt, ast.For):
                self._collect_param_aliases_recursive(stmt.body or [])
                self._collect_param_aliases_recursive(getattr(stmt, "orelse", []) or [])
            elif isinstance(stmt, ast.While):
                self._collect_param_aliases_recursive(stmt.body or [])
                self._collect_param_aliases_recursive(getattr(stmt, "orelse", []) or [])
    
    def _collect_constant_vars_recursive(self, stmts: List[ast.stmt]) -> None:
        """递归采集常量变量定义"""
        for stmt in stmts:
            if isinstance(stmt, ast.AnnAssign):
                target = getattr(stmt, "target", None)
                value = getattr(stmt, "value", None)
                if isinstance(target, ast.Name) and isinstance(value, ast.Constant):
                    self.const_var_values[target.id] = str(value.value)
            
            elif isinstance(stmt, ast.Assign):
                # 仅处理单目标 Name <- Constant
                if len(getattr(stmt, "targets", [])) == 1:
                    target0 = stmt.targets[0]
                    if isinstance(target0, ast.Name) and isinstance(stmt.value, ast.Constant):
                        self.const_var_values[target0.id] = str(stmt.value.value)
            
            # 递归处理控制流
            elif isinstance(stmt, ast.If):
                self._collect_constant_vars_recursive(stmt.body or [])
                self._collect_constant_vars_recursive(stmt.orelse or [])
            elif hasattr(ast, "Match") and isinstance(stmt, getattr(ast, "Match")):
                for case in getattr(stmt, "cases", []):
                    self._collect_constant_vars_recursive(getattr(case, "body", []) or [])
            elif isinstance(stmt, ast.For):
                self._collect_constant_vars_recursive(stmt.body or [])
                self._collect_constant_vars_recursive(getattr(stmt, "orelse", []) or [])

    def _collect_control_flow_usage_recursive(self, stmts: List[ast.stmt]) -> None:
        """递归采集控制流条件中对入口形参的使用。"""
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                self._record_control_flow_from_expr(stmt.test)
                self._collect_control_flow_usage_recursive(stmt.body or [])
                self._collect_control_flow_usage_recursive(stmt.orelse or [])
            elif isinstance(stmt, ast.While):
                self._record_control_flow_from_expr(stmt.test)
                self._collect_control_flow_usage_recursive(stmt.body or [])
                self._collect_control_flow_usage_recursive(getattr(stmt, "orelse", []) or [])
            elif hasattr(ast, "Match") and isinstance(stmt, getattr(ast, "Match")):
                # match 语句的 subject 也视为控制流条件来源：
                #   match 控制表达式:
                #       case ...:
                #           ...
                # 若 subject 为入口形参或者其别名/实例字段别名，需要将其标记为控制流使用，
                # 以便后续将对应的数据输入虚拟引脚映射到“多分支”节点的控制表达式输入端口。
                subject = getattr(stmt, "subject", None)
                if isinstance(subject, ast.expr):
                    self._record_control_flow_from_expr(subject)
                for case in getattr(stmt, "cases", []):
                    self._collect_control_flow_usage_recursive(getattr(case, "body", []) or [])
            elif isinstance(stmt, ast.For):
                self._collect_control_flow_usage_recursive(stmt.body or [])
                self._collect_control_flow_usage_recursive(getattr(stmt, "orelse", []) or [])
            elif isinstance(stmt, ast.Try):
                # 按当前项目约定不会使用 try/except 包裹复合节点逻辑，但为了稳健仍递归子块
                self._collect_control_flow_usage_recursive(stmt.body or [])
                self._collect_control_flow_usage_recursive(stmt.finalbody or [])
                self._collect_control_flow_usage_recursive(stmt.orelse or [])
                for handler in getattr(stmt, "handlers", []):
                    self._collect_control_flow_usage_recursive(getattr(handler, "body", []) or [])

    def _record_control_flow_from_expr(self, expr: ast.expr) -> None:
        """在单个条件表达式中标记入口形参的控制流使用。"""
        if isinstance(expr, ast.Name):
            self._mark_param_control_flow_usage(expr.id)
        elif isinstance(expr, ast.Attribute):
            # 例如：if self.xxx:
            self._record_state_alias_usage_in_control_flow(expr)
        elif isinstance(expr, ast.UnaryOp):
            # 例如：if not 条件:
            operand = getattr(expr, "operand", None)
            if isinstance(operand, ast.expr):
                self._record_control_flow_from_expr(operand)
        elif isinstance(expr, ast.BoolOp):
            # 例如：if 条件 and 其他:
            for value in getattr(expr, "values", []):
                if isinstance(value, ast.expr):
                    self._record_control_flow_from_expr(value)
        elif isinstance(expr, ast.Compare):
            # 例如：if 条件 == 1:
            left = getattr(expr, "left", None)
            if isinstance(left, ast.expr):
                self._record_control_flow_from_expr(left)
            for comparator in getattr(expr, "comparators", []):
                if isinstance(comparator, ast.expr):
                    self._record_control_flow_from_expr(comparator)
        elif isinstance(expr, ast.Call):
            # 例如：if IsTrue(条件):
            for arg_expr in getattr(expr, "args", []):
                if isinstance(arg_expr, ast.expr):
                    self._record_control_flow_from_expr(arg_expr)
            for keyword in getattr(expr, "keywords", []):
                value_expr = getattr(keyword, "value", None)
                if isinstance(value_expr, ast.expr):
                    self._record_control_flow_from_expr(value_expr)
        elif isinstance(expr, ast.IfExp):
            # 三元表达式内部的条件
            test_expr = getattr(expr, "test", None)
            if isinstance(test_expr, ast.expr):
                self._record_control_flow_from_expr(test_expr)

    def _mark_param_control_flow_usage(self, name: str) -> None:
        """根据变量名标记其来源入口形参的控制流使用。"""
        if name in self.control_flow_usage:
            self.control_flow_usage[name] = True
        elif name in self.alias_of_param:
            original_param_name = self.alias_of_param[name]
            if original_param_name in self.control_flow_usage:
                self.control_flow_usage[original_param_name] = True

    def _record_state_alias_usage_in_control_flow(self, expr: ast.Attribute) -> None:
        """当条件表达式中出现 self.xxx 且 xxx 对应入口形参别名时，标记该入口形参。"""
        owner = expr.value
        if not isinstance(owner, ast.Name) or owner.id != "self":
            return
        attribute_name = expr.attr
        param_name = self.state_attr_to_param.get(attribute_name)
        if not param_name:
            return
        if param_name in self.control_flow_usage:
            self.control_flow_usage[param_name] = True
    
    def _traverse_and_record_usage(self, stmts: List[ast.stmt], title_to_queue: Dict[str, List[NodeModel]]) -> None:
        """递归遍历并记录参数使用"""
        for stmt in stmts:
            call_node = None
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call_node = stmt.value
            elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                call_node = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and isinstance(getattr(stmt, "value", None), ast.Call):
                call_node = getattr(stmt, "value")
            
            if call_node:
                self._match_one_call(call_node, title_to_queue)
            
            # 递归处理控制流
            if isinstance(stmt, ast.If):
                self._traverse_and_record_usage(stmt.body or [], title_to_queue)
                self._traverse_and_record_usage(stmt.orelse or [], title_to_queue)
            elif hasattr(ast, "Match") and isinstance(stmt, getattr(ast, "Match")):
                for case in getattr(stmt, "cases", []):
                    self._traverse_and_record_usage(getattr(case, "body", []) or [], title_to_queue)
            elif isinstance(stmt, ast.For):
                self._traverse_and_record_usage(stmt.body or [], title_to_queue)
                self._traverse_and_record_usage(getattr(stmt, "orelse", []) or [], title_to_queue)
            elif isinstance(stmt, ast.While):
                self._traverse_and_record_usage(stmt.body or [], title_to_queue)
                self._traverse_and_record_usage(getattr(stmt, "orelse", []) or [], title_to_queue)
    
    def _match_one_call(self, call_expr: ast.Call, title_to_queue: Dict[str, List[NodeModel]]) -> None:
        """匹配单个调用并记录参数使用"""
        if not isinstance(call_expr.func, ast.Name):
            return
        
        func_name = call_expr.func.id
        queue = self._find_node_queue(func_name, title_to_queue)
        if not queue:
            return
        
        dst_node = queue.pop(0)
        
        # 关键字参数
        for keyword in getattr(call_expr, 'keywords', []):
            param_name = keyword.arg
            val = keyword.value
            if isinstance(val, ast.Name):
                nm = val.id
                bound = nm if nm in self.input_param_usage else self.alias_of_param.get(nm, "")
                if bound and bound in self.input_param_usage:
                    self.input_param_usage[bound].append((dst_node.id, param_name))
            elif isinstance(val, ast.Attribute):
                # self.xxx 形式：若 xxx 与入口形参存在别名关系，则记录为对应虚拟引脚的使用
                self._record_state_alias_usage(val, dst_node, param_name)
        
        # 位置参数（跳过第一个 game），用于变参节点的数字端口 0/1/2...
        if getattr(call_expr, 'args', None):
            data_index_for_variadic = -1
            for i, arg_expr in enumerate(call_expr.args):
                if i == 0:
                    continue
                data_index_for_variadic += 1
                port_name_for_variadic = str(data_index_for_variadic)
                if isinstance(arg_expr, ast.Name):
                    nm2 = arg_expr.id
                    bound2 = nm2 if nm2 in self.input_param_usage else self.alias_of_param.get(nm2, "")
                    if bound2 and bound2 in self.input_param_usage:
                        self.input_param_usage[bound2].append((dst_node.id, port_name_for_variadic))
                elif isinstance(arg_expr, ast.Attribute):
                    self._record_state_alias_usage(arg_expr, dst_node, port_name_for_variadic)
    
    def _record_state_alias_usage(self, expr: ast.expr, dst_node: NodeModel, port_name: str) -> None:
        """当参数是 self.xxx 且 xxx 与入口形参存在别名关系时，记录该入口形参在当前端口上的使用位置。"""
        if not isinstance(expr, ast.Attribute):
            return
        owner = expr.value
        if not isinstance(owner, ast.Name) or owner.id != "self":
            return
        attr_name = expr.attr
        param_name = self.state_attr_to_param.get(attr_name)
        if not param_name:
            return
        if param_name not in self.state_pin_usage:
            self.state_pin_usage[param_name] = []
        self.state_pin_usage[param_name].append((dst_node.id, port_name))
    
    def _collect_const_var_refs(self, stmts: List[ast.stmt], call_list: List[Tuple[str, Dict[str, str]]]) -> None:
        """遍历AST，收集所有引用了常量变量的节点调用"""
        for stmt in stmts:
            call_node = None
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call_node = stmt.value
            elif isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                call_node = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and isinstance(getattr(stmt, "value", None), ast.Call):
                call_node = getattr(stmt, "value")
            
            if call_node and isinstance(call_node.func, ast.Name):
                func_name = call_node.func.id
                const_params: Dict[str, str] = {}
                
                # 收集引用了常量变量的参数
                for keyword in getattr(call_node, 'keywords', []):
                    param_name = keyword.arg
                    param_value = keyword.value
                    if isinstance(param_value, ast.Name):
                        var_name = param_value.id
                        if var_name in self.const_var_values:
                            const_params[param_name] = var_name
                
                if const_params:
                    call_list.append((func_name, const_params))
                else:
                    # 即使没有常量参数，也要记录，以保持与节点的顺序一致
                    call_list.append((func_name, {}))
            
            # 递归处理控制流语句
            if isinstance(stmt, ast.If):
                self._collect_const_var_refs(stmt.body or [], call_list)
                self._collect_const_var_refs(stmt.orelse or [], call_list)
            elif hasattr(ast, "Match") and isinstance(stmt, getattr(ast, "Match")):
                for case in getattr(stmt, "cases", []):
                    self._collect_const_var_refs(getattr(case, "body", []) or [], call_list)
            elif isinstance(stmt, ast.For):
                self._collect_const_var_refs(stmt.body or [], call_list)
                self._collect_const_var_refs(getattr(stmt, "orelse", []) or [], call_list)
            elif isinstance(stmt, ast.While):
                self._collect_const_var_refs(stmt.body or [], call_list)
                self._collect_const_var_refs(getattr(stmt, "orelse", []) or [], call_list)
    
    def _find_node_queue(self, func_name: str, title_to_queue: Dict[str, List[NodeModel]]) -> Optional[List[NodeModel]]:
        """查找节点队列（支持同义键）"""
        queue = title_to_queue.get(func_name)
        if not queue:
            full_key = self.node_name_index.get(func_name)
            if full_key:
                node_def_for_name = self.node_library.get(full_key)
                if node_def_for_name:
                    queue = (
                        title_to_queue.get(node_def_for_name.name)
                        or title_to_queue.get(node_def_for_name.name.replace('/', ''))
                    )
        return queue
    
    def _enqueue_aliases(self, title: str, node: NodeModel, queue_dict: Dict[str, List[NodeModel]]) -> None:
        """将节点加入队列（含同义键）"""
        queue_dict.setdefault(title, []).append(node)
        if '/' in title:
            queue_dict.setdefault(title.replace('/', ''), []).append(node)


