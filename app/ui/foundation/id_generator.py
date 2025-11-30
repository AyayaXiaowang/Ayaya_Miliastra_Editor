"""统一的 ID 生成工具。

提供基于时间戳 + 随机熵的 ID 生成方法，避免在 UI 层重复写 `datetime`
格式化逻辑。当需要为某个资源创建 ID 时，请始终通过本模块获取，以便
后续替换为其他方案（如雪花 ID、可配置前缀）时只需修改一个入口。
"""

from datetime import datetime
from secrets import token_hex


def generate_prefixed_id(prefix: str) -> str:
    """返回带有前缀的唯一 ID，例如 prefix_20250101_120101_123456_abcd."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    random_suffix = token_hex(2)  # 提供额外熵，避免同秒碰撞
    return f"{prefix}_{timestamp}_{random_suffix}"


