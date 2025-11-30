"""节点图错误状态跟踪器 - 跟踪保存失败的节点图"""

from __future__ import annotations
from typing import Dict, Optional, Set
from datetime import datetime
from PyQt6 import QtCore


class GraphErrorInfo:
    """节点图错误信息"""
    
    def __init__(self, graph_id: str, error_message: str, error_type: str = "save_failed"):
        self.graph_id = graph_id
        self.error_message = error_message
        self.error_type = error_type  # "save_failed", "validation_failed", "corrupted"
        self.timestamp = datetime.now()
    
    def __str__(self) -> str:
        return f"[{self.error_type}] {self.graph_id}: {self.error_message}"


class GraphErrorTracker(QtCore.QObject):
    """节点图错误状态跟踪器
    
    功能：
    - 记录保存失败的节点图及其错误信息
    - 提供查询接口，供UI组件显示错误状态
    - 发送信号通知错误状态变化
    
    注意：使用模块级单例，不要直接创建实例，使用 get_instance() 获取
    """
    
    # 信号定义
    error_status_changed = QtCore.pyqtSignal(str, bool)  # (graph_id, has_error)
    
    def __init__(self):
        super().__init__()
        
        # 错误记录：{graph_id: GraphErrorInfo}
        self._errors: Dict[str, GraphErrorInfo] = {}
        
        print("[错误跟踪器] 初始化完成")
    
    def mark_error(self, graph_id: str, error_message: str, error_type: str = "save_failed") -> None:
        """标记节点图有错误
        
        Args:
            graph_id: 节点图ID
            error_message: 错误信息
            error_type: 错误类型
        """
        error_info = GraphErrorInfo(graph_id, error_message, error_type)
        self._errors[graph_id] = error_info
        
        print(f"[错误跟踪器] 标记错误: {error_info}")
        
        # 发送信号
        self.error_status_changed.emit(graph_id, True)
    
    def clear_error(self, graph_id: str) -> None:
        """清除节点图的错误标记
        
        Args:
            graph_id: 节点图ID
        """
        if graph_id in self._errors:
            del self._errors[graph_id]
            print(f"[错误跟踪器] 清除错误: {graph_id}")
            
            # 发送信号
            self.error_status_changed.emit(graph_id, False)
    
    def has_error(self, graph_id: str) -> bool:
        """检查节点图是否有错误
        
        Args:
            graph_id: 节点图ID
        
        Returns:
            是否有错误
        """
        return graph_id in self._errors
    
    def get_error_info(self, graph_id: str) -> Optional[GraphErrorInfo]:
        """获取节点图的错误信息
        
        Args:
            graph_id: 节点图ID
        
        Returns:
            错误信息，如果没有错误返回None
        """
        return self._errors.get(graph_id)
    
    def get_all_error_graphs(self) -> Set[str]:
        """获取所有有错误的节点图ID集合
        
        Returns:
            节点图ID集合
        """
        return set(self._errors.keys())
    
    def clear_all_errors(self) -> None:
        """清除所有错误标记"""
        graph_ids = list(self._errors.keys())
        self._errors.clear()
        print("[错误跟踪器] 清除所有错误")
        
        # 为每个清除的错误发送信号
        for graph_id in graph_ids:
            self.error_status_changed.emit(graph_id, False)
    
    def get_error_count(self) -> int:
        """获取错误数量
        
        Returns:
            错误数量
        """
        return len(self._errors)
    
    def get_error_summary(self) -> str:
        """获取错误摘要
        
        Returns:
            错误摘要字符串
        """
        if not self._errors:
            return "无错误"
        
        summary_lines = [f"共 {len(self._errors)} 个节点图有错误:"]
        for graph_id, error_info in self._errors.items():
            summary_lines.append(f"  - {graph_id}: {error_info.error_type}")
        
        return "\n".join(summary_lines)


# 模块级单例实例
_tracker_instance: Optional[GraphErrorTracker] = None


def get_instance() -> GraphErrorTracker:
    """获取全局单例实例
    
    Returns:
        GraphErrorTracker 单例实例
    """
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = GraphErrorTracker()
    return _tracker_instance

