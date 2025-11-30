"""复合节点虚拟引脚管理器 - 负责虚拟引脚的映射、验证和管理"""

from __future__ import annotations
from typing import Dict, List, Optional, Set, Tuple

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig, MappedPort
from engine.utils.logging.logger import log_info, log_error


class CompositeVirtualPinManager:
    """复合节点虚拟引脚管理器
    
    职责：
    - 添加和移除虚拟引脚的端口映射
    - 验证映射的合法性（方向、类型、唯一性）
    - 查找端口对应的虚拟引脚
    - 获取可用的虚拟引脚列表
    - 计算引脚的显示编号
    """
    
    def __init__(self, composite_nodes: Dict[str, CompositeNodeConfig]):
        """初始化虚拟引脚管理器
        
        Args:
            composite_nodes: 复合节点字典 {composite_id: CompositeNodeConfig}
        """
        self.composite_nodes = composite_nodes
    
    def add_virtual_pin_mapping(
        self,
        composite_id: str,
        pin_index: int,
        node_id: str,
        port_name: str,
        is_input: bool,
        port_type: str = None,
        is_flow: bool = False
    ) -> bool:
        """为虚拟引脚添加端口映射
        
        Args:
            composite_id: 复合节点ID
            pin_index: 虚拟引脚序号
            node_id: 内部节点ID
            port_name: 端口名称
            is_input: 端口方向
            port_type: 端口类型（可选，用于类型检查）
            is_flow: 是否为流程端口
            
        Returns:
            是否成功
        """
        composite = self.composite_nodes.get(composite_id)
        if not composite:
            return False
        
        # 查找虚拟引脚
        virtual_pin = next((p for p in composite.virtual_pins if p.pin_index == pin_index), None)
        if not virtual_pin:
            return False
        
        # 检查方向一致性
        if virtual_pin.is_input != is_input:
            log_error(f"端口方向不匹配：虚拟引脚是{'输入' if virtual_pin.is_input else '输出'}，端口是{'输入' if is_input else '输出'}")
            return False
        
        # 检查流程/数据类型一致性
        if virtual_pin.is_flow != is_flow:
            log_error(f"端口类型不匹配：虚拟引脚是{'流程' if virtual_pin.is_flow else '数据'}，端口是{'流程' if is_flow else '数据'}")
            return False
        
        # 检查该端口是否已被其他虚拟引脚映射
        for pin in composite.virtual_pins:
            if any(mp.node_id == node_id and mp.port_name == port_name for mp in pin.mapped_ports):
                log_error(f"端口已被映射到虚拟引脚: {pin.pin_name}")
                return False
        
        # 类型一致性检查（如果提供了端口类型）
        if port_type:
            # 如果虚拟引脚已有映射，检查类型是否一致
            if virtual_pin.mapped_ports:
                # 虚拟引脚的类型应该与第一个映射的类型一致
                if virtual_pin.pin_type != port_type:
                    # 检查是否兼容（any类型可以与任何类型连接）
                    if virtual_pin.pin_type != "any" and port_type != "any":
                        log_error(f"端口类型不匹配：虚拟引脚类型为 {virtual_pin.pin_type}，端口类型为 {port_type}")
                        return False
            else:
                # 如果是第一个映射，更新虚拟引脚的类型
                if virtual_pin.pin_type == "any" or not virtual_pin.pin_type:
                    virtual_pin.pin_type = port_type
        
        # 添加映射
        mapped_port = MappedPort(node_id=node_id, port_name=port_name, is_input=is_input, is_flow=is_flow)
        virtual_pin.mapped_ports.append(mapped_port)
        
        log_info(f"添加映射: {virtual_pin.pin_name} <- {node_id}.{port_name} ({port_type or '未知类型'})")
        return True
    
    def remove_virtual_pin_mapping(
        self,
        composite_id: str,
        pin_index: int,
        node_id: str,
        port_name: str
    ) -> bool:
        """移除虚拟引脚的端口映射
        
        Args:
            composite_id: 复合节点ID
            pin_index: 虚拟引脚序号
            node_id: 内部节点ID
            port_name: 端口名称
            
        Returns:
            是否成功
        """
        composite = self.composite_nodes.get(composite_id)
        if not composite:
            return False
        
        # 查找虚拟引脚
        virtual_pin = next((p for p in composite.virtual_pins if p.pin_index == pin_index), None)
        if not virtual_pin:
            return False
        
        # 移除映射
        virtual_pin.mapped_ports = [
            mp for mp in virtual_pin.mapped_ports
            if not (mp.node_id == node_id and mp.port_name == port_name)
        ]
        
        log_info(f"移除映射: {virtual_pin.pin_name} <- {node_id}.{port_name}")
        return True
    
    def find_port_virtual_pin(
        self,
        composite_id: str,
        node_id: str,
        port_name: str
    ) -> Optional[VirtualPinConfig]:
        """查找端口对应的虚拟引脚
        
        Args:
            composite_id: 复合节点ID
            node_id: 内部节点ID
            port_name: 端口名称
            
        Returns:
            虚拟引脚配置，如果没有映射则返回None
        """
        composite = self.composite_nodes.get(composite_id)
        if not composite:
            return None
        
        for virtual_pin in composite.virtual_pins:
            if any(mp.node_id == node_id and mp.port_name == port_name for mp in virtual_pin.mapped_ports):
                return virtual_pin
        
        return None
    
    def get_available_virtual_pins(
        self,
        composite_id: str,
        is_input: bool,
        is_flow: bool = None
    ) -> List[VirtualPinConfig]:
        """获取可用的虚拟引脚列表（用于添加到现有虚拟引脚）
        
        Args:
            composite_id: 复合节点ID
            is_input: 端口方向
            is_flow: 是否为流程端口（None表示不过滤）
            
        Returns:
            同方向、同类型的虚拟引脚列表
        """
        composite = self.composite_nodes.get(composite_id)
        if not composite:
            return []
        
        pins = [pin for pin in composite.virtual_pins if pin.is_input == is_input]
        
        # 如果指定了is_flow，则进一步过滤
        if is_flow is not None:
            pins = [pin for pin in pins if pin.is_flow == is_flow]
        
        return pins
    
    def get_pin_display_number(
        self,
        composite_id: str,
        virtual_pin: VirtualPinConfig
    ) -> tuple[str, int]:
        """获取虚拟引脚的显示编号
        
        引脚编号规则：流程口和数据口分别编号，输入和输出分别编号
        
        Args:
            composite_id: 复合节点ID
            virtual_pin: 虚拟引脚配置
            
        Returns:
            (类型前缀, 编号)，例如 ("流", 1) 表示 [流1]
        """
        composite = self.composite_nodes.get(composite_id)
        if not composite:
            return ("", 0)
        
        # 按类型和方向分组
        same_type_pins = [
            pin for pin in composite.virtual_pins
            if pin.is_input == virtual_pin.is_input and pin.is_flow == virtual_pin.is_flow
        ]
        
        # 按 pin_index 排序
        same_type_pins.sort(key=lambda p: p.pin_index)
        
        # 找到当前引脚的位置（1-based）
        position = same_type_pins.index(virtual_pin) + 1
        
        # 确定类型前缀
        prefix = "流" if virtual_pin.is_flow else "数"
        
        return (prefix, position)

    # -------------------------------------------------------------------------
    # 批量清理：按节点 ID 移除所有相关映射（供节点删除/批处理使用）
    # -------------------------------------------------------------------------

    def cleanup_mappings_for_deleted_node(
        self,
        composite_id: str,
        node_id: str,
    ) -> Tuple[bool, Set[str], int]:
        """清理指定复合节点中与给定内部节点相关的所有虚拟引脚映射。

        典型使用场景：
        - 复合节点子图中删除节点后，需要同步移除对应的虚拟引脚映射；
        - 若某个虚拟引脚不再包含任何映射，则一并删除该虚拟引脚。

        Args:
            composite_id: 复合节点 ID
            node_id: 被删除的内部节点 ID

        Returns:
            (has_changes, affected_node_ids, removed_pins)
            - has_changes: 是否有映射或引脚被修改
            - affected_node_ids: 受影响的内部节点 ID 集合（用于 UI 层刷新端口）
            - removed_pins: 被删除的虚拟引脚数量
        """
        composite = self.composite_nodes.get(composite_id)
        if not composite:
            return False, set(), 0

        has_changes: bool = False
        pins_to_delete: List[VirtualPinConfig] = []
        affected_node_ids: Set[str] = set()

        for virtual_pin in composite.virtual_pins:
            if not virtual_pin.mapped_ports:
                continue

            mapped_nodes_before = [mapped_port.node_id for mapped_port in virtual_pin.mapped_ports]
            original_count = len(virtual_pin.mapped_ports)

            # 过滤掉映射到被删除节点的端口
            virtual_pin.mapped_ports = [
                mapped_port
                for mapped_port in virtual_pin.mapped_ports
                if mapped_port.node_id != node_id
            ]

            if len(virtual_pin.mapped_ports) < original_count:
                has_changes = True
                # 受影响节点：原来映射到该虚拟引脚的所有节点
                affected_node_ids.update(mapped_nodes_before)
                removed_count = original_count - len(virtual_pin.mapped_ports)
                log_info(
                    "[虚拟引脚管理] 从引脚 '{}' 中移除了 {} 个映射（节点: {}）",
                    virtual_pin.pin_name,
                    removed_count,
                    node_id,
                )

                # 若不再包含任何映射，稍后删除该虚拟引脚本身
                if not virtual_pin.mapped_ports:
                    pins_to_delete.append(virtual_pin)

        removed_pins = 0
        if pins_to_delete:
            for pin in pins_to_delete:
                # 这里 pin.mapped_ports 通常已为空，但仍做一次聚合以防后续扩展
                for mapped_port in pin.mapped_ports:
                    affected_node_ids.add(mapped_port.node_id)
                composite.virtual_pins.remove(pin)
                removed_pins += 1
                log_info(
                    "[虚拟引脚管理] 删除虚拟引脚 '{}'(index={})，因其映射已全部移除",
                    pin.pin_name,
                    pin.pin_index,
                )

        return has_changes, affected_node_ids, removed_pins

