from __future__ import annotations

"""port_type_steps: 端口类型设置步骤门面。

说明：
- 历史上本模块同时承担“类型推断 + 端口定位 + UI 点击 + 输入/输出两侧控制流”等多重职责，
  导致体量膨胀、测试困难；
- 目前已将逻辑拆分到多个更细粒度子模块，本文件仅作为兼容入口与统一导出层：
  - `port_type_effective`：纯类型推断辅助（无 UI）；
  - `port_type_ui_steps`：端口定位与通用类型设置 UI 步骤；
  - `port_type_steps_input`：输入侧端口类型设置流程；
  - `port_type_steps_output`：输出侧端口类型设置流程。
"""

from app.automation.core.executor_protocol import EditorExecutorProtocol
from app.automation.ports.port_type_effective import (
    infer_effective_input_type,
    infer_effective_output_type,
)
from app.automation.ports.port_type_steps_input import process_input_ports_type_setting
from app.automation.ports.port_type_steps_output import process_output_ports_type_setting
from app.automation.ports.port_type_ui_steps import (
    apply_port_type_via_ui,
    compute_planned_ordinal,
    locate_port_center,
    set_port_type_with_settings,
)


__all__ = [
    # 纯推断辅助
    "infer_effective_input_type",
    "infer_effective_output_type",
    # 通用 UI 步骤
    "compute_planned_ordinal",
    "locate_port_center",
    "set_port_type_with_settings",
    "apply_port_type_via_ui",
    # 输入/输出侧步骤
    "process_input_ports_type_setting",
    "process_output_ports_type_setting",
]
