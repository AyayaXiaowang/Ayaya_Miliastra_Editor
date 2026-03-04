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


# NOTE:
# 历史误判：早期我们以为“信号 meta binding 的参数 InParam kernel index 固定为 0”，
# 但对照真源 `.gil`（例如 sig_sample_09 / correct_signal）可确认：
# - 参数 pins 的 i2(pin_index2) 与 i1(pin_index) **一致**（shell=kernel=slot）
# - 即：slot_index=1 的参数 pin，其 i2.index 也应为 1（而不是 0）
#
# 为兼容旧代码保留该常量，但不要再用于参数 pin 的 kernel index 计算。
SIGNAL_META_BINDING_PARAM_KERNEL_INDEX: int = 0  # deprecated: do not use for param pins


def resolve_signal_meta_binding_param_pin_indices(*, slot_index: int) -> tuple[int, int]:
    """
    将“信号 meta binding 参数端口”的 GraphModel slot_index 映射为 (shell_index, kernel_index)。

    约定（对齐真源 `.gil` / `.gia` Graph IR）：
    - shell_index = slot_index
    - kernel_index = slot_index
    """
    return int(slot_index), int(slot_index)


__all__ = [
    "SIGNAL_META_BINDING_PARAM_KERNEL_INDEX",
    "resolve_signal_meta_binding_param_pin_indices",
]

