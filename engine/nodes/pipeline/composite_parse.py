from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from engine.nodes.node_definition_loader import NodeDef
from engine.graph.composite_code_parser import CompositeCodeParser
from engine.nodes.advanced_node_features import CompositeNodeConfig


def parse_composite_defs(
    files: List[Path],
    base_node_library: Dict[str, NodeDef],
    workspace_path: Path,
    verbose: bool = False,
) -> Dict[str, NodeDef]:
    """
    解析复合节点定义为 NodeDef 字典。

    说明：直接使用 CompositeCodeParser 解析函数格式复合节点文件，
    基于解析得到的 VirtualPinConfig 列表构建 NodeDef，保持与旧管理器行为一致：
    - 输入/输出名称来源于虚拟引脚名称
    - 端口类型：流程口统一为“流程”，数据口使用虚拟引脚声明类型
    - 节点类别自动判断：有输入流程→执行节点；仅有输出流程→事件节点；否则查询节点
    - 标记 is_composite=True 且带 composite_id
    """
    if not isinstance(workspace_path, Path):
        raise TypeError("workspace_path 必须是 pathlib.Path 实例")

    parser = CompositeCodeParser(node_library=base_node_library, verbose=verbose)

    def _to_node_def(composite: CompositeNodeConfig) -> NodeDef:
        """转换复合节点配置为 NodeDef（使用统一的转换函数）"""
        from engine.nodes.advanced_node_features import convert_composite_to_node_def
        return convert_composite_to_node_def(composite)

    library: Dict[str, NodeDef] = {}
    for fp in files or []:
        composite_cfg = parser.parse_file(fp)
        node_def = _to_node_def(composite_cfg)
        key = f"复合节点/{node_def.name}"
        library[key] = node_def

    return library

