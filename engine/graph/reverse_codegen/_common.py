from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from engine.nodes.node_definition_loader import NodeDef


class ReverseGraphCodeError(ValueError):
    """反向生成 Graph Code 失败（输入图超出当前支持范围或缺少必要信息）。"""


_LOCAL_VAR_RELAY_NODE_ID_PREFIX = "node_localvar_relay_block_"
_COPY_MARKER = "_copy_"


def _is_local_var_relay_node_id(node_id: object) -> bool:
    return isinstance(node_id, str) and node_id.startswith(_LOCAL_VAR_RELAY_NODE_ID_PREFIX)


def _is_data_node_copy(node: object) -> bool:
    return bool(getattr(node, "is_data_node_copy", False))


def _strip_copy_suffix(node_id: str) -> str:
    text = str(node_id or "")
    idx = text.find(_COPY_MARKER)
    return text[:idx] if idx != -1 else text


def _is_layout_artifact_node_id(*, node_id: str, node: object) -> bool:
    # 布局层可能插入：
    # - 局部变量 relay（node_localvar_relay_block_...）
    # - 数据节点副本（is_data_node_copy=True / *_copy_block_*）
    return _is_local_var_relay_node_id(node_id) or _is_data_node_copy(node) or (_COPY_MARKER in str(node_id or ""))


@dataclass(frozen=True, slots=True)
class ReverseGraphCodeOptions:
    """GraphModel -> Graph Code 的生成选项。"""

    scope: str = "server"  # "server" | "client"
    class_name: str = ""  # 默认使用 graph_name；为空时自动推导
    include_sys_path_bootstrap: bool = True
    include_validate_node_graph_in_init: bool = True
    include_main_validate_cli: bool = True
    # 若开启：对基础算术节点（加减乘除）在反向生成时尽量输出 `a + b` 形式（带括号）。
    # 默认关闭以保持 canonical 显式节点调用输出，避免全仓库风格突变与大 diff。
    prefer_arithmetic_operators: bool = False


def _resolve_node_def(*, node: object, node_library: Dict[str, NodeDef]) -> NodeDef:
    category = str(getattr(node, "category", "") or "")
    title = str(getattr(node, "title", "") or "")
    key = f"{category}/{title}"
    if key in node_library:
        return node_library[key]
    composite_key = f"复合节点/{title}"
    if composite_key in node_library:
        return node_library[composite_key]
    raise ReverseGraphCodeError(f"无法在节点库中定位 NodeDef：{key!r}")


def _try_resolve_node_def(*, node: object, node_library: Dict[str, NodeDef]) -> Optional[NodeDef]:
    """尽量解析 NodeDef；失败时返回 None（避免用 try/except 做控制流）。"""

    category = str(getattr(node, "category", "") or "")
    title = str(getattr(node, "title", "") or "")
    key = f"{category}/{title}"
    if key in node_library:
        return node_library[key]
    composite_key = f"复合节点/{title}"
    if composite_key in node_library:
        return node_library[composite_key]
    return None

