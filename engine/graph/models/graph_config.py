"""节点图配置模型 - 独立的节点图资源"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime


@dataclass
class GraphConfig:
    """独立的节点图配置（可复用的节点图资源）"""
    graph_id: str
    name: str
    graph_type: str  # "server" 或 "client"
    folder_path: str = ""  # 文件夹路径，如 "服务器节点图/角色"
    description: str = ""
    data: dict = field(default_factory=dict)  # GraphModel 序列化后的数据
    metadata: dict = field(default_factory=dict)  # 元数据
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保 metadata 中有基本字段
        if "created_at" not in self.metadata:
            self.metadata["created_at"] = datetime.now().isoformat()
        if "updated_at" not in self.metadata:
            self.metadata["updated_at"] = datetime.now().isoformat()
    
    def serialize(self) -> dict:
        """序列化为字典"""
        return {
            "graph_id": self.graph_id,
            "name": self.name,
            "graph_type": self.graph_type,
            "folder_path": self.folder_path,
            "description": self.description,
            "data": self.data,
            "created_at": self.metadata.get("created_at"),
            "last_modified": self.metadata.get("updated_at"),
            "metadata": self.metadata
        }
    
    @staticmethod
    def deserialize(data: dict) -> GraphConfig:
        """从字典反序列化"""
        return GraphConfig(
            graph_id=data["graph_id"],
            name=data["name"],
            graph_type=data.get("graph_type", "server"),
            folder_path=data.get("folder_path", ""),
            description=data.get("description", ""),
            data=data.get("data", {}),
            metadata=data.get("metadata", {})
        )
    
    def update_timestamp(self) -> None:
        """更新时间戳"""
        self.metadata["updated_at"] = datetime.now().isoformat()
    
    def get_node_count(self) -> int:
        """获取节点数量"""
        if "nodes" in self.data:
            return len(self.data["nodes"])
        return 0
    
    def get_edge_count(self) -> int:
        """获取连接数量"""
        if "edges" in self.data:
            return len(self.data["edges"])
        return 0


