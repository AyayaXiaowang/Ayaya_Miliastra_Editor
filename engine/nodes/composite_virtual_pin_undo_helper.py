"""复合节点虚拟引脚撤销辅助模块。

本模块位于引擎 `nodes` 层，负责围绕虚拟引脚的“快照 / 清理 / 恢复”三步流程，
为 UI 撤销命令与场景层提供纯模型级的帮助函数：

- `snapshot_virtual_pins_for_node`：在删除内部节点前，对受影响的虚拟引脚做快照；
- `cleanup_virtual_pins_for_deleted_node`：删除节点后，从虚拟引脚上移除对应映射并清理空引脚；
- `restore_virtual_pins_from_snapshot`：撤销删除时，根据快照恢复虚拟引脚及其映射。

注意：本模块只操作 `CompositeNodeManager` 与 `CompositeNodeConfig`，不感知 Qt/UI，
是否写回磁盘通过 `is_read_only` 参数控制，由调用方决定何时刷新 UI。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set, Tuple

from engine.nodes.advanced_node_features import (
    VirtualPinConfig,
    MappedPort,
)
from engine.nodes.composite_node_manager import CompositeNodeManager
from engine.utils.logging.logger import log_info


@dataclass
class CompositeVirtualPinSnapshot:
    """单个内部节点删除前的虚拟引脚快照。

    - deleted_pins: 删除该节点后会被整体移除的虚拟引脚（所有映射都指向该节点）；
    - modified_pins: 删除该节点后仍然存在，但映射集合会被裁剪的虚拟引脚。
    """

    deleted_pins: List[VirtualPinConfig]
    modified_pins: List[VirtualPinConfig]


def _clone_virtual_pin(virtual_pin: VirtualPinConfig) -> VirtualPinConfig:
    """深拷贝一个 VirtualPinConfig（含全部 mapped_ports）。"""
    return VirtualPinConfig(
        pin_index=virtual_pin.pin_index,
        pin_name=virtual_pin.pin_name,
        pin_type=virtual_pin.pin_type,
        is_input=virtual_pin.is_input,
        is_flow=virtual_pin.is_flow,
        description=virtual_pin.description,
        mapped_ports=[
            MappedPort(
                node_id=mapped_port.node_id,
                port_name=mapped_port.port_name,
                is_input=mapped_port.is_input,
                is_flow=mapped_port.is_flow,
            )
            for mapped_port in virtual_pin.mapped_ports
        ],
        merge_strategy=virtual_pin.merge_strategy,
    )


def snapshot_virtual_pins_for_node(
    manager: CompositeNodeManager,
    composite_id: str,
    node_id: str,
) -> CompositeVirtualPinSnapshot:
    """为即将删除的内部节点生成虚拟引脚快照。

    Args:
        manager: 复合节点管理器
        composite_id: 复合节点 ID
        node_id: 即将被删除的内部节点 ID

    Returns:
        CompositeVirtualPinSnapshot 对象；若当前没有任何相关映射，两个列表均为空。
    """
    composite = manager.get_composite_node(composite_id)
    if composite is None:
        return CompositeVirtualPinSnapshot(deleted_pins=[], modified_pins=[])

    deleted_pins: List[VirtualPinConfig] = []
    modified_pins: List[VirtualPinConfig] = []

    for virtual_pin in composite.virtual_pins:
        has_mapping_for_node = any(
            mapped_port.node_id == node_id for mapped_port in virtual_pin.mapped_ports
        )
        if not has_mapping_for_node:
            continue

        saved_pin = _clone_virtual_pin(virtual_pin)
        remaining_mappings = [
            mapped_port
            for mapped_port in virtual_pin.mapped_ports
            if mapped_port.node_id != node_id
        ]
        if not remaining_mappings:
            deleted_pins.append(saved_pin)
        else:
            modified_pins.append(saved_pin)

    if deleted_pins or modified_pins:
        log_info(
            "[虚拟引脚-Undo] 删除节点前快照: node_id={}, deleted_pins={}, modified_pins={}",
            node_id,
            len(deleted_pins),
            len(modified_pins),
        )

    return CompositeVirtualPinSnapshot(
        deleted_pins=deleted_pins,
        modified_pins=modified_pins,
    )


def cleanup_virtual_pins_for_deleted_node(
    manager: CompositeNodeManager,
    composite_id: str,
    node_id: str,
    *,
    is_read_only: bool = False,
) -> Tuple[bool, Set[str]]:
    """在删除内部节点后，清理复合节点中的虚拟引脚映射。

    - 移除所有指向该节点的 mapped_port；
    - 若某个虚拟引脚的映射全部被移除，则删除该虚拟引脚本身；
    - 非只读上下文会写回函数文件。

    Args:
        manager: 复合节点管理器
        composite_id: 复合节点 ID
        node_id: 被删除的内部节点 ID
        is_read_only: 是否为只读上下文（只更新内存，不写盘）

    Returns:
        (has_changes, affected_node_ids)
        - has_changes: 是否有任何虚拟引脚被修改或删除；
        - affected_node_ids: 受影响的内部节点 ID 集合（用于 UI 刷新端口显示）。
    """
    composite = manager.get_composite_node(composite_id)
    if composite is None:
        return False, set()

    has_changes = False
    pins_to_delete: List[VirtualPinConfig] = []
    affected_node_ids: Set[str] = set()

    for virtual_pin in composite.virtual_pins:
        mapped_nodes_before = [mapped_port.node_id for mapped_port in virtual_pin.mapped_ports]
        original_count = len(virtual_pin.mapped_ports)

        virtual_pin.mapped_ports = [
            mapped_port
            for mapped_port in virtual_pin.mapped_ports
            if mapped_port.node_id != node_id
        ]

        if len(virtual_pin.mapped_ports) < original_count:
            has_changes = True
            affected_node_ids.update(mapped_nodes_before)
            log_info(
                "[虚拟引脚清理] composite_id={} pin='{}' 移除了 {} 个映射 (deleted_node_id={})",
                composite_id,
                virtual_pin.pin_name,
                original_count - len(virtual_pin.mapped_ports),
                node_id,
            )

            if not virtual_pin.mapped_ports:
                pins_to_delete.append(virtual_pin)

    if pins_to_delete:
        for pin in pins_to_delete:
            affected_node_ids.update(
                mapped_port.node_id for mapped_port in getattr(pin, "mapped_ports", [])
            )
            composite.virtual_pins.remove(pin)
        log_info(
            "[虚拟引脚清理] composite_id={} 删除 {} 个无映射虚拟引脚",
            composite_id,
            len(pins_to_delete),
        )

    if not has_changes:
        return False, affected_node_ids

    if not is_read_only:
        manager.update_composite_node(composite_id, composite)
        log_info(
            "[虚拟引脚清理] composite_id={} 已写回复合节点文件",
            composite_id,
        )
    else:
        log_info(
            "[虚拟引脚清理] composite_id={} 只读上下文，仅更新内存（不写盘）",
            composite_id,
        )

    return True, affected_node_ids


def restore_virtual_pins_from_snapshot(
    manager: CompositeNodeManager,
    composite_id: str,
    snapshot: CompositeVirtualPinSnapshot,
    *,
    is_read_only: bool = False,
) -> Set[str]:
    """根据快照恢复虚拟引脚状态（用于撤销节点删除）。

    Args:
        manager: 复合节点管理器
        composite_id: 复合节点 ID
        snapshot: 删除前记录的虚拟引脚快照
        is_read_only: 是否为只读上下文（只更新内存，不写盘）

    Returns:
        affected_node_ids: 受影响的内部节点 ID 集合（用于 UI 刷新端口显示）。
    """
    if snapshot is None:
        return set()

    composite = manager.get_composite_node(composite_id)
    if composite is None:
        return set()

    affected_node_ids: Set[str] = set()

    # 先恢复“整个被删除”的虚拟引脚
    for saved_pin in snapshot.deleted_pins:
        # 避免重复追加：按 pin_index 判定
        exists = any(
            pin.pin_index == saved_pin.pin_index for pin in composite.virtual_pins
        )
        if not exists:
            composite.virtual_pins.append(saved_pin)
        for mapped_port in saved_pin.mapped_ports:
            affected_node_ids.add(mapped_port.node_id)

    # 再恢复“被裁剪映射”的虚拟引脚
    for saved_pin in snapshot.modified_pins:
        for virtual_pin in composite.virtual_pins:
            if virtual_pin.pin_index == saved_pin.pin_index:
                virtual_pin.mapped_ports = [
                    MappedPort(
                        node_id=mapped_port.node_id,
                        port_name=mapped_port.port_name,
                        is_input=mapped_port.is_input,
                        is_flow=mapped_port.is_flow,
                    )
                    for mapped_port in saved_pin.mapped_ports
                ]
                for mapped_port in saved_pin.mapped_ports:
                    affected_node_ids.add(mapped_port.node_id)
                break

    if snapshot.deleted_pins or snapshot.modified_pins:
        if not is_read_only:
            manager.update_composite_node(composite_id, composite)
            log_info(
                "[虚拟引脚-Undo] composite_id={} 撤销节点删除，恢复 deleted_pins={} / modified_pins={}",
                composite_id,
                len(snapshot.deleted_pins),
                len(snapshot.modified_pins),
            )
        else:
            log_info(
                "[虚拟引脚-Undo] composite_id={} 撤销节点删除（只读上下文，仅更新内存）",
                composite_id,
            )

    return affected_node_ids


__all__ = [
    "CompositeVirtualPinSnapshot",
    "snapshot_virtual_pins_for_node",
    "cleanup_virtual_pins_for_deleted_node",
    "restore_virtual_pins_from_snapshot",
]


