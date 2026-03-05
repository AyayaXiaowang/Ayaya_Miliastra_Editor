from __future__ import annotations
from engine.nodes.node_spec import node_spec
from plugins.nodes.shared.server_查询节点_impl_helpers import *
from engine.utils.logging.logger import log_info

@node_spec(
    name="获取角色属性",
    category="查询节点",
    inputs=[("目标实体", "实体")],
    outputs=[("等级", "整数"), ("当前生命值", "浮点数"), ("上限生命值", "浮点数"), ("当前攻击力", "浮点数"), ("基础攻击力", "浮点数"), ("当前防御力", "浮点数"), ("基础防御力", "浮点数"), ("受打断值上限", "浮点数"), ("当前受打断值", "浮点数"), ("当前受打断状态", "枚举")],
    description="获取角色实体的基础属性",
    doc_reference="服务器节点/查询节点/查询节点.md",
    output_enum_options={
        "当前受打断状态": [
            "抗打断状态",
            "易受打断状态",
            "受保护状态",
        ],
    },
)
def 获取角色属性(game, 目标实体):
    """获取角色实体的基础属性"""
    # 本地测试（MockRuntime）最小语义：
    # - 允许通过自定义变量注入各属性（变量名与端口显示名一致）；
    # - 未设置时回退为 0/0.0，受打断状态回退为“抗打断状态”。
    get_custom = getattr(game, "get_custom_variable", None)
    if not callable(get_custom):
        return 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, "抗打断状态"

    等级 = int(get_custom(目标实体, "等级", 0) or 0)
    当前生命值 = float(get_custom(目标实体, "当前生命值", 0.0) or 0.0)
    上限生命值 = float(get_custom(目标实体, "上限生命值", 0.0) or 0.0)
    当前攻击力 = float(get_custom(目标实体, "当前攻击力", 0.0) or 0.0)
    基础攻击力 = float(get_custom(目标实体, "基础攻击力", 0.0) or 0.0)
    当前防御力 = float(get_custom(目标实体, "当前防御力", 0.0) or 0.0)
    基础防御力 = float(get_custom(目标实体, "基础防御力", 0.0) or 0.0)
    受打断值上限 = float(get_custom(目标实体, "受打断值上限", 0.0) or 0.0)
    当前受打断值 = float(get_custom(目标实体, "当前受打断值", 0.0) or 0.0)
    当前受打断状态 = str(get_custom(目标实体, "当前受打断状态", "抗打断状态") or "抗打断状态")
    if 当前受打断状态 not in {"抗打断状态", "易受打断状态", "受保护状态"}:
        当前受打断状态 = "抗打断状态"

    return (
        等级,
        当前生命值,
        上限生命值,
        当前攻击力,
        基础攻击力,
        当前防御力,
        基础防御力,
        受打断值上限,
        当前受打断值,
        当前受打断状态,
    )
