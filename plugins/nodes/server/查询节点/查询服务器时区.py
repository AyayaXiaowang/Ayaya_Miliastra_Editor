from __future__ import annotations
from datetime import datetime
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="查询服务器时区",
    category="查询节点",
    outputs=[("时区", "整数")],
    description="可以查询服务器的时区",
    doc_reference="服务器节点/查询节点/查询节点.md"
)
def 查询服务器时区(game):
    """可以查询服务器的时区"""
    # 优先允许在 MockRuntime 上显式注入（便于测试不随系统时区漂移）
    injected = getattr(game, "server_timezone_hours", None)
    if isinstance(injected, int):
        return int(injected)
    if isinstance(injected, float):
        return int(round(float(injected)))

    # 回退：使用当前环境的本地时区偏移（单位小时，四舍五入到整数）
    offset = datetime.now().astimezone().utcoffset()
    if offset is None:
        return 0
    hours = float(offset.total_seconds()) / 3600.0
    return int(round(hours))
