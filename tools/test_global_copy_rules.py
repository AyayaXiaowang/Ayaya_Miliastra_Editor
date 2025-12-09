"""
测试 GlobalCopyManager 的三个复制规则：

1. 同一个块里的数据节点不需要复制
2. 复制后旧连线要断开，改为副本连接
3. 同一个块内多个消费者共用一个副本
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.graph.models import GraphModel, NodeModel, EdgeModel, PortModel
from engine.layout.utils.global_copy_manager import GlobalCopyManager
from engine.layout.core.layout_models import LayoutBlock


def create_test_node(node_id: str, has_flow: bool = False) -> NodeModel:
    """创建测试节点"""
    inputs = []
    outputs = []
    
    if has_flow:
        inputs.append(PortModel(name="流程入", is_input=True))
        outputs.append(PortModel(name="流程出", is_input=False))
    
    inputs.append(PortModel(name="输入", is_input=True))
    outputs.append(PortModel(name="输出", is_input=False))
    
    node = NodeModel(
        id=node_id,
        title=node_id,
        category="测试节点",
        inputs=inputs,
        outputs=outputs,
    )
    node._rebuild_port_maps()
    return node


def create_edge(src_node: str, src_port: str, dst_node: str, dst_port: str) -> EdgeModel:
    """创建边"""
    return EdgeModel(
        id=f"edge_{src_node}_{dst_node}",
        src_node=src_node,
        src_port=src_port,
        dst_node=dst_node,
        dst_port=dst_port,
    )


def test_rule_1_same_block_no_copy():
    """
    规则1测试：同一个块里的数据节点不需要复制
    
    场景：
    - 块1包含流程节点 F1, F2
    - 数据节点 A 被 F1 和 F2 消费（都在块1内）
    - 预期：A 不应该被复制
    """
    print("\n" + "=" * 60)
    print("规则1测试：同一个块里的数据节点不需要复制")
    print("=" * 60)
    
    # 创建模型
    model = GraphModel(graph_name="test_rule_1")
    
    # 创建节点
    flow_f1 = create_test_node("F1", has_flow=True)
    flow_f2 = create_test_node("F2", has_flow=True)
    data_a = create_test_node("A", has_flow=False)
    
    model.nodes["F1"] = flow_f1
    model.nodes["F2"] = flow_f2
    model.nodes["A"] = data_a
    
    # 创建边：A -> F1, A -> F2（同块内）
    edge1 = create_edge("A", "输出", "F1", "输入")
    edge2 = create_edge("A", "输出", "F2", "输入")
    flow_edge = create_edge("F1", "流程出", "F2", "流程入")
    
    model.edges[edge1.id] = edge1
    model.edges[edge2.id] = edge2
    model.edges[flow_edge.id] = flow_edge
    
    # 创建块：F1 和 F2 在同一个块
    block1 = LayoutBlock()
    block1.flow_nodes = ["F1", "F2"]
    block1.order_index = 0
    
    # 执行复制
    manager = GlobalCopyManager(model, [block1])
    manager.analyze_dependencies()
    manager.execute_copy_plan()
    
    # 验证
    copy_count = sum(1 for node in model.nodes.values() if node.is_data_node_copy)
    
    print(f"  场景：数据节点A被同一块内的F1、F2消费")
    print(f"  结果：副本数量 = {copy_count}")
    print(f"  预期：副本数量 = 0")
    
    if copy_count == 0:
        print("  ✓ 通过：同一块内不复制")
        return True
    else:
        print("  ✗ 失败：同一块内不应该复制")
        return False


def test_rule_2_old_edge_removed():
    """
    规则2测试：复制后旧连线要断开，改为副本连接
    
    场景：
    - 块1包含流程节点 F1
    - 块2包含流程节点 F2
    - 数据节点 A 在块1，被 F1 和 F2 消费
    - 预期：
      - A -> F2 的边被删除
      - A2（副本）-> F2 的边被创建
      - A -> F1 的边保留
    """
    print("\n" + "=" * 60)
    print("规则2测试：复制后旧连线要断开，改为副本连接")
    print("=" * 60)
    
    # 创建模型
    model = GraphModel(graph_name="test_rule_2")
    
    # 创建节点
    flow_f1 = create_test_node("F1", has_flow=True)
    flow_f2 = create_test_node("F2", has_flow=True)
    data_a = create_test_node("A", has_flow=False)
    
    model.nodes["F1"] = flow_f1
    model.nodes["F2"] = flow_f2
    model.nodes["A"] = data_a
    
    # 创建边
    edge_a_f1 = create_edge("A", "输出", "F1", "输入")
    edge_a_f2 = create_edge("A", "输出", "F2", "输入")
    flow_edge = create_edge("F1", "流程出", "F2", "流程入")
    
    model.edges[edge_a_f1.id] = edge_a_f1
    model.edges[edge_a_f2.id] = edge_a_f2
    model.edges[flow_edge.id] = flow_edge
    
    original_edge_a_f2_id = edge_a_f2.id
    
    # 创建块：F1 在块1，F2 在块2
    block1 = LayoutBlock()
    block1.flow_nodes = ["F1"]
    block1.order_index = 0
    
    block2 = LayoutBlock()
    block2.flow_nodes = ["F2"]
    block2.order_index = 1
    
    # 执行复制
    manager = GlobalCopyManager(model, [block1, block2])
    manager.analyze_dependencies()
    manager.execute_copy_plan()
    
    # 验证
    print(f"  场景：块1的A连接块2的F2")
    
    # 检查旧边是否被删除
    old_edge_exists = original_edge_a_f2_id in model.edges
    print(f"  原边 A->F2 存在: {old_edge_exists}")
    print(f"  预期：原边不存在 (False)")
    
    # 检查新边是否创建（副本 -> F2）
    copy_to_f2_edges = [
        e for e in model.edges.values()
        if e.dst_node == "F2" and e.dst_port == "输入" and "copy" in e.src_node
    ]
    new_edge_exists = len(copy_to_f2_edges) > 0
    print(f"  新边 A副本->F2 存在: {new_edge_exists}")
    print(f"  预期：新边存在 (True)")
    
    # 检查原边 A -> F1 是否保留
    a_to_f1_edges = [
        e for e in model.edges.values()
        if e.src_node == "A" and e.dst_node == "F1"
    ]
    original_edge_preserved = len(a_to_f1_edges) > 0
    print(f"  原边 A->F1 保留: {original_edge_preserved}")
    print(f"  预期：保留 (True)")
    
    success = (not old_edge_exists) and new_edge_exists and original_edge_preserved
    if success:
        print("  ✓ 通过：旧边断开，新边创建，owner块边保留")
        return True
    else:
        print("  ✗ 失败")
        return False


def test_rule_3_one_copy_per_block():
    """
    规则3测试：同一个块内多个消费者共用一个副本
    
    场景：
    - 块1包含流程节点 F1
    - 块2包含流程节点 F2, F3, F4
    - 数据节点 A 被 F1, F2, F3, F4 消费
    - 预期：
      - A 只复制一次（A2）
      - A2 连接 F2, F3, F4
    """
    print("\n" + "=" * 60)
    print("规则3测试：同一个块内多个消费者共用一个副本")
    print("=" * 60)
    
    # 创建模型
    model = GraphModel(graph_name="test_rule_3")
    
    # 创建节点
    flow_f1 = create_test_node("F1", has_flow=True)
    flow_f2 = create_test_node("F2", has_flow=True)
    flow_f3 = create_test_node("F3", has_flow=True)
    flow_f4 = create_test_node("F4", has_flow=True)
    data_a = create_test_node("A", has_flow=False)
    
    model.nodes["F1"] = flow_f1
    model.nodes["F2"] = flow_f2
    model.nodes["F3"] = flow_f3
    model.nodes["F4"] = flow_f4
    model.nodes["A"] = data_a
    
    # 创建边：A 连接所有流程节点
    edge_a_f1 = create_edge("A", "输出", "F1", "输入")
    edge_a_f2 = create_edge("A", "输出", "F2", "输入")
    edge_a_f3 = create_edge("A", "输出", "F3", "输入")
    edge_a_f4 = create_edge("A", "输出", "F4", "输入")
    
    # 流程边
    flow_edge_1 = create_edge("F1", "流程出", "F2", "流程入")
    flow_edge_2 = create_edge("F2", "流程出", "F3", "流程入")
    flow_edge_3 = create_edge("F3", "流程出", "F4", "流程入")
    
    model.edges[edge_a_f1.id] = edge_a_f1
    model.edges[edge_a_f2.id] = edge_a_f2
    model.edges[edge_a_f3.id] = edge_a_f3
    model.edges[edge_a_f4.id] = edge_a_f4
    model.edges[flow_edge_1.id] = flow_edge_1
    model.edges[flow_edge_2.id] = flow_edge_2
    model.edges[flow_edge_3.id] = flow_edge_3
    
    # 创建块：F1 在块1，F2/F3/F4 在块2
    block1 = LayoutBlock()
    block1.flow_nodes = ["F1"]
    block1.order_index = 0
    
    block2 = LayoutBlock()
    block2.flow_nodes = ["F2", "F3", "F4"]
    block2.order_index = 1
    
    # 执行复制
    manager = GlobalCopyManager(model, [block1, block2])
    manager.analyze_dependencies()
    manager.execute_copy_plan()
    
    # 验证
    print(f"  场景：块1的A被块2的F2、F3、F4消费")
    
    # 检查副本数量
    copies = [node for node in model.nodes.values() if node.is_data_node_copy and node.original_node_id == "A"]
    copy_count = len(copies)
    print(f"  副本数量: {copy_count}")
    print(f"  预期：1 个")
    
    if copy_count != 1:
        print("  ✗ 失败：应该只有一个副本")
        return False
    
    copy_id = copies[0].id
    print(f"  副本ID: {copy_id}")
    
    # 检查副本连接了几个消费者
    copy_out_edges = [
        e for e in model.edges.values()
        if e.src_node == copy_id
    ]
    connected_consumers = {e.dst_node for e in copy_out_edges}
    print(f"  副本连接的消费者: {connected_consumers}")
    print(f"  预期：{{'F2', 'F3', 'F4'}}")
    
    expected_consumers = {"F2", "F3", "F4"}
    if connected_consumers == expected_consumers:
        print("  ✓ 通过：一个副本连接所有块内消费者")
        return True
    else:
        print(f"  ✗ 失败：连接的消费者不匹配")
        return False


def test_rule_4_disable_copy_node_in_one_block():
    """
    规则4测试：禁用复制时，数据节点只被分配到一个块
    
    场景：
    - 块1包含流程节点 F1
    - 块2包含流程节点 F2
    - 数据节点 A 被 F1 和 F2 消费
    - 禁用复制时，A 只应该被分配到块1（第一个使用它的块）
    """
    print("\n" + "=" * 60)
    print("规则4测试：禁用复制时节点只属于一个块")
    print("=" * 60)
    
    # 创建模型
    model = GraphModel(graph_name="test_rule_4")
    
    # 创建节点
    flow_f1 = create_test_node("F1", has_flow=True)
    flow_f2 = create_test_node("F2", has_flow=True)
    data_a = create_test_node("A", has_flow=False)
    
    model.nodes["F1"] = flow_f1
    model.nodes["F2"] = flow_f2
    model.nodes["A"] = data_a
    
    # 创建边
    edge_a_f1 = create_edge("A", "输出", "F1", "输入")
    edge_a_f2 = create_edge("A", "输出", "F2", "输入")
    flow_edge = create_edge("F1", "流程出", "F2", "流程入")
    
    model.edges[edge_a_f1.id] = edge_a_f1
    model.edges[edge_a_f2.id] = edge_a_f2
    model.edges[flow_edge.id] = flow_edge
    
    # 创建块
    block1 = LayoutBlock()
    block1.flow_nodes = ["F1"]
    block1.order_index = 0
    
    block2 = LayoutBlock()
    block2.flow_nodes = ["F2"]
    block2.order_index = 1
    
    # 分析依赖但不执行复制（模拟禁用复制）
    manager = GlobalCopyManager(model, [block1, block2])
    manager.analyze_dependencies()
    # 不调用 execute_copy_plan()
    
    # 检查数据节点归属
    block1_nodes = manager.get_block_data_nodes("block_0")
    block2_nodes = manager.get_block_data_nodes("block_1")
    
    print(f"  场景：数据节点A被块1的F1和块2的F2消费，禁用复制")
    print(f"  块1的数据节点: {block1_nodes}")
    print(f"  块2的数据节点: {block2_nodes}")
    
    # A 应该只在块1（第一个使用它的块）
    a_in_block1 = "A" in block1_nodes
    a_in_block2 = "A" in block2_nodes
    no_copies = not any("copy" in nid for nid in model.nodes.keys())
    
    print(f"  A在块1: {a_in_block1}")
    print(f"  A在块2: {a_in_block2}")
    print(f"  无副本创建: {no_copies}")
    print(f"  预期：A只在块1，不在块2，无副本")
    
    success = a_in_block1 and (not a_in_block2) and no_copies
    if success:
        print("  ✓ 通过：禁用复制时节点只属于第一个块")
        return True
    else:
        print("  ✗ 失败")
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("GlobalCopyManager 复制规则测试")
    print("=" * 60)
    
    results = []
    
    results.append(("规则1: 同一块内不复制", test_rule_1_same_block_no_copy()))
    results.append(("规则2: 旧边断开新边创建", test_rule_2_old_edge_removed()))
    results.append(("规则3: 同块多消费者共用副本", test_rule_3_one_copy_per_block()))
    results.append(("规则4: 禁用复制时节点只属于一个块", test_rule_4_disable_copy_node_in_one_block()))
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("所有测试通过！")
        return 0
    else:
        print("存在失败的测试！")
        return 1


if __name__ == "__main__":
    sys.exit(main())

