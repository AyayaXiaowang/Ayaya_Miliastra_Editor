from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GraphCodeRewriteConfig:
    """Graph Code/复合节点语法糖归一化的统一配置。

    设计目标：
    - 将“改写参数上限（列表/字典元素数等）+ enable_shared_composite_sugars 开关策略”
      集中为单一真源，避免解析入口与 validate 规则两侧口径漂移。
    """

    max_list_literal_elements: int
    max_dict_literal_pairs: int
    enable_shared_composite_sugars: bool


# 约定：这些上限属于“语法糖归一化”的改写器能力边界，不属于 validate 阈值（warning/error）范畴。
DEFAULT_MAX_LIST_LITERAL_ELEMENTS = 100
DEFAULT_MAX_DICT_LITERAL_PAIRS = 50


def build_graph_code_rewrite_config(*, is_composite: bool) -> GraphCodeRewriteConfig:
    """构建当前文件类型对应的改写配置。

    Args:
        is_composite: 是否为复合节点定义文件。

    Returns:
        GraphCodeRewriteConfig
    """
    return GraphCodeRewriteConfig(
        max_list_literal_elements=DEFAULT_MAX_LIST_LITERAL_ELEMENTS,
        max_dict_literal_pairs=DEFAULT_MAX_DICT_LITERAL_PAIRS,
        # 共享复合节点语法糖：仅普通节点图启用；复合节点文件默认关闭以避免“复合内嵌套复合”。
        enable_shared_composite_sugars=(not bool(is_composite)),
    )


__all__ = [
    "GraphCodeRewriteConfig",
    "DEFAULT_MAX_LIST_LITERAL_ELEMENTS",
    "DEFAULT_MAX_DICT_LITERAL_PAIRS",
    "build_graph_code_rewrite_config",
]


