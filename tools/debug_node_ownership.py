"""
调试工具：检查指定节点图的数据节点归属情况
"""

from pathlib import Path

if __package__:
    from ._bootstrap import ensure_workspace_root_on_sys_path
else:
    from _bootstrap import ensure_workspace_root_on_sys_path

ensure_workspace_root_on_sys_path()

from engine.graph.graph_code_parser import GraphCodeParser
from engine.layout.utils.global_copy_manager import GlobalCopyManager
from engine.layout.internal.layout_context import LayoutContext
from engine.layout.flow.event_flow_analyzer import find_event_roots
from engine.layout.blocks.block_identification_coordinator import BlockIdentificationCoordinator
from engine.layout.internal.layout_models import LayoutBlock
from engine.layout.internal.constants import (
    NODE_WIDTH_DEFAULT,
    NODE_HEIGHT_DEFAULT,
    BLOCK_PADDING_DEFAULT,
    BLOCK_COLORS_DEFAULT,
)


def analyze_node_ownership(file_path: str):
    """分析指定节点图的数据节点归属"""
    print(f"\n分析文件: {file_path}")
    print("=" * 80)
    
    # 解析节点图
    workspace_path = Path(__file__).parent.parent
    parser = GraphCodeParser(workspace_path)
    model, _ = parser.parse_file(Path(file_path))
    
    print(f"节点总数: {len(model.nodes)}")
    print(f"边总数: {len(model.edges)}")
    
    # 创建布局上下文
    layout_context = LayoutContext(model)
    
    # 找到事件节点
    event_nodes = find_event_roots(model, include_virtual_pin_roots=True, layout_context=layout_context)
    print(f"事件节点数: {len(event_nodes)}")
    
    if not event_nodes:
        print("无事件节点，跳过分析")
        return
    
    # 识别块
    layout_blocks = []
    global_visited = set()
    
    coordinator = BlockIdentificationCoordinator(
        model,
        layout_context,
        layout_blocks,
        BLOCK_COLORS_DEFAULT,
        NODE_WIDTH_DEFAULT,
        NODE_HEIGHT_DEFAULT,
        BLOCK_PADDING_DEFAULT,
    )
    
    for event_node in sorted(event_nodes, key=lambda n: n.id):
        coordinator.identify_blocks_flow_only(event_node.id, global_visited, event_node.id, event_node.title)
    
    print(f"识别到的块数: {len(layout_blocks)}")
    
    # 创建 GlobalCopyManager 分析依赖
    manager = GlobalCopyManager(model, layout_blocks, layout_context)
    manager.analyze_dependencies()
    
    # 检查数据节点归属
    print("\n" + "-" * 40)
    print("数据节点归属分析（不执行复制）:")
    print("-" * 40)
    
    # 检查每个数据节点被哪些块使用
    node_to_blocks = {}
    for block_id, dependency in manager.block_dependencies.items():
        for data_id in dependency.full_data_closure:
            if data_id not in node_to_blocks:
                node_to_blocks[data_id] = []
            node_to_blocks[data_id].append(block_id)
    
    # 找出被多个块使用的节点
    shared_nodes = {nid: blocks for nid, blocks in node_to_blocks.items() if len(blocks) > 1}
    
    print(f"\n被多个块的闭包包含的数据节点数: {len(shared_nodes)}")
    if shared_nodes:
        for node_id, blocks in sorted(shared_nodes.items())[:10]:
            node = model.nodes.get(node_id)
            title = node.title if node else "?"
            print(f"  - {node_id[:40]}... ({title}): {blocks}")
        if len(shared_nodes) > 10:
            print(f"  ... 还有 {len(shared_nodes) - 10} 个")
    
    # 检查每个块拥有的节点
    print("\n各块拥有的数据节点:")
    all_owned = set()
    for block in layout_blocks:
        block_id = f"block_{block.order_index}"
        owned = manager.get_block_data_nodes(block_id)
        print(f"  {block_id}: {len(owned)} 个数据节点")
        
        # 检查重复
        duplicates = owned & all_owned
        if duplicates:
            print(f"    ⚠️ 重复归属: {len(duplicates)} 个")
            for dup_id in list(duplicates)[:5]:
                node = model.nodes.get(dup_id)
                title = node.title if node else "?"
                print(f"       - {dup_id[:40]}... ({title})")
        
        all_owned.update(owned)
    
    print(f"\n总共被分配的数据节点数: {len(all_owned)}")
    
    # 计算每个节点被分配到几个块
    node_assignment_count = {}
    for block in layout_blocks:
        block_id = f"block_{block.order_index}"
        owned = manager.get_block_data_nodes(block_id)
        for node_id in owned:
            node_assignment_count[node_id] = node_assignment_count.get(node_id, 0) + 1
    
    multi_assigned = {nid: count for nid, count in node_assignment_count.items() if count > 1}
    if multi_assigned:
        print(f"\n⚠️ 被分配到多个块的节点: {len(multi_assigned)} 个")
        for node_id, count in sorted(multi_assigned.items())[:10]:
            node = model.nodes.get(node_id)
            title = node.title if node else "?"
            print(f"  - {node_id[:40]}... ({title}): 被分配到 {count} 个块")
    else:
        print("\n✓ 没有节点被分配到多个块")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 默认分析用户提到的文件
        file_path = "assets/资源库/节点图/server/锻刀/打造/锻刀英雄_武器展示与选择_变量变化.py"
    else:
        file_path = sys.argv[1]
    
    analyze_node_ownership(file_path)

