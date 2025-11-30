from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

import ast

from engine.graph.models.graph_model import GraphModel  # type: ignore

if TYPE_CHECKING:
    # 仅用于类型标注，避免在运行时引入额外依赖或循环导入
    from engine.resources.package_interfaces import PackageLike  # type: ignore
    from engine.resources.resource_manager import ResourceManager  # type: ignore
    from engine.nodes.node_definition_loader import NodeDef  # type: ignore


@dataclass
class ValidationContext:
    """规则执行上下文（跨规则共享只读数据）"""

    # 文件/图级上下文（节点图验证）
    workspace_path: Path
    file_path: Optional[Path] = None
    graph_model: Optional["GraphModel"] = None
    is_composite: bool = False
    virtual_pin_mappings: Dict[Tuple[str, str], bool] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)

    # 包级 / 资源级上下文（存档综合验证）
    package: Optional["PackageLike"] = None
    resource_manager: Optional["ResourceManager"] = None
    node_library: Dict[str, "NodeDef"] = field(default_factory=dict)
    verbose: bool = False
    ast_cache: Dict[Path, ast.AST] = field(default_factory=dict)
