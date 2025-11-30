# -*- coding: utf-8 -*-
"""
执行引导文案集中化：根据步骤类型在监控面板输出统一的引导信息。

约定：
- monitor_panel 提供 log(str) 与 update_status(str) 等方法
"""

from typing import Dict, Any


class ExecutionGuides:
    """执行指引：提供执行相关的用户指引。"""

    @staticmethod
    def log_composite_guide(monitor_panel, detail_type: str, info: Dict[str, Any]) -> None:
        """在执行监控面板输出复合节点相关步骤的指引信息。"""
        composite_name = info.get("composite_name", "复合节点")
        composite_id = info.get("composite_id", "")

        if detail_type == "composite_root":
            monitor_panel.log(f"目标：{composite_name}（{composite_id}）")
            monitor_panel.log("1) 新建复合节点  2) 设置名称/描述/文件夹  3) 设置虚拟引脚  4) 保存")
            return

        if detail_type == "composite_create_new":
            monitor_panel.log(f"新建复合节点：{composite_name}")
            monitor_panel.log("在复合节点管理器中点击'新建复合节点'，位于当前文件夹下。")
            return

        if detail_type == "composite_set_meta":
            monitor_panel.log(
                f"设置属性：名称={info.get('name','')}, 文件夹={info.get('folder_path','')}"
            )
            monitor_panel.log("在右侧'复合节点属性'面板填写名称与描述，必要时选择文件夹。")
            return

        if detail_type == "composite_set_pins":
            inputs = info.get("inputs", []) or []
            outputs = info.get("outputs", []) or []
            if inputs:
                monitor_panel.log("输入引脚：")
                for pin in inputs:
                    pin_name = pin.get("name", "")
                    is_flow = bool(pin.get("is_flow", False))
                    monitor_panel.log(f" - {'流程' if is_flow else '数据'}输入：{pin_name}")
            if outputs:
                monitor_panel.log("输出引脚：")
                for pin in outputs:
                    pin_name = pin.get("name", "")
                    is_flow = bool(pin.get("is_flow", False))
                    monitor_panel.log(f" - {'流程' if is_flow else '数据'}输出：{pin_name}")
            monitor_panel.log("在复合节点编辑器内部，右键端口→设置为虚拟引脚/添加到现有虚拟引脚。")
            return

        if detail_type == "composite_save":
            monitor_panel.log("保存复合节点：点击工具栏'保存'，确保节点库同步。")
            return

        monitor_panel.log("未识别的复合节点步骤类型。")

