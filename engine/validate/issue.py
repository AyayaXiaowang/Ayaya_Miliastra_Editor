from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class EngineIssue:
    """统一的验证问题数据结构（引擎内部使用）
    
    说明：
    - 与 UI 侧 `ValidationIssue` 无直接耦合，避免破坏现有调用路径
    - code 为稳定错误码，用于配置化豁免、统计与跨版本兼容
    - category/level 用于人类可读分组与展示
    """
    level: str                     # error | warning | info
    category: str                  # 例如：结构/代码规范/复合节点/挂载
    code: str = ""                 # 稳定错误码，例如 STRUCT_PORT_MISMATCH
    message: str = ""              # 人类可读错误信息
    file: Optional[str] = None     # 相对工作区路径
    graph_id: Optional[str] = None
    location: Optional[str] = None # UI用可读定位（如 “容器A > 图 'xxx' > 节点 'GetPlayer'”）
    node_id: Optional[str] = None
    port: Optional[str] = None
    line_span: Optional[str] = None
    reference: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "category": self.category,
            "code": self.code,
            "message": self.message,
            "file": self.file,
            "graph_id": self.graph_id,
            "location": self.location,
            "node_id": self.node_id,
            "port": self.port,
            "line_span": self.line_span,
            "reference": self.reference,
            "detail": self.detail,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "EngineIssue":
        return EngineIssue(
            level=str(data.get("level", "")),
            category=str(data.get("category", "")),
            code=str(data.get("code", "")),
            message=str(data.get("message", "")),
            file=data.get("file"),
            graph_id=data.get("graph_id"),
            location=data.get("location"),
            node_id=data.get("node_id"),
            port=data.get("port"),
            line_span=data.get("line_span"),
            reference=data.get("reference"),
            detail=data.get("detail") or {},
        )


@dataclass
class ValidationReport:
    """一次校验的聚合报告"""
    issues: List[EngineIssue]
    stats: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)

    def by_level(self) -> Dict[str, List[EngineIssue]]:
        result: Dict[str, List[EngineIssue]] = {}
        for issue in self.issues:
            result.setdefault(issue.level, []).append(issue)
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "stats": self.stats,
            "config": self.config,
        }


