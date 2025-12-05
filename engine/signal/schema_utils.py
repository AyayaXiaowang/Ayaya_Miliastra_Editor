from __future__ import annotations

"""信号 schema 哈希工具。

基于当前包的 `{signal_id: SignalConfig}` 字典，构造稳定的结构化数据并计算 MD5，
用于判断“信号定义是否发生变化”，供图编辑器与缓存层按需刷新信号端口结构。
"""

from typing import Any, Dict, List

from engine.graph.models import SignalConfig
from engine.utils.graph.graph_utils import compute_stable_md5_from_data


def _build_signal_schema_payload(signals: Dict[str, SignalConfig]) -> List[Dict[str, Any]]:
    """将信号定义字典转换为稳定的中间结构。

    约定：
    - 先按 signal_id 升序排序；
    - 每个信号内部按参数名升序排序；
    - 仅关心 ID、名称与参数名/类型，忽略描述等非结构字段。
    """
    items: List[Dict[str, Any]] = []

    for signal_id in sorted(signals.keys()):
        config = signals[signal_id]
        signal_name_value = getattr(config, "signal_name", "")
        parameters_value = getattr(config, "parameters", []) or []

        param_items: List[Dict[str, str]] = []
        # 按参数名排序以获得稳定顺序
        sorted_params = sorted(
            parameters_value,
            key=lambda param: str(getattr(param, "name", "")),
        )
        for param in sorted_params:
            name_value = str(getattr(param, "name", ""))
            parameter_type_value = str(getattr(param, "parameter_type", ""))
            param_items.append(
                {
                    "name": name_value,
                    "parameter_type": parameter_type_value,
                }
            )

        items.append(
            {
                "signal_id": str(getattr(config, "signal_id", signal_id)),
                "signal_name": str(signal_name_value),
                "parameters": param_items,
            }
        )

    return items


def compute_signal_schema_hash(signals: Dict[str, SignalConfig]) -> str:
    """计算当前信号定义集合的稳定 schema 哈希。

    Args:
        signals: 当前包的信号定义字典 `{signal_id: SignalConfig}`。

    Returns:
        基于 ID/名称/参数名与参数类型计算出的 MD5 字符串。
    """
    if not isinstance(signals, dict):
        raise TypeError("compute_signal_schema_hash 期望接收 dict[str, SignalConfig] 类型的参数")

    payload = _build_signal_schema_payload(signals)
    return compute_stable_md5_from_data(payload)



