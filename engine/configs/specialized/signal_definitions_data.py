from __future__ import annotations

from typing import Any, Dict

# 本文件由 tools/generate_struct_and_signal_definitions.py 自动生成。
# 信号定义以 Python 字典常量形式固化为 SIGNAL_DEFINITION_PAYLOADS。
# 运行时不再依赖 assets/资源库/管理配置/信号 下的聚合 JSON 文件。

SIGNAL_DEFINITION_PAYLOADS: Dict[str, Dict[str, Any]] = {
    'signal_20251119_103753_007435_f98e': {'signal_id': 'signal_20251119_103753_007435_f98e', 'signal_name': '信号1', 'parameters': [{'name': '测试参数1', 'parameter_type': '整数', 'description': ''}], 'description': '1'},
    'signal_forge_hero_teleport_01': {'signal_id': 'signal_forge_hero_teleport_01', 'signal_name': '传送', 'parameters': [{'name': '地点', 'parameter_type': '字符串', 'description': '目标界面名称（强化界面/挑战界面/打造界面/冒险界面）'}], 'description': '锻刀英雄主城内用于在不同界面锚点之间传送玩家的信号。'},
}

def list_signal_ids() -> list[str]:
    """返回所有可用的信号 ID 列表（排序后）。"""
    return sorted(SIGNAL_DEFINITION_PAYLOADS.keys())

def get_signal_payload(signal_id: str) -> Dict[str, Any] | None:
    """按 ID 获取单个信号定义载荷的浅拷贝，未找到时返回 None。"""
    key = str(signal_id)
    payload = SIGNAL_DEFINITION_PAYLOADS.get(key)
    if payload is None:
        return None
    return dict(payload)
