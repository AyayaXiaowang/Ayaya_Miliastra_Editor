from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Sequence, Mapping
from collections import defaultdict
from datetime import datetime
import re

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.graph.models import GraphModel, NodeModel
from engine.graph.common import (
    is_flow_port,
    SIGNAL_LISTEN_NODE_TITLE,
    STRUCT_NODE_TITLES,
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_MODIFY_NODE_TITLE,
    STRUCT_SPLIT_STATIC_INPUTS,
    STRUCT_SPLIT_STATIC_OUTPUTS,
    STRUCT_BUILD_STATIC_INPUTS,
    STRUCT_BUILD_STATIC_OUTPUTS,
    STRUCT_MODIFY_STATIC_INPUTS,
    STRUCT_MODIFY_STATIC_OUTPUTS,
)
from importlib import import_module
from engine.nodes.port_type_system import is_flow_port_with_context
from engine.graph.utils.metadata_extractor import extract_metadata_from_code
from engine.graph.utils.ast_utils import is_class_structure_format
from engine.graph.utils.comment_extractor import extract_comments, associate_comments_to_nodes
from engine.graph.code_to_graph_orchestrator import CodeToGraphParser
from engine.utils.name_utils import dedupe_preserve_order


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
    
    def _allows_implicit_data_input(node: NodeModel, port_name: str) -> bool:
        """判断某些节点/端口是否允许“无显式数据来源”（由运行时代码注入默认值）。
        
        目前约定：
        - 【设置自定义变量】/【获取自定义变量】节点的“目标实体”输入端：
          若未连线且无常量，代码生成器会自动注入 self.owner_entity 作为默认目标实体，
          因此在结构校验阶段不再视作“缺少数据来源”的错误。
        """
        title = getattr(node, "title", "") or ""
        name = str(port_name or "")
        if title in ("设置自定义变量", "获取自定义变量") and name == "目标实体":
            return True
        return False
    
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
                    # 对支持隐式默认值的端口（例如自定义变量节点的“目标实体”），
                    # 允许在图结构中不显式连接数据来源，由执行代码负责注入。
                    if _allows_implicit_data_input(node, port.name):
                        continue
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
        # 信号定义仓库：用于在 register_handlers 中接受“信号名”或 signal_id，并统一解析为 ID。
        # 使用延迟导入避免在引擎初始化早期引入 `engine.signal` → `engine.validate` → `engine.graph` 的循环依赖。
        self._signal_repo = None
    
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

        # 5. 基于 docstring 中的结构体 ID 约定，为结构体相关节点补充默认结构体绑定。
        self._apply_struct_bindings_from_code(tree, graph_model)
        
        # 同步 docstring/代码中的图变量
        if metadata.get("graph_variables"):
            graph_model.graph_variables = metadata["graph_variables"]
        
        # 6. 提取并关联注释
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
        - 仅处理形如 self.game.register_event_handler(\"<literal>\", self.on_监听信号, owner=...) 的调用；
        - literal 既可以是 signal_id，也可以是信号显示名（signal_name）；
        - 本方法会使用信号定义仓库将 literal 解析为稳定的 signal_id 后写入
          GraphModel.metadata[\"signal_bindings\"]，若解析失败则保留原文；
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

                # 将 register_event_handler 中的事件名称作为“信号标识字面量”，
                # 既接受 signal_id，也允许写信号显示名（signal_name）；最终写入稳定的 ID，
                # 后续 UI / 校验与代码生成统一依赖 GraphModel.metadata["signal_bindings"] 中的 ID。
                resolved_id = self._resolve_signal_id_from_literal(raw_event_name)
                graph_model.set_node_signal_binding(node_id, resolved_id)

    def _resolve_signal_id_from_literal(self, literal: str) -> str:
        """将 register_event_handler 中的事件名字面量解析为稳定的 signal_id。

        解析策略：
        - 若 literal 本身就是一个合法的 signal_id（在全局信号定义中存在），则直接返回该 ID；
        - 否则按显示名（signal_name）尝试解析；
        - 解析失败时返回原始 literal，以便后续信号校验规则给出“信号不存在”等更具体的提示。
        """
        text = str(literal or "").strip()
        if not text:
            return text

        if self._signal_repo is None:
            signal_module = import_module("engine.signal")
            get_repo = getattr(signal_module, "get_default_signal_repository")
            self._signal_repo = get_repo()

        # 1) 直接作为 ID 查询
        payload = self._signal_repo.get_payload(text)
        if isinstance(payload, dict) and payload:
            return text

        # 2) 按显示名称解析 ID
        resolved_by_name = self._signal_repo.resolve_id_by_name(text)
        if resolved_by_name:
            return resolved_by_name

        # 3) 保留原文，交由后续规则处理
        return text

    def _apply_struct_bindings_from_code(
        self,
        tree: ast.Module,
        graph_model: GraphModel,
    ) -> None:
        """从 Graph Code 中推导结构体节点的默认绑定信息。

        约定与边界：
        - 仅在模块 docstring 中出现且仅出现一次形如 ``struct_xxx`` 的结构体 ID 时启用；
        - 仅绑定标记为基础结构体（struct_ype == "basic" 或未显式标注类型）的定义；
        - 仅为尚未在 ``GraphModel.metadata['struct_bindings']`` 中出现绑定记录的节点写入默认绑定；
        - 对于每个结构体节点，默认将 `field_names` 设置为当前图模型中已存在、且在目标结构体定义里
          出现的字段端口名集合（按出现顺序去重），从而让“拼装/拆分/修改结构体”节点在编辑器中只生成
          与当前代码实际使用字段一致的数据端口。
        """
        if not isinstance(tree, ast.Module):
            return

        docstring_text = ast.get_docstring(tree)
        if not docstring_text:
            return

        # 在模块 docstring 中查找唯一的结构体 ID（形式为 struct_xxx）。
        # 注意：这里使用的是正则中的“单词边界” \b，而不是字面量反斜杠。
        pattern = r"\bstruct_[A-Za-z0-9_]+\b"
        struct_id_candidates = dedupe_preserve_order(re.findall(pattern, docstring_text))
        if len(struct_id_candidates) != 1:
            return

        struct_id_text = struct_id_candidates[0]
        if not struct_id_text:
            return

        from engine.resources.definition_schema_view import get_default_definition_schema_view

        schema_view = get_default_definition_schema_view()
        all_struct_definitions = schema_view.get_all_struct_definitions()
        struct_payload = all_struct_definitions.get(struct_id_text)
        if not isinstance(struct_payload, dict):
            return

        struct_type_raw = struct_payload.get("struct_ype")
        struct_type = str(struct_type_raw).strip() if isinstance(struct_type_raw, str) else ""
        if struct_type and struct_type != "basic":
            return

        struct_name_raw = struct_payload.get("name")
        struct_name = (
            str(struct_name_raw).strip()
            if isinstance(struct_name_raw, str) and str(struct_name_raw).strip()
            else struct_id_text
        )

        # 预先收集结构体定义中的字段名集合，后续用于对代码中出现的字段名做合法性过滤。
        defined_field_names: List[str] = []
        value_entries = struct_payload.get("value")
        if isinstance(value_entries, Sequence):
            for entry in value_entries:
                if not isinstance(entry, Mapping):
                    continue
                raw_name = entry.get("key")
                name_text = str(raw_name).strip() if isinstance(raw_name, str) else ""
                if not name_text:
                    continue
                if name_text not in defined_field_names:
                    defined_field_names.append(name_text)
        defined_field_name_set = set(defined_field_names)

        existing_bindings = graph_model.get_struct_bindings()

        # 构造“结构体节点 → 源码行范围”索引，便于将 AST 中的调用与具体节点对应起来。
        span_records: List[Tuple[str, int, int, str]] = []
        for raw_node_id, node in graph_model.nodes.items():
            node_title = getattr(node, "title", "") or ""
            if node_title not in STRUCT_NODE_TITLES:
                continue
            start_line = getattr(node, "source_lineno", 0) or 0
            end_line = getattr(node, "source_end_lineno", 0) or 0
            if not isinstance(start_line, int) or start_line <= 0:
                continue
            if not isinstance(end_line, int) or end_line < start_line:
                end_line = start_line
            span_records.append((node_title, start_line, end_line, str(raw_node_id)))

        def _get_ast_span(ast_node: ast.AST) -> Tuple[int, int]:
            lineno = getattr(ast_node, "lineno", 0) or 0
            end_lineno = getattr(ast_node, "end_lineno", lineno) or lineno
            if not isinstance(lineno, int) or lineno <= 0:
                return 0, 0
            if not isinstance(end_lineno, int) or end_lineno < lineno:
                end_lineno = lineno
            return lineno, end_lineno

        def _match_struct_node_id(node_title: str, lineno: int, end_lineno: int) -> Optional[str]:
            best_id: Optional[str] = None
            best_overlap = 0
            for title, start, end, candidate_id in span_records:
                if title != node_title:
                    continue
                lo = max(start, lineno)
                hi = min(end, end_lineno)
                if lo > hi:
                    continue
                overlap = hi - lo + 1
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_id = candidate_id
            return best_id

        field_names_by_node_id: Dict[str, List[str]] = {}

        # 1) 处理“拼装结构体 / 修改结构体”调用：字段名来源于关键字参数。
        for ast_node in ast.walk(tree):
            if not isinstance(ast_node, ast.Call):
                continue

            func_obj = ast_node.func
            func_name = ""
            if isinstance(func_obj, ast.Name):
                func_name = func_obj.id
            elif isinstance(func_obj, ast.Attribute):
                func_name = func_obj.attr
            if not func_name:
                continue

            if func_name == STRUCT_BUILD_NODE_TITLE:
                lineno, end_lineno = _get_ast_span(ast_node)
                if lineno <= 0:
                    continue
                matched_id = _match_struct_node_id(STRUCT_BUILD_NODE_TITLE, lineno, end_lineno)
                if not matched_id:
                    continue
                static_inputs = set(STRUCT_BUILD_STATIC_INPUTS)
                target_list = field_names_by_node_id.setdefault(matched_id, [])
                for keyword in ast_node.keywords or []:
                    arg_name = keyword.arg
                    if not isinstance(arg_name, str) or not arg_name:
                        continue
                    if arg_name in static_inputs:
                        continue
                    if arg_name not in defined_field_name_set:
                        continue
                    if arg_name not in target_list:
                        target_list.append(arg_name)

            elif func_name == STRUCT_MODIFY_NODE_TITLE:
                lineno, end_lineno = _get_ast_span(ast_node)
                if lineno <= 0:
                    continue
                matched_id = _match_struct_node_id(STRUCT_MODIFY_NODE_TITLE, lineno, end_lineno)
                if not matched_id:
                    continue
                static_inputs = set(STRUCT_MODIFY_STATIC_INPUTS)
                target_list = field_names_by_node_id.setdefault(matched_id, [])
                for keyword in ast_node.keywords or []:
                    arg_name = keyword.arg
                    if not isinstance(arg_name, str) or not arg_name:
                        continue
                    if arg_name in static_inputs:
                        continue
                    if arg_name not in defined_field_name_set:
                        continue
                    if arg_name not in target_list:
                        target_list.append(arg_name)

        # 2) 处理“拆分结构体”：字段名来源于左侧的多目标赋值。
        for ast_node in ast.walk(tree):
            if not isinstance(ast_node, (ast.Assign, ast.AnnAssign)):
                continue

            if isinstance(ast_node, ast.Assign):
                value_node = ast_node.value
            else:
                value_node = ast_node.value

            if not isinstance(value_node, ast.Call):
                continue

            func_obj = value_node.func
            func_name = ""
            if isinstance(func_obj, ast.Name):
                func_name = func_obj.id
            elif isinstance(func_obj, ast.Attribute):
                func_name = func_obj.attr
            if func_name != STRUCT_SPLIT_NODE_TITLE:
                continue

            lineno, end_lineno = _get_ast_span(value_node)
            if lineno <= 0:
                continue
            matched_id = _match_struct_node_id(STRUCT_SPLIT_NODE_TITLE, lineno, end_lineno)
            if not matched_id:
                continue

            target_list = field_names_by_node_id.setdefault(matched_id, [])

            def _collect_names_from_target(target: ast.AST) -> None:
                if isinstance(target, ast.Name):
                    name_text = target.id.strip()
                    if not name_text:
                        return
                    if name_text not in defined_field_name_set:
                        return
                    if name_text not in target_list:
                        target_list.append(name_text)
                elif isinstance(target, ast.Tuple):
                    for element in target.elts:
                        _collect_names_from_target(element)

            if isinstance(ast_node, ast.Assign):
                for target in ast_node.targets:
                    _collect_names_from_target(target)
            else:
                _collect_names_from_target(ast_node.target)

        # 3) 写回绑定：保留已有绑定，未显式配置的节点按“代码中实际使用字段”推导字段列表。
        for node_id, node in graph_model.nodes.items():
            node_title = getattr(node, "title", "") or ""
            if node_title not in STRUCT_NODE_TITLES:
                continue

            existing_binding = existing_bindings.get(str(node_id))
            if isinstance(existing_binding, dict):
                # 避免覆盖 UI 或其它工具已写入的绑定信息。
                continue

            used_field_names = field_names_by_node_id.get(str(node_id)) or []

            binding_payload: Dict[str, Any] = {
                "struct_id": struct_id_text,
                "struct_name": struct_name,
            }
            # 若当前节点在代码中已经通过字段名显式使用了一部分结构体字段，
            # 则将这些字段作为默认的 field_names 写入绑定，避免在编辑器中
            # 再次自动扩展为“全部字段”。
            if used_field_names:
                binding_payload["field_names"] = list(used_field_names)

            graph_model.set_node_struct_binding(node_id, binding_payload)
