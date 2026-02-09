from __future__ import annotations


class LoopProtection:
    """循环保护 - 防止无限循环。

    说明：
    - 该类为纯逻辑工具，放在 engine 层供 plugins/runtime 等复用；
    - 目的：避免 plugins 依赖 app（分层边界：plugins 仅允许依赖 engine）。
    """

    MAX_ITERATIONS = 10000  # 最大迭代次数

    def __init__(self) -> None:
        self.iteration_count = 0

    def check(self) -> None:
        """检查是否超过最大迭代次数。"""
        self.iteration_count += 1
        if self.iteration_count > self.MAX_ITERATIONS:
            raise RuntimeError(
                f"检测到可能的无限循环！已迭代 {self.iteration_count} 次。"
                f"如果这是预期行为，请修改 LoopProtection.MAX_ITERATIONS"
            )

    def reset(self) -> None:
        """重置计数器。"""
        self.iteration_count = 0


