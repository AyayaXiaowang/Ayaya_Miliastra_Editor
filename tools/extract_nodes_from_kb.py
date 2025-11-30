#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从知识库 Markdown 文件提取节点定义并生成节点定义文件"""
import re
import sys
import io
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import argparse

# 设置输出编码为UTF-8，避免Windows控制台编码问题
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class NodePortInfo:
    """端口信息"""
    name: str
    port_type: str  # 数据类型
    is_input: bool
    description: str = ""


@dataclass
class NodeInfo:
    """节点信息"""
    name: str
    category: str
    description: str
    is_client: bool
    input_ports: List[NodePortInfo] = field(default_factory=list)
    output_ports: List[NodePortInfo] = field(default_factory=list)
    mount_restrictions: List[str] = field(default_factory=list)
    doc_reference: str = ""


def extract_nodes_from_md(md_file: Path, is_client: bool) -> List[NodeInfo]:
    """从 Markdown 文件提取节点信息
    
    Args:
        md_file: Markdown 文件路径
        is_client: 是否为客户端节点
        
    Returns:
        节点信息列表
    """
    content = md_file.read_text(encoding="utf-8")
    lines = content.splitlines()
    
    nodes = []
    i = 0
    
    # 提取文件级别的分类（如 "事件节点", "执行节点"）
    file_stem = md_file.stem
    category_map = {
        "事件节点": "事件节点",
        "执行节点": "执行节点",
        "查询节点": "查询节点",
        "运算节点": "运算节点",
        "流程控制节点": "流程控制节点",
        "其他节点": "其他节点",
    }
    file_category = category_map.get(file_stem, "执行节点")
    
    while i < len(lines):
        line = lines[i].strip()
        
        # 查找节点标题（格式：数字.节点名 或 直接节点名）
        # 例如：1.实体创建时 或 实体创建时
        node_title_match = re.match(r"^(?:\d+\.)?(.+)$", line)
        if node_title_match and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            
            # 检查下一行是否是 "节点功能"
            if next_line == "节点功能":
                node_name = node_title_match.group(1).strip()
                
                # 提取节点描述（节点功能后面的内容）
                description_lines = []
                j = i + 2
                while j < len(lines):
                    desc_line = lines[j].strip()
                    if desc_line == "节点参数":
                        break
                    if desc_line and not desc_line.startswith("|"):
                        description_lines.append(desc_line)
                    j += 1
                description = " ".join(description_lines)
                
                # 提取节点参数表格
                input_ports = []
                output_ports = []
                
                # 查找表格（节点参数后面）
                k = j + 1  # 跳过"节点参数"行
                
                # 跳过空行找到表格
                while k < len(lines) and not lines[k].strip():
                    k += 1
                
                # 检查是否找到表格
                if k < len(lines) and lines[k].strip().startswith("|"):
                    # 跳过表头行
                    k += 1
                    # 跳过分隔行（| --- | --- | --- | --- |）
                    if k < len(lines) and "---" in lines[k]:
                        k += 1
                    
                    # 解析表格内容
                    while k < len(lines):
                        table_line = lines[k].strip()
                        if not table_line.startswith("|"):
                            break
                        
                        # 解析表格行：| 参数类型 | 参数名 | 类型 | 说明 |
                        parts = [p.strip() for p in table_line.split("|")]
                        if len(parts) >= 5:  # 至少有5个部分（包括首尾空字符串）
                            param_type = parts[1]  # 入参/出参
                            param_name = parts[2]
                            data_type = parts[3]
                            param_desc = parts[4] if len(parts) > 4 else ""
                            
                            if param_name and data_type:
                                port_info = NodePortInfo(
                                    name=param_name,
                                    port_type=data_type,
                                    is_input=param_type == "入参",
                                    description=param_desc
                                )
                                
                                if param_type == "入参":
                                    input_ports.append(port_info)
                                elif param_type == "出参":
                                    output_ports.append(port_info)
                        
                        k += 1
                
                # 创建节点信息
                node = NodeInfo(
                    name=node_name,
                    category=file_category,
                    description=description,
                    is_client=is_client,
                    input_ports=input_ports,
                    output_ports=output_ports,
                    doc_reference=f"{'客户端节点' if is_client else '服务器节点'}/{file_category}/{file_stem}.md"
                )
                
                nodes.append(node)
                
                # 跳到表格结束位置
                i = k
                continue
        
        i += 1
    
    return nodes


def generate_node_definition_code(nodes: List[NodeInfo]) -> str:
    """生成节点定义代码
    
    Args:
        nodes: 节点信息列表
        
    Returns:
        生成的Python代码
    """
    lines = []
    lines.append("# -*- coding: utf-8 -*-")
    lines.append("# 自动生成的节点定义文件")
    lines.append("")
    
    for node in nodes:
        # 生成函数签名（排除流程端口）
        params = [port.name for port in node.input_ports]
        func_line = f"function {node.name}({', '.join(params)})"
        lines.append(func_line)
        
        # 生成作用域注释（新格式）
        scope = "客户端" if node.is_client else "服务器"
        lines.append(f"# 作用域: {scope}")
        
        if node.description:
            lines.append(f"# 功能描述: {node.description}")
        
        if node.doc_reference:
            lines.append(f"# 文档引用: {node.doc_reference}")
        
        # 生成输入类型（如果有）
        if node.input_ports:
            input_type_pairs = [f"{port.name}={port.port_type}" for port in node.input_ports]
            lines.append(f"# 输入类型: {', '.join(input_type_pairs)}")
        
        # 生成输出类型（如果有）
        if node.output_ports:
            output_type_pairs = [f"{port.name}={port.port_type}" for port in node.output_ports]
            lines.append(f"# 输出类型: {', '.join(output_type_pairs)}")
        
        # 判断流程入点和出点
        # 根据节点类型判断
        if node.category == "事件节点":
            lines.append("# 流程入点: 无")
            lines.append("# 流程出点: 有")
        elif node.category in ["执行节点", "流程控制节点"]:
            lines.append("# 流程入点: 有")
            lines.append("# 流程出点: 有")
        else:  # 查询节点、运算节点
            lines.append("# 流程入点: 无")
            lines.append("# 流程出点: 无")
        
        # 生成返回值
        returns = [port.name for port in node.output_ports]
        if returns:
            lines.append(f"return {', '.join(returns)}")
        else:
            lines.append("return")
        
        lines.append("")  # 空行分隔
    
    return "\n".join(lines)


def process_kb_directory(kb_dir: Path, output_dir: Path):
    """处理知识库目录，生成所有节点定义文件
    
    Args:
        kb_dir: 知识库根目录
        output_dir: 输出目录
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 处理服务器节点
    server_node_dir = kb_dir / "服务器节点"
    if server_node_dir.exists():
        print(f"\n处理服务器节点...")
        
        for category_dir in server_node_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            print(f"  处理分类: {category_dir.name}")
            
            for md_file in category_dir.glob("*.md"):
                print(f"    解析文件: {md_file.name}")
                nodes = extract_nodes_from_md(md_file, is_client=False)
                print(f"      提取了 {len(nodes)} 个节点")
                
                if nodes:
                    # 生成文件名
                    output_file = output_dir / f"server_{md_file.stem}.py"
                    code = generate_node_definition_code(nodes)
                    output_file.write_text(code, encoding="utf-8")
                    print(f"      生成文件: {output_file.name}")
    
    # 处理客户端节点
    client_node_dir = kb_dir / "客户端节点"
    if client_node_dir.exists():
        print(f"\n处理客户端节点...")
        
        for category_dir in client_node_dir.iterdir():
            if not category_dir.is_dir():
                continue
            
            print(f"  处理分类: {category_dir.name}")
            
            for md_file in category_dir.glob("*.md"):
                print(f"    解析文件: {md_file.name}")
                nodes = extract_nodes_from_md(md_file, is_client=True)
                print(f"      提取了 {len(nodes)} 个节点")
                
                if nodes:
                    # 生成文件名
                    output_file = output_dir / f"client_{md_file.stem}.py"
                    code = generate_node_definition_code(nodes)
                    output_file.write_text(code, encoding="utf-8")
                    print(f"      生成文件: {output_file.name}")


def main():
    parser = argparse.ArgumentParser(description="从知识库提取节点定义")
    parser.add_argument("--kb-dir", required=True, help="知识库目录路径")
    parser.add_argument("--output-dir", required=True, help="输出目录路径")
    args = parser.parse_args()
    
    kb_dir = Path(args.kb_dir)
    output_dir = Path(args.output_dir)
    
    if not kb_dir.exists():
        print(f"错误：知识库目录不存在: {kb_dir}")
        return 1
    
    print("=" * 60)
    print("从知识库提取节点定义")
    print("=" * 60)
    print(f"知识库目录: {kb_dir}")
    print(f"输出目录: {output_dir}")
    
    process_kb_directory(kb_dir, output_dir)
    
    print("\n" + "=" * 60)
    print("[SUCCESS] 节点定义生成完成！")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

