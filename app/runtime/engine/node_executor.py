"""节点执行器基类 - 用于扩展节点执行逻辑"""

from typing import Any, Callable, Dict, List


class NodeExecutor:
    """节点执行器基类
    
    可以用于实现更复杂的节点执行逻辑，如：
    - 断点调试
    - 执行追踪
    - 性能分析
    """
    
    def __init__(self, game_runtime):
        self.game = game_runtime
        self.execution_stack = []  # 执行栈
        self.breakpoints = set()   # 断点
        self.trace_enabled = False  # 是否启用追踪
    
    def execute_node(self, node_name: str, node_func: Callable, *args, **kwargs):
        """执行单个节点"""
        if self.trace_enabled:
            print(f"[执行追踪] 开始执行节点: {node_name}")
            self.execution_stack.append(node_name)
        
        # 检查断点
        if node_name in self.breakpoints:
            print(f"[断点] 在节点 {node_name} 处暂停")
            # 这里可以添加交互式调试逻辑
        
        # 执行节点
        result = node_func(*args, **kwargs)
        
        if self.trace_enabled:
            self.execution_stack.pop()
            print(f"[执行追踪] 完成执行节点: {node_name}, 返回值: {result}")
        
        return result
    
    def add_breakpoint(self, node_name: str):
        """添加断点"""
        self.breakpoints.add(node_name)
        print(f"[断点] 已在节点 {node_name} 添加断点")
    
    def remove_breakpoint(self, node_name: str):
        """移除断点"""
        if node_name in self.breakpoints:
            self.breakpoints.remove(node_name)
            print(f"[断点] 已移除节点 {node_name} 的断点")
    
    def enable_trace(self):
        """启用执行追踪"""
        self.trace_enabled = True
        print("[执行追踪] 已启用")
    
    def disable_trace(self):
        """禁用执行追踪"""
        self.trace_enabled = False
        print("[执行追踪] 已禁用")
    
    def get_execution_stack(self) -> List[str]:
        """获取当前执行栈"""
        return self.execution_stack.copy()


class LoopProtection:
    """循环保护 - 防止无限循环"""
    
    MAX_ITERATIONS = 10000  # 最大迭代次数
    
    def __init__(self):
        self.iteration_count = 0
    
    def check(self):
        """检查是否超过最大迭代次数"""
        self.iteration_count += 1
        if self.iteration_count > self.MAX_ITERATIONS:
            raise RuntimeError(
                f"检测到可能的无限循环！已迭代 {self.iteration_count} 次。"
                f"如果这是预期行为，请修改 LoopProtection.MAX_ITERATIONS"
            )
    
    def reset(self):
        """重置计数器"""
        self.iteration_count = 0

