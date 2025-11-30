from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any
from collections import defaultdict
from datetime import datetime

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.graph.models import GraphModel, NodeModel
from engine.graph.common import is_flow_port, SIGNAL_LISTEN_NODE_TITLE
from engine.nodes.port_type_system import is_flow_port_with_context
from engine.graph.utils.metadata_extractor import extract_metadata_from_code
from engine.graph.utils.ast_utils import is_class_structure_format
from engine.graph.utils.comment_extractor import extract_comments, associate_comments_to_nodes
from engine.graph.code_to_graph_orchestrator import CodeToGraphParser


"""节点图代码（Graph Code）解析工具集。

提供从类结构 Python 文件到 `GraphModel` 的解析能力，委托 `CodeToGraphParser` 和 utils 工具。
设计为**静态建模 + 校验**组件：只关心“用哪些节点、如何连线、元数据和注释”，不会执行节点实际业务逻辑，主要用于给 AI / 开发者提供可验证的节点图代码接口。
"""


# ============================================================================
# 验证函数（保持不变）
# ============================================================================

def validate_graph(
    model: GraphModel,
    virtual_pin_mappings: Optional[Dict[Tuple[str, str], bool]] = None,
    *,
    workspace_path: Optional[Path] = None,
    node_library: Optional[Dict[str, NodeDef]] = None,
) -> List[str]:
    """验证图的完整性（简化版本）
    
    Args:
        model: 节点图模型
        virtual_pin_mappings: 虚拟引脚映射 {(node_id, port_name): is_input}
                             用于复合节点编辑器，标记哪些端口已暴露为虚拟引脚
        workspace_path: 工作区路径（可选，未提供 node_library 时用于加载节点库）
        node_library: 预加载的节点库（可选，避免重复加载）
    
    Returns:
        错误列表
    """
    errors: List[str] = []
    virtual_pin_mappings = virtual_pin_mappings or {}
    
    # 获取节点库（用于端口类型查询）
    if node_library is None:
        workspace = workspace_path or Path(__file__).resolve().parents[2]
        registry = get_node_registry(workspace)
        node_library = registry.get_library()
    
    incoming_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for edge in model.edges.values():
        incoming_counts[edge.dst_node][edge.dst_port] += 1
    
    def _is_flow(node: NodeModel, port_name: str, is_source: bool) -> bool:
        return is_flow_port_with_context(node, port_name, is_source, node_library)
    
    # 检查端口类型匹配：流程端口不能连接到数据端口
    # 说明：使用集中式的上下文感知判定，覆盖"多分支"等语义特殊节点。

    for edge in model.edges.values():
        src_node = model.nodes.get(edge.src_node)
        dst_node = model.nodes.get(edge.dst_node)

        if not src_node or not dst_node:
            continue

        # 判断源端口和目标端口的类型（结合节点上下文和节点库定义）
        src_is_flow = _is_flow(src_node, edge.src_port, True)
        dst_is_flow = _is_flow(dst_node, edge.dst_port, False)

        # 流程端口和数据端口不能互连
        if src_is_flow != dst_is_flow:
            src_type = "流程端口" if src_is_flow else "数据端口"
            dst_type = "流程端口" if dst_is_flow else "数据端口"
            # 计算源/目标节点的源代码行范围（若有）
            src_lo = getattr(src_node, 'source_lineno', 0) if src_node else 0
            src_hi = getattr(src_node, 'source_end_lineno', 0) if src_node else 0
            dst_lo = getattr(dst_node, 'source_lineno', 0) if dst_node else 0
            dst_hi = getattr(dst_node, 'source_end_lineno', 0) if dst_node else 0
            lo_candidates = [x for x in [src_lo, dst_lo] if isinstance(x, int) and x > 0]
            hi_candidates = [x for x in [src_hi or src_lo, dst_hi or dst_lo] if isinstance(x, int) and x > 0]
            if lo_candidates and hi_candidates:
                span_lo = min(lo_candidates)
                span_hi = max(hi_candidates)
                span_text = f" (第{span_lo}~{span_hi}行)"
            else:
                span_text = " (第?~?行)"
            errors.append(
                f"端口类型不匹配：{src_node.title}.{edge.src_port}({src_type}) → "
                f"{dst_node.title}.{edge.dst_port}({dst_type}){span_text}"
            )
    
    for node in model.nodes.values():
        # 流程入口校验（事件节点除外）
        if node.category != '事件节点':
            incoming = incoming_counts.get(node.id, {})
            for port in node.inputs:
                if _is_flow(node, port.name, False) and port.name != '跳出循环':
                    in_count = incoming.get(port.name, 0)
                    is_virtual_pin = virtual_pin_mappings.get((node.id, port.name), False)
                    if in_count == 0 and not is_virtual_pin:
                        lo = getattr(node, 'source_lineno', 0)
                        hi = getattr(node, 'source_end_lineno', 0) or lo
                        span_text = f" (第{lo}~{hi}行)" if isinstance(lo, int) and lo > 0 else " (第?~?行)"
                        errors.append(f"节点 {node.category}/{node.title} 的流程入口 '{port.name}' 未连接{span_text}")
        
        incoming = incoming_counts.get(node.id, {})
        for port in node.inputs:
            if not _is_flow(node, port.name, False):
                has_incoming_edge = incoming.get(port.name, 0) > 0
                has_constant_value = port.name in node.input_constants
                is_virtual_pin = virtual_pin_mappings.get((node.id, port.name), False)
                if not (has_incoming_edge or has_constant_value or is_virtual_pin):
                    lo = getattr(node, 'source_lineno', 0)
                    hi = getattr(node, 'source_end_lineno', 0) or lo
                    span_text = f" (第{lo}~{hi}行)" if isinstance(lo, int) and lo > 0 else " (第?~?行)"
                    errors.append(f"节点 {node.category}/{node.title} 的输入端 \"{port.name}\" 缺少数据来源{span_text}")
    
    return errors


# ============================================================================
# 节点图代码解析器
# ============================================================================

class GraphParseError(Exception):
    """解析错误"""
    def __init__(self, message: str, line_number: Optional[int] = None):
        self.message = message
        self.line_number = line_number
        super().__init__(self._format_message())
    
    def _format_message(self) -> str:
        if self.line_number:
            return f"第{self.line_number}行: {self.message}"
        return self.message


class GraphCodeParser:
    """节点图代码解析器 - 从类结构 Python 文件解析节点图"""
    
    def __init__(self, workspace_path: Path, node_library: Optional[Dict[str, NodeDef]] = None, verbose: bool = False):
        """初始化解析器
        
        Args:
            workspace_path: 工作空间路径（Graph_Generater目录）
            node_library: 可选的节点库（如果为None，则自动加载）
            verbose: 是否输出详细日志
        """
        self.workspace_path = workspace_path
        self.verbose = verbose
        if node_library is not None:
            self.node_library = node_library
        else:
            registry = get_node_registry(workspace_path, include_composite=True)
            self.node_library = registry.get_library()
        self._code_parser = CodeToGraphParser(self.node_library, verbose=self.verbose)
    
    def parse_file(self, code_file: Path) -> Tuple[GraphModel, Dict[str, Any]]:
        """解析节点图代码文件为 GraphModel 和元数据
        
        Args:
            code_file: 文件路径
            
        Returns:
            (GraphModel, metadata字典)
            
        Raises:
            GraphParseError: 解析失败时抛出
        """
        # 文件路径用于错误信息
        file_path_str = str(code_file)
        
        # 1. 读取文件内容
        with open(code_file, 'r', encoding='utf-8') as f:
            code = f.read()
        
        # 2. 仅支持类结构格式（虚拟挂载架构）。判定失败直接报错。
        if not is_class_structure_format(code):
            raise GraphParseError(
                f"当前节点图文件不符合类结构 Python 格式。文件: {file_path_str}"
            )
        # 新格式：类结构（虚拟挂载架构）
        return self._parse_class_structure(code, code_file)
    
    def _parse_class_structure(self, code: str, code_file: Path) -> Tuple[GraphModel, Dict[str, Any]]:
        """解析类结构格式的节点图，委托CodeToGraphParser
        
        Args:
            code: 源代码
            code_file: 文件路径
            
        Returns:
            (GraphModel, metadata)
        """
        # 1. 提取元数据
        tree = ast.parse(code)
        metadata_obj = extract_metadata_from_code(code)
        metadata = {
            "graph_id": metadata_obj.graph_id,
            "graph_name": (metadata_obj.graph_name or "未命名节点图"),
            "graph_type": (metadata_obj.graph_type or "server"),
            "folder_path": metadata_obj.folder_path,
            "description": metadata_obj.description,
            "graph_variables": metadata_obj.graph_variables,
            "dynamic_ports": metadata_obj.dynamic_ports,
        }
        
        graph_name = metadata.get("graph_name", "未命名节点图")
        
        # 2. 委托CodeToGraphParser解析
        graph_model = self._code_parser.parse_code(code, graph_name, tree=tree)
        
        # 3. 设置元数据到GraphModel
        graph_model.graph_id = metadata.get("graph_id", graph_model.graph_id)
        graph_model.graph_name = graph_name
        graph_model.description = metadata.get("description", "")
        graph_model.metadata["parsed_from_class_structure"] = True
        graph_model.metadata["graph_type"] = metadata.get("graph_type", "server")
        # 使用相对仓库根目录的路径，避免泄露本地绝对路径
        workspace_root = self.workspace_path.resolve()
        code_path = code_file.resolve()
        root_parts = workspace_root.parts
        path_parts = code_path.parts
        relative_str = ""
        if len(path_parts) >= len(root_parts) and path_parts[:len(root_parts)] == root_parts:
            tail_parts = path_parts[len(root_parts):]
            if tail_parts:
                relative_str = "/".join(tail_parts)
            else:
                relative_str = code_path.name
        else:
            # 不在工作区下时，保存文件名以避免绝对路径
            relative_str = code_path.name
        graph_model.metadata["source_file"] = relative_str
        graph_model.metadata["parsed_at"] = datetime.now().isoformat()
        
        # 4. 基于 register_handlers 中的注册调用，为【监听信号】事件节点补充信号绑定。
        self._apply_signal_bindings_from_register_handlers(tree, graph_model)
        
        # 同步docstring中的图变量
        if metadata.get("graph_variables"):
            graph_model.graph_variables = metadata["graph_variables"]
        
        # 5. 提取并关联注释
        associate_comments_to_nodes(code, graph_model)
        
        if self.verbose:
            print(f"[OK] 成功解析节点图: {graph_name}")
            print(f"  节点数: {len(graph_model.nodes)}, 连线数: {len(graph_model.edges)}")
        
        return graph_model, metadata
    
    def _apply_signal_bindings_from_register_handlers(
        self,
        tree: ast.Module,
        graph_model: GraphModel,
    ) -> None:
        """从类内 register_handlers 调用中推导【监听信号】事件节点的信号绑定。

        约定：
        - 仅处理形如 self.game.register_event_handler(\"<signal_id>\", self.on_监听信号, owner=...) 的调用；
        - 若 GraphModel.metadata 中已存在针对该节点的 signal_bindings，则不覆盖用户在 UI 中配置的绑定。
        """
        if not isinstance(tree, ast.Module):
            return

        # 1) 构建事件名称 → 节点 ID 的映射（按解析顺序对齐 event_flow_order 与 event_flow_titles）。
        title_to_node_id: Dict[str, str] = {}
        titles = list(graph_model.event_flow_titles or [])
        ids = list(graph_model.event_flow_order or [])
        for node_id, title in zip(ids, titles):
            node = graph_model.nodes.get(node_id)
            if not node:
                continue
            if getattr(node, "category", "") != "事件节点":
                continue
            # 标题即事件名称（例如“实体创建时”/“监听信号”）
            title_to_node_id[str(title)] = str(node_id)

        if not title_to_node_id:
            return

        # 2) 定位图类与 register_handlers 方法。
        target_class: Optional[ast.ClassDef] = None
        register_func: Optional[ast.FunctionDef] = None
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "register_handlers":
                        target_class = node
                        register_func = item
                        break
            if register_func is not None:
                break

        if register_func is None:
            return

        # 3) 遍历 register_handlers 体内的所有 register_event_handler 调用。
        from engine.graph.models.graph_model import GraphModel as _GM  # 类型提示友好
        _ = _GM  # 占位强调依赖关系

        for stmt in register_func.body:
            for node in ast.walk(stmt):
                if not isinstance(node, ast.Call):
                    continue
                func_expr = node.func
                if not isinstance(func_expr, ast.Attribute):
                    continue
                if func_expr.attr != "register_event_handler":
                    continue

                args = list(node.args or [])
                if len(args) < 2:
                    continue

                event_name_node = args[0]
                handler_node = args[1]

                if not isinstance(event_name_node, ast.Constant) or not isinstance(
                    event_name_node.value, str
                ):
                    continue
                raw_event_name = str(event_name_node.value).strip()
                if not raw_event_name:
                    continue

                if not (
                    isinstance(handler_node, ast.Attribute)
                    and isinstance(handler_node.value, ast.Name)
                    and handler_node.value.id == "self"
                    and isinstance(handler_node.attr, str)
                    and handler_node.attr.startswith("on_")
                ):
                    continue

                method_base_name = handler_node.attr[3:]  # 去掉前缀 on_
                if not method_base_name:
                    continue

                node_id = title_to_node_id.get(method_base_name)
                if not node_id:
                    continue

                event_node = graph_model.nodes.get(node_id)
                if not event_node:
                    continue

                # 仅对【监听信号】事件节点写入 signal_bindings。
                if getattr(event_node, "title", "") != SIGNAL_LISTEN_NODE_TITLE:
                    continue

                # 若 UI 已经为该节点写入绑定，则不覆盖。
                existing_signal_id = graph_model.get_node_signal_id(node_id)
                if existing_signal_id:
                    continue

                graph_model.set_node_signal_binding(node_id, raw_event_name)


