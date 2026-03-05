from __future__ import annotations

"""
ugc_file_tools.contracts.signal_meta_binding

单一真源：信号节点（发送/监听/发送到服务端）的 meta binding 口径约定。

该规则同时影响：
- `.gia` 导出（NodePin 的 shell/kernel index、compositePinIndex）
- `.gil` 写回（record 的 pin index/index2 与 compositePinIndex）

若口径分叉，典型后果：
- 编辑器/游戏侧忽略默认值（表现为“填空全空”）
- 信号端口索引漂移导致参数错位或断线
"""


def resolve_signal_meta_binding_param_pin_indices(*, slot_index: int) -> tuple[int, int]:
    """
    将“信号 meta binding 参数端口”的 GraphModel slot_index 映射为 (shell_index, kernel_index)。

    约定（对齐 `.gil` 写回回归用例）：
    - shell_index = slot_index
    - kernel_index = slot_index
    """
    return int(slot_index), int(slot_index)


__all__ = [
    "resolve_signal_meta_binding_param_pin_indices",
]

