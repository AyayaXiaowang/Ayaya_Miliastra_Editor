"""CompositeNodeManagerWidget 的保存/虚拟引脚/基本信息变更 mixin。"""

from __future__ import annotations

from typing import Optional

from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from app.ui.foundation.dialog_utils import ask_yes_no_dialog


class CompositeNodeManagerSaveMixin:
    # ------------------------------------------------------------------ 虚拟引脚与基本信息（供右侧面板调用）

    def add_virtual_pin(self, is_input: bool) -> None:
        """添加虚拟引脚（由属性面板调用）。"""
        if not self.current_composite:
            from app.ui.foundation.dialog_utils import show_warning_dialog

            show_warning_dialog(self, "提示", "请先选择一个复合节点")
            return

        existing_indices = [virtual_pin.pin_index for virtual_pin in self.current_composite.virtual_pins]
        new_index = max(existing_indices) + 1 if existing_indices else 1

        direction_name = "输入" if is_input else "输出"
        new_pin = VirtualPinConfig(
            pin_index=new_index,
            pin_name=f"{direction_name}_{new_index}",
            pin_type="泛型",
            is_input=is_input,
            description="",
        )
        self.current_composite.virtual_pins.append(new_pin)
        self._composite_meta_dirty = True
        self.composite_selected.emit(self.current_composite_id)

    def remove_virtual_pin(self, pin_index: int) -> None:
        """删除指定的虚拟引脚（由属性面板调用）。"""
        if not self.current_composite:
            return

        self.current_composite.virtual_pins = [
            virtual_pin for virtual_pin in self.current_composite.virtual_pins if virtual_pin.pin_index != pin_index
        ]
        self._composite_meta_dirty = True
        self.composite_selected.emit(self.current_composite_id)

    def update_pin_from_table(self, pin_index: int, name: str, pin_type: str) -> None:
        """更新虚拟引脚的名称与类型（由属性面板调用）。"""
        if not self.current_composite:
            return

        target_pin = next(
            (virtual_pin for virtual_pin in self.current_composite.virtual_pins if virtual_pin.pin_index == pin_index),
            None,
        )
        if target_pin is None:
            return
        target_pin.pin_name = name
        target_pin.pin_type = pin_type
        self._composite_meta_dirty = True

    def update_composite_basic_info(self, name: str, description: str) -> None:
        """更新复合节点基本信息（由属性面板调用）。"""
        if not self.current_composite:
            return

        self.current_composite.node_name = name
        self.current_composite.node_description = description
        self._composite_meta_dirty = True

    def get_current_composite(self) -> Optional[CompositeNodeConfig]:
        """获取当前编辑的复合节点。"""
        return self.current_composite

    # ------------------------------------------------------------------ 保存（仍保留，只读模式下短路）

    def _save_current_composite(self) -> None:
        """保存当前编辑的复合节点（默认在只读模式下短路，不落盘）。"""
        if not self.current_composite or not self.current_composite_id:
            return
        if not self.can_persist_composite:
            return
        if not self._has_unsaved_changes():
            return

        if self.graph_model is not None:
            self.current_composite.sub_graph = self.graph_model.serialize()

        # 保护：若该复合节点文件不是 payload 格式，保存会覆盖原有源码结构（转换为 payload 以保证可解析/可校验）。
        if not self._is_payload_backed_file(self.current_composite_id):
            if not ask_yes_no_dialog(
                self,
                "确认覆盖源码",
                (
                    "该复合节点当前不是“可视化落盘（payload）格式”。\n"
                    "继续保存将覆盖原有 Python 源码结构，并转换为 payload 格式，"
                    "以保证后续可被解析器加载与校验器验证。\n\n"
                    "是否继续？"
                ),
            ):
                print(f"[取消] 用户取消保存复合节点: {self.current_composite.node_name}")
                return

        impact = self._service.analyze_update_impact(self.current_composite_id, self.current_composite)
        if impact.get("has_impact", False):
            if not self._show_impact_confirmation_dialog(impact):
                print(f"[取消] 用户取消保存复合节点: {self.current_composite.node_name}")
                return

        self._service.persist_updated_composite(
            self.current_composite_id,
            self.current_composite,
            skip_impact_check=True,
        )
        self._composite_meta_dirty = False
        if self.graph_editor_controller is not None:
            self.graph_editor_controller.mark_as_saved()

    def _is_payload_backed_file(self, composite_id: str) -> bool:
        """判断复合节点文件是否为 payload 落盘格式。"""
        file_path = getattr(self.manager, "composite_index", {}).get(composite_id)
        if file_path is None:
            return False
        if not file_path.exists():
            return False
        with open(file_path, "r", encoding="utf-8") as file:
            code = file.read()
        return "COMPOSITE_PAYLOAD_JSON" in code

    def _show_impact_confirmation_dialog(self, impact: dict) -> bool:
        """显示复合节点更新影响的确认对话框。"""
        removed_pins = impact.get("removed_pins", [])
        changed_pins = impact.get("changed_pins", [])
        affected_graphs = impact.get("affected_graphs", [])
        total_connections = impact.get("total_affected_connections", 0)

        if not self.current_composite:
            return False

        message_lines: list[str] = [f"复合节点 '{self.current_composite.node_name}' 的修改会影响其他节点图：\n"]

        if removed_pins:
            message_lines.append(f"⚠️  删除了 {len(removed_pins)} 个引脚：")
            for pin_name in removed_pins[:5]:
                message_lines.append(f"   • {pin_name}")
            if len(removed_pins) > 5:
                message_lines.append(f"   ... 还有 {len(removed_pins) - 5} 个")
            message_lines.append("")

        if changed_pins:
            message_lines.append(f"⚠️  修改了 {len(changed_pins)} 个引脚的类型：")
            for pin_name in changed_pins[:5]:
                message_lines.append(f"   • {pin_name}")
            if len(changed_pins) > 5:
                message_lines.append(f"   ... 还有 {len(changed_pins) - 5} 个")
            message_lines.append("")

        message_lines.append("📊 影响范围：")
        message_lines.append(f"   • {len(affected_graphs)} 个节点图")
        message_lines.append(f"   • {total_connections} 条连线将被自动断开\n")

        message_lines.append("受影响的节点图：")
        for graph in affected_graphs[:5]:
            graph_name = graph.get("graph_name", "")
            connection_count = graph.get("connection_count", 0)
            message_lines.append(f"   • {graph_name} ({connection_count} 条连线)")
        if len(affected_graphs) > 5:
            message_lines.append(f"   ... 还有 {len(affected_graphs) - 5} 个节点图")

        message_lines.append("\n⚡ 确认保存后，受影响的连线会自动断开。")
        message_lines.append("您确定要保存这些修改吗？")

        message_text = "\n".join(message_lines)
        return ask_yes_no_dialog(
            self,
            "确认保存复合节点",
            message_text,
        )



