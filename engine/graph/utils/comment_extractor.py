"""注释提取与关联工具

从Python代码中提取注释并关联到节点。
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import defaultdict, deque
from typing import Deque, Dict, List, Optional

from engine.graph.models import GraphModel, NodeModel


def extract_comments(code: str) -> Dict[int, str]:
    """提取代码中的所有注释
    
    使用tokenize模块扫描所有注释token，返回行号到注释文本的映射。
    
    Args:
        code: Python代码字符串
        
    Returns:
        {行号: 注释文本} 的映射（注释文本已去除#前缀和前后空格）
    """
    comments = {}
    
    # 使用tokenize模块提取注释
    tokens = tokenize.generate_tokens(io.StringIO(code).readline)
    
    for token in tokens:
        if token.type == tokenize.COMMENT:
            line_number = token.start[0]
            comment_text = token.string.lstrip('#').strip()
            comments[line_number] = comment_text
    
    return comments


def associate_comments_to_nodes(
    code: str,
    graph_model: GraphModel,
    comments: Optional[Dict[int, str]] = None
) -> None:
    """将注释关联到节点
    
    关联规则：
    1. 块注释：节点前连续多行注释作为 custom_comment
    2. 行尾注释：节点所在行的注释作为 inline_comment
    3. composite_id：形如 "# composite_id: xxx" 的注释提取到节点的 composite_id 字段
    4. 事件流注释：形如 "# ===事件流N===" 的注释及其描述行
    
    注意：直接修改 graph_model 和其中的节点，无返回值。
    
    Args:
        code: Python代码字符串
        graph_model: 节点图模型（会被直接修改）
        comments: 可选的预提取注释映射（如果为None则自动提取）
    """
    if comments is None:
        comments = extract_comments(code)
    
    tree = ast.parse(code)
    
    # 构建“源码行 -> 节点”映射，优先按精确行号匹配
    node_list = list(graph_model.nodes.values())
    nodes_by_line: Dict[int, Deque[NodeModel]] = defaultdict(deque)
    fallback_queue: Deque[NodeModel] = deque()
    for candidate in node_list:
        source_ln = getattr(candidate, 'source_lineno', 0)
        if isinstance(source_ln, int) and source_ln > 0:
            nodes_by_line[source_ln].append(candidate)
        else:
            fallback_queue.append(candidate)

    def acquire_node(line_number: int) -> Optional[NodeModel]:
        bucket = nodes_by_line.get(line_number)
        if bucket:
            try:
                return bucket.popleft()
            except IndexError:
                pass
        if fallback_queue:
            return fallback_queue.popleft()
        return None
    
    # 事件流注释提取的正则
    event_flow_pattern = re.compile(r'^=+\s*事件流\s+(\d+)\s*=+')
    
    # 遍历AST中的所有语句
    for node in ast.walk(tree):
        # 跳过非赋值/表达式语句
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr)):
            continue
        
        lineno = node.lineno
        
        # 处理赋值语句（节点创建）
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                current_node = acquire_node(lineno)
                if current_node:
                    _associate_node_comments(current_node, node, lineno, comments)
        
        # 处理不带赋值的表达式语句（如：打印字符串(...)）
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            current_node = acquire_node(lineno)
            if current_node:
                _associate_node_comments(current_node, node, lineno, comments)
    
    # 提取事件流注释
    event_flow_index = 0
    for lineno, comment_text in comments.items():
        match = event_flow_pattern.match(comment_text)
        if match:
            # 提取事件流序号
            flow_number = int(match.group(1))
            # 查找下一行的注释（事件流描述）
            if lineno + 1 in comments:
                flow_comment = comments[lineno + 1]
                _ensure_event_comment_capacity(graph_model, flow_number)
                graph_model.event_flow_comments[flow_number - 1] = flow_comment


def _ensure_event_comment_capacity(graph_model: GraphModel, flow_number: int) -> None:
    """确保 event_flow_comments 有足够容量。"""
    if not hasattr(graph_model, "event_flow_comments"):
        graph_model.event_flow_comments = []
    while len(graph_model.event_flow_comments) < flow_number:
        graph_model.event_flow_comments.append("")


def _associate_node_comments(
    node: NodeModel,
    ast_node: ast.AST,
    lineno: int,
    comments: Dict[int, str]
) -> None:
    """将注释关联到单个节点（内部辅助函数）
    
    Args:
        node: 节点模型
        ast_node: AST节点
        lineno: 节点所在行号
        comments: 注释映射
    """
    # 记录源代码行范围（用于后续验证错误定位）
    start_ln = getattr(ast_node, 'lineno', None)
    end_ln = getattr(ast_node, 'end_lineno', start_ln)
    if isinstance(start_ln, int):
        existing_ln = getattr(node, 'source_lineno', 0)
        # 若节点尚未有有效源码行号，则回填；否则保留创建时写入的更精确行号
        if not isinstance(existing_ln, int) or existing_ln <= 0:
            node.source_lineno = start_ln
            node.source_end_lineno = end_ln if isinstance(end_ln, int) else start_ln
    
    # 查找该行之前的注释（多行注释块）
    comment_lines = []
    composite_id_found = None
    
    for line in range(lineno - 1, 0, -1):
        if line in comments:
            comment_text = comments[line]
            
            # 检查是否是 composite_id 注释
            if comment_text.startswith('composite_id:'):
                composite_id_found = comment_text.split(':', 1)[1].strip()
                continue  # 不加入 custom_comment
            
            # 跳过分隔线式的注释
            if comment_text and not comment_text.startswith('='):
                comment_lines.insert(0, comment_text)
        else:
            break  # 遇到非注释行，停止
    
    # 设置 composite_id（如果找到）
    if composite_id_found and node.category == "复合节点":
        node.composite_id = composite_id_found
    
    if comment_lines:
        node.custom_comment = '\n'.join(comment_lines)
    
    # 查找该行的行尾注释
    if lineno in comments:
        node.inline_comment = comments[lineno]

