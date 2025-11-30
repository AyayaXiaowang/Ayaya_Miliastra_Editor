"""事件处理器聚合 Mixin - 将不同领域的 UI 事件拆分为小模块后进行组合"""
from __future__ import annotations

from .package_events_mixin import PackageEventsMixin
from .graph_events_mixin import GraphEventsMixin
from .todo_events_mixin import TodoEventsMixin
from .window_navigation_events_mixin import WindowAndNavigationEventsMixin


class EventHandlerMixin(
    PackageEventsMixin,
    GraphEventsMixin,
    TodoEventsMixin,
    WindowAndNavigationEventsMixin,
):
    """事件处理相关方法的组合 Mixin。

    本类本身不实现具体逻辑，仅负责将若干领域内聚的事件处理 Mixin 组合在一起：
    - PackageEventsMixin: 存档加载/保存、存档下拉框与资源归属变更
    - GraphEventsMixin: 节点图加载/保存、图库交互与复合节点库更新
    - TodoEventsMixin: 任务清单刷新、勾选与图编辑器右上角按钮联动
    - WindowAndNavigationEventsMixin: 导航切换、窗口标题/保存状态、验证与设置对话框
    """

    ...
