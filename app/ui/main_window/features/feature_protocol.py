from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MainWindowFeature(Protocol):
    """主窗口 Feature 最小协议。

    设计目标：
    - 让新增功能可以以“一个模块 + 一次注册”的方式接入；
    - 避免把装配与连线继续堆进 UISetupMixin / wiring / 各类 mixin。
    """

    feature_id: str

    def install(self, *, main_window: Any) -> None:
        """在主窗口 UI 基础对象就绪后执行安装（创建控件、注册右侧标签、连接信号等）。"""


