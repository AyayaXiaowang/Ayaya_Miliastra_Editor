"""生成节点实现清单脚本（基于实现侧@node_spec）"""

from pathlib import Path
from collections import defaultdict
from engine.nodes import get_node_registry


def scan_nodes():
    """从实现库加载 NodeDef，提取节点信息"""
    workspace = Path(__file__).parent.parent
    registry = get_node_registry(workspace)
    library = registry.get_library()

    nodes_by_category = defaultdict(list)
    total_count = 0

    for _, node_def in library.items():
        # 计算是否有流程入/出
        has_flow_in = ("流程入" in node_def.inputs) or any(("流程" in t) for t in node_def.input_types.values())
        has_flow_out = ("流程出" in node_def.outputs) or any(("流程" in t) for t in node_def.output_types.values())

        node_type = "数据节点"
        if has_flow_in and has_flow_out:
            node_type = "流程节点"
        elif has_flow_in:
            node_type = "执行节点"

        # 仅统计数据入参（排除流程端口）
        data_params = [p for p in node_def.inputs if node_def.input_types.get(p, "") != "流程"]
        params_text = ", ".join(data_params)

        priority = classify_priority(node_def.name, node_type, params_text)

        scope_text = ",".join(node_def.scopes) if getattr(node_def, "scopes", None) else ""
        description = (node_def.description or "")
        if len(description) > 50:
            description = description[:50] + "..."

        node_info = {
            "name": node_def.name,
            "params": params_text,
            "type": node_type,
            "priority": priority,
            "category": node_def.category,
            "description": description,
            "scope": scope_text,
        }

        nodes_by_category[node_def.category].append(node_info)
        total_count += 1

    return nodes_by_category, total_count

def classify_priority(node_name, node_type, params):
    """根据节点名称和类型判断优先级"""
    
    # P0 - 核心节点（必须）
    p0_keywords = [
        "打印", "双分支", "多分支", "有限循环", "列表迭代循环",
        "设置自定义变量", "设置节点图变量", "获取局部变量", "设置局部变量",
        "获取随机", "加", "减", "乘", "除", "大于", "小于", "等于",
        "逻辑与", "逻辑或", "逻辑非", "布尔值"
    ]
    
    for keyword in p0_keywords:
        if keyword in node_name:
            return "P0"
    
    # P1 - 常用节点
    p1_keywords = [
        "列表", "创建实体", "销毁实体", "移除实体", "传送",
        "定时器", "计时器", "获取", "查询", "修改", "设置",
        "三维向量", "位置", "旋转", "实体", "玩家"
    ]
    
    for keyword in p1_keywords:
        if keyword in node_name:
            return "P1"
    
    # 其余为P2
    return "P2"

def generate_markdown(nodes_by_category, total_count):
    """生成Markdown清单"""
    lines = []
    lines.append("# 节点实现清单\n")
    lines.append(f"**总计**: {total_count}个节点\n")
    lines.append(f"**生成时间**: {Path(__file__).parent.parent.name}\n")
    lines.append("\n## 优先级说明\n")
    lines.append("- **P0**: 核心节点（流程控制、变量、基础运算） - 必须优先实现\n")
    lines.append("- **P1**: 常用节点（列表、实体、定时器等） - 覆盖80%场景\n")
    lines.append("- **P2**: 高级节点（完整覆盖）\n")
    
    # 按优先级统计
    priority_stats = {"P0": 0, "P1": 0, "P2": 0}
    for category_nodes in nodes_by_category.values():
        for node in category_nodes:
            priority_stats[node["priority"]] += 1
    
    lines.append(f"\n**统计**: P0={priority_stats['P0']}个, P1={priority_stats['P1']}个, P2={priority_stats['P2']}个\n")
    
    # 按文件分类输出
    for category_name in sorted(nodes_by_category.keys()):
        nodes = nodes_by_category[category_name]
        lines.append(f"\n## {category_name} ({len(nodes)}个节点)\n")
        
        # 按优先级排序
        for priority in ["P0", "P1", "P2"]:
            priority_nodes = [n for n in nodes if n["priority"] == priority]
            if not priority_nodes:
                continue
            
            lines.append(f"\n### {priority}优先级 ({len(priority_nodes)}个)\n")
            for node in priority_nodes:
                checkbox = "- [ ]"
                params_str = f"({node['params']})" if node['params'] else "()"
                scope_hint = f" | scopes={node['scope']}" if node['scope'] else ""
                lines.append(
                    f"{checkbox} **{node['name']}**{params_str} | {node['type']} | {node['category']}{scope_hint}\n"
                )
                if node['description']:
                    lines.append(f"  - {node['description']}\n")
    
    return "".join(lines)

if __name__ == "__main__":
    print("正在扫描节点定义...")
    nodes_by_category, total_count = scan_nodes()
    
    print(f"发现 {total_count} 个节点")
    print(f"分布在 {len(nodes_by_category)} 个文件中")
    
    # 生成Markdown
    markdown_content = generate_markdown(nodes_by_category, total_count)
    
    # 保存到文件
    output_file = Path(__file__).parent.parent / "node_implementation_checklist.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(markdown_content)
    
    print(f"\n清单已生成: {output_file}")
    print("\n优先级统计:")
    priority_stats = {"P0": 0, "P1": 0, "P2": 0}
    for category_nodes in nodes_by_category.values():
        for node in category_nodes:
            priority_stats[node["priority"]] += 1
    
    for priority, count in sorted(priority_stats.items()):
        print(f"  {priority}: {count}个节点")

